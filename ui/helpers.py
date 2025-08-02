from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime as dt
import html

# ----------------- Session & CSV helpers -----------------

def ensure_session_keys() -> None:
    """Create all session_state keys used by the app if missing."""
    defaults = [
        ("families",   pd.DataFrame()),
        ("rooms",      pd.DataFrame()),
        ("assigned",   pd.DataFrame()),
        ("unassigned", pd.DataFrame()),
        ("log_lines",  []),
        ("range_mode", False),
    ]
    for k, v in defaults:
        if k not in st.session_state:
            st.session_state[k] = v

def read_csv(file):
    """Read CSV with sane defaults (handle Hebrew headers and avoid 'nan' strings)."""
    try:
        return pd.read_csv(file, encoding="utf-8-sig", keep_default_na=False, na_filter=False)
    except Exception:
        file.seek(0)
        return pd.read_csv(file, keep_default_na=False, na_filter=False)

# ----------------- DataFrame helpers -----------------

def with_dt_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure check_in_dt/check_out_dt exist as datetime columns for filtering."""
    df = df.copy()
    if df.empty:
        df["check_in_dt"]  = pd.to_datetime(pd.Series([], dtype="datetime64[ns]"))
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

def is_empty_opt(val) -> bool:
    if pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in {"", "nan", "none", "null"}

def highlight_forced(row):
    """Styler: highlight rows that have a forced_room value."""
    return ["background-color: #fff9c4"] * len(row) if not is_empty_opt(row.get("forced_room", "")) else [""] * len(row)

def unique_values(df: pd.DataFrame, col: str) -> list[str]:
    """Safely get sorted unique values or empty list if col missing/empty df."""
    if df is None or df.empty or col not in df.columns:
        return []
    return sorted(df[col].astype(str).unique())

# ----------------- Filters UI & apply -----------------

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

# ----------------- (Optional) Daily Operations Sheet helpers -----------------

def _first_col(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def night_progress_str(check_in: str, check_out: str, on_date: dt) -> str:
    try:
        ci = pd.to_datetime(str(check_in), format="%d/%m/%Y", errors="coerce")
        co = pd.to_datetime(str(check_out), format="%d/%m/%Y", errors="coerce")
        d  = pd.to_datetime(on_date.date())
        if pd.isna(ci) or pd.isna(co):
            return ""
        total = int((co - ci).days)
        if total <= 0 or not (ci <= d < co):
            return ""
        k = int((d - ci).days) + 1
        return f"{k}/{total}"
    except Exception:
        return ""

def build_day_sheet_sections(
    assigned_df: pd.DataFrame,
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    on_date: dt,
    include_empty_units: bool = True,
) -> dict[str, list[dict]]:
    if assigned_df is None:
        assigned_df = pd.DataFrame()
    if families_df is None:
        families_df = pd.DataFrame()
    if rooms_df is None:
        rooms_df = pd.DataFrame()

    a = assigned_df.copy()
    a["room_type"] = a.get("room_type", "").astype(str).str.strip()
    a["room"]      = a.get("room", "").astype(str).str.strip()
    a["family"]    = a.get("family", "").astype(str).str.strip()

    f = families_df.copy()
    if "family" not in f.columns:
        alt = _first_col(f, "full_name", "שם מלא")
        f["family"] = f[alt].astype(str).str.strip() if alt else ""

    people_col    = _first_col(f, "people", "אנשים")
    breakfast_col = _first_col(f, "breakfast", "א.בוקר")
    notes_col     = _first_col(f, "notes", "הערות")
    crib_col      = _first_col(f, "crib", "לול")

    merge_keys = ["family", "room_type", "check_in", "check_out"]
    for k in merge_keys:
        if k not in a.columns and k in f.columns:
            a[k] = f[k]
    on_f = f[[c for c in f.columns if c in merge_keys + [people_col, breakfast_col, notes_col, crib_col] and c is not None]].copy()
    merged = pd.merge(a, on_f, on=merge_keys, how="left")

    d = pd.to_datetime(on_date.date())
    merged["ci_dt"] = pd.to_datetime(merged["check_in"],  format="%d/%m/%Y", errors="coerce")
    merged["co_dt"] = pd.to_datetime(merged["check_out"], format="%d/%m/%Y", errors="coerce")
    active = merged[(merged["ci_dt"] <= d) & (merged["co_dt"] > d)].copy()

    def section_for(rt: str) -> str:
        s = (rt or "").lower()
        if any(k in s for k in ["זוג", "double", "couple"]) or "בקת" in s or "cabin" in s:
            return "זוגי+בקתות"
        if "yurt" in s or "יורט" in s:
            return "DYurt"
        if "קבוצ" in s or "group" in s:
            return "מתחם קבוצתי"
        if "סככ" in s or "shelter" in s:
            return "סככות"
        if "שטח" in s or "field" in s or "camp" in s or "pitch" in s:
            return "מתחם שטח"
        if "משפח" in s or "family" in s:
            return "מתחם משפחתי"
        return "אחר"

    room_catalog = rooms_df.copy()
    room_catalog["room_type"] = room_catalog.get("room_type", "").astype(str).str.strip()
    room_catalog["room"]      = room_catalog.get("room", "").astype(str).str.strip()
    room_catalog["__section"] = room_catalog["room_type"].map(section_for)

    active["__section"] = active["room_type"].map(section_for)

    out: dict[str, list[dict]] = {}
    for _, row in active.sort_values(["__section", "room"]).iterrows():
        out.setdefault(row["__section"], []).append({
            "room": row["room"],
            "family": row["family"],
            "people": ("" if not people_col else row.get(people_col, "")),
            "nights": night_progress_str(row["check_in"], row["check_out"], on_date),
            "breakfast": ("✓" if breakfast_col and str(row.get(breakfast_col, "")).strip().lower() in {"1","true","yes","y","✓","v","✔"} else ""),
            "notes": " | ".join(
                s for s in [
                    ("" if not crib_col else ("לול" if str(row.get(crib_col, "")).strip().lower() in {"1","true","yes","y"} else "")),
                    ("" if not notes_col else str(row.get(notes_col, "")).strip()),
                ] if s
            ),
        })

    if include_empty_units and not room_catalog.empty:
        filled_keys = {(sec, r["room"]) for sec, rows in out.items() for r in rows}
        for _, rr in room_catalog.sort_values(["__section", "room"]).iterrows():
            key = (rr["__section"], rr["room"])
            if key not in filled_keys:
                out.setdefault(rr["__section"], []).append(
                    {"room": rr["room"], "family": "", "people": "", "nights": "", "breakfast": "", "notes": ""}
                )

    order = ["זוגי+בקתות", "DYurt", "מתחם קבוצתי", "סככות", "מתחם שטח", "מתחם משפחתי", "אחר"]
    return {sec: out.get(sec, []) for sec in order if sec in out or include_empty_units}

def daily_sheet_html(sections: dict[str, list[dict]], on_date: dt) -> str:
    date_str = on_date.strftime("%d/%m/%Y")
    def esc(x): return html.escape(str(x) if x is not None else "")
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:Arial,Helvetica,sans-serif;margin:16px}",
        "h1{margin:0 0 8px 0;font-size:20px}",
        "h2{margin:20px 0 6px 0;font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px}",
        "table{width:100%;border-collapse:collapse;margin-bottom:10px}",
        "th,td{border:1px solid #ddd;padding:6px;font-size:13px}",
        "th{background:#f7f7f7;text-align:left}",
        "td.center{text-align:center;width:70px}",
        "td.room{width:140px}",
        "</style></head><body>",
        f"<h1>דף תפעול יומי — {esc(date_str)}</h1>",
    ]
    for sec, rows in sections.items():
        parts.append(f"<h2>{esc(sec)}</h2>")
        parts.append("<table>")
        parts.append("<tr><th>יחידה</th><th>משפחה</th><th>אנשים</th><th>לילות</th><th>א.בוקר</th><th>הערות</th></tr>")
        if rows:
            for r in rows:
                parts.append(
                    "<tr>"
                    f"<td class='room'>{esc(r.get('room',''))}</td>"
                    f"<td>{esc(r.get('family',''))}</td>"
                    f"<td class='center'>{esc(r.get('people',''))}</td>"
                    f"<td class='center'>{esc(r.get('nights',''))}</td>"
                    f"<td class='center'>{esc(r.get('breakfast',''))}</td>"
                    f"<td>{esc(r.get('notes',''))}</td>"
                    "</tr>"
                )
        else:
            parts.append("<tr><td colspan='6' style='text-align:center;color:#888'>— אין נתונים —</td></tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)

__all__ = [
    "ensure_session_keys",
    "read_csv",
    "with_dt_cols",
    "highlight_forced",
    "unique_values",
    "family_filters_ui",
    "roomtype_filters_ui",
    "apply_filters",
    "build_day_sheet_sections",
    "daily_sheet_html",
]
