# Phase 6: testing and submission

## Verified workflow

The repeatable demo command is:

```powershell
python scripts\run_demo.py --database-url sqlite:///data/phase6-demo.db --output-dir data\submission
```

It seeds the starter dataset only when the selected database is empty, then
persists a 2027-Fall forecast, section/faculty allocation, validation report,
audit history, and entity-level exports. Run it against a fresh database for a
clean submission snapshot; it never deletes existing rows.

The export directory contains per-table CSV and JSON files, a separate
`ground_truth.csv`/`.json`, `seed.sql`, `source_manifest.json`, and
`workflow_summary.json`. Apply [schema.sql](../backend/database/schema.sql) to
an empty MySQL 8 schema before executing `seed.sql`. Use the same SQLAlchemy
schema from `Base.metadata` for SQLite.

## Automated checks

```powershell
python -m pytest -q
Set-Location frontend
npm run typecheck
npm run build
```

The backend tests cover deterministic starter/full generation, SQLite
foreign-key persistence, CSV/JSON/SQL snapshot output, RF and baseline metrics,
allocation constraints/idempotence, all five labelled negative cases, API
request errors, exception resolution, and a complete REST workflow including
exports.

The full-size generator and its ground-truth labels were independently
generated twice with seed `20261022`; row counts and SHA-256 checksums matched.
The dashboard production build and TypeScript checks are also part of
verification.

## Screenshot

The dashboard and API were started for a screenshot attempt, but the browser
tool could not reach the local Vite service (`ERR_CONNECTION_TIMED_OUT`) in this
sandbox. No screenshot file is claimed as a deliverable. To capture it locally,
run the API and frontend using the README instructions, open the Vite URL, and
save a screenshot as `documentation/screenshots/dashboard.png`.
