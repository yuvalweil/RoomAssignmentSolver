from __future__ import annotations
import streamlit as st
from logic.solver   import assign_rooms
from logic.validate import validate_constraints

def log_collector():
    def _log(msg: str):
        ts = dt.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["log_lines"].append(f"[{ts}] {msg}")
    return _log

def run_assignment():
    """Run the solver, store results in session_state, and show quick feedback."""
    try:
        st.session_state["log_lines"] = []
        log_func = log_collector()
        assigned_df, unassigned_df = assign_rooms(
            st.session_state["families"],
            st.session_state["rooms"],
            log_func=log_func,
        )
        st.session_state["assigned"]   = assigned_df
        st.session_state["unassigned"] = unassigned_df

        hard_ok, soft_violations = validate_constraints(assigned_df)
        if hard_ok:
            st.success("✅ Room assignment completed. No hard constraint violations.")
        else:
            st.error("❌ Assignment finished with HARD constraint violations. Please review.")
        if soft_violations:
            with st.expander("ℹ️ Soft constraint warnings", expanded=False):
                for s in soft_violations:
                    st.write(f"• {s}")
    except Exception as e:
        st.error(f"❌ Assignment error: {e}")
