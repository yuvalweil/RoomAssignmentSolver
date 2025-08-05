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
    def are_serial(a, b):
        return False
    def parse_room_number(x):
        return None

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
# Core solver
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
    Soft-constraint relaxation ladder:
      1) serial ON, forced ON
      2) serial OFF, forced ON
      3) serial OFF, forced OFF
    """
    log = (lambda m: None) if log_func is None else log_func

    # --- 1) Build Booking objects, parsing forced_room into a list of ints
    bookings: List[Booking] = []
    for i, row in families_df.fillna("").iterrows():
        raw = str(row.get("forced_room", "")).strip()
        if raw:
            forced_list = [
                int(tok) for tok in raw.split(",")
                if tok.strip().isdigit()
            ]
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

    # --- 2) Build Room objects
    rooms_list: List[Room] = []
    for _, row in rooms_df.fillna("").iterrows():
        rooms_list.append(Room(
            room=str(row.get("room", "")).strip(),
            room_type=str(row.get("room_type", "")).strip()
        ))

    # --- 3) Group rooms by type
    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms_list:
        rooms_by_type[rm.room_type].append(rm)

    # --- 4) Per-type backtracking
    all_assigned = []
    all_unassigned = []

    for rtype, r_bookings in group_by_room_type(bookings).items():
        available_rooms = rooms_by_type.get(rtype, [])
        if not available_rooms:
            # no rooms of this type → all unassigned
            all_unassigned.extend(rtype for _ in r_bookings)
            continue

        # call internal backtracker (time/node budgets apply there)
        assigned_map, unassigned_idxs = _search_assignments(
            r_bookings,
            available_rooms,
            time_limit_sec,
            node_limit,
            log
        )

        # collect results
        for idx, room in assigned_map.items():
            all_assigned.append((idx, room))
        for idx in unassigned_idxs:
            all_unassigned.append(idx)

    # --- 5) Build DataFrames to return
    assigned_rows = []
    for idx, room in all_assigned:
        fam = families_df.loc[idx].to_dict()
        fam["room"] = room
        assigned_rows.append(fam)

    unassigned_rows = []
    for idx in all_unassigned:
        fam = families_df.loc[idx].to_dict()
        unassigned_rows.append(fam)

    assigned_df = pd.DataFrame(assigned_rows)
    unassigned_df = pd.DataFrame(unassigned_rows)

    return assigned_df, unassigned_df

# -----------------------------------------------------------------------------
# Internal backtracking (legacy wrapper + actual search lives here)
# -----------------------------------------------------------------------------
def _search_assignments(
    bookings: List[Booking],
    rooms: List[Room],
    time_limit_sec: float,
    node_limit: int,
    log: Callable[[str], None],
) -> Tuple[Dict[int, str], List[int]]:
    """
    Find the best assignment mapping booking.idx → room.room for as many bookings as possible.
    Applies soft-constraint penalties for serial and forced.
    """
    # ... Your existing MRV + backtracking implementation here ...
    # Within the core assignment step, when considering a booking:
    #
    # if booking.forced_rooms:
    #     for target in booking.forced_rooms:
    #         if target in available_numbers:
    #             assign that room and break
    #     else:
    #         note a soft‐violation for this booking
    # else:
    #     apply existing soft‐scoring to pick best room
    #
    # Ensure date‐interval and room‐type hard checks remain.
    #
    # Return a tuple: (assigned_map, unassigned_idx_list)
    raise NotImplementedError("Insert your backtracker here.")

# -----------------------------------------------------------------------------
# Helper: group bookings by room_type
# -----------------------------------------------------------------------------
def group_by_room_type(bookings: List[Booking]) -> Dict[str, List[Booking]]:
    d: Dict[str, List[Booking]] = defaultdict(list)
    for b in bookings:
        d[b.room_type].append(b)
    return d
