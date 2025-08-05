# logic/solver.py
from __future__ import annotations
import time
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd

# --- Safe import of are_serial (fallback if not present) ---------------------
try:
    from .utils import are_serial  # your existing helper
except Exception:
    def are_serial(a: str, b: str) -> bool:
        """Fallback: rooms are 'serial' if their numbers differ by 1."""
        def num(x):
            m = re.search(r"(\d+)", str(x))
            return int(m.group(1)) if m else None
        na, nb = num(a), num(b)
        return na is not None and nb is not None and abs(na - nb) == 1

# --- Field helpers for שטח soft constraints ---------------------------------
def is_field_type(room_type: str) -> bool:
    s = (room_type or "").strip().lower()
    return "שטח" in s or "field" in s or "camp" in s or "pitch" in s

def extract_room_number(room: str) -> int | None:
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

# Preference sets
FIELD_ONE_ROOM_PREF    = [8, 12, 17, 1, 18]   # 1 room
FIELD_TWO_ROOMS_PREF   = [16, 18]             # 2 rooms -> 16,18
FIELD_THREE_ROOMS_PREF = [12, 13, 14]         # 3 rooms -> 12,13,14
FIELD_FIVE_ROOMS_PREF  = [1, 2, 3, 4, 5]      # 5 rooms -> 1..5

def field_target_set(group_size: int) -> List[int] | None:
    if group_size == 5:
        return FIELD_FIVE_ROOMS_PREF
    if group_size == 3:
        return FIELD_THREE_ROOMS_PREF
    if group_size == 2:
        return FIELD_TWO_ROOMS_PREF
    if group_size == 1:
        return FIELD_ONE_ROOM_PREF
    return None

# --- Core data classes -------------------------------------------------------
@dataclass
class Booking:
    idx: int
    family: str
    room_type: str
    check_in: str
    check_out: str
    forced_room: str | None

@dataclass
class Room:
    room: str
    room_type: str

# --- Build שטח groups --------------------------------------------------------
def build_field_groups(bookings: List[Booking]) -> Dict[Tuple[str, str, str, str], Dict]:
    """
    Groups only שטח bookings by (family, room_type, check_in, check_out).
    Each group keeps size, target_set (by size), assigned_numbers, and chosen_area.
    """
    groups: Dict[Tuple[str, str, str, str], Dict] = {}
    for b in bookings:
        if not is_field_type(b.room_type):
            continue
        key = (b.family, b.room_type, b.check_in, b.check_out)
        if key not in groups:
            groups[key] = {"size": 0, "target_set": None, "assigned_numbers": set(), "chosen_area": None}
        groups[key]["size"] += 1

    for key, meta in groups.items():
        meta["target_set"] = field_target_set(meta["size"])
    return groups

# --- Candidate scoring (SOFT constraints) ------------------------------------
def score_candidate(
    booking: Booking,
    room: Room,
    family_serial_memory: Dict[str, List[str]],
    groups: Dict[Tuple[str, str, str, str], Dict],
    waive_serial: bool,
    waive_forced: bool,
) -> Tuple[int, Tuple]:
    """
    Lower score is better. We combine:
      - forced_room preference (unless waived)
      - serial adjacency within same family (unless waived)
      - שטח group preferences (target sets + stay in same area, avoid 5↔6 split)
    """
    penalty = 0
    tie: List = []

    # forced_room preference
    if not waive_forced and booking.forced_room:
        if str(room.room).strip() != str(booking.forced_room).strip():
            penalty += 5
        else:
            penalty -= 10  # strong bonus if we match forced

    # serial adjacency
    if not waive_serial:
        last_rooms = family_serial_memory.get(booking.family, [])
        if last_rooms:
            if are_serial(last_rooms[-1], room.room):
                penalty -= 3
            else:
                penalty += 1

    # שטח preferences
    if is_field_type(booking.room_type):
        key = (booking.family, booking.room_type, booking.check_in, booking.check_out)
        meta = groups.get(key)
        num = extract_room_number(room.room)
        area = field_area_id(num)

        if meta and meta["size"] > 1 and meta["assigned_numbers"]:
            assigned_areas = {field_area_id(n) for n in meta["assigned_numbers"] if n is not None}
            chosen = meta.get("chosen_area")
            if chosen is None and len(assigned_areas) == 1:
                chosen = assigned_areas.pop()
                meta["chosen_area"] = chosen
            if chosen is not None and area is not None:
                if area != chosen:
                    penalty += 6   # crossing 5↔6 boundary is undesirable
                else:
                    penalty -= 2   # staying in the same area is slightly good

        if meta and meta["target_set"]:
            if num in meta["target_set"]:
                idx = meta["target_set"].index(num)
                penalty -= (12 - idx)  # earlier preferred numbers get more bonus
            else:
                ts_areas = {field_area_id(n) for n in meta["target_set"] if n is not None}
                if len(ts_areas) == 1 and area is not None:
                    (ts_area,) = tuple(ts_areas)
                    if ts_area == area:
                        penalty -= 1

    tie.extend([str(room.room_type), str(room.room)])
    return (penalty, tuple(tie))

# --- Public API --------------------------------------------------------------
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
    Backtracking solver with MRV + soft scoring.
    - Per-type solving (default) to reduce search space.
    - Time/node budgets per type with best-so-far fallback.
    Relaxation ladder per type: (serial on, forced on) → (serial off, forced on) → (serial off, forced off).
    """
    log = (lambda m: None) if log_func is None else log_func

    fam = families_df.fillna("")
    if "family" not in fam.columns:
        if "full_name" in fam.columns:
            fam["family"] = fam["full_name"]
        elif "שם מלא" in fam.columns:
            fam["family"] = fam["שם מלא"]
        else:
            fam["family"] = ""
    if "forced_room" not in fam.columns:
        fam["forced_room"] = ""

    # Build bookings
    bookings: List[Booking] = []
    for i, r in fam.iterrows():
        bookings.append(
            Booking(
                idx=int(i),
                family=str(r.get("family", "")).strip(),
                room_type=str(r.get("room_type", "")).strip(),
                check_in=str(r.get("check_in", "")).strip(),
                check_out=str(r.get("check_out", "")).strip(),
                forced_room=(str(r.get("forced_room", "")).strip() or None),
            )
        )

    # Rooms catalog
    rooms_list = [
        Room(room=str(r.get("room", "")).strip(), room_type=str(r.get("room_type", "")).strip())
        for _, r in rooms_df.fillna("").iterrows()
    ]
    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms_list:
        rooms_by_type[rm.room_type].append(rm)

    # Group bookings by type
    bookings_by_type: Dict[str, List[Booking]] = defaultdict(list)
    for b in bookings:
        bookings_by_type[b.room_type].append(b)

    # If no per-type solving, run once on all
    if not solve_per_type:
        rt_list = ["<all>"]
        per_type_bookings = {"<all>": bookings}
        per_type_rooms = {"<all>": rooms_list}
    else:
        rt_list = sorted(bookings_by_type.keys())
        per_type_bookings = bookings_by_type
        per_type_rooms = rooms_by_type

    # Distribute budgets across types
    t_per = max(time_limit_sec / max(1, len(rt_list)), 3.0)  # at least 3s per type
    n_per = max(node_limit // max(1, len(rt_list)), 20_000)

    global_assigned: Dict[int, str] = {}
    for rt in rt_list:
        bk = per_type_bookings.get(rt, [])
        rms = per_type_rooms.get(rt, [])

        if not bk:
            continue
        if not rms:
            log(f"[{rt}] No rooms available for this type.")
            continue

        # Build groups for שטח (only these bookings)
        field_groups = build_field_groups([b for b in bk if is_field_type(b.room_type)])

        # Relaxation ladder per type
        best_map: Dict[int, str] = {}
        best_complete = False
        for waive_serial, waive_forced in [(False, False), (True, False), (True, True)]:
            log(f"[{rt}] Start search (waive_serial={waive_serial}, waive_forced={waive_forced}) "
                f"budget={t_per:.1f}s/{n_per} nodes")
            found_map, complete, explored, timed_out = _search_assignments(
                bk, rms, field_groups,
                waive_serial=waive_serial,
                waive_forced=waive_forced,
                time_limit_sec=t_per,
                node_limit=n_per,
                log=log,
            )
            log(f"[{rt}] explored={explored} nodes; timed_out={timed_out}; "
                f"assigned={len(found_map)}/{len(bk)}; complete={complete}")
            if len(found_map) > len(best_map):
                best_map = found_map
                best_complete = complete
            if complete:
                break

        global_assigned.update(best_map)

    # Build outputs
    assigned_rows, unassigned_rows = [], []
    for b in bookings:
        base = {
            "_idx": b.idx,       # legacy
            "id": b.idx,         # extra compatibility
            "family": b.family,
            "room_type": b.room_type,
            "check_in": b.check_in,
            "check_out": b.check_out,
            "forced_room": b.forced_room or "",
        }
        room_assigned = global_assigned.get(b.idx, "")
        if room_assigned:
            row = dict(base)
            row["room"] = room_assigned
            assigned_rows.append(row)
        else:
            row = dict(base)
            row["room"] = ""
            unassigned_rows.append(row)

    return pd.DataFrame(assigned_rows), pd.DataFrame(unassigned_rows)

# -----------------------------------------------------------------------------
# Back-compat wrapper for older code paths (core.py still calls this)
# -----------------------------------------------------------------------------
def assign_per_type(families_arg, rooms_arg, *args, **kwargs):
    """
    Older call-sites pass (families, rooms, maybe_other, log_func) and
    expect THREE return values. We:
      • Coerce inputs to DataFrames (handles lists/dicts too).
      • Detect the last callable among *args/**kwargs as log_func.
      • Return (assigned_df, unassigned_df, meta) where meta is a placeholder.
    """
    families_df = families_arg if isinstance(families_arg, pd.DataFrame) else pd.DataFrame(families_arg)
    rooms_df    = rooms_arg    if isinstance(rooms_arg,    pd.DataFrame) else pd.DataFrame(rooms_arg)

    # Extract a logger if pro
