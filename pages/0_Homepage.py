"""
Homepage page: card-based journal of Highlight-tagged time entries
for the current week.
"""

import streamlit as st
from datetime import date, datetime, timedelta
import os

from src.theme import apply_theme
from src.data_store import get_connection, get_entries_df
from src.sync import sync_all, get_sync_status

apply_theme()

# ---------------------------------------------------------------------------
# Main content: Homepage -- This Week's Highlights
# ---------------------------------------------------------------------------

st.title("Homepage")

sync_status = get_sync_status()

if not sync_status["has_data"]:
    st.info(
        "**Getting started:**\n\n"
        "1. Copy `.env.example` to `.env`\n"
        "2. Paste your Toggl API token (from https://track.toggl.com/profile)\n"
        "3. Click **Full Sync** in the sidebar to download your history\n\n"
        "This will take about 1 minute for 8-9 years of data."
    )

    # Auto-sync: if the API token is configured but no data exists
    # (e.g. cold start on Streamlit Cloud), run a full sync automatically.
    token = os.getenv("TOGGL_API_TOKEN", "")
    if not token:
        try:
            token = st.secrets.get("TOGGL_API_TOKEN", "")
        except Exception:
            pass
    if token:
        st.subheader("Auto-syncing your data...")
        try:
            from src.toggl_client import TogglClient
            client = TogglClient()
            auto_bar = st.progress(0)
            auto_status = st.empty()

            def on_auto_progress(msg, frac):
                auto_status.text(msg)
                auto_bar.progress(min(frac, 1.0))

            import time
            result = sync_all(client, earliest_year=2017, progress_callback=on_auto_progress)
            st.success(
                f"Auto-sync complete! {result['total_entries']} entries across "
                f"{result['years_synced']} years."
            )
            time.sleep(1.5)
            st.rerun()
        except Exception as e:
            st.error(f"Auto-sync failed: {e}")
            st.caption("You can try again using the Full Sync button in the sidebar.")

    st.stop()

# ---------------------------------------------------------------------------
# Query: Highlight entries for the current ISO week
# ---------------------------------------------------------------------------

today = date.today()
iso_year, iso_week, _ = today.isocalendar()

# Compute the Monday-Sunday date range for this ISO week
monday = datetime.strptime(f"{iso_year}-W{iso_week:02d}-1", "%G-W%V-%u").date()
sunday = monday + timedelta(days=6)

conn = get_connection()
df = get_entries_df(conn, start_date=monday.isoformat(), end_date=sunday.isoformat())
conn.close()

# Filter to entries that carry the "Highlight" tag
if not df.empty and "tags_list" in df.columns:
    highlights = df[df["tags_list"].apply(lambda tags: "Highlight" in tags)].copy()
else:
    highlights = df.iloc[0:0]  # empty DataFrame with same columns

# ---------------------------------------------------------------------------
# Render: week header + card journal
# ---------------------------------------------------------------------------

st.markdown(
    f"### This Week's Highlights"
)
st.caption(
    f"Week {iso_week}  --  {monday.strftime('%b %d')} to {sunday.strftime('%b %d, %Y')}"
)

if highlights.empty:
    st.markdown("")
    st.info("No highlights logged this week yet.")
else:
    # Sort chronologically so the journal reads like a timeline
    highlights = highlights.sort_values("start", ascending=True)

    for _, row in highlights.iterrows():
        # Parse start datetime for display
        try:
            start_dt = datetime.fromisoformat(str(row["start"]).replace("Z", "+00:00"))
            day_label = start_dt.strftime("%a, %b %d")      # e.g. "Mon, Feb 23"
            time_label = start_dt.strftime("%H:%M")          # e.g. "09:15"
        except (ValueError, TypeError):
            day_label = str(row.get("start_date", ""))
            time_label = ""

        description = row.get("description") or "(no description)"
        project = row.get("project_name") or ""
        hours = row.get("duration_hours", 0)

        # Format the duration as a readable string
        if hours >= 1:
            dur_str = f"{hours:.1f}h"
        else:
            dur_str = f"{int(hours * 60)}m"

        # Build the metadata line: day . project . duration . time
        meta_parts = [day_label]
        if project:
            meta_parts.append(project)
        meta_parts.append(dur_str)
        if time_label:
            meta_parts.append(time_label)
        meta_line = "  \u00b7  ".join(meta_parts)

        # Render a card using a bordered container
        with st.container(border=True):
            st.markdown(f"**{description}**")
            st.caption(meta_line)
