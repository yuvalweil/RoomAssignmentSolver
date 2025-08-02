# app.py — single-page entry with robust import diagnostics
import streamlit as st
import sys, os, traceback
from pathlib import Path
import importlib.util

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# ---- Ensure local packages (ui/, logic/) are importable
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _diagnostics(err: Exception):
    """Render helpful info if imports fail."""
    st.error("Couldn't import UI modules. See diagnostics below.")
    with st.expander("🔎 Import diagnostics", expanded=True):
        st.write("**Working directory:**", os.getcwd())
        st.write("**app.py directory:**", str(ROOT))

        ui_dir = ROOT / "ui"
        logic_dir = ROOT / "logic"
        st.write("**ui/ exists:**", ui_dir.exists(), "  **logic/ exists:**", logic_dir.exists())

        def list_dir(p: Path, max_items=50):
            try:
                items = [f.name + ("/" if f.is_dir() else "") for f in sorted(p.iterdir())][:max_items]
                return items
            except Exception:
                return []

        st.write("**Root contents:**", list_dir(ROOT))
        st.write("**ui/ contents:**", list_dir(ui_dir))
        st.write("**logic/ contents:**", list_dir(logic_dir))

        # Show whether Python can locate these modules at all
        st.write("**find_spec('ui') ->**", bool(importlib.util.find_spec("ui")))
        st.write("**find_spec('ui.helpers') ->**", bool(importlib.util.find_spec("ui.helpers")))
        st.write("**find_spec('logic') ->**", bool(importlib.util.find_spec("logic")))

        # If helpers exists, show first few lines to catch syntax issues
        helpers_path = ui_dir / "helpers.py"
        if helpers_path.exists():
            st.write(f"**Preview {helpers_path.name}:**")
            try:
                txt = helpers_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                st.code("\n".join(txt[:120]) + ("\n... (truncated)" if len(txt) > 120 else ""), language="python")
            except Exception as e:
                st.write("Couldn't read helpers.py:", e)

        st.write("**Original ImportError/traceback:**")
        st.exception(err)

    st.stop()  # stop running the rest of the app

# ---- Try importing your UI modules
try:
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
        # If you already added it:
        # render_daily_operations_sheet,
    )
except Exception as e:
    _diagnostics(e)

# ---- Normal app flow (runs only if imports succeed)
ensure_session_keys()
render_uploads()
render_recalc_button()

render_assigned_overview()
render_date_or_range_view()
# If you implemented the printable daily sheet, uncomment:
# render_daily_operations_sheet()

render_manual_override()
render_diagnostics()
render_what_if()
render_logs()
