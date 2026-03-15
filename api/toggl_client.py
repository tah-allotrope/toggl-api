"""
Toggl Track API v9 client with rate limiting and retry logic.

Handles authentication, respects plan-tier limits (auto-detected from response
headers: 30 req/hr Free, 600 req/hr Premium), and provides methods for fetching
time entries, projects, tags, tasks, clients, and reports.
"""

import csv
import hashlib
import io
import os
import time
from base64 import b64encode
from datetime import date, datetime

import requests
from dotenv import load_dotenv

load_dotenv()


def _get_toggl_token() -> str:
    """Resolve TOGGL_API_TOKEN from environment only."""
    return os.getenv("TOGGL_API_TOKEN", "")


BASE_URL = "https://api.track.toggl.com"
API_V9 = f"{BASE_URL}/api/v9"
REPORTS_V3 = f"{BASE_URL}/reports/api/v3"

MAX_REQUESTS_PER_HOUR_DEFAULT = 30
SAFE_INTERVAL_SECONDS = 1.1


class RateLimiter:
    """Sliding-window rate limiter with auto-upgrade from Toggl quota headers."""

    def __init__(
        self,
        max_per_hour: int = MAX_REQUESTS_PER_HOUR_DEFAULT,
        min_interval: float = SAFE_INTERVAL_SECONDS,
    ):
        self.max_per_hour = max_per_hour
        self.min_interval = min_interval
        self._timestamps: list[float] = []
        self._last_request: float = 0
        self._quota_detected: bool = False

    def clear_stale(self) -> None:
        """Remove timestamps older than one hour from the rolling window."""
        one_hour_ago = time.time() - 3600
        self._timestamps = [t for t in self._timestamps if t > one_hour_ago]

    def update_from_headers(self, headers: dict) -> None:
        """Parse Toggl headers and upgrade hourly quota if detected higher."""
        remaining_str = headers.get("X-Toggl-Quota-Remaining")
        if remaining_str is None:
            return

        try:
            remaining = int(remaining_str)
        except (ValueError, TypeError):
            return

        one_hour_ago = time.time() - 3600
        consumed = len([t for t in self._timestamps if t > one_hour_ago])
        inferred_ceiling = consumed + remaining

        if inferred_ceiling > self.max_per_hour:
            if not self._quota_detected:
                print(
                    f"[rate-limit] Detected quota ceiling: {inferred_ceiling} req/hr "
                    f"(was {self.max_per_hour}). Upgrading."
                )
            self.max_per_hour = inferred_ceiling
            self._quota_detected = True

    def wait_if_needed(self) -> None:
        """Block until both per-second and per-hour limits are respected."""
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        one_hour_ago = time.time() - 3600
        self._timestamps = [t for t in self._timestamps if t > one_hour_ago]

        if len(self._timestamps) >= self.max_per_hour:
            wait_time = self._timestamps[0] - one_hour_ago + 1
            print(
                f"[rate-limit] Hourly quota ({self.max_per_hour}/hr) reached. "
                f"Waiting {wait_time:.0f}s..."
            )
            time.sleep(wait_time)

        self._last_request = time.time()
        self._timestamps.append(self._last_request)


class TogglClient:
    """Toggl Track API client with built-in rate limiting and auto-quota detection."""

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or _get_toggl_token()
        if not self.api_token:
            raise ValueError("TOGGL_API_TOKEN is not set.")

        self._session = requests.Session()
        self._session.auth = (self.api_token, "api_token")
        self._session.headers.update({"Content-Type": "application/json"})
        self._limiter = RateLimiter()

        self._me: dict | None = None
        self._workspace_id: int | None = None

    def _request(
        self, method: str, url: str, retries: int = 3, **kwargs
    ) -> requests.Response:
        """Make a rate-limited request with retries for 429/402 responses."""
        for attempt in range(retries):
            self._limiter.wait_if_needed()
            resp = self._session.request(method, url, **kwargs)
            self._limiter.update_from_headers(dict(resp.headers))

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(
                    f"[429] Rate limited. Retrying in {wait}s (attempt {attempt + 1}/{retries})"
                )
                time.sleep(wait)
                continue

            if resp.status_code == 402:
                resets_in = resp.headers.get("X-Toggl-Quota-Resets-In", "?")
                if attempt < retries - 1:
                    wait = int(resets_in) if resets_in != "?" else 120
                    print(f"[402] Quota exceeded. Waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue

            resp.raise_for_status()
            return resp

        raise RuntimeError(f"Request failed after {retries} retries: {method} {url}")

    def _get(self, url: str, **kwargs) -> requests.Response:
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs) -> requests.Response:
        return self._request("POST", url, **kwargs)

    def get_me(self) -> dict:
        """Fetch and cache the authenticated user profile."""
        if self._me is None:
            self._me = self._get(f"{API_V9}/me").json()
        return self._me

    def get_workspace_id(self) -> int:
        """Return the default workspace ID for the authenticated user."""
        if self._workspace_id is None:
            self._workspace_id = self.get_me()["default_workspace_id"]
        return self._workspace_id

    def get_projects(self, workspace_id: int | None = None) -> list[dict]:
        wid = workspace_id or self.get_workspace_id()
        return self._get(
            f"{API_V9}/workspaces/{wid}/projects", params={"per_page": 200}
        ).json()

    def get_tags(self, workspace_id: int | None = None) -> list[dict]:
        wid = workspace_id or self.get_workspace_id()
        return self._get(f"{API_V9}/workspaces/{wid}/tags").json()

    def get_clients(self, workspace_id: int | None = None) -> list[dict]:
        wid = workspace_id or self.get_workspace_id()
        data = self._get(f"{API_V9}/workspaces/{wid}/clients").json()
        return data if isinstance(data, list) else []

    def get_tasks(self, project_id: int, workspace_id: int | None = None) -> list[dict]:
        wid = workspace_id or self.get_workspace_id()
        try:
            data = self._get(
                f"{API_V9}/workspaces/{wid}/projects/{project_id}/tasks",
                params={"per_page": 200},
            ).json()
            return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (403, 404):
                return []
            raise

    def get_all_tasks(
        self, projects: list[dict], workspace_id: int | None = None
    ) -> list[dict]:
        all_tasks: list[dict] = []
        for project in projects:
            project_id = project.get("id")
            if not project_id:
                continue
            tasks = self.get_tasks(project_id, workspace_id)
            for task in tasks:
                task.setdefault("project_id", project_id)
                task.setdefault("project_name", project.get("name", ""))
            all_tasks.extend(tasks)
        return all_tasks

    def get_detailed_report_json(
        self,
        start_date: str,
        end_date: str,
        workspace_id: int | None = None,
        page_size: int = 50,
        first_row_number: int | None = None,
    ) -> tuple[list[dict], dict]:
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
        return (data if isinstance(data, list) else []), dict(resp.headers)

    def get_all_detailed_entries(
        self, start_date: str, end_date: str, workspace_id: int | None = None
    ) -> list[dict]:
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

    @staticmethod
    def _flatten_report_entries(
        report_rows: list[dict],
        tag_map: dict[int, str] | None = None,
        task_map: dict[int, str] | None = None,
        client_map: dict[int, str] | None = None,
        workspace_id: int | None = None,
    ) -> list[dict]:
        flat: list[dict] = []
        tag_map = tag_map or {}
        task_map = task_map or {}
        client_map = client_map or {}

        for row in report_rows:
            tag_ids: list[int] = row.get("tag_ids") or []
            tag_names = [tag_map.get(tid, str(tid)) for tid in tag_ids]

            task_id = row.get("task_id")
            raw_task_name = task_map.get(task_id) if task_id else row.get("task_name")
            task_name = raw_task_name or ""

            client_id = row.get("client_id")
            client_name = row.get("client_name", "")
            if client_id and not client_name:
                client_name = client_map.get(client_id, "")

            project_id = row.get("project_id")
            project_name = row.get("project_name", "")
            description = row.get("description", "")
            billable = bool(row.get("billable", False))

            for te in row.get("time_entries", []):
                flat.append(
                    {
                        "id": te.get("id"),
                        "toggl_id": te.get("id"),
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
                        "task_id": task_id,
                        "task_name": task_name,
                        "client_name": client_name,
                        "user_id": te.get("user_id"),
                    }
                )

        return flat

    def fetch_year_entries(
        self,
        year: int,
        tag_map: dict[int, str] | None = None,
        task_map: dict[int, str] | None = None,
        client_map: dict[int, str] | None = None,
        workspace_id: int | None = None,
    ) -> list[dict]:
        """Fetch all entries for a year via Reports JSON endpoint."""
        today = date.today()
        end = f"{year}-12-31" if year < today.year else today.isoformat()
        start = f"{year}-01-01"

        self._limiter.clear_stale()
        wid = workspace_id or self.get_workspace_id()
        rows = self.get_all_detailed_entries(start, end, workspace_id=wid)
        return self._flatten_report_entries(
            rows,
            tag_map=tag_map,
            task_map=task_map,
            client_map=client_map,
            workspace_id=wid,
        )
