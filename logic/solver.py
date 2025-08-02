# logic/solver.py
from __future__ import annotations
import pandas as pd
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
import re

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
FIELD_ONE_ROOM_PREF   = [8, 12, 17, 1, 18]   # 1 room
FIELD_TWO_ROOMS_PREF  = [16, 18]             # 2 rooms -> 16,18
FIELD_THREE_ROOMS_PREF= [12, 13, 14]         # 3 rooms -> 12,13,14
FIELD_FIVE_ROOMS_PREF = [1, 2, 3, 4, 5]      # 5 rooms -> 1..5

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
    partial_assign: Dict[int, str],               # booking.idx -> room label
    groups: Dict[Tuple[str, str, str, str], Dict],
    family_serial_memory: Dict[str, List[str]],
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

# --- Main solver API ---------------------------------------------------------
def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func: Optional[Callable[[str], None]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Backtracking solver with MRV + soft scoring.
    Relaxation ladder: (serial on, forced on) → (serial off, forced on) → (serial off, forced off).
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
                idx=i,
                family=str(r.get("family", "")).strip(),
                room_type=str(r.get("room_type", "")).strip(),
                check_in=str(r.get("check_in", "")).strip(),
                check_out=str(r.get("check_out", "")).strip(),
                forced_room=(str(r.get("forced_room", "")).strip() or None),
            )
        )

    rooms = [
        Room(room=str(r.get("room", "")).strip(), room_type=str(r.get("room_type", "")).strip())
        for _, r in rooms_df.fillna("").iterrows()
    ]
    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms:
        rooms_by_type[rm.room_type].append(rm)

    field_groups = build_field_groups(bookings)

    assigned_map: Dict[int, str] = {}
    for waive_serial, waive_forced in [(False, False), (True, False), (True, True)]:
        log(f"Start search (waive_serial={waive_serial}, waive_forced={waive_forced})")
        result = _search_assignments(
            bookings,
            rooms_by_type,
            log=log,
            waive_serial=waive_serial,
            waive_forced=waive_forced,
            field_groups=field_groups,
        )
        if result is not None:
            assigned_map = result
            break

    assigned_rows, unassigned_rows = [], []
    for b in bookings:
        row = {
            "family": b.family,
            "room_type": b.room_type,
            "check_in": b.check_in,
            "check_out": b.check_out,
            "forced_room": b.forced_room or "",
        }
        room_assigned = assigned_map.get(b.idx, "")
        if room_assigned:
            row["room"] = room_assigned
            assigned_rows.append(row)
        else:
            row["room"] = ""
            unassigned_rows.append(row)

    return pd.DataFrame(assigned_rows), pd.DataFrame(unassigned_rows)

# Keep backward compatibility with older core.py call-sites
def assign_per_type(families_arg, rooms_arg, *args, **kwargs):
    """
    Older call-sites pass  (families, rooms, maybe_other, log_func).
    • We coerce *anything* that isn't already a DataFrame into one.
    • We treat the *last callable* (positional or keyword) as log_func.
    • Extra positional args that aren't callables are ignored.
    """
    import pandas as pd

    # 1) Coerce first two args to DataFrames if needed
    families_df = families_arg if isinstance(families_arg, pd.DataFrame) else pd.DataFrame(families_arg)
    rooms_df    = rooms_arg    if isinstance(rooms_arg,    pd.DataFrame) else pd.DataFrame(rooms_arg)

    # 2) Detect a logger among *args or **kwargs
    log_func = kwargs.get("log_func", None)
    for a in reversed(args):
        if callable(a):
            log_func = a
            break

    # 3) Delegate to the modern solver
    return assign_rooms(families_df, rooms_df, log_func=log_func)

# --- Backtracking search -----------------------------------------------------
def _search_assignments(
    bookings: List[Booking],
    rooms_by_type: Dict[str, List[Room]],
    *,
    log: Callable[[str], None],
    waive_serial: bool,
    waive_forced: bool,
    field_groups: Dict[Tuple[str, str, str, str], Dict],
) -> Optional[Dict[int, str]]:
    """
    MRV + soft value ordering.
    Hard overlap is enforced via a room->intervals calendar during the search.
    """
    calendars: Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]] = defaultdict(list)

    def parse_date(s: str) -> pd.Timestamp:
        return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")

    intervals = {}
    for b in bookings:
        ci = parse_date(b.check_in)
        co = parse_date(b.check_out)
        intervals[b.idx] = (ci, co)

    assigned_map: Dict[int, str] = {}
    family_serial_memory: Dict[str, List[str]] = defaultdict(list)

    def feasible(b: Booking, rm: Room) -> bool:
        ci, co = intervals[b.idx]
        if pd.isna(ci) or pd.isna(co):
            return False
        for (eci, eco) in calendars[rm.room]:
            if ci < eco and eci < co:  # [ci,co) overlaps [eci,eco)
                return False
        return True

    order = list(range(len(bookings)))

    def backtrack(pos: int) -> Optional[Dict[int, str]]:
        if pos == len(order):
            return dict(assigned_map)

        # MRV: find booking with fewest feasible rooms
        candidates_per_idx: Dict[int, List[Room]] = {}
        counts: List[Tuple[int, int]] = []
        for i in order:
            if i in assigned_map:
                continue
            b = bookings[i]
            rooms = rooms_by_type.get(b.room_type, [])
            feas = [rm for rm in rooms if feasible(b, rm)]
            candidates_per_idx[i] = feas
            counts.append((len(feas), i))

        if not counts:
            return dict(assigned_map)

        counts.sort()
        _, idx = counts[0]
        b = bookings[idx]
        feas = candidates_per_idx[idx]

        # soft scoring for value ordering
        scored = []
        for rm in feas:
            sc = score_candidate(
                b, rm, assigned_map, field_groups, family_serial_memory, waive_serial, waive_forced
            )
            scored.append((sc, rm))
        scored.sort(key=lambda x: x[0])
        ordered_rooms = [rm for _, rm in scored]

        for rm in ordered_rooms:
            assigned_map[idx] = rm.room
            ci, co = intervals[idx]
            calendars[rm.room].append((ci, co))
            family_serial_memory[b.family].append(rm.room)

            # update שטח group meta
            if is_field_type(b.room_type):
                key = (b.family, b.room_type, b.check_in, b.check_out)
                meta = field_groups.get(key)
                if meta is not None:
                    num = extract_room_number(rm.room)
                    if num is not None:
                        meta["assigned_numbers"].add(num)
                        if meta.get("chosen_area") is None:
                            meta["chosen_area"] = field_area_id(num)

            res = backtrack(pos + 1)
            if res is not None:
                return res

            # undo
            calendars[rm.room].pop()
            family_serial_memory[b.family].pop()
            if is_field_type(b.room_type):
                key = (b.family, b.room_type, b.check_in, b.check_out)
                meta = field_groups.get(key)
                if meta is not None:
                    num = extract_room_number(rm.room)
                    if num is not None and num in meta["assigned_numbers"]:
                        meta["assigned_numbers"].remove(num)

            del assigned_map[idx]

        return None

    return backtrack(0)
