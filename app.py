from __future__ import annotations
import streamlit as st
import pandas as pd
from io import StringIO

st.set_page_config(page_title="Room Assignment — Main", page_icon="🧭", layout="wide")

# ---- Try to use your existing upload/init utilities if present ----
try:
    from ui import upload as ui_upload  # optional helper module per your repo
except Exception:
    ui_upload = None

# ------------------ Short Summary & How-To (5 lines) ------------------
st.title("Main")
st.markdown(
    """
**What this app does:** assigns families to rooms across date ranges using a backtracking solver with hard & soft constraints.

**How to use (5 lines):**
1. Upload `families.csv` and `rooms.csv` (DD/MM/YYYY dates).
2. Click **Recalculate** (on other pages) to run the solver; toggle soft constraints as needed.
3. See **Assigned All** for the full schedule; use **Assigned per date/range** to filter by a day/range.
4. Use **Rest** for Diagnostics, What‑if scenarios, Manual Overrides, Logs, and more.
5. Download CSVs/Logs from the relevant sections.
"""
)

st.divider()
st.subheader("Upload CSVs")

# ------------------ Session helpers ------------------
FAMILIES_KEY = "families_df"
ROOMS_KEY = "rooms_df"

def put_df(key: str, df: pd.DataFrame | None):
    if df is not None:
        st.session_state[key] = df

def show_uploaded_badge():
    fam_ok = FAMILIES_KEY in st.session_state and not st.session_state[FAMILIES_KEY].empty
    rm_ok = ROOMS_KEY in st.session_state and not st.session_state[ROOMS_KEY].empty
    if fam_ok and rm_ok:
        st.success("Files loaded. You can switch to the other pages now ✅", icon="✅")

# ------------------ Preferred path: use your upload module ------------------
if ui_upload and hasattr(ui_upload, "render_uploaders"):
    try:
        ui_upload.render_uploaders()  # your module handles reading, typing, and st.session_state
        show_uploaded_badge()
        st.stop()
    except Exception as e:
        st.info("Falling back to built‑in uploaders (ui/upload.py not available or raised).")
        # continue to fallback

# ------------------ Fallback uploaders (safe UTF-8-SIG, no 'nan' strings) ------------------
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

st.info(
    "Tip: After uploading, go to **Assigned All** or **Assigned per date/range** to run and view assignments. "
    "Soft constraints can be toggled from the Recalculate section on those pages."
)
