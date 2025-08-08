# logic/solver.py

from __future__ import annotations

import time
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd

# -----------------------------------------------------------------------------
# Safe import of are_serial (fallback if not present)
# -----------------------------------------------------------------------------
try:
    from .utils import are_serial  # your existing helper
except Exception:
    def are_serial(a: str, b: str) -> bool:
        """Fallback: rooms are 'serial' if their numeric parts differ by 1."""
        def num(x):
            m = re.search(r"(\d+)", str(x))
            return int(m.group(1)) if m else None
        na, nb = num(a), num(b)
        return na is not None and nb is not None and abs(na - nb) == 1

# -----------------------------------------------------------------------------
# שטח helpers and preferences
# -----------------------------------------------------------------------------
def is_field_type(room_type: str) -> bool:
    s = (room_type or "").strip().lower()
    return "שטח" in s or "field" in s or "camp" in s or "pitch" in s

def extract_room_number(room: str) -> Optional[int]:
    if room is None:
        return None
    m = re.search(r"(\d+)", str(room))
    return int(m.group(1)) if m else None

def field_area_id(num: Optional[int]) -> Optional[int]:
    """Area 1 = 1..5, Area 2 = 6..18; else None."""
    if num is None:
        return None
    if 1 <= num <= 5:
        return 1
    if 6 <= num <= 18:
        return 2
    return None

FIELD_ONE_ROOM_PREF    = [8, 12, 17, 1, 18]   # size=1
FIELD_TWO_ROOMS_PREF   = [16, 18]             # size=2
FIELD_THREE_ROOMS_PREF = [12, 13, 14]         # size=3
FIELD_FIVE_ROOMS_PREF  = [1, 2, 3, 4, 5]      # size=5

def field_target_set(group_size: int) -> Optional[List[int]]:
    if group_size == 5:
        return FIELD_FIVE_ROOMS_PREF
    if group_size == 3:
        return FIELD_THREE_ROOMS_PREF
    if group_size == 2:
        return FIELD_TWO_ROOMS_PREF
    if group_size == 1:
        return FIELD_ONE_ROOM_PREF
    return None

# -----------------------------------------------------------------------------
# NEW: clusters and single-room prohibitions for שטח
# -----------------------------------------------------------------------------
PROHIBITED_SINGLE_ROOMS = {2, 3, 4, 5, 15}
FIELD_CLUSTERS = [
    {2, 3},
    {9, 10, 11},
    {10, 11},      # nested rule
    {13, 14},
    {16, 18},
]
LAST_PRIORITY_ROOM = 15

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
    forced_room: Optional[str]

@dataclass
class Room:
    room: str
    room_type: str

# -----------------------------------------------------------------------------
# Build שטח groups (family + type + identical date range)
# -----------------------------------------------------------------------------
def build_field_groups(bookings: List[Booking]) -> Dict[Tuple[str, str, str, str], Dict]:
    groups: Dict[Tuple[str, str, str, str], Dict] = {}
    for b in bookings:
        if not is_field_type(b.room_type):
            continue
        key = (b.family, b.room_type, b.check_in, b.check_out)
        if key not in groups:
            groups[key] = {
                "size": 0,
                "target_set": None,
                "assigned_numbers": set(),
                "chosen_area": None
            }
        groups[key]["size"] += 1

    for key, meta in groups.items():
        meta["target_set"] = field_target_set(meta["size"])
    return groups

# -----------------------------------------------------------------------------
# Candidate scoring (soft constraints)
# -----------------------------------------------------------------------------
def score_candidate(
    booking: Booking,
    room: Room,
    family_serial_memory: Dict[str, List[str]],
    groups: Dict[Tuple[str, str, str, str], Dict],
    waive_serial: bool,
    waive_forced: bool,
    use_soft: bool,  # NEW
) -> Tuple[int, Tuple]:
    # If soft constraints are disabled, return zero penalty (hard rules still enforced elsewhere)
    if not use_soft:
        # Keep a deterministic tiebreak on type/room so value ordering is stable
        return (0, (str(room.room_type), str(room.room)))

    penalty = 0
    tie: List = []

    # --- forced_room preference
    if not waive_forced and booking.forced_room:
        if str(room.room).strip() != str(booking.forced_room).strip():
            penalty += 5
        else:
            penalty -= 10  # strong bonus

    # --- serial adjacency
    if not waive_serial:
        last_rooms = family_serial_memory.get(booking.family, [])
        if last_rooms:
            if are_serial(last_rooms[-1], room.room):
                penalty -= 3
            else:
                penalty += 1

    # --- שטח preferences & cluster rules
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
                penalty += (6 if area != chosen else -2)

        if meta and meta["target_set"]:
            if num in meta["target_set"]:
                idx = meta["target_set"].index(num)
                penalty -= (12 - idx)
            else:
                ts_areas = {field_area_id(n) for n in meta["target_set"] if n is not None}
                if len(ts_areas) == 1 and area is not None and next(iter(ts_areas)) == area:
                    penalty -= 1

        if meta and meta["size"] == 1:
            if num in PROHIBITED_SINGLE_ROOMS:
                penalty += 50
            if num == LAST_PRIORITY_ROOM:
                penalty += 100

        if meta:
            assigned = meta["assigned_numbers"]
            for cluster in FIELD_CLUSTERS:
                if assigned & cluster:
                    if (num in cluster and any(a not in cluster for a in assigned)) or (
                        num not in cluster and assigned & cluster):
                        penalty += 30

    tie.extend([str(room.room_type), str(room.room)])
    return (penalty, tuple(tie))

# -----------------------------------------------------------------------------
# Search with budgets and best-so-far fallback
# -----------------------------------------------------------------------------
def _search_assignments(
    bookings: List[Booking],
    rooms: List[Room],
    field_groups_all: Dict[Tuple[str, str, str, str], Dict],
    *,
    waive_serial: bool,
    waive_forced: bool,
    time_limit_sec: float,
    node_limit: int,
    log: Callable[[str], None],
    use_soft: bool,   # NEW
) -> Tuple[Dict[int, str], bool, int, bool]:
    start = time.perf_counter()
    explored_nodes = 0
    timed_out = False

    calendars: Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]] = defaultdict(list)
    family_serial_memory: Dict[str, List[str]] = defaultdict(list)

    bset = {(b.family, b.room_type, b.check_in, b.check_out) for b in bookings if is_field_type(b.room_type)}
    field_groups = {k: dict(v) for k, v in field_groups_all.items() if k in bset}
    for meta in field_groups.values():
        meta["assigned_numbers"] = set()
        meta["chosen_area"] = None

    def parse_date(s: str) -> pd.Timestamp:
        return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")

    intervals: Dict[int, Tuple[pd.Timestamp, pd.Timestamp]] = {
        b.idx: (parse_date(b.check_in), parse_date(b.check_out)) for b in bookings
    }

    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms:
        rooms_by_type[rm.room_type].append(rm)

    best_map: Dict[int, str] = {}
    best_penalty = float("inf")

    # -------------------------------------------------------------------------
    # Ensure forced-room bookings are tried first in the depth order
    forced_pos = [i for i, b in enumerate(bookings) if b.forced_room]
    nonforced = [i for i, b in enumerate(bookings) if not b.forced_room]
    depth_order = forced_pos + nonforced

    def feasible(b: Booking, rm: Room) -> bool:
        ci, co = intervals[b.idx]
        if pd.isna(ci) or pd.isna(co):
            return False
        for (eci, eco) in calendars[rm.room]:
            if ci < eco and eci < co:
                return False
        return True

    def now_exceeded() -> bool:
        nonlocal timed_out
        if explored_nodes >= node_limit or (time.perf_counter() - start) >= time_limit_sec:
            timed_out = True
            return True
        return False

    def backtrack(depth: int, current_map: Dict[int, str], current_pen: int) -> Optional[Dict[int, str]]:
        nonlocal explored_nodes, best_map, best_penalty

        if now_exceeded():
            return None

        if len(current_map) > len(best_map) or (len(current_map) == len(best_map) and current_pen < best_penalty):
            best_map = dict(current_map)
            best_penalty = current_pen

        if depth == len(depth_order):
            return dict(current_map)

        candidates_per_bid: Dict[int, List[Room]] = {}
        mrv_list: List[Tuple[int, int, int]] = []

        # Generate feasible candidates, hard-enforcing forced_room
        for pos in depth_order:
            b = bookings[pos]
            bid = b.idx
            if bid in current_map:
                continue

            feas = [rm for rm in rooms_by_type.get(b.room_type, []) if feasible(b, rm)]
            if b.forced_room:
                feas = [
                    rm for rm in feas
                    if str(rm.room).strip() == str(b.forced_room).strip()
                ]

            candidates_per_bid[bid] = feas
            mrv_list.append((len(feas), pos, bid))

        explored_nodes += 1
        if not mrv_list:
            return dict(current_map)

        mrv_list.sort()
        _, pos, bid = mrv_list[0]
        b = bookings[pos]
        feas = candidates_per_bid[bid]

        # Value ordering by score
        scored: List[Tuple[Tuple[int], Room]] = []
        for rm in feas:
            sc_pen, _ = score_candidate(
                b, rm, family_serial_memory, field_groups, waive_serial, waive_forced, use_soft
            )
            scored.append(((sc_pen,), rm))
        scored.sort(key=lambda x: x[0])
        ordered_rooms = [rm for _, rm in scored]

        for rm in ordered_rooms:
            current_map[bid] = rm.room
            ci, co = intervals[bid]
            calendars[rm.room].append((ci, co))
            family_serial_memory[b.family].append(rm.room)

            if is_field_type(b.room_type):
                key = (b.family, b.room_type, b.check_in, b.check_out)
                meta = field_groups.get(key)
                if meta is not None:
                    num = extract_room_number(rm.room)
                    if num is not None:
                        meta["assigned_numbers"].add(num)
                        if meta.get("chosen_area") is None:
                            meta["chosen_area"] = field_area_id(num)

            res = backtrack(
                depth + 1,
                current_map,
                current_pen + score_candidate(b, rm, family_serial_memory, field_groups, waive_serial, waive_forced, use_soft)[0]
            )
            if res is not None and len(res) == len(bookings):
                return res

            # undo assignment
            calendars[rm.room].pop()
            family_serial_memory[b.family].pop()
            if is_field_type(b.room_type):
                key = (b.family, b.room_type, b.check_in, b.check_out)
                meta = field_groups.get(key)
                if meta is not None:
                    num = extract_room_number(rm.room)
                    if num is not None and num in meta["assigned_numbers"]:
                        meta["assigned_numbers"].remove(num)

            del current_map[bid]

            if now_exceeded():
                break

        return None

    full = backtrack(0, {}, 0)
    complete = full is not None and len(full) == len(bookings)
    return (full or best_map), complete, explored_nodes, timed_out

# -----------------------------------------------------------------------------
# Public API: assign_rooms
# -----------------------------------------------------------------------------
def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func: Optional[Callable[[str], None]] = None,
    *,
    time_limit_sec: float = 60.0,
    node_limit: int = 500_000,
    solve_per_type: bool = True,
    use_soft: bool = True,   # NEW
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Backtracking solver with MRV + soft scoring.
    Forced_room has been promoted to a HARD constraint.
    Relaxation ladder per type:
      1) honor forced_room only
      2) honor forced_room + serial adjacency
      3) relax both
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

    rooms_list = [
        Room(room=str(r.get("room", "")).strip(), room_type=str(r.get("room_type", "")).strip())
        for _, r in rooms_df.fillna("").iterrows()
    ]
    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms_list:
        rooms_by_type[rm.room_type].append(rm)

    bookings_by_type: Dict[str, List[Booking]] = defaultdict(list)
    for b in bookings:
        bookings_by_type[b.room_type].append(b)

    if not solve_per_type:
        rt_list = ["<all>"]
        per_type_bookings = {"<all>": bookings}
        per_type_rooms = {"<all>": rooms_list}
    else:
        rt_list = sorted(bookings_by_type.keys())
        per_type_bookings = bookings_by_type
        per_type_rooms = rooms_by_type

    t_per = max(time_limit_sec / max(1, len(rt_list)), 3.0)
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

        field_groups = build_field_groups(bk)

        best_map: Dict[int, str] = {}
        best_complete = False
        for waive_serial, waive_forced in [
            (True,  False),
            (False, False),
            (True,  True),
        ]:
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

    assigned_rows, unassigned_rows = [], []
    for b in bookings:
        base = {
            "_idx": b.idx,
            "id": b.idx,
            "family": b.family,
            "room_type": b.room_type,
            "check_in": b.check_in,
            "check_out": b.check_out,
            "forced_room": b.forced_room or "",
        }
        room_assigned = global_assigned.get(b.idx, "")
        row = dict(base, room=room_assigned)
        if room_assigned:
            assigned_rows.append(row)
        else:
            unassigned_rows.append(row)

    return pd.DataFrame(assigned_rows), pd.DataFrame(unassigned_rows)

# -----------------------------------------------------------------------------
# Back-compat wrapper
# -----------------------------------------------------------------------------
def assign_per_type(families_arg, rooms_arg, *args, **kwargs):
    families_df = families_arg if isinstance(families_arg, pd.DataFrame) else pd.DataFrame(families_arg)
    rooms_df    = rooms_arg    if isinstance(rooms_arg,    pd.DataFrame) else pd.DataFrame(rooms_arg)

    log_func = kwargs.get("log_func", None)
    for a in reversed(args):
        if callable(a):
            log_func = a
            break

    assigned_df, unassigned_df = assign_rooms(families_df, rooms_df, log_func=log_func)
    return assigned_df, unassigned_df, None
