"""
Toggl Time Journal -- Router / Entrypoint.

Uses st.navigation + st.Page to declare all pages explicitly.
This file runs on every rerun and renders the shared sidebar
(sync controls) before delegating to the selected page.

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

from src.sync import sync_all, sync_current_year, get_sync_status

# ---------------------------------------------------------------------------
# Navigation: declare all pages (replaces pages/ auto-discovery)
# ---------------------------------------------------------------------------

pg = st.navigation([
    st.Page("pages/0_Homepage.py", title="Homepage", icon="\U0001f3e0", default=True),
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="\U0001f4ca"),
    st.Page("pages/2_Retrospect.py", title="Retrospect", icon="\U0001f50d"),
    st.Page("pages/3_Chat.py", title="Chat", icon="\U0001f4ac"),
])

# ---------------------------------------------------------------------------
# Sidebar: Sync controls (shared across all pages)
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
# Run the selected page
# ---------------------------------------------------------------------------

pg.run()
