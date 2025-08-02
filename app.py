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
# SECTION 2: Filter by Date Range
# ========================
st.markdown("---")
st.markdown("## 📅 View Assignments and Unassigned for Date Range")

if "assigned" in st.session_state and "unassigned" in st.session_state:

    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input("📅 Start Date", format="DD/MM/YYYY", key="start_date")
    with date_col2:
        end_date = st.date_input("📅 End Date", format="DD/MM/YYYY", key="end_date")

    if start_date > end_date:
        st.warning("⚠️ End date must be after start date.")
    else:
        start_dt = dt.combine(start_date, time.min)
        end_dt = dt.combine(end_date, time.max)

        # Filter assigned
        assigned_df = st.session_state["assigned"].copy()
        assigned_df["check_in_dt"] = pd.to_datetime(assigned_df["check_in"], format="%d/%m/%Y")
        assigned_df["check_out_dt"] = pd.to_datetime(assigned_df["check_out"], format="%d/%m/%Y")

        assigned_filtered = assigned_df[
            (assigned_df["check_in_dt"] < end_dt) & (assigned_df["check_out_dt"] > start_dt)
        ]

        # Filter unassigned
        unassigned_df = st.session_state["unassigned"].copy()
        if not unassigned_df.empty:
            unassigned_df["check_in_dt"] = pd.to_datetime(unassigned_df["check_in"], format="%d/%m/%Y")
            unassigned_df["check_out_dt"] = pd.to_datetime(unassigned_df["check_out"], format="%d/%m/%Y")

            unassigned_filtered = unassigned_df[
                (unassigned_df["check_in_dt"] < end_dt) & (unassigned_df["check_out_dt"] > start_dt)
            ]
        else:
            unassigned_filtered = pd.DataFrame()

        # Show results
        st.subheader(f"✅ Assigned Families from {start_date.strftime('%d/%m/%Y')} to {end_date.strftime('%d/%m/%Y')}")
        if not assigned_filtered.empty:
            st.da
