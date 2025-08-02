import streamlit as st
from ui.helpers import ensure_session_keys
from ui.upload import render_uploads
from ui.sections import (
    render_recalc_button,
    render_assigned_overview,
    render_date_or_range_view,
    render_manual_override,
    render_diagnostics,
    render_what_if,
    render_logs,
)

st.set_page_config(page_title="Room Assignment", layout="wide")
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
render_manual_override()
render_diagnostics()
render_what_if()
render_logs()
