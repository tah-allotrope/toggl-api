import hashlib
import json
from datetime import datetime
from typing import Any, Tuple

def parse_duration_hms(duration_hms: str) -> int:
    """Return duration in whole seconds parsed from HH:MM:SS."""
    try:
        parts = duration_hms.split(':')
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
    except (ValueError, AttributeError):
        pass
    return 0

def derive_time_parts(start_iso: str) -> Tuple[str, int, int, int, int]:
    """Return (start_date, start_year, start_month, start_day, start_week_iso)."""
    try:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        start_date = dt.strftime("%Y-%m-%d")
        return (
            start_date,
            dt.year,
            dt.month,
            dt.day,
            dt.isocalendar()[1]
        )
    except (ValueError, AttributeError):
        start_date = start_iso[:10] if len(start_iso) >= 10 else ""
        start_year = int(start_iso[:4]) if len(start_iso) >= 4 else 0
        start_month = int(start_iso[5:7]) if len(start_iso) >= 7 else 0
        start_day = int(start_iso[8:10]) if len(start_iso) >= 10 else 0
        return start_date, start_year, start_month, start_day, 0

def build_synthetic_id(start_iso: str, stop_iso: str, description: str, project_name: str, duration_sec: int) -> int:
    """Return deterministic positive integer ID from SHA-256 seed fields."""
    seed = f"{start_iso}|{stop_iso}|{description}|{project_name}|{duration_sec}"
    digest = hashlib.sha256(seed.encode('utf-8')).hexdigest()
    # Take first 15 chars of hex to fit in Postgres BIGINT (max 9223372036854775807)
    return int(digest[:15], 16)

def transform_csv_entry(row: dict[str, str]) -> dict[str, Any]:
    """Return normalized time-entry dict from one Toggl CSV row."""
    start_time = row.get("Start time", "00:00:00")
    start_date_str = row.get("Start date", "")
    start_iso = f"{start_date_str}T{start_time}Z" if start_date_str else ""
    
    stop_time = row.get("End time", "00:00:00")
    stop_date_str = row.get("End date", "")
    stop_iso = f"{stop_date_str}T{stop_time}Z" if stop_date_str else ""
    
    duration_hms = row.get("Duration", "00:00:00")
    duration_sec = parse_duration_hms(duration_hms)
    
    description = row.get("Description", "")
    project_name = row.get("Project", "")
    client_name = row.get("Client", "")
    task_name = row.get("Task", "")
    
    tags_str = row.get("Tags", "")
    tags = [t.strip() for t in tags_str.split('|') if t.strip()] if tags_str else []
    
    synthetic_id = build_synthetic_id(start_iso, stop_iso, description, project_name, duration_sec)
    
    start_date, start_year, start_month, start_day, start_week = derive_time_parts(start_iso)
    
    return {
        "id": synthetic_id,
        "description": description,
        "start": start_iso,
        "stop": stop_iso,
        "duration": duration_sec,
        "project_id": None,
        "project_name": project_name,
        "workspace_id": None,
        "tags": tags,
        "tag_ids": [],
        "billable": 1 if row.get("Billable", "No") == "Yes" else 0,
        "at": None,
        "start_date": start_date,
        "start_year": start_year,
        "start_month": start_month,
        "start_day": start_day,
        "start_week": start_week,
        "duration_hours": duration_sec / 3600.0,
        "toggl_id": None,
        "task_id": None,
        "task_name": task_name,
        "client_name": client_name,
        "user_id": None
    }

def transform_json_entry(row: dict[str, Any], workspace_id: int) -> dict[str, Any]:
    """Return normalized time-entry dict from one Toggl JSON entry."""
    start_iso = row.get("start", "")
    stop_iso = row.get("stop", "")
    duration_sec = row.get("duration", 0)
    if duration_sec < 0:
        # Currently running timer
        duration_sec = int(datetime.utcnow().timestamp()) + duration_sec
        
    start_date, start_year, start_month, start_day, start_week = derive_time_parts(start_iso)
    
    return {
        "id": row.get("id"),
        "description": row.get("description", ""),
        "start": start_iso,
        "stop": stop_iso,
        "duration": duration_sec,
        "project_id": row.get("project_id"),
        "project_name": None, # Will be joined/enriched later if needed, or left NULL
        "workspace_id": row.get("workspace_id", workspace_id),
        "tags": row.get("tags", []),
        "tag_ids": row.get("tag_ids", []),
        "billable": 1 if row.get("billable") else 0,
        "at": row.get("at"),
        "start_date": start_date,
        "start_year": start_year,
        "start_month": start_month,
        "start_day": start_day,
        "start_week": start_week,
        "duration_hours": duration_sec / 3600.0,
        "toggl_id": row.get("id"),
        "task_id": row.get("task_id"),
        "task_name": None,
        "client_name": None,
        "user_id": row.get("user_id")
    }
