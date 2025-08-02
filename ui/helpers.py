from __future__ import annotations
import pandas as pd
import streamlit as st
from datetime import datetime as dt

from logic import (
    assign_rooms,
    validate_constraints,
    rebuild_calendar_from_assignments,
    explain_soft_constraints,
)

# -------- Session & CSV helpers ---------------------------------------------

def ensure_session_keys():
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

def read_csv(file):
    # UTF-8 with BOM handles Hebrew; keep_default_na/na_filter prevent "nan" strings
    try:
        return pd.read_csv(file, encoding="utf-8-sig", keep_default_na=False, na_filter=False)
    except Exception:
        file.seek(0)
        return pd.read_csv(file, keep_default_na=False, na_filter=False)

def log_collector():
    def _log(msg):
        ts = dt.now().strftime("%Y-%m-%d %H:%M:%S")
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

# -------- Dataframe helpers --------------------------------------------------

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

def is_empty_opt(val):
    if pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in {"", "nan", "none", "null"}

def highlight_forced(row):
    return ["background-color: #fff9c4"] * len(row) if not is_empty_opt(row.get("forced_room", "")) else [""] * len(row)

def unique_values(df: pd.DataFrame, col: str) -> list[str]:
    if df is None or df.empty or col not in df.columns:
        return []
    return sorted(df[col].astype(str).unique())

# -------- Filters UI & apply -------------------------------------------------

def family_filters_ui(names, key_prefix: str):
    c1, c2 = st.columns([2, 1])
    with c1:
        sel = st.multiselect("Filter by family", names, key=f"fam_sel_{key_prefix}")
    with c2:
        q = st.text_input("Search name", key=f"fam_q_{key_prefix}", placeholder="type to search…")
    return sel, q

def roomtype_filters_ui(types, key_prefix: str):
    c1, c2 = st.columns([2, 1])
    with c1:
        sel = st.multiselect("Filter by room type", types, key=f"rt_sel_{key_prefix}")
    with c2:
        q = st.text_input("Search type", key=f"rt_q_{key_prefix}", placeholder="e.g. Family, Cabin")
    return sel, q

def apply_filters(df: pd.DataFrame,
                  fam_sel: list[str], fam_q: str,
                  rt_sel: list[str],  rt_q: str) -> pd.DataFrame:
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

# Re-exports for other modules (optional convenience)
__all__ = [
    "ensure_session_keys",
    "read_csv",
    "run_assignment",
    "with_dt_cols",
    "highlight_forced",
    "unique_values",
    "family_filters_ui",
    "roomtype_filters_ui",
    "apply_filters",
    "rebuild_calendar_from_assignments",
    "validate_constraints",
    "explain_soft_constraints",
]
