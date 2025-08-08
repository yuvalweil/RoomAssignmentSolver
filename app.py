from __future__ import annotations
import streamlit as st
import pandas as pd
from io import StringIO

st.set_page_config(page_title="Room Assignment — Main", page_icon="🧭", layout="wide")

# Optional helper modules from your repo (fail-safe if missing)
try:
    from ui import upload as ui_upload
except Exception:
    ui_upload = None

try:
    from ui.runner import run_assignment  # orchestrates solver + logs; reads use_soft
except Exception:
    run_assignment = None

FAMILIES_KEY = "families_df"
ROOMS_KEY = "rooms_df"
USE_SOFT_KEY = "use_soft_constraints"

# ------------------ Header & 5-line instructions ------------------
st.title("Main")
st.markdown(
    """
**What this app does:** assigns families to rooms across date ranges using a backtracking solver with hard & soft constraints.

**How to use (5 lines):**
1. Upload `families.csv` and `rooms.csv` (DD/MM/YYYY dates).
2. Choose whether to **apply soft constraints** (serial & preferences).
3. Click **Recalculate** to run the solver.
4. See **Assigned All** for the full schedule; **Assigned per date/range** to filter by day/range.
5. Use **Rest** for Diagnostics, What‑if, Manual Overrides, Logs, and Daily Sheet (if enabled).
"""
)

st.divider()
st.subheader("Upload CSVs")

def put_df(key: str, df: pd.DataFrame | None):
    if df is not None:
        st.session_state[key] = df

def have_data() -> bool:
    return (
        FAMILIES_KEY in st.session_state
        and ROOMS_KEY in st.session_state
        and isinstance(st.session_state[FAMILIES_KEY], pd.DataFrame)
        and isinstance(st.session_state[ROOMS_KEY], pd.DataFrame)
        and not st.session_state[FAMILIES_KEY].empty
        and not st.session_state[ROOMS_KEY].empty
    )

def show_uploaded_badge():
    if have_data():
        st.success("Files loaded. You can recalculate or switch to the other pages ✅", icon="✅")

# ------------------ Preferred path: your upload module ------------------
if ui_upload and hasattr(ui_upload, "render_uploaders"):
    try:
        ui_upload.render_uploaders()  # your own uploader populates session_state
        show_uploaded_badge()
    except Exception:
        st.info("Falling back to built‑in uploaders (ui/upload.py not available or raised).")

# ------------------ Fallback uploaders (safe UTF-8-SIG) ------------------
if not have_data():
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**families.csv**")
        f_file = st.file_uploader("Upload families.csv", type=["csv"], key="families_upl")
        if f_file:
            try:
                text = f_file.read().decode("utf-8-sig")
                df = pd.read_csv(StringIO(text), dtype=str).fillna("")
                put_df(FAMILIES_KEY, df)
                st.dataframe(df.head(20), use_container_width=True)
            except Exception as e:
                st.error(f"Failed to read families.csv: {e}")

    with col2:
        st.markdown("**rooms.csv**")
        r_file = st.file_uploader("Upload rooms.csv", type=["csv"], key="rooms_upl")
        if r_file:
            try:
                text = r_file.read().decode("utf-8-sig")
                df = pd.read_csv(StringIO(text), dtype=str).fillna("")
                put_df(ROOMS_KEY, df)
                st.dataframe(df.head(20), use_container_width=True)
            except Exception as e:
                st.error(f"Failed to read rooms.csv: {e}")

show_uploaded_badge()

# ------------------ Quick Run: Soft toggle + Recalculate ------------------
st.divider()
st.subheader("Quick Recalculate")

# Initialize toggle from session (default True to keep existing behavior)
if USE_SOFT_KEY not in st.session_state:
    st.session_state[USE_SOFT_KEY] = True

use_soft = st.checkbox(
    "Apply soft constraints (serial & preferences)",
    value=st.session_state[USE_SOFT_KEY],
    help="Turn off to assign with hard constraints only. Forced rooms remain hard.",
)
st.session_state[USE_SOFT_KEY] = use_soft  # keep global state in sync

recalc_btn = st.button("🔁 Recalculate", type="primary", disabled=not have_data())

if recalc_btn:
    if not have_data():
        st.warning("Please upload both CSV files first.")
    elif run_assignment is None:
        st.error("`ui.runner.run_assignment` not found — cannot recalculate from here.")
    else:
        with st.spinner("Solving…"):
            try:
                # run_assignment() should read st.session_state["use_soft_constraints"]
                # If your runner expects an explicit arg, uncomment:
                # run_assignment(use_soft=use_soft)
                run_assignment()
                st.success("Recalculation complete ✅")
            except Exception as e:
                st.error(f"Recalculate failed: {e}")

# Optional tiny status after run (non-blocking)
if "assigned_df" in st.session_state or "unassigned_df" in st.session_state:
    a = st.session_state.get("assigned_df")
    u = st.session_state.get("unassigned_df")
    a_n = len(a) if isinstance(a, pd.DataFrame) else 0
    u_n = len(u) if isinstance(u, pd.DataFrame) else 0
    st.caption(f"Current state — Assigned rows: **{a_n}**, Unassigned rows: **{u_n}**")

st.info(
    "Next: check **Assigned All** or **Assigned per date/range** to view results, or open **Rest** for Diagnostics, What‑if, Manual Override, and Logs."
)
