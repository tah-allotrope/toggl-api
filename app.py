"""
Toggl Time Journal -- Main app entry point.

This is the home page that shows overall stats and provides sync controls.
Streamlit auto-discovers pages in the pages/ directory.

Run with:  streamlit run app.py
"""

import streamlit as st
from datetime import date
import time

st.set_page_config(
    page_title="Toggl Time Journal",
    page_icon="\u23f0",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.theme import apply_theme
apply_theme()

from src.data_store import get_connection, get_total_stats, get_available_years
from src.sync import sync_all, sync_current_year, get_sync_status

# ---------------------------------------------------------------------------
# Sidebar: Sync controls
# ---------------------------------------------------------------------------

st.sidebar.title("Data Sync")

sync_status = get_sync_status()

if sync_status["has_data"]:
    years = sync_status["years_with_data"]
    st.sidebar.success(f"Data loaded: {min(years)}-{max(years)}")
    if sync_status["last_full_sync"]:
        st.sidebar.caption(f"Last full sync: {sync_status['last_full_sync'][:16]}")
    if sync_status["last_incremental_sync"]:
        st.sidebar.caption(f"Last quick sync: {sync_status['last_incremental_sync'][:16]}")
else:
    st.sidebar.warning("No data yet. Run a full sync to get started.")

st.sidebar.divider()

# Quick sync (current year only)
if st.sidebar.button("Quick Sync (current year)", type="primary", use_container_width=True):
    try:
        from src.toggl_client import TogglClient
        client = TogglClient()
        progress_bar = st.sidebar.progress(0)
        status_text = st.sidebar.empty()

        def on_progress(msg, frac):
            status_text.text(msg)
            progress_bar.progress(min(frac, 1.0))

        result = sync_current_year(client, progress_callback=on_progress)
        st.sidebar.success(f"Synced {result['entries']} entries for {result['year']}")
        time.sleep(1.5)
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Sync failed: {e}")

# Full sync
with st.sidebar.expander("Full Sync (all years)"):
    earliest = st.number_input("Earliest year", min_value=2006, max_value=date.today().year, value=2017)
    if st.button("Run Full Sync", use_container_width=True):
        try:
            from src.toggl_client import TogglClient
            client = TogglClient()
            progress_bar = st.progress(0)
            status_text = st.empty()

            def on_full_progress(msg, frac):
                status_text.text(msg)
                progress_bar.progress(min(frac, 1.0))

            result = sync_all(client, earliest_year=int(earliest), progress_callback=on_full_progress)
            st.success(
                f"Synced {result['total_entries']} entries across {result['years_synced']} years "
                f"({result['projects']} projects, {result['tags']} tags)"
            )
            time.sleep(1.5)
            st.rerun()
        except Exception as e:
            st.error(f"Sync failed: {e}")

# ---------------------------------------------------------------------------
# Main content: Overview stats
# ---------------------------------------------------------------------------

st.title("Toggl Time Journal")
st.markdown("Your personal time tracking history, visualized and searchable.")

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
    import os
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

# Show overview stats
conn = get_connection()
stats = get_total_stats(conn)
years = get_available_years(conn)
conn.close()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Hours", f"{stats['total_hours']:,.0f}")
col2.metric("Total Entries", f"{stats['total_entries']:,}")
col3.metric("Unique Projects", str(stats['unique_projects']))
col4.metric("Years Tracked", str(stats['years_tracked']))

st.divider()

st.markdown(f"**Data range:** {stats['earliest_date']} to {stats['latest_date']}")
st.markdown(f"**Years with data:** {', '.join(str(y) for y in years)}")

st.divider()

st.markdown("### Navigate")
st.markdown(
    "Use the sidebar to navigate between pages:\n\n"
    "- **Dashboard** -- Year-level charts, project breakdowns, activity heatmaps\n"
    "- **Retrospect** -- \"On this day\" across all years, week and year comparisons\n"
    "- **Chat** -- Ask questions about your time data in natural language"
)
