# app.py — Single-page app entry
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
    render_daily_operations_sheet,  # NEW section
    render_manual_override,
    render_diagnostics,
    render_what_if,
    render_logs,
)

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# Initialize session keys
ensure_session_keys()

# Uploads (reads CSVs + auto-run when both CSVs are present)
render_uploads()

# Manual recalc
render_recalc_button()

# Main sections
render_assigned_overview()
render_date_or_range_view()
render_daily_operations_sheet()      # NEW: printable daily sheet builder
render_manual_override()
render_diagnostics()
render_what_if()
render_logs()
