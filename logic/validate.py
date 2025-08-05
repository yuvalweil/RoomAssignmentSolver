# logic/validate.py

from __future__ import annotations

from typing import List, Tuple
import pandas as pd

from .utils import _parse_date, _overlaps

def validate_constraints(assigned_df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Returns:
      hard_ok (bool),
      soft_violations (list[str])
    """
    if assigned_df is None or assigned_df.empty:
        return True, []

    df = assigned_df.copy()
    hard_ok = True
    soft_violations: List[str] = []

    # --- Hard‐constraint checks: no double‐booking per room
    for room, group in df.groupby("room"):
        intervals = [
            (_parse_date(r["check_in"]), _parse_date(r["check_out"]))
            for _, r in group.iterrows()
        ]
        for i in range(len(intervals)):
            for j in range(i + 1, len(intervals)):
                if _overlaps(intervals[i], intervals[j]):
                    hard_ok = False
                    soft_violations.append(
                        f"Double‐booking: room {room} between rows {group.index[i]} and {group.index[j]}"
                    )

    # --- Soft constraints: forced_rooms
    for _, row in df.iterrows():
        raw = str(row.get("forced_room", "")).strip()
        if raw:
            fr_list = [int(tok) for tok in raw.split(",") if tok.strip().isdigit()]
            assigned_num = int(str(row["room"]).strip())
            if assigned_num not in fr_list:
                soft_violations.append(
                    f"{row['family']}: assigned room {assigned_num} not in forced list {fr_list}"
                )

    return hard_ok, soft_violations
