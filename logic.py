# logic.py
from __future__ import annotations
import re
from datetime import datetime as dt
from typing import Callable, Dict, List, Tuple, Optional

import pandas as pd

# -------------------------- Configuration / Globals --------------------------

DATE_FMT = "%d/%m/%Y"

# Room calendars keyed by (room_type, room_id) so the same numeric label can
# exist under different room types without colliding.
room_calendars: Dict[Tuple[str, str], List[Tuple[dt, dt]]] = {}


# ------------------------------- Utilities -----------------------------------

def _parse_date(s: str) -> dt:
    return dt.strptime(str(s).strip(), DATE_FMT)


def _norm_room(x) -> str:
    """Normalize any room value to a clean string (no spaces)."""
    return str(x).strip()


def _room_sort_key(r: str):
    """
    Sort rooms numerically by the first number inside the label, then by the
    full string as tie-breaker. e.g., '2' < '10' and 'WC01' < 'WC02'.
    """
    s = _norm_room(r)
    m = re.search(r"\d+", s)
    return (int(m.group()) if m else float("inf"), s)


def _overlaps(a_start: dt, a_end: dt, b_start: dt, b_end: dt) -> bool:
    """Half-open intervals: [start, end). checkout == next checkin is OK."""
    return not (a_end <= b_start or a_start >= b_end)


def _clean_opt(v) -> str:
    """
    Treat NaN/'nan'/'none'/'null'/'' as empty. Return a trimmed string otherwise.
    Use for optional fields like forced_room.
    """
    if pd.isna(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"", "nan", "none", "null"} else s


# ------------------------------- Calendar ------------------------------------

def is_available(room_type: str, room: str, check_in_str: str, check_out_str: str) -> bool:
    """Check availability for (room_type, room) across all reserved intervals."""
    key = (str(room_type).strip(), _norm_room(room))
    check_in = _parse_date(check_in_str)
    check_out = _parse_date(check_out_str)

    if key not in room_calendars:
        room_calendars[key] = []

    for (start, end) in room_calendars[key]:
        if _overlaps(check_in, check_out, start, end):
            return False
    return True


def reserve(room_type: str, room: str, check_in_str: str, check_out_str: str) -> None:
    """Reserve a room by adding its interval to the calendar."""
    key = (str(room_type).strip(), _norm_room(room))
    check_in = _parse_date(check_in_str)
    check_out = _parse_date(check_out_str)
    if key not in room_calendars:
        room_calendars[key] = []
    room_calendars[key].append((check_in, check_out))


# ------------------------- Interval/Capacity Helpers -------------------------

def _max_overlap(rows: List[dict]) -> int:
    """Return the maximum number of overlapping intervals (lower bound on rooms needed)."""
    events = []
    for r in rows:
        events.append((_parse_date(r["check_in"]), 1))
        events.append((_parse_date(r["check_out"]), -1))
    events.sort()
    cur = best = 0
    for _, delta in events:
        cur += delta
        best = max(best, cur)
    return best


def _no_conflict_with_schedule(room_sched: List[Tuple[dt, dt]], start: dt, end: dt) -> bool:
    for s, e in room_sched:
        if _overlaps(s, e, start, end):
            return False
    return True


# ---------------------------- Global Solver (per type) -----------------------

def _assign_per_type(
    rows: List[dict],
    rooms: List[str],
    room_type: str,
    log_func: Callable[[str], None],
) -> Tuple[Dict[int, str], List[int], List[int]]:
    """
    Assign all rows of a given room_type using:
      1) Forced pre-placement (greedy, conflict-detecting)
      2) Backtracking with MRV (minimum remaining values) to fill the rest
    Returns:
      assignment_map: {row_idx -> room_label}
      waived_forced_indices: [row_idx ...]  (forced waived to enable full assignment)
      unassigned_indices:    [row_idx ...]  (if impossible; capacity shortfall)
    """
    # Normalize room labels
    rooms = [_norm_room(r) for r in rooms]
    rooms.sort(key=_room_sort_key)

    # Prepare schedules per room (local to this type run)
    schedules: Dict[str, List[Tuple[dt, dt]]] = {r: [] for r in rooms}

    # Index rows for stable reference
    for i, r in enumerate(rows):
        r["_idx"] = i
        r["_start"] = _parse_date(r["check_in"])
        r["_end"] = _parse_date(r["check_out"])
        r["_forced"] = _clean_opt(r.get("forced_room", ""))

    # Quick feasibility check (lower bound)
    if _max_overlap(rows) > len(rooms):
        log_func(
            f"⚠️ {room_type}: required concurrent rooms exceed available ({_max_overlap(rows)} > {len(rooms)})."
        )

    # ------------- Step 1: Forced pre-placement with conflict resolution -----
    assignment: Dict[int, str] = {}
    waived_forced: List[int] = []

    # Group by forced room
    forced_groups: Dict[str, List[dict]] = {}
    for r in rows:
        if r["_forced"]:
            if r["_forced"] not in rooms:
                # Non-existent room label; must waive
                waived_forced.append(r["_idx"])
                r["_forced"] = ""
                log_func(f"⚠️ {r['family']}/{room_type}: forced room {r.get('forced_room')} not found → waived.")
                continue
            forced_groups.setdefault(r["_forced"], []).append(r)

    # For each forced room, greedily place non-overlapping rows; waive the conflicting ones
    for forced_room, group in forced_groups.items():
        # Sort by earliest end to pack more (classic interval scheduling)
        group_sorted = sorted(group, key=lambda x: (x["_end"], x["_start"]))
        placed_intervals: List[Tuple[dt, dt, int]] = []
        for r in group_sorted:
            can_place = True
            for (s, e, _) in placed_intervals:
                if _overlaps(s, e, r["_start"], r["_end"]):
                    can_place = False
                    break
            if can_place and _no_conflict_with_schedule(schedules[forced_room], r["_start"], r["_end"]):
                schedules[forced_room].append((r["_start"], r["_end"]))
                assignment[r["_idx"]] = forced_room
                placed_intervals.append((r["_start"], r["_end"], r["_idx"]))
                # keep forced
            else:
                # waive this forced — will be assigned later by solver
                waived_forced.append(r["_idx"])
                r["_forced"] = ""
                log_func(
                    f"⚠️ {r['family']}/{room_type}: forced {forced_room} overlaps with another forced → waived."
                )

    # ------------- Step 2: Backtracking for all remaining rows ---------------
    # Build the set of remaining row indices to assign
    remainder: List[dict] = [r for r in rows if r["_idx"] not in assignment]

    # Helper: candidates per row given current schedules
    def candidates_for(row: dict) -> List[str]:
        start, end = row["_start"], row["_end"]
        cands = []
        for rm in rooms:
            # Respect current assignments (schedules filled)
            if _no_conflict_with_schedule(schedules[rm], start, end):
                cands.append(rm)
        # Prefer rooms that keep serial with same family's already assigned rooms
        fam_rooms = {assignment[idx] for idx in assignment if rows[idx]["family"] == row["family"]}
        def serial_score(rm: str) -> int:
            # count how many already-assigned rooms for this family are serial with rm
            score = 0
            for fr in fam_rooms:
                if are_serial(fr, rm):
                    score += 1
            return -score  # negative for ascending sort; more serial → smaller key
        cands.sort(key=lambda rm: (serial_score(rm), _room_sort_key(rm)))
        return cands

    # MRV selection: pick row with fewest candidates
    def select_unassigned(unassigned: List[dict]) -> Optional[dict]:
        best = None
        best_count = 10**9
        for r in unassigned:
            c = candidates_for(r)
            cnt = len(c)
            if cnt < best_count:
                best = r
                best_count = cnt
                if cnt == 0:
                    # Early fail shortcut
                    return r
        return best

    solved = False
    best_partial_assignment: Dict[int, str] = assignment.copy()  # in case of failure

    def backtrack(unassigned: List[dict]) -> bool:
        nonlocal solved, best_partial_assignment
        if not unassigned:
            solved = True
            return True

        # MRV: row with fewest valid rooms now
        row = select_unassigned(unassigned)
        cands = candidates_for(row)

        if not cands:
            # dead end
            return False

        # Try each candidate room
        for rm in cands:
            # Place
            schedules[rm].append((row["_start"], row["_end"]))
            assignment[row["_idx"]] = rm

            # Recurse
            nxt = [r for r in unassigned if r["_idx"] != row["_idx"]]
            if backtrack(nxt):
                return True

            # Undo
            schedules[rm].pop()
            assignment.pop(row["_idx"], None)

        # Track best partial (more assigned rows)
        if len(assignment) > len(best_partial_assignment):
            best_partial_assignment = assignment.copy()

        return False

    if remainder:
        backtrack(remainder)

    if not solved and remainder:
        # Could not fully assign; compute which rows remain unassigned
        assigned_now = set(assignment.keys())
        all_ids = {r["_idx"] for r in rows}
        unassigned_ids = sorted(list(all_ids - assigned_now))
        # Log a concise summary
        log_func(
            f"❌ {room_type}: could not assign {len(unassigned_ids)} row(s) without breaking hard constraints."
        )
        return assignment, waived_forced, unassigned_ids

    return assignment, waived_forced, []


# ------------------------------- Main API ------------------------------------

def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func: Callable[[str], None] = print,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute room assignments with relaxation:
      - Try to honor forced rooms; waive only when necessary to assign everyone.
      - Prefer serial rooms but never at the expense of feasibility.
      - Never violate hard constraints (no double bookings; room_type bound).
    Returns:
        assigned_df: columns = [family, room, room_type, check_in, check_out, forced_room]
        unassigned_df: original unassigned rows with their original columns (only if impossible)
    """
    # Reset calendars each run
    global room_calendars
    room_calendars = {}

    fam = families_df.copy()
    rms = rooms_df.copy()

    # ---- Rooms normalization
    rms["room_type"] = rms["room_type"].astype(str).str.strip()
    rms["room"] = rms["room"].astype(str).str.strip()
    rooms_by_type: Dict[str, List[str]] = (
        rms.groupby("room_type")["room"]
        .apply(lambda x: sorted(map(_norm_room, x), key=_room_sort_key))
        .to_dict()
    )

    # ---- Families normalization
    # Family name can be English or Hebrew header
    if "full_name" in fam.columns:
        fam["family"] = fam["full_name"].astype(str).str.strip()
    elif "שם מלא" in fam.columns:
        fam["family"] = fam["שם מלא"].astype(str).str.strip()
    else:
        raise ValueError("Missing 'full_name' (or 'שם מלא') column in families CSV.")

    # Required fields
    for col in ["room_type", "check_in", "check_out"]:
        if col not in fam.columns:
            raise ValueError(f"Missing '{col}' column in families CSV.")
        fam[col] = fam[col].astype(str).str.strip()

    # Optional forced_room
    if "forced_room" not in fam.columns:
        fam["forced_room"] = ""
    fam["forced_room"] = fam["forced_room"].fillna("").astype(str).str.strip()
    fam["forced_room"] = fam["forced_room"].apply(_clean_opt)

    assigned_rows: List[dict] = []
    unassigned_rows: List[dict] = []

    # Solve independently per room_type
    for rt, group in fam.groupby("room_type", sort=False):
        rows = group.to_dict("records")
        available = rooms_by_type.get(rt, [])
        if not available:
            # No rooms of this type exist → all rows unassigned
            for r in rows:
                unassigned_rows.append(r)
            log_func(f"❌ {rt}: no rooms of this type are defined.")
            continue

        assignment_map, waived_forced_ids, unassigned_ids = _assign_per_type(rows, available, rt, log_func)

        # Build outputs; also reserve into global calendars for validate & override flows
        for r in rows:
            idx = r["_idx"]
            if idx in assignment_map:
                room_assigned = assignment_map[idx]
                reserve(rt, room_assigned, r["check_in"], r["check_out"])
                assigned_rows.append(
                    {
                        "family": r["family"],
                        "room": room_assigned,
                        "room_type": rt,
                        "check_in": r["check_in"],
                        "check_out": r["check_out"],
                        "forced_room": _clean_opt(r.get("forced_room", "")),
                    }
                )
                # Logging
                fr = _clean_opt(r.get("forced_room", ""))
                if fr and idx not in waived_forced_ids and room_assigned == fr:
                    log_func(f"🏷️ {r['family']}/{rt}: used forced room {room_assigned}")
                elif fr and idx in waived_forced_ids:
                    log_func(f"⚠️ {r['family']}/{rt}: forced {fr} waived to enable full assignment (assigned {room_assigned}).")
                else:
                    log_func(f"✅ {r['family']}/{rt}: assigned {room_assigned}")
            else:
                # truly unassigned (capacity shortfall)
                unassigned_rows.append(r)

        # Summary notes per type
        if waived_forced_ids:
            log_func(f"ℹ️ {rt}: waived {len(waived_forced_ids)} forced preference(s) to assign everyone else.")
        if unassigned_ids:
            log_func(f"ℹ️ {rt}: {len(unassigned_ids)} row(s) remain unassigned — capacity/overlap infeasible.")

    assigned_df = pd.DataFrame(assigned_rows)
    unassigned_df = pd.DataFrame(unassigned_rows)

    return assigned_df, unassigned_df


# ----------------------------- Validations -----------------------------------

def are_serial(r1: str, r2: str) -> bool:
    """Two rooms are 'serial' if their first numeric parts differ by exactly 1."""
    n1 = re.findall(r"\d+", _norm_room(r1))
    n2 = re.findall(r"\d+", _norm_room(r2))
    if n1 and n2:
        return abs(int(n1[0]) - int(n2[0])) == 1
    return False


def validate_constraints(assigned_df: pd.DataFrame) -> tuple[bool, list[str]]:
    """
    Validate hard and soft constraints.

    Returns:
        hard_ok (bool): True if no overlaps for any (room_type, room)
        soft_violations (list[str]): notes about non-serial allocations or unmet forced rooms
    """
    if assigned_df is None or assigned_df.empty:
        return True, []

    df = assigned_df.copy()
    df["room"] = df["room"].astype(str).str.strip()
    df["room_type"] = df["room_type"].astype(str).str.strip()

    # Hard: no overlapping intervals per (room_type, room)
    hard_ok = True
    for (rt, r), grp in df.groupby(["room_type", "room"]):
        intervals = []
        for _, row in grp.iterrows():
            try:
                start = _parse_date(row["check_in"])
                end = _parse_date(row["check_out"])
            except Exception:
                # If dates are malformed, treat as hard violation
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

    # Soft: seriality within a family per room_type; and forced rooms honored
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
                    soft_violations.append(
                        f"{family}/{rt}: rooms not in serial order ({', '.join(rooms_sorted)})."
                    )

        # Forced-room satisfaction
        for _, row in fam_grp.iterrows():
            forced = _clean_opt(row.get("forced_room", ""))
            if forced and str(row["room"]).strip() != forced:
                soft_violations.append(f"{family}: forced {forced} not met (got {row['room']}).")

    return hard_ok, soft_violations


def rebuild_calendar_from_assignments(assigned_df: pd.DataFrame) -> None:
    """
    Rebuild internal calendars from an assigned table (for manual edits).
    """
    global room_calendars
    room_calendars = {}
    if assigned_df is None or assigned_df.empty:
        return
    for _, row in assigned_df.iterrows():
        reserve(row["room_type"], row["room"], row["check_in"], row["check_out"])
