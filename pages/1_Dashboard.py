"""
Dashboard page: year-level charts, project/tag breakdowns, activity heatmap.
Cyberpunk neon theme applied to all visualizations.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

from src.data_store import get_connection, get_entries_df, get_available_years

from src.theme import (
    apply_theme, neon_chart_layout, COLORS, NEON_SEQUENCE,
    SCALE_CYAN_MAGENTA, SCALE_NEON_HEATMAP, SCALE_MAGENTA_FIRE,
)
apply_theme()

st.title("Dashboard")

conn = get_connection()
years = get_available_years(conn)

if not years:
    st.warning("No data available. Please run a sync from the home page.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------

st.sidebar.header("Filters")

view_mode = st.sidebar.radio("View", ["Single Year", "All Time", "Custom Range"])

selected_year = max(years)
if view_mode == "Single Year":
    _sel = st.sidebar.selectbox("Year", sorted(years, reverse=True))
    selected_year = _sel if _sel is not None else selected_year
    df = get_entries_df(conn, year=selected_year)
    title_suffix = str(selected_year)
elif view_mode == "All Time":
    df = get_entries_df(conn)
    title_suffix = f"{min(years)}-{max(years)}"
else:
    col1, col2 = st.sidebar.columns(2)
    start = col1.date_input("From", date(max(years), 1, 1))
    end = col2.date_input("To", date.today())
    df = get_entries_df(conn, start_date=start.isoformat(), end_date=end.isoformat())
    title_suffix = f"{start} to {end}"

conn.close()

if df.empty:
    st.info(f"No entries found for {title_suffix}.")
    st.stop()

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

st.subheader(f"Overview: {title_suffix}")

total_hours = df["duration_hours"].sum()
total_entries = len(df)
unique_projects = df["project_name"].nunique()
unique_days = df["start_date"].nunique()
avg_hours_per_day = total_hours / unique_days if unique_days > 0 else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Hours", f"{total_hours:,.1f}")
col2.metric("Entries", f"{total_entries:,}")
col3.metric("Projects", str(unique_projects))
col4.metric("Active Days", str(unique_days))
col5.metric("Avg Hours/Day", f"{avg_hours_per_day:.1f}")

st.divider()

# ---------------------------------------------------------------------------
# Project breakdown (pie + bar)
# ---------------------------------------------------------------------------

st.subheader("Time by Project")

project_hours = (
    df.groupby("project_name")["duration_hours"]
    .sum()
    .reset_index()
    .sort_values("duration_hours", ascending=False)
)
project_hours.columns = ["Project", "Hours"]
project_hours["Project"] = project_hours["Project"].replace("", "(No Project)")

col_pie, col_bar = st.columns(2)

with col_pie:
    fig = px.pie(
        project_hours.head(15),
        values="Hours",
        names="Project",
        title="Top 15 Projects (proportion)",
        hole=0.4,
        color_discrete_sequence=NEON_SEQUENCE,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        textfont=dict(color=COLORS["text"], size=11),
        marker=dict(line=dict(color=COLORS["bg"], width=2)),
    )
    neon_chart_layout(fig, height=480)
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col_bar:
    fig = px.bar(
        project_hours.head(20),
        x="Hours",
        y="Project",
        orientation="h",
        title="Top 20 Projects (hours)",
        color="Hours",
        color_continuous_scale=SCALE_CYAN_MAGENTA,
    )
    fig.update_traces(
        marker_line_color=COLORS["cyan"],
        marker_line_width=0.5,
    )
    neon_chart_layout(fig, height=480)
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        showlegend=False,
        coloraxis_colorbar=dict(
            title="Hours",
            tickfont=dict(color=COLORS["text_muted"]),
            title_font=dict(color=COLORS["text_muted"]),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Tag breakdown
# ---------------------------------------------------------------------------

st.subheader("Time by Tag")

if "tags_list" in df.columns:
    tags_exploded = df.explode("tags_list")
    tags_exploded = tags_exploded[tags_exploded["tags_list"].notna() & (tags_exploded["tags_list"] != "")]

    if not tags_exploded.empty:
        tag_hours = (
            tags_exploded.groupby("tags_list")["duration_hours"]
            .sum()
            .reset_index()
            .sort_values("duration_hours", ascending=False)
        )
        tag_hours.columns = ["Tag", "Hours"]

        fig = px.bar(
            tag_hours.head(25),
            x="Hours",
            y="Tag",
            orientation="h",
            title="Top 25 Tags (hours)",
            color="Hours",
            color_continuous_scale=SCALE_MAGENTA_FIRE,
        )
        fig.update_traces(
            marker_line_color=COLORS["magenta"],
            marker_line_width=0.5,
        )
        neon_chart_layout(fig, height=500)
        fig.update_layout(
            yaxis=dict(autorange="reversed"),
            showlegend=False,
            coloraxis_colorbar=dict(
                title="Hours",
                tickfont=dict(color=COLORS["text_muted"]),
                title_font=dict(color=COLORS["text_muted"]),
            ),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No tagged entries found in this period.")
else:
    st.caption("No tag data available.")

st.divider()

# ---------------------------------------------------------------------------
# Monthly trend
# ---------------------------------------------------------------------------

st.subheader("Monthly Trend")

df["year_month"] = df["start_date"].str[:7]
monthly = df.groupby("year_month")["duration_hours"].sum().reset_index()
monthly.columns = ["Month", "Hours"]

fig = px.line(
    monthly,
    x="Month",
    y="Hours",
    title="Hours Tracked per Month",
    markers=True,
)
fig.update_traces(
    line=dict(color=COLORS["cyan"], width=2.5),
    marker=dict(
        color=COLORS["cyan"],
        size=8,
        line=dict(color=COLORS["bg"], width=1.5),
    ),
)
# Add a gradient fill under the line
fig.add_trace(go.Scatter(
    x=monthly["Month"],
    y=monthly["Hours"],
    fill="tozeroy",
    fillcolor=f"rgba(0, 255, 249, 0.08)",
    line=dict(width=0),
    showlegend=False,
    hoverinfo="skip",
))
neon_chart_layout(fig, height=400)
fig.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Daily activity heatmap (GitHub-style)
# ---------------------------------------------------------------------------

st.subheader("Daily Activity Heatmap")

daily = df.groupby("start_date")["duration_hours"].sum().reset_index()
daily.columns = ["Date", "Hours"]
daily["Date"] = pd.to_datetime(daily["Date"])
daily["Weekday"] = daily["Date"].dt.dayofweek
# Use ISO year (not calendar year) so Dec 31 in ISO week 1 groups with the
# correct year -- prevents week-1 data collisions in the heatmap pivot.
iso_cal = daily["Date"].dt.isocalendar()
daily["Week"] = iso_cal.week.astype(int)
daily["Year"] = iso_cal.year.astype(int)

day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _render_heatmap(data: pd.DataFrame, title: str, height: int = 220):
    """Render a single GitHub-style heatmap for the given daily data."""
    pivot = data.pivot_table(
        index="Weekday", columns="Week", values="Hours", aggfunc="sum"
    )
    # Fill all 53 ISO weeks so empty weeks render as dark cells, not gaps
    pivot = pivot.reindex(columns=range(1, 54), fill_value=0).fillna(0)
    # Ensure all 7 weekdays are present
    pivot = pivot.reindex(index=range(7), fill_value=0).fillna(0)

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[f"W{w}" for w in pivot.columns],
        y=[day_labels[i] for i in pivot.index],
        colorscale=SCALE_NEON_HEATMAP,
        hovertemplate="Week %{x}<br>%{y}<br>%{z:.1f} hours<extra></extra>",
        xgap=2,
        ygap=2,
    ))
    neon_chart_layout(fig, height=height)
    fig.update_layout(
        title=title,
        yaxis=dict(autorange="reversed"),
        xaxis=dict(side="top"),
        coloraxis_colorbar=dict(
            title="Hours",
            tickfont=dict(color=COLORS["text_muted"]),
            title_font=dict(color=COLORS["text_muted"]),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)


if view_mode == "Single Year":
    heatmap_data = daily[daily["Year"] == selected_year]
    if not heatmap_data.empty:
        _render_heatmap(heatmap_data, f"Daily Hours Tracked — {selected_year}")
else:
    # Show a small-multiples heatmap: one row per year, most recent first
    heatmap_years = sorted(daily["Year"].unique(), reverse=True)
    for yr in heatmap_years:
        yr_data = daily[daily["Year"] == yr]
        if not yr_data.empty:
            _render_heatmap(yr_data, f"{yr}", height=180)

st.divider()

# ---------------------------------------------------------------------------
# Top descriptions / most common activities
# ---------------------------------------------------------------------------

st.subheader("Most Common Activities")

desc_counts = (
    df[df["description"].notna() & (df["description"] != "")]
    .groupby("description")
    .agg(count=("id", "count"), total_hours=("duration_hours", "sum"))
    .reset_index()
    .sort_values("total_hours", ascending=False)
    .head(30)
)
desc_counts.columns = ["Description", "Entries", "Total Hours"]
desc_counts["Avg Hours"] = desc_counts["Total Hours"] / desc_counts["Entries"]

st.dataframe(
    desc_counts.style.format({"Total Hours": "{:.1f}", "Avg Hours": "{:.2f}"}),
    use_container_width=True,
    hide_index=True,
)
