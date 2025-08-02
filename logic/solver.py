from __future__ import annotations
from typing import Callable, Dict, List, Tuple, Optional

from .utils import _parse_date, _norm_room, _room_sort_key, are_serial
from .capacity import max_overlap, no_conflict_with_schedule

def assign_per_type(
    rows: List[dict],
    rooms: List[str],
    room_type: str,
    log_func: Callable[[str], None],
) -> Tuple[Dict[int, str], List[int], List[int]]:
    """
    Assign all rows of a given room_type with relaxation order:
      - Serial preference is only a tie-breaker (never blocks feasibility).
      - If still infeasible, waive the minimal number of forced rows (k=1).
    Returns:
      assignment_map: {row_idx -> room_label}
      waived_forced_indices: [row_idx ...]
      unassigned_indices:    [row_idx ...]
    """
    rooms = [_norm_room(r) for r in rooms]
    rooms.sort(key=_room_sort_key)

    def fresh_schedules():
        return {r: [] for r in rooms}

    schedules = fresh_schedules()

    # Index rows
    for i, r in enumerate(rows):
        r["_idx"] = i
        r["_start"] = _parse_date(r["check_in"])
        r["_end"] = _parse_date(r["check_out"])
        r["_forced"] = str(r.get("forced_room", "")).strip()

    # Feasibility hint
    mo = max_overlap(rows)
    if mo > len(rooms):
        log_func(f"⚠️ {room_type}: required concurrent rooms exceed available ({mo} > {len(rooms)}).")

    # Step 1: pin non-conflicting forced on their requested room; waive intrinsic conflicts
    assignment: Dict[int, str] = {}
    waived_forced: List[int] = []
    pinned_forced_ids: List[int] = []

    forced_groups: Dict[str, List[dict]] = {}
    for r in rows:
        fr = r["_forced"]
        if fr:
            if fr not in rooms:
                waived_forced.append(r["_idx"])
                r["_forced"] = ""
                log_func(f"⚠️ {r['family']}/{room_type}: forced room {r.get('forced_room')} not found → waived.")
                continue
            forced_groups.setdefault(fr, []).append(r)

    for forced_room, group in forced_groups.items():
        group_sorted = sorted(group, key=lambda x: (x["_end"], x["_start"]))
        placed: List[Tuple] = []
        for r in group_sorted:
            ok = all(not (s <= r["_start"] < e or s < r["_end"] <= e or (r["_start"] <= s and r["_end"] > s)) for s, e, _ in placed)
            ok = ok and no_conflict_with_schedule(schedules[forced_room], r["_start"], r["_end"])
            if ok:
                schedules[forced_room].append((r["_start"], r["_end"]))
                assignment[r["_idx"]] = forced_room
                placed.append((r["_start"], r["_end"], r["_idx"]))
                pinned_forced_ids.append(r["_idx"])
            else:
                waived_forced.append(r["_idx"])
                r["_forced"] = ""
                log_func(f"⚠️ {r['family']}/{room_type}: forced {forced_room} overlaps with another forced → waived.")

    # Step 2: MRV backtracking for remainder (serial only preferences ordering)
    def candidates_for(row, sched, cur_assign) -> List[str]:
        start, end = row["_start"], row["_end"]
        cands = [rm for rm in rooms if no_conflict_with_schedule(sched[rm], start, end)]
        fam_rooms = {cur_assign[idx] for idx in cur_assign if rows[idx]["family"] == row["family"]}
        def serial_score(rm: str) -> int:
            return -sum(1 for fr in fam_rooms if are_serial(fr, rm))
        cands.sort(key=lambda rm: (serial_score(rm), _room_sort_key(rm)))
        return cands

    def select_unassigned(unassigned, sched, cur_assign):
        best = None; best_count = 10**9
        for r in unassigned:
            cnt = len(candidates_for(r, sched, cur_assign))
            if cnt < best_count:
                best, best_count = r, cnt
                if cnt == 0:
                    return r
        return best

    solved = False
    best_partial = assignment.copy()

    def backtrack(unassigned, sched, cur_assign) -> bool:
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

    # Step 3 (last resort): try waiving exactly one pinned forced to reach full assignment
    if pinned_forced_ids:
        def conflict_degree(fid: int) -> int:
            r = next(x for x in rows if x["_idx"] == fid)
            return sum(1 for o in rows if o["_idx"] != fid and not (o["_end"] <= r["_start"] or o["_start"] >= r["_end"]))
        try_order = sorted(pinned_forced_ids, key=lambda fid: -conflict_degree(fid))

        for fid in try_order:
            sched2 = fresh_schedules()
            assign2: Dict[int, str] = {}
            for pid in pinned_forced_ids:
                if pid == fid:
                    continue
                pr = rows[pid]
                rm = assignment[pid]
                sched2[rm].append((pr["_start"], pr["_end"]))
                assign2[pid] = rm

            remainder2 = [r for r in rows if r["_idx"] not in assign2]

            solved2 = False
            best_local = assign2.copy()

            def backtrack2(unassigned2, sched_local, cur_assign_local) -> bool:
                nonlocal solved2, best_local
                if not unassigned2:
                    solved2 = True
                    return True
                row2 = select_unassigned(unassigned2, sched_local, cur_assign_local)
                c2 = candidates_for(row2, sched_local, cur_assign_local)
                if not c2:
                    return False
                for rm2 in c2:
                    sched_local[rm2].append((row2["_start"], row2["_end"]))
                    cur_assign_local[row2["_idx"]] = rm2
                    nxt2 = [r for r in unassigned2 if r["_idx"] != row2["_idx"]]
                    if backtrack2(nxt2, sched_local, cur_assign_local):
                        return True
                    sched_local[rm2].pop()
                    cur_assign_local.pop(row2["_idx"], None)
                if len(cur_assign_local) > len(best_local):
                    best_local = cur_assign_local.copy()
                return False

            if remainder2:
                backtrack2(remainder2, sched2, assign2)

            if solved2:
                return assign2, waived_forced + [fid], []

    # Still infeasible
    assigned_now = set(assignment.keys())
    all_ids = {r["_idx"] for r in rows}
    unassigned_ids = sorted(list(all_ids - assigned_now))
    log_func(f"❌ {room_type}: could not assign {len(unassigned_ids)} row(s) without breaking hard constraints.")
    return assignment, waived_forced, unassigned_ids
