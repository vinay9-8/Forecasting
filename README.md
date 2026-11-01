# AI-Powered Course Demand Forecasting and Faculty Allocation

Integrated academic-planning demo: deterministic synthetic data, moving-average
and Random Forest forecasts, constrained section/faculty allocation, isolated
labelled anomaly scenarios, validation history, REST APIs, exports, and a React
dashboard.

## Requirements

- Python 3.11+
- Node.js 20+ and npm
- MySQL 8 for a MySQL deployment; local development can use SQLite

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm install
Set-Location ..
```

By default, the backend uses `sqlite:///course_demand.db`. For MySQL, copy
`.env.example` as a reference and set `DATABASE_URL` in the process environment
or VS Code launch configuration; the application does not load `.env` files.
Never commit database credentials.

## Run the complete starter workflow

Use an empty database or let the demo seed one on first run. The script runs
generation → forecasting → section/faculty allocation → validation and writes
per-table CSV/JSON, ground truth, a source manifest, SQL seed inserts, and a
workflow summary:

```powershell
python scripts\run_demo.py
```

Default exports go to `data/submission`. The script never clears or replaces
existing records. To use a dedicated SQLite file:

```powershell
python scripts\run_demo.py --database-url sqlite:///data/phase6-demo.db --output-dir data\submission
```

To start the dashboard, launch the API and frontend in separate terminals:

```powershell
python -m backend.app
```

```powershell
Set-Location frontend
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`).
Vite proxies `/api` requests to the local Flask server at
`http://127.0.0.1:5000`; keep the API running in its separate terminal. Set
`VITE_API_BASE_URL` before starting Vite to use a different API URL.

## Generate, validate, and export data independently

```powershell
python scripts\generate_data.py --mode starter --seed 20261022
python scripts\generate_data.py --mode full --seed 20261022 --output-dir data\generated\full
python scripts\reproduce_dataset.py --mode starter --seed 20261022
python scripts\reproduce_dataset.py --mode full --seed 20261022
python scripts\run_validation.py --seed-starter-if-empty
python scripts\export_data.py --output-dir data\submission
```

Pass `--persist` to `generate_data.py` to insert generated rows into
`DATABASE_URL`. Generation is transactional and deliberately returns a conflict
if deterministic IDs already exist; it does not overwrite historical data.
`run_validation.py` validates the configured database. It exits nonzero when
checks fail.

## Tests and build

```powershell
python -m pytest -q
Set-Location frontend
npm run typecheck
npm run build
```

The Phase 6 workflow was verified end to end: all 30 backend tests passed,
frontend typechecking and production build succeeded, and the demo export
contains 24 course forecasts, 24 generated sections, and 13 validation checks
with no failures. The generated snapshot and detailed metrics are in
[data/submission](data/submission) and
[workflow_summary.json](data/submission/workflow_summary.json).

The dashboard screenshot could not be captured because the browser environment
could not connect to the locally running frontend. No screenshot is included;
see [submission notes](documentation/SUBMISSION.md) for local capture steps.

## Forecasting and allocation

The forecast uses a historical moving-average baseline and a seeded
`RandomForestRegressor`. A fixed 80/20 train/test split reports MAE, RMSE, MAPE
(zero-actual observations are excluded from the percentage denominator), and
R². The model is selected only when its holdout MAE is no worse than the
baseline. Per-course results include prediction spread across trees,
recommended sections, demand category, and explanatory input values.

The section planner consumes the most recent forecast for the requested term.
It respects course and room capacity, room time conflicts, faculty skill,
availability/leave, workload, and schedule conflicts; it reports unmet demand
and leaves sections unassigned rather than violating a hard constraint. Repeated
allocation for the same forecast accounts for existing planned enrollment and
does not recreate already covered seats.

## API

All routes are under `/api` and return JSON with a `data` property, except CSV
and JSON downloads:

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET / POST | `/programs`, `/courses`, `/faculty` | List and create master records |
| GET | `/students` | List student plans |
| GET | `/dashboard/summary` | KPI and chart data |
| POST / GET | `/forecast/run`, `/forecast/results` | Run and review forecasts |
| POST / GET | `/allocations/sections` | Plan and list sections |
| POST / GET | `/allocations/faculty` | Assign and list faculty workloads |
| GET / PATCH | `/exceptions`, `/exceptions/{id}/resolve` | Review and resolve issues |
| POST / GET | `/validation/run`, `/validation/results` | Run and review validation |
| POST | `/data/generate` | Generate and persist starter/full synthetic data |
| GET | `/export/csv`, `/export/json`, `/reports` | Download data and report snapshots |

See [API documentation](documentation/API_DOCUMENTATION.md) for request and
response examples.

## Documentation and deliverables

- [Data dictionary](documentation/DATA_DICTIONARY.md)
- [Database schema](documentation/DATABASE_SCHEMA.md) and
  [MySQL DDL](backend/database/schema.sql)
- [Forecasting and validation methodology](documentation/METHODOLOGY.md)
- [Synthetic data generator](documentation/GENERATOR.md)
- [Phase 6 test and submission notes](documentation/SUBMISSION.md)

The 11 core domain entities are Program, Course, Prerequisite, StudentPlan,
RegistrationInterest, Faculty, FacultySkill, Availability, Section, Room, and
WorkloadAssignment. Forecast runs/results, validation runs, exception records,
and append-only audit events are additional workflow tables.

All data is synthetic. Ground-truth anomaly examples are exported separately;
the five negative cases are constructed in isolated fixtures and do not alter
the valid baseline records.
