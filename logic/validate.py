from __future__ import annotations
from typing import List, Tuple
import pandas as pd

from .utils import _parse_date, _overlaps, _room_sort_key, are_serial

def validate_constraints(assigned_df: pd.DataFrame):
    """
    Returns:
      hard_ok (bool),
      soft_violations (list[str])
    """
    if assigned_df is None or assigned_df.empty:
        return True, []

    df = assigned_df.copy()
    df["room"] = df["room"].astype(str).str.strip()
    df["room_type"] = df["room_type"].astype(str).str.strip()

    # Hard: no overlaps per (room_type, room)
    hard_ok = True
    for (rt, r), grp in df.groupby(["room_type", "room"]):
        intervals = []
        for _, row in grp.iterrows():
            try:
                start = _parse_date(row["check_in"])
                end = _parse_date(row["check_out"])
            except Exception:
                hard_ok = False
                break
            intervals.append((start, end))
        if not hard_ok:
            break
        intervals.sort()
        for i in range(1, len(intervals)):
            if _overlaps(intervals[i - 1][0], intervals[i - 1][1], intervals[i][0], intervals[i][1]):
                hard_ok = False
                break
        if not hard_ok:
            break

    # Soft: serial order per family/type; forced honored
    soft_violations: List[str] = []
    for family, fam_grp in df.groupby("family"):
        for rt, rt_grp in fam_grp.groupby("room_type"):
            rooms = list(rt_grp["room"])
            if len(rooms) > 1:
                rooms_sorted = sorted(rooms, key=_room_sort_key)
                ok = True
                for i in range(len(rooms_sorted) - 1):
                    if not are_serial(rooms_sorted[i], rooms_sorted[i + 1]):
                        ok = False
                        break
                if not ok:
                    soft_violations.append(f"{family}/{rt}: rooms not in serial order ({', '.join(rooms_sorted)}).")
        for _, row in fam_grp.iterrows():
            fr = str(row.get("forced_room", "")).strip()
            if fr and str(row["room"]).strip() != fr:
                soft_violations.append(f"{family}: forced {fr} not met (got {row['room']}).")

    return hard_ok, soft_violations
