from __future__ import annotations
import pandas as pd
from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .utils import is_field_type, extract_room_number, field_area_id
from .validate import check_hard_overlap  # assumed helper you already had (room availability)
from .utils import are_serial  # your existing serial helper, if present

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# “Field area” soft preferences for room_type == "שטח"
# ---------------------------------------------------------------------------

FIELD_ONE_ROOM_PREF = [8, 12, 17, 1, 18]          # 1 room preference list
FIELD_TWO_ROOMS_PREF = [16, 18]                    # 2 rooms -> exactly these two if possible
FIELD_THREE_ROOMS_PREF = [12, 13, 14]              # 3 rooms -> these three
FIELD_FIVE_ROOMS_PREF = [1, 2, 3, 4, 5]            # 5 rooms -> these five (Area 1)

def field_target_set(group_size: int) -> List[int] | None:
    if group_size == 5:
        return FIELD_FIVE_ROOMS_PREF
    if group_size == 3:
        return FIELD_THREE_ROOMS_PREF
    if group_size == 2:
        return FIELD_TWO_ROOMS_PREF
    if group_size == 1:
        return FIELD_ONE_ROOM_PREF
    return None  # no special pattern for other sizes

# ---------------------------------------------------------------------------
# Precompute “groups” for שטח: family + room_type + identical date range
# ---------------------------------------------------------------------------

def build_field_groups(bookings: List[Booking]) -> Dict[Tuple[str, str, str, str], Dict]:
    """
    Groups only שטח bookings by (family, room_type, check_in, check_out).
    Returns mapping to dict with:
      - size: number of rows in the group
      - target_set: list[int] | None   (desired numbers)
      - assigned_numbers: set[int] during search (mutable)
      - chosen_area: int | None        (1..5 or 6..18), inferred as we assign
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

# ---------------------------------------------------------------------------
# Candidate ordering & scoring
# ---------------------------------------------------------------------------

def score_candidate(
    booking: Booking,
    room: Room,
    partial_assign: Dict[int, str],  # booking.idx -> room.room
    groups: Dict[Tuple[str, str, str, str], Dict],
    family_serial_memory: Dict[str, List[str]],  # used by your existing "serial" soft constraint
    waive_serial: bool,
    waive_forced: bool,
) -> Tuple[int, Tuple]:
    """
    Lower score is better (we return (penalty, tie-breakers...)).
    Components:
      - HARD disqualifications handled outside (availability conflicts).
      - SOFT: forced match bonus (unless waived), serial adjacency bonus (unless waived),
              שטח preferences (target sets and area consistency).
    """
    penalty = 0
    tie: List = []

    # --- Soft: forced_room preference
    if not waive_forced and booking.forced_room:
        if str(room.room).strip() != str(booking.forced_room).strip():
            penalty += 5   # prefer matching forced; small penalty if not
        else:
            penalty -= 10  # strong bonus when we match forced

    # --- Soft: serial proximity within same family (existing behavior)
    if not waive_serial:
        last_rooms = family_serial_memory.get(booking.family, [])
        if last_rooms:
            if are_serial(last_rooms[-1], room.room):
                penalty -= 3  # adjacency bonus
            else:
                penalty += 1  # small penalty when we break seriality

    # --- Soft: שטח preferences
    if is_field_type(booking.room_type):
        key = (booking.family, booking.room_type, booking.check_in, booking.check_out)
        meta = groups.get(key)
        num = extract_room_number(room.room)
        area = field_area_id(num)

        # Prefer assigned numbers to stay within one area if group_size>1
        if meta and meta["size"] > 1 and meta["assigned_numbers"]:
            assigned_areas = {field_area_id(n) for n in meta["assigned_numbers"] if n is not None}
            # infer chosen area if not yet fixed
            chosen = meta.get("chosen_area")
            if chosen is None and len(assigned_areas) == 1:
                chosen = assigned_areas.pop()
                meta["chosen_area"] = chosen
            if chosen is not None and area is not None:
                if area != chosen:
                    penalty += 6  # crossing the 5↔6 boundary is undesirable
                else:
                    penalty -= 2  # staying in same area is a small bonus

        # Target set preference by group size
        if meta and meta["target_set"]:
            # big bonus if we hit a desired number; the earlier in list, the better
            if num in meta["target_set"]:
                idx = meta["target_set"].index(num)
                penalty -= (12 - idx)  # 12,11,10,... stronger for earlier preferences
            else:
                # Prefer numbers in the same area as target set (if target spans one area)
                ts_areas = {field_area_id(n) for n in meta["target_set"] if n is not None}
                if len(ts_areas) == 1 and area is not None:
                    (ts_area,) = tuple(ts_areas)
                    if ts_area == area:
                        penalty -= 1  # slight nudge toward target area

    # Tie-breakers to keep room labels stable
    tie.extend([str(room.room_type), str(room.room)])

    return (penalty, tuple(tie))

# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func: Optional[Callable[[str], None]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Backtracking solver with MRV:
      1) Build bookings list (expand families rows into Booking records).
      2) Precompute groups for שטח soft preferences.
      3) Assign respecting HARD constraints; apply SOFT scoring for value ordering.
      4) Relaxation ladder: if no complete solution, retry with (a) waive serial, (b) waive forced.
    """
    log = (lambda m: None) if log_func is None else log_func

    # Normalize families -> Booking list
    fam = families_df.fillna("")
    if "family" not in fam.columns:
        # fallback for alt headers
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
        b = Booking(
            idx=i,
            family=str(r.get("family", "")).strip(),
            room_type=str(r.get("room_type", "")).strip(),
            check_in=str(r.get("check_in", "")).strip(),
            check_out=str(r.get("check_out", "")).strip(),
            forced_room=str(r.get("forced_room", "")).strip() or None,
        )
        bookings.append(b)

    # Rooms catalog
    rooms = [
        Room(room=str(r.get("room", "")).strip(), room_type=str(r.get("room_type", "")).strip())
        for _, r in rooms_df.fillna("").iterrows()
    ]

    # Index rooms by type
    rooms_by_type: Dict[str, List[Room]] = defaultdict(list)
    for rm in rooms:
        rooms_by_type[rm.room_type].append(rm)

    # Build groups for שטח
    field_groups = build_field_groups(bookings)

    # Try with soft constraints full, then relax serial, then relax forced
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
            assigned_map = result  # booking.idx -> room label
            break
    else:
        assigned_map = {}

    # Build output DataFrames
    assigned_rows = []
    unassigned_rows = []
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

    assigned_df = pd.DataFrame(assigned_rows)
    unassigned_df = pd.DataFrame(unassigned_rows)
    return assigned_df, unassigned_df

# ---------------------------------------------------------------------------
# Backtracking search
# ---------------------------------------------------------------------------

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
    MRV: pick the booking with the fewest feasible rooms next.
    Order values with score_candidate() which includes all soft prefs.
    """
    # Availability calendars: room -> list of (ci, co) intervals
    calendars: Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]] = defaultdict(list)

    def parse_date(s: str) -> pd.Timestamp:
        return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")

    # Pre-parse booking intervals
    intervals = {}
    for b in bookings:
        ci = parse_date(b.check_in)
        co = parse_date(b.check_out)
        intervals[b.idx] = (ci, co)

    assigned_map: Dict[int, str] = {}
    family_serial_memory: Dict[str, List[str]] = defaultdict(list)

    # Helper: check if room is free for b
    def feasible(b: Booking, rm: Room) -> bool:
        ci, co = intervals[b.idx]
        if pd.isna(ci) or pd.isna(co):
            return False
        # hard overlap check
        for (eci, eco) in calendars[rm.room]:
            # [ci,co) overlaps [eci,eco) if ci < eco and eci < co
            if ci < eco and eci < co:
                return False
        return True

    # MRV loop with recursion
    order = list(range(len(bookings)))

    def backtrack(pos: int) -> Optional[Dict[int, str]]:
        if pos == len(order):
            return dict(assigned_map)

        # choose next booking: MRV by counting feasible rooms
        # compute feasible set once to reduce rework
        candidates_per_idx: Dict[int, List[Room]] = {}
        counts: List[Tuple[int, int]] = []  # (count, idx)
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

        counts.sort()  # fewest options first
        _, idx = counts[0]
        b = bookings[idx]
        feas = candidates_per_idx[idx]

        # value ordering using soft scoring
        scored = []
        for rm in feas:
            sc = score_candidate(
                b, rm, assigned_map, field_groups, family_serial_memory, waive_serial, waive_forced
            )
            scored.append((sc, rm))
        scored.sort(key=lambda x: x[0])  # lower penalty first
        ordered_rooms = [rm for _, rm in scored]

        # try each room
        for rm in ordered_rooms:
            # assign
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
                        # infer chosen area if still None
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
                        # do not reset chosen_area; leaving it helps keep area coherence

            del assigned_map[idx]

        return None

    return backtrack(0)
