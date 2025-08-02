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

    # If available, reserve it
    room_calendars[room].append((check_in, check_out))
    return True

# Main assignment function
def assign_rooms(families_df, rooms_df):
    assigned = []
    unassigned = []

    # Map: room_type -> list of room names
    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(list).to_dict()

    for _, row in families_df.iterrows():
        # Get info from row
        family = row.get("שם מלא") or row.get("full_name") or row.get("family")
        check_in = row["check_in"]
        check_out = row["check_out"]
        room_type = row.get("room_type")
        if not room_type:
            raise ValueError(f"Missing 'room_type' in row: {row.to_dict()}")

        assigned_room = None

        for room in rooms_by_type.get(room_type, []):
            if is_available(room, check_in, check_out):
                assigned_room = room
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

    assigned_df = pd.DataFrame(assigned)
    unassigned_df = pd.DataFrame(unassigned)
    return assigned_df, unassigned_df
