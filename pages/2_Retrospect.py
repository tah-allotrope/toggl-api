"""
Retrospect page: "On this day" across all years, week-level comparison,
and year-over-year side-by-side view.

This is the page that replaces manually checking "what did I do on this date
in previous years?" -- it shows all matching entries at a glance.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime, timedelta

from src.data_store import (
    get_connection, get_entries_for_date_across_years,
    get_entries_for_week_across_years, get_entries_df, get_available_years,
)
from src.theme import (
    apply_theme, neon_chart_layout, COLORS, NEON_SEQUENCE,
    SCALE_CYAN_MONO, SCALE_MAGENTA_FIRE,
)

st.set_page_config(page_title="Retrospect", page_icon="\U0001f50d", layout="wide")
apply_theme()
st.title("Retrospect")

conn = get_connection()
years = get_available_years(conn)

if not years:
    st.warning("No data available. Please run a sync from the home page.")
    st.stop()

# ---------------------------------------------------------------------------
# Tab navigation
# ---------------------------------------------------------------------------

tab_day, tab_week, tab_compare = st.tabs(["On This Day", "Week View", "Year vs Year"])

# ===========================================================================
# TAB 1: On This Day
# ===========================================================================

with tab_day:
    st.subheader("On This Day Across All Years")

    col_date, col_spacer = st.columns([1, 3])
    with col_date:
        selected_date = st.date_input(
            "Pick a date",
            value=date.today(),
            help="See what you were doing on this month/day in every year"
        )

    month = selected_date.month
    day = selected_date.day

    df_day = get_entries_for_date_across_years(conn, month, day)

    if df_day.empty:
        st.info(f"No entries found for {selected_date.strftime('%B %d')} in any year.")
    else:
        # Summary: hours per year for this date
        year_summary = (
            df_day.groupby("start_year")
            .agg(
                hours=("duration_hours", "sum"),
                entries=("id", "count"),
                projects=("project_name", "nunique"),
            )
            .reset_index()
        )
        year_summary = year_summary.rename(columns={
            "start_year": "Year", "hours": "Hours", "entries": "Entries", "projects": "Projects",
        })

        # Bar chart: hours by year for this date
        fig = px.bar(
            year_summary,
            x="Year",
            y="Hours",
            title=f"Hours on {selected_date.strftime('%B %d')} by Year",
            text="Hours",
            color="Hours",
            color_continuous_scale=SCALE_CYAN_MONO,
        )
        fig.update_traces(
            texttemplate="%{text:.1f}h",
            textposition="outside",
            textfont=dict(color=COLORS["cyan"]),
            marker_line_width=0,
        )
        neon_chart_layout(fig, height=350)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # Detailed view per year
        for year_val in sorted(df_day["start_year"].unique(), reverse=True):
            year_entries = df_day[df_day["start_year"] == year_val]
            total_h = year_entries["duration_hours"].sum()

            with st.expander(
                f"{int(year_val)} -- {total_h:.1f} hours, {len(year_entries)} entries",
                expanded=(year_val == df_day["start_year"].max()),
            ):
                display_df = year_entries[["start", "description", "project_name", "duration_hours", "tags"]].copy()
                display_df = display_df.rename(columns={
                    "start": "Start Time",
                    "description": "Description",
                    "project_name": "Project",
                    "duration_hours": "Hours",
                    "tags": "Tags",
                })
                display_df["Start Time"] = pd.to_datetime(display_df["Start Time"]).dt.strftime("%H:%M")
                display_df["Hours"] = display_df["Hours"].round(2)
                st.dataframe(display_df, use_container_width=True, hide_index=True)

# ===========================================================================
# TAB 2: Week View
# ===========================================================================

with tab_week:
    st.subheader("This Week Across All Years")

    today = date.today()
    current_week = today.isocalendar()[1]

    selected_week = st.slider(
        "ISO Week Number",
        min_value=1,
        max_value=53,
        value=current_week,
        help="Compare the same week number across all years",
    )

    df_week = get_entries_for_week_across_years(conn, selected_week)

    if df_week.empty:
        st.info(f"No entries found for week {selected_week} in any year.")
    else:
        # Hours per year for this week
        week_by_year = (
            df_week.groupby("start_year")["duration_hours"]
            .sum()
            .reset_index()
        )
        week_by_year = week_by_year.rename(columns={"start_year": "Year", "duration_hours": "Hours"})

        fig = px.bar(
            week_by_year,
            x="Year",
            y="Hours",
            title=f"Hours in Week {selected_week} by Year",
            text="Hours",
            color="Hours",
            color_continuous_scale=SCALE_MAGENTA_FIRE,
        )
        fig.update_traces(
            texttemplate="%{text:.1f}h",
            textposition="outside",
            textfont=dict(color=COLORS["magenta"]),
            marker_line_width=0,
        )
        neon_chart_layout(fig, height=350)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # Project breakdown per year for this week
        week_projects = (
            df_week.groupby(["start_year", "project_name"])["duration_hours"]
            .sum()
            .reset_index()
        )
        week_projects = week_projects.rename(columns={
            "start_year": "Year", "project_name": "Project", "duration_hours": "Hours",
        })
        week_projects["Project"] = week_projects["Project"].replace("", "(No Project)")

        fig2 = px.bar(
            week_projects,
            x="Year",
            y="Hours",
            color="Project",
            title=f"Week {selected_week} -- Project Breakdown by Year",
            barmode="stack",
            color_discrete_sequence=NEON_SEQUENCE,
        )
        neon_chart_layout(fig2, height=400)
        st.plotly_chart(fig2, use_container_width=True)

# ===========================================================================
# TAB 3: Year vs Year
# ===========================================================================

with tab_compare:
    st.subheader("Year-over-Year Comparison")

    col1, col2 = st.columns(2)
    with col1:
        year_a = st.selectbox("Year A", sorted(years, reverse=True), index=0, key="year_a")
    with col2:
        default_b = min(1, len(years) - 1)
        year_b = st.selectbox("Year B", sorted(years, reverse=True), index=default_b, key="year_b")

    df_a = get_entries_df(conn, year=year_a)
    df_b = get_entries_df(conn, year=year_b)

    if df_a.empty and df_b.empty:
        st.info("No data for the selected years.")
    else:
        # Monthly comparison
        df_a["month"] = df_a["start_month"]
        df_b["month"] = df_b["start_month"]

        monthly_a = df_a.groupby("month")["duration_hours"].sum().reindex(range(1, 13), fill_value=0)
        monthly_b = df_b.groupby("month")["duration_hours"].sum().reindex(range(1, 13), fill_value=0)

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=month_names, y=monthly_a.values, name=str(year_a),
            marker_color=COLORS["cyan"],
            marker_line=dict(width=1, color=COLORS["cyan"]),
        ))
        fig.add_trace(go.Bar(
            x=month_names, y=monthly_b.values, name=str(year_b),
            marker_color=COLORS["magenta"],
            marker_line=dict(width=1, color=COLORS["magenta"]),
        ))
        fig.update_layout(
            title=f"Monthly Hours: {year_a} vs {year_b}",
            barmode="group",
            yaxis_title="Hours",
        )
        neon_chart_layout(fig, height=400)
        st.plotly_chart(fig, use_container_width=True)

        # Project comparison
        st.markdown("#### Project Hours Comparison")

        proj_a = df_a.groupby("project_name")["duration_hours"].sum().reset_index()
        proj_a = proj_a.rename(columns={"project_name": "Project", "duration_hours": f"{year_a} Hours"})
        proj_b = df_b.groupby("project_name")["duration_hours"].sum().reset_index()
        proj_b = proj_b.rename(columns={"project_name": "Project", "duration_hours": f"{year_b} Hours"})

        proj_compare = pd.merge(proj_a, proj_b, on="Project", how="outer").fillna(0)
        proj_compare["Project"] = proj_compare["Project"].replace("", "(No Project)")
        proj_compare["Difference"] = proj_compare[f"{year_a} Hours"] - proj_compare[f"{year_b} Hours"]
        proj_compare = proj_compare.sort_values(f"{year_a} Hours", ascending=False)

        st.dataframe(
            proj_compare.style.format({
                f"{year_a} Hours": "{:.1f}",
                f"{year_b} Hours": "{:.1f}",
                "Difference": "{:+.1f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Summary stats comparison
        st.markdown("#### Summary Stats")

        stats_data = {
            "Metric": ["Total Hours", "Total Entries", "Active Days", "Unique Projects", "Avg Hours/Day"],
        }

        for label, df_x, year_x in [(str(year_a), df_a, year_a), (str(year_b), df_b, year_b)]:
            total_h = df_x["duration_hours"].sum()
            total_e = len(df_x)
            active_d = df_x["start_date"].nunique()
            unique_p = df_x["project_name"].nunique()
            avg_h = total_h / active_d if active_d > 0 else 0
            stats_data[label] = [f"{total_h:.1f}", str(total_e), str(active_d), str(unique_p), f"{avg_h:.1f}"]

        st.dataframe(pd.DataFrame(stats_data), use_container_width=True, hide_index=True)

conn.close()
