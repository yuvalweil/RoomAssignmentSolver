import streamlit as st
import pandas as pd
from datetime import datetime as dt, time
from logic import assign_rooms

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# ================
# UPLOAD SECTION
# ================
st.markdown("### 📁 Upload Guest & Room Lists")

upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv", label_visibility="collapsed")
    st.markdown("*👨‍👩‍👧 Families*", help="Upload your families.csv file")

with upload_col2:
    room_file = st.file_uploader("🏠 Rooms CSV", type="csv", label_visibility="collapsed")
    st.markdown("*🏠 Rooms*", help="Upload your rooms.csv file")

# Load uploaded data
if fam_file:
    st.session_state["families"] = pd.read_csv(fam_file)

if room_file:
    st.session_state["rooms"] = pd.read_csv(room_file)

# Run assignment
def run_assignment():
    try:
        assigned_df, unassigned_df = assign_rooms(
            st.session_state["families"],
            st.session_state["rooms"]
        )
        st.session_state["assigned"] = assigned_df
        st.session_state["unassigned"] = unassigned_df
        st.success("✅ Room assignment completed.")
    except Exception as e:
        st.error(f"❌ Assignment error: {e}")

# Auto-run
if "assigned" not in st.session_state and "families" in st.session_state and "rooms" in st.session_state:
    run_assignment()

# Recalculate manually
if "families" in st.session_state and "rooms" in st.session_state:
    if st.button("🔁 Recalculate Assignment"):
        run_assignment()

# ========================
# SECTION 1: All Data View
# ========================
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
        st.dataframe(st.session_state["unassigned"], use_container_width=True)

# ========================
# SECTION 2: Filter by Date
# ========================
st.markdown("---")
st.markdown("## 📅 View Assignments for Specific Date")

if "assigned" in st.session_state:
    selected_date = st.date_input("Select a date", format="DD/MM/YYYY")

    df = st.session_state["assigned"].copy()
    df["check_in_dt"] = pd.to_datetime(df["check_in"], format="%d/%m/%Y")
    df["check_out_dt"] = pd.to_datetime(df["check_out"], format="%d/%m/%Y")
    selected_datetime = dt.combine(selected_date, time.min)

    filtered_df = df[(selected_datetime >= df["check_in_dt"]) & (selected_datetime < df["check_out_dt"])]

    if not filtered_df.empty:
        st.success(f"✅ {len(filtered_df)} assignments found on {selected_date.strftime('%d/%m/%Y')}")
        st.dataframe(filtered_df[["family", "room", "check_in", "check_out"]], use_container_width=True)
    else:
        st.info("📭 No assignments for that date.")
