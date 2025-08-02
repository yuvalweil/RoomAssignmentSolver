# --- Daily sheet helpers ------------------------------------------------------
from datetime import datetime as dt
import pandas as pd
import html

def _first_col(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def night_progress_str(check_in: str, check_out: str, on_date: dt) -> str:
    """Return 'k/n' where k is tonight index (1-based) and n is total nights."""
    try:
        ci = pd.to_datetime(str(check_in), format="%d/%m/%Y", errors="coerce")
        co = pd.to_datetime(str(check_out), format="%d/%m/%Y", errors="coerce")
        d  = pd.to_datetime(on_date.date())
        if pd.isna(ci) or pd.isna(co): 
            return ""
        total = int((co - ci).days)
        if total <= 0:
            return ""
        # half-open: [check_in, check_out)
        if not (ci <= d < co):
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
    """
    Returns a dict: {section_title: [rows...]}, each row has:
      room, family, people, nights, breakfast, notes
    """
    if assigned_df is None:
        assigned_df = pd.DataFrame()
    if families_df is None:
        families_df = pd.DataFrame()
    if rooms_df is None:
        rooms_df = pd.DataFrame()

    # Normalize
    a = assigned_df.copy()
    a["room_type"] = a.get("room_type", "").astype(str).str.strip()
    a["room"]      = a.get("room", "").astype(str).str.strip()
    a["family"]    = a.get("family", "").astype(str).str.strip()

    f = families_df.copy()
    # unify family name
    if "family" not in f.columns:
        alt = _first_col(f, "full_name", "שם מלא")
        if alt:
            f["family"] = f[alt].astype(str).str.strip()
        else:
            f["family"] = ""
    # optional fields
    people_col     = _first_col(f, "people", "אנשים")
    breakfast_col  = _first_col(f, "breakfast", "א.בוקר")
    notes_col      = _first_col(f, "notes", "הערות")
    crib_col       = _first_col(f, "crib", "לול")

    # Merge assigned with per-row extras (matching by family, room_type, dates)
    merge_keys = ["family", "room_type", "check_in", "check_out"]
    for k in merge_keys:
        if k not in a.columns and k in f.columns:
            a[k] = f[k]
    on_f = f[[c for c in f.columns if c in merge_keys + [people_col, breakfast_col, notes_col, crib_col] and c is not None]].copy()
    merged = pd.merge(a, on_f, on=merge_keys, how="left")

    # Filter to rows active on the selected date
    d = pd.to_datetime(on_date.date())
    merged["ci_dt"] = pd.to_datetime(merged["check_in"],  format="%d/%m/%Y", errors="coerce")
    merged["co_dt"] = pd.to_datetime(merged["check_out"], format="%d/%m/%Y", errors="coerce")
    active = merged[(merged["ci_dt"] <= d) & (merged["co_dt"] > d)].copy()

    # Map room_type -> section
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

    # Prepare full unit list (for empty rows) from rooms_df
    room_catalog = rooms_df.copy()
    room_catalog["room_type"] = room_catalog.get("room_type", "").astype(str).str.strip()
    room_catalog["room"]      = room_catalog.get("room", "").astype(str).str.strip()
    room_catalog["__section"] = room_catalog["room_type"].map(section_for)

    # Build filled rows
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

    # Add empty units (present in catalog but not in active)
    if include_empty_units and not room_catalog.empty:
        filled_keys = {(sec, r["room"]) for sec, rows in out.items() for r in rows}
        for _, rr in room_catalog.sort_values(["__section", "room"]).iterrows():
            key = (rr["__section"], rr["room"])
            if key not in filled_keys:
                out.setdefault(rr["__section"], []).append({
                    "room": rr["room"], "family": "", "people": "", "nights": "", "breakfast": "", "notes": ""
                })

    # Stable section order similar to your doc
    order = ["זוגי+בקתות", "DYurt", "מתחם קבוצתי", "סככות", "מתחם שטח", "מתחם משפחתי", "אחר"]
    return {sec: out.get(sec, []) for sec in order if sec in out or include_empty_units}
    

def daily_sheet_html(sections: dict[str, list[dict]], on_date: dt) -> str:
    """Return a simple printable HTML string for download/print."""
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
