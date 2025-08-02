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
        # Overlapping range
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
    room_calendars = {}  # ✅ Reset availability state before every run

    assigned = []
    unassigned = []

    # Map: room_type -> list of room names (sorted)
    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()

    # Group family orders by name
    family_groups = families_df.groupby(families_df["full_name" if "full_name" in families_df.columns else "שם מלא"])

    for family, group in family_groups:
        group = group.sort_values(by="check_in")  # Optional: sort by date
        for room_type, orders in group.groupby("room_type"):
            available_rooms = [r for r in rooms_by_type.get(room_type, []) if all(
                is_available(r, row["check_in"], row["check_out"]) for _, row in orders.iterrows()
            )]

            found = False
            # Try consecutive blocks
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

            # Fallback to any available rooms if no consecutive block found
            if not found:
                assigned_rooms = []
                for _, row in orders.iterrows():
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

    assigned_df = pd.DataFrame(assigned)
    unassigned_df = pd.DataFrame(unassigned)
    return assigned_df, unassigned_df
