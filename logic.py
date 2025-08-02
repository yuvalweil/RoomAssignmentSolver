import pandas as pd
from datetime import datetime as dt

room_calendars = {}

# Use (room_type, room) as unique key
def is_available(room_type, room, check_in_str, check_out_str):
    key = (room_type, room)
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")

    if key not in room_calendars:
        room_calendars[key] = []

    for (start, end) in room_calendars[key]:
        if not (check_out <= start or check_in >= end):
            return False
    return True

def reserve(room_type, room, check_in_str, check_out_str):
    key = (room_type, room)
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")
    if key not in room_calendars:
        room_calendars[key] = []
    room_calendars[key].append((check_in, check_out))

def assign_rooms(families_df, rooms_df, log_func=None):
    global room_calendars
    room_calendars = {}

    assigned = []
    unassigned = []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()

    families_df = families_df.copy()
    families_df["forced_room"] = families_df.get("forced_room", "").fillna("").astype(str).str.strip()
    forced_rows = families_df[families_df["forced_room"] != ""]

    families_done = set()
    forced_queue = forced_rows.itertuples()

    def log(msg):
        if log_func:
            log_func(msg)

    def process_family(family_df, family):
        grouped = family_df.groupby("room_type")
        success = True

        for room_type, orders in grouped:
            orders = orders.sort_values("check_in")
            forced_rooms = orders["forced_room"].unique()
            forced_rooms = [r for r in forced_rooms if r]

            candidate_blocks = []

            if forced_rooms:
                sorted_rooms = rooms_by_type.get(room_type, [])
                for i in range(len(sorted_rooms) - len(orders) + 1):
                    block = sorted_rooms[i:i+len(orders)]
                    if forced_rooms[0] in block:
                        candidate_blocks.append(block)
                candidate_blocks = [b for b in candidate_blocks if all(
                    is_available(room_type, b[j], row["check_in"], row["check_out"])
                    for j, (_, row) in enumerate(orders.iterrows())
                )]
            else:
                candidate_blocks = []
                sorted_rooms = rooms_by_type.get(room_type, [])
                for i in range(len(sorted_rooms) - len(orders) + 1):
                    block = sorted_rooms[i:i+len(orders)]
                    if all(
                        is_available(room_type, block[j], row["check_in"], row["check_out"])
                        for j, (_, row) in enumerate(orders.iterrows())
                    ):
                        candidate_blocks.append(block)

            if candidate_blocks:
                chosen = candidate_blocks[0]
                for j, (_, row) in enumerate(orders.iterrows()):
                    reserve(room_type, chosen[j], row["check_in"], row["check_out"])
                    assigned.append({
                        "family": family,
                        "room": chosen[j],
                        "room_type": room_type,
                        "check_in": row["check_in"],
                        "check_out": row["check_out"],
                        "forced_room": row["forced_room"]
                    })
                    log(f"✅ Assigned {family} to {chosen[j]} for {room_type}")
            else:
                # Try fallback assignment
                for _, row in orders.iterrows():
                    assigned_room = None
                    for room in rooms_by_type.get(room_type, []):
                        if is_available(room_type, room, row["check_in"], row["check_out"]):
                            assigned_room = room
                            reserve(room_type, room, row["check_in"], row["check_out"])
                            assigned.append({
                                "family": family,
                                "room": room,
                                "room_type": room_type,
                                "check_in": row["check_in"],
                                "check_out": row["check_out"],
                                "forced_room": row["forced_room"]
                            })
                            log(f"✅ Assigned {family} to {room} for {room_type}")
                            break
                    if not assigned_room:
                        unassigned.append(row.to_dict())
                        success = False
        return success

    # Step 1: assign forced_room families first
    for row in forced_queue:
        family = row.full_name if "full_name" in families_df.columns else row.שם_מלא
        if family in families_done:
            continue
        fam_df = families_df[families_df["full_name"] == family] if "full_name" in families_df.columns else families_df[families_df["שם מלא"] == family]
        process_family(fam_df, family)
        families_done.add(family)

    # Step 2: assign all remaining families
    for family, group in families_df.groupby("full_name" if "full_name" in families_df.columns else "שם מלא"):
        if family in families_done:
            continue
        process_family(group, family)

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)
