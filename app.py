import streamlit as st

# (optional) ensure local packages are importable even if CWD changes
import sys, os
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

# init session keys
ensure_session_keys()

# Uploads (reads CSVs + auto-run if both present)
render_uploads()

# Recalculate button
render_recalc_button()

# Keep these sections on Home
render_date_or_range_view()
render_manual_override()
render_diagnostics()
render_what_if()
