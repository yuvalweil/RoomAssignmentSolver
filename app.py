import streamlit as st
import pandas as pd
from logic import assign_rooms
from datetime import datetime

st.set_page_config(page_title="Room Assignment", layout="wide")

# --- Functions ---

def highlight_forced(row):
    if pd.notna(row.get("forced_room", None)):
        return ["background-color: lightcoral"] * len(row)
    return [""] * len(row)

def load_csv(name, key):
    uploaded = st.file_uploader(f"Upload {name} CSV", type=["csv"], key=key)
    if uploaded:
        df = pd.read_csv(uploaded)
        st.session_state[name] = df
        st.success(f"{name} CSV loaded.")
        return df
    return st.session_state.get(name)

def filter_by_date(df, col_checkin, col_checkout, selected, mode):
    if df is None:
        return None
    if mode == "Single Date":
        return df[(df[col_checkin] <= selected) & (df[col_checkout] >= selected)]
    else:
        return df[(df[col_checkout] >= selected[0]) & (df[col_checkin] <= selected[1])]

# --- Load Data ---

if "families" not in st.session_state:
    st.session_state["families"] = None
if "rooms" not in st.session_state:
    st.session_state["rooms"] = None
if "assigned" not in st.session_state:
    st.session_state["assigned"] = None
if "unassigned" not in st.session_state:
    st.session_state["unassigned"] = None

st.title("🏕️ Room Assignment Tool")

col1, col2 = st.columns(2)
with col1:
    families_df = load_csv("families", key="fam_csv")
with col2:
    rooms_df = load_csv("rooms", key="room_csv")

# --- Date Filter ---

st.markdown("### Filter Options")
filter_mode = st.radio("Filter by", ["Single Date", "Date Range"], horizontal=True)
if filter_mode == "Single Date":
    selected_date = st.date_input("Select date", value=datetime.today())
else:
    selected_date = st.date_input("Select date range", value=(datetime.today(), datetime.today()))

# --- Assign Rooms Button ---

if st.button("🔄 Assign Rooms"):
    if families_df is not None and rooms_df is not None:
        filtered_families = filter_by_date(
            families_df, "check_in", "check_out", selected_date, filter_mode
        )
        assigned, unassigned = assign_rooms(filtered_families, rooms_df)
        st.session_state["assigned"] = assigned
        st.session_state["unassigned"] = unassigned
    else:
        st.warning("Please upload both families and rooms CSV files.")

# --- Assigned View ---

st.markdown("### ✅ Assigned Families")
if st.session_state["assigned"] is not None:
    styled_df = st.session_state["assigned"][
        ["family", "room", "room_type", "check_in", "check_out", "forced_room"]
    ].style.apply(highlight_forced, axis=1)
    st.dataframe(styled_df, use_container_width=True)
    st.download_button("Download Assigned CSV", st.session_state["assigned"].to_csv(index=False), "assigned.csv")

# --- Unassigned View ---

st.markdown("### ❌ Unassigned Families")
if st.session_state["unassigned"] is not None:
    st.dataframe(st.session_state["unassigned"][["family", "check_in", "check_out", "forced_room"]], use_container_width=True)
    st.download_button("Download Unassigned CSV", st.session_state["unassigned"].to_csv(index=False), "unassigned.csv")

# --- Delete Family Order ---

st.markdown("### 🗑️ Delete Family Order")
if families_df is not None:
    family_to_delete = st.selectbox("Select a family to delete", sorted(families_df["family"].unique()))
    if st.button("Delete Selected Family"):
        families_df = families_df[families_df["family"] != family_to_delete]
        st.session_state["families"] = families_df
        st.success(f"Deleted family: {family_to_delete}")
