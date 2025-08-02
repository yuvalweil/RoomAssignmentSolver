# logic.py
import re
from datetime import datetime as dt
from typing import Callable, Dict, List, Tuple

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


# -------------------------- Assignment Primitives ----------------------------

def _assign_rows_in_block(
    rows_df: pd.DataFrame,
    room_type: str,
    block: List[str],
    log_func: Callable[[str], None],
) -> Dict[int, str] | None:
    """
    Try to assign all rows in rows_df into the given 'block' (contiguous, same type),
    honoring forced_room when present and per-row availability.
    Returns mapping: index -> assigned_room, or None if impossible.
    """
    block = [_norm_room(r) for r in block]

    # Forced rooms per row, cleaned
    forced_map = {
        idx: _clean_opt(row.get("forced_room", ""))
        for idx, row in rows_df.iterrows()
        if _clean_opt(row.get("forced_room", ""))
    }

    # All forced rooms must be inside the block and available for the row
    used = set()
    assignment: Dict[int, str] = {}

    for idx, row in rows_df.iterrows():
        fr = forced_map.get(idx, "")
        if not fr:
            continue
        if fr not in block:
            return None  # this block cannot satisfy the forced set for this family/type
        if not is_available(room_type, fr, row["check_in"], row["check_out"]):
            return None
        assignment[idx] = fr
        used.add(fr)

    # Place remaining rows greedily within the block
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


# ------------------------------- Main API ------------------------------------

def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func: Callable[[str], None] = print,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute room assignments.

    Returns:
        assigned_df: columns = [family, room, room_type, check_in, check_out, forced_room]
        unassigned_df: original unassigned rows with their original columns
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

    processed_families: set[str] = set()

    # Families that have at least one forced row
    forced_families = set(fam.loc[fam["forced_room"] != "", "family"].unique())

    def process_family_group(family_group: pd.DataFrame, is_forced_batch: bool = False):
        family_name = str(family_group["family"].iloc[0])
        if family_name in processed_families:
            return

        log_func(f"🔍 {family_name}: start")
        processed_families.add(family_name)

        # Process per room_type to keep seriality within each type
        for rt, group in family_group.groupby("room_type"):
            rows = group.sort_values(["check_in", "check_out"]).copy()
            available = rooms_by_type.get(rt, [])

            if not available:
                for _, row in rows.iterrows():
                    unassigned_rows.append(row.to_dict())
                log_func(f"❌ {family_name}/{rt}: no rooms of this type are defined")
                continue

            # Try to place as a contiguous block first (serial preference)
            placed = False
            need = len(rows)
            for i in range(0, max(0, len(available) - need + 1)):
                block = available[i : i + need]
                assignment = _assign_rows_in_block(rows, rt, block, log_func)
                if assignment:
                    for idx, row in rows.iterrows():
                        r = assignment[idx]
                        reserve(rt, r, row["check_in"], row["check_out"])
                        assigned_rows.append(
                            {
                                "family": family_name,
                                "room": r,
                                "room_type": rt,
                                "check_in": row["check_in"],
                                "check_out": row["check_out"],
                                "forced_room": _clean_opt(row.get("forced_room", "")),
                            }
                        )
                        fr_clean = _clean_opt(row.get("forced_room", ""))
                        if fr_clean and r == fr_clean:
                            log_func(f"🏷️ {family_name}/{rt}: used forced room {r}")
                        else:
                            log_func(f"✅ {family_name}/{rt}: assigned {r}")
                    placed = True
                    break

            if placed:
                continue

            # Fallback: assign each row independently (still respect forced when possible)
            for _, row in rows.iterrows():
                target_force = _clean_opt(row.get("forced_room", "")) if is_forced_batch else ""
                assigned_room = None

                if target_force:
                    if target_force not in available:
                        log_func(f"⚠️ {family_name}/{rt}: forced room {target_force} not found in this room_type")
                    elif is_available(rt, target_force, row["check_in"], row["check_out"]):
                        assigned_room = target_force
                        log_func(f"🏷️ {family_name}/{rt}: forced room {target_force} used")
                    else:
                        log_func(
                            f"⚠️ {family_name}/{rt}: forced {target_force} unavailable for "
                            f"{row['check_in']}-{row['check_out']}"
                        )

                if assigned_room is None:
                    for r in available:
                        if is_available(rt, r, row["check_in"], row["check_out"]):
                            assigned_room = r
                            break

                if assigned_room:
                    reserve(rt, assigned_room, row["check_in"], row["check_out"])
                    assigned_rows.append(
                        {
                            "family": family_name,
                            "room": assigned_room,
                            "room_type": rt,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": _clean_opt(row.get("forced_room", "")),
                        }
                    )
                    log_func(f"✅ {family_name}/{rt}: assigned {assigned_room}")
                else:
                    unassigned_rows.append(row.to_dict())
                    log_func(f"❌ {family_name}/{rt}: could not assign row")

    # Step 1: families with at least one forced row (and process all their rows)
    for fam_name in forced_families:
        process_family_group(fam[fam["family"] == fam_name], is_forced_batch=True)

    # Step 2: the rest
    for fam_name, fam_group in fam.groupby("family"):
        if fam_name not in processed_families:
            process_family_group(fam_group, is_forced_batch=False)

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
