import streamlit as st
import pandas as pd
from logic import assign_rooms

st.title("🏕️ Room Assignment System")

# Upload files
fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv")
room_file = st.file_uploader("🏠 Rooms CSV", type="csv")

# Load data into session state
if fam_file:
    st.session_state["families"] = pd.read_csv(fam_file)

if room_file:
    st.session_state["rooms"] = pd.read_csv(room_file)

# Function to run assignment and store in session
def run_assignment():
    try:
        assignments = assign_rooms(
            st.session_state["families"], 
            st.session_state["rooms"]
        )
        st.session_state["assignments"] = assignments
        st.success("✅ Room assignment complete.")
    except Exception as e:
        st.error(f"Assignment error: {e}")

# Initial auto-run after both files uploaded
if "assignments" not in st.session_state and "families" in st.session_state and "rooms" in st.session_state:
    run_assignment()

# Reassignment button
if "families" in st.session_state and "rooms" in st.session_state:
    if st.button("🔁 Recalculate Assignment"):
        run_assignment()

# Show output
if "assignments" in st.session_state:
    st.dataframe(st.session_state["assignments"])
    csv = st.session_state["assignments"].to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download Assignments", csv, "assignments.csv", "text/csv")
