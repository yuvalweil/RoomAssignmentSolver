import streamlit as st
import pandas as pd
from datetime import datetime
from logic import assign_rooms

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# Upload CSV files
fam_file = st.file_uploader("👨‍👩‍👧 Upload Families CSV", type="csv")
room_file = st.file_uploader("🏠 Upload Rooms CSV", type="csv")

# Load uploaded files
if fam_file:
    st.session_state["families"] = pd.read_csv(fam_file)

if room_file:
    st.session_state["rooms"] = pd.read_csv(room_file)

# Run assignment and save results
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
        st.error(f"❌ Error during assignment: {e}")

# Auto-run if both CSVs exist and assignment not done
if "assigned" not in st.session_state and "families" in st.session_state and "rooms" in st.session_state:
    run_assignment()

# Manual rerun
if "families" in st.session_state and "rooms" in st.session_state:
    if st.button("🔁 Recalculate Assignment"):
        run_assignment()

# Show assignment results
if "assigned" in st.session_state:
    st.subheader("✅ Assigned Families")
    st.dataframe(st.session_state["assigned"], use_container_width=True)

    # Download assigned
    csv = st.session_state["assigned"].to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download Assigned Families", csv, "assigned_families.csv", "text/csv")

    # 📅 Filter by date
    st.subheader("📅 View Assignments for Specific Date")
    selected_date = st.date_input("Select a date", format="DD/MM/YYYY")

    # Convert check-in/out to datetime
    df = st.session_state["assigned"].copy()
    df["check_in_dt"] = pd.to_datetime(df["check_in"], format="%d/%m/%Y")
    df["check_out_dt"] = pd.to_datetime(df["check_out"], format="%d/%m/%Y")

    # Filter rows where selected date falls within check-in/check-out
    filtered_df = df[(selected_date >= df["check_in_dt"]) & (selected_date < df["check_out_dt"])]

    if not filtered_df.empty:
        st.success(f"✅ {len(filtered_df)} assignments found on {selected_date.strftime('%d/%m/%Y')}")
        st.dataframe(filtered_df[["family", "room", "check_in", "check_out"]], use_container_width=True)
    else:
        st.warning("📭 No assignments for that date.")

# Show unassigned families
if "unassigned" in st.session_state and not st.session_state["unassigned"].empty:
    st.subheader("⚠️ Unassigned Families")
    st.dataframe(st.session_state["unassigned"], use_container_width=True)
