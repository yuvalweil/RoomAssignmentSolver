Room Assignment System (Streamlit + Python)

A Streamlit app that assigns guests to rooms/campsites for a tourism business.Users upload two CSVs (families.csv and rooms.csv), then the app assigns rooms under hard and soft constraints, provides filters and diagnostics, supports manual overrides and “what‑if” tests, and exports a Daily Operations Sheet in Hebrew layout.

✨ What’s New (Aug 2025)

forced_room is now a hard constraint. If a row has forced_room, the solver will only consider that exact room. If it can’t fit (conflict / wrong type / missing), the row won’t be assigned.

Priority updated: Hard (incl. forced_room) → Serial (same type) → Mixed‑type rules → Field ("שטח") preferences.

Solver changes:

Bookings with forced_room are tried first in the search order.

Candidate generation filters to the forced room when present (true hardening).

Defaults increased: 60s & 500k nodes per room type; ui/runner.py passes these fixed budgets (no sliders).

Diagnostics: added checks for mixed‑type rules and clearer forced‑room explanations.

UI tweak: The “Full Assignment Overview” displays only family, room_type, room_num (display rename of room), check_in, check_out, forced_room.

📁 Repository Structure (representative)

app.py
ui/
  helpers.py        # session, CSV read, filters, daily sheet builders
  sections.py       # Streamlit sections (overview, date/range, daily sheet, manual override, diagnostics, what-if, logs)
  upload.py         # file inputs and inits
  runner.py         # run_assignment() – fixed budgets → solver
logic/
  __init__.py       # exports assign_rooms (from solver), validate, diagnostics, etc.
  solver.py         # backtracking (MRV + soft scoring), per-type solving, budgets, forced_room hardened
  utils.py          # helpers (are_serial, room parsing, intervals, formatting)
  validate.py       # validate_constraints(), rebuild_calendar_from_assignments()
  diagnostics.py    # explain_soft_constraints() incl. mixed-type rules

If you add or move modules, keep logic/__init__.py exporting assign_rooms from logic/solver.py.

🔧 Installation

# Python 3.10+ recommended
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# If no requirements.txt, minimally:
pip install streamlit pandas numpy

▶️ Running the App

streamlit run app.py

Open the URL shown by Streamlit.

📥 CSV Inputs

families.csv (one row = one booking)

Required columns

family (or full_name / שם מלא)

room_type

check_in, check_out — format DD/MM/YYYY (half‑open [check_in, check_out))

Optional columns (used when present)

forced_room (hard if set)

people / אנשים

extras / תוספת

breakfast / א.בוקר (truthy → ✓ on Daily Sheet)

paid / שולם

charge / לחיוב

notes / הערות

crib / לול

CSV parsing is UTF‑8‑SIG; empty cells remain empty (no accidental "nan").

rooms.csv

room_type

room (label; may include digits — numeric part is used for some preferences)

🧠 Solver (logic/solver.py)

Algorithm: Backtracking with MRV (fewest feasible rooms first) and value ordering by soft‑penalty score.Decomposition: Per‑type solving (each room_type solved independently) to shrink the search space.Budgets (per type): time_limit_sec = 60.0, node_limit = 500_000 (set in ui/runner.py). When exceeded, the solver returns the best partial assignment so far (most rows placed; tiebreak by lower soft penalty).

Hard Constraints

No double‑booking: For a given (room_type, room), no two intervals [check_in, check_out) may overlap.

Room must exist under its type: Only rooms present in rooms.csv for the room_type are considered.

Full‑range availability: Room must be free for the entire requested interval.

forced_room is HARD: If set, only that room is considered as a candidate for the row.

Family may span multiple rows: A family can legitimately receive multiple rooms (business requirement).

Soft Constraints (in priority order)

Tier 1 — Serial adjacency (same type within a family)

If a family has multiple bookings of the same room_type, prefer contiguous/serial room numbers (e.g., WC01→WC02).

Tier 2 — Mixed‑type family rules (as requested)

שטח + זוגי: זוגי must be room 1; שטח must be in 1–5.

שטח + (קבוצתי or סוכה): שטח in 4–7; קבוצתי/סוכה in 1–2.

משפחתי + (בקתה/קבוצתי/סוכה): משפחתי in {4,5,6,8}.

Tier 3 — Field ("שטח") preferences

Prefer one area per group: 1–5 vs 6–18; penalize crossing 5↔6.

Group‑size target sets:

size 5 → [1,2,3,4,5]

size 3 → [12,13,14]

size 2 → [16,18]

size 1 → [8,12,17,1,18]

Avoid splitting clusters across assignments: {2,3}, {9,10,11}, {10,11}, {13,14}, {16,18}.

Singles prohibited in {2,3,4,5,15}; room 15 is last‑priority for singles.

Search Order & Relaxation

Depth order: bookings with forced_room are processed first.

Relaxation ladder (per type):

forced only (serial waived)

forced + serial

relax both (note: forced_room remains hard at candidate generation, so if a forced row can’t fit, there may be no full solution)

🖥️ UI Highlights

📋 Full Assignment Overview: shows only family, room_type, room_num, check_in, check_out, forced_room (and highlights forced rows).Note: room_num is just a display rename of the room column.

📅 Date / Range View: filter by a single date or by range; shows assigned/unassigned with the same columns.

🗂️ Daily Operations Sheet (Printable HTML): Hebrew headersיחידה, שם, אנשים, לילות, תוספת, א.בוקר, שולם, לחיוב, הערות

🛠️ Manual override: apply a room change to a family row and re‑validate (hard constraints enforced; soft warnings shown).

🧪 What‑if: temporary forced_room on a selected input row; compare before/after; download results & log.

🔎 Diagnostics: soft‑constraint report (forced_not_met, non_serial, mixed‑type issues) with reasons and blockers.

🐞 Logs: shows a tail of solver logs; downloadable.

📅 Date Handling

Dates must be DD/MM/YYYY.

Intervals are half‑open: [check_in, check_out) — guests stay nights starting on check_in, up to but not including check_out.

⚙️ Configuration

Fixed budgets in ui/runner.py → run_assignment():

time_limit_sec = 60.0 (per room_type)

node_limit = 500_000 (per room_type)

solve_per_type = True

You can still adjust defaults in logic/solver.py if needed.

🧪 Quick Scenarios (manual testing)

Forced‑room respected

# families.csv
family,room_type,check_in,check_out,forced_room
FamA,זוגי,01/09/2025,03/09/2025,2

# rooms.csv
room,room_type
1,זוגי
2,זוגי

Expected: FamA → room 2.

Serial adjacency (same type)

family,room_type,check_in,check_out,forced_room
FamA,זוגי,01/09/2025,02/09/2025,
FamA,זוגי,02/09/2025,03/09/2025,

Rooms for זוגי: 1,2,3 → expect two contiguous rooms (e.g., 1 & 2).

Mixed‑type: שטח + זוגי

family,room_type,check_in,check_out,forced_room
FamA,שטח,01/09/2025,02/09/2025,
FamA,זוגי,01/09/2025,02/09/2025,

Rooms: זוגי→1; שטח→2,6,7 → expect זוגי=1 and שטח within 1–5 ⇒ choose 2 if free.

✅ “Last Good Version”

git add -A && git commit -m "Save last good version"
git tag -a last-good-YYYY-MM-DD -m "Last good version"
git push && git push origin last-good-YYYY-MM-DD

🤖 Using ChatGPT with This Repo (optional)

Complex solver design/debugging: o3

Everyday fast iteration on code/tests: o4‑mini

Long‑form refactors/design docs: GPT‑4.1

When sharing screenshots/log images: GPT‑4o

Paste the “Context for New Chat” snippet when opening a fresh chat to onboard the assistant quickly.

📝 License

Private/internal project (choose a license if/when open‑sourcing).

🙋 Support

Open an issue or share the CSV pair (families.csv, rooms.csv) and the expected behavior. Include any assigned_families.csv and diagnostics for quicker triage.
