import streamlit as st
import sys
from pathlib import Path

# Make sure we can import local packages when running from /pages
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.helpers import ensure_session_keys

st.set_page_config(page_title="Assignment Log", layout="wide")
st.title("🐞 Assignment Log")

ensure_session_keys()

logs = st.session_state.get("log_lines", [])
if not logs:
    st.info("No logs yet. Run an assignment on the Home page.")
else:
    n = st.slider("Show last N lines", min_value=20, max_value=1000, value=200, step=20)
    tail = logs[-n:]
    st.text_area("Log (compact)", value="\n".join(tail), height=300, label_visibility="collapsed")

    st.download_button(
        "📥 Download Log",
        "\n".join(logs).encode("utf-8-sig"),
        file_name="assignment.log",
        mime="text/plain",
    )
