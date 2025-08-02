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

    families_df["family"] = families_df["full_name" if "full_name" in families_df.columns else "שם מלא"]
    families_df["forced_room"] = families_df.get("forced_room", "")

    processed_families = set()
    forced_rows = families_df[families_df["forced_room"].notna() & (families_df["forced_room"].astype(str).str.strip() != "")]

    def process_family_group(family_group, is_forced=False):
        family_name = family_group["family"].iloc[0]
        if family_name in processed_families:
            return

        log_func(f"🔍 Processing family: {family_name}")
        processed_families.add(family_name)

        for room_type, group in family_group.groupby("room_type"):
            rows = group.sort_values("check_in")
            available_rooms = rooms_by_type.get(room_type, [])

            # Try serial block
            for i in range(len(available_rooms) - len(rows) + 1):
                block = available_rooms[i:i + len(rows)]
                if all(is_available(block[j], row["check_in"], row["check_out"])
                       for j, (_, row) in enumerate(rows.iterrows())):
                    for j, (_, row) in enumerate(rows.iterrows()):
                        r = block[j]
                        reserve(r, row["check_in"], row["check_out"])
                        assigned.append({
                            "family": family_name,
                            "room": r,
                            "room_type": room_type,
                            "check_in": row["check_in"],
                            "check_out": row["check_out"],
                            "forced_room": row.get("forced_room", "")
                        })
                        log_func(f"✅ Assigned {family_name} to {r}")
                    return

            # Fallback to any available
            for _, row in rows.iterrows():
                target_room = row.get("forced_room", "").strip() if is_forced else None
                assigned_room = None

                if target_room and is_available(target_room, row["check_in"], row["check_out"]):
                    assigned_room = target_room
                    log_func(f"🏷️ Forced room {target_room} used for {family_name}")
                else:
                    for r in available_rooms:
                        if is_available(r, row["check_in"], row["check_out"]):
                            assigned_room = r
                            break

                if assigned_room:
                    reserve(assigned_room, row["check_in"], row["check_out"])
                    assigned.append({
                        "family": family_name,
                        "room": assigned_room,
                        "room_type": room_type,
                        "check_in": row["check_in"],
                        "check_out": row["check_out"],
                        "forced_room": row.get("forced_room", "")
                    })
                    log_func(f"✅ Assigned {family_name} to {assigned_room}")
                else:
                    unassigned.append(row.to_dict())
                    log_func(f"❌ Could not assign row for {family_name}")

    # Step 1: Process families with forced_room
    for _, row in forced_rows.iterrows():
        family_name = row["family"]
        family_group = families_df[families_df["family"] == family_name]
        process_family_group(family_group, is_forced=True)

    # Step 2: All remaining families
    for family_name, family_group in families_df.groupby("family"):
        if family_name not in processed_families:
            process_family_group(family_group)

    return pd.DataFrame(assigned), pd.DataFrame(unassigned)

def validate_constraints(df):
    hard_ok = True
    soft_violations = []

    seen = {}
    for i, row in df.iterrows():
        key = (row["room"], row["check_in"], row["check_out"])
        if key in seen:
            hard_ok = False
            break
        seen[key] = True

    # Check soft constraints
    grouped = df.groupby("family")
    for family, group in grouped:
        group = group.sort_values("room")
        rooms = list(group["room"])
        if len(rooms) > 1:
            for i in range(len(rooms) - 1):
                if not are_serial(rooms[i], rooms[i + 1]):
                    soft_violations.append(f"{family} not assigned to serial rooms.")
                    break

        for _, row in group.iterrows():
            forced = str(row.get("forced_room", "")).strip()
            if forced and row["room"] != forced:
                soft_violations.append(f"{family} did not get forced room {forced} (got {row['room']}).")

    return hard_ok, soft_violations

def are_serial(r1, r2):
    # Extract number suffix, compare numerically
    import re
    n1 = re.findall(r'\d+', r1)
    n2 = re.findall(r'\d+', r2)
    if n1 and n2:
        return abs(int(n1[0]) - int(n2[0])) == 1
    return False
