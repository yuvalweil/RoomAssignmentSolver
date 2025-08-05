# ui/sections.py

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
    build_day_sheet_sections,
    daily_sheet_html,
)
from .runner import run_assignment
from logic.validate import validate_constraints


def render_header():
    st.title("Room Assignment Solver")
    st.markdown("---")


def render_recalc_button():
    """Button to re-run the solver on demand."""
    if not st.session_state["families"].empty and not st.session_state["rooms"].empty:
        if st.button("🔁 Recalculate Assignment"):
            run_assignment()


def render_assigned_overview():
    """Shows the full assigned/unassigned tables with download buttons."""
    st.markdown("## 📋 Full Assignment Overview")
    col1, col2 = st.columns(2)

    # Assigned
    with col1:
        if not st.session_state["assigned"].empty:
            st.subheader("✅ Assigned Families (All)")
            df_assigned = st.session_state["assigned"]
            fam_sel, fam_q = family_filters_ui(unique_values(df_assigned, "family"), key_prefix="all")
            rt_sel, rt_q = roomtype_filters_ui(unique_values(df_assigned, "room_type"), key_prefix="all")

            view = apply_filters(df_assigned, fam_sel, fam_q, rt_sel, rt_q)
            if not view.empty:
                st.write(view.style.apply(highlight_forced, axis=1))
            else:
                st.info("📭 No rows match the current filters.")

            csv = view.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Download Assigned", csv, "assigned_families.csv", "text/csv")

    # Unassigned
    with col2:
        df_un = st.session_state["unassigned"]
        if not df_un.empty:
            st.subheader("⚠️ Unassigned Families (All)")
            st.dataframe(df_un.drop(columns=["id"], errors="ignore"), use_container_width=True)
            csv = df_un.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Download Unassigned", csv, "unassigned_families.csv", "text/csv")


def render_date_or_range_view():
    """Toggle between single-date or date-range views."""
    st.markdown("---")
    st.markdown("## 📅 View Assignments for Date or Range")

    # Toggle state
    if "range_mode" not in st.session_state:
        st.session_state["range_mode"] = False
    label = "🔄 Switch to Range View" if not st.session_state["range_mode"] else "🔄 Switch to Single Date View"
    if st.button(label):
        st.session_state["range_mode"] = not st.session_state["range_mode"]

    df_assigned = with_dt_cols(st.session_state.get("assigned", pd.DataFrame()))
    df_unassigned = with_dt_cols(st.session_state.get("unassigned", pd.DataFrame()))

    if st.session_state["range_mode"]:
        # Date range input
        c1, c2 = st.columns(2)
        with c1:
            start = st.date_input("Start Date", format="DD/MM/YYYY")
        with c2:
            end = st.date_input("End Date", format="DD/MM/YYYY")
        if start > end:
            st.warning("⚠️ End date must be after start date.")
            return

        start_dt = dt.combine(start, time.min)
        end_dt = dt.combine(end, time.max)
        a = df_assigned[(df_assigned.check_in_dt < end_dt) & (df_assigned.check_out_dt > start_dt)]
        u = df_unassigned[(df_unassigned.check_in_dt < end_dt) & (df_unassigned.check_out_dt > start_dt)]

        fam_sel, fam_q = family_filters_ui(unique_values(a, "family"), key_prefix="range")
        rt_sel, rt_q = roomtype_filters_ui(unique_values(a, "room_type"), key_prefix="range")
        a = apply_filters(a, fam_sel, fam_q, rt_sel, rt_q)

        st.subheader(f"✅ Assigned Families from {start:%d/%m/%Y} to {end:%d/%m/%Y}")
        if not a.empty:
            st.write(a.style.apply(highlight_forced, axis=1))
        else:
            st.info("📭 No assigned families in that range.")

        st.subheader(f"⚠️ Unassigned Families from {start:%d/%m/%Y} to {end:%d/%m/%Y}")
        if not u.empty:
            st.dataframe(u.drop(columns=["id"], errors="ignore"), use_container_width=True)
        else:
            st.info("📭 No unassigned families in that range.")
    else:
        # Single date input
        sel = st.date_input("Select a date", format="DD/MM/YYYY")
        sel_dt = dt.combine(sel, time.min)
        a = df_assigned[(df_assigned.check_in_dt <= sel_dt) & (df_assigned.check_out_dt > sel_dt)]
        u = df_unassigned[(df_unassigned.check_in_dt <= sel_dt) & (df_unassigned.check_out_dt > sel_dt)]

        fam_sel, fam_q = family_filters_ui(unique_values(a, "family"), key_prefix="date")
        rt_sel, rt_q = roomtype_filters_ui(unique_values(a, "room_type"), key_prefix="date")
        a = apply_filters(a, fam_sel, fam_q, rt_sel, rt_q)

        st.subheader(f"✅ Assigned Families on {sel:%d/%m/%Y}")
        if not a.empty:
            st.write(a.style.apply(highlight_forced, axis=1))
        else:
            st.info("📭 No assigned families on that date.")

        st.subheader(f"⚠️ Unassigned Families on {sel:%d/%m/%Y}")
        if not u.empty:
            st.dataframe(u.drop(columns=["id"], errors="ignore"), use_container_width=True)
        else:
            st.info("📭 No unassigned families on that date.")


def render_daily_operations_sheet():
    """Printable daily sheet using only the raw input CSVs (assignment optional)."""
    st.markdown("---")
    st.markdown("## 🗂️ Daily Operations Sheet (Printable)")

    fam = st.session_state.get("families", pd.DataFrame())
    rms = st.session_state.get("rooms", pd.DataFrame())
    if fam.empty or rms.empty:
        st.info("Upload both families.csv and rooms.csv to generate the sheet.")
        return

    on_date = st.date_input("Select date", format="DD/MM/YYYY")
    show_empty = st.checkbox("Show empty units", value=True,
                             help="Include units with no booking for layout consistency.")
    on_dt = dt.combine(on_date, time.min)

    sections = build_day_sheet_sections(
        st.session_state.get("assigned", pd.DataFrame()), fam, rms, on_dt, show_empty
    )

    # Preview with Hebrew headers
    cols = ["unit", "name", "people", "nights", "extra", "breakfast", "paid", "charge", "notes"]
    headers = ["יחידה", "שם", "אנשים", "לילות", "תוספת", "א.בוקר", "שולם", "לחיוב", "הערות"]

    for sec, rows in sections.items():
        st.subheader(sec)
        if rows:
            df = pd.DataFrame(rows, columns=cols)
            df.columns = headers
            st.dataframe(df, use_container_width=True)
        else:
            st.caption("— אין נתונים —")

    html = daily_sheet_html(sections, on_dt)
    st.download_button(
        "📥 Download printable HTML",
        data=html.encode("utf-8"),
        file_name=f"daily_sheet_{on_date:%Y-%m-%d}.html",
        mime="text/html",
    )


def render_manual_override():
    """Allow manual editing of a single assignment row, with HARD-constraint validation."""
    if st.session_state.get("assigned", pd.DataFrame()).empty:
        return

    st.markdown("---")
    with st.expander("🛠️ Manual assignment override", expanded=False):
        df = st.session_state["assigned"].copy()
        families = sorted(df["family"].unique())
        if not families:
            st.info("No assigned families to edit.")
            return

        sel = st.selectbox("Family", families)
        fam_rows = df[df.family == sel].reset_index()
        labels = [
            f"{i}: {r.room_type} | {r.check_in}→{r.check_out} | current: {r.room}"
            for i, r in fam_rows.iterrows()
        ]
        idx = st.selectbox("Select row to edit", fam_rows.index.tolist(), format_func=lambda i: labels[i])

        rt = fam_rows.at[idx, "room_type"]
        options = st.session_state["rooms"]
        options = options[options.room_type.astype(str).str.strip() == rt.strip()]
        opts = sorted(options["room"].astype(str).unique())

        new_room = st.selectbox("New room", opts)
        if st.button("Apply override"):
            orig_room = st.session_state["assigned"].at[fam_rows.at[idx, "index"], "room"]
            st.session_state["assigned"].at[fam_rows.at[idx, "index"], "room"] = new_room

            hard_ok, soft = validate_constraints(st.session_state["assigned"])
            if not hard_ok:
                st.error("❌ Violates HARD constraints. Reverting.")
                st.session_state["assigned"].at[fam_rows.at[idx, "index"], "room"] = orig_room
            else:
                st.success("✅ Change applied.")
                if soft:
                    st.warning("Soft-constraint notes:")
                    for note in soft:
                        st.write(f"• {note}")


def render_what_if():
    """Non-destructive what-if analysis by pinning one forced_room and re-running."""
    if st.session_state["families"].empty or st.session_state["rooms"].empty:
        return

    st.markdown("---")
    with st.expander("🧪 What-if: pin a forced room", expanded=False):
        fam_src = st.session_state["families"].copy()
        if "family" not in fam_src:
            if "full_name" in fam_src:
                fam_src["family"] = fam_src["full_name"].astype(str).str.strip()
            elif "שם מלא" in fam_src:
                fam_src["family"] = fam_src["שם מלא"].astype(str).str.strip()

        if fam_src.empty:
            st.info("Upload families.csv to run a what-if.")
            return

        labels = [
            f"{i}: {row.family} | {row.room_type} | {row.check_in}→{row.check_out} | forced={row.get('forced_room','') or '-'}"
            for i, row in fam_src.iterrows()
        ]
        choice = st.selectbox("Pick a row to pin", fam_src.index.tolist(), format_func=lambda i: labels[i])
        sel_row = fam_src.loc[choice]

        rt = sel_row.room_type.strip()
        opts = st.session_state["rooms"]
        opts = opts[opts.room_type.astype(str).str.strip() == rt]
        room_opts = sorted(opts.room.astype(str).unique())

        pin = st.selectbox("Force this room", room_opts)

        if st.button("Run what-if"):
            fam_test = fam_src.copy()
            fam_test["forced_room"] = fam_test.get("forced_room","").astype(str)
            fam_test.at[choice, "forced_room"] = pin

            from logic.solver import assign_rooms
            new_assigned, new_unassigned = assign_rooms(fam_test, st.session_state["rooms"])
            hard_ok, soft = validate_constraints(new_assigned)

            st.write(f"Hard OK: {'✅' if hard_ok else '❌'}")
            if soft:
                st.write("Soft notes:")
                for n in soft:
                    st.write(f"• {n}")

            st.markdown("**Before vs After**")
            before = st.session_state["assigned"]
            st.write("Before:")
            st.dataframe(before[before.family == sel_row.family], use_container_width=True)
            st.write("After:")
            st.dataframe(new_assigned[new_assigned.family == sel_row.family], use_container_width=True)


def render_logs():
    """Show the last N lines of the assignment log."""
    if not st.session_state.get("log_lines"):
        return

    st.markdown("---")
    st.markdown("### 🐞 Assignment Log")
    n = st.slider("Show last N lines", min_value=20, max_value=1000, value=200, step=20)
    tail = st.session_state["log_lines"][-n:]
    st.text_area("Log (compact)", "\n".join(tail), height=200, label_visibility="collapsed")

    log_bytes = "\n".join(tail).encode("utf-8-sig")
    st.download_button("📥 Download Log", log_bytes, "assignment.log", "text/plain")
