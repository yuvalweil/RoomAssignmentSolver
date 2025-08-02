import streamlit as st
import pandas as pd
from datetime import datetime as dt, time
from logic import assign_rooms

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# Upload section
st.markdown("### 📁 Upload Guest & Room Lists")
upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv", label_visibility="collapsed")
    st.markdown("*👨‍👩‍👧 Families*", help="Upload your families.csv file")

with upload_col2:
    room_file = st.file_uploader("🏠 Rooms CSV", type="csv", label_visibility="collapsed")
    st.markdown("*🏠 Rooms*", help="Upload your rooms.csv file")

if fam_file:
    st.session_state["families"] = pd.read_csv(fam_file)

if room_file:
    st.session_state["rooms"] = pd.read_csv(room_file)

def run_assignment():
    try:
        st.session_state["debug_log"] = []

        def log(msg):
            st.session_state["debug_log"].append(msg)

        assigned_df, unassigned_df = assign_rooms(
            st.session_state["families"],
            st.session_state["rooms"],
            log_func=log
        )
        st.session_state["assigned"] = assigned_df
        st.session_state["unassigned"] = unassigned_df
        st.success("✅ Room assignment completed.")
    except Exception as e:
        st.error(f"❌ Assignment error: {e}")

if "assigned" not in st.session_state and "families" in st.session_state and "rooms" in st.session_state:
    run_assignment()

if "families" in st.session_state and "rooms" in st.session_state:
    if st.button("🔁 Recalculate Assignment"):
        run_assignment()

st.markdown("## 📋 Full Assignment Overview")
col1, col2 = st.columns(2)

with col1:
    if "assigned" in st.session_state:
        st.subheader("✅ Assigned Families (All)")
        st.dataframe(st.session_state["assigned"], use_container_width=True)
        csv = st.session_state["assigned"].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Assigned", csv, "assigned_families.csv", "text/csv")

with col2:
    if "unassigned" in st.session_state and not st.session_state["unassigned"].empty:
        st.subheader("⚠️ Unassigned Families (All)")
        unassigned_display = st.session_state["unassigned"].drop(columns=["id"], errors="ignore")
        st.dataframe(unassigned_display, use_container_width=True)

# Display debug log
if "debug_log" in st.session_state:
    with st.expander("🛠️ Debug Log"):
        for line in st.session_state["debug_log"]:
            st.text(line)
