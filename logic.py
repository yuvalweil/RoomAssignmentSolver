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

def assign_rooms(families_df, rooms_df, log_func=print):
    global room_calendars
    room_calendars = {}
    assigned = []
    unassigned = []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()
    families_df["forced_room"] = families_df.get("forced_room", "").fillna("")

    forced_rows = families_df[families_df["forced_room"].str.strip() != ""]
    processed_families = set()

    for _, row in forced_rows.iterrows():
        family = row["full_name"] if "full_name" in row else row["שם מלא"]
        if family in processed_families:
            continue
        group = families_df[families_df["full_name" if "full_name" in families_df.columns else "שם מלא"] == family]
        log_func(f"🔒 Attempting forced assignment for {family}...")

        success = try_assign_family(group, rooms_by_type, assigned, unassigned, forced_room=row["forced_room"], log_func=log_func)
        if not success:
            log_func(f"⚠️ Could not honor forced_room {row['forced_room']} for {family}.")
        processed_families.add(family)

    for family, group in families_df.groupby("full_name" if "full_name" in families_df.columns else "שם מלא"):
        if family in processed_families:
            continue
        log_func(f"➡️ Assigning {family} (no forced room)...")
        try_assign_family(group, rooms_by_type, assigned, unassigned, forced_room=None, log_func=log_func)

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)

def try_assign_family(group, rooms_by_type, assigned, unassigned, forced_room=None, log_func=print):
    family = group["full_name"].iloc[0] if "full_name" in group else group["שם מלא"]
    group = group.sort_values(by="check_in")
    grouped_by_type = group.groupby("room_type")

    success = True

    for room_type, orders in grouped_by_type:
        available_rooms = rooms_by_type.get(room_type, [])

        # Filter forced room if specified
        if forced_room:
            if forced_room not in available_rooms:
                log_func(f"❌ Forced room {forced_room} not found in room_type {room_type}")
                success = False
                unassigned.extend(orders.to_dict(orient="records"))
                continue
            start_index = available_rooms.index(forced_room)
            candidates = available_rooms[start_index : start_index + len(orders)]
        else:
            candidates = available_rooms

        # Try to assign consecutive rooms
        found_block = False
        for i in range(len(candidates) - len(orders) + 1):
            block = candidates[i : i + len(orders)]
            if all(is_available(block[j], row["check_in"], row["check_out"]) for j, (_, row) in enumerate(orders.iterrows())):
                for j, (_, row) in enumerate(orders.iterrows()):
                    reserve(block[j], row["check_in"], row["check_out"])
                    assigned.append({
                        "family": family,
                        "room": block[j],
                        "room_type": room_type,
                        "check_in": row["check_in"],
                        "check_out": row["check_out"],
                        "forced_room": row.get("forced_room", "")
                    })
                    log_func(f"✅ Assigned {family} to {block[j]}")
                found_block = True
                break

        if not found_block:
            log_func(f"⚠️ No consecutive rooms available for {family} ({room_type})")
            # Try to assign any available rooms
            for _, row in orders.iterrows():
                assigned_room = None
                for room in available_rooms:
                    if is_available(room, row["check_in"], row["check_out"]):
                        reserve(room, row["check_in"], row["check_out"])
                        assigned_room = room
                        assigned.append({
                            "family": family,
                            "room": room,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": row.get("forced_room", "")
                        })
                        log_func(f"✅ Fallback assignment: {family} to {room}")
                        break
                if not assigned_room:
                    unassigned.append(row.to_dict())
                    log_func(f"❌ Could not assign room for {family} - {row['room_type']}")
                    success = False

    return success
