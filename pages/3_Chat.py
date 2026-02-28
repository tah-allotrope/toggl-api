"""
Chat page: conversational interface to query your time data.

Uses a built-in pattern-matching query engine for now.
Designed with a clear extension point for AI API integration later.
"""

import streamlit as st
from src.queries import answer_question
from src.data_store import get_connection, get_available_years

st.set_page_config(page_title="Chat", page_icon="\U0001f4ac", layout="wide")

from src.theme import apply_theme
apply_theme()

st.title("Chat with Your Time Data")

conn = get_connection()
years = get_available_years(conn)
conn.close()

if not years:
    st.warning("No data available. Please run a sync from the home page.")
    st.stop()

st.caption(f"Data available for: {min(years)}-{max(years)}")

# ---------------------------------------------------------------------------
# Chat state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hi! I can help you explore your Toggl time tracking history. "
                "Here's what I can do:\n\n"
                '**Time periods:**\n'
                '- "How was 2024?" -- Year summary\n'
                '- "What did I do on March 15?" -- Date across all years\n'
                '- "In February 2024" -- Monthly summary\n'
                '- "This week" / "Last week" -- Weekly view\n'
                '- "Today" / "Yesterday" -- Today in history\n\n'
                '**Projects & Tags:**\n'
                '- "Top projects" / "Top projects in 2024" -- Project ranking\n'
                '- "Top tags" -- Tag ranking\n'
                '- Just type a project name (e.g. "Work", "Health") -- Project details\n'
                '- "Tag Highlight" / "Tagged Deep in 2024" -- Tag details\n\n'
                '**Analysis:**\n'
                '- "Compare 2023 and 2024" -- Year comparison\n'
                '- "Total hours" -- All-time stats\n'
                '- "Search meditation" -- Keyword search across descriptions, projects & tags\n\n'
                "What would you like to know?"
            ),
        }
    ]

# ---------------------------------------------------------------------------
# Display chat history
# ---------------------------------------------------------------------------

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask about your time data..."):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate answer
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = answer_question(prompt)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

# ---------------------------------------------------------------------------
# Quick action buttons
# ---------------------------------------------------------------------------

st.divider()
st.markdown("**Quick queries:**")

col1, col2, col3 = st.columns(3)
col4, col5, col6 = st.columns(3)

quick_queries = [
    (col1, "Today in history", "today"),
    (col2, "This week", "this week"),
    (col3, "Total stats", "total hours all time"),
    (col4, "Top projects", "top projects"),
    (col5, "Top tags", "top tags"),
    (col6, "Yesterday", "yesterday"),
]

for col, label, query in quick_queries:
    if col.button(label, use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": query})
        answer = answer_question(query)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()
