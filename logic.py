import pandas as pd
from datetime import datetime as dt

room_calendars = {}

def is_available(room, check_in_str, check_out_str):
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")
    if room not in room_calendars:
        room_calendars[room] = []
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

def assign_rooms(families_df, rooms_df):
    global room_calendars
    room_calendars = {}

    assigned = []
    unassigned = []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()
    name_col = "full_name" if "full_name" in families_df.columns else "שם מלא"

    families_df = families_df.copy()
    families_df["forced_room"] = families_df.get("forced_room", pd.Series([None]*len(families_df)))

    # 1️⃣ Assign all forced_room orders first (priority)
    forced_df = families_df[families_df["forced_room"].notnull()]
    for _, row in forced_df.iterrows():
        room_type = row["room_type"]
        forced_room = row["forced_room"]
        check_in = row["check_in"]
        check_out = row["check_out"]
        family = row[name_col]

        if forced_room in rooms_by_type.get(room_type, []) and is_available(forced_room, check_in, check_out):
            assigned.append({
                "family": family,
                "room": forced_room,
                "room_type": room_type,
                "check_in": check_in,
                "check_out": check_out
            })
            reserve(forced_room, check_in, check_out)
        else:
            unassigned.append(row.to_dict())

    # 2️⃣ Now assign the rest of the orders normally
    remaining_df = families_df[families_df["forced_room"].isnull()]
    family_groups = remaining_df.groupby(remaining_df[name_col])

    for family, group in family_groups:
        group = group.sort_values(by="check_in")

        for room_type, orders in group.groupby("room_type"):
            orders = orders.copy()

            available_rooms = [r for r in rooms_by_type.get(room_type, []) if all(
                is_available(r, row["check_in"], row["check_out"]) for _, row in orders.iterrows()
            )]

            found = False
            for i in range(len(available_rooms) - len(orders) + 1):
                block = available_rooms[i:i+len(orders)]
                if all(
                    is_available(block[j], row["check_in"], row["check_out"])
                    for j, (_, row) in enumerate(orders.iterrows())
                ):
                    for j, (_, row) in enumerate(orders.iterrows()):
                        check_in = row["check_in"]
                        check_out = row["check_out"]
                        assigned.append({
                            "family": family,
                            "room": block[j],
                            "room_type": room_type,
                            "check_in": check_in,
                            "check_out": check_out
                        })
                        reserve(block[j], check_in, check_out)
                    found = True
                    break

            if not found:
                for _, row in orders.iterrows():
                    check_in = row["check_in"]
                    check_out = row["check_out"]
                    assigned_room = None
                    for room in rooms_by_type.get(room_type, []):
                        if is_available(room, check_in, check_out):
                            assigned_room = room
                            reserve(room, check_in, check_out)
                            break
                    if assigned_room:
                        assigned.append({
                            "family": family,
                            "room": assigned_room,
                            "room_type": room_type,
                            "check_in": check_in,
                            "check_out": check_out
                        })
                    else:
                        unassigned.append(row.to_dict())

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)
