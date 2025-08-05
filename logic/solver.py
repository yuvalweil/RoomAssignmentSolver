# logic/solver.py

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd

# -----------------------------------------------------------------------------
# Compatibility shim: are_serial and date/utils
# -----------------------------------------------------------------------------
try:
    from .utils import are_serial, parse_room_number, _parse_date, _overlaps
except ImportError:
    def are_serial(a, b): return False
    def parse_room_number(x): return None
    def _parse_date(x): raise NotImplementedError
    def _overlaps(a, b): raise NotImplementedError

# -----------------------------------------------------------------------------
# שׂטח-specific soft-constraint parameters
# -----------------------------------------------------------------------------
PROHIBITED_SINGLE_ROOMS = {2, 3, 4, 5, 15}
SHTACH_CLUSTERS = [
    {9, 10, 11},
    {10, 11},    # nested cluster rule
    {13, 14},
    {16, 18},
]
LAST_PRIORITY_ROOM = 15

def penalty_for_shtach(booking_group: List[Booking], assigned_rooms: List[int]) -> int:
    penalty = 0

    # 1) Single-family prohibition
    if len(booking_group) == 1:
        room = assigned_rooms[0]
        if room in PROHIBITED_SINGLE_ROOMS:
            penalty += 50
        if room == LAST_PRIORITY_ROOM:
            penalty += 100

    # 2) Don’t split across any defined clusters
    for cluster in SHTACH_CLUSTERS:
        inside = [r for r in assigned_rooms if r in cluster]
        if 0 < len(inside) < len(assigned_rooms):
            penalty += 30

    # 3) Last-priority for room 15 (all families)
    for r in assigned_rooms:
        if r == LAST_PRIORITY_ROOM:
            penalty += 20

    return penalty

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
    forced_rooms: List[int]

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
    Backtracking solver with MRV + soft scoring, per-room_type.
    """
    log = log_func or (lambda m: None)

    # --- 1) Build Booking list, parsing forced_room → List[int]
    bookings: List[Booking] = []
    for i, row in families_df.fillna("").iterrows():
        raw = str(row.get("forced_room", "")).strip()
        forced = [int(tok) for tok in raw.split(",") if tok.strip().isdigit()] if raw else []
        bookings.append(Booking(
            idx=int(i),
            family=str(row.get("family", "")).strip(),
            room_type=str(row.get("room_type", "")).strip(),
            check_in=str(row.get("check_in", "")).strip(),
            check_out=str(row.get("check_out", "")).strip(),
            forced_rooms=forced,
        ))

    # --- 2) Build Room list
    rooms_list: List[Room] = []
    for _, row in rooms_df.fillna("").iterrows():
        rooms_list.append(Room(
            room=str(row.get("room", "")).strip(),
            room_type=str(row.get("room_type", "")).strip(),
        ))

    # --- 3) Group rooms by type
    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms_list:
        rooms_by_type[rm.room_type].append(rm)

    # --- 4) Per-type solve
    all_assigned = []    # List[(booking_idx, room_label)]
    all_unassigned = []  # List[booking_idx]

    for rtype, group in _group_by_type(bookings).items():
        available = rooms_by_type.get(rtype, [])
        if not available:
            # no rooms of this type: everyone unassigned
            all_unassigned.extend([b.idx for b in group])
            continue

        assigned_map, unassigned_idxs = _search_assignments(
            group, available, time_limit_sec, node_limit, log
        )
        all_assigned.extend(list(assigned_map.items()))
        all_unassigned.extend(unassigned_idxs)

    # --- 5) Build output DataFrames
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
    Should implement MRV + backtracking:
      - Hard checks: date overlap, room_type match
      - Soft scoring: are_serial, forced_rooms, shtach penalties
    Returns:
      assigned_map: {booking.idx: room_label}
      unassigned_idxs: [booking.idx, ...]
    """
    # Pseudocode sketch for scoring a complete assignment for one family:
    #   score = 0
    #   if booking.forced_rooms:
    #       if assigned not in booking.forced_rooms: score += X
    #   if booking.room_type == "שטח":
    #       score += penalty_for_shtach(family_group, assigned_room_nums)
    #   if len(family_group) > 1:
    #       score += serial_penalty(...)
    #
    # (Omitted: full MRV/backtracking implementation.)
    raise NotImplementedError("Insert backtracking logic here.")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _group_by_type(bookings: List[Booking]) -> Dict[str, List[Booking]]:
    d: Dict[str, List[Booking]] = defaultdict(list)
    for b in bookings:
        d[b.room_type].append(b)
    return d
