# DEPRECATED: Streamlit entrypoint. See frontend/ for the Firebase SPA.
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
import os

is_authenticated = st.session_state.get("authenticated", False)

st.set_page_config(
    page_title="Toggl Time Journal",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="expanded" if is_authenticated else "collapsed",
)

if not is_authenticated:
    st.markdown(
        """
        <style>
            [data-testid="collapsedControl"] { display: none; }
            [data-testid="stSidebar"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Login Required")
    with st.form("login_form"):
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if pwd == os.getenv("DASHBOARD_PASSWORD", "290391"):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password")
    st.stop()


from src.theme import apply_theme

apply_theme()

from src.sync import sync_all, sync_current_year, sync_enriched_all, get_sync_status
from src.data_store import get_connection, get_enrichment_stats

# ---------------------------------------------------------------------------
# Navigation: declare all pages (replaces pages/ auto-discovery)
# ---------------------------------------------------------------------------

pg = st.navigation(
    [
        st.Page(
            "pages/0_Homepage.py", title="Homepage", icon="\U0001f3e0", default=True
        ),
        st.Page("pages/1_Dashboard.py", title="Dashboard", icon="\U0001f4ca"),
        st.Page("pages/2_Retrospect.py", title="Retrospect", icon="\U0001f50d"),
        st.Page("pages/3_Chat.py", title="Chat", icon="\U0001f4ac"),
    ]
)

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
        st.sidebar.caption(
            f"Last quick sync: {sync_status['last_incremental_sync'][:16]}"
        )
    if sync_status["last_enriched_sync"]:
        st.sidebar.caption(
            f"Last enriched sync: {sync_status['last_enriched_sync'][:16]}"
        )
else:
    st.sidebar.warning("No data yet. Run a full sync to get started.")

st.sidebar.divider()

# Quick sync (current year only)
if st.sidebar.button(
    "Quick Sync (current year)", type="primary", use_container_width=True
):
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
    earliest = st.number_input(
        "Earliest year", min_value=2006, max_value=date.today().year, value=2017
    )
    if st.button("Run Full Sync", use_container_width=True):
        try:
            from src.toggl_client import TogglClient

            client = TogglClient()
            progress_bar = st.progress(0)
            status_text = st.empty()

            def on_full_progress(msg, frac):
                status_text.text(msg)
                progress_bar.progress(min(frac, 1.0))

            result = sync_all(
                client, earliest_year=int(earliest), progress_callback=on_full_progress
            )
            st.success(
                f"Synced {result['total_entries']} entries across {result['years_synced']} years "
                f"({result['projects']} projects, {result['tags']} tags)"
            )
            time.sleep(1.5)
            st.rerun()
        except Exception as e:
            st.error(f"Sync failed: {e}")

# Enriched sync — pulls full JSON data while on Premium
with st.sidebar.expander("Enriched Sync (Premium)", expanded=False):
    st.caption(
        "Pulls native Toggl IDs, project_id, tag_ids, task data, client names, "
        "and Premium project fields via the JSON API. "
        "Requires ~2 hrs on Premium (600 req/hr). "
        "Enriched data persists after Premium expires."
    )

    # Show current enrichment coverage if data exists
    if sync_status["has_data"]:
        try:
            _conn = get_connection()
            _stats = get_enrichment_stats(_conn)
            _conn.close()
            _pct = (
                int(100 * _stats["enriched_entries"] / _stats["total_entries"])
                if _stats["total_entries"] > 0
                else 0
            )
            st.metric(
                "Enrichment Coverage",
                f"{_stats['enriched_entries']:,} / {_stats['total_entries']:,} ({_pct}%)",
            )
            if sync_status["last_enriched_sync"]:
                st.caption(f"Last enriched: {sync_status['last_enriched_sync'][:16]}")
            if _stats["total_tasks"] > 0 or _stats["total_clients"] > 0:
                st.caption(
                    f"{_stats['total_tasks']} tasks · {_stats['total_clients']} clients stored"
                )
        except Exception:
            pass

    st.caption(
        "Note: Streamlit Cloud has an ephemeral filesystem. "
        "Enriched data is lost on cold start and must be re-synced manually."
    )

    earliest_e = st.number_input(
        "Earliest year",
        min_value=2006,
        max_value=date.today().year,
        value=2017,
        key="enriched_earliest",
    )
    if st.button("Run Enriched Sync", use_container_width=True, type="secondary"):
        try:
            from src.toggl_client import TogglClient

            client = TogglClient()
            progress_bar = st.progress(0)
            status_text = st.empty()

            def on_enrich_progress(msg, frac):
                status_text.text(msg)
                progress_bar.progress(min(frac, 1.0))

            result = sync_enriched_all(
                client,
                earliest_year=int(earliest_e),
                progress_callback=on_enrich_progress,
            )
            st.success(
                f"Enriched {result['total_entries']:,} entries across {result['years_enriched']} years "
                f"({result['tasks']} tasks, {result['clients']} clients)"
            )
            if result["errors"]:
                st.warning(
                    f"{len(result['errors'])} year(s) failed: {', '.join(result['errors'])}"
                )
            time.sleep(1.5)
            st.rerun()
        except Exception as e:
            st.error(f"Enriched sync failed: {e}")

# ---------------------------------------------------------------------------
# Run the selected page
# ---------------------------------------------------------------------------

pg.run()
