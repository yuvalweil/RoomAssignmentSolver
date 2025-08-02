from __future__ import annotations
import re
from datetime import datetime as dt

DATE_FMT = "%d/%m/%Y"

def _parse_date(s: str) -> dt:
    return dt.strptime(str(s).strip(), DATE_FMT)

def _norm_room(x) -> str:
    return str(x).strip()

def _room_sort_key(r: str):
    s = _norm_room(r)
    m = re.search(r"\d+", s)
    return (int(m.group()) if m else float("inf"), s)

def _overlaps(a_start: dt, a_end: dt, b_start: dt, b_end: dt) -> bool:
    # half-open intervals [start, end)
    return not (a_end <= b_start or a_start >= b_end)

def _clean_opt(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"", "nan", "none", "null"} else s

def are_serial(r1: str, r2: str) -> bool:
    n1 = re.findall(r"\d+", _norm_room(r1))
    n2 = re.findall(r"\d+", _norm_room(r2))
    if n1 and n2:
        return abs(int(n1[0]) - int(n2[0])) == 1
    return False

def is_field_type(room_type: str) -> bool:
    s = (room_type or "").strip().lower()
    return "שטח" in s or "field" in s or "camp" in s or "pitch" in s

def extract_room_number(room: str) -> int | None:
    """Return the integer part of a room label (e.g., 'שטח 12' -> 12)."""
    if room is None:
        return None
    m = re.search(r"(\d+)", str(room))
    return int(m.group(1)) if m else None

def field_area_id(num: int | None) -> int | None:
    """Area 1 = 1..5, Area 2 = 6..18; else None."""
    if num is None:
        return None
    if 1 <= num <= 5:
        return 1
    if 6 <= num <= 18:
        return 2
    return None
