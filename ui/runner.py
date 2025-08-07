# ui/runner.py

import streamlit as st
from logic.solver import assign_rooms

def run_assignment():
    st.session_state["log_lines"] = []
    families_df = st.session_state["families"]
    rooms_df    = st.session_state["rooms"]

    # --- New budget controls ---
    st.sidebar.markdown("### Solver Budgets")
    time_limit_sec = st.sidebar.slider(
        "Time limit per room_type (seconds)",
        min_value=5.0, max_value=120.0, value=60.0, step=5.0
    )
    node_limit = st.sidebar.slider(
        "Node limit per room_type",
        min_value=50_000, max_value=1_000_000, value=500_000, step=50_000
    )
    solve_per_type = st.sidebar.checkbox(
        "Solve per room_type", value=True
    )

    # Clear prior results
    st.session_state["assigned"]   = pd.DataFrame()
    st.session_state["unassigned"] = pd.DataFrame()

    # Run solver with dynamic budgets
    assigned_df, unassigned_df = assign_rooms(
        families_df,
        rooms_df,
        log_func=lambda m: st.session_state["log_lines"].append(m),
        time_limit_sec=time_limit_sec,
        node_limit=node_limit,
        solve_per_type=solve_per_type,
    )

    st.session_state["assigned"]   = assigned_df
    st.session_state["unassigned"] = unassigned_df
