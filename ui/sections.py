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
    if not st.session_state["families"].empty and not st.session_state["rooms"].empty:
        if st.button("🔁 Recalculate Assignment"):
            run_assignment()


def render_assigned_overview():
    st.markdown("## 📋 Full Assignment Overview")
    col1, col2 = st.columns(2)

    # Assigned
    with col1:
        df = st.session_state["assigned"]
        if not df.empty:
            st.subheader("✅ Assigned Families (All)")
            fam_sel, fam_q = family_filters_ui(unique_values(df, "family"), key_prefix="all")
            rt_sel, rt_q = roomtype_filters_ui(unique_values(df, "room_type"), key_prefix="all")
            view = apply_filters(df, fam_sel, fam_q, rt_sel, rt_q)
            if not view.empty:
                st.write(view.style.apply(highlight_forced, axis=1))
            else:
                st.info("📭 No rows match the current filters.")
            csv = view.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Download Assigned", csv, "assigned_families.csv", "text/csv")

    # Unassigned
    with col2:
        dfu = st.session_state["unassigned"]
        if not dfu.empty:
            st.subheader("⚠️ Unassigned Families (All)")
            st.dataframe(dfu.drop(columns=["id"], errors="ignore"), use_container_width=True)
            csvu = dfu.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Download Unassigned", csvu, "unassigned_families.csv", "text/csv")


def render_date_or_range_view():
    st.markdown("---")
    st.markdown("## 📅 View Assignments for Date or Range")

    if "range_mode" not in st.session_state:
        st.session_state["range_mode"] = False
    label = "🔄 Switch to Range View" if not st.session_state["range_mode"] else "🔄 Switch to Single Date View"
    if st.button(label):
        st.session_state["range_mode"] = not st.session_state["range_mode"]

    a = with_dt_cols(st.session_state.get("assigned", pd.DataFrame()))
    u = with_dt_cols(st.session_state.get("unassigned", pd.DataFrame()))

    if st.session_state["range_mode"]:
        c1, c2 = st.columns(2)
        with c1:
            start = st.date_input("Start Date", format="DD/MM/YYYY")
        with c2:
            end = st.date_input("End Date", format="DD/MM/YYYY")
        if start > end:
            st.warning("⚠️ End date must be after start date.")
            return
        sd, ed = dt.combine(start, time.min), dt.combine(end, time.max)
        af = a[(a.check_in_dt < ed) & (a.check_out_dt > sd)]
        uf = u[(u.check_in_dt < ed) & (u.check_out_dt > sd)]
        fam_sel, fam_q = family_filters_ui(unique_values(af, "family"), key_prefix="range")
        rt_sel, rt_q = roomtype_filters_ui(unique_values(af, "room_type"), key_prefix="range")
        af = apply_filters(af, fam_sel, fam_q, rt_sel, rt_q)
        st.subheader(f"✅ Assigned from {start:%d/%m/%Y} to {end:%d/%m/%Y}")
        st.write(af.style.apply(highlight_forced, axis=1)) if not af.empty else st.info("📭 No assigned in range.")
        st.subheader(f"⚠️ Unassigned from {start:%d/%m/%Y} to {end:%d/%m/%Y}")
        st.dataframe(uf.drop(columns=["id"], errors="ignore"), use_container_width=True) if not uf.empty else st.info("📭 No unassigned in range.")
    else:
        sel = st.date_input("Select a date", format="DD/MM/YYYY")
        sd = dt.combine(sel, time.min)
        af = a[(a.check_in_dt <= sd) & (a.check_out_dt > sd)]
        uf = u[(u.check_in_dt <= sd) & (u.check_out_dt > sd)]
        fam_sel, fam_q = family_filters_ui(unique_values(af, "family"), key_prefix="date")
        rt_sel, rt_q = roomtype_filters_ui(unique_values(af, "room_type"), key_prefix="date")
        af = apply_filters(af,fam_sel,fam_q, rt_sel, rt_q)
        st.subheader(f"✅ Assigned on {sel:%d/%m/%Y}")
        st.write(af.style.apply(highlight_forced, axis=1)) if not af.empty else st.info("📭 No assigned on date.")
        st.subheader(f"⚠️ Unassigned on {sel:%d/%m/%Y}")
        st.dataframe(uf.drop(columns=["id"], errors="ignore"), use_container_width=True) if not uf.empty else st.info("📭 No unassigned on date.")


def render_daily_operations_sheet():
    st.markdown("---")
    st.markdown("## 🗂️ Daily Operations Sheet (Printable)")
    fam = st.session_state.get("families", pd.DataFrame())
    rms = st.session_state.get("rooms", pd.DataFrame())
    if fam.empty or rms.empty:
        st.info("Upload both CSVs to generate the sheet.")
        return
    date = st.date_input("Select date", format="DD/MM/YYYY")
    show_empty = st.checkbox("Show empty units", value=True)
    on_dt = dt.combine(date, time.min)
    secs = build_day_sheet_sections(st.session_state.get("assigned", pd.DataFrame()), fam, rms, on_dt, show_empty)
    cols = ["unit","name","people","nights","extra","breakfast","paid","charge","notes"]
    hdr = ["יחידה","שם","אנשים","לילות","תוספת","א.בוקר","שולם","לחיוב","הערות"]
    for sec, rows in secs.items():
        st.subheader(sec)
        if rows:
            df = pd.DataFrame(rows, columns=cols)
            df.columns = hdr
            st.dataframe(df, use_container_width=True)
        else:
            st.caption("— אין נתונים —")
    html = daily_sheet_html(secs, on_dt)
    st.download_button("📥 Download printable HTML", data=html.encode("utf-8"), file_name=f"daily_{date:%Y-%m-%d}.html", mime="text/html")


def render_manual_override():
    if st.session_state.get("assigned", pd.DataFrame()).empty:
        return
    st.markdown("---")
    with st.expander("🛠️ Manual assignment override", expanded=False):
        df = st.session_state["assigned"].copy()
        fams = sorted(df.family.unique())
        if not fams:
            st.info("No assigned families.")
            return
        sel = st.selectbox("Family", fams)
        sub = df[df.family == sel].reset_index()
        labels = [f"{i}: {r.room_type} | {r.check_in}→{r.check_out} | current {r.room}" for i,r in sub.iterrows()]
        idx = st.selectbox("Row to edit", sub.index.tolist(), format_func=lambda i: labels[i])
        rt = sub.at[idx, "room_type"]
        opts = st.session_state["rooms"]
        opts = opts[opts.room_type.astype(str).str.strip() == rt.strip()]
        rooms = sorted(opts.room.astype(str).unique())
        new = st.selectbox("New room", rooms)
        if st.button("Apply override"):
            orig = st.session_state["assigned"].at[sub.at[idx,"index"], "room"]
            st.session_state["assigned"].at[sub.at[idx,"index"], "room"] = new
            hard_ok, soft = validate_constraints(st.session_state["assigned"])
            if not hard_ok:
                st.error("❌ Violates HARD constraints. Reverting.")
                st.session_state["assigned"].at[sub.at[idx,"index"], "room"] = orig
            else:
                st.success("✅ Change applied.")
                if soft:
                    st.warning("Soft notes:")
                    for n in soft:
                        st.write(f"• {n}")


def render_what_if():
    if st.session_state["families"].empty or st.session_state["rooms"].empty:
        return
    st.markdown("---")
    with st.expander("🧪 What-if: pin a forced room", expanded=False):
        fam = st.session_state["families"].copy()
        if "family" not in fam:
            if "full_name" in fam:
                fam["family"] = fam.full_name.astype(str).str.strip()
            elif "שם מלא" in fam:
                fam["family"] = fam["שם מלא"].astype(str).str.strip()
        if fam.empty:
            st.info("Upload families.csv.")
            return
        labels = [f"{i}: {r.family} | {r.room_type} | {r.check_in}→{r.check_out} | forced={r.get('forced_room','')or'-'}" for i,r in fam.iterrows()]
        choice = st.selectbox("Pick a row", fam.index.tolist(), format_func=lambda i: labels[i])
        row = fam.loc[choice]
        rt = row.room_type.strip()
        opts = st.session_state["rooms"]
        opts = opts[opts.room_type.astype(str).str.strip() == rt]
        rooms = sorted(opts.room.astype(str).unique())
        pin = st.selectbox("Force this room", rooms)
        if st.button("Run what-if"):
            from logic.solver import assign_rooms
            test = fam.copy()
            test["forced_room"] = test.get("forced_room","").astype(str)
            test.at[choice, "forced_room"] = pin
            new_a, new_u = assign_rooms(test, st.session_state["rooms"])
            hard_ok, soft = validate_constraints(new_a)
            st.write(f"Hard OK: {'✅' if hard_ok else '❌'}")
            if soft:
                st.write("Soft notes:")
                for n in soft:
                    st.write(f"• {n}")
            before = st.session_state["assigned"]
            st.markdown("**Before vs After**")
            st.write("Before:")
            st.dataframe(before[before.family==row.family], use_container_width=True)
            st.write("After:")
            st.dataframe(new_a[new_a.family==row.family], use_container_width=True)


def render_logs():
    if not st.session_state.get("log_lines"):
        return
    st.markdown("---")
    st.markdown("### 🐞 Assignment Log")
    n = st.slider("Show last N lines", 20,1000,200,20)
    tail = st.session_state["log_lines"][-n:]
    st.text_area("Log", "\n".join(tail), height=200, label_visibility="collapsed")
    st.download_button("📥 Download Log", "\n".join(tail).encode("utf-8-sig"), "assignment.log", "text/plain")


def render_footer():
    st.markdown("---")
    st.caption("© Your Company 2025")
