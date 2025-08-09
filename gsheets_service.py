import os
from flask import Flask, request, jsonify
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from logic import assign_rooms

app = Flask(__name__)


def _load_sheet(sh, title):
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=1, cols=1)


@app.route("/solve", methods=["POST"])
def solve_from_sheet():
    data = request.get_json(force=True)
    spreadsheet_id = data["spreadsheet_id"]
    families_sheet = data.get("families_sheet", "families")
    rooms_sheet = data.get("rooms_sheet", "rooms")
    assigned_sheet = data.get("assigned_sheet", "assigned")
    unassigned_sheet = data.get("unassigned_sheet", "unassigned")
    cred_file = data.get("service_account_file", os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json"))

    gc = gspread.service_account(filename=cred_file)
    sh = gc.open_by_key(spreadsheet_id)

    fam_ws = sh.worksheet(families_sheet)
    rooms_ws = sh.worksheet(rooms_sheet)
    families_df = get_as_dataframe(fam_ws, evaluate_formulas=True, header=0).dropna(how="all").fillna("")
    rooms_df = get_as_dataframe(rooms_ws, evaluate_formulas=True, header=0).dropna(how="all").fillna("")

    assigned_df, unassigned_df = assign_rooms(families_df, rooms_df)

    assigned_ws = _load_sheet(sh, assigned_sheet)
    assigned_ws.clear()
    set_with_dataframe(assigned_ws, assigned_df)

    unassigned_ws = _load_sheet(sh, unassigned_sheet)
    unassigned_ws.clear()
    set_with_dataframe(unassigned_ws, unassigned_df)

    return jsonify({
        "assigned_rows": int(len(assigned_df)),
        "unassigned_rows": int(len(unassigned_df)),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
