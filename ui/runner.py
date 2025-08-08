import streamlit as st
import pandas as pd
from logic.solver import assign_rooms

def run_assignment():
    """
    Recalculate room assignments using fixed solver budgets:
      - time_limit_sec = 60.0 seconds per room_type
      - node_limit = 500_000 nodes per room_type
      - solve_per_type = True
    """
    # Initialize/clear log
    st.session_state["log_lines"] = []

    families_df = st.session_state.get("families", pd.DataFrame())
    rooms_df    = st.session_state.get("rooms", pd.DataFrame())

    # Clear previous outputs
    st.session_state["assigned"]   = pd.DataFrame()
    st.session_state["unassigned"] = pd.DataFrame()

    # Fixed budgets
    time_limit_sec = 60.0
    node_limit     = 500_000
    solve_per_type = True

    # NEW: read toggle (default True)
    use_soft = bool(st.session_state.get("use_soft_constraints", True))

    assigned_df, unassigned_df = assign_rooms(
        families_df,
        rooms_df,
        log_func=lambda msg: st.session_state["log_lines"].append(msg),
        time_limit_sec=time_limit_sec,
        node_limit=node_limit,
        solve_per_type=solve_per_type,
        use_soft=use_soft,   # <<--- pass the flag
    )

    st.session_state["assigned"]   = assigned_df
    st.session_state["unassigned"] = unassigned_df
