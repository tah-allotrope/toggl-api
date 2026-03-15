"""Pattern-matching chat engine adapted to Firestore-backed data helpers."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from data_store import (
    get_all_client_names,
    get_all_project_names,
    get_all_tag_names,
    get_entries,
    get_entries_by_tag,
    get_entries_for_date_across_years,
    get_entries_for_week_across_years,
    get_total_stats,
    search_entries,
)

MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _fuzzy_match(name: str, candidates: list[str]) -> str | None:
    lower = name.lower().strip()
    for candidate in candidates:
        if candidate.lower() == lower:
            return candidate
    for candidate in candidates:
        if lower in candidate.lower() or candidate.lower() in lower:
            return candidate
    return None


def _to_df(entries: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(entries)
    if df.empty:
        return df

    if "duration_hours" not in df.columns:
        df["duration_hours"] = (
            df.get("duration_seconds", 0).fillna(0).astype(float)
        ) / 3600.0
    if "start_date" not in df.columns and "start" in df.columns:
        df["start_date"] = pd.to_datetime(
            df["start"], utc=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")
    if "start_year" not in df.columns and "start_date" in df.columns:
        df["start_year"] = pd.to_datetime(df["start_date"], errors="coerce").dt.year
    if "start_month" not in df.columns and "start_date" in df.columns:
        df["start_month"] = pd.to_datetime(df["start_date"], errors="coerce").dt.month
    if "tags_list" not in df.columns:
        df["tags_list"] = df.get("tags_json", pd.Series(dtype=object)).apply(
            lambda value: value if isinstance(value, list) else []
        )
    if "project_name" not in df.columns:
        df["project_name"] = df.get("project", "")
    return df


def _entries_for_year(db, year: int | None = None) -> pd.DataFrame:
    if year is None:
        return _to_df(get_entries(db))
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    return _to_df(get_entries(db, start_date=start, end_date=end))


def answer_question(db, question: str) -> str:
    q = question.lower().strip()
    known_projects = get_all_project_names(db)
    known_tags = get_all_tag_names(db)
    known_clients = get_all_client_names(db)

    if any(
        keyword in q
        for keyword in [
            "top project",
            "biggest project",
            "most project",
            "best project",
            "main project",
        ]
    ):
        year_match = re.search(r"\b(20\d{2})\b", q)
        year_val = int(year_match.group(1)) if year_match else None
        return _answer_top_projects(db, year_val)

    if any(
        keyword in q
        for keyword in [
            "top tag",
            "biggest tag",
            "most tag",
            "best tag",
            "main tag",
            "what tag",
        ]
    ):
        year_match = re.search(r"\b(20\d{2})\b", q)
        year_val = int(year_match.group(1)) if year_match else None
        return _answer_top_tags(db, year_val)

    if any(
        keyword in q
        for keyword in ["top task", "what task", "biggest task", "most task"]
    ):
        year_match = re.search(r"\b(20\d{2})\b", q)
        year_val = int(year_match.group(1)) if year_match else None
        return _answer_top_tasks(db, year_val)

    client_match = re.search(
        r'(?:client)\s+["\']?(.+?)["\']?(?:\s+in\s+(20\d{2}))?$', q
    )
    if client_match:
        client_name = client_match.group(1).strip()
        year_val = int(client_match.group(2)) if client_match.group(2) else None
        matched_client = _fuzzy_match(client_name, known_clients)
        if matched_client:
            return _answer_client(db, matched_client, year_val)
        return f"No client matching '{client_name}'. Known clients: {', '.join(known_clients)}"

    task_match = re.search(r'(?:task)\s+["\']?(.+?)["\']?(?:\s+in\s+(20\d{2}))?$', q)
    if task_match:
        task_name = task_match.group(1).strip()
        year_val = int(task_match.group(2)) if task_match.group(2) else None
        return _answer_task(db, task_name, year_val)

    tag_match = re.search(
        r'(?:tagged|tag)\s+["\']?(.+?)["\']?(?:\s+in\s+(20\d{2}))?$', q
    )
    if tag_match:
        tag_name = tag_match.group(1).strip()
        year_val = int(tag_match.group(2)) if tag_match.group(2) else None
        matched_tag = _fuzzy_match(tag_name, known_tags)
        if matched_tag:
            return _answer_tag(db, matched_tag, year_val)
        return (
            f"No tag matching '{tag_name}' found. Known tags: {', '.join(known_tags)}"
        )

    date_match = re.search(
        r"(?:on|for)\s+(?:(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:[,\s]+(\d{4}))?)", q
    )
    if date_match:
        month_str, day_str, year_str = date_match.groups()
        month_num = MONTH_MAP.get(month_str.lower())
        if month_num:
            day_num = int(day_str)
            if year_str:
                return _answer_specific_date(db, int(year_str), month_num, day_num)
            return _answer_date_across_years(db, month_num, day_num)

    if "this week" in q:
        return _answer_week(db, int(date.today().isocalendar()[1]))
    if "last week" in q:
        return _answer_week(
            db, int((date.today() - timedelta(weeks=1)).isocalendar()[1])
        )

    week_match = re.search(r"week\s*(\d{1,2})", q)
    if week_match:
        return _answer_week(db, int(week_match.group(1)))

    if "today" in q:
        today = date.today()
        return _answer_date_across_years(db, today.month, today.day)
    if "yesterday" in q:
        yesterday = date.today() - timedelta(days=1)
        return _answer_date_across_years(db, yesterday.month, yesterday.day)

    compare_match = re.search(
        r"(?:compare\s+)?(20\d{2})\s+(?:and|vs|to|with|versus)\s+(20\d{2})", q
    )
    if compare_match:
        return _answer_compare(
            db, int(compare_match.group(1)), int(compare_match.group(2))
        )

    if any(
        keyword in q
        for keyword in ["total", "overall", "how much time", "all time", "lifetime"]
    ):
        for project in known_projects:
            if project.lower() in q:
                year_match = re.search(r"\b(20\d{2})\b", q)
                year_val = int(year_match.group(1)) if year_match else None
                return _answer_project(db, project, year_val)
        for tag in known_tags:
            if tag.lower() in q:
                year_match = re.search(r"\b(20\d{2})\b", q)
                year_val = int(year_match.group(1)) if year_match else None
                return _answer_tag(db, tag, year_val)
        for client in known_clients:
            if client.lower() in q:
                year_match = re.search(r"\b(20\d{2})\b", q)
                year_val = int(year_match.group(1)) if year_match else None
                return _answer_client(db, client, year_val)
        return _answer_totals(db)

    month_match = re.search(r"(?:in|last|for)\s+(\w+)(?:\s+(20\d{2}))?", q)
    if month_match:
        month_str = month_match.group(1).lower()
        month_num = MONTH_MAP.get(month_str)
        if month_num:
            year_val = int(month_match.group(2)) if month_match.group(2) else None
            return _answer_month(db, month_num, year_val)

    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match:
        return _answer_year(db, int(year_match.group(1)))

    project_match = re.search(
        r'(?:project)\s+["\']?(.+?)["\']?(?:\s+in\s+(20\d{2}))?$', q
    )
    if project_match:
        project_name = project_match.group(1).strip()
        year_val = int(project_match.group(2)) if project_match.group(2) else None
        matched = _fuzzy_match(project_name, known_projects)
        if matched:
            return _answer_project(db, matched, year_val)
        return f"No project matching '{project_name}'. Known projects: {', '.join(known_projects[:10])}..."

    for project in known_projects:
        if project.lower() == q or q == project.lower().rstrip():
            return _answer_project(db, project, None)

    search_match = re.search(r"(?:search|find|look for|when did i)\s+(.+)", q)
    if search_match:
        return _answer_search(db, search_match.group(1).strip().strip("\"'"))

    return _help_message(known_projects, known_tags)


def _answer_totals(db) -> str:
    stats = get_total_stats(db)
    return (
        "**All-Time Stats:**\n\n"
        f"- **Total hours:** {stats['total_hours']:,.1f}\n"
        f"- **Total entries:** {stats['total_entries']:,}\n"
        f"- **Years tracked:** {stats['years_tracked']}\n"
        f"- **Unique projects:** {stats['unique_projects']}\n"
        f"- **Date range:** {stats['earliest_date']} to {stats['latest_date']}"
    )


def _answer_year(db, year: int) -> str:
    df = _entries_for_year(db, year)
    if df.empty:
        return f"No data found for {year}."

    total_h = float(df["duration_hours"].sum())
    total_e = len(df)
    active_days = int(df["start_date"].nunique())
    avg_h = total_h / active_days if active_days > 0 else 0.0

    top_projects = (
        df.groupby("project_name")["duration_hours"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )
    project_lines = "\n".join(
        f"  - {name or '(No Project)'}: {hours:.1f}h"
        for name, hours in top_projects.items()
    )

    return (
        f"**{year} Summary:**\n\n"
        f"- **Total hours:** {total_h:,.1f}\n"
        f"- **Entries:** {total_e:,}\n"
        f"- **Active days:** {active_days}\n"
        f"- **Avg hours/day:** {avg_h:.1f}\n\n"
        f"**Top 5 Projects:**\n{project_lines}"
    )


def _answer_specific_date(db, year: int, month: int, day: int) -> str:
    target = f"{year}-{month:02d}-{day:02d}"
    df = _to_df(get_entries(db, start_date=target, end_date=target))
    if df.empty:
        return f"No entries found for {target}."

    lines: list[str] = []
    for _, row in df.iterrows():
        desc = row.get("description") or "(no description)"
        proj = row.get("project_name") or "(no project)"
        h = float(row.get("duration_hours") or 0)
        lines.append(f"- **{proj}** -- {desc} ({h:.1f}h)")

    return (
        f"**{target}** -- {df['duration_hours'].sum():.1f} hours, {len(df)} entries:\n\n"
        + "\n".join(lines)
    )


def _answer_date_across_years(db, month: int, day: int) -> str:
    df = _to_df(get_entries_for_date_across_years(db, month, day))
    if df.empty:
        return f"No entries found for {month:02d}-{day:02d} in any year."

    lines: list[str] = []
    for year_val in sorted(df["start_year"].dropna().unique()):
        year_df = df[df["start_year"] == year_val]
        total_h = float(year_df["duration_hours"].sum())
        top_proj = year_df.groupby("project_name")["duration_hours"].sum().idxmax()
        top_desc = (
            year_df.sort_values("duration_hours", ascending=False)
            .iloc[0]
            .get("description")
            or ""
        )
        line = f"- **{int(year_val)}:** {total_h:.1f}h -- top project: {top_proj or '(none)'}"
        if top_desc:
            line += f", main activity: {top_desc}"
        lines.append(line)

    return f"**On {month:02d}/{day:02d} across all years:**\n\n" + "\n".join(lines)


def _answer_month(db, month: int, year: int | None) -> str:
    if year is not None:
        start = f"{year}-{month:02d}-01"
        end = f"{year}-{month:02d}-31"
        df = _to_df(get_entries(db, start_date=start, end_date=end))
        label = f"{datetime(2000, month, 1).strftime('%B')} {year}"
    else:
        df = _entries_for_year(db, None)
        if not df.empty:
            df = df[df["start_month"] == month]
        label = f"{datetime(2000, month, 1).strftime('%B')} (all years)"

    if df.empty:
        return f"No entries found for {label}."

    top = (
        df.groupby("project_name")["duration_hours"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )
    proj_lines = "\n".join(
        f"  - {name or '(No Project)'}: {hours:.1f}h" for name, hours in top.items()
    )
    return (
        f"**{label}:**\n\n"
        f"- **Hours:** {df['duration_hours'].sum():.1f}\n"
        f"- **Entries:** {len(df)}\n\n"
        f"**Top projects:**\n{proj_lines}"
    )


def _answer_week(db, week_num: int) -> str:
    df = _to_df(get_entries_for_week_across_years(db, week_num))
    if df.empty:
        return f"No entries found for week {week_num}."

    lines: list[str] = []
    for year_val in sorted(df["start_year"].dropna().unique()):
        year_df = df[df["start_year"] == year_val]
        total_h = float(year_df["duration_hours"].sum())
        lines.append(f"- **{int(year_val)}:** {total_h:.1f}h ({len(year_df)} entries)")

    return f"**Week {week_num} across all years:**\n\n" + "\n".join(lines)


def _answer_project(db, project_name: str, year: int | None) -> str:
    df = _entries_for_year(db, year)
    if df.empty:
        return f"No entries found for project matching '{project_name}'."

    mask = (
        df["project_name"]
        .fillna("")
        .str.lower()
        .str.contains(project_name.lower(), na=False)
    )
    df = df[mask]
    if df.empty:
        return f"No entries found for project matching '{project_name}'."

    top_desc = (
        df[df["description"].fillna("") != ""]
        .groupby("description")["duration_hours"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )
    desc_lines = (
        "\n".join(f"  - {desc}: {hours:.1f}h" for desc, hours in top_desc.items())
        or "  (no descriptions)"
    )
    label = f"'{project_name}'" + (f" in {year}" if year else " (all time)")

    return (
        f"**Project {label}:**\n\n"
        f"- **Hours:** {df['duration_hours'].sum():,.1f}\n"
        f"- **Entries:** {len(df):,}\n"
        f"- **Active days:** {df['start_date'].nunique()}\n"
        f"- **Date range:** {df['start_date'].min()} to {df['start_date'].max()}\n\n"
        f"**Top activities:**\n{desc_lines}"
    )


def _answer_tag(db, tag_name: str, year: int | None) -> str:
    entries = get_entries_by_tag(db, tag_name, year=year)
    df = _to_df(entries)
    if df.empty:
        scope = f" in {year}" if year else ""
        return f"No entries found with tag '{tag_name}'{scope}."

    top_proj = (
        df.groupby("project_name")["duration_hours"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )
    proj_lines = "\n".join(
        f"  - {name or '(No Project)'}: {hours:.1f}h"
        for name, hours in top_proj.items()
    )
    label = f"'{tag_name}'" + (f" in {year}" if year else " (all time)")

    return (
        f"**Tag {label}:**\n\n"
        f"- **Hours:** {df['duration_hours'].sum():,.1f}\n"
        f"- **Entries:** {len(df):,}\n"
        f"- **Date range:** {df['start_date'].min()} to {df['start_date'].max()}\n\n"
        f"**Top projects with this tag:**\n{proj_lines}"
    )


def _answer_top_projects(db, year: int | None) -> str:
    df = _entries_for_year(db, year)
    if df.empty:
        return "No data found."

    top = (
        df.groupby("project_name")
        .agg(hours=("duration_hours", "sum"), entries=("id", "count"))
        .sort_values("hours", ascending=False)
        .head(10)
        .reset_index()
    )
    total_h = float(df["duration_hours"].sum())
    scope = str(year) if year else "All Time"

    lines = []
    for _, row in top.iterrows():
        name = row["project_name"] or "(No Project)"
        pct = (float(row["hours"]) / total_h * 100) if total_h > 0 else 0.0
        lines.append(
            f"  - **{name}:** {float(row['hours']):,.1f}h ({pct:.1f}%) -- {int(row['entries'])} entries"
        )

    return f"**Top 10 Projects ({scope}):**\n\n" + "\n".join(lines)


def _answer_top_tags(db, year: int | None) -> str:
    df = _entries_for_year(db, year)
    if df.empty:
        return "No data found."

    exploded = df.explode("tags_list")
    exploded = exploded[exploded["tags_list"].notna() & (exploded["tags_list"] != "")]
    if exploded.empty:
        return "No tagged entries found."

    top = (
        exploded.groupby("tags_list")
        .agg(hours=("duration_hours", "sum"), entries=("id", "count"))
        .sort_values("hours", ascending=False)
        .head(10)
        .reset_index()
    )

    scope = str(year) if year else "All Time"
    lines = [
        f"  - **{row['tags_list']}:** {float(row['hours']):,.1f}h -- {int(row['entries'])} entries"
        for _, row in top.iterrows()
    ]
    return f"**Top Tags ({scope}):**\n\n" + "\n".join(lines)


def _answer_client(db, client_name: str, year: int | None) -> str:
    df = _entries_for_year(db, year)
    if "client_name" not in df.columns:
        return "No client data available."

    mask = (
        df["client_name"]
        .fillna("")
        .str.lower()
        .str.contains(client_name.lower(), na=False)
    )
    df = df[mask]
    if df.empty:
        scope = f" in {year}" if year else ""
        return f"No entries found for client '{client_name}'{scope}."

    top_proj = (
        df.groupby("project_name")["duration_hours"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )
    proj_lines = "\n".join(
        f"  - {name or '(No Project)'}: {hours:.1f}h"
        for name, hours in top_proj.items()
    )
    label = f"'{client_name}'" + (f" in {year}" if year else " (all time)")
    return (
        f"**Client {label}:**\n\n"
        f"- **Hours:** {df['duration_hours'].sum():,.1f}\n"
        f"- **Entries:** {len(df):,}\n"
        f"- **Date range:** {df['start_date'].min()} to {df['start_date'].max()}\n\n"
        f"**Projects for this client:**\n{proj_lines}"
    )


def _answer_task(db, task_name: str, year: int | None) -> str:
    df = _entries_for_year(db, year)
    if "task_name" not in df.columns:
        return "No task data available (requires enrichment sync)."

    mask = (
        df["task_name"].fillna("").str.lower().str.contains(task_name.lower(), na=False)
    )
    df = df[mask]
    if df.empty:
        scope = f" in {year}" if year else ""
        return f"No entries found for task matching '{task_name}'{scope}."

    top_proj = (
        df.groupby("project_name")["duration_hours"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )
    proj_lines = "\n".join(
        f"  - {name or '(No Project)'}: {hours:.1f}h"
        for name, hours in top_proj.items()
    )
    label = f"'{task_name}'" + (f" in {year}" if year else " (all time)")
    return (
        f"**Task {label}:**\n\n"
        f"- **Hours:** {df['duration_hours'].sum():,.1f}\n"
        f"- **Entries:** {len(df):,}\n"
        f"- **Date range:** {df['start_date'].min()} to {df['start_date'].max()}\n\n"
        f"**Projects with this task:**\n{proj_lines}"
    )


def _answer_top_tasks(db, year: int | None) -> str:
    df = _entries_for_year(db, year)
    if df.empty or "task_name" not in df.columns:
        return "No task data available."

    tasks_df = df[df["task_name"].notna() & (df["task_name"] != "")]
    if tasks_df.empty:
        return "No task data found (requires enrichment sync)."

    top = (
        tasks_df.groupby("task_name")
        .agg(hours=("duration_hours", "sum"), entries=("id", "count"))
        .sort_values("hours", ascending=False)
        .head(10)
        .reset_index()
    )
    scope = str(year) if year else "All Time"
    lines = [
        f"  - **{row['task_name']}:** {float(row['hours']):,.1f}h -- {int(row['entries'])} entries"
        for _, row in top.iterrows()
    ]
    return f"**Top Tasks ({scope}):**\n\n" + "\n".join(lines)


def _answer_search(db, keyword: str) -> str:
    df = _to_df(search_entries(db, keyword))
    if df.empty:
        return f"No entries found matching '{keyword}'."

    total_h = float(df["duration_hours"].sum())
    lines: list[str] = []
    for _, row in df.head(10).iterrows():
        d = row.get("start_date")
        desc = row.get("description") or "(no description)"
        proj = row.get("project_name") or ""
        h = float(row.get("duration_hours") or 0)
        lines.append(f"- **{d}** -- {desc} [{proj}] ({h:.1f}h)")

    result = f"**Search results for '{keyword}'** ({len(df)} entries, {total_h:.1f}h total):\n\n"
    result += "\n".join(lines)
    if len(df) > 10:
        result += f"\n\n...and {len(df) - 10} more entries."
    return result


def _answer_compare(db, year_a: int, year_b: int) -> str:
    df_a = _entries_for_year(db, year_a)
    df_b = _entries_for_year(db, year_b)

    def stats(df: pd.DataFrame, y: int) -> str:
        if df.empty:
            return f"No data for {y}."
        return (
            f"  - Hours: {df['duration_hours'].sum():,.1f}\n"
            f"  - Entries: {len(df):,}\n"
            f"  - Active days: {df['start_date'].nunique()}\n"
            f"  - Projects: {df['project_name'].nunique()}"
        )

    return (
        f"**{year_a} vs {year_b}:**\n\n"
        f"**{year_a}:**\n{stats(df_a, year_a)}\n\n"
        f"**{year_b}:**\n{stats(df_b, year_b)}"
    )


def _help_message(
    known_projects: list[str] | None = None, known_tags: list[str] | None = None
) -> str:
    proj_examples = ""
    if known_projects and len(known_projects) >= 2:
        proj_examples = f' (e.g. "{known_projects[0]}", "{known_projects[1]}")'

    tag_examples = ""
    if known_tags:
        tag_examples = f' (e.g. "tag {known_tags[0]}")'

    return (
        "I can answer questions about your Toggl time data. Try:\n\n"
        '- **"How was 2024?"** -- Year summary\n'
        '- **"What did I do on March 15, 2023?"** -- Specific date\n'
        '- **"Compare 2023 and 2024"** or **"2023 vs 2024"** -- Year comparison\n'
        '- **"This week"** / **"Last week"** -- Weekly view\n'
        '- **"Today"** / **"Yesterday"** -- Date across all years\n'
        '- **"In February 2024"** -- Monthly summary\n'
        '- **"Total hours"** -- All-time stats\n'
        '- **"Top projects"** / **"Top projects in 2024"** -- Project ranking\n'
        '- **"Top tags"** / **"Top tasks"** -- Tag or task ranking\n'
        f"- **Project name directly**{proj_examples} -- Project details\n"
        f'- **"Tag Highlight"** / **"Tagged Deep in 2024"**{tag_examples} -- Tag details\n'
        '- **"Client X"** / **"Client X in 2024"** -- Client breakdown\n'
        '- **"Task X"** / **"Hours on task X"** -- Task details\n'
        '- **"Search meditation"** -- Keyword search across descriptions, projects, and tags\n\n'
        "For AI-powered analysis, an AI API integration can be added later."
    )
