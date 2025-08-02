import streamlit as st
import pandas as pd
from .helpers import read_csv
from .runner import run_assignment

def render_uploads():
    st.markdown("### 📁 Upload Guest & Room Lists")
    upload_col1, upload_col2 = st.columns(2)

    with upload_col1:
        fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv", label_visibility="collapsed")
        st.markdown("*👨‍👩‍👧 Families*", help="Upload your families.csv (supports Hebrew headers).")

    with upload_col2:
        room_file = st.file_uploader("🏠 Rooms CSV", type="csv", label_visibility="collapsed")
        st.markdown("*🏠 Rooms*", help="Upload your rooms.csv (room numbers may repeat across room types).")

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
