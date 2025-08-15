from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime as dt
import html
import re
from urllib.request import urlopen
from logic.utils import _room_sort_key  # you already have this

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
            
def sort_by_room_natural(df: pd.DataFrame, room_col: str = "room") -> pd.DataFrame:
    """Return df sorted by room using natural (human) order."""
    if df is None or df.empty or room_col not in df.columns:
        return df
    # map each room value -> a sortable key via _room_sort_key
    return df.sort_values(by=room_col, key=lambda s: s.astype(str).map(_room_sort_key))

def _peek_start(src, size: int = 1024) -> bytes:
    """Return up to ``size`` bytes from the start of ``src`` without consuming it."""
    try:
        if hasattr(src, "read") and hasattr(src, "seek") and hasattr(src, "tell"):
            pos = src.tell()
            data = src.read(size)
            src.seek(pos)
            return data
        if isinstance(src, str):
            if src.startswith(("http://", "https://")):
                with urlopen(src) as resp:
                    return resp.read(size)
            with open(src, "rb") as fh:
                return fh.read(size)
    except Exception:
        pass
    return b""


def read_csv(src):
    """Read CSV from an uploaded file or a URL.

    Uses UTF‑8‑SIG decoding and avoids converting empty cells to ``"nan"``.
    ``src`` may be a file-like object (e.g. ``BytesIO``) or a string/URL.
    Automatically detects common delimiters, checks for HTML responses, and
    provides user-friendly errors.
    """
    start = _peek_start(src)
    if b"<html" in start.lower():
        raise ValueError("The provided source returned HTML, not CSV. Check the URL or file.")
    try:
        return pd.read_csv(
            src,
            encoding="utf-8-sig",
            keep_default_na=False,
            na_filter=False,
            sep=None,
            engine="python",
        )
    except pd.errors.ParserError as exc:
        raise ValueError(
            "Could not parse CSV. The file may be invalid or use an unexpected delimiter."
        ) from exc
    except Exception:
        # If this is a file-like object, reset the pointer and try again with
        # default encoding (some browsers omit the BOM).
        if hasattr(src, "seek"):
            src.seek(0)
        try:
            return pd.read_csv(
                src,
                keep_default_na=False,
                na_filter=False,
                sep=None,
                engine="python",
            )
        except pd.errors.ParserError as exc:
            raise ValueError(
                "Could not parse CSV. The file may be invalid or use an unexpected delimiter."
            ) from exc

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

def apply_natural_room_order(df: pd.DataFrame, room_col: str = "room") -> pd.DataFrame:
    """
    Make the room column an *ordered categorical* using natural order.
    Streamlit then sorts by this human order when you click the column.
    Works for pure numbers (4,5,10) and mixed labels (WC01, WC02, WC10).
    """
    if df is None or df.empty or room_col not in df.columns:
        return df
    out = df.copy()
    cats = sorted(out[room_col].astype(str).unique(), key=_room_sort_key)
    out[room_col] = pd.Categorical(out[room_col].astype(str), categories=cats, ordered=True)
    return out
    
def highlight_forced(row):
    """
    Row-level highlight:
      - green when forced_room is set and equals assigned room
      - red   when forced_room is set but not met (or unassigned)
      - no color when forced_room is empty
    Works with either 'room' or 'room_num' in the DataFrame.
    """
    fr = str(row.get("forced_room", "")).strip()
    if not fr:
        return [""] * len(row)

    def norm(val):
        s = str(val).strip()
        if s == "":
            return ""
        m = re.search(r"(\d+)", s)
        # If there are digits, compare by numeric core; otherwise compare as-is
        return m.group(1) if m else s

    assigned = ""
    # Prefer 'room' if present; fall back to 'room_num' (used in overview display)
    if "room" in row.index:
        assigned = str(row.get("room", "")).strip()
    if not assigned and "room_num" in row.index:
        assigned = str(row.get("room_num", "")).strip()

    ok = (assigned != "") and (norm(assigned) == norm(fr))

    color = "background-color: #e6ffed" if ok else "background-color: #ffe6e6"
    return [color] * len(row)

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

# ----------------- Daily Operations Sheet helpers -----------------

def _first_col(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def night_progress_str(check_in: str, check_out: str, on_date: dt) -> str:
    """Return 'k/n' where k is tonight index (1-based) and n is total nights. Half-open [ci,co)."""
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

def _truthy_to_check(val) -> str:
    """Maps any truthy-ish value to '✓', else ''."""
    s = str(val).strip().lower()
    if s in {"1", "true", "yes", "y", "✓", "v", "✔"}:
        return "✓"
    try:
        return "✓" if float(s) > 0 else ""
    except Exception:
        return ""

def build_day_sheet_sections(
    assigned_df: pd.DataFrame | None,
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    on_date: dt,
    include_empty_units: bool = True,
) -> dict[str, list[dict]]:
    """
    Returns a dict: {section_title: [rows...]}, each row has:
      unit, name, people, nights, extra, breakfast, paid, charge, notes

    Data sources:
      • EVERY value comes from families.csv & rooms.csv only.
      • 'unit' is taken from *assigned_df* if available; otherwise uses families.forced_room if present.
      • 'nights' is derived from families.check_in/check_out.
    """
    if families_df is None:
        families_df = pd.DataFrame()
    if rooms_df is None:
        rooms_df = pd.DataFrame()

    # Start with families: one row per booking
    f = families_df.copy()

    # Normalize family name
    if "family" not in f.columns:
        alt = _first_col(f, "full_name", "שם מלא")
        f["family"] = f[alt].astype(str).str.strip() if alt else ""

    # Normalize key fields
    for c in ["room_type", "check_in", "check_out"]:
        if c not in f.columns:
            f[c] = ""

    f["room_type"] = f["room_type"].astype(str).str.strip()
    f["family"]    = f["family"].astype(str).str.strip()

    # Optional columns mapping (Hebrew/English)
    people_col    = _first_col(f, "people", "אנשים")
    extras_col    = _first_col(f, "extras", "extra", "תוספת")
    breakfast_col = _first_col(f, "breakfast", "א.בוקר")
    paid_col      = _first_col(f, "paid", "שולם")
    charge_col    = _first_col(f, "charge", "לחיוב")
    notes_col     = _first_col(f, "notes", "הערות")
    crib_col      = _first_col(f, "crib", "לול")
    forced_col    = _first_col(f, "forced_room", "חדר מוכתב", "חדר_מוכתב")

    # Date filter: rows active on the selected date
    d = pd.to_datetime(on_date.date())
    f["ci_dt"] = pd.to_datetime(f["check_in"],  format="%d/%m/%Y", errors="coerce")
    f["co_dt"] = pd.to_datetime(f["check_out"], format="%d/%m/%Y", errors="coerce")
    active = f[(f["ci_dt"] <= d) & (f["co_dt"] > d)].copy()

    # If we have an assigned_df, use it for unit; else fall back to forced_room
    assigned_units = {}
    if isinstance(assigned_df, pd.DataFrame) and not assigned_df.empty:
        a = assigned_df.copy()
        # keys to map a unique booking row: family + room_type + dates
        for _, r in a.iterrows():
            key = (
                str(r.get("family", "")).strip(),
                str(r.get("room_type", "")).strip(),
                str(r.get("check_in", "")).strip(),
                str(r.get("check_out", "")).strip(),
            )
            assigned_units[key] = str(r.get("room", "")).strip()

    # Section mapping
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

    # Catalog of all units to optionally show empty rows as well
    room_catalog = rooms_df.copy()
    if not room_catalog.empty:
        room_catalog["room_type"] = room_catalog.get("room_type", "").astype(str).str.strip()
        room_catalog["room"]      = room_catalog.get("room", "").astype(str).str.strip()
        room_catalog["__section"] = room_catalog["room_type"].map(section_for)

    # Build rows purely from families + (assigned OR forced_room)
    active["__section"] = active["room_type"].map(section_for)
    out: dict[str, list[dict]] = {}

    for _, row in active.sort_values(["__section", "room_type", "family"]).iterrows():
        key = (
            str(row.get("family", "")).strip(),
            str(row.get("room_type", "")).strip(),
            str(row.get("check_in", "")).strip(),
            str(row.get("check_out", "")).strip(),
        )
        unit = assigned_units.get(key, "")
        if not unit and forced_col:
            unit = str(row.get(forced_col, "")).strip()

        name = row.get("family", "")
        people = "" if not people_col else row.get(people_col, "")
        extra  = "" if not extras_col else row.get(extras_col, "")
        breakfast = "" if not breakfast_col else _truthy_to_check(row.get(breakfast_col, ""))
        paid   = "" if not paid_col else row.get(paid_col, "")
        charge = "" if not charge_col else row.get(charge_col, "")
        notes  = "" if not notes_col else str(row.get(notes_col, "")).strip()

        # (Optional) Add crib into notes. Remove this if you don't want it appended.
        if crib_col and str(row.get(crib_col, "")).strip().lower() in {"1", "true", "yes", "y"}:
            notes = ("לול" if not notes else f"לול | {notes}")

        out.setdefault(row["__section"], []).append({
            "unit": unit,
            "name": name,
            "people": people,
            "nights": night_progress_str(row["check_in"], row["check_out"], on_date),
            "extra": extra,
            "breakfast": breakfast,
            "paid": paid,
            "charge": charge,
            "notes": notes,
        })

    # Add empty units (from rooms.csv) that are not used by any active row
    if include_empty_units and not room_catalog.empty:
        used = {(sec, r["unit"]) for sec, rows in out.items() for r in rows if r.get("unit")}
        for _, rr in room_catalog.sort_values(["__section", "room"]).iterrows():
            key2 = (rr["__section"], rr["room"])
            if key2 not in used:
                out.setdefault(rr["__section"], []).append({
                    "unit": rr["room"], "name": "", "people": "", "nights": "",
                    "extra": "", "breakfast": "", "paid": "", "charge": "", "notes": ""
                })

    order = ["זוגי+בקתות", "DYurt", "מתחם קבוצתי", "סככות", "מתחם שטח", "מתחם משפחתי", "אחר"]
    return {sec: out.get(sec, []) for sec in order if (sec in out) or include_empty_units}

def daily_sheet_html(sections: dict[str, list[dict]], on_date: dt) -> str:
    """Printable HTML with headers: יחידה, שם, אנשים, לילות, תוספת, א.בוקר, שולם, לחיוב, הערות."""
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
        "td.unit{width:160px}",
        "</style></head><body>",
        f"<h1>דף תפעול יומי — {esc(date_str)}</h1>",
    ]
    for sec, rows in sections.items():
        parts.append(f"<h2>{esc(sec)}</h2>")
        parts.append("<table>")
        parts.append("<tr>"
                     "<th>יחידה</th><th>שם</th><th>אנשים</th><th>לילות</th>"
                     "<th>תוספת</th><th>א.בוקר</th><th>שולם</th><th>לחיוב</th><th>הערות</th>"
                     "</tr>")
        if rows:
            for r in rows:
                parts.append(
                    "<tr>"
                    f"<td class='unit'>{esc(r.get('unit',''))}</td>"
                    f"<td>{esc(r.get('name',''))}</td>"
                    f"<td class='center'>{esc(r.get('people',''))}</td>"
                    f"<td class='center'>{esc(r.get('nights',''))}</td>"
                    f"<td class='center'>{esc(r.get('extra',''))}</td>"
                    f"<td class='center'>{esc(r.get('breakfast',''))}</td>"
                    f"<td class='center'>{esc(r.get('paid',''))}</td>"
                    f"<td class='center'>{esc(r.get('charge',''))}</td>"
                    f"<td>{esc(r.get('notes',''))}</td>"
                    "</tr>"
                )
        else:
            parts.append("<tr><td colspan='9' style='text-align:center;color:#888'>— אין נתונים —</td></tr>")
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
