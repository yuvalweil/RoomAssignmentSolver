import streamlit as st
import pandas as pd
from datetime import datetime as dt, time
from logic import assign_rooms, validate_constraints, rebuild_calendar_from_assignments

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# --- Helpers -----------------------------------------------------------------
def _read_csv(file):
    # UTF-8 with BOM handles Hebrew headers well; fallback to default if needed
    try:
        return pd.read_csv(file, encoding="utf-8-sig")
    except Exception:
        file.seek(0)
        return pd.read_csv(file)

def _ensure_session_keys():
    for k, v in [
        ("families", pd.DataFrame()),
        ("rooms", pd.DataFrame()),
        ("assigned", pd.DataFrame()),
        ("unassigned", pd.DataFrame()),
        ("log_lines", []),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

_ensure_session_keys()

def log_collector():
    def _log(msg):
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["log_lines"].append(f"[{ts}] {msg}")
    return _log

def run_assignment():
    try:
        st.session_state["log_lines"] = []
        log_func = log_collector()
        assigned_df, unassigned_df = assign_rooms(
            st.session_state["families"],
            st.session_state["rooms"],
            log_func=log_func,
        )
        st.session_state["assigned"] = assigned_df
        st.session_state["unassigned"] = unassigned_df

        # Immediate validation feedback
        hard_ok, soft_violations = validate_constraints(assigned_df)
        if hard_ok:
            st.success("✅ Room assignment completed. No hard constraint violations.")
        else:
            st.error("❌ Assignment finished with HARD constraint violations. Please review.")
        if soft_violations:
            with st.expander("ℹ️ Soft constraint warnings", expanded=False):
                for s in soft_violations:
                    st.write(f"• {s}")
    except Exception as e:
        st.error(f"❌ Assignment error: {e}")

# --- Upload section ----------------------------------------------------------
st.markdown("### 📁 Upload Guest & Room Lists")
upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv", label_visibility="collapsed")
    st.markdown("*👨‍👩‍👧 Families*", help="Upload your families.csv (supports Hebrew headers).")

with upload_col2:
    room_file = st.file_uploader("🏠 Rooms CSV", type="csv", label_visibility="collapsed")
    st.markdown("*🏠 Rooms*", help="Upload your rooms.csv (room numbers may repeat across types).")

if fam_file:
    st.session_state["families"] = _read_csv(fam_file)
if room_file:
    st.session_state["rooms"] = _read_csv(room_file)

# Auto run after both are present
if (
    st.session_state.get("assigned", pd.DataFrame()).empty
    and not st.session_state["families"].empty
    and not st.session_state["rooms"].empty
):
    run_assignment()

# Recalculate button
if not st.session_state["families"].empty and not st.session_state["rooms"].empty:
    if st.button("🔁 Recalculate Assignment"):
        run_assignment()

# --- Styling helper ----------------------------------------------------------
def highlight_forced(row):
    if pd.notna(row.get("forced_room")) and str(row["forced_room"]).strip():
        return ["background-color: #fff9c4"] * len(row)
    return [""] * len(row)

# --- Assignment Overview -----------------------------------------------------
st.markdown("## 📋 Full Assignment Overview")
col1, col2 = st.columns(2)

with col1:
    if not st.session_state["assigned"].empty:
        st.subheader("✅ Assigned Families (All)")
        styled = st.session_state["assigned"].style.apply(highlight_forced, axis=1)
        st.write(styled)
        csv = st.session_state["assigned"].to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Download Assigned", csv, "assigned_families.csv", "text/csv")

with col2:
    if not st.session_state["unassigned"].empty:
        st.subheader("⚠️ Unassigned Families (All)")
        st.dataframe(
            st.session_state["unassigned"].drop(columns=["id"], errors="ignore"),
            use_container_width=True,
        )
        csv_un = st.session_state["unassigned"].to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Download Unassigned", csv_un, "unassigned_families.csv", "text/csv")

# --- Date filtering ----------------------------------------------------------
st.markdown("---")
st.markdown("## 📅 View Assignments for Date or Range")

if "range_mode" not in st.session_state:
    st.session_state["range_mode"] = False

toggle_label = "🔄 Switch to Range View" if not st.session_state["range_mode"] else "🔄 Switch to Single Date View"
if st.button(toggle_label):
    st.session_state["range_mode"] = not st.session_state["range_mode"]

assigned_df = st.session_state.get("assigned", pd.DataFrame()).copy()
unassigned_df = st.session_state.get("unassigned", pd.DataFrame()).copy()

# Add datetime columns
for df in [assigned_df, unassigned_df]:
    if not df.empty and "check_in" in df.columns:
        df["check_in_dt"] = pd.to_datetime(df["check_in"], format="%d/%m/%Y", errors="coerce")
        df["check_out_dt"] = pd.to_datetime(df["check_out"], format="%d/%m/%Y", errors="coerce")

if st.session_state["range_mode"]:
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", format="DD/MM/YYYY")
    with col2:
        end_date = st.date_input("End Date", format="DD/MM/YYYY")

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
            st.write(
                assigned_filtered[["family", "room", "room_type", "check_in", "check_out", "forced_room"]]
                .style.apply(highlight_forced, axis=1)
            )
        else:
            st.info("📭 No assigned families in that range.")

        st.subheader(f"⚠️ Unassigned Families from {start_date.strftime('%d/%m/%Y')} to {end_date.strftime('%d/%m/%Y')}")
        if not unassigned_filtered.empty:
            st.dataframe(
                unassigned_filtered.drop(columns=["id"], errors="ignore")[
                    ["people", "check_in", "check_out", "room_type", "forced_room"]
                ],
                use_container_width=True,
            )
        else:
            st.info("📭 No unassigned families in that range.")
else:
    selected_date = st.date_input("Select a date", format="DD/MM/YYYY")
    selected_dt = dt.combine(selected_date, time.min)

    assigned_filtered = assigned_df[
        (assigned_df["check_in_dt"] <= selected_dt) & (assigned_df["check_out_dt"] > selected_dt)
    ]
    unassigned_filtered = unassigned_df[
        (unassigned_df["check_in_dt"] <= selected_dt) & (unassigned_df["check_out_dt"] > selected_dt)
    ]

    st.subheader(f"✅ Assigned Families on {selected_date.strftime('%d/%m/%Y')}")
    if not assigned_filtered.empty:
        st.write(
            assigned_filtered[["family", "room", "room_type", "check_in", "check_out", "forced_room"]]
            .style.apply(highlight_forced, axis=1)
        )
    else:
        st.info("📭 No assigned families on that date.")

    st.subheader(f"⚠️ Unassigned Families on {selected_date.strftime('%d/%m/%Y')}")
    if not unassigned_filtered.empty:
        st.dataframe(
            unassigned_filtered.drop(columns=["id"], errors="ignore")[
                ["people", "check_in", "check_out", "room_type", "forced_room"]
            ],
            use_container_width=True,
        )
    else:
        st.info("📭 No unassigned families on that date.")

# --- Manual overrides + revalidation ----------------------------------------
if not st.session_state["assigned"].empty:
    st.markdown("---")
    with st.expander("🛠️ Manual assignment override (with validation)", expanded=False):
        assigned = st.session_state["assigned"].copy()
        families = sorted(assigned["family"].unique())
        sel_family = st.selectbox("Family", families)

        fam_rows = assigned[assigned["family"] == sel_family].reset_index(drop=True)
        # make a concise label for selection
        row_labels = [
            f"{i}: {r['room_type']} | {r['check_in']}→{r['check_out']} | current room: {r['room']}"
            for i, r in fam_rows.iterrows()
        ]
        sel_idx = st.selectbox("Select row to edit", list(range(len(fam_rows))), format_func=lambda i: row_labels[i])

        sel_rt = fam_rows.loc[sel_idx, "room_type"]
        # candidate rooms by type from the uploaded rooms list
        candidate_rooms = st.session_state["rooms"]
        candidate_rooms = candidate_rooms[candidate_rooms["room_type"].astype(str).str.strip() == str(sel_rt).strip()]
        candidate_rooms = sorted(candidate_rooms["room"].astype(str).str.strip().unique())

        new_room = st.selectbox("New room", candidate_rooms)
        if st.button("Apply override"):
            # Apply, rebuild calendars, validate
            st.session_state["assigned"].loc[
                st.session_state["assigned"].query("family == @sel_family").index[sel_idx], "room"
            ] = str(new_room)

            # Rebuild calendars from current assignments and validate
            rebuild_calendar_from_assignments(st.session_state["assigned"])
            hard_ok, soft_violations = validate_constraints(st.session_state["assigned"])

            if not hard_ok:
                st.error("❌ Change rejected: violates HARD constraints (overlap). Reverting.")
                # revert
                st.session_state["assigned"].loc[
                    st.session_state["assigned"].query("family == @sel_family").index[sel_idx], "room"
                ] = fam_rows.loc[sel_idx, "room"]
            else:
                st.success("✅ Change applied. No hard violations.")
                if soft_violations:
                    st.warning("Some soft constraints are not satisfied:")
                    for s in soft_violations:
                        st.write(f"• {s}")

# --- Logs: compact view + download ------------------------------------------
if st.session_state.get("log_lines"):
    st.markdown("---")
    st.markdown("### 🐞 Assignment Log")

    n = st.slider("Show last N lines", min_value=20, max_value=1000, value=200, step=20)
    tail = st.session_state["log_lines"][-n:]
    st.text_area("Log (compact)", value="\n".join(tail), height=200, label_visibility="collapsed")

    log_bytes = "\n".join(st.session_state["log_lines"]).encode("utf-8-sig")
    st.download_button("📥 Download Log", log_bytes, file_name="assignment.log", mime="text/plain")
