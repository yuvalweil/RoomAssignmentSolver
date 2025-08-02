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
    if room not in room_calendars:
        room_calendars[room] = []
    room_calendars[room].append((check_in, check_out))

def assign_rooms(families_df, rooms_df, log_func=None):
    global room_calendars
    room_calendars = {}

    assigned = []
    unassigned = []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()
    family_groups = families_df.groupby(families_df["full_name" if "full_name" in families_df.columns else "שם מלא"])

    forced_families = families_df[families_df["forced_room"].notna()]
    forced_family_names = forced_families["full_name"].unique().tolist()

    all_processed = set()

    def process_group(family, group):
        nonlocal assigned, unassigned
        if log_func: log_func(f"🔍 Processing {family}")
        for room_type, orders in group.groupby("room_type"):
            available_rooms = [r for r in rooms_by_type.get(room_type, []) if all(
                is_available(r, row["check_in"], row["check_out"]) for _, row in orders.iterrows()
            )]
            found = False
            for i in range(len(available_rooms) - len(orders) + 1):
                block = available_rooms[i:i+len(orders)]
                if all(is_available(block[j], row["check_in"], row["check_out"]) for j, (_, row) in enumerate(orders.iterrows())):
                    for j, (_, row) in enumerate(orders.iterrows()):
                        reserve(block[j], row["check_in"], row["check_out"])
                        assigned.append({
                            "family": family,
                            "room": block[j],
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": row.get("forced_room", None)
                        })
                        if log_func: log_func(f"✅ Assigned {family} to {block[j]}")
                    found = True
                    break
            if not found:
                for _, row in orders.iterrows():
                    assigned_room = None
                    if pd.notna(row.get("forced_room")):
                        fr = row["forced_room"]
                        if is_available(fr, row["check_in"], row["check_out"]):
                            reserve(fr, row["check_in"], row["check_out"])
                            assigned_room = fr
                            if log_func: log_func(f"✅ Forced room {fr} assigned to {family}")
                        else:
                            if log_func: log_func(f"❌ Forced room {fr} NOT available for {family}")
                    else:
                        for room in rooms_by_type.get(room_type, []):
                            if is_available(room, row["check_in"], row["check_out"]):
                                reserve(room, row["check_in"], row["check_out"])
                                assigned_room = room
                                break
                    if assigned_room:
                        assigned.append({
                            "family": family,
                            "room": assigned_room,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": row.get("forced_room", None)
                        })
                        if log_func: log_func(f"✅ Assigned {family} to {assigned_room}")
                    else:
                        unassigned.append(row.to_dict())
                        if log_func: log_func(f"❌ Could not assign {family} for {room_type} on {row['check_in']}")

    for fr_name in forced_family_names:
        if fr_name in all_processed:
            continue
        group = family_groups.get_group(fr_name)
        process_group(fr_name, group)
        all_processed.add(fr_name)

    for family, group in family_groups:
        if family in all_processed:
            continue
        process_group(family, group)

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)
