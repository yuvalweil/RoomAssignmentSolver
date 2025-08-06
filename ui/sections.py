from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime as dt, time

from .helpers import (
    with_dt_cols,
    highlight_forced,
    unique_values,
    family_filters_ui,
    roomtype_filters_ui,
    apply_filters,
    build_day_sheet_sections,   # printable sheet data (now uses only families+rooms; assignment optional)
    daily_sheet_html,           # printable sheet HTML
)
from .runner import run_assignment
from logic import rebuild_calendar_from_assignments, validate_constraints, explain_soft_constraints


# ---------- Recalculate button ----------------------------------------------
def render_recalc_button():
    if not st.session_state["families"].empty and not st.session_state["rooms"].empty:
        if st.button("🔁 Recalculate Assignment"):
            run_assignment()


# ---------- Assignment Overview (All) ---------------------------------------
def render_assigned_overview():
    st.markdown("## 📋 Full Assignment Overview")
    col1, col2 = st.columns(2)

    with col1:
        if not st.session_state["assigned"].empty:
            st.subheader("✅ Assigned Families (All)")
            all_families = unique_values(st.session_state["assigned"], "family")
            all_types    = unique_values(st.session_state["assigned"], "room_type")

            fam_sel_all, fam_q_all = family_filters_ui(all_families, key_prefix="all")
            rt_sel_all,  rt_q_all  = roomtype_filters_ui(all_types,   key_prefix="all")

            assigned_all_view = apply_filters(
                st.session_state["assigned"],
                fam_sel_all, fam_q_all,
                rt_sel_all,  rt_q_all,
            )

            if not assigned_all_view.empty:
                # select only the desired columns, reorder, and rename "room" -> "room_num"
                overview = assigned_all_view[[
                    "family",
                    "room_type",
                    "room_num",
                    "check_in",
                    "check_out",
                    "forced_room",
                ]].copy()
                overview.rename(columns={"room": "room_num"}, inplace=True)

                st.write(overview.style.apply(highlight_forced, axis=1))
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



# ---------- Date or Range View ----------------------------------------------
def render_date_or_range_view():
    st.markdown("---")
    st.markdown("## 📅 View Assignments for Date or Range")

    if "range_mode" not in st.session_state:
        st.session_state["range_mode"] = False

    toggle_label = "🔄 Switch to Range View" if not st.session_state["range_mode"] else "🔄 Switch to Single Date View"
    if st.button(toggle_label):
        st.session_state["range_mode"] = not st.session_state["range_mode"]

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
            return

        start_dt = dt.combine(start_date, time.min)
        end_dt = dt.combine(end_date, time.max)

        assigned_filtered = assigned_df[
            (assigned_df["check_in_dt"] < end_dt) & (assigned_df["check_out_dt"] > start_dt)
        ]
        unassigned_filtered = unassigned_df[
            (unassigned_df["check_in_dt"] < end_dt) & (unassigned_df["check_out_dt"] > start_dt)
        ]

        range_fams  = unique_values(assigned_filtered, "family")
        range_types = unique_values(assigned_filtered, "room_type")

        fam_sel_r, fam_q_r = family_filters_ui(range_fams,  key_prefix="range")
        rt_sel_r,  rt_q_r  = roomtype_filters_ui(range_types, key_prefix="range")

        assigned_filtered = apply_filters(
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

        date_fams  = unique_values(assigned_filtered, "family")
        date_types = unique_values(assigned_filtered, "room_type")

        fam_sel_d, fam_q_d = family_filters_ui(date_fams,  key_prefix="date")
        rt_sel_d,  rt_q_d  = roomtype_filters_ui(date_types, key_prefix="date")

        assigned_filtered = apply_filters(
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


# ---------- Daily Operations Sheet (Printable, inputs-only) ------------------
def render_daily_operations_sheet():
    """Printable daily sheet using ONLY families.csv + rooms.csv (assignment optional)."""
    st.markdown("---")
    st.markdown("## 🗂️ Daily Operations Sheet (Printable)")

    families_df = st.session_state.get("families", pd.DataFrame())
    rooms_df    = st.session_state.get("rooms", pd.DataFrame())
    if families_df.empty or rooms_df.empty:
        st.info("Upload both families.csv and rooms.csv to generate the sheet.")
        return

    on_date = st.date_input("Select date", format="DD/MM/YYYY")
    include_empty = st.checkbox(
        "Show empty units",
        value=True,
        help="Include rooms/campsites with no booking for visual consistency.",
    )
    on_dt = dt.combine(on_date, time.min)

    # If an assignment exists, it is derived from the two inputs—safe to use.
    assigned_df = st.session_state.get("assigned", pd.DataFrame())

    sections = build_day_sheet_sections(assigned_df, families_df, rooms_df, on_dt, include_empty)

    # Preview with final headers
    preview_cols = ["unit","name","people","nights","extra","breakfast","paid","charge","notes"]
    preview_headers = ["יחידה","שם","אנשים","לילות","תוספת","א.בוקר","שולם","לחיוב","הערות"]

    for sec, rows in sections.items():
        st.subheader(sec)
        if rows:
            df = pd.DataFrame(rows, columns=preview_cols)
            df.columns = preview_headers
            st.dataframe(df, use_container_width=True)
        else:
            st.caption("— אין נתונים —")

    # Download as single HTML
    html_str = daily_sheet_html(sections, on_dt)
    st.download_button(
        "📥 Download printable HTML",
        data=html_str.encode("utf-8"),
        file_name=f"daily_sheet_{on_date.strftime('%Y-%m-%d')}.html",
        mime="text/html",
    )


# ---------- Manual override ---------------------------------------------------
def render_manual_override():
    if st.session_state.get("assigned", pd.DataFrame()).empty:
        return

    st.markdown("---")
    with st.expander("🛠️ Manual assignment override (with validation)", expanded=False):
        assigned_tbl = st.session_state["assigned"].copy()
        families = sorted(assigned_tbl["family"].unique())
        if not families:
            st.info("No assigned families to edit.")
            return

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
            st.session_state["assigned"].loc[
                st.session_state["assigned"].query("family == @sel_family").index[sel_idx], "room"
            ] = str(new_room)

            rebuild_calendar_from_assignments(st.session_state["assigned"])
            hard_ok, soft_violations = validate_constraints(st.session_state["assigned"])

            if not hard_ok:
                st.error("❌ Change rejected: violates HARD constraints (overlap). Reverting.")
                st.session_state["assigned"].loc[
                    st.session_state["assigned"].query("family == @sel_family").index[sel_idx], "room"
                ] = fam_rows.loc[sel_idx, "room"]
            else:
                st.success("✅ Change applied. No hard violations.")
                if soft_violations:
                    st.warning("Some soft constraints are not satisfied:")
                    for s in soft_violations:
                        st.write(f"• {s}")


# ---------- Diagnostics -------------------------------------------------------
def render_diagnostics():
    if st.session_state.get("assigned", pd.DataFrame()).empty:
        return
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


# ---------- What-if -----------------------------------------------------------
def render_what_if():
    if st.session_state["families"].empty or st.session_state["rooms"].empty:
        return

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
            return

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

            from logic import assign_rooms  # local import
            new_assigned, new_unassigned = assign_rooms(fam_test, st.session_state["rooms"], log_func=lambda m: None)
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
                "— non-logging what-if —".encode("utf-8-sig"),
                file_name="whatif.log",
                mime="text/plain",
            )


# ---------- Logs --------------------------------------------------------------
def render_logs():
    if not st.session_state.get("log_lines"):
        return
    st.markdown("---")
    st.markdown("### 🐞 Assignment Log")

    n = st.slider("Show last N lines", min_value=20, max_value=1000, value=200, step=20)
    tail = st.session_state["log_lines"][-n:]
    st.text_area("Log (compact)", value="\n".join(tail), height=200, label_visibility="collapsed")

    log_bytes = "\n".join(st.session_state["log_lines"]).encode("utf-8-sig")
    st.download_button("📥 Download Log", log_bytes, file_name="assignment.log", mime="text/plain")
