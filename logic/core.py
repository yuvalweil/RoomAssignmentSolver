from __future__ import annotations
from typing import Dict, List, Tuple
import pandas as pd

from .utils import _norm_room, _room_sort_key, _clean_opt
from .calendar_store import reserve
from .solver import assign_per_type

def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func=print,
):
    """
    Returns:
        assigned_df: [family, room, room_type, check_in, check_out, forced_room]
        unassigned_df: original rows that could not be assigned (only if infeasible)
    """
    fam = families_df.copy()
    rms = rooms_df.copy()

    # Rooms normalization
    rms["room_type"] = rms["room_type"].astype(str).str.strip()
    rms["room"] = rms["room"].astype(str).str.strip()
    rooms_by_type = (
        rms.groupby("room_type")["room"]
        .apply(lambda x: sorted(map(_norm_room, x), key=_room_sort_key))
        .to_dict()
    )

    # Families normalization
    if "family" not in fam.columns:
        if "full_name" in fam.columns:
            fam["family"] = fam["full_name"].astype(str).str.strip()
        elif "שם מלא" in fam.columns:
            fam["family"] = fam["שם מלא"].astype(str).str.strip()
        else:
            raise ValueError("Missing 'full_name' (or 'שם מלא') column in families CSV.")

    for col in ["room_type", "check_in", "check_out"]:
        if col not in fam.columns:
            raise ValueError(f"Missing '{col}' column in families CSV.")
        fam[col] = fam[col].astype(str).str.strip()

    if "forced_room" not in fam.columns:
        fam["forced_room"] = ""
    fam["forced_room"] = fam["forced_room"].fillna("").astype(str).str.strip()
    fam["forced_room"] = fam["forced_room"].apply(_clean_opt)

    assigned_rows: List[dict] = []
    unassigned_rows: List[dict] = []

    for rt, group in fam.groupby("room_type", sort=False):
        rows = group.to_dict("records")
        available = rooms_by_type.get(rt, [])
        if not available:
            # No rooms of this type exist → all rows unassigned
            for r in rows:
                unassigned_rows.append(r)
            log_func(f"❌ {rt}: no rooms of this type are defined.")
            continue

        assignment_map, waived_forced_ids, unassigned_ids = assign_per_type(rows, available, rt, log_func)

        # Build outputs; also reserve in global calendars for validation/overrides
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
                fr = _clean_opt(r.get("forced_room", ""))
                if fr and idx in waived_forced_ids:
                    log_func(f"⚠️ {r['family']}/{rt}: forced {fr} waived to enable full assignment (assigned {room_assigned}).")
                elif fr and room_assigned == fr:
                    log_func(f"🏷️ {r['family']}/{rt}: used forced room {room_assigned}")
                else:
                    log_func(f"✅ {r['family']}/{rt}: assigned {room_assigned}")
            else:
                unassigned_rows.append(r)

        if waived_forced_ids:
            log_func(f"ℹ️ {rt}: waived {len(waived_forced_ids)} forced preference(s) to assign everyone else.")
        if unassigned_ids:
            log_func(f"ℹ️ {rt}: {len(unassigned_ids)} row(s) remain unassigned — capacity/overlap infeasible.")

    return pd.DataFrame(assigned_rows), pd.DataFrame(unassigned_rows)
