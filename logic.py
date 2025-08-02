# logic.py
from __future__ import annotations
import re
from datetime import datetime as dt
from typing import Callable, Dict, List, Tuple, Optional, DefaultDict

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
    Assign all rows of a given room_type with relaxation order:
      1) Serial preference is only a tie-breaker (implicitly sacrificed first).
      2) If still infeasible, waive the minimal number of forced rows (try k=1).
    Returns:
      assignment_map: {row_idx -> room_label}
      waived_forced_indices: [row_idx ...]  (forced waived to enable full assignment)
      unassigned_indices:    [row_idx ...]  (if impossible; capacity shortfall)
    """
    # Normalize room labels
    rooms = [_norm_room(r) for r in rooms]
    rooms.sort(key=_room_sort_key)

    # Prepare schedules per room (local to this type run)
    def fresh_schedules() -> Dict[str, List[Tuple[dt, dt]]]:
        return {r: [] for r in rooms}

    schedules: Dict[str, List[Tuple[dt, dt]]] = fresh_schedules()

    # Index rows for stable reference
    for i, r in enumerate(rows):
        r["_idx"] = i
        r["_start"] = _parse_date(r["check_in"])
        r["_end"] = _parse_date(r["check_out"])
        r["_forced"] = _clean_opt(r.get("forced_room", ""))

    # Quick feasibility hint (lower bound)
    mo = _max_overlap(rows)
    if mo > len(rooms):
        log_func(f"⚠️ {room_type}: required concurrent rooms exceed available ({mo} > {len(rooms)}).")

    # ---- Forced pre-placement (conflicts only against same forced room) ----
    assignment: Dict[int, str] = {}
    waived_forced: List[int] = []
    pinned_forced_ids: List[int] = []  # forced rows we managed to pin

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

    # For each forced room, pack non-overlapping intervals; waive the rest.
    for forced_room, group in forced_groups.items():
        group_sorted = sorted(group, key=lambda x: (x["_end"], x["_start"]))
        placed_intervals: List[Tuple[dt, dt, int]] = []
        for r in group_sorted:
            can_place = all(not _overlaps(s, e, r["_start"], r["_end"]) for (s, e, _) in placed_intervals)
            can_place = can_place and _no_conflict_with_schedule(schedules[forced_room], r["_start"], r["_end"])
            if can_place:
                schedules[forced_room].append((r["_start"], r["_end"]))
                assignment[r["_idx"]] = forced_room
                placed_intervals.append((r["_start"], r["_end"], r["_idx"]))
                pinned_forced_ids.append(r["_idx"])
            else:
                # Intrinsic conflict (same room/time) → cannot satisfy both forced
                waived_forced.append(r["_idx"])
                r["_forced"] = ""
                log_func(f"⚠️ {r['family']}/{room_type}: forced {forced_room} overlaps with another forced → waived.")

    # ---- MRV backtracking for the rest (serial is only a preference) ----
    def candidates_for(row: dict, sched: Dict[str, List[Tuple[dt, dt]]], cur_assign: Dict[int, str]) -> List[str]:
        start, end = row["_start"], row["_end"]
        cands = [rm for rm in rooms if _no_conflict_with_schedule(sched[rm], start, end)]

        # Prefer rooms that keep serial with already-assigned rooms of the same family
        fam_rooms = {cur_assign[idx] for idx in cur_assign if rows[idx]["family"] == row["family"]}
        def serial_score(rm: str) -> int:
            return -sum(1 for fr in fam_rooms if are_serial(fr, rm))  # more serial → smaller (better)
        cands.sort(key=lambda rm: (serial_score(rm), _room_sort_key(rm)))
        return cands

    def select_unassigned(unassigned: List[dict], sched, cur_assign) -> dict:
        best, best_count = None, 10**9
        for r in unassigned:
            cnt = len(candidates_for(r, sched, cur_assign))
            if cnt < best_count:
                best, best_count = r, cnt
                if cnt == 0:
                    return r
        return best

    solved = False
    best_partial: Dict[int, str] = assignment.copy()

    def backtrack(unassigned: List[dict], sched, cur_assign) -> bool:
        nonlocal solved, best_partial
        if not unassigned:
            solved = True
            return True
        row = select_unassigned(unassigned, sched, cur_assign)
        cands = candidates_for(row, sched, cur_assign)
        if not cands:
            return False
        for rm in cands:
            sched[rm].append((row["_start"], row["_end"]))
            cur_assign[row["_idx"]] = rm
            nxt = [r for r in unassigned if r["_idx"] != row["_idx"]]
            if backtrack(nxt, sched, cur_assign):
                return True
            sched[rm].pop()
            cur_assign.pop(row["_idx"], None)
        if len(cur_assign) > len(best_partial):
            best_partial = cur_assign.copy()
        return False

    remainder = [r for r in rows if r["_idx"] not in assignment]
    if remainder:
        backtrack(remainder, schedules, assignment)

    if solved:
        return assignment, waived_forced, []

    # ----------------- Relaxation step 2: consider waiving forced ------------
    # We already sacrificed serial (never enforced). Now, as a LAST RESORT,
    # try waiving exactly one *pinned* forced row to see if we can assign everyone.
    if pinned_forced_ids:
        # Rank forced rows by "conflict degree" (how many other rows overlap in time)
        def conflict_degree(fid: int) -> int:
            r = next(x for x in rows if x["_idx"] == fid)
            return sum(1 for o in rows if o["_idx"] != fid and _overlaps(r["_start"], r["_end"], o["_start"], o["_end"]))
        try_order = sorted(pinned_forced_ids, key=lambda fid: -conflict_degree(fid))

        for fid in try_order:
            # Build fresh schedules/assignment with all pinned forced except 'fid'
            sched2 = fresh_schedules()
            assign2: Dict[int, str] = {}
            for pid in pinned_forced_ids:
                if pid == fid:
                    continue  # waived candidate
                pr = rows[pid]
                rm = assignment[pid]
                sched2[rm].append((pr["_start"], pr["_end"]))
                assign2[pid] = rm

            # Unassigned set includes the waived one and everyone else not yet placed
            remainder2 = [r for r in rows if r["_idx"] not in assign2]

            solved2 = False
            best_partial_local: Dict[int, str] = assign2.copy()

            def backtrack2(unassigned2: List[dict], sched_local, cur_assign_local) -> bool:
                nonlocal solved2, best_partial_local
                if not unassigned2:
                    solved2 = True
                    return True
                row = select_unassigned(unassigned2, sched_local, cur_assign_local)
                cands = candidates_for(row, sched_local, cur_assign_local)
                if not cands:
                    return False
                for rm in cands:
                    sched_local[rm].append((row["_start"], row["_end"]))
                    cur_assign_local[row["_idx"]] = rm
                    nxt = [r for r in unassigned2 if r["_idx"] != row["_idx"]]
                    if backtrack2(nxt, sched_local, cur_assign_local):
                        return True
                    sched_local[rm].pop()
                    cur_assign_local.pop(row["_idx"], None)
                if len(cur_assign_local) > len(best_partial_local):
                    best_partial_local = cur_assign_local.copy()
                return False

            if remainder2:
                backtrack2(remainder2, sched2, assign2)

            if solved2:
                # Success by waiving exactly one forced
                waived_forced.append(fid)
                log_func(f"ℹ️ {room_type}: waived 1 forced preference to enable full assignment.")
                return assign2, waived_forced, []

    # Still infeasible → report which remain unassigned
    assigned_now = set(assignment.keys())
    all_ids = {r["_idx"] for r in rows}
    unassigned_ids = sorted(list(all_ids - assigned_now))
    log_func(f"❌ {room_type}: could not assign {len(unassigned_ids)} row(s) without breaking hard constraints.")
    return assignment, waived_forced, unassigned_ids


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
      - Never violate hard constraints (no double bookings; correct room_type).
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


# ============================= Diagnostics ===================================
# These helpers analyze "why" a soft constraint wasn't satisfied in the *final*
# assignment produced by assign_rooms(). They do not change the assignment.

def _schedules_from_df(assigned_df: pd.DataFrame):
    """
    Build a schedule dict: {(room_type, room) -> [(start, end, family), ...]}
    """
    sched: Dict[Tuple[str, str], List[Tuple[dt, dt, str]]] = {}
    if assigned_df is None or assigned_df.empty:
        return sched
    for _, row in assigned_df.iterrows():
        rt = str(row["room_type"]).strip()
        rm = _norm_room(row["room"])
        key = (rt, rm)
        sched.setdefault(key, []).append(
            (_parse_date(row["check_in"]), _parse_date(row["check_out"]), str(row["family"]))
        )
    return sched


def _conflicts_on(sched, room_type: str, room: str, start: dt, end: dt) -> List[Tuple[str, str, str]]:
    """
    Return list of conflicting assignments on (room_type, room) that overlap [start, end).
    Each item: (family, check_in_str, check_out_str)
    """
    key = (str(room_type).strip(), _norm_room(room))
    out = []
    for s, e, fam in sched.get(key, []):
        if _overlaps(s, e, start, end):
            out.append((fam, s.strftime(DATE_FMT), e.strftime(DATE_FMT)))
    return out


def _rooms_by_type_from_df(rooms_df: pd.DataFrame) -> Dict[str, List[str]]:
    """Consistent room ordering for diagnostics."""
    rdf = rooms_df.copy()
    rdf["room_type"] = rdf["room_type"].astype(str).str.strip()
    rdf["room"] = rdf["room"].astype(str).str.strip()
    return (
        rdf.groupby("room_type")["room"]
        .apply(lambda x: sorted(map(_norm_room, x), key=_room_sort_key))
        .to_dict()
    )


def _perfect_matching(choices: Dict[int, List[str]]) -> bool:
    """
    Simple DFS-based bipartite matching: rows (indices) -> rooms (labels).
    Returns True if every row can be matched to a distinct room in its candidate list.
    """
    matchR: Dict[str, int] = {}

    def dfs(u: int, seen: set) -> bool:
        for v in choices.get(u, []):
            if v in seen:
                continue
            seen.add(v)
            if v not in matchR or dfs(matchR[v], seen):
                matchR[v] = u
                return True
        return False

    for u in choices.keys():
        if not dfs(u, set()):
            return False
    return True


def explain_soft_constraints(
    assigned_df: pd.DataFrame,
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Produce a row-per-issue explanation:
      violation          : 'forced_not_met' | 'non_serial'
      family             : family name
      room_type          : affected type
      check_in/check_out : (forced rows only)
      forced_room        : (forced rows only)
      assigned_room      : (forced rows only)
      assigned_rooms     : (serial only) list of final rooms
      feasible_serial_block : a serial block that *could* have worked given others fixed, or ''
      reason             : concise explanation
      blockers           : semicolon-separated conflicts (family and dates)
    """
    results: List[dict] = []
    if assigned_df is None or assigned_df.empty:
        return pd.DataFrame(results)

    # Build helper maps
    sched = _schedules_from_df(assigned_df)
    rooms_by_type = _rooms_by_type_from_df(rooms_df)

    # Normalize families for lookup
    fam = families_df.copy()
    if "family" not in fam.columns:
        if "full_name" in fam.columns:
            fam["family"] = fam["full_name"].astype(str).str.strip()
        elif "שם מלא" in fam.columns:
            fam["family"] = fam["שם מלא"].astype(str).str.strip()
    for c in ["room_type", "check_in", "check_out"]:
        if c in fam.columns:
            fam[c] = fam[c].astype(str).str.strip()
    if "forced_room" not in fam.columns:
        fam["forced_room"] = ""
    fam["forced_room"] = fam["forced_room"].fillna("").astype(str).str.strip()
    fam["forced_room"] = fam["forced_room"].apply(_clean_opt)

    # ----- A) Forced not met --------------------------------------------------
    forced_rows = fam[fam["forced_room"] != ""]
    for _, src in forced_rows.iterrows():
        fml = str(src["family"]).strip()
        rt = str(src["room_type"]).strip()
        ci = str(src["check_in"]).strip()
        co = str(src["check_out"]).strip()
        fr = _norm_room(src["forced_room"])

        # Find the assigned row corresponding to this source row (same family/type/dates)
        mask = (
            (assigned_df["family"].astype(str).str.strip() == fml) &
            (assigned_df["room_type"].astype(str).stripped := assigned_df["room_type"].astype(str).str.strip()) &  # noqa
            (assigned_df["room_type"].astype(str).str.strip() == rt) &
            (assigned_df["check_in"].astype(str).str.strip() == ci) &
            (assigned_df["check_out"].astype(str).str.strip() == co)
        )
        # The ":= …" line above is a harmless no-op to avoid multiple casts when stepping through; kept for readability.

        if not mask.any():
            results.append({
                "violation": "forced_not_met",
                "family": fml, "room_type": rt,
                "check_in": ci, "check_out": co,
                "forced_room": fr, "assigned_room": "",
                "assigned_rooms": "",
                "feasible_serial_block": "",
                "reason": "row not assigned",
                "blockers": "",
            })
            continue

        assigned_row = assigned_df.loc[mask].iloc[0]
        assigned_room = _norm_room(assigned_row["room"])

        if assigned_room == fr:
            continue  # forced met; no issue

        # Analyze reason
        in_type = fr in rooms_by_type.get(rt, [])
        start = _parse_date(ci)
        end = _parse_date(co)

        if not in_type:
            reason = f"forced room {fr} does not exist under room_type '{rt}'."
            blockers = ""
        else:
            confs = _conflicts_on(sched, rt, fr, start, end)
            if confs:
                top = "; ".join([f"{c[0]} ({c[1]}–{c[2]})" for c in confs[:4]])
                reason = f"forced room {fr} was occupied during the interval."
                blockers = top
            else:
                reason = (
                    "solver relaxed forced to achieve full assignment "
                    "(room looks free now, but using it would have blocked other rows)."
                )
                blockers = ""

        results.append({
            "violation": "forced_not_met",
            "family": fml, "room_type": rt,
            "check_in": ci, "check_out": co,
            "forced_room": fr, "assigned_room": assigned_room,
            "assigned_rooms": "",
            "feasible_serial_block": "",
            "reason": reason,
            "blockers": blockers,
        })

    # ----- B) Serial violations ----------------------------------------------
    # Build quick view of assignments by (family, room_type)
    by_family_type: DefaultDict[Tuple[str, str], List[dict]] = DefaultDict(list)
    for _, row in assigned_df.iterrows():
        by_family_type[(str(row["family"]).strip(), str(row["room_type"]).strip())].append({
            "room": _norm_room(row["room"]),
            "check_in": str(row["check_in"]).strip(),
            "check_out": str(row["check_out"]).strip(),
        })

    for (fml, rt), rows in by_family_type.items():
        if len(rows) <= 1:
            continue
        rooms_now = [r["room"] for r in rows]
        rooms_sorted = sorted(rooms_now, key=_room_sort_key)

        # Check if already serial
        serial_ok = True
        for i in range(len(rooms_sorted) - 1):
            if not are_serial(rooms_sorted[i], rooms_sorted[i + 1]):
                serial_ok = False
                break
        if serial_ok:
            continue  # no violation

        # Try to see if any serial block of size k was feasible given other families fixed
        all_rooms = rooms_by_type.get(rt, [])
        k = len(rows)
        feasible_block: List[str] = []
        best_block: List[str] = []
        best_avail_pairs = -1

        # Prepare schedules EXCLUDING this family's own reservations (we are free to move them)
        sched_excl_self: Dict[Tuple[str, str], List[Tuple[dt, dt, str]]] = {}
        base_sched = _schedules_from_df(assigned_df)
        for key, intervals in base_sched.items():
            rt_key, rm_key = key
            if rt_key != rt:
                sched_excl_self[key] = intervals[:]  # copy
                continue
            kept = [(s, e, famname) for (s, e, famname) in intervals if famname != fml]
            if kept:
                sched_excl_self[key] = kept

        # Build row list with parsed dates
        rows_with_dt = [{
            "idx": i,
            "start": _parse_date(r["check_in"]),
            "end": _parse_date(r["check_out"]),
        } for i, r in enumerate(rows)]

        for i in range(max(0, len(all_rooms) - k + 1)):
            block = list(map(_norm_room, all_rooms[i:i + k]))
            # Choices per row inside this block
            choices: Dict[int, List[str]] = {}
            avail_pairs = 0
            for rinfo in rows_with_dt:
                opts = []
                for rm in block:
                    key = (rt, rm)
                    intervals = sched_excl_self.get(key, [])
                    ok = True
                    for s, e, _ in intervals:
                        if _overlaps(s, e, rinfo["start"], rinfo["end"]):
                            ok = False
                            break
                    if ok:
                        opts.append(rm)
                choices[rinfo["idx"]] = opts
                avail_pairs += len(opts)

            if all(choices[j] for j in choices) and _perfect_matching(choices):
                feasible_block = block
                break

            # Track best block for reporting (max total availability)
            if avail_pairs > best_avail_pairs:
                best_avail_pairs = avail_pairs
                best_block = block

        if feasible_block:
            reason = "serial block was feasible without moving other families; solver chose a non-serial arrangement."
            blockers = ""
        else:
            # Summarize blockers inside the best_block
            conflict_notes = []
            for rm in best_block:
                key = (rt, rm)
                for s, e, famname in sched_excl_self.get(key, []):
                    conflict_notes.append(f"{rm} blocked by {famname} ({s.strftime(DATE_FMT)}–{e.strftime(DATE_FMT)})")
            blockers = "; ".join(conflict_notes[:6])
            reason = "no contiguous serial block of size {} was free given other families' reservations.".format(k)

        results.append({
            "violation": "non_serial",
            "family": fml, "room_type": rt,
            "check_in": "", "check_out": "",
            "forced_room": "", "assigned_room": "",
            "assigned_rooms": ", ".join(rooms_sorted),
            "feasible_serial_block": " ".join(feasible_block),
            "reason": reason,
            "blockers": blockers,
        })

    return pd.DataFrame(results)
