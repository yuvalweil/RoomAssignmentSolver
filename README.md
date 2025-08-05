# Room Assignment System (Streamlit + Python)

A Streamlit app that assigns guests to rooms/campsites for a tourism business.  
Users upload **two CSVs** (`families.csv` and `rooms.csv`), then the app assigns rooms under hard and soft constraints, provides filters and diagnostics, supports manual overrides and “what‑if” tests, and exports a **Daily Operations Sheet** in Hebrew layout.

---

## ✨ Features

- **CSV uploads** with safe parsing (UTF‑8‑SIG; no accidental `"nan"` strings).
- **Backtracking solver** with MRV + soft scoring, **per‑room_type solving** and **time/node budgets** so the UI never hangs.
- **Relaxation ladder** to ensure all rows get assigned when possible: waive **serial** first, then **forced** (soft) constraints.
- **Soft preferences for “שטח” room_type** (two areas + group-size targets; see below).
- **Filters & views** (all, by date, by date range; by family & room_type).
- **Manual override** with **hard‑constraint validation**.
- **What‑if**: try a single `forced_room` change without touching the main state.
- **Diagnostics**: soft-constraint report.
- **Daily Operations Sheet (Printable HTML)** with Hebrew headers:  
  **יחידה, שם, אנשים, לילות, תוספת, א.בוקר, שולם, לחיוב, הערות**.

---

## 📁 Repository structure (representative)

```
app.py
ui/
  helpers.py        # session, CSV read, filters, daily sheet builders
  sections.py       # Streamlit sections (overview, date/range, daily sheet, manual override, diagnostics, what-if, logs)
  upload.py         # file inputs and inits
  runner.py         # run_assignment() – passes time/node budgets to solver
logic/
  __init__.py       # exports assign_rooms (from solver), validate, diagnostics, etc.
  solver.py         # MRV + soft scoring, per-type solving, time/node budgets, legacy wrapper
  utils.py          # helpers (are_serial, room number parsing, etc.)
  validate.py       # validate_constraints(), rebuild_calendar_from_assignments()
  diagnostics.py    # explain_soft_constraints()
```

> If you add or move modules, keep `logic/__init__.py` exporting `assign_rooms` from `logic/solver.py`.

---

## 🔧 Installation

```bash
# Python 3.10+ recommended
python -m venv .venv
source .venv/bin/activate  # (Windows: .venv\Scripts\activate)

pip install -r requirements.txt
# If no requirements.txt, minimally:
pip install streamlit pandas numpy
```

---

## ▶️ Running the app

```bash
streamlit run app.py
```

Open the URL shown by Streamlit in your browser.

---

## 📥 CSV Inputs

### `families.csv` (one row = one booking)

**Required columns**
- `family` (or `full_name` / `שם מלא`)
- `room_type`
- `check_in`, `check_out` — format **DD/MM/YYYY** (half-open interval `[check_in, check_out)`)

**Optional columns** (used when present)
- `forced_room`
- `people` / `אנשים`
- `extras` / `תוספת`
- `breakfast` / `א.בוקר` (truthy values render as ✓ on the Daily Sheet)
- `paid` / `שולם`
- `charge` / `לחיוב`
- `notes` / `הערות`
- `crib` / `לול` (if truthy, “לול” is appended to notes — configurable)

> Empty cells remain empty (no `"nan"`).

### `rooms.csv`

- `room_type`
- `room` (label; may contain a number like “שטח 12” — the number is parsed for preferences)

---

## 🧠 Solver (logic/solver.py)

**Algorithm:** Backtracking with **MRV** (fewest feasible rooms first) and *value ordering* by soft scores.  
**Performance:** 
- **Per‑type solving** (assign each `room_type` independently) to reduce search space.
- **Budgets** per type: `time_limit_sec` (default **20s**) and `node_limit` (default **150k**).  
  If a search exceeds the budget, the solver returns the **best partial** assignment so far (max assigned; tiebreak by lowest total soft penalty).

**Hard constraints**
- No room double-booking (`[check_in, check_out)` intervals).
- Must match `room_type` (no cross-type assignment).
- Families can be assigned multiple rooms (e.g., large families/grouped tents).

**Soft constraints**
1. **Serial adjacency within a family** (bonus if consecutive/“serial” rooms; waived first if needed).  
2. **Respect `forced_room`** (bonus when matched, mild penalty when not; waived only after serial).  
3. **שטח (field) room_type logic:**
   - Two separate areas: **1–5** and **6–18** → prefer keeping a family’s group within one area; **penalize crossing 5↔6**.
   - Group-size targets (when possible):
     - 5 rooms → **1,2,3,4,5**
     - 3 rooms → **12,13,14**
     - 2 rooms → **16,18**
     - 1 room → prefer **8,12,17,1,18** (in that order)

**Relaxation order**
- Try **serial ON + forced ON** → if no full solution, **waive serial** → if still no full solution, **waive serial + forced**.  
- The goal is to **assign everyone** when possible, while honoring soft constraints as much as feasible.

**Compatibility shims**
- `assign_per_type(families, rooms, ...)` accepts either **DataFrames** or **lists of dicts** and returns **(assigned_df, unassigned_df, meta)**.  
- Outputs include columns **`_idx`** and **`id`** for legacy code paths.

---

## 🖥️ UI Highlights

- **Full Assignment Overview** + filters (by family & room_type). Forced rows are highlighted.
- **By Date / Date Range** view (uses derived `check_in_dt` / `check_out_dt`).
- **Daily Operations Sheet (Printable HTML)**  
  Built only from `families.csv` & `rooms.csv`. Columns:  
  **יחידה, שם, אנשים, לילות, תוספת, א.בוקר, שולם, לחיוב, הערות**  
  - **יחידה** comes from assignment if available, otherwise from `forced_room` (if present).  
  - **לילות** shows `k/n` for the selected date (`k` = current night index; `n` = total nights).  
  - Download as a single HTML file.
- **Manual Override** (change a single assigned row; hard-validate; warn on soft breaks).
- **What‑if** (temporary `forced_room` on a single row to preview impact).
- **Diagnostics** (soft-constraint explanations) and **Logs** (compact tail + downloadable).

---

## 📅 Date handling

- Dates are expected as **DD/MM/YYYY**.
- Stays are treated as **half-open**: `[check_in, check_out)`; the guest stays nights starting on `check_in` up to but **not including** `check_out`.

---

## ⚙️ Configuration knobs

- In `ui/runner.py` → `run_assignment()`:
  - `time_limit_sec`: default **20.0** seconds (per room_type).
  - `node_limit`: default **150_000** explored nodes (per room_type).
  - `solve_per_type`: default **True** (recommended).

These can be exposed as Streamlit controls if desired.

---

## ✅ “Last good version”

Use a tag to bookmark a known‑good state:

```bash
git add -A && git commit -m "Save last good version"
git tag -a last-good-YYYY-MM-DD -m "Last good version"
git push && git push origin last-good-YYYY-MM-DD
```

---

## 🧪 Roadmap / Ideas

- Local-search improvement pass after backtracking (swap/2-opt for soft gains).  
- UI controls for solver budgets; per-type budget multipliers.  
- Enriched diagnostics explaining which soft rules were waived and why.  
- Export Daily Ops Sheet to **Excel/PDF** with styled columns/RTL.  
- Regression tests with small synthetic CSVs.

---

## 🤖 Using ChatGPT with this repo (optional)

- **Complex solver design or debugging:** use **o3** (best reasoning).  
- **Everyday fast iteration on code/tests:** use **o4‑mini**.  
- **Long-form refactors/design docs:** use **GPT‑4.1** (large context).  
- **When sharing screenshots/log images:** use **GPT‑4o** (multimodal).

Paste the **“Context for New Chat”** snippet from this README when opening a fresh chat to onboard the assistant quickly.

---

## 📝 License

Private/internal project (choose a license if/when open‑sourcing).

---

## 🙋 Support

Open an issue or ping the maintainer with the CSVs (redacted as needed) and the expected behavior.
