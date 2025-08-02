import streamlit as st
import pandas as pd
from datetime import datetime as dt, time

from logic import (
    assign_rooms,
    validate_constraints,
    rebuild_calendar_from_assignments,
    explain_soft_constraints,  # diagnostics panel
)

st.set_page_config(page_title="Room Assignment", layout="wide")
st.title("🏕️ Room Assignment System")

# --- CSV reading -------------------------------------------------------------
def _read_csv(file):
    # UTF-8 with BOM handles Hebrew headers; keep_default_na/na_filter stop blanks becoming "nan"
    try:
        return pd.read_csv(file, encoding="utf-8-sig", keep_default_na=False, na_filter=False)
    except Exception:
        file.seek(0)
        return pd.read_csv(file, keep_default_na=False, na_filter=False)

# --- Session init ------------------------------------------------------------
def _ensure_session_keys():
    for k, v in [
        ("families", pd.DataFrame()),
        ("rooms", pd.DataFrame()),
        ("assigned", pd.DataFrame()),
        ("unassigned", pd.DataFrame()),
        ("log_lines", []),
        ("range_mode", False),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

_ensure_session_keys()

# --- Logging collector --------------------------------------------------------
def log_collector():
    def _log(msg):
        ts = dt.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["log_lines"].append(f"[{ts}] {msg}")
    return _log

# --- Run assignment -----------------------------------------------------------
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

# --- Date helper columns (for filtering views) -------------------------------
def with_dt_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        df["check_in_dt"] = pd.to_datetime(pd.Series([], dtype="datetime64[ns]"))
        df["check_out_dt"] = pd.to_datetime(pd.Series([], dtype="datetime64[ns]"))
        return df
    if "check_in" in df.columns:
        df["check_in_dt"] = pd.to_datetime(df["check_in"], format="%d/%m/%Y", errors="coerce")
    else:
        df["check_in_dt"] = pd.to_datetime(pd.Series([pd.NaT] * len(df)))
    if "check_out" in df.columns:
        df["check_out_dt"] = pd.to_datetime(df["check_out"], format="%d/%m/%Y", errors="coerce")
    else:
        df["check_out_dt"] = pd.to_datetime(pd.Series([pd.NaT] * len(df)))
    return df

# --- Display helpers ----------------------------------------------------------
def _is_empty_opt(val):
    if pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in {"", "nan", "none", "null"}

def highlight_forced(row):
    return ["background-color: #fff9c4"] * len(row) if not _is_empty_opt(row.get("forced_room", "")) else [""] * len(row)

# --- NEW: safe unique list helper --------------------------------------------
def _unique_values(df: pd.DataFrame, col: str) -> list[str]:
    """Return sorted unique values for a column if it exists, else an empty list."""
    if df is None or df.empty or col not in df.columns:
        return []
    return sorted(df[col].astype(str).unique())

# --- Family + Room-Type filter helpers ---------------------------------------
def _family_filters_ui(names, key_prefix: str):
    c1, c2 = st.columns([2, 1])
    with c1:
        sel = st.multiselect("Filter by family", names, key=f"fam_sel_{key_prefix}")
    with c2:
        q = st.text_input("Search name", key=f"fam_q_{key_prefix}", placeholder="type to search…")
    return sel, q

def _roomtype_filters_ui(types, key_prefix: str):
    c1, c2 = st.columns([2, 1])
    with c1:
        sel = st.multiselect("Filter by room type", types, key=f"rt_sel_{key_prefix}")
    with c2:
        q = st.text_input("Search type", key=f"rt_q_{key_prefix}", placeholder="e.g. Family, Cabin")
    return sel, q

def _apply_filters(df: pd.DataFrame,
                   fam_sel: list[str], fam_q: str,
                   rt_sel: list[str],  rt_q: str) -> pd.DataFrame:
    """Apply family + room_type filters to any dataframe that has those columns."""
    if df is None or df.empty:
        return df

    out = df
    if fam_sel and "family" in out.columns:
        out = out[out["family"].astype(str).isin(fam_sel)]
    if fam_q and fam_q.strip() and "family" in out.columns:
        out = out[out["family"].astype(str).str.contains(fam_q.strip(), case=False, na=False)]

    if rt_sel and "room_type" in out.columns:
        out = out[out["room_type"].astype(str).isin(rt_sel)]
    if rt_q and rt_q.strip() and "room_type" in out.columns:
        out = out[out["room_type"].astype(str).str.contains(rt_q.strip(), case=False, na=False)]

    return out

# =============================== UI ==========================================

# --- Upload section ----------------------------------------------------------
st.markdown("### 📁 Upload Guest & Room Lists")
upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    fam_file = st.file_uploader("👨‍👩‍👧 Families CSV", type="csv", label_visibility="collapsed")
    st.markdown("*👨‍👩‍👧 Families*", help="Upload your families.csv (supports Hebrew headers).")

with upload_col2:
    room_file = st.file_uploader("🏠 Rooms CSV", type="csv", label_visibility="collapsed")
    st.markdown("*🏠 Rooms*", help="Upload your rooms.csv (room numbers may repeat across room types).")

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

# --- Assignment Overview (All) -----------------------------------------------
st.markdown("## 📋 Full Assignment Overview")
col1, col2 = st.columns(2)

with col1:
    if not st.session_state["assigned"].empty:
        st.subheader("✅ Assigned Families (All)")

        # Combined family + room_type filters
        all_families = _unique_values(st.session_state["assigned"], "family")
        all_types    = _unique_values(st.session_state["assigned"], "room_type")

        fam_sel_all, fam_q_all = _family_filters_ui(all_families, key_prefix="all")
        rt_sel_all,  rt_q_all  = _roomtype_filters_ui(all_types,   key_prefix="all")

        assigned_all_view = _apply_filters(
            st.session_state["assigned"],
            fam_sel_all, fam_q_all,
            rt_sel_all,  rt_q_all,
        )

        if not assigned_all_view.empty:
            st.write(assigned_all_view.style.apply(highlight_forced, axis=1))
        else:
            st.info("📭 No rows match the current filters.")

        csv = assigned_all_view.to_csv(index=False).encode("utf-8-sig")
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

toggle_label = "🔄 Switch to Range View" if not st.session_state["range_mode"] else "🔄 Switch to Single Date View"
if st.button(toggle_label):
    st.session_state["range_mode"] = not st.session_state["range_mode"]

# Prepare dataframes with guaranteed datetime columns
assigned_df = with_dt_cols(st.session_state.get("assigned", pd.DataFrame()))
unassigned_df = with_dt_cols(st.session_state.get("unassigned", pd.DataFrame()))

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

        # Family + room_type filters for the range subset (SAFE unique lists)
        range_fams  = _unique_values(assigned_filtered, "family")
        range_types = _unique_values(assigned_filtered, "room_type")

        fam_sel_r, fam_q_r = _family_filters_ui(range_fams,  key_prefix="range")
        rt_sel_r,  rt_q_r  = _roomtype_filters_ui(range_types, key_prefix="range")

        assigned_filtered = _apply_filters(
            assigned_filtered,
            fam_sel_r, fam_q_r,
            rt_sel_r,  rt_q_r,
        )

        st.subheader(f"✅ Assigned Families from {start_date.strftime('%d/%m/%Y')} to {end_date.strftime('%d/%m/%Y')}")
        if not assigned_filtered.empty:
            st.write(
                assigned_filtered[["family", "room", "room_type", "check_in", "check_out", "forced_room"]]
                .style.apply(highlight_forced, axis=1)
            )
        else:
            st.info("📭 No assigned families in that range (after filters).")

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

    # Family + room_type filters for the single-date subset (SAFE unique lists)
    date_fams  = _unique_values(assigned_filtered, "family")
    date_types = _unique_values(assigned_filtered, "room_type")

    fam_sel_d, fam_q_d = _family_filters_ui(date_fams,  key_prefix="date")
    rt_sel_d,  rt_q_d  = _roomtype_filters_ui(date_types, key_prefix="date")

    assigned_filtered = _apply_filters(
        assigned_filtered,
        fam_sel_d, fam_q_d,
        rt_sel_d,  rt_q_d,
    )

    st.subheader(f"✅ Assigned Families on {selected_date.strftime('%d/%m/%Y')}")
    if not assigned_filtered.empty:
        st.write(
            assigned_filtered[["family", "room", "room_type", "check_in", "check_out", "forced_room"]]
            .style.apply(highlight_forced, axis=1)
        )
    else:
        st.info("📭 No assigned families on that date (after filters).")

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
        assigned_tbl = st.session_state["assigned"].copy()
        families = sorted(assigned_tbl["family"].unique())
        sel_family = st.selectbox("Family", families)

        fam_rows = assigned_tbl[assigned_tbl["family"] == sel_family].reset_index(drop=True)
        row_labels = [
            f"{i}: {r['room_type']} | {r['check_in']}→{r['check_out']} | current room: {r['room']}"
            for i, r in fam_rows.iterrows()
        ]
        sel_idx = st.selectbox("Select row to edit", list(range(len(fam_rows))), format_func=lambda i: row_labels[i])

        sel_rt = fam_rows.loc[sel_idx, "room_type"]
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

# --- Soft-constraint diagnostics --------------------------------------------
if not st.session_state["assigned"].empty:
    st.markdown("---")
    with st.expander("🔎 Soft-constraint diagnostics", expanded=False):
        diag = explain_soft_constraints(
            st.session_state["assigned"],
            st.session_state["families"],
            st.session_state["rooms"],
        )
        if diag.empty:
            st.success("All soft constraints were satisfied.")
        else:
            st.dataframe(diag, use_container_width=True)
            st.download_button(
                "📥 Download soft-constraints report",
                diag.to_csv(index=False).encode("utf-8-sig"),
                file_name="soft_constraints_report.csv",
                mime="text/csv",
            )

# --- What-if: enforce a specific forced room (sandbox) ----------------------
if not st.session_state["families"].empty and not st.session_state["rooms"].empty:
    st.markdown("---")
    with st.expander("🧪 What-if: enforce a specific forced room (non-destructive)", expanded=False):
        fam_src = st.session_state["families"].copy()
        if "family" not in fam_src.columns:
            if "full_name" in fam_src.columns:
                fam_src["family"] = fam_src["full_name"].astype(str).str.strip()
            elif "שם מלא" in fam_src.columns:
                fam_src["family"] = fam_src["שם מלא"].astype(str).str.strip()

        if fam_src.empty:
            st.info("Upload families.csv to run a what-if.")
        else:
            labels = []
            for i, r in fam_src.iterrows():
                fam_name = str(r.get("family", "")).strip()
                rt = str(r.get("room_type", "")).strip()
                ci = str(r.get("check_in", "")).strip()
                co = str(r.get("check_out", "")).strip()
                fr = str(r.get("forced_room", "")).strip() if "forced_room" in fam_src.columns else ""
                labels.append(f"{i}: {fam_name} | {rt} | {ci}→{co} | forced={fr or '-'}")

            sel_row_idx = st.selectbox(
                "Pick a source row to pin",
                list(fam_src.index),
                format_func=lambda i: labels[list(fam_src.index).index(i)],
            )
            sel_row = fam_src.loc[sel_row_idx]

            sel_rt = str(sel_row["room_type"]).strip()
            room_options = st.session_state["rooms"]
            room_options = room_options[room_options["room_type"].astype(str).str.strip() == sel_rt]
            room_options = sorted(room_options["room"].astype(str).str.strip().unique())

            chosen_room = st.selectbox("Force this room for the selected row", room_options)

            if st.button("Run what-if"):
                fam_test = fam_src.copy()
                if "forced_room" not in fam_test.columns:
                    fam_test["forced_room"] = ""
                fam_test.loc[sel_row_idx, "forced_room"] = str(chosen_room)

                whatif_logs = []
                def _wlog(msg):
                    ts = dt.now().strftime("%Y-%m-%d %H:%M:%S")
                    whatif_logs.append(f"[{ts}] {msg}")

                new_assigned, new_unassigned = assign_rooms(fam_test, st.session_state["rooms"], log_func=_wlog)
                hard_ok, soft_violations = validate_constraints(new_assigned)

                st.subheader("Result summary")
                st.write(f"Hard OK: {'✅' if hard_ok else '❌'}")
                if soft_violations:
                    st.write("Soft notes:")
                    for s in soft_violations:
                        st.write(f"• {s}")

                if new_unassigned.empty:
                    st.success("All rows assigned under this what-if scenario.")
                else:
                    st.error(f"{len(new_unassigned)} row(s) remained unassigned in this scenario.")

                fam_name = str(sel_row.get("family", "")).strip()
                st.markdown("#### Before vs After (selected family)")
                before = st.session_state["assigned"]
                if not before.empty:
                    st.write("**Before:**")
                    st.dataframe(
                        before[before["family"].astype(str).str.strip() == fam_name],
                        use_container_width=True,
                    )
                st.write("**After (what-if):**")
                st.dataframe(
                    new_assigned[new_assigned["family"].astype(str).str.strip() == fam_name],
                    use_container_width=True,
                )

                st.download_button(
                    "📥 Download what-if assigned CSV",
                    new_assigned.to_csv(index=False).encode("utf-8-sig"),
                    file_name="whatif_assigned.csv",
                    mime="text/csv",
                )
                st.download_button(
                    "📥 Download what-if log",
                    "\n".join(whatif_logs).encode("utf-8-sig"),
                    file_name="whatif.log",
                    mime="text/plain",
                )

# --- Logs: compact view + download ------------------------------------------
if st.session_state.get("log_lines"):
    st.markdown("---")
    st.markdown("### 🐞 Assignment Log")

    n = st.slider("Show last N lines", min_value=20, max_value=1000, value=200, step=20)
    tail = st.session_state["log_lines"][-n:]
    st.text_area("Log (compact)", value="\n".join(tail), height=200, label_visibility="collapsed")

    log_bytes = "\n".join(st.session_state["log_lines"]).encode("utf-8-sig")
    st.download_button("📥 Download Log", log_bytes, file_name="assignment.log", mime="text/plain")
