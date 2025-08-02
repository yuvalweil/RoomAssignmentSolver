from datetime import datetime as dt, time
import pandas as pd
import streamlit as st

from .helpers import (
    with_dt_cols,
    build_day_sheet_sections,
    daily_sheet_html,
)

def render_daily_operations_sheet():
    st.markdown("---")
    st.markdown("## 🗂️ Daily Operations Sheet (Printable)")
    if st.session_state.get("assigned") is None or st.session_state["assigned"].empty:
        st.info("No assignments yet. Upload & run first.")
        return

    # Inputs
    on_date = st.date_input("Select date", format="DD/MM/YYYY")
    include_empty = st.checkbox("Show empty units", value=True, help="Include rooms/campsites with no booking for visual consistency.")
    on_dt = dt.combine(on_date, time.min)

    # Build sections
    assigned_df  = st.session_state["assigned"]
    families_df  = st.session_state.get("families", pd.DataFrame())
    rooms_df     = st.session_state.get("rooms", pd.DataFrame())

    sections = build_day_sheet_sections(assigned_df, families_df, rooms_df, on_dt, include_empty)

    # Preview tables in the app (lightweight)
    for sec, rows in sections.items():
        st.subheader(sec)
        if rows:
            df = pd.DataFrame(rows, columns=["room","family","people","nights","breakfast","notes"])
            st.dataframe(df, use_container_width=True)
        else:
            st.caption("— אין נתונים —")

    # Export as single HTML
    html_str = daily_sheet_html(sections, on_dt)
    html_bytes = html_str.encode("utf-8")
    st.download_button(
        "📥 Download printable HTML",
        data=html_bytes,
        file_name=f"daily_sheet_{on_date.strftime('%Y-%m-%d')}.html",
        mime="text/html",
    )
