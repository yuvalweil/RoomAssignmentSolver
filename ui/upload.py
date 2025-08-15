import streamlit as st
import pandas as pd
from .helpers import read_csv
from .runner import run_assignment

from logic.solver   import assign_rooms
from logic.validate import validate_constraints

def render_uploads():
    st.markdown("### 📁 Upload Guest & Room Lists")

    use_links = st.toggle(
        "Use links instead of file upload",
        key="use_links",
        help="Switch to provide URLs pointing to the CSV files.",
    )

    # Clear previous data when switching modes
    if st.session_state.get("_last_use_links") != use_links:
        st.session_state["families"] = pd.DataFrame()
        st.session_state["rooms"] = pd.DataFrame()
        st.session_state["_last_use_links"] = use_links

    if use_links:
        link_col1, link_col2 = st.columns(2)

        with link_col1:
            fam_url = st.text_input(
                "👨‍👩‍👧 Families CSV URL",
                key="fam_url",
                placeholder="https://example.com/families.csv",
            )

        with link_col2:
            room_url = st.text_input(
                "🏠 Rooms CSV URL",
                key="room_url",
                placeholder="https://example.com/rooms.csv",
            )

        if fam_url:
            try:
                st.session_state["families"] = read_csv(fam_url)
            except Exception as e:
                st.error(f"Failed to load families CSV: {e}")
        if room_url:
            try:
                st.session_state["rooms"] = read_csv(room_url)
            except Exception as e:
                st.error(f"Failed to load rooms CSV: {e}")
    else:
        upload_col1, upload_col2 = st.columns(2)

        with upload_col1:
            fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv", label_visibility="collapsed")
            st.markdown(
                "*👨‍👩‍👧 Families*",
                help="Upload your families.csv (supports Hebrew headers).",
            )

        with upload_col2:
            room_file = st.file_uploader("🏠 Rooms CSV", type="csv", label_visibility="collapsed")
            st.markdown(
                "*🏠 Rooms*",
                help="Upload your rooms.csv (room numbers may repeat across room types).",
            )

        if fam_file:
            st.session_state["families"] = read_csv(fam_file)
        if room_file:
            st.session_state["rooms"] = read_csv(room_file)

    # Auto run after both are present and no prior assignment
    if (
        st.session_state.get("assigned", pd.DataFrame()).empty
        and not st.session_state["families"].empty
        and not st.session_state["rooms"].empty
    ):
        run_assignment()
