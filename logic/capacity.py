from __future__ import annotations
from typing import List, Tuple
from datetime import datetime as dt
from .utils import _parse_date, _overlaps

def max_overlap(rows: List[dict]) -> int:
    """Lower bound on rooms needed: max concurrent intervals."""
    events: List[Tuple[dt, int]] = []
    for r in rows:
        events.append((_parse_date(r["check_in"]), 1))
        events.append((_parse_date(r["check_out"]), -1))
    events.sort()
    cur = best = 0
    for _, d in events:
        cur += d
        best = max(best, cur)
    return best

def no_conflict_with_schedule(room_sched: List[Tuple[dt, dt]], start: dt, end: dt) -> bool:
    for s, e in room_sched:
        if _overlaps(s, e, start, end):
            return False
    return True
