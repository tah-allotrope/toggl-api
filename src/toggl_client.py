"""
Toggl Track API v9 client with rate limiting and retry logic.

Handles authentication, respects Free plan limits (30 req/hr per workspace),
and provides methods for fetching time entries, projects, tags, and reports.
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
    # Streamlit Cloud secrets take priority
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

# Free-plan limits
MAX_REQUESTS_PER_HOUR = 30
SAFE_INTERVAL_SECONDS = 1.1  # slightly over 1 req/sec to stay safe


class RateLimiter:
    """Sliding-window rate limiter that respects both per-second and per-hour limits."""

    def __init__(self, max_per_hour: int = MAX_REQUESTS_PER_HOUR, min_interval: float = SAFE_INTERVAL_SECONDS):
        self.max_per_hour = max_per_hour
        self.min_interval = min_interval
        self._timestamps: list[float] = []
        self._last_request: float = 0

    def wait_if_needed(self):
        """Block until it's safe to make the next request."""
        now = time.time()

        # Enforce minimum interval between requests (1 req/sec)
        elapsed = now - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        # Enforce hourly quota -- drop timestamps older than 1 hour
        one_hour_ago = time.time() - 3600
        self._timestamps = [t for t in self._timestamps if t > one_hour_ago]

        if len(self._timestamps) >= self.max_per_hour:
            # Wait until the oldest request falls outside the window
            wait_time = self._timestamps[0] - one_hour_ago + 1
            print(f"[rate-limit] Hourly quota reached. Waiting {wait_time:.0f}s...")
            time.sleep(wait_time)

        self._last_request = time.time()
        self._timestamps.append(self._last_request)


class TogglClient:
    """Toggl Track API client with built-in rate limiting."""

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

    def _request(self, method: str, url: str, retries: int = 3, **kwargs) -> requests.Response:
        """Make a rate-limited HTTP request with retry on 429."""
        for attempt in range(retries):
            self._limiter.wait_if_needed()
            resp = self._session.request(method, url, **kwargs)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"[429] Rate limited. Retrying in {wait}s (attempt {attempt + 1}/{retries})")
                time.sleep(wait)
                continue

            if resp.status_code == 402:
                remaining = resp.headers.get("X-Toggl-Quota-Remaining", "?")
                resets_in = resp.headers.get("X-Toggl-Quota-Resets-In", "?")
                print(f"[402] Quota exceeded. Remaining: {remaining}, resets in: {resets_in}s")
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
    # Projects & Tags (workspace-specific)
    # ------------------------------------------------------------------

    def get_projects(self, workspace_id: int | None = None) -> list[dict]:
        """Fetch all projects for the workspace."""
        wid = workspace_id or self.get_workspace_id()
        resp = self._get(f"{API_V9}/workspaces/{wid}/projects", params={"per_page": 200})
        return resp.json() if resp.status_code == 200 else []

    def get_tags(self, workspace_id: int | None = None) -> list[dict]:
        """Fetch all tags for the workspace."""
        wid = workspace_id or self.get_workspace_id()
        resp = self._get(f"{API_V9}/workspaces/{wid}/tags")
        return resp.json() if resp.status_code == 200 else []

    # ------------------------------------------------------------------
    # Time Entries (user-specific endpoint -- separate 30/hr quota)
    # ------------------------------------------------------------------

    def get_time_entries(self, start_date: str, end_date: str) -> list[dict]:
        """
        Fetch time entries between start_date and end_date (YYYY-MM-DD).
        Uses the user-specific endpoint /api/v9/me/time_entries.
        """
        resp = self._get(
            f"{API_V9}/me/time_entries",
            params={"start_date": start_date, "end_date": end_date},
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Reports API v3 -- Detailed Report (workspace-specific)
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
        Fetch detailed report as JSON with pagination support.
        Returns (time_entries, response_headers).
        """
        wid = workspace_id or self.get_workspace_id()
        body = {
            "start_date": start_date,
            "end_date": end_date,
            "page_size": page_size,
            "enrich_response": True,
            "order_by": "date",
            "order_dir": "ASC",
        }
        if first_row_number is not None:
            body["first_row_number"] = first_row_number

        resp = self._post(f"{REPORTS_V3}/workspace/{wid}/search/time_entries", json=body)
        return resp.json(), dict(resp.headers)

    def get_all_detailed_entries(
        self, start_date: str, end_date: str, workspace_id: int | None = None
    ) -> list[dict]:
        """
        Fetch ALL detailed report entries for a date range, handling pagination.
        This uses multiple API calls (50 entries per page).
        """
        all_entries = []
        first_row_number = None

        while True:
            entries, headers = self.get_detailed_report_json(
                start_date, end_date, workspace_id,
                page_size=50, first_row_number=first_row_number,
            )
            if not entries:
                break

            all_entries.extend(entries)

            # Check pagination headers
            next_row = headers.get("X-Next-Row-Number")
            if next_row:
                first_row_number = int(next_row)
            else:
                break

        return all_entries

    def export_detailed_csv(
        self, start_date: str, end_date: str, workspace_id: int | None = None
    ) -> bytes:
        """
        Export detailed report as CSV bytes -- equivalent to manual Toggl CSV export.
        Single API call returns the full dataset (no pagination needed for exports).
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
        self, start_date: str, end_date: str, workspace_id: int | None = None,
        grouping: str = "projects", sub_grouping: str = "time_entries",
    ) -> list[dict]:
        """Fetch summary report grouped by projects/tags."""
        wid = workspace_id or self.get_workspace_id()
        body = {
            "start_date": start_date,
            "end_date": end_date,
            "grouping": grouping,
            "sub_grouping": sub_grouping,
        }
        resp = self._post(f"{REPORTS_V3}/workspace/{wid}/summary/time_entries", json=body)
        return resp.json()

    # ------------------------------------------------------------------
    # Convenience: Fetch a full year
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_report_entries(
        report_rows: list[dict],
        tag_map: dict[int, str] | None = None,
    ) -> list[dict]:
        """
        Flatten Reports API v3 detailed response into the same flat dict format
        that the Time Entries API v9 returns.

        Reports API nests actual time entries inside each row's 'time_entries' array.
        We merge the row-level metadata (description, project, tags) with each
        individual time entry so upsert_time_entries can process them uniformly.

        tag_map: optional {tag_id: tag_name} for resolving tag IDs to names.
        """
        flat = []
        tag_map = tag_map or {}
        for row in report_rows:
            tag_ids = row.get("tag_ids") or []
            tag_names = [tag_map.get(tid, str(tid)) for tid in tag_ids]
            for te in row.get("time_entries", []):
                flat.append({
                    "id": te["id"],
                    "description": row.get("description", ""),
                    "start": te.get("start", ""),
                    "stop": te.get("stop", ""),
                    "duration": te.get("seconds", 0),
                    "project_id": row.get("project_id"),
                    "project_name": row.get("project_name", ""),
                    "workspace_id": None,  # filled from client context if needed
                    "tags": tag_names,
                    "tag_ids": tag_ids,
                    "billable": row.get("billable", False),
                    "at": te.get("at", ""),
                })
        return flat

    def fetch_year_entries(
        self, year: int, tag_map: dict[int, str] | None = None
    ) -> list[dict]:
        """
        Fetch all time entries for a given year via CSV export (single API call).
        Parses the CSV and returns flat dicts compatible with upsert_time_entries.
        This is the most efficient approach: 1 API call per year.
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

            # Combine Start date + Start time into ISO start timestamp
            start_date = row.get("Start date", "")
            start_time = row.get("Start time", "00:00:00")
            start_iso = f"{start_date}T{start_time}" if start_date else ""

            end_date = row.get("End date", "")
            end_time = row.get("End time", "00:00:00")
            stop_iso = f"{end_date}T{end_time}" if end_date else ""

            # Tags come as comma-separated string in CSV
            tags_str = row.get("Tags", "")
            tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

            # Generate a deterministic synthetic ID from entry content.
            # The CSV export doesn't include Toggl's internal entry ID, so we
            # hash the key fields to produce a stable integer for upsert.
            description = row.get("Description", "")
            project = row.get("Project", "")
            id_seed = f"{start_iso}|{stop_iso}|{description}|{project}|{duration_sec}"
            synth_id = int(hashlib.sha256(id_seed.encode()).hexdigest()[:15], 16)

            entries.append({
                "id": synth_id,
                "description": description,
                "start": start_iso,
                "stop": stop_iso,
                "duration": duration_sec,
                "project_id": None,  # CSV doesn't include project IDs
                "project_name": project,
                "workspace_id": None,
                "tags": tags,
                "tag_ids": [],
                "billable": row.get("Billable", "No") == "Yes",
                "at": "",
            })

        print(f"  {year}: parsed {len(entries)} entries from CSV")
        return entries

    def fetch_year_csv(self, year: int) -> bytes:
        """Export a full year as CSV via the Reports API (single request)."""
        today = date.today()
        end = f"{year}-12-31" if year < today.year else today.isoformat()
        return self.export_detailed_csv(f"{year}-01-01", end)
