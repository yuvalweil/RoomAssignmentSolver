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

# Run assignment logic
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

if "assigned" not in st.session_state and "families" in st.session_state and "rooms" in st.session_state:
    run_assignment()

if "families" in st.session_state and "rooms" in st.session_state:
    if st.button("🔁 Recalculate Assignment"):
        run_assignment()

# Show full assignments
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

# Toggle between range/single view
st.markdown("---")
st.markdown("## 📅 View Assignments for Date or Range")

if "range_mode" not in st.session_state:
    st.session_state["range_mode"] = False

toggle_label = "🔄 Switch to Range View" if not st.session_state["range_mode"] else "🔄 Switch to Single Date View"
if st.button(toggle_label, key="toggle_button"):
    st.session_state["range_mode"] = not st.session_state["range_mode"]

# Get data
assigned_df = st.session_state.get("assigned", pd.DataFrame())
unassigned_df = st.session_state.get("unassigned", pd.DataFrame())

# Ensure date columns always exist
if not assigned_df.empty and "check_in" in assigned_df.columns:
    assigned_df["check_in_dt"] = pd.to_datetime(assigned_df["check_in"], format="%d/%m/%Y", errors="coerce")
    assigned_df["check_out_dt"] = pd.to_datetime(assigned_df["check_out"], format="%d/%m/%Y", errors="coerce")
else:
    assigned_df["check_in_dt"] = pd.NaT
    assigned_df["check_out_dt"] = pd.NaT

if not unassigned_df.empty and "check_in" in unassigned_df.columns:
    unassigned_df["check_in_dt"] = pd.to_datetime(unassigned_df["check_in"], format="%d/%m/%Y", errors="coerce")
    unassigned_df["check_out_dt"] = pd.to_datetime(unassigned_df["check_out"], format="%d/%m/%Y", errors="coerce")
else:
    unassigned_df["check_in_dt"] = pd.NaT
    unassigned_df["check_out_dt"] = pd.NaT

# Filter by selected date or range
if st.session_state["range_mode"]:
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", format="DD/MM/YYYY", key="start_date")
    with col2:
        end_date = st.date_input("End Date", format="DD/MM/YYYY", key="end_date")

    if start_date > end_date:
        st.warning("⚠️ End date must be after start date.")
    else:
        start_dt = dt.combine(start_date, time.min)
        end_dt = dt.combine(end_date, time.max)

        assigned_filtered = assigned_df[
            (assigned_df["check_in_dt"] < end_dt) & (assigned_df["check_out_dt"] > start_dt)
        ]
        unassigned_filtered = unassigned_df[
            (unassigned_df["check_in_dt"] < end_dt) & (unassigned_df["check_out_dt"] > start_dt)
        ]

        st.subheader(f"✅ Assigned Families from {start_date.strftime('%d/%m/%Y')} to {end_date.strftime('%d/%m/%Y')}")
        if not assigned_filtered.empty:
            st.dataframe(assigned_filtered[["family", "room", "room_type", "check_in", "check_out"]], use_container_width=True)
        else:
            st.info("📭 No assigned families in that range.")

        st.subheader(f"⚠️ Unassigned Families from {start_date.strftime('%d/%m/%Y')} to {end_date.strftime('%d/%m/%Y')}")
        if not unassigned_filtered.empty:
            st.dataframe(unassigned_filtered.drop(columns=["id"], errors="ignore")[["people", "check_in", "check_out", "room_type"]], use_container_width=True)
        else:
            st.info("📭 No unassigned families in that range.")
else:
    selected_date = st.date_input("Select a date", format="DD/MM/YYYY", key="single_date")
    selected_dt = dt.combine(selected_date, time.min)

    assigned_filtered = assigned_df[
        (assigned_df["check_in_dt"] <= selected_dt) & (assigned_df["check_out_dt"] > selected_dt)
    ]
    unassigned_filtered = unassigned_df[
        (unassigned_df["check_in_dt"] <= selected_dt) & (unassigned_df["check_out_dt"] > selected_dt)
    ]

    st.subheader(f"✅ Assigned Families on {selected_date.strftime('%d/%m/%Y')}")
    if not assigned_filtered.empty:
        st.dataframe(assigned_filtered[["family", "room", "room_type", "check_in", "check_out"]], use_container_width=True)
    else:
        st.info("📭 No assigned families on that date.")

    st.subheader(f"⚠️ Unassigned Families on {selected_date.strftime('%d/%m/%Y')}")
    if not unassigned_filtered.empty:
        st.dataframe(unassigned_filtered.drop(columns=["id"], errors="ignore")[["people", "check_in", "check_out", "room_type"]], use_container_width=True)
    else:
        st.info("📭 No unassigned families on that date.")
