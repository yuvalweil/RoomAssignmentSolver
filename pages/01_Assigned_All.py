import streamlit as st
import sys
from pathlib import Path

# Make sure we can import local packages when running from /pages
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.helpers import (
    ensure_session_keys,
    unique_values,
    family_filters_ui,
    roomtype_filters_ui,
    apply_filters,
    highlight_forced,
)

st.set_page_config(page_title="Assigned (All)", layout="wide")
st.title("✅ Assigned Families (All)")

ensure_session_keys()

if st.session_state.get("assigned") is None or st.session_state["assigned"].empty:
    st.info("No assigned data yet. Go to Home, upload files, and run the solver.")
else:
    all_families = unique_values(st.session_state["assigned"], "family")
    all_types    = unique_values(st.session_state["assigned"], "room_type")

    fam_sel, fam_q = family_filters_ui(all_families, key_prefix="assigned_all")
    rt_sel,  rt_q  = roomtype_filters_ui(all_types,   key_prefix="assigned_all")

    view = apply_filters(
        st.session_state["assigned"],
        fam_sel, fam_q,
        rt_sel,  rt_q,
    )

    if not view.empty:
        st.write(view.style.apply(highlight_forced, axis=1))
        st.download_button(
            "📥 Download Assigned (filtered)",
            view.to_csv(index=False).encode("utf-8-sig"),
            file_name="assigned_families_filtered.csv",
            mime="text/csv",
        )
    else:
        st.info("📭 No rows match the current filters.")
