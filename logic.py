import pandas as pd
from datetime import datetime as dt

# Tracks booked date ranges per room
room_calendars = {}

# Check if a room is available for the requested date range
def is_available(room, check_in_str, check_out_str):
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")

    if room not in room_calendars:
        room_calendars[room] = []

    for (start, end) in room_calendars[room]:
        if not (check_out <= start or check_in >= end):
            return False
    return True

# Reserve a room for a specific time range
def reserve(room, check_in_str, check_out_str):
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")
    if room not in room_calendars:
        room_calendars[room] = []
    room_calendars[room].append((check_in, check_out))

# Main assignment function
def assign_rooms(families_df, rooms_df):
    global room_calendars
    room_calendars = {}  # Reset availability before each run

    assigned = []
    unassigned = []

    # Map room_type -> list of rooms
    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()

    # Group family orders by full name
    name_col = "full_name" if "full_name" in families_df.columns else "שם מלא"
    family_groups = families_df.groupby(families_df[name_col])

    for family, group in family_groups:
        group = group.sort_values(by="check_in")

        for room_type, orders in group.groupby("room_type"):
            orders = orders.copy()

            # 1️⃣ Handle forced_room first
            forced_orders = orders[orders.get("forced_room").notnull()]
            regular_orders = orders[orders.get("forced_room").isnull()]

            for _, row in forced_orders.iterrows():
                check_in = row["check_in"]
                check_out = row["check_out"]
                forced_room = row["forced_room"]

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

            if regular_orders.empty:
                continue

            # 2️⃣ Handle regular orders (try consecutive rooms first)
            available_rooms = [r for r in rooms_by_type.get(room_type, []) if all(
                is_available(r, row["check_in"], row["check_out"]) for _, row in regular_orders.iterrows()
            )]

            found = False
            for i in range(len(available_rooms) - len(regular_orders) + 1):
                block = available_rooms[i:i+len(regular_orders)]
                if all(
                    is_available(block[j], row["check_in"], row["check_out"])
                    for j, (_, row) in enumerate(regular_orders.iterrows())
                ):
                    for j, (_, row) in enumerate(regular_orders.iterrows()):
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

            # 3️⃣ Fallback to any available room
            if not found:
                for _, row in regular_orders.iterrows():
                    assigned_room = None
                    for room in rooms_by_type.get(room_type, []):
                        if is_available(room, row["check_in"], row["check_out"]):
                            assigned_room = room
                            reserve(room, row["check_in"], row["check_out"])
                            break
                    if assigned_room:
                        assigned.append({
                            "family": family,
                            "room": assigned_room,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"]
                        })
                    else:
                        unassigned.append(row.to_dict())

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)
