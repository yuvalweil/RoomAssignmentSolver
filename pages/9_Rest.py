from __future__ import annotations
import streamlit as st

st.set_page_config(page_title="Room Assignment — Rest", page_icon="🧰", layout="wide")
st.title("Rest")

# Import the optional sections. Some may not exist in older code — handle gracefully.
try:
    from ui.sections import (
        render_recalculate_section,
        render_diagnostics_section,
        render_what_if_section,
        render_manual_override_section,
        render_logs_section,
        render_daily_sheet_section,  # feature-flagged inside your code
    )
except Exception:
    render_recalculate_section = None
    render_diagnostics_section = None
    render_what_if_section = None
    render_manual_override_section = None
    render_logs_section = None
    render_daily_sheet_section = None

def guard_data():
    if "families_df" not in st.session_state or "rooms_df" not in st.session_state:
        st.warning("Please upload `families.csv` and `rooms.csv` on the **Main** page first.")
        st.stop()

guard_data()

st.caption("Everything that isn't in the two Assigned pages lives here: Recalculate, Diagnostics, What‑if, Manual Override, Logs, and Daily Sheet (if enabled).")

# Recalculate (w/ soft constraints checkbox) — if present
if render_recalculate_section:
    st.header("Recalculate")
    render_recalculate_section()
else:
    st.info("Recalculate section unavailable in this build.")

# Diagnostics
if render_diagnostics_section:
    st.header("Diagnostics")
    render_diagnostics_section()
else:
    st.info("Diagnostics section unavailable in this build.")

# What-if
if render_what_if_section:
    st.header("What‑if Scenario")
    render_what_if_section()
else:
    st.info("What‑if section unavailable in this build.")

# Manual override
if render_manual_override_section:
    st.header("Manual Override")
    render_manual_override_section()
else:
    st.info("Manual Override section unavailable in this build.")

# Logs
if render_logs_section:
    st.header("Logs")
    render_logs_section()
else:
    st.info("Logs section unavailable in this build.")

# Daily sheet (respects your ENABLE_DAILY_SHEET flag internally)
if render_daily_sheet_section:
    st.header("Daily Operations Sheet")
    render_daily_sheet_section()
