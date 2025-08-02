import streamlit as st
import pandas as pd
from datetime import datetime as dt
from logic import assign_rooms

st.set_page_config(layout="wide")

st.title("🏕️ Room Assignment System")

st.markdown("Upload the **families** and **rooms** CSV files:")

col1, col2 = st.columns(2)
with col1:
    families_file = st.file_uploader("📄 Upload Families CSV", type=["csv"])
with col2:
    rooms_file = st.file_uploader("📄 Upload Rooms CSV", type=["csv"])

if families_file and rooms_file:
    families_df = pd.read_csv(families_file)
    rooms_df = pd.read_csv(rooms_file)

    families_df.columns = families_df.columns.str.strip()
    rooms_df.columns = rooms_df.columns.str.strip()

    name_col = "full_name" if "full_name" in families_df.columns else "שם מלא"
    if "forced_room" not in families_df.columns:
        families_df["forced_room"] = None

    families_df["check_in_dt"] = pd.to_datetime(families_df["check_in"], format="%d/%m/%Y")
    families_df["check_out_dt"] = pd.to_datetime(families_df["check_out"], format="%d/%m/%Y")

    if "assignments" not in st.session_state:
        st.session_state["assignments"], st.session_state["unassigned"] = assign_rooms(families_df, rooms_df)

    st.button("🔄 Recalculate Assignments", on_click=lambda: st.session_state.update({
        "assignments": assign_rooms(families_df, rooms_df)[0],
        "unassigned": assign_rooms(families_df, rooms_df)[1]
    }))

    st.markdown("## 📋 Assigned Families")
    st.dataframe(st.session_state["assignments"][["family", "room", "room_type", "check_in", "check_out", "forced_room"]])

    st.markdown("## ❌ Unassigned Families")
    unassigned = st.session_state["unassigned"]
    unassigned_display = unassigned[[name_col, "room_type", "check_in", "check_out", "forced_room"]] if not unassigned.empty else pd.DataFrame()
    st.dataframe(unassigned_display)

    st.markdown("---")
    st.markdown("## 📅 View Assignments/Unassigned for Specific Date or Range")

    toggle_range = st.toggle("🔁 Switch to Date Range View")

    if toggle_range:
        col1, col2 = st.columns(2)
        with col1:
            start_dt = st.date_input("Start Date")
        with col2:
            end_dt = st.date_input("End Date")

        if start_dt and end_dt:
            df = st.session_state["assignments"]
            df["check_in_dt"] = pd.to_datetime(df["check_in"], format="%d/%m/%Y")
            df["check_out_dt"] = pd.to_datetime(df["check_out"], format="%d/%m/%Y")
            filtered_df = df[(df["check_in_dt"] < end_dt) & (df["check_out_dt"] > start_dt)]
            st.markdown("### ✅ Assigned in Date Range")
            st.dataframe(filtered_df[["family", "room", "room_type", "check_in", "check_out", "forced_room"]])

            uf = st.session_state["unassigned"]
            uf["check_in_dt"] = pd.to_datetime(uf["check_in"], format="%d/%m/%Y")
            uf["check_out_dt"] = pd.to_datetime(uf["check_out"], format="%d/%m/%Y")
            unassigned_filtered = uf[(uf["check_in_dt"] < end_dt) & (uf["check_out_dt"] > start_dt)]
            if not unassigned_filtered.empty:
                st.markdown("### ❌ Unassigned in Date Range")
                st.dataframe(unassigned_filtered[[name_col, "room_type", "check_in", "check_out", "forced_room"]])

    else:
        selected_dt = st.date_input("📆 Select Date")
        if selected_dt:
            df = st.session_state["assignments"]
            df["check_in_dt"] = pd.to_datetime(df["check_in"], format="%d/%m/%Y")
            df["check_out_dt"] = pd.to_datetime(df["check_out"], format="%d/%m/%Y")
            filtered_df = df[(selected_dt >= df["check_in_dt"]) & (selected_dt < df["check_out_dt"])]
            st.markdown("### ✅ Assigned on Selected Date")
            st.dataframe(filtered_df[["family", "room", "room_type", "check_in", "check_out", "forced_room"]])

            uf = st.session_state["unassigned"]
            uf["check_in_dt"] = pd.to_datetime(uf["check_in"], format="%d/%m/%Y")
            uf["check_out_dt"] = pd.to_datetime(uf["check_out"], format="%d/%m/%Y")
            unassigned_filtered = uf[(selected_dt >= uf["check_in_dt"]) & (selected_dt < uf["check_out_dt"])]
            if not unassigned_filtered.empty:
                st.markdown("### ❌ Unassigned on Selected Date")
                st.dataframe(unassigned_filtered[[name_col, "room_type", "check_in", "check_out", "forced_room"]])
