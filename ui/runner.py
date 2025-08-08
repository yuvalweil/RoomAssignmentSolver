# ui/runner.py
from __future__ import annotations
import streamlit as st
import pandas as pd

def run_assignment(use_soft: bool | None = None):
    # 1) read data
    families = st.session_state.get("families_df")
    rooms    = st.session_state.get("rooms_df")
    if families is None or rooms is None or families.empty or rooms.empty:
        raise ValueError("families_df/rooms_df missing or empty in session_state")

    # 2) read toggle from session unless explicitly provided
    if use_soft is None:
        use_soft = bool(st.session_state.get("use_soft_constraints", True))
    st.session_state["use_soft_constraints"] = use_soft  # keep canonical

    # 3) call your solver (adapt import if needed)
    from logic.solver import assign_per_type  # or assign_rooms / assign_all, etc.

    assigned_df, unassigned_df, meta = assign_per_type(
        families=families,
        rooms=rooms,
        use_soft=use_soft,
        # pass other budgets/args here if your solver expects them
    )

    # 4) guarantee DataFrames & expected columns exist
    assigned_df  = assigned_df.copy() if isinstance(assigned_df, pd.DataFrame) else pd.DataFrame()
    unassigned_df = unassigned_df.copy() if isinstance(unassigned_df, pd.DataFrame) else pd.DataFrame()

    # 5) STORE in session under stable keys that pages expect
    st.session_state["assigned_df"]   = assigned_df
    st.session_state["unassigned_df"] = unassigned_df
    st.session_state["assign_meta"]   = meta or {}

    # optional: derive date columns for fast filtering (used by date/range page)
    for df_key in ("assigned_df", "unassigned_df"):
        df = st.session_state[df_key]
        if not df.empty:
            for c in ("check_in", "check_out"):
                if c in df.columns and not c.endswith("_dt"):
                    df[f"{c}_dt"] = pd.to_datetime(df[c], format="%d/%m/%Y", errors="coerce")

    # 6) optional: return as well
    return assigned_df, unassigned_df, meta
