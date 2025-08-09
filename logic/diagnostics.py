# logic/diagnostics.py

from __future__ import annotations
from typing import Dict, List, Tuple, DefaultDict
import pandas as pd

from .utils import _parse_date, _norm_room, _room_sort_key, _overlaps, are_serial, DATE_FMT
from .core import assign_rooms  # (optional; not used here but handy if you extend)

def _schedules_from_df(assigned_df: pd.DataFrame):
    sched: Dict[Tuple[str, str], List[Tuple]] = {}
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

def _conflicts_on(sched, room_type: str, room: str, start, end):
    key = (str(room_type).strip(), _norm_room(room))
    out = []
    for s, e, fam in sched.get(key, []):
        if _overlaps(s, e, start, end):
            out.append((fam, s.strftime(DATE_FMT), e.strftime(DATE_FMT)))
    return out

def _rooms_by_type_from_df(rooms_df: pd.DataFrame):
    rdf = rooms_df.copy()
    rdf["room_type"] = rdf["room_type"].astype(str).str.strip()
    rdf["room"] = rdf["room"].astype(str).str.strip()
    return (
        rdf.groupby("room_type")["room"]
        .apply(lambda x: sorted(map(_norm_room, x), key=_room_sort_key))
        .to_dict()
    )

def _perfect_matching(choices: Dict[int, List[str]]) -> bool:
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
    rooms_df: pd.DataFrame
) -> pd.DataFrame:
    results: List[dict] = []
    if assigned_df is None or assigned_df.empty:
        return pd.DataFrame(results)

    sched = _schedules_from_df(assigned_df)
    rooms_by_type = _rooms_by_type_from_df(rooms_df)

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

    # A) Forced not met
    forced_rows = fam[fam["forced_room"].astype(str).str.strip() != ""]
    for _, src in forced_rows.iterrows():
        fml = str(src["family"]).strip()
        rt = str(src["room_type"]).strip()
        ci = str(src["check_in"]).strip()
        co = str(src["check_out"]).strip()
        fr = _norm_room(src["forced_room"])

        mask = (
            (assigned_df["family"].astype(str).str.strip() == fml) &
            (assigned_df["room_type"].astype(str).str.strip() == rt) &
            (assigned_df["check_in"].astype(str).str.strip() == ci) &
            (assigned_df["check_out"].astype(str).str.strip() == co)
        )
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
            continue

        in_type = fr in rooms_by_type.get(rt, [])
        start = _parse_date(ci); end = _parse_date(co)
        if not in_type:
            reason = f"forced room {fr} does not exist under room_type '{rt}'."
            blockers = ""
        else:
            confs = _conflicts_on(sched, rt, fr, start, end)
            if confs:
                blockers = "; ".join([f"{c[0]} ({c[1]}–{c[2]})" for c in confs[:4]])
                reason = "forced room was occupied during the interval."
            else:
                reason = "solver relaxed forced to achieve full assignment (using it blocked others)."
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

    # B) Non-serial
    by_family_type: DefaultDict[Tuple[str, str], List[dict]] = {}  # type: ignore
    for _, row in assigned_df.iterrows():
        key = (str(row["family"]).strip(), str(row["room_type"]).strip())
        by_family_type.setdefault(key, []).append({
            "room": _norm_room(row["room"]),
            "check_in": str(row["check_in"]).strip(),
            "check_out": str(row["check_out"]).strip(),
        })

    for (fml, rt), rows in by_family_type.items():
        if len(rows) <= 1:
            continue
        rooms_now = [r["room"] for r in rows]
        rooms_sorted = sorted(rooms_now, key=_room_sort_key)

        serial_ok = True
        for i in range(len(rooms_sorted) - 1):
            if not are_serial(rooms_sorted[i], rooms_sorted[i + 1]):
                serial_ok = False
                break
        if serial_ok:
            continue

        all_rooms = rooms_by_type.get(rt, [])
        k = len(rows)
        feasible_block: List[str] = []
        best_block: List[str] = []
        best_avail = -1

        # schedules excluding this family's own reservations
        sched_excl = {}
        for key, intervals in sched.items():
            rt_key, rm_key = key
            if rt_key != rt:
                sched_excl[key] = intervals[:]
                continue
            kept = [(s, e, famname) for (s, e, famname) in intervals if famname != fml]
            if kept:
                sched_excl[key] = kept

        rows_with_dt = [{
            "idx": i,
            "start": _parse_date(r["check_in"]),
            "end": _parse_date(r["check_out"]),
        } for i, r in enumerate(rows)]

        for i in range(max(0, len(all_rooms) - k + 1)):
            block = list(map(_norm_room, all_rooms[i:i+k]))
            choices = {}
            avail_pairs = 0
            for rinfo in rows_with_dt:
                opts = []
                for rm in block:
                    key = (rt, rm)
                    ok = True
                    for s, e, _ in sched_excl.get(key, []):
                        if _overlaps(s, e, rinfo["start"], rinfo["end"]):
                            ok = False; break
                    if ok:
                        opts.append(rm)
                choices[rinfo["idx"]] = opts
                avail_pairs += len(opts)

            if all(choices[j] for j in choices) and _perfect_matching(choices):
                feasible_block = block
                break

            if avail_pairs > best_avail:
                best_avail = avail_pairs
                best_block = block

        if feasible_block:
            reason = "serial block was feasible without moving other families; solver chose non-serial."
            blockers = ""
        else:
            notes = []
            for rm in best_block:
                key = (rt, rm)
                for s, e, famname in sched_excl.get(key, []):
                    notes.append(f"{rm} blocked by {famname} ({s.strftime(DATE_FMT)}–{e.strftime(DATE_FMT)})")
            blockers = "; ".join(notes[:6])
            reason = f"no contiguous serial block of size {k} was free given other families."

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

    # C) New multi–room-type soft constraints
    def to_int(r):
        try:
            return int(str(r))
        except Exception:
            return None

    for fam, grp in assigned_df.groupby("family"):
        types = [str(t).strip() for t in grp["room_type"]]
        room_map = {
            rt: to_int(grp.loc[grp["room_type"] == rt, "room"].iat[0])
            for rt in types
        }

        # Rule 1: 'שטח' + 'זוגי'
        if "שטח" in types and "זוגי" in types:
            # זוגי → room 1
            r_zug = room_map.get("זוגי")
            if r_zug != 1:
                results.append({
                    "violation": "mixed_שטח_זוגי",
                    "family": fam, "room_type": "זוגי",
                    "check_in": "", "check_out": "",
                    "forced_room": "", "assigned_room": r_zug,
                    "assigned_rooms": "",
                    "feasible_serial_block": "",
                    "reason": f"זוגי must be in room 1, but is in {r_zug}",
                    "blockers": "",
                })
            # שטח → 1–5
            r_shatach = room_map.get("שטח")
            if r_shatach is None or not (1 <= r_shatach <= 5):
                results.append({
                    "violation": "mixed_שטח_זוגי",
                    "family": fam, "room_type": "שטח",
                    "check_in": "", "check_out": "",
                    "forced_room": "", "assigned_room": r_shatach,
                    "assigned_rooms": "",
                    "feasible_serial_block": "",
                    "reason": f"שטח must be in rooms 1–5, but is in {r_shatach}",
                    "blockers": "",
                })

        # Rule 2: 'שטח' + ('קבוצתי' or 'סוכה')
        if "שטח" in types and any(x in types for x in ["קבוצתי", "סוכה"]):
            r_shatach = room_map.get("שטח")
            if r_shatach is None or not (4 <= r_shatach <= 7):
                results.append({
                    "violation": "mixed_שטח_קבוצתי_סוכה",
                    "family": fam, "room_type": "שטח",
                    "check_in": "", "check_out": "",
                    "forced_room": "", "assigned_room": r_shatach,
                    "assigned_rooms": "",
                    "feasible_serial_block": "",
                    "reason": f"שטח with קבוצתי/סוכה must be in rooms 4–7, but is in {r_shatach}",
                    "blockers": "",
                })
            for grp_type in ("קבוצתי", "סוכה"):
                if grp_type in types:
                    r_grp = room_map.get(grp_type)
                    if r_grp is None or not (1 <= r_grp <= 2):
                        results.append({
                            "violation": "mixed_שטח_קבוצתי_סוכה",
                            "family": fam, "room_type": grp_type,
                            "check_in": "", "check_out": "",
                            "forced_room": "", "assigned_room": r_grp,
                            "assigned_rooms": "",
                            "feasible_serial_block": "",
                            "reason": f"{grp_type} must be in rooms 1–2 when with שטח, but is in {r_grp}",
                            "blockers": "",
                        })

        # Rule 3: 'משפחתי' + ('בקתה','קבוצתי','סוכה')
        if "משפחתי" in types and any(x in types for x in ["בקתה", "קבוצתי", "סוכה"]):
            r_mishpa = room_map.get("משפחתי")
            if r_mishpa is None or r_mishpa not in {4, 5, 6, 8}:
                results.append({
                    "violation": "mixed_משפחתי_אחר",
                    "family": fam, "room_type": "משפחתי",
                    "check_in": "", "check_out": "",
                    "forced_room": "", "assigned_room": r_mishpa,
                    "assigned_rooms": "",
                    "feasible_serial_block": "",
                    "reason": f"משפחתי must be in rooms 4,5,6,8 when with בקתה/קבוצתי/סוכה, but is in {r_mishpa}",
                    "blockers": "",
                })

    return pd.DataFrame(results)
