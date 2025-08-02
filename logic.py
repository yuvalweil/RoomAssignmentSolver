import pandas as pd
from datetime import datetime as dt

room_calendars = {}

def is_available(room, check_in_str, check_out_str):
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")
    if room not in room_calendars:
        return True
    return all(check_out <= start or check_in >= end for start, end in room_calendars[room])

def reserve(room, check_in_str, check_out_str):
    check_in = dt.strptime(check_in_str, "%d/%m/%Y")
    check_out = dt.strptime(check_out_str, "%d/%m/%Y")
    room_calendars.setdefault(room, []).append((check_in, check_out))

def assign_rooms(families_df, rooms_df):
    global room_calendars
    room_calendars = {}

    assigned, unassigned = [], []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()
    families_df["forced_room"] = families_df.get("forced_room", "").fillna("")

    # Group families for prioritization
    families_df["has_forced"] = families_df["forced_room"].str.strip() != ""
    forced_families = families_df[families_df["has_forced"]]["full_name"].unique()
    other_families = families_df[~families_df["full_name"].isin(forced_families)]["full_name"].unique()

    all_families_ordered = list(forced_families) + list(other_families)

    for family in all_families_ordered:
        group = families_df[families_df["full_name"] == family].copy()
        group = group.sort_values(by="check_in")
        grouped_by_type = group.groupby("room_type")

        for room_type, orders in grouped_by_type:
            orders = orders.sort_values(by="check_in")

            # 1. Try to assign forced_room rows first
            forced_rows = orders[orders["forced_room"].str.strip() != ""]
            normal_rows = orders[orders["forced_room"].str.strip() == ""]

            skip_entire_group = False
            for _, row in forced_rows.iterrows():
                room = row["forced_room"].strip()
                if room not in rooms_by_type.get(room_type, []):
                    unassigned.append(row.to_dict())
                    skip_entire_group = True
                    break
                if is_available(room, row["check_in"], row["check_out"]):
                    assigned.append({
                        "family": family,
                        "room": room,
                        "room_type": room_type,
                        "check_in": row["check_in"],
                        "check_out": row["check_out"],
                        "forced_room": room
                    })
                    reserve(room, row["check_in"], row["check_out"])
                else:
                    unassigned.append(row.to_dict())
                    skip_entire_group = True
                    break
            if skip_entire_group:
                for _, row in normal_rows.iterrows():
                    unassigned.append(row.to_dict())
                continue

            # 2. Try serial room block
            available_rooms = [r for r in rooms_by_type.get(room_type, []) if all(
                is_available(r, row["check_in"], row["check_out"]) for _, row in normal_rows.iterrows()
            )]

            block_found = False
            for i in range(len(available_rooms) - len(normal_rows) + 1):
                block = available_rooms[i:i+len(normal_rows)]
                if all(is_available(block[j], row["check_in"], row["check_out"])
                       for j, (_, row) in enumerate(normal_rows.iterrows())):
                    for j, (_, row) in enumerate(normal_rows.iterrows()):
                        assigned.append({
                            "family": family,
                            "room": block[j],
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": ""
                        })
                        reserve(block[j], row["check_in"], row["check_out"])
                    block_found = True
                    break

            # 3. Fallback to any room
            if not block_found:
                for _, row in normal_rows.iterrows():
                    room_found = None
                    for room in rooms_by_type.get(room_type, []):
                        if is_available(room, row["check_in"], row["check_out"]):
                            room_found = room
                            break
                    if room_found:
                        assigned.append({
                            "family": family,
                            "room": room_found,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": ""
                        })
                        reserve(room_found, row["check_in"], row["check_out"])
                    else:
                        unassigned.append(row.to_dict())

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)
