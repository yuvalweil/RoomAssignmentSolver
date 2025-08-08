from __future__ import annotations
import streamlit as st

st.set_page_config(page_title="Room Assignment — Assigned per date/range", page_icon="📆", layout="wide")
st.title("Assigned per date/range")

try:
    from ui.sections import render_date_or_range_view
except Exception:
    render_date_or_range_view = None

def guard_data():
    if "families_df" not in st.session_state or "rooms_df" not in st.session_state:
        st.warning("Please upload `families.csv` and `rooms.csv` on the **Main** page first.")
        st.stop()

guard_data()

if render_date_or_range_view:
    render_date_or_range_view()
else:
    st.error("`render_date_or_range_view()` not found in ui/sections.py")
