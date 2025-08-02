import pandas as pd
from datetime import datetime as dt

room_calendars = {}

def is_available(room, check_in_str, check_out_str):
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")
    if room not in room_calendars:
        return True
    for (start, end) in room_calendars[room]:
        if not (check_out <= start or check_in >= end):
            return False
    return True

def reserve(room, check_in_str, check_out_str):
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")
    room_calendars.setdefault(room, []).append((check_in, check_out))

def assign_rooms(families_df, rooms_df):
    global room_calendars
    room_calendars = {}

    assigned = []
    unassigned = []
    warnings = []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()
    families_df = families_df.copy()
    families_df["forced_room"] = families_df.get("forced_room", "").fillna("")

    grouped = families_df.groupby(families_df["full_name" if "full_name" in families_df.columns else "שם מלא"])
    families = list(grouped.groups.keys())

    processed = set()

    # Prioritize families with at least one forced room
    forced_rows = families_df[families_df["forced_room"].str.strip() != ""]
    processed_families = []

    for _, forced_row in forced_rows.iterrows():
        fam = forced_row["full_name"] if "full_name" in forced_row else forced_row["שם מלא"]
        if fam in processed:
            continue
        group = grouped.get_group(fam)
        processed.add(fam)
        processed_families.append((fam, group))

    for fam in families:
        if fam not in processed:
            group = grouped.get_group(fam)
            processed_families.append((fam, group))

    for fam, group in processed_families:
        group = group.sort_values("check_in")
        for room_type, orders in group.groupby("room_type"):
            orders = orders.copy()
            assigned_rooms = []

            # Handle forced rooms first
            forced_ok = True
            for i, row in orders.iterrows():
                fr = str(row.get("forced_room", "")).strip()
                if fr:
                    if is_available(fr, row["check_in"], row["check_out"]):
                        assigned.append({
                            "family": fam,
                            "room": fr,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": fr
                        })
                        reserve(fr, row["check_in"], row["check_out"])
                        assigned_rooms.append(fr)
                    else:
                        forced_ok = False
                        unassigned.append(row.to_dict())
                        warnings.append(f"⚠️ Forced room {fr} unavailable for {fam}")
            if not forced_ok:
                continue

            remaining_orders = orders[orders["forced_room"].str.strip() == ""]

            available_rooms = [r for r in rooms_by_type.get(room_type, []) if r not in assigned_rooms]
            available_rooms = [r for r in available_rooms if all(
                is_available(r, row["check_in"], row["check_out"]) for _, row in remaining_orders.iterrows()
            )]

            found = False
            for i in range(len(available_rooms) - len(remaining_orders) + 1):
                block = available_rooms[i:i+len(remaining_orders)]
                if all(
                    is_available(block[j], row["check_in"], row["check_out"])
                    for j, (_, row) in enumerate(remaining_orders.iterrows())
                ):
                    for j, (_, row) in enumerate(remaining_orders.iterrows()):
                        assigned.append({
                            "family": fam,
                            "room": block[j],
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": ""
                        })
                        reserve(block[j], row["check_in"], row["check_out"])
                    found = True
                    break

            if not found:
                for _, row in remaining_orders.iterrows():
                    assigned_room = None
                    for room in rooms_by_type.get(room_type, []):
                        if is_available(room, row["check_in"], row["check_out"]):
                            assigned_room = room
                            reserve(room, row["check_in"], row["check_out"])
                            break
                    if assigned_room:
                        assigned.append({
                            "family": fam,
                            "room": assigned_room,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": ""
                        })
                    else:
                        unassigned.append(row.to_dict())

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)

def validate_assignments(assigned_df, rooms_df):
    hard_violations = []
    soft_violations = []

    room_usage = {}
    for idx, row in assigned_df.iterrows():
        room = row["room"]
        check_in = dt.strptime(row["check_in"], "%d/%m/%Y")
        check_out = dt.strptime(row["check_out"], "%d/%m/%Y")
        for used_in, used_out in room_usage.get(room, []):
            if not (check_out <= used_in or check_in >= used_out):
                hard_violations.append(f"Room {room} double-booked between {row['check_in']} and {row['check_out']}")
        room_usage.setdefault(room, []).append((check_in, check_out))

    fam_groups = assigned_df.groupby("family")
    for fam, group in fam_groups:
        forced = group[group["forced_room"].str.strip() != ""]
        if not forced.empty:
            for _, row in forced.iterrows():
                if row["room"] != row["forced_room"]:
                    soft_violations.append(f"{fam} was not assigned to their forced room {row['forced_room']} (got {row['room']})")

        for room_type, sub in group.groupby("room_type"):
            rooms = sorted(sub["room"])
            expected = list(rooms_df[rooms_df["room_type"] == room_type]["room"].sort_values())
            indices = [expected.index(r) for r in rooms if r in expected]
            if len(indices) >= 2 and not all(b - a == 1 for a, b in zip(indices, indices[1:])):
                soft_violations.append(f"{fam} not assigned serial rooms for type {room_type}")

    return hard_violations, soft_violations
