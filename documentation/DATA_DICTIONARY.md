# Data dictionary

All identifiers are deterministic strings. Core records carry `lifecycle_state`,
`effective_from`, `effective_to`, `created_at`, and `updated_at`; date/time values
are generated against the fixed seed date, not the machine clock. `audit_events`
is a supporting change-history table in addition to the 11 requested domain entities.

| Entity / table | Primary key | Important fields and relationships |
|---|---|---|
| Program / `programs` | `PRG-000001` | Unique `program_code`, name, department, degree level. One program has many courses and student plans. |
| Course / `courses` | `CRS-000001` | `program_id` FK, unique course code, credits, required/elective category, max section size, synthetic popularity score. |
| Prerequisite / `prerequisites` | `PRE-000001` | Links a course to its required course; self-prerequisites and duplicate pairs are prohibited. |
| StudentPlan / `student_plans` | `PLN-000001` | `program_id` FK, cohort year, entry term. A plan has registration-interest records. |
| RegistrationInterest / `registration_interests` | `INT-000000001` | Student-plan and course FKs, term, requested timestamp, and status. `registered`/`completed` records provide historical enrollment observations. |
| Faculty / `faculty` | `FAC-000001` | Department, experience, maximum weekly workload. |
| FacultySkill / `faculty_skills` | `FSK-000001` | Faculty/course bridge with proficiency; one skill record per pair. |
| Availability / `availabilities` | `AVL-0000001` | Faculty FK, weekday, time interval, and `available`/`leave` type. |
| Room / `rooms` | `ROM-000001` | Unique room code, building, capacity, and room type. |
| Section / `sections` | `SEC-2026-000001` | Course/room FKs, term, section number, capacity, planned enrollment, weekday, and meeting interval. Planned enrollment cannot exceed capacity. |
| WorkloadAssignment / `workload_assignments` | `WLA-2026-000001` | Faculty/section FKs, weekly hours, assignment state, optional score and explanation. |
| AuditEvent / `audit_events` | `AUD-000001` | Supporting append-only event record with entity reference, action, JSON details, and occurrence time. |
| ForecastRun / `forecast_runs` | `FRN-2027-000001` | Immutable run metadata, target term, selected algorithm, holdout metrics, and creation timestamp. |
| ForecastResult / `forecast_results` | `FCR-2027-000001-000001` | Run/course FKs, latest historical enrollment, interest count, prediction, tree uncertainty, recommended sections, demand class, and explanation. |
| ExceptionRecord / `exceptions` | `EXC-000001` | Entity, issue type, severity, detection time, isolated ground-truth label, resolution status, source. |
| ValidationRun / `validation_runs` | `VAL-000001` | Check totals/status, warning count, full JSON report, and run timestamp. |

## Status values

- Program, course, student plan, faculty, room, and association rows use lifecycle
  states such as `active`, `inactive`, `draft`, `scheduled`, `assigned`,
  `unassigned`, `completed`, `cancelled`, and `retired`.
- Registration interests use `interested`, `registered`, `completed`,
  `waitlisted`, or `withdrawn`.
- Availability uses `available` or `leave`.
- Workload assignments use `assigned` or `unassigned`.
- Exception severity uses `critical`, `high`, `medium`, or `low`; resolution
  status uses `open`, `in_progress`, `resolved`, or `dismissed`.
- Forecast demand category uses `High`, `Medium`, or `Low`.

## Synthetic data volumes

| Mode | Programs | Courses | Faculty | Student plans | Rooms |
|---|---:|---:|---:|---:|---:|
| Starter | 4 | 24 | 12 | 160 | 8 |
| Full | 100 | 1,000 | 500 | 20,000 | 80 |

Registration interests, skills, availability, prerequisites, sections, workload
assignments, and audit events are generated as related child records. Historical
registration rows use four fixed terms (`2024-Fall`, `2025-Spring`, `2025-Fall`,
`2026-Fall`). The final term represents current interest/registration. High
popularity scores are deliberately assigned to some electives.

Forecasting and validation append immutable run/result records. Forecast
explanations are JSON feature summaries; the separate validation ground-truth
file contains only labelled scenario metadata and is never passed into
forecast-model inputs.
