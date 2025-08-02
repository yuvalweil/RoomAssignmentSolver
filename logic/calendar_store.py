from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import datetime as dt

from .utils import _parse_date, _norm_room, _overlaps

# (room_type, room) -> list of (start_dt, end_dt)
room_calendars: Dict[Tuple[str, str], List[Tuple[dt, dt]]] = {}

def is_available(room_type: str, room: str, check_in_str: str, check_out_str: str) -> bool:
    key = (str(room_type).strip(), _norm_room(room))
    check_in = _parse_date(check_in_str)
    check_out = _parse_date(check_out_str)
    if key not in room_calendars:
        room_calendars[key] = []
    for (start, end) in room_calendars[key]:
        if _overlaps(check_in, check_out, start, end):
            return False
    return True

def reserve(room_type: str, room: str, check_in_str: str, check_out_str: str) -> None:
    key = (str(room_type).strip(), _norm_room(room))
    check_in = _parse_date(check_in_str)
    check_out = _parse_date(check_out_str)
    if key not in room_calendars:
        room_calendars[key] = []
    room_calendars[key].append((check_in, check_out))

def rebuild_calendar_from_assignments(assigned_df) -> None:
    """Rebuild internal calendars from an assigned table (for manual edits)."""
    global room_calendars
    room_calendars = {}
    if assigned_df is None or assigned_df.empty:
        return
    for _, row in assigned_df.iterrows():
        reserve(row["room_type"], row["room"], row["check_in"], row["check_out"])
