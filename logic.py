import pandas as pd
from datetime import datetime

def is_available(bookings, check_in, check_out):
    for b in bookings:
        if not (check_out <= b["check_in"] or check_in >= b["check_out"]):
            return False
    return True

def assign_rooms(families_df, rooms_df):
    rooms = {
        row["id"]: {
            "type": row["type"],
            "max_occupancy": row["max_occupancy"]
        } for _, row in rooms_df.iterrows()
    }

    assigned_rooms = set()
    assignments = []

    for _, fam in families_df.iterrows():
        # Parse dates in dd/mm/yyyy format
        check_in = datetime.strptime(fam["check_in"], "%d/%m/%Y")
        check_out = datetime.strptime(fam["check_out"], "%d/%m/%Y")

        for room_id, room in rooms.items():
            if (room_id not in assigned_rooms and
                room["type"] == fam["room_type"] and
                room["max_occupancy"] >= fam["people"]):
                
                assignments.append({"family": fam["id"], "room": room_id})
                assigned_rooms.add(room_id)
                break

    return pd.DataFrame(assignments)
