# REST API

Base URL: `http://localhost:5000/api`. JSON request bodies are validated and
errors have the shape:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request body is invalid.",
    "details": [{"field": "term_code", "message": "String should match pattern"}]
  }
}
```

Successful JSON responses use `{"data": ...}`. Collection routes return
`{"data": [...]}`. CSV and JSON export routes return downloadable files.

## Workflow

1. `POST /data/generate` with `{"mode":"starter","seed":20261022}` to seed an
   empty database. Existing deterministic IDs return HTTP 409; no data is
   overwritten.
2. `POST /forecast/run` with `{"term_code":"2027-Fall","seed":20261022}`.
3. `POST /allocations/sections` and `POST /allocations/faculty` with
   `{"term_code":"2027-Fall"}`.
4. `POST /validation/run`, then inspect `/validation/results` and `/exceptions`.
5. Resolve an exception with `PATCH /exceptions/{id}/resolve`.

## Routes

| Method | Route | Response |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| GET / POST | `/programs` | Program list / created program |
| GET / POST | `/courses` | Course list / created course |
| GET | `/students` | Student-plan list |
| GET / POST | `/faculty` | Faculty list / created faculty |
| GET | `/dashboard/summary` | KPI/chart aggregates |
| POST / GET | `/forecast/run`, `/forecast/results` | Persist an immutable forecast / per-course rows |
| POST / GET | `/allocations/sections` | Create sections from latest term forecast / section rows |
| POST / GET | `/allocations/faculty` | Assign eligible unassigned sections / assignments |
| GET / PATCH | `/exceptions`, `/exceptions/{id}/resolve` | Exception history / mark resolved |
| POST / GET | `/validation/run`, `/validation/results` | Persist validation report / latest report |
| POST | `/data/generate` | Seed generated records and baseline CSV/JSON files |
| GET | `/export/csv`, `/export/json` | Combined database snapshot |
| GET | `/reports` | JSON by default; CSV when `Accept: text/csv` |

List routes return at most 5,000 rows. Export routes include the full snapshot.
Forecast result queries accept an optional `term_code` query parameter. Section
and faculty-allocation lists accept the same filter.

## Create records

`POST /programs`:

```json
{
  "program_code": "CSE-201",
  "name": "Computer Science BSc",
  "department": "Computer Science",
  "degree_level": "undergraduate"
}
```

`POST /courses` requires an existing `program_id` plus `course_code`, `name`,
`credits`, `category`, `is_elective`, `max_section_size`, and `popularity_score`.
`POST /faculty` accepts `name`, `department`, `years_experience`, and
`max_weekly_workload`.

Use the interactive dashboard for the same forecast, allocation, validation,
exception-resolution, and export operations.