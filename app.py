# app.py — Home page
import streamlit as st

# Ensure local packages are importable (works when running pages/* too)
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.helpers import ensure_session_keys
from ui.upload import render_uploads
from ui.sections import (
    render_recalc_button,
    render_date_or_range_view,
    render_manual_override,
    render_diagnostics,
    render_what_if,
)

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# Sidebar navigation (links only to files under pages/)
with st.sidebar:
    st.header("Navigation")
    # Some Streamlit versions don't register the main script as a page.
    # We skip a Home link to avoid KeyError and just link to sub-pages.
    try:
        st.page_link("pages/01_Assigned_All.py", label="✅ Assigned Families (All)")
        st.page_link("pages/99_Assignment_Log.py", label="🐞 Assignment Log")
    except Exception:
        # If page_link isn't available or pages aren't registered yet:
        st.info("Use the sidebar page picker (or update Streamlit to enable page links).")

    # Optional quick status
    st.markdown("---")
    ensure_session_keys()  # safe to call here too
    assigned = st.session_state.get("assigned")
    unassigned = st.session_state.get("unassigned")
    st.caption(
        f"Assigned rows: **{0 if assigned is None or assigned.empty else len(assigned)}**"
        + f"\n\nUnassigned rows: **{0 if unassigned is None or unassigned.empty else len(unassigned)}**"
    )

# Initialize session state (main page flow)
ensure_session_keys()

# Uploads (reads CSVs + autorun assignment when both CSVs present)
render_uploads()

# Manual recalc
render_recalc_button()

# Main sections on Home
render_date_or_range_view()
render_manual_override()
render_diagnostics()
render_what_if()
