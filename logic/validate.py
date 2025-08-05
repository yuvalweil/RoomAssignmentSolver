# logic/validate.py

from __future__ import annotations

from typing import List, Tuple
import pandas as pd

from .utils import _parse_date, _overlaps

def validate_constraints(assigned_df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Validate hard and soft constraints on the fully assigned DataFrame.

    Returns:
      hard_ok (bool): True if no hard-constraint violations.
      soft_violations (List[str]): Descriptions of any soft-constraint breaches.
    """
    if assigned_df is None or assigned_df.empty:
        return True, []

    df = assigned_df.copy()
    hard_ok = True
    soft_violations: List[str] = []

    # --- Hard constraints: no double-booking per room
    grouped = df.groupby("room")
    for room, group in grouped:
        # check pairwise overlaps
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

    # --- Hard constraint: room_type match (if room_type column present)
    if "room_type" in df.columns:
        mismatches = df[df["room_type"] != df["room_type"]]
        # (unlikely, placeholder for any extra hard checks)

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
