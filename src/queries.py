"""
Query engine: parses natural-language-ish questions and runs them against SQLite.

This is the "brain" behind the Chat page. It pattern-matches common question
types and returns structured answers. Designed to be replaced or augmented
by an actual AI API later.
"""

import re
import json
from datetime import date, datetime, timedelta

import pandas as pd

from src.data_store import (
    get_connection, get_entries_df, get_entries_for_date_across_years,
    get_entries_for_week_across_years, get_total_stats, get_available_years,
    search_entries, get_entries_by_tag, get_all_project_names, get_all_tag_names,
)

# Month name -> number mapping
MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _fuzzy_match_project(name: str, known_projects: list[str]) -> str | None:
    """Case-insensitive match of user input against known project names."""
    lower = name.lower().strip()
    for proj in known_projects:
        if proj.lower() == lower:
            return proj
    # Partial / substring match as fallback
    for proj in known_projects:
        if lower in proj.lower() or proj.lower() in lower:
            return proj
    return None


def _fuzzy_match_tag(name: str, known_tags: list[str]) -> str | None:
    """Case-insensitive match of user input against known tag names."""
    lower = name.lower().strip()
    for tag in known_tags:
        if tag.lower() == lower:
            return tag
    for tag in known_tags:
        if lower in tag.lower() or tag.lower() in lower:
            return tag
    return None


def answer_question(question: str) -> str:
    """
    Parse a natural language question and return an answer string.
    Falls back to a help message if the question can't be parsed.
    """
    q = question.lower().strip()
    conn = get_connection()

    try:
        known_projects = get_all_project_names(conn)
        known_tags = get_all_tag_names(conn)

        # ----- "top projects" / "top tags" / "biggest projects" -----
        if any(kw in q for kw in ["top project", "biggest project", "most project",
                                   "best project", "main project"]):
            year_match = re.search(r'\b(20\d{2})\b', q)
            year_val = int(year_match.group(1)) if year_match else None
            return _answer_top_projects(conn, year_val)

        if any(kw in q for kw in ["top tag", "biggest tag", "most tag",
                                   "best tag", "main tag", "what tag"]):
            year_match = re.search(r'\b(20\d{2})\b', q)
            year_val = int(year_match.group(1)) if year_match else None
            return _answer_top_tags(conn, year_val)

        # ----- tag-specific queries: "tagged X", "tag X", "hours on tag X" -----
        tag_match = re.search(
            r'(?:tagged|tag)\s+["\']?(.+?)["\']?(?:\s+in\s+(20\d{2}))?$', q
        )
        if tag_match:
            tag_name = tag_match.group(1).strip()
            year_val = int(tag_match.group(2)) if tag_match.group(2) else None
            matched_tag = _fuzzy_match_tag(tag_name, known_tags)
            if matched_tag:
                return _answer_tag(conn, matched_tag, year_val)
            return f"No tag matching '{tag_name}' found. Known tags: {', '.join(known_tags)}"

        # ----- "what did I do on <date>" -----
        date_match = re.search(
            r'(?:on|for)\s+(?:(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:[,\s]+(\d{4}))?)',
            q
        )
        if date_match:
            month_str, day_str, year_str = date_match.groups()
            month_num = MONTH_MAP.get(month_str.lower())
            if month_num:
                day_num = int(day_str)
                if year_str:
                    return _answer_specific_date(conn, int(year_str), month_num, day_num)
                else:
                    return _answer_date_across_years(conn, month_num, day_num)

        # ----- "this week" / "last week" / "week <n>" -----
        if "this week" in q:
            week_num = date.today().isocalendar()[1]
            return _answer_week(conn, week_num)
        if "last week" in q:
            week_num = (date.today() - timedelta(weeks=1)).isocalendar()[1]
            return _answer_week(conn, week_num)
        week_match = re.search(r'week\s*(\d{1,2})', q)
        if week_match:
            return _answer_week(conn, int(week_match.group(1)))

        # ----- "today" / "yesterday" -----
        if "today" in q:
            today = date.today()
            return _answer_date_across_years(conn, today.month, today.day)
        if "yesterday" in q:
            yesterday = date.today() - timedelta(days=1)
            return _answer_date_across_years(conn, yesterday.month, yesterday.day)

        # ----- compare years: "compare 2023 and 2024" or "2023 vs 2024" -----
        compare_match = re.search(r'(?:compare\s+)?(20\d{2})\s+(?:and|vs|to|with|versus)\s+(20\d{2})', q)
        if compare_match:
            return _answer_compare(conn, int(compare_match.group(1)), int(compare_match.group(2)))

        # ----- "total" / "overall" / "all time" -- but only if not scoped -----
        # Check that it's not scoped to a project/tag (e.g. "total on Work")
        if any(kw in q for kw in ["total", "overall", "how much time", "all time", "lifetime"]):
            # If the query also mentions a known project, route to project handler
            for proj in known_projects:
                if proj.lower() in q:
                    year_match = re.search(r'\b(20\d{2})\b', q)
                    year_val = int(year_match.group(1)) if year_match else None
                    return _answer_project(conn, proj, year_val)
            # If the query also mentions a known tag, route to tag handler
            for tag in known_tags:
                if tag.lower() in q:
                    year_match = re.search(r'\b(20\d{2})\b', q)
                    year_val = int(year_match.group(1)) if year_match else None
                    return _answer_tag(conn, tag, year_val)
            return _answer_totals(conn)

        # ----- "last <month>" or "in <month> <year>" -----
        month_match = re.search(r'(?:in|last|for)\s+(\w+)(?:\s+(20\d{2}))?', q)
        if month_match:
            month_str = month_match.group(1).lower()
            month_num = MONTH_MAP.get(month_str)
            if month_num:
                year_val = int(month_match.group(2)) if month_match.group(2) else None
                return _answer_month(conn, month_num, year_val)

        # ----- year-specific questions: "how was 2024" -----
        year_match = re.search(r'\b(20\d{2})\b', q)
        if year_match:
            return _answer_year(conn, int(year_match.group(1)))

        # ----- explicit "project X" prefix -----
        project_match = re.search(
            r'(?:project)\s+["\']?(.+?)["\']?(?:\s+in\s+(20\d{2}))?$', q
        )
        if project_match:
            project_name = project_match.group(1).strip()
            year_val = int(project_match.group(2)) if project_match.group(2) else None
            matched = _fuzzy_match_project(project_name, known_projects)
            if matched:
                return _answer_project(conn, matched, year_val)
            return f"No project matching '{project_name}'. Known projects: {', '.join(known_projects[:10])}..."

        # ----- bare project name: check if input matches a known project -----
        for proj in known_projects:
            if proj.lower() == q or q == proj.lower().rstrip():
                return _answer_project(conn, proj, None)

        # ----- keyword search -----
        search_match = re.search(r'(?:search|find|look for|when did i)\s+(.+)', q)
        if search_match:
            keyword = search_match.group(1).strip().strip('"\'')
            return _answer_search(conn, keyword)

        # ----- fallback -----
        return _help_message(known_projects, known_tags)

    finally:
        conn.close()


def _answer_totals(conn) -> str:
    stats = get_total_stats(conn)
    return (
        f"**All-Time Stats:**\n\n"
        f"- **Total hours:** {stats['total_hours']:,.1f}\n"
        f"- **Total entries:** {stats['total_entries']:,}\n"
        f"- **Years tracked:** {stats['years_tracked']}\n"
        f"- **Unique projects:** {stats['unique_projects']}\n"
        f"- **Date range:** {stats['earliest_date']} to {stats['latest_date']}"
    )


def _answer_year(conn, year: int) -> str:
    df = get_entries_df(conn, year=year)
    if df.empty:
        return f"No data found for {year}."

    total_h = df["duration_hours"].sum()
    total_e = len(df)
    active_days = df["start_date"].nunique()
    avg_h = total_h / active_days if active_days > 0 else 0

    # Top 5 projects
    top_projects = (
        df.groupby("project_name")["duration_hours"].sum()
        .sort_values(ascending=False).head(5)
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


def _answer_specific_date(conn, year: int, month: int, day: int) -> str:
    start = f"{year}-{month:02d}-{day:02d}"
    df = get_entries_df(conn, start_date=start, end_date=start)
    if df.empty:
        return f"No entries found for {start}."

    total_h = df["duration_hours"].sum()
    lines = []
    for _, row in df.iterrows():
        desc = row["description"] or "(no description)"
        proj = row["project_name"] or "(no project)"
        h = row["duration_hours"]
        lines.append(f"- **{proj}** -- {desc} ({h:.1f}h)")

    entries_text = "\n".join(lines)
    return f"**{start}** -- {total_h:.1f} hours, {len(df)} entries:\n\n{entries_text}"


def _answer_date_across_years(conn, month: int, day: int) -> str:
    df = get_entries_for_date_across_years(conn, month, day)
    if df.empty:
        return f"No entries found for {month:02d}-{day:02d} in any year."

    lines = []
    for year_val in sorted(df["start_year"].unique()):
        year_df = df[df["start_year"] == year_val]
        total_h = year_df["duration_hours"].sum()
        top_proj = year_df.groupby("project_name")["duration_hours"].sum().idxmax()
        top_desc = year_df.sort_values("duration_hours", ascending=False).iloc[0]["description"] or ""
        lines.append(f"- **{int(year_val)}:** {total_h:.1f}h -- top project: {top_proj or '(none)'}" +
                     (f", main activity: {top_desc}" if top_desc else ""))

    return f"**On {month:02d}/{day:02d} across all years:**\n\n" + "\n".join(lines)


def _answer_month(conn, month: int, year: int | None) -> str:
    if year:
        start = f"{year}-{month:02d}-01"
        if month == 12:
            end = f"{year}-12-31"
        else:
            end = f"{year}-{month+1:02d}-01"
        df = get_entries_df(conn, start_date=start, end_date=end)
        label = f"{datetime(2000, month, 1).strftime('%B')} {year}"
    else:
        # All years, this month
        df = get_entries_df(conn)
        df = df[df["start_month"] == month]
        label = f"{datetime(2000, month, 1).strftime('%B')} (all years)"

    if df.empty:
        return f"No entries found for {label}."

    total_h = df["duration_hours"].sum()
    total_e = len(df)
    top = df.groupby("project_name")["duration_hours"].sum().sort_values(ascending=False).head(5)
    proj_lines = "\n".join(f"  - {n or '(No Project)'}: {h:.1f}h" for n, h in top.items())

    return (
        f"**{label}:**\n\n"
        f"- **Hours:** {total_h:.1f}\n"
        f"- **Entries:** {total_e}\n\n"
        f"**Top projects:**\n{proj_lines}"
    )


def _answer_week(conn, week_num: int) -> str:
    df = get_entries_for_week_across_years(conn, week_num)
    if df.empty:
        return f"No entries found for week {week_num}."

    lines = []
    for year_val in sorted(df["start_year"].unique()):
        year_df = df[df["start_year"] == year_val]
        total_h = year_df["duration_hours"].sum()
        lines.append(f"- **{int(year_val)}:** {total_h:.1f}h ({len(year_df)} entries)")

    return f"**Week {week_num} across all years:**\n\n" + "\n".join(lines)


def _answer_project(conn, project_name: str, year: int | None) -> str:
    df = get_entries_df(conn, year=year) if year else get_entries_df(conn)
    # Case-insensitive match
    mask = df["project_name"].str.lower().str.contains(project_name.lower(), na=False)
    df = df[mask]

    if df.empty:
        return f"No entries found for project matching '{project_name}'."

    total_h = df["duration_hours"].sum()
    total_e = len(df)
    active_d = df["start_date"].nunique()
    label = f"'{project_name}'" + (f" in {year}" if year else " (all time)")

    # Top activities
    top_desc = (
        df[df["description"].notna() & (df["description"] != "")]
        .groupby("description")["duration_hours"].sum()
        .sort_values(ascending=False).head(5)
    )
    desc_lines = "\n".join(
        f"  - {d}: {h:.1f}h" for d, h in top_desc.items()
    ) if not top_desc.empty else "  (no descriptions)"

    return (
        f"**Project {label}:**\n\n"
        f"- **Hours:** {total_h:,.1f}\n"
        f"- **Entries:** {total_e:,}\n"
        f"- **Active days:** {active_d}\n"
        f"- **Date range:** {df['start_date'].min()} to {df['start_date'].max()}\n\n"
        f"**Top activities:**\n{desc_lines}"
    )


def _answer_tag(conn, tag_name: str, year: int | None) -> str:
    df = get_entries_by_tag(conn, tag_name, year=year)

    if df.empty:
        scope = f" in {year}" if year else ""
        return f"No entries found with tag '{tag_name}'{scope}."

    total_h = df["duration_hours"].sum()
    total_e = len(df)
    label = f"'{tag_name}'" + (f" in {year}" if year else " (all time)")

    # Top projects for this tag
    top_proj = (
        df.groupby("project_name")["duration_hours"].sum()
        .sort_values(ascending=False).head(5)
    )
    proj_lines = "\n".join(
        f"  - {n or '(No Project)'}: {h:.1f}h" for n, h in top_proj.items()
    )

    return (
        f"**Tag {label}:**\n\n"
        f"- **Hours:** {total_h:,.1f}\n"
        f"- **Entries:** {total_e:,}\n"
        f"- **Date range:** {df['start_date'].min()} to {df['start_date'].max()}\n\n"
        f"**Top projects with this tag:**\n{proj_lines}"
    )


def _answer_top_projects(conn, year: int | None) -> str:
    df = get_entries_df(conn, year=year) if year else get_entries_df(conn)
    if df.empty:
        return "No data found."

    top = (
        df.groupby("project_name")
        .agg(hours=("duration_hours", "sum"), entries=("id", "count"))
        .sort_values("hours", ascending=False)
        .head(10)
        .reset_index()
    )

    total_h = df["duration_hours"].sum()
    scope = str(year) if year else "All Time"
    lines = []
    for _, row in top.iterrows():
        name = row["project_name"] or "(No Project)"
        pct = (row["hours"] / total_h * 100) if total_h > 0 else 0
        lines.append(f"  - **{name}:** {row['hours']:,.1f}h ({pct:.1f}%) -- {row['entries']} entries")

    return f"**Top 10 Projects ({scope}):**\n\n" + "\n".join(lines)


def _answer_top_tags(conn, year: int | None) -> str:
    df = get_entries_df(conn, year=year) if year else get_entries_df(conn)
    if df.empty:
        return "No data found."

    if "tags_list" not in df.columns:
        return "No tag data available."

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
    lines = []
    for _, row in top.iterrows():
        lines.append(f"  - **{row['tags_list']}:** {row['hours']:,.1f}h -- {row['entries']} entries")

    return f"**Top Tags ({scope}):**\n\n" + "\n".join(lines)


def _answer_search(conn, keyword: str) -> str:
    df = search_entries(conn, keyword, limit=20)
    if df.empty:
        return f"No entries found matching '{keyword}'."

    total_h = df["duration_hours"].sum()
    lines = []
    for _, row in df.head(10).iterrows():
        d = row["start_date"]
        desc = row["description"] or "(no description)"
        proj = row["project_name"] or ""
        h = row["duration_hours"]
        lines.append(f"- **{d}** -- {desc} [{proj}] ({h:.1f}h)")

    result = f"**Search results for '{keyword}'** ({len(df)} entries, {total_h:.1f}h total):\n\n"
    result += "\n".join(lines)
    if len(df) > 10:
        result += f"\n\n...and {len(df) - 10} more entries."
    return result


def _answer_compare(conn, year_a: int, year_b: int) -> str:
    df_a = get_entries_df(conn, year=year_a)
    df_b = get_entries_df(conn, year=year_b)

    def stats(df, y):
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


def _help_message(known_projects: list[str] | None = None,
                  known_tags: list[str] | None = None) -> str:
    proj_examples = ""
    if known_projects:
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
        f'- **"Top projects"** / **"Top projects in 2024"** -- Project ranking\n'
        f'- **"Top tags"** -- Tag ranking\n'
        f'- **Project name directly**{proj_examples} -- Project details\n'
        f'- **"Tag Highlight"** / **"Tagged Deep in 2024"**{tag_examples} -- Tag details\n'
        '- **"Search meditation"** -- Keyword search across descriptions, projects, and tags\n\n'
        "For AI-powered analysis, an AI API integration can be added later."
    )
