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

def assign_rooms(families_df, rooms_df, log_func=print):
    global room_calendars
    room_calendars = {}

    assigned = []
    unassigned = []

    rooms_by_type = rooms_df.groupby("room_type")["room"].apply(lambda x: sorted(x)).to_dict()

    families_df["forced_room"] = families_df.get("forced_room", "")

    def get_family_name(row):
        return row["full_name"] if "full_name" in row else row["שם מלא"]

    families_df["family"] = families_df.apply(get_family_name, axis=1)

    forced_rows = families_df[families_df["forced_room"].notna() & (families_df["forced_room"].astype(str).str.strip() != "")]
    forced_families = forced_rows["family"].unique().tolist()

    handled_families = set()

    for _, forced_row in forced_rows.iterrows():
        family = forced_row["family"]
        if family in handled_families:
            continue
        group = families_df[families_df["family"] == family]
        log_func(f"🔒 Trying forced assignment for family: {family}")

        for room_type, orders in group.groupby("room_type"):
            orders = orders.sort_values("check_in")
            forced_room = forced_row["forced_room"]
            if all(is_available(forced_room, row["check_in"], row["check_out"]) for _, row in orders.iterrows()):
                for _, row in orders.iterrows():
                    reserve(forced_room, row["check_in"], row["check_out"])
                    assigned.append({
                        **row.to_dict(),
                        "room": forced_room
                    })
                log_func(f"✅ Forced assignment for {family} to {forced_room}")
            else:
                log_func(f"❌ Failed forced_room {forced_room} for family {family}")
                for _, row in orders.iterrows():
                    unassigned.append(row.to_dict())

        handled_families.add(family)

    # Serial assignment for other families (first those with some forced row)
    remaining_families = families_df[~families_df["family"].isin(handled_families)]
    prioritized = []

    with_forced = remaining_families.groupby("family").filter(lambda g: (g["forced_room"].astype(str).str.strip() != "").any())
    without_forced = remaining_families[~remaining_families["family"].isin(with_forced["family"])]

    prioritized += list(with_forced.groupby("family"))
    prioritized += list(without_forced.groupby("family"))

    for family, group in prioritized:
        group = group.sort_values(by="check_in")
        for room_type, orders in group.groupby("room_type"):
            available_rooms = [r for r in rooms_by_type.get(room_type, []) if all(
                is_available(r, row["check_in"], row["check_out"]) for _, row in orders.iterrows()
            )]
            found = False
            for i in range(len(available_rooms) - len(orders) + 1):
                block = available_rooms[i:i + len(orders)]
                if all(is_available(block[j], row["check_in"], row["check_out"]) for j, (_, row) in enumerate(orders.iterrows())):
                    for j, (_, row) in enumerate(orders.iterrows()):
                        reserve(block[j], row["check_in"], row["check_out"])
                        assigned.append({**row.to_dict(), "room": block[j]})
                    found = True
                    log_func(f"👨‍👩‍👧 Assigned {family} to serial rooms: {block}")
                    break

            if not found:
                for _, row in orders.iterrows():
                    assigned_room = None
                    for room in rooms_by_type.get(room_type, []):
                        if is_available(room, row["check_in"], row["check_out"]):
                            assigned_room = room
                            reserve(room, row["check_in"], row["check_out"])
                            assigned.append({**row.to_dict(), "room": room})
                            log_func(f"🧩 Assigned {family} to {room}")
                            break
                    if not assigned_room:
                        unassigned.append(row.to_dict())
                        log_func(f"❗ Could not assign row for {family}: {row.to_dict()}")

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)

def validate_constraints(assigned_df, rooms_df):
    hard_ok = True
    soft_violations = []
    room_bookings = {}

    for idx, row in assigned_df.iterrows():
        room = row["room"]
        check_in = dt.strptime(row["check_in"], "%d/%m/%Y")
        check_out = dt.strptime(row["check_out"], "%d/%m/%Y")

        if room not in room_bookings:
            room_bookings[room] = []
        else:
            for (start, end) in room_bookings[room]:
                if not (check_out <= start or check_in >= end):
                    hard_ok = False
                    soft_violations.append(f"❌ Double booking: {room} for row {idx}")
        room_bookings[room].append((check_in, check_out))

    grouped = assigned_df.groupby("family")
    for family, group in grouped:
        grouped_by_type = group.groupby("room_type")
        for room_type, orders in grouped_by_type:
            rooms = sorted(orders["room"].tolist())
            if len(rooms) > 1:
                serial = True
                for i in range(1, len(rooms)):
                    prev = int(''.join(filter(str.isdigit, rooms[i - 1])))
                    curr = int(''.join(filter(str.isdigit, rooms[i])))
                    if curr != prev + 1:
                        serial = False
                        break
                if not serial:
                    soft_violations.append(f"⚠️ {family} rooms not serial: {rooms}")

    return hard_ok, soft_violations
