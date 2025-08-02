import pandas as pd
from datetime import datetime

def is_available(bookings, check_in, check_out):
    for b in bookings:
        existing_check_in = b["check_in"]
        existing_check_out = b["check_out"]
        # If the new booking overlaps with an existing one
        if not (check_out <= existing_check_in or check_in >= existing_check_out):
            return False
    return True

def assign_rooms(families_df, rooms_df):
    rooms = {
        row["id"]: {
            "type": row["type"],
            "max_occupancy": row["max_occupancy"],
            "bookings": []  # List of {"check_in": date, "check_out": date}
        } for _, row in rooms_df.iterrows()
    }

    assignments = []
    unassigned = []

    for _, fam in families_df.iterrows():
        try:
            check_in = datetime.strptime(fam["check_in"], "%d/%m/%Y")
            check_out = datetime.strptime(fam["check_out"], "%d/%m/%Y")
        except Exception as e:
            unassigned.append(fam)
            continue

        assigned = False
        for room_id, room in rooms.items():
            if (room["type"] == fam["room_type"] and
                room["max_occupancy"] >= fam["people"] and
                is_available(room["bookings"], check_in, check_out)):

                room["bookings"].append({"check_in": check_in, "check_out": check_out})
                assignments.append({
                    "family": fam["id"],
                    "room": room_id,
                    "check_in": fam["check_in"],
                    "check_out": fam["check_out"]
                })
                assigned = True
                break

        if not assigned:
            unassigned.append(fam)

    assigned_df = pd.DataFrame(assignments)
    unassigned_df = pd.DataFrame(unassigned)

    return assigned_df, unassigned_df
