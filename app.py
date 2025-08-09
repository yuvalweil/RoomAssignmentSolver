import streamlit as st

# --- Ensure local packages (ui/, logic/) are importable ----------------------
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# -----------------------------------------------------------------------------

from ui.helpers import ensure_session_keys
from ui.upload import render_uploads
from ui.sections import (
    render_recalc_button,
    render_assigned_overview,
    render_date_or_range_view,
    render_daily_operations_sheet,  # NEW
    render_manual_override,
    render_diagnostics,
    render_what_if,
    render_logs,
)

st.set_page_config(
    page_title="Room Assignment",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🏕️ Room Assignment System")

# init session keys
ensure_session_keys()

# Uploads (reads CSVs + auto-run if both present)
render_uploads()

# Recalculate button
render_recalc_button()

# Sections
render_assigned_overview()
render_date_or_range_view()
render_daily_operations_sheet()      # NEW: printable daily sheet + download
render_manual_override()
render_diagnostics()
render_what_if()
render_logs()
