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
    room_calendars = {}

    assigned = []
    unassigned = []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()

    if "full_name" in families_df.columns:
        name_col = "full_name"
    elif "שם מלא" in families_df.columns:
        name_col = "שם מלא"
    else:
        raise ValueError("Missing full name column")

    family_groups = families_df.groupby(families_df[name_col])

    # STEP 1: Assign forced_room + rest of that family
    processed_families = set()
    forced_rows = families_df.dropna(subset=["forced_room"])
    forced_families = forced_rows[name_col].unique()

    def process_family(family, group):
        group = group.sort_values(by="check_in")
        for room_type, orders in group.groupby("room_type"):
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
                        assigned.append({
                            "family": family,
                            "room": block[j],
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": row.get("forced_room", None)
                        })
                        reserve(block[j], row["check_in"], row["check_out"])
                    found = True
                    break

            if not found:
                for _, row in orders.iterrows():
                    assigned_room = None

                    # First try forced_room if applicable
                    if pd.notna(row.get("forced_room")):
                        forced = row["forced_room"]
                        if is_available(forced, row["check_in"], row["check_out"]):
                            assigned_room = forced
                            reserve(forced, row["check_in"], row["check_out"])

                    # Else try any room
                    if not assigned_room:
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
                            "check_out": row["check_out"],
                            "forced_room": row.get("forced_room", None)
                        })
                    else:
                        unassigned.append(row.to_dict())

    for family in forced_families:
        if family in family_groups.groups:
            group = family_groups.get_group(family)
            process_family(family, group)
            processed_families.add(family)

    # STEP 2: assign all other families
    for family, group in family_groups:
        if family in processed_families:
            continue
        process_family(family, group)

    assigned_df = pd.DataFrame(assigned)
    unassigned_df = pd.DataFrame(unassigned)
    return assigned_df, unassigned_df
