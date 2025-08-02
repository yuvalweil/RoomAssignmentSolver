import streamlit as st
import pandas as pd
from logic import assign_rooms

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# Upload files
fam_file = st.file_uploader("👨‍👩‍👧 Upload Families CSV", type="csv")
room_file = st.file_uploader("🏠 Upload Rooms CSV", type="csv")

# Load uploaded files into session state
if fam_file:
    st.session_state["families"] = pd.read_csv(fam_file)

if room_file:
    st.session_state["rooms"] = pd.read_csv(room_file)

# Run assignment and store in session_state
def run_assignment():
    try:
        assigned_df, unassigned_df = assign_rooms(
            st.session_state["families"],
            st.session_state["rooms"]
        )
        st.session_state["assigned"] = assigned_df
        st.session_state["unassigned"] = unassigned_df
        st.success("✅ Room assignment completed successfully.")
    except Exception as e:
        st.error(f"❌ Assignment failed: {e}")

# Initial run if data is available
if "assigned" not in st.session_state and "families" in st.session_state and "rooms" in st.session_state:
    run_assignment()

# Manual reassignment button
if "families" in st.session_state and "rooms" in st.session_state:
    if st.button("🔁 Recalculate Assignment"):
        run_assignment()

# Show assignment results
if "assigned" in st.session_state:
    st.subheader("✅ Assigned Families")
    st.dataframe(st.session_state["assigned"], use_container_width=True)

    csv = st.session_state["assigned"].to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download Assigned Families", csv, "assigned_families.csv", "text/csv")

if "unassigned" in st.session_state and not st.session_state["unassigned"].empty:
    st.warning(f"⚠️ {len(st.session_state['unassigned'])} families could not be assigned to any room.")
    st.subheader("Unassigned Families")
    st.dataframe(st.session_state["unassigned"], use_container_width=True)
