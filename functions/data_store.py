"""Firestore-backed data access helpers for sync and chat functions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from firebase_admin import firestore


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware datetime in UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _doc_to_entry(doc: firestore.DocumentSnapshot) -> dict[str, Any]:
    data = doc.to_dict() or {}
    data["id"] = doc.id
    return data


def upsert_time_entries_firestore(
    db: firestore.Client, entries: list[dict[str, Any]]
) -> int:
    """Write a list of Toggl entries to Firestore with merge semantics."""
    written = 0
    batch = db.batch()
    batch_count = 0

    for entry in entries:
        toggl_id = entry.get("toggl_id")
        doc_id = str(toggl_id) if toggl_id is not None else str(entry.get("id"))
        if not doc_id or doc_id == "None":
            continue

        start_raw = entry.get("start")
        stop_raw = entry.get("stop")
        start_dt = _parse_iso_datetime(start_raw)
        stop_dt = _parse_iso_datetime(stop_raw)

        if start_dt is not None:
            start_year = start_dt.year
            start_month = start_dt.month
            start_day = start_dt.day
            start_week = int(start_dt.isocalendar()[1])
            start_date = start_dt.strftime("%Y-%m-%d")
        else:
            start_year = None
            start_month = None
            start_day = None
            start_week = None
            start_date = None

        payload = {
            "toggl_id": toggl_id,
            "description": entry.get("description", ""),
            "start": start_dt,
            "end": stop_dt,
            "duration_seconds": int(entry.get("duration", 0) or 0),
            "duration_hours": max(int(entry.get("duration", 0) or 0), 0) / 3600.0,
            "project": entry.get("project_name", "") or "",
            "project_name": entry.get("project_name", "") or "",
            "project_id": entry.get("project_id"),
            "workspace_id": entry.get("workspace_id"),
            "tags_json": entry.get("tags") or [],
            "tag_ids": entry.get("tag_ids") or [],
            "billable": bool(entry.get("billable", False)),
            "enriched": toggl_id is not None,
            "at": entry.get("at") or "",
            "task_id": entry.get("task_id"),
            "task_name": entry.get("task_name") or "",
            "client_name": entry.get("client_name") or "",
            "user_id": entry.get("user_id"),
            "start_date": start_date,
            "start_year": start_year,
            "start_month": start_month,
            "start_day": start_day,
            "start_week": start_week,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

        ref = db.collection("time_entries").document(doc_id)
        batch.set(ref, payload, merge=True)
        batch_count += 1
        written += 1

        if batch_count == 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0

    if batch_count:
        batch.commit()

    return written


def upsert_projects_firestore(
    db: firestore.Client, projects: list[dict[str, Any]]
) -> int:
    written = 0
    for project in projects:
        project_id = project.get("id")
        if project_id is None:
            continue
        db.collection("projects").document(str(project_id)).set(
            {
                "name": project.get("name", ""),
                "workspace_id": project.get("workspace_id") or project.get("wid"),
                "client_id": project.get("client_id"),
                "color": project.get("color", ""),
                "active": bool(project.get("active", True)),
                "billable": bool(project.get("billable", False)),
                "is_private": bool(project.get("is_private", False)),
                "estimated_hours": project.get("estimated_hours"),
                "rate": project.get("rate"),
                "currency": project.get("currency"),
                "fixed_fee": project.get("fixed_fee"),
                "actual_hours": project.get("actual_hours"),
                "created_at": project.get("created_at"),
                "at": project.get("at"),
                "server_deleted_at": project.get("server_deleted_at"),
            },
            merge=True,
        )
        written += 1
    return written


def upsert_tags_firestore(db: firestore.Client, tags: list[dict[str, Any]]) -> int:
    written = 0
    for tag in tags:
        tag_id = tag.get("id")
        if tag_id is None:
            continue
        db.collection("tags").document(str(tag_id)).set(
            {
                "name": tag.get("name", ""),
                "workspace_id": tag.get("workspace_id") or tag.get("wid"),
                "creator_id": tag.get("creator_id"),
                "at": tag.get("at"),
                "deleted_at": tag.get("deleted_at"),
            },
            merge=True,
        )
        written += 1
    return written


def upsert_clients_firestore(
    db: firestore.Client, clients: list[dict[str, Any]]
) -> int:
    written = 0
    for client in clients:
        client_id = client.get("id")
        if client_id is None:
            continue
        db.collection("clients").document(str(client_id)).set(
            {
                "name": client.get("name", ""),
                "workspace_id": client.get("workspace_id") or client.get("wid"),
                "archived": bool(client.get("archived", False)),
                "at": client.get("at"),
            },
            merge=True,
        )
        written += 1
    return written


def upsert_tasks_firestore(db: firestore.Client, tasks: list[dict[str, Any]]) -> int:
    written = 0
    for task in tasks:
        task_id = task.get("id")
        if task_id is None:
            continue
        db.collection("tasks").document(str(task_id)).set(
            {
                "name": task.get("name", ""),
                "project_id": task.get("project_id"),
                "workspace_id": task.get("workspace_id") or task.get("wid"),
                "user_id": task.get("user_id"),
                "active": bool(task.get("active", True)),
                "estimated_seconds": task.get("estimated_seconds"),
                "tracked_seconds": task.get("tracked_seconds"),
                "at": task.get("at"),
            },
            merge=True,
        )
        written += 1
    return written


def set_sync_meta(db: firestore.Client, key: str, value: str) -> None:
    """Set a sync meta key/value pair."""
    db.collection("sync_meta").document(key).set({"value": value}, merge=True)


def get_sync_meta(db: firestore.Client, key: str) -> str | None:
    """Read sync meta value by key."""
    doc = db.collection("sync_meta").document(key).get()
    if not doc.exists:
        return None
    return (doc.to_dict() or {}).get("value")


def get_entries(
    db: firestore.Client,
    start_date: str | None = None,
    end_date: str | None = None,
    project: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch entries with optional date/project/tag filtering."""
    query = db.collection("time_entries")

    if start_date:
        query = query.where("start_date", ">=", start_date)
    if end_date:
        query = query.where("start_date", "<=", end_date)
    if project:
        query = query.where("project_name", "==", project)
    if tag:
        query = query.where("tags_json", "array_contains", tag)

    docs = query.stream()
    entries = [_doc_to_entry(doc) for doc in docs]
    entries.sort(key=lambda item: item.get("start_date") or "")
    return entries


def get_entries_for_date_across_years(
    db: firestore.Client, month: int, day: int
) -> list[dict[str, Any]]:
    """Fetch entries for a given month/day across all years."""
    docs = (
        db.collection("time_entries")
        .where("start_month", "==", month)
        .where("start_day", "==", day)
        .stream()
    )
    entries = [_doc_to_entry(doc) for doc in docs]
    entries.sort(
        key=lambda item: ((item.get("start_year") or 0), item.get("start_date") or "")
    )
    return entries


def get_entries_for_week_across_years(
    db: firestore.Client, week: int
) -> list[dict[str, Any]]:
    """Fetch entries for a given ISO week across all years."""
    docs = db.collection("time_entries").where("start_week", "==", week).stream()
    entries = [_doc_to_entry(doc) for doc in docs]
    entries.sort(
        key=lambda item: ((item.get("start_year") or 0), item.get("start_date") or "")
    )
    return entries


def search_entries(db: firestore.Client, keyword: str) -> list[dict[str, Any]]:
    """Search entries by substring in description, project_name, client_name, or tags."""
    needle = keyword.lower().strip()
    if not needle:
        return []

    matches: list[dict[str, Any]] = []
    for doc in db.collection("time_entries").stream():
        entry = _doc_to_entry(doc)
        description = str(entry.get("description") or "").lower()
        project_name = str(entry.get("project_name") or "").lower()
        client_name = str(entry.get("client_name") or "").lower()
        tags = [str(tag).lower() for tag in entry.get("tags_json") or []]

        if (
            needle in description
            or needle in project_name
            or needle in client_name
            or any(needle in tag for tag in tags)
        ):
            matches.append(entry)

    matches.sort(key=lambda item: item.get("start_date") or "", reverse=True)
    return matches


def get_entries_by_tag(
    db: firestore.Client, tag_name: str, year: int | None = None
) -> list[dict[str, Any]]:
    """Fetch entries containing a given tag name, optionally filtered by year."""
    query = db.collection("time_entries").where("tags_json", "array_contains", tag_name)
    if year is not None:
        query = query.where("start_year", "==", year)
    entries = [_doc_to_entry(doc) for doc in query.stream()]
    entries.sort(key=lambda item: item.get("start_date") or "", reverse=True)
    return entries


def get_total_stats(db: firestore.Client) -> dict[str, Any]:
    """Compute aggregate totals across all entries."""
    total_entries = 0
    total_hours = 0.0
    earliest_date = None
    latest_date = None
    projects: set[str] = set()
    years: set[int] = set()

    for doc in db.collection("time_entries").stream():
        entry = doc.to_dict() or {}
        duration_hours = float(entry.get("duration_hours") or 0.0)
        if duration_hours <= 0:
            continue

        total_entries += 1
        total_hours += duration_hours

        start_date = entry.get("start_date")
        if start_date:
            earliest_date = (
                start_date if earliest_date is None else min(earliest_date, start_date)
            )
            latest_date = (
                start_date if latest_date is None else max(latest_date, start_date)
            )

        project_name = entry.get("project_name")
        if project_name:
            projects.add(str(project_name))

        year = entry.get("start_year")
        if year is not None:
            years.add(int(year))

    return {
        "total_entries": total_entries,
        "total_hours": total_hours,
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "unique_projects": len(projects),
        "years_tracked": len(years),
    }


def get_enrichment_stats(db: firestore.Client) -> dict[str, Any]:
    """Compute enrichment coverage stats over entries and metadata collections."""
    total_entries = 0
    enriched_entries = 0
    entries_with_project_id = 0
    entries_with_tag_ids = 0
    entries_with_tasks = 0
    entries_with_at = 0

    for doc in db.collection("time_entries").stream():
        entry = doc.to_dict() or {}
        total_entries += 1
        if entry.get("toggl_id") is not None:
            enriched_entries += 1
        if entry.get("project_id") is not None:
            entries_with_project_id += 1
        if entry.get("tag_ids"):
            entries_with_tag_ids += 1
        if entry.get("task_id") is not None:
            entries_with_tasks += 1
        if entry.get("at"):
            entries_with_at += 1

    total_tasks = sum(1 for _ in db.collection("tasks").stream())
    total_clients = sum(1 for _ in db.collection("clients").stream())

    return {
        "total_entries": total_entries,
        "enriched_entries": enriched_entries,
        "entries_with_project_id": entries_with_project_id,
        "entries_with_tag_ids": entries_with_tag_ids,
        "entries_with_tasks": entries_with_tasks,
        "entries_with_at": entries_with_at,
        "total_tasks": total_tasks,
        "total_clients": total_clients,
    }


def get_available_years(db: firestore.Client) -> list[int]:
    years: set[int] = set()
    for doc in db.collection("time_entries").stream():
        year = (doc.to_dict() or {}).get("start_year")
        if year is not None:
            years.add(int(year))
    return sorted(years)


def get_all_project_names(db: firestore.Client) -> list[str]:
    names: set[str] = set()
    for doc in db.collection("time_entries").stream():
        project_name = (doc.to_dict() or {}).get("project_name")
        if project_name:
            names.add(str(project_name))
    return sorted(names)


def get_all_tag_names(db: firestore.Client) -> list[str]:
    names: set[str] = set()
    for doc in db.collection("tags").stream():
        name = (doc.to_dict() or {}).get("name")
        if name:
            names.add(str(name))
    return sorted(names)


def get_all_client_names(db: firestore.Client) -> list[str]:
    names: set[str] = set()
    for doc in db.collection("time_entries").stream():
        client_name = (doc.to_dict() or {}).get("client_name")
        if client_name:
            names.add(str(client_name))
    return sorted(names)
