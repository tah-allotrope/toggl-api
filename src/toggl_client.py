# DEPRECATED: Legacy Streamlit Toggl client. See functions/toggl_client.py.
"""
Toggl Track API v9 client with rate limiting and retry logic.

Handles authentication, respects plan-tier limits (auto-detected from response
headers: 30 req/hr Free, 600 req/hr Premium), and provides methods for fetching
time entries, projects, tags, tasks, clients, and reports.
"""

import time
import json
import os
import io
import csv
import hashlib
from datetime import datetime, date
from pathlib import Path
from base64 import b64encode

import requests
from dotenv import load_dotenv

load_dotenv()


def _get_toggl_token() -> str:
    """Resolve TOGGL_API_TOKEN from st.secrets (Streamlit Cloud) or .env."""
    try:
        import streamlit as st

        token = st.secrets.get("TOGGL_API_TOKEN", "")
        if token:
            return token
    except Exception:
        pass
    return os.getenv("TOGGL_API_TOKEN", "")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://api.track.toggl.com"
API_V9 = f"{BASE_URL}/api/v9"
REPORTS_V3 = f"{BASE_URL}/reports/api/v3"

# Conservative defaults — upgraded at runtime via header auto-detection.
# Free: 30/hr, Starter: 240/hr, Premium: 600/hr, Enterprise: higher.
MAX_REQUESTS_PER_HOUR_DEFAULT = 30
SAFE_INTERVAL_SECONDS = 1.1  # slightly over 1 req/sec burst protection


class RateLimiter:
    """
    Sliding-window rate limiter that respects both per-second and per-hour limits.

    The hourly quota is auto-detected from Toggl's X-Toggl-Quota-Remaining and
    X-Toggl-Quota-Resets-In response headers. On the first response we observe
    the remaining count and infer the window ceiling, then keep it updated.
    This means Premium users (600/hr) automatically get the higher budget without
    any manual configuration.
    """

    def __init__(
        self,
        max_per_hour: int = MAX_REQUESTS_PER_HOUR_DEFAULT,
        min_interval: float = SAFE_INTERVAL_SECONDS,
    ):
        self.max_per_hour = max_per_hour
        self.min_interval = min_interval
        self._timestamps: list[float] = []
        self._last_request: float = 0
        # Tracks whether we've upgraded the quota ceiling from headers yet.
        self._quota_detected: bool = False

    def clear_stale(self):
        """Remove timestamps older than 1 hour. Call at the start of each year's fetch."""
        one_hour_ago = time.time() - 3600
        self._timestamps = [t for t in self._timestamps if t > one_hour_ago]

    def update_from_headers(self, headers: dict):
        """
        Parse Toggl quota headers from an API response and update the hourly
        limit if we detect a higher ceiling than the current setting.

        Toggl returns:
          X-Toggl-Quota-Remaining  — requests left in the current hour window
          X-Toggl-Quota-Resets-In  — seconds until the window resets

        We infer the total ceiling by adding the requests we've already made
        (len of timestamps still in the window) to the remaining count.
        """
        remaining_str = headers.get("X-Toggl-Quota-Remaining")
        if remaining_str is None:
            return

        try:
            remaining = int(remaining_str)
        except (ValueError, TypeError):
            return

        # Estimate ceiling = consumed so far + remaining
        one_hour_ago = time.time() - 3600
        consumed = len([t for t in self._timestamps if t > one_hour_ago])
        inferred_ceiling = consumed + remaining

        # Only ever upgrade the ceiling, never downgrade (avoids jitter from
        # late-in-window observations where consumed+remaining < real ceiling).
        if inferred_ceiling > self.max_per_hour:
            if not self._quota_detected:
                print(
                    f"[rate-limit] Detected quota ceiling: {inferred_ceiling} req/hr "
                    f"(was {self.max_per_hour}). Upgrading."
                )
            self.max_per_hour = inferred_ceiling
            self._quota_detected = True

    def wait_if_needed(self):
        """Block until it's safe to make the next request."""
        now = time.time()

        # Enforce minimum interval between requests (burst protection)
        elapsed = now - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        # Enforce hourly quota — drop timestamps outside the rolling window
        one_hour_ago = time.time() - 3600
        self._timestamps = [t for t in self._timestamps if t > one_hour_ago]

        if len(self._timestamps) >= self.max_per_hour:
            wait_time = self._timestamps[0] - one_hour_ago + 1
            print(
                f"[rate-limit] Hourly quota ({self.max_per_hour}/hr) reached. Waiting {wait_time:.0f}s..."
            )
            time.sleep(wait_time)

        self._last_request = time.time()
        self._timestamps.append(self._last_request)


class TogglClient:
    """Toggl Track API client with built-in rate limiting and auto-quota detection."""

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or _get_toggl_token()
        if not self.api_token:
            raise ValueError(
                "TOGGL_API_TOKEN not set. "
                "Copy .env.example to .env and paste your token from https://track.toggl.com/profile"
            )
        self._session = requests.Session()
        self._session.auth = (self.api_token, "api_token")
        self._session.headers.update({"Content-Type": "application/json"})
        self._limiter = RateLimiter()

        # Cached after first call
        self._me: dict | None = None
        self._workspace_id: int | None = None

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    def _request(
        self, method: str, url: str, retries: int = 3, **kwargs
    ) -> requests.Response:
        """
        Make a rate-limited HTTP request with retry on 429/402.
        Updates the rate limiter's quota ceiling from response headers on each call.
        """
        for attempt in range(retries):
            self._limiter.wait_if_needed()
            resp = self._session.request(method, url, **kwargs)

            # Update quota detection on every response (even errors carry headers)
            self._limiter.update_from_headers(dict(resp.headers))

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(
                    f"[429] Rate limited. Retrying in {wait}s (attempt {attempt + 1}/{retries})"
                )
                time.sleep(wait)
                continue

            if resp.status_code == 402:
                remaining = resp.headers.get("X-Toggl-Quota-Remaining", "?")
                resets_in = resp.headers.get("X-Toggl-Quota-Resets-In", "?")
                print(
                    f"[402] Quota exceeded. Remaining: {remaining}, resets in: {resets_in}s"
                )
                if attempt < retries - 1:
                    wait = int(resets_in) if resets_in != "?" else 120
                    print(f"  Waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue

            resp.raise_for_status()
            return resp

        raise RuntimeError(f"Request failed after {retries} retries: {method} {url}")

    def _get(self, url: str, **kwargs) -> requests.Response:
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs) -> requests.Response:
        return self._request("POST", url, **kwargs)

    # ------------------------------------------------------------------
    # User & Workspace
    # ------------------------------------------------------------------

    def get_me(self) -> dict:
        """Fetch the authenticated user profile. Cached after first call."""
        if self._me is None:
            resp = self._get(f"{API_V9}/me")
            self._me = resp.json()
        assert self._me is not None
        return self._me

    def get_workspace_id(self) -> int:
        """Return the user's default workspace ID."""
        if self._workspace_id is None:
            me = self.get_me()
            self._workspace_id = me["default_workspace_id"]
        assert self._workspace_id is not None
        return self._workspace_id

    # ------------------------------------------------------------------
    # Projects, Tags, Clients, Tasks (workspace-specific)
    # ------------------------------------------------------------------

    def get_projects(self, workspace_id: int | None = None) -> list[dict]:
        """
        Fetch all projects for the workspace.
        With Premium, the response includes billable, rate, currency, fixed_fee,
        estimated_hours, estimated_seconds, auto_estimates, recurring, and template fields.
        """
        wid = workspace_id or self.get_workspace_id()
        resp = self._get(
            f"{API_V9}/workspaces/{wid}/projects", params={"per_page": 200}
        )
        return resp.json() if resp.status_code == 200 else []

    def get_tags(self, workspace_id: int | None = None) -> list[dict]:
        """
        Fetch all tags for the workspace.
        Returns richer metadata than before: creator_id, at, deleted_at.
        """
        wid = workspace_id or self.get_workspace_id()
        resp = self._get(f"{API_V9}/workspaces/{wid}/tags")
        return resp.json() if resp.status_code == 200 else []

    def get_clients(self, workspace_id: int | None = None) -> list[dict]:
        """Fetch all clients for the workspace."""
        wid = workspace_id or self.get_workspace_id()
        resp = self._get(f"{API_V9}/workspaces/{wid}/clients")
        if resp.status_code == 200:
            data = resp.json()
            # API returns null when there are no clients
            return data if isinstance(data, list) else []
        return []

    def get_tasks(self, project_id: int, workspace_id: int | None = None) -> list[dict]:
        """
        Fetch all tasks for a specific project (Premium feature).
        Returns [] on 403 (project has no tasks / not Premium) without raising.
        """
        wid = workspace_id or self.get_workspace_id()
        try:
            resp = self._get(
                f"{API_V9}/workspaces/{wid}/projects/{project_id}/tasks",
                params={"per_page": 200},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (403, 404):
                return []
            raise
        return []

    def get_all_tasks(
        self, projects: list[dict], workspace_id: int | None = None
    ) -> list[dict]:
        """
        Fetch tasks for all projects that have tasks enabled (Premium).
        Skips projects where tasks return 403/404 silently.
        Returns a flat list of all task dicts.
        """
        all_tasks: list[dict] = []
        for project in projects:
            project_id = project.get("id")
            if not project_id:
                continue
            tasks = self.get_tasks(project_id, workspace_id)
            # Stamp each task with project info for denormalization
            for t in tasks:
                t.setdefault("project_id", project_id)
                t.setdefault("project_name", project.get("name", ""))
            all_tasks.extend(tasks)
        return all_tasks

    # ------------------------------------------------------------------
    # Time Entries (user-specific endpoint — separate 30/hr quota)
    # ------------------------------------------------------------------

    def get_time_entries(self, start_date: str, end_date: str) -> list[dict]:
        """
        Fetch time entries between start_date and end_date (YYYY-MM-DD).
        Uses the user-specific endpoint /api/v9/me/time_entries.
        Note: this endpoint has its own 30/hr user quota separate from org quota.
        """
        resp = self._get(
            f"{API_V9}/me/time_entries",
            params={"start_date": start_date, "end_date": end_date},
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Reports API v3 — Detailed Report (workspace-specific, org quota)
    # ------------------------------------------------------------------

    def get_detailed_report_json(
        self,
        start_date: str,
        end_date: str,
        workspace_id: int | None = None,
        page_size: int = 50,
        first_row_number: int | None = None,
    ) -> tuple[list[dict], dict]:
        """
        Fetch one page of the detailed report as JSON.
        Always uses enrich_response=True to get maximum field coverage.
        Returns (time_entries, response_headers).
        """
        wid = workspace_id or self.get_workspace_id()
        body: dict = {
            "start_date": start_date,
            "end_date": end_date,
            "page_size": page_size,
            "enrich_response": True,
            "order_by": "date",
            "order_dir": "ASC",
        }
        if first_row_number is not None:
            body["first_row_number"] = first_row_number

        resp = self._post(
            f"{REPORTS_V3}/workspace/{wid}/search/time_entries", json=body
        )
        data = resp.json()
        # API returns null on empty result sets
        return (data if isinstance(data, list) else []), dict(resp.headers)

    def get_all_detailed_entries(
        self, start_date: str, end_date: str, workspace_id: int | None = None
    ) -> list[dict]:
        """
        Fetch ALL detailed report rows for a date range, handling pagination.
        Uses 50-entry pages and follows X-Next-Row-Number until exhausted.
        Each row contains nested time_entries; call _flatten_report_entries() to expand.
        """
        all_rows: list[dict] = []
        first_row_number: int | None = None

        while True:
            rows, headers = self.get_detailed_report_json(
                start_date,
                end_date,
                workspace_id,
                page_size=50,
                first_row_number=first_row_number,
            )
            if not rows:
                break

            all_rows.extend(rows)

            next_row = headers.get("X-Next-Row-Number")
            if next_row:
                first_row_number = int(next_row)
            else:
                break

        return all_rows

    def export_detailed_csv(
        self, start_date: str, end_date: str, workspace_id: int | None = None
    ) -> bytes:
        """
        Export detailed report as CSV bytes — equivalent to manual Toggl CSV export.
        Single API call, no pagination. Used by the original CSV-based sync path.
        """
        wid = workspace_id or self.get_workspace_id()
        body = {
            "start_date": start_date,
            "end_date": end_date,
        }
        resp = self._post(
            f"{REPORTS_V3}/workspace/{wid}/search/time_entries.csv",
            json=body,
        )
        return resp.content

    # ------------------------------------------------------------------
    # Summary Report
    # ------------------------------------------------------------------

    def get_summary_report(
        self,
        start_date: str,
        end_date: str,
        workspace_id: int | None = None,
        grouping: str = "projects",
        sub_grouping: str = "time_entries",
    ) -> list[dict]:
        """Fetch summary report grouped by projects/tags."""
        wid = workspace_id or self.get_workspace_id()
        body = {
            "start_date": start_date,
            "end_date": end_date,
            "grouping": grouping,
            "sub_grouping": sub_grouping,
        }
        resp = self._post(
            f"{REPORTS_V3}/workspace/{wid}/summary/time_entries", json=body
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Flatten helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_report_entries(
        report_rows: list[dict],
        tag_map: dict[int, str] | None = None,
        task_map: dict[int, str] | None = None,
        client_map: dict[int, str] | None = None,
        workspace_id: int | None = None,
    ) -> list[dict]:
        """
        Flatten Reports API v3 detailed response rows into a list of flat dicts
        compatible with upsert_time_entries.

        The Reports API v3 nests actual time entries inside each row's
        'time_entries' array. We merge row-level metadata (description, project,
        tags, task, client) with each individual time entry sub-record.

        New fields captured vs. the original CSV-based version:
          - toggl_id: the native Toggl integer entry ID (no more synthetic IDs)
          - task_id / task_name: Premium task assignment
          - client_name: denormalized from the row's project->client chain
          - user_id: Toggl user ID who created the entry
          - at: last-updated ISO timestamp (absent from CSV)
          - tag_ids: real integer tag ID array (CSV only has names)
          - project_id: real integer project ID (CSV omits this)

        Args:
            report_rows: raw rows from get_all_detailed_entries()
            tag_map: {tag_id: tag_name} for resolving names from IDs
            task_map: {task_id: task_name} for resolving task names from IDs
            client_map: {client_id: client_name} for resolving client names
            workspace_id: workspace to stamp on each entry
        """
        flat: list[dict] = []
        tag_map = tag_map or {}
        task_map = task_map or {}
        client_map = client_map or {}

        for row in report_rows:
            # --- Row-level fields (shared across all sub-entries in this row) ---
            tag_ids: list[int] = row.get("tag_ids") or []
            tag_names: list[str] = [tag_map.get(tid, str(tid)) for tid in tag_ids]

            task_id: int | None = row.get("task_id")
            task_name: str = ""
            if task_id:
                _raw_task_name: str | None = task_map.get(task_id) or row.get(
                    "task_name"
                )
                task_name = _raw_task_name if _raw_task_name is not None else ""

            # client_id may appear on the row when enrich_response=True
            client_id: int | None = row.get("client_id")
            client_name: str = row.get("client_name", "")
            if client_id and not client_name:
                client_name = client_map.get(client_id, "")

            project_id: int | None = row.get("project_id")
            project_name: str = row.get("project_name", "")
            description: str = row.get("description", "")
            billable: bool = bool(row.get("billable", False))

            # --- Expand each nested time entry sub-record ---
            for te in row.get("time_entries", []):
                flat.append(
                    {
                        # Native Toggl entry ID — the core improvement over CSV
                        "toggl_id": te.get("id"),
                        # Keep a synthetic id field for backward compat; callers
                        # can decide which to use as the SQLite PK during upsert.
                        "id": te.get("id"),
                        "description": description,
                        "start": te.get("start", ""),
                        "stop": te.get("stop", ""),
                        "duration": te.get("seconds", 0),
                        "project_id": project_id,
                        "project_name": project_name,
                        "workspace_id": workspace_id,
                        "tags": tag_names,
                        "tag_ids": tag_ids,
                        "billable": billable,
                        "at": te.get("at", ""),
                        # New enrichment fields
                        "task_id": task_id,
                        "task_name": task_name,
                        "client_name": client_name,
                        "user_id": te.get("user_id"),
                    }
                )
        return flat

    # ------------------------------------------------------------------
    # Convenience: Fetch a full year — original CSV path (preserved)
    # ------------------------------------------------------------------

    def fetch_year_csv(self, year: int) -> bytes:
        """Export a full year as CSV via the Reports API (single request)."""
        today = date.today()
        end = f"{year}-12-31" if year < today.year else today.isoformat()
        return self.export_detailed_csv(f"{year}-01-01", end)

    def fetch_year_entries(
        self, year: int, tag_map: dict[int, str] | None = None
    ) -> list[dict]:
        """
        Fetch all time entries for a given year via CSV export (single API call).
        Parses the CSV and returns flat dicts compatible with upsert_time_entries.
        This is the fast legacy path: 1 API call per year, but drops field richness.
        """
        csv_bytes = self.fetch_year_csv(year)
        csv_text = csv_bytes.decode("utf-8-sig")  # Toggl CSV may have BOM

        if not csv_text.strip():
            print(f"  {year}: empty CSV (no entries)")
            return []

        reader = csv.DictReader(io.StringIO(csv_text))
        entries = []
        for row in reader:
            # Parse duration from "HH:MM:SS" to seconds
            duration_sec = 0
            dur_str = row.get("Duration", "0:00:00")
            try:
                parts = dur_str.split(":")
                duration_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except (ValueError, IndexError):
                pass

            start_date_str = row.get("Start date", "")
            start_time = row.get("Start time", "00:00:00")
            start_iso = f"{start_date_str}T{start_time}" if start_date_str else ""

            end_date_str = row.get("End date", "")
            end_time = row.get("End time", "00:00:00")
            stop_iso = f"{end_date_str}T{end_time}" if end_date_str else ""

            tags_str = row.get("Tags", "")
            tags = (
                [t.strip() for t in tags_str.split(",") if t.strip()]
                if tags_str
                else []
            )

            description = row.get("Description", "")
            project = row.get("Project", "")
            id_seed = f"{start_iso}|{stop_iso}|{description}|{project}|{duration_sec}"
            synth_id = int(hashlib.sha256(id_seed.encode()).hexdigest()[:15], 16)

            entries.append(
                {
                    "id": synth_id,
                    "toggl_id": None,  # CSV path — native ID unknown
                    "description": description,
                    "start": start_iso,
                    "stop": stop_iso,
                    "duration": duration_sec,
                    "project_id": None,
                    "project_name": project,
                    "workspace_id": None,
                    "tags": tags,
                    "tag_ids": [],
                    "billable": row.get("Billable", "No") == "Yes",
                    "at": "",
                    "task_id": None,
                    "task_name": "",
                    "client_name": "",
                    "user_id": None,
                }
            )

        print(f"  {year}: parsed {len(entries)} entries from CSV")
        return entries

    # ------------------------------------------------------------------
    # Convenience: Fetch a full year — rich JSON path (enrichment phase)
    # ------------------------------------------------------------------

    def fetch_year_entries_json(
        self,
        year: int,
        tag_map: dict[int, str] | None = None,
        task_map: dict[int, str] | None = None,
        client_map: dict[int, str] | None = None,
        workspace_id: int | None = None,
    ) -> list[dict]:
        """
        Fetch all time entries for a given year via the Reports API v3 JSON
        endpoint with enrich_response=True. This pulls the full field set:
        native Toggl IDs, project_id, tag_ids, task_id, client_name, at timestamp.

        Uses multiple API calls (50 entries/page) — budget ~N/50 calls per year.
        Only call this during the enrichment sync window while on Premium.
        """
        today = date.today()
        end = f"{year}-12-31" if year < today.year else today.isoformat()
        start = f"{year}-01-01"

        self._limiter.clear_stale()

        wid = workspace_id or self.get_workspace_id()
        rows = self.get_all_detailed_entries(start, end, workspace_id=wid)

        entries = self._flatten_report_entries(
            rows,
            tag_map=tag_map,
            task_map=task_map,
            client_map=client_map,
            workspace_id=wid,
        )

        print(
            f"  {year}: fetched {len(entries)} entries via JSON ({len(rows)} report rows)"
        )
        return entries
