# app.py — Home page
import streamlit as st

# Ensure local packages are importable (helps when running from different CWDs)
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

# Sidebar hint (we use Streamlit's built-in page picker in the sidebar)
with st.sidebar:
    st.markdown("### Navigation\nUse the page picker above to switch pages.")
    st.markdown("---")

# Initialize session state
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
