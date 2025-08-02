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
