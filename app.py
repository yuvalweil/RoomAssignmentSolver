import streamlit as st
import pandas as pd
from logic import assign_rooms

st.title("🏕️ Room Assignment System")

st.markdown("Upload your **Families** and **Rooms** CSV files:")

fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv")
room_file = st.file_uploader("🏠 Rooms CSV", type="csv")

if fam_file and room_file:
    families = pd.read_csv(fam_file)
    rooms = pd.read_csv(room_file)

    try:
        assignments = assign_rooms(families, rooms)
        st.success("✅ Room assignment complete.")
        st.dataframe(assignments)

        csv = assignments.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Assignments", csv, "assignments.csv", "text/csv")
    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Upload both CSV files to begin.")
