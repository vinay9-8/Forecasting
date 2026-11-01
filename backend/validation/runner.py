from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import (
    AuditEvent,
    Availability,
    Course,
    ExceptionRecord,
    Faculty,
    FacultySkill,
    Prerequisite,
    Program,
    RegistrationInterest,
    Room,
    Section,
    StudentPlan,
    ValidationRun,
    WorkloadAssignment,
)
from backend.validation.engine import validate_tables

DATASET_MODELS = {
    "programs": Program,
    "courses": Course,
    "prerequisites": Prerequisite,
    "student_plans": StudentPlan,
    "registration_interests": RegistrationInterest,
    "faculty": Faculty,
    "faculty_skills": FacultySkill,
    "availabilities": Availability,
    "rooms": Room,
    "sections": Section,
    "workload_assignments": WorkloadAssignment,
    "audit_events": AuditEvent,
}


def _next_id(ids: list[str], prefix: str) -> int:
    numbers = []
    for value in ids:
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", value)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def run_validation(session: Session) -> dict[str, Any]:
    tables = {
        name: list(session.scalars(select(model).order_by(model.id)))
        for name, model in DATASET_MODELS.items()
    }
    report = validate_tables(tables)
    validation_ids = list(session.scalars(select(ValidationRun.id)))
    exception_ids = list(session.scalars(select(ExceptionRecord.id)))
    audit_ids = list(session.scalars(select(AuditEvent.id)))
    run_number = _next_id(validation_ids, "VAL-")
    run_id = f"VAL-{run_number:06d}"
    now = datetime.now(timezone.utc)

    validation_run = ValidationRun(
        id=run_id,
        total_checks=report["total_checks"],
        passed_checks=report["passed_checks"],
        failed_checks=report["failed_checks"],
        warning_count=report["warning_count"],
        validation_status=report["validation_status"],
        details=report,
        created_at=now,
    )
    session.add(validation_run)

    for issue_index, issue in enumerate(report["issues"], start=1):
        exception_number = _next_id(exception_ids, "EXC-") + issue_index - 1
        session.add(
            ExceptionRecord(
                id=f"EXC-{exception_number:06d}",
                entity_id=issue["entity_id"],
                issue_type=issue["issue_type"],
                description=issue["description"],
                severity=issue["severity"],
                detected_at=now,
                ground_truth_label=issue["ground_truth_label"] == "true",
                resolution_status="open",
                source=issue["source"],
                created_at=now,
            )
        )
    session.add(
        AuditEvent(
            id=f"AUD-{_next_id(audit_ids, 'AUD-'):06d}",
            entity_type="validation_run",
            entity_id=run_id,
            action="dataset_validated",
            details={
                "validation_status": report["validation_status"],
                "total_checks": report["total_checks"],
                "failed_checks": report["failed_checks"],
                "issue_count": len(report["issues"]),
            },
            occurred_at=now,
        )
    )
    session.flush()
    return {**report, "run_id": run_id, "created_at": now.isoformat()}