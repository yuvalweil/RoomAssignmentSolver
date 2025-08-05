# logic/solver.py

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd

# -----------------------------------------------------------------------------
# Compatibility shim: are_serial falls back to no-op if missing
# -----------------------------------------------------------------------------
try:
    from .utils import are_serial, parse_room_number
except ImportError:
    def are_serial(a, b): return False
    def parse_room_number(x): return None

# -----------------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------------
@dataclass
class Booking:
    idx: int
    family: str
    room_type: str
    check_in: str
    check_out: str
    forced_rooms: List[int]           # parsed from forced_room CSV field

@dataclass
class Room:
    room: str
    room_type: str

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func: Optional[Callable[[str], None]] = None,
    *,
    time_limit_sec: float = 20.0,
    node_limit: int = 150_000,
    solve_per_type: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Backtracking solver with MRV + soft scoring, per-room_type solving.
    """
    log = log_func or (lambda m: None)

    # 1) Build Booking objects, parsing forced_room into a list
    bookings: List[Booking] = []
    for i, row in families_df.fillna("").iterrows():
        raw = str(row.get("forced_room", "")).strip()
        if raw:
            forced_list = [int(tok) for tok in raw.split(",") if tok.strip().isdigit()]
        else:
            forced_list = []

        bookings.append(Booking(
            idx=int(i),
            family=str(row.get("family", "")).strip(),
            room_type=str(row.get("room_type", "")).strip(),
            check_in=str(row.get("check_in", "")).strip(),
            check_out=str(row.get("check_out", "")).strip(),
            forced_rooms=forced_list,
        ))

    # 2) Build Room objects
    rooms_list: List[Room] = []
    for _, row in rooms_df.fillna("").iterrows():
        rooms_list.append(Room(
            room=str(row.get("room", "")).strip(),
            room_type=str(row.get("room_type", "")).strip(),
        ))

    # 3) Group rooms by type
    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms_list:
        rooms_by_type[rm.room_type].append(rm)

    # 4) Per-type backtracking
    all_assigned = []    # List of (booking_idx, room_label)
    all_unassigned = []  # List of booking_idx

    for rtype, group in group_by_room_type(bookings).items():
        available = rooms_by_type.get(rtype, [])
        if not available:
            all_unassigned.extend(b.idx for b in group)
            continue

        assigned_map, unassigned_idxs = _search_assignments(
            group, available, time_limit_sec, node_limit, log
        )
        all_assigned.extend(assigned_map.items())
        all_unassigned.extend(unassigned_idxs)

    # 5) Build DataFrames
    assigned_rows = []
    for idx, room in all_assigned:
        rec = families_df.loc[idx].to_dict()
        rec["room"] = room
        assigned_rows.append(rec)

    unassigned_rows = []
    for idx in all_unassigned:
        rec = families_df.loc[idx].to_dict()
        unassigned_rows.append(rec)

    return pd.DataFrame(assigned_rows), pd.DataFrame(unassigned_rows)

# -----------------------------------------------------------------------------
# Internal backtracking placeholder
# -----------------------------------------------------------------------------
def _search_assignments(
    bookings: List[Booking],
    rooms: List[Room],
    time_limit_sec: float,
    node_limit: int,
    log: Callable[[str], None],
) -> Tuple[Dict[int, str], List[int]]:
    """
    Your MRV + backtracking implementation goes here.

    Should enforce hard constraints (date overlap, room_type match)
    and apply soft scoring (are_serial, forced_rooms, etc.).
    """
    raise NotImplementedError("Insert your backtracker here.")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def group_by_room_type(bookings: List[Booking]) -> Dict[str, List[Booking]]:
    d: Dict[str, List[Booking]] = defaultdict(list)
    for b in bookings:
        d[b.room_type].append(b)
    return d

# Legacy alias for backward compatibility
assign_per_type = assign_rooms
