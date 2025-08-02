import pandas as pd
import re
from datetime import datetime as dt

# Calendar is keyed by (room_type, room_id) to avoid collisions across types
room_calendars = {}

DATE_FMT = "%d/%m/%Y"

def _parse_date(s: str):
    return dt.strptime(str(s).strip(), DATE_FMT)

def _norm_room(x):
    return str(x).strip()

def _room_sort_key(r):
    s = _norm_room(r)
    m = re.search(r"\d+", s)
    return (int(m.group()) if m else float("inf"), s)

def _overlaps(a_start, a_end, b_start, b_end):
    # [start, end) convention: checkout equals next checkin is OK
    return not (a_end <= b_start or a_start >= b_end)

def is_available(room_type, room, check_in_str, check_out_str):
    """Check availability for (room_type, room)."""
    key = (room_type, _norm_room(room))
    check_in = _parse_date(check_in_str)
    check_out = _parse_date(check_out_str)

    if key not in room_calendars:
        room_calendars[key] = []

    for (start, end) in room_calendars[key]:
        if _overlaps(check_in, check_out, start, end):
            return False
    return True

def reserve(room_type, room, check_in_str, check_out_str):
    key = (room_type, _norm_room(room))
    check_in = _parse_date(check_in_str)
    check_out = _parse_date(check_out_str)
    if key not in room_calendars:
        room_calendars[key] = []
    room_calendars[key].append((check_in, check_out))

def _assign_rows_in_block(rows_df, room_type, block, log_func):
    """
    Try assign all rows in rows_df into the given 'block' of room ids (same type),
    honoring forced_room when present. Greedy but respects availability per row.
    Returns mapping: index -> assigned_room or None if impossible.
    """
    # Normalize
    block = [_norm_room(r) for r in block]
    # Per-row forced rooms
    forced_map = {
        idx: _norm_room(str(row.get("forced_room", "")).strip())
        for idx, row in rows_df.iterrows()
        if str(row.get("forced_room", "")).strip()
    }
    # First, ensure all forced rooms are inside the block and available
    used = set()
    assignment = {}

    # Place forced rows first
    for idx, row in rows_df.iterrows():
        fr = forced_map.get(idx, "")
        if fr:
            if fr not in block:
                return None  # this block cannot satisfy the forced set
            if not is_available(room_type, fr, row["check_in"], row["check_out"]):
                return None
            assignment[idx] = fr
            used.add(fr)

    # Place remaining rows greedily in any free room from the block
    for idx, row in rows_df.iterrows():
        if idx in assignment:
            continue
        placed = False
        for r in block:
            if r in used:
                continue
            if is_available(room_type, r, row["check_in"], row["check_out"]):
                assignment[idx] = r
                used.add(r)
                placed = True
                break
        if not placed:
            return None

    return assignment

def assign_rooms(families_df, rooms_df, log_func=print):
    """
    Returns: assigned_df, unassigned_df
    assigned_df columns: family, room, room_type, check_in, check_out, forced_room
    """
    global room_calendars
    room_calendars = {}

    # Defensive copies and normalization
    families_df = families_df.copy()
    rooms_df = rooms_df.copy()

    # Normalize rooms table
    rooms_df["room_type"] = rooms_df["room_type"].astype(str).str.strip()
    rooms_df["room"] = rooms_df["room"].astype(str).str.strip()
    rooms_by_type = (
        rooms_df.groupby("room_type")["room"]
        .apply(lambda x: sorted(map(_norm_room, x), key=_room_sort_key))
        .to_dict()
    )

    # Normalize families table
    # family name can be in English or Hebrew header
    if "full_name" in families_df.columns:
        families_df["family"] = families_df["full_name"].astype(str).str.strip()
    elif "שם מלא" in families_df.columns:
        families_df["family"] = families_df["שם מלא"].astype(str).str.strip()
    else:
        raise ValueError("Missing 'full_name' (or 'שם מלא') column in families CSV.")

    # Normalize and ensure presence of fields
    for col in ["room_type", "check_in", "check_out"]:
        if col not in families_df.columns:
            raise ValueError(f"Missing '{col}' column in families CSV.")
        families_df[col] = families_df[col].astype(str).str.strip()

    if "forced_room" not in families_df.columns:
        families_df["forced_room"] = ""
    families_df["forced_room"] = families_df["forced_room"].astype(str).fillna("").str.strip()

    assigned = []
    unassigned = []

    processed_families = set()
    forced_rows = families_df[
        families_df["forced_room"].astype(str).str.strip() != ""
    ]

    def process_family_group(family_group, is_forced=False):
        family_name = family_group["family"].iloc[0]
        if family_name in processed_families:
            return

        log_func(f"🔍 {family_name}: start")
        processed_families.add(family_name)

        # process per room_type to honor type constraints and serial placement within type
        for room_type, group in family_group.groupby("room_type"):
            rows = group.sort_values("check_in")  # stable order
            available_rooms = rooms_by_type.get(room_type, [])

            if not available_rooms:
                for _, row in rows.iterrows():
                    unassigned.append(row.to_dict())
                log_func(f"❌ {family_name}/{room_type}: no rooms of this type are defined")
                continue

            # Try to find a contiguous block (by sorted index) that can fit all rows, honoring forced rooms
            placed = False
            for i in range(len(available_rooms) - len(rows) + 1):
                block = available_rooms[i : i + len(rows)]
                assignment = _assign_rows_in_block(rows, room_type, block, log_func)
                if assignment:
                    # Reserve and record
                    for idx, row in rows.iterrows():
                        r = assignment[idx]
                        reserve(room_type, r, row["check_in"], row["check_out"])
                        assigned.append(
                            {
                                "family": family_name,
                                "room": r,
                                "room_type": room_type,
                                "check_in": row["check_in"],
                                "check_out": row["check_out"],
                                "forced_room": row.get("forced_room", ""),
                            }
                        )
                        if str(row.get("forced_room", "")).strip() and r == str(row.get("forced_room")).strip():
                            log_func(f"🏷️ {family_name}/{room_type}: used forced room {r}")
                        else:
                            log_func(f"✅ {family_name}/{room_type}: assigned {r}")
                    placed = True
                    break

            if placed:
                continue

            # Fallback: assign each row individually
            for _, row in rows.iterrows():
                target_room = str(row.get("forced_room", "")).strip() if is_forced else ""
                assigned_room = None

                # If a forced room is specified, try it first (but only if it belongs to this type)
                if target_room:
                    if target_room not in available_rooms:
                        log_func(f"⚠️ {family_name}/{room_type}: forced room {target_room} doesn't exist in this type")
                    elif is_available(room_type, target_room, row["check_in"], row["check_out"]):
                        assigned_room = target_room
                        log_func(f"🏷️ {family_name}/{room_type}: forced room {target_room} used")
                    else:
                        log_func(f"⚠️ {family_name}/{room_type}: forced room {target_room} unavailable for {row['check_in']}-{row['check_out']}")

                # Otherwise use any available room
                if assigned_room is None:
                    for r in available_rooms:
                        if is_available(room_type, r, row["check_in"], row["check_out"]):
                            assigned_room = r
                            break

                if assigned_room:
                    reserve(room_type, assigned_room, row["check_in"], row["check_out"])
                    assigned.append(
                        {
                            "family": family_name,
                            "room": assigned_room,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": row.get("forced_room", ""),
                        }
                    )
                    log_func(f"✅ {family_name}/{room_type}: assigned {assigned_room}")
                else:
                    unassigned.append(row.to_dict())
                    log_func(f"❌ {family_name}/{room_type}: could not assign row")

    # Step 1: families that have at least one forced room
    for _, row in forced_rows.iterrows():
        family_name = row["family"]
        family_group = families_df[families_df["family"] == family_name]
        process_family_group(family_group, is_forced=True)

    # Step 2: remaining families
    for family_name, family_group in families_df.groupby("family"):
        if family_name not in processed_families:
            process_family_group(family_group, is_forced=False)

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)

def are_serial(r1, r2):
    n1 = re.findall(r"\d+", _norm_room(r1))
    n2 = re.findall(r"\d+", _norm_room(r2))
    if n1 and n2:
        return abs(int(n1[0]) - int(n2[0])) == 1
    return False

def validate_constraints(assigned_df):
    """
    Returns:
      hard_ok (bool),
      soft_violations (list[str])
    """
    if assigned_df is None or assigned_df.empty:
        return True, []

    # Normalize
    df = assigned_df.copy()
    df["room"] = df["room"].astype(str).str.strip()
    df["room_type"] = df["room_type"].astype(str).str.strip()

    # Hard: no overlaps for the same (room_type, room)
    hard_ok = True
    for (rt, r), grp in df.groupby(["room_type", "room"]):
        intervals = []
        for _, row in grp.iterrows():
            start = _parse_date(row["check_in"])
            end = _parse_date(row["check_out"])
            intervals.append((start, end))
        intervals.sort()
        for i in range(1, len(intervals)):
            if _overlaps(intervals[i - 1][0], intervals[i - 1][1], intervals[i][0], intervals[i][1]):
                hard_ok = False
                break
        if not hard_ok:
            break

    # Soft: serial rooms per family within each room_type; and forced rooms honored
    soft_violations = []
    for family, fam_grp in df.groupby("family"):
        for rt, rt_grp in fam_grp.groupby("room_type"):
            rooms = list(rt_grp["room"])
            rooms_sorted = sorted(rooms, key=_room_sort_key)
            if len(rooms_sorted) > 1:
                ok = True
                for i in range(len(rooms_sorted) - 1):
                    if not are_serial(rooms_sorted[i], rooms_sorted[i + 1]):
                        ok = False
                        break
                if not ok:
                    soft_violations.append(f"{family}/{rt}: rooms not in serial order ({', '.join(rooms_sorted)}).")

        for _, row in fam_grp.iterrows():
            forced = str(row.get("forced_room", "")).strip()
            if forced and row["room"] != forced:
                soft_violations.append(f"{family}: forced {forced} not met (got {row['room']}).")

    return hard_ok, soft_violations

def rebuild_calendar_from_assignments(assigned_df):
    """Rebuild internal calendars from an assigned table (for manual edits)."""
    global room_calendars
    room_calendars = {}
    if assigned_df is None or assigned_df.empty:
        return
    for _, row in assigned_df.iterrows():
        reserve(row["room_type"], row["room"], row["check_in"], row["check_out"])
