from __future__ import annotations

import re
from collections import Counter
from typing import Any


ID_PATTERNS = {
    "programs": re.compile(r"^PRG-\d{6}$"),
    "courses": re.compile(r"^CRS-\d{6}$"),
    "faculty": re.compile(r"^FAC-\d{6}$"),
    "sections": re.compile(r"^SEC-\d{4}-\d{6}$"),
    "workload_assignments": re.compile(r"^WLA-\d{4}-\d{6}$"),
}
LIFECYCLE_STATES = {
    "active", "draft", "scheduled", "assigned", "unassigned",
    "completed", "cancelled", "inactive", "retired",
}


def primary_key_issues(tables: dict[str, list[Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for table, rows in tables.items():
        ids = [row.id for row in rows]
        duplicates = [identifier for identifier, count in Counter(ids).items() if count > 1]
        issues.extend(
            {
                "entity_id": identifier,
                "description": f"Duplicate primary key {identifier} in {table}.",
            }
            for identifier in duplicates
        )
    return issues


def foreign_key_issues(tables: dict[str, list[Any]]) -> list[dict[str, str]]:
    references = {
        "courses": (("program_id", "programs"),),
        "prerequisites": (("course_id", "courses"), ("required_course_id", "courses")),
        "student_plans": (("program_id", "programs"),),
        "registration_interests": (
            ("student_plan_id", "student_plans"), ("course_id", "courses")
        ),
        "faculty_skills": (("faculty_id", "faculty"), ("course_id", "courses")),
        "availabilities": (("faculty_id", "faculty"),),
        "sections": (("course_id", "courses"), ("room_id", "rooms")),
        "workload_assignments": (
            ("faculty_id", "faculty"), ("section_id", "sections")
        ),
    }
    ids_by_table = {
        table: {record.id for record in rows} for table, rows in tables.items()
    }
    issues: list[dict[str, str]] = []
    for table, relationships in references.items():
        for field, referenced_table in relationships:
            for record in tables[table]:
                if getattr(record, field) not in ids_by_table[referenced_table]:
                    issues.append(
                        {
                            "entity_id": record.id,
                            "description": (
                                f"{table}.{record.id} references a missing "
                                f"{referenced_table} record through {field}."
                            ),
                        }
                    )
    program_by_plan = {
        plan.id: plan.program_id for plan in tables["student_plans"]
    }
    program_by_course = {course.id: course.program_id for course in tables["courses"]}
    for record in tables["registration_interests"]:
        if (
            record.student_plan_id in program_by_plan
            and record.course_id in program_by_course
            and program_by_plan[record.student_plan_id]
            != program_by_course[record.course_id]
        ):
            issues.append(
                {
                    "entity_id": record.id,
                    "description": (
                        "Registration interest course and student plan belong "
                        "to different programs."
                    ),
                }
            )
    return issues


def identifier_issues(tables: dict[str, list[Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for table, pattern in ID_PATTERNS.items():
        for record in tables[table]:
            if not pattern.fullmatch(record.id):
                issues.append(
                    {
                        "entity_id": record.id,
                        "description": f"Invalid {table} identifier format: {record.id}.",
                    }
                )
    return issues


def lifecycle_issues(tables: dict[str, list[Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for table, rows in tables.items():
        if table == "audit_events":
            continue
        for record in rows:
            if record.lifecycle_state not in LIFECYCLE_STATES:
                issues.append(
                    {
                        "entity_id": record.id,
                        "description": (
                            f"Unsupported lifecycle state {record.lifecycle_state!r} "
                            f"on {table}."
                        ),
                    }
                )
            if (
                record.effective_to is not None
                and record.effective_to < record.effective_from
            ):
                issues.append(
                    {
                        "entity_id": record.id,
                        "description": f"Effective end precedes start on {table}.",
                    }
                )
    return issues