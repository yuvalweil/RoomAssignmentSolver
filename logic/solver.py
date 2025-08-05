# logic/solver.py

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd
from ortools.sat.python import cp_model

# -----------------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------------
@dataclass
class Booking:
    idx: int
    family: str
    room_type: str
    check_in: pd.Timestamp
    check_out: pd.Timestamp
    forced_list: List[int]

@dataclass
class Room:
    idx: int
    label: str
    room_type: str

# -----------------------------------------------------------------------------
# Helpers for שטח constraints
# -----------------------------------------------------------------------------
def extract_num(label: str) -> Optional[int]:
    m = re.search(r"(\d+)", label)
    return int(m.group(1)) if m else None

def is_field_type(rt: str) -> bool:
    s = (rt or "").strip().lower()
    return "שטח" in s or "field" in s or "camp" in s or "pitch" in s

# Penalty settings
PEN_FORCED_VIOL   = 20
PEN_ROOM15        = 5
PEN_FIELD_SINGLE  = 50
PEN_CLUSTER_SPLIT = 30

PROHIBITED_SINGLE = {2, 3, 4, 5, 15}
FIELD_CLUSTERS    = [{2, 3}, {9, 10, 11}, {10, 11}, {13, 14}, {16, 18}]

# -----------------------------------------------------------------------------
# Main entry point – replaces backtracking
# -----------------------------------------------------------------------------
def assign_rooms(
    families_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    log_func: Optional[Callable[[str], None]] = None,
    *,
    time_limit_sec: float = 20.0,
    **kwargs
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Uses OR-Tools CP-SAT to assign rooms.
    """

    # 1) Preprocess bookings
    fam = families_df.copy()
    fam["ci"] = pd.to_datetime(fam["check_in"], dayfirst=True)
    fam["co"] = pd.to_datetime(fam["check_out"], dayfirst=True)
    fam["forced_list"] = fam["forced_room"].fillna("").astype(str).apply(
        lambda s: [int(t) for t in s.split(",") if t.strip().isdigit()]
    )

    bookings: List[Booking] = [
        Booking(idx=i,
                family=str(r.get("family","")),
                room_type=str(r.get("room_type","")),
                check_in=r["ci"],
                check_out=r["co"],
                forced_list=r["forced_list"])
        for i, r in fam.iterrows()
    ]

    # 2) Preprocess rooms
    rooms: List[Room] = [
        Room(idx=j,
             label=str(r.get("room","")),
             room_type=str(r.get("room_type","")))
        for j, r in rooms_df.iterrows()
    ]

    # 3) Build model
    model = cp_model.CpModel()
    x: Dict[Tuple[int,int], cp_model.IntVar] = {}
    for b in bookings:
        for rm in rooms:
            if b.room_type != rm.room_type:
                continue
            x[b.idx, rm.idx] = model.NewBoolVar(f"x_b{b.idx}_r{rm.idx}")

    # 4) Hard constraints
    # 4a) Each booking exactly one room
    for b in bookings:
        model.Add(sum(x[b.idx, rm.idx] for rm in rooms
                      if (b.idx, rm.idx) in x) == 1)

    # 4b) No overlapping bookings share a room
    for rm in rooms:
        # gather bookings eligible for rm
        bs = [b for b in bookings if (b.idx, rm.idx) in x]
        for i in range(len(bs)):
            for j in range(i+1, len(bs)):
                b1, b2 = bs[i], bs[j]
                if b1.check_in < b2.check_out and b2.check_in < b1.check_out:
                    model.Add(x[b1.idx, rm.idx] + x[b2.idx, rm.idx] <= 1)

    # 5) Build objective penalties
    obj_terms = []
    for b in bookings:
        # identify peers for cluster-split logic
        peers = [p.idx for p in bookings
                 if p.family == b.family and
                    p.check_in == b.check_in and
                    p.check_out == b.check_out]
        is_single = len(peers) == 1
        is_field  = is_field_type(b.room_type)

        for rm in rooms:
            key = (b.idx, rm.idx)
            if key not in x:
                continue
            var = x[key]
            num = extract_num(rm.label) or -1

            # forced-room violation
            if b.forced_list and num not in b.forced_list:
                obj_terms.append((PEN_FORCED_VIOL, var))

            # room 15 preference
            if num == 15:
                obj_terms.append((PEN_ROOM15, var))

            # שטח single-family prohibition
            if is_field and is_single and num in PROHIBITED_SINGLE:
                obj_terms.append((PEN_FIELD_SINGLE, var))

            # cluster-split for multi bookings
            if is_field and not is_single:
                for cl in FIELD_CLUSTERS:
                    if num in cl:
                        # penalize pairing with any peer outside cluster
                        for pidx in peers:
                            for rm2 in rooms:
                                num2 = extract_num(rm2.label) or -1
                                if num2 not in cl and (pidx, rm2.idx) in x:
                                    obj_terms.append((PEN_CLUSTER_SPLIT,
                                                      var * x[pidx, rm2.idx]))

    model.Minimize(sum(coeff * var for coeff, var in obj_terms))

    # 6) Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_sec
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    # 7) Collect results
    assigned, unassigned = [], []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for b in bookings:
            chosen = next((rm.label for rm in rooms
                           if (b.idx, rm.idx) in x and solver.Value(x[b.idx, rm.idx])==1),
                          "")
            rec = fam.loc[b.idx].to_dict()
            rec["room"] = chosen
            if chosen:
                assigned.append(rec)
            else:
                unassigned.append(rec)
    else:
        # if no solution, mark all unassigned
        unassigned = fam.to_dict("records")

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)
