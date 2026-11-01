# Database schema

The canonical ORM definition is [models.py](../backend/database/models.py).
The equivalent MySQL 8 DDL is [schema.sql](../backend/database/schema.sql).
All relationships use foreign keys with restrictive deletion, so historical
registration, section, and workload records cannot be removed by deleting a
parent entity.

The 11 core domain entities are `Program`, `Course`, `Prerequisite`,
`StudentPlan`, `RegistrationInterest`, `Faculty`, `FacultySkill`, `Availability`,
`Section`, `Room`, and `WorkloadAssignment`. `AuditEvent` is an additional
supporting table for append-only history.

The `Prerequisite` table uses two course foreign keys to represent the
self-referential course relationship. `FacultySkill` and `WorkloadAssignment`
are bridge tables for their many-to-many relationships. Sections have a unique
course/term/section-number key, reference one room, and record expected
enrollment independently from capacity.

`ForecastRun` and `ForecastResult` preserve each forecast and its per-course
outputs. `ValidationRun` preserves the check summary and report. `ExceptionRecord`
tracks real validation/allocation findings and separately labels isolated
ground-truth scenarios. `AuditEvent` records the generation, forecast,
allocation, validation, and resolution history. These tables are included in
the ORM-generated local schema and the MySQL DDL.

For development, SQLAlchemy defaults to a local SQLite database. Set
`DATABASE_URL` to a MySQL 8 connection string to use MySQL; the same ORM schema
and data generator work with either engine.
