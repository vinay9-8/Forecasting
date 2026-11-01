from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, time, timezone
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request
from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.allocation.faculty_allocator import assign_faculty
from backend.allocation.section_allocator import (
    AllocationInputError,
    allocate_sections,
)
from backend.database.db import session_factory
from backend.database.models import (
    AuditEvent,
    Availability,
    Course,
    ExceptionRecord,
    Faculty,
    FacultySkill,
    ForecastResult,
    ForecastRun,
    Program,
    RegistrationInterest,
    Room,
    Section,
    StudentPlan,
    ValidationRun,
    WorkloadAssignment,
)
from backend.forecasting.demand_forecast import ForecastInputError, run_forecast
from backend.generators.master_generator import (
    ENTITY_MODELS,
    export_dataset,
    generate_dataset,
    persist_dataset,
)
from backend.schemas import (
    CourseCreate,
    FacultyCreate,
    ForecastRequest,
    GenerationRequest,
    ProgramCreate,
    TermRequest,
)
from backend.validation.runner import run_validation

api = Blueprint("api", __name__, url_prefix="/api")
EXPORT_MODELS = {
    **ENTITY_MODELS,
    "forecast_runs": ForecastRun,
    "forecast_results": ForecastResult,
    "exceptions": ExceptionRecord,
    "validation_runs": ValidationRun,
}


def _session() -> Session:
    return session_factory(current_app.extensions["database_engine"])()


def _error(
    code: str, message: str, status: int, details: Any | None = None
) -> tuple[Response, int]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def _validated(model: type, body: Any) -> Any:
    try:
        return model.model_validate(body)
    except ValidationError as error:
        details = [
            {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
            for item in error.errors()
        ]
        raise RequestBodyError(details) from error


class RequestBodyError(ValueError):
    def __init__(self, details: list[dict[str, str]]):
        self.details = details
        super().__init__("The request body is invalid.")


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _record(record: Any) -> dict[str, Any]:
    return {
        column.name: _json_value(getattr(record, column.name))
        for column in record.__table__.columns
    }


def _rows(session: Session, model: type, limit: int = 5000) -> list[Any]:
    return list(
        session.scalars(select(model).order_by(model.id).limit(limit))
    )


def _next_id(session: Session, model: type, prefix: str) -> int:
    identifiers = list(session.scalars(select(model.id)))
    numbers = []
    for identifier in identifiers:
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", identifier)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _next_audit_id(session: Session) -> str:
    return f"AUD-{_next_id(session, AuditEvent, 'AUD-'):06d}"


def _create_exception(
    session: Session,
    *,
    entity_id: str,
    issue_type: str,
    description: str,
    severity: str,
    ground_truth_label: bool = False,
    source: str = "allocation",
) -> ExceptionRecord:
    if source == "allocation":
        existing = session.scalar(
            select(ExceptionRecord)
            .where(
                ExceptionRecord.entity_id == entity_id,
                ExceptionRecord.issue_type == issue_type,
                ExceptionRecord.resolution_status == "open",
            )
            .limit(1)
        )
        if existing:
            return existing
    number = _next_id(session, ExceptionRecord, "EXC-")
    now = datetime.now(timezone.utc)
    record = ExceptionRecord(
        id=f"EXC-{number:06d}",
        entity_id=entity_id,
        issue_type=issue_type,
        description=description,
        severity=severity,
        detected_at=now,
        ground_truth_label=ground_truth_label,
        resolution_status="open",
        source=source,
        created_at=now,
    )
    session.add(record)
    return record


def _forecast_records(session: Session, term_code: str | None = None) -> list[dict[str, Any]]:
    statement = (
        select(ForecastResult, ForecastRun, Course)
        .join(ForecastRun, ForecastResult.run_id == ForecastRun.id)
        .join(Course, ForecastResult.course_id == Course.id)
        .order_by(ForecastRun.created_at.desc(), Course.course_code)
    )
    if term_code:
        statement = statement.where(ForecastRun.term_code == term_code)
    results = session.execute(statement).all()
    latest_seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for result, run, course in results:
        if course.id in latest_seen:
            continue
        latest_seen.add(course.id)
        records.append(
            {
                **_record(result),
                "term_code": run.term_code,
                "algorithm": run.algorithm,
                "course_code": course.course_code,
                "course_name": course.name,
                "forecast_run_id": run.id,
            }
        )
    return records


def _section_records(session: Session, term_code: str | None = None) -> list[dict[str, Any]]:
    statement = (
        select(Section, Course, Room)
        .join(Course, Section.course_id == Course.id)
        .join(Room, Section.room_id == Room.id)
        .order_by(Section.term_code.desc(), Course.course_code, Section.section_number)
    )
    if term_code:
        statement = statement.where(Section.term_code == term_code)
    records = []
    for section, course, room in session.execute(statement).all():
        records.append(
            {
                **_record(section),
                "course_code": course.course_code,
                "course_name": course.name,
                "room_code": room.room_code,
            }
        )
    return records


def _faculty_allocation_records(
    session: Session, term_code: str | None = None
) -> list[dict[str, Any]]:
    statement = (
        select(WorkloadAssignment, Section, Course, Faculty)
        .join(Section, WorkloadAssignment.section_id == Section.id)
        .join(Course, Section.course_id == Course.id)
        .join(Faculty, WorkloadAssignment.faculty_id == Faculty.id)
        .order_by(Section.term_code.desc(), Faculty.name, Course.course_code)
    )
    if term_code:
        statement = statement.where(Section.term_code == term_code)
    return [
        {
            **_record(assignment),
            "term_code": section.term_code,
            "section_id": section.id,
            "course_code": course.course_code,
            "faculty_name": faculty.name,
        }
        for assignment, section, course, faculty in session.execute(statement).all()
    ]


def _table_data(session: Session) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}
    for name, model in EXPORT_MODELS.items():
        data[name] = [_record(item) for item in _rows(session, model, limit=1_000_000)]
    return data


@api.get("/health")
def health() -> Response:
    return jsonify({"status": "ok"})


@api.get("/dashboard/summary")
def dashboard_summary() -> tuple[Response, int] | Response:
    session = _session()
    try:
        counts = {
            "programs": session.scalar(select(func.count()).select_from(Program)) or 0,
            "courses": session.scalar(select(func.count()).select_from(Course)) or 0,
            "students": session.scalar(select(func.count()).select_from(StudentPlan)) or 0,
            "faculty": session.scalar(select(func.count()).select_from(Faculty)) or 0,
            "sections": session.scalar(select(func.count()).select_from(Section)) or 0,
        }
        latest_run = session.scalar(
            select(ForecastRun).order_by(ForecastRun.created_at.desc()).limit(1)
        )
        forecast_results = (
            list(
                session.scalars(
                    select(ForecastResult).where(
                        ForecastResult.run_id == latest_run.id
                    )
                )
            )
            if latest_run
            else []
        )
        forecast_history = []
        actual_by_term: dict[str, int] = {}
        for term_code, amount in session.execute(
            select(
                RegistrationInterest.term_code,
                func.count(RegistrationInterest.id),
            )
            .where(RegistrationInterest.interest_status.in_(("registered", "completed")))
            .group_by(RegistrationInterest.term_code)
        ):
            actual_by_term[term_code] = amount
        forecast_by_term: dict[str, list[int]] = {}
        for run in session.scalars(select(ForecastRun).order_by(ForecastRun.created_at)):
            run_total = session.scalar(
                select(func.sum(ForecastResult.predicted_enrollment)).where(
                    ForecastResult.run_id == run.id
                )
            ) or 0
            forecast_by_term.setdefault(run.term_code, []).append(int(run_total))
        for term_code in sorted(set(actual_by_term) | set(forecast_by_term)):
            forecast_history.append(
                {
                    "term": term_code,
                    "actual": actual_by_term.get(term_code, 0),
                    "predicted": (
                        forecast_by_term[term_code][-1]
                        if term_code in forecast_by_term
                        else 0
                    ),
                }
            )

        demand_counts = {"High": 0, "Medium": 0, "Low": 0}
        for result in forecast_results:
            demand_counts[result.demand_category] += 1
        latest_section_term = (
            latest_run.term_code
            if latest_run
            else session.scalar(select(Section.term_code).order_by(Section.term_code.desc()).limit(1))
        )
        assigned_hours_expression = WorkloadAssignment.weekly_hours
        if latest_section_term:
            assigned_hours_expression = case(
                (Section.term_code == latest_section_term, WorkloadAssignment.weekly_hours),
                else_=0,
            )
        workload_statement = (
            select(
                Faculty,
                func.coalesce(func.sum(assigned_hours_expression), 0),
            )
            .outerjoin(WorkloadAssignment, Faculty.id == WorkloadAssignment.faculty_id)
            .outerjoin(Section, WorkloadAssignment.section_id == Section.id)
            .group_by(Faculty.id)
            .order_by(Faculty.name)
            .limit(12)
        )
        workload_points = []
        for faculty, assigned_hours in session.execute(
            workload_statement
        ):
            workload_points.append(
                {
                    "faculty": faculty.name,
                    "assigned_hours": float(assigned_hours),
                    "max_hours": faculty.max_weekly_workload,
                }
            )
        capacity_points = []
        for section, course in session.execute(
            select(Section, Course)
            .join(Course, Section.course_id == Course.id)
            .order_by(Section.id.desc())
            .limit(12)
        ):
            capacity_points.append(
                {
                    "course": course.course_code,
                    "capacity": section.capacity,
                    "enrollment": section.expected_enrollment,
                }
            )
        status_statement = select(
            func.count(func.distinct(WorkloadAssignment.section_id))
        ).where(WorkloadAssignment.assignment_status == "assigned")
        if latest_section_term:
            status_statement = status_statement.join(
                Section, WorkloadAssignment.section_id == Section.id
            ).where(Section.term_code == latest_section_term)
        assigned_sections = session.scalar(status_statement) or 0
        unassigned_statement = select(func.count()).select_from(Section).where(
            Section.lifecycle_state == "unassigned"
        )
        if latest_section_term:
            unassigned_statement = unassigned_statement.where(
                Section.term_code == latest_section_term
            )
        faculty_status = [
            {"status": "Assigned", "count": assigned_sections},
            {
                "status": "Unassigned",
                "count": session.scalar(unassigned_statement) or 0,
            },
        ]
        unmet: dict[str, int] = {}
        for event_record in session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == "sections_allocated")
            .order_by(AuditEvent.occurred_at.desc())
        ):
            raw = event_record.details.get("unmet_demand", {})
            if raw:
                unmet = raw
                break
        allocation_section_count = (
            session.scalar(
                select(func.count()).select_from(Section).where(
                    Section.term_code == latest_section_term
                )
            )
            if latest_section_term
            else counts["sections"]
        ) or 0
        summary = {
            **counts,
            "predicted_enrollment": sum(
                result.predicted_enrollment for result in forecast_results
            ),
            "unmet_demand": sum(unmet.values()),
            "allocation_success_rate": (
                round(
                    100 * assigned_sections / allocation_section_count,
                    1,
                )
                if allocation_section_count
                else 0.0
            ),
            "forecast_history": forecast_history,
            "demand_distribution": [
                {"category": category, "count": amount}
                for category, amount in demand_counts.items()
            ],
            "faculty_workload": workload_points,
            "capacity_utilization": capacity_points,
            "faculty_status": faculty_status,
            "unmet_by_course": [
                {"course": key, "unmet": value} for key, value in unmet.items()
            ],
        }
        return jsonify({"data": summary})
    except Exception:
        session.rollback()
        current_app.logger.exception("Failed to build dashboard summary.")
        return _error("INTERNAL_ERROR", "Could not load dashboard summary.", 500)
    finally:
        session.close()


@api.get("/programs")
def get_programs() -> Response:
    session = _session()
    try:
        return jsonify({"data": [_record(item) for item in _rows(session, Program)]})
    finally:
        session.close()


@api.post("/programs")
def create_program() -> tuple[Response, int]:
    session = _session()
    try:
        body = _validated(ProgramCreate, request.get_json(silent=False))
        item = Program(
            id=f"PRG-{_next_id(session, Program, 'PRG-'):06d}",
            **body.model_dump(),
        )
        session.add(item)
        session.commit()
        return jsonify({"data": _record(item)}), 201
    except RequestBodyError as error:
        session.rollback()
        return _error("INVALID_REQUEST", str(error), 400, error.details)
    except IntegrityError:
        session.rollback()
        return _error("CONFLICT", "Program code already exists.", 409)
    finally:
        session.close()


@api.get("/courses")
def get_courses() -> Response:
    session = _session()
    try:
        return jsonify({"data": [_record(item) for item in _rows(session, Course)]})
    finally:
        session.close()


@api.post("/courses")
def create_course() -> tuple[Response, int]:
    session = _session()
    try:
        body = _validated(CourseCreate, request.get_json(silent=False))
        if session.get(Program, body.program_id) is None:
            return _error("NOT_FOUND", "The requested program does not exist.", 404)
        item = Course(
            id=f"CRS-{_next_id(session, Course, 'CRS-'):06d}",
            **body.model_dump(),
        )
        session.add(item)
        session.commit()
        return jsonify({"data": _record(item)}), 201
    except RequestBodyError as error:
        session.rollback()
        return _error("INVALID_REQUEST", str(error), 400, error.details)
    except IntegrityError:
        session.rollback()
        return _error("CONFLICT", "Course code already exists.", 409)
    finally:
        session.close()


@api.get("/students")
def get_students() -> Response:
    session = _session()
    try:
        return jsonify({"data": [_record(item) for item in _rows(session, StudentPlan)]})
    finally:
        session.close()


@api.get("/faculty")
def get_faculty() -> Response:
    session = _session()
    try:
        return jsonify({"data": [_record(item) for item in _rows(session, Faculty)]})
    finally:
        session.close()


@api.post("/faculty")
def create_faculty() -> tuple[Response, int]:
    session = _session()
    try:
        body = _validated(FacultyCreate, request.get_json(silent=False))
        item = Faculty(
            id=f"FAC-{_next_id(session, Faculty, 'FAC-'):06d}",
            **body.model_dump(),
        )
        session.add(item)
        session.commit()
        return jsonify({"data": _record(item)}), 201
    except RequestBodyError as error:
        session.rollback()
        return _error("INVALID_REQUEST", str(error), 400, error.details)
    finally:
        session.close()


@api.post("/data/generate")
def generate_data() -> tuple[Response, int] | Response:
    session = _session()
    try:
        body = _validated(GenerationRequest, request.get_json(silent=False))
        dataset = generate_dataset(body.mode, body.seed)
        persist_dataset(session, dataset)
        session.commit()
        output_dir = (
            current_app.config["DATA_OUTPUT_DIR"] / body.mode
        )
        manifest = export_dataset(dataset, output_dir)
        return jsonify(
            {
                "data": {
                    "mode": body.mode,
                    "seed": body.seed,
                    "entity_counts": {
                        name: details["row_count"]
                        for name, details in manifest["entities"].items()
                    },
                    "ground_truth_count": manifest["ground_truth"]["row_count"],
                }
            }
        ), 201
    except RequestBodyError as error:
        session.rollback()
        return _error("INVALID_REQUEST", str(error), 400, error.details)
    except IntegrityError:
        session.rollback()
        return _error(
            "DATA_ALREADY_EXISTS",
            "Generated IDs already exist; generation never overwrites prior records.",
            409,
        )
    except Exception:
        session.rollback()
        current_app.logger.exception("Synthetic dataset generation failed.")
        return _error("GENERATION_FAILED", "Could not generate the dataset.", 500)
    finally:
        session.close()


@api.post("/forecast/run")
def forecast_run() -> tuple[Response, int] | Response:
    session = _session()
    try:
        body = _validated(ForecastRequest, request.get_json(silent=False))
        result = run_forecast(session, term_code=body.term_code, seed=body.seed)
        session.commit()
        return jsonify({"data": result}), 201
    except RequestBodyError as error:
        session.rollback()
        return _error("INVALID_REQUEST", str(error), 400, error.details)
    except ForecastInputError as error:
        session.rollback()
        return _error("FORECAST_INPUT_ERROR", str(error), 422)
    except Exception:
        session.rollback()
        current_app.logger.exception("Demand forecast failed.")
        return _error("FORECAST_FAILED", "Could not run the demand forecast.", 500)
    finally:
        session.close()


@api.get("/forecast/results")
def forecast_results() -> Response:
    session = _session()
    try:
        records = _forecast_records(session, request.args.get("term_code"))
        return jsonify({"data": records})
    finally:
        session.close()


@api.post("/allocations/sections")
def sections_allocate() -> tuple[Response, int] | Response:
    session = _session()
    try:
        body = _validated(TermRequest, request.get_json(silent=False))
        latest_run = session.scalar(
            select(ForecastRun)
            .where(ForecastRun.term_code == body.term_code)
            .order_by(ForecastRun.created_at.desc())
            .limit(1)
        )
        if latest_run is None:
            return _error(
                "FORECAST_REQUIRED",
                "Run a forecast for this term before generating sections.",
                409,
            )
        predicted_demand = {
            result.course_id: result.predicted_enrollment
            for result in session.scalars(
                select(ForecastResult).where(ForecastResult.run_id == latest_run.id)
            )
        }
        plan = allocate_sections(
            session, predicted_demand, term_code=body.term_code
        )
        for issue in plan.exceptions:
            _create_exception(
                session,
                entity_id=issue["entity_id"],
                issue_type=issue["issue_type"],
                description=issue["description"],
                severity=issue["severity"],
                source="allocation",
            )
        for course_id, seats in plan.unmet_demand.items():
            _create_exception(
                session,
                entity_id=course_id,
                issue_type="UNMET_DEMAND",
                description=f"{seats} predicted student(s) cannot be accommodated in {body.term_code}.",
                severity="medium",
                source="allocation",
            )
        session.commit()
        return jsonify(
            {
                "data": {
                    "term_code": plan.term_code,
                    "sections": [_record(item) for item in plan.sections],
                    "assignments": [_record(item) for item in plan.assignments],
                    "unmet_demand": plan.unmet_demand,
                    "exceptions": plan.exceptions,
                    "metrics": plan.metrics,
                }
            }
        ), 201
    except RequestBodyError as error:
        session.rollback()
        return _error("INVALID_REQUEST", str(error), 400, error.details)
    except AllocationInputError as error:
        session.rollback()
        return _error("ALLOCATION_INPUT_ERROR", str(error), 422)
    except Exception:
        session.rollback()
        current_app.logger.exception("Section allocation failed.")
        return _error("ALLOCATION_FAILED", "Could not generate sections.", 500)
    finally:
        session.close()


@api.get("/allocations/sections")
def get_sections() -> Response:
    session = _session()
    try:
        return jsonify({"data": _section_records(session, request.args.get("term_code"))})
    finally:
        session.close()


@api.post("/allocations/faculty")
def allocate_faculty_route() -> tuple[Response, int] | Response:
    session = _session()
    try:
        body = _validated(TermRequest, request.get_json(silent=False))
        sections = list(
            session.scalars(
                select(Section)
                .where(
                    Section.term_code == body.term_code,
                    Section.lifecycle_state == "unassigned",
                )
                .order_by(Section.id)
            )
        )
        existing_assignments = list(
            session.scalars(
                select(WorkloadAssignment)
                .join(Section, WorkloadAssignment.section_id == Section.id)
                .where(
                    Section.term_code == body.term_code,
                    WorkloadAssignment.assignment_status == "assigned",
                )
            )
        )
        courses = list(session.scalars(select(Course)))
        faculty = list(session.scalars(select(Faculty)))
        skills = list(session.scalars(select(FacultySkill)))
        availability = list(session.scalars(select(Availability)))
        all_sections = list(
            session.scalars(select(Section).where(Section.term_code == body.term_code))
        )
        existing_ids = list(session.scalars(select(WorkloadAssignment.id)))
        start_id = _next_id(
            session, WorkloadAssignment, f"WLA-{body.term_code[:4]}-"
        )
        season = body.term_code.split("-", 1)[1]
        effective_on = date(
            int(body.term_code[:4]),
            {"Winter": 1, "Spring": 1, "Summer": 5, "Fall": 8}[season],
            1,
        )
        faculty = [
            item
            for item in faculty
            if item.lifecycle_state == "active"
            and item.effective_from <= effective_on
            and (item.effective_to is None or item.effective_to >= effective_on)
        ]
        skills = [
            item
            for item in skills
            if item.lifecycle_state == "active"
            and item.effective_from <= effective_on
            and (item.effective_to is None or item.effective_to >= effective_on)
        ]
        availability = [
            item
            for item in availability
            if item.lifecycle_state == "active"
            and item.effective_from <= effective_on
            and (item.effective_to is None or item.effective_to >= effective_on)
        ]
        assignments, exceptions = assign_faculty(
            sections,
            courses_by_id={item.id: item for item in courses},
            faculty_by_id={item.id: item for item in faculty},
            skills=skills,
            availability=availability,
            prior_assignments=existing_assignments,
            existing_sections=all_sections,
            assignment_id_start=start_id,
            year=int(body.term_code[:4]),
        )
        session.add_all(assignments)
        for issue in exceptions:
            _create_exception(
                session,
                entity_id=issue["entity_id"],
                issue_type=issue["issue_type"],
                description=issue["description"],
                severity=issue["severity"],
            )
        session.commit()
        return jsonify(
            {
                "data": {
                    "term_code": body.term_code,
                    "assignments": [_record(item) for item in assignments],
                    "exceptions": exceptions,
                    "previous_assignment_count": len(existing_ids),
                }
            }
        ), 201
    except RequestBodyError as error:
        session.rollback()
        return _error("INVALID_REQUEST", str(error), 400, error.details)
    except Exception:
        session.rollback()
        current_app.logger.exception("Faculty allocation failed.")
        return _error("FACULTY_ALLOCATION_FAILED", "Could not allocate faculty.", 500)
    finally:
        session.close()


@api.get("/allocations/faculty")
def get_faculty_allocations() -> Response:
    session = _session()
    try:
        return jsonify(
            {"data": _faculty_allocation_records(session, request.args.get("term_code"))}
        )
    finally:
        session.close()


@api.get("/exceptions")
def get_exceptions() -> Response:
    session = _session()
    try:
        rows = list(
            session.scalars(
                select(ExceptionRecord)
                .order_by(ExceptionRecord.detected_at.desc(), ExceptionRecord.id)
                .limit(5000)
            )
        )
        return jsonify({"data": [_record(item) for item in rows]})
    finally:
        session.close()


@api.patch("/exceptions/<exception_id>/resolve")
def resolve_exception(exception_id: str) -> tuple[Response, int] | Response:
    session = _session()
    try:
        record = session.get(ExceptionRecord, exception_id)
        if record is None:
            return _error("NOT_FOUND", "Exception not found.", 404)
        if record.resolution_status == "resolved":
            return jsonify({"data": _record(record)})
        record.resolution_status = "resolved"
        now = datetime.now(timezone.utc)
        session.add(
            AuditEvent(
                id=_next_audit_id(session),
                entity_type="exception",
                entity_id=record.id,
                action="exception_resolved",
                details={"issue_type": record.issue_type},
                occurred_at=now,
            )
        )
        session.commit()
        return jsonify({"data": _record(record)})
    finally:
        session.close()


@api.post("/validation/run")
def validate_dataset_route() -> tuple[Response, int] | Response:
    session = _session()
    try:
        result = run_validation(session)
        session.commit()
        return jsonify({"data": result}), 201
    except Exception:
        session.rollback()
        current_app.logger.exception("Dataset validation failed.")
        return _error("VALIDATION_FAILED", "Could not validate the dataset.", 500)
    finally:
        session.close()


@api.get("/validation/results")
def get_validation_results() -> Response | tuple[Response, int]:
    session = _session()
    try:
        run = session.scalar(
            select(ValidationRun).order_by(ValidationRun.created_at.desc()).limit(1)
        )
        if run is None:
            return jsonify({"data": []})
        return jsonify(
            {
                "data": [
                    {
                        "id": run.id,
                        "total_checks": run.total_checks,
                        "passed_checks": run.passed_checks,
                        "failed_checks": run.failed_checks,
                        "warning_count": run.warning_count,
                        "validation_status": run.validation_status,
                        "created_at": _json_value(run.created_at),
                        "details": run.details,
                    }
                ]
            }
        )
    finally:
        session.close()


@api.get("/export/csv")
def export_csv() -> Response:
    session = _session()
    try:
        tables = _table_data(session)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=("entity", "id", "record_json"))
        writer.writeheader()
        for entity, rows in tables.items():
            for row in rows:
                writer.writerow(
                    {
                        "entity": entity,
                        "id": row.get("id", ""),
                        "record_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
                    }
                )
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="academic-data.csv"'},
        )
    finally:
        session.close()


@api.get("/export/json")
def export_json() -> Response:
    session = _session()
    try:
        return Response(
            json.dumps(_table_data(session), ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": 'attachment; filename="academic-data.json"'},
        )
    finally:
        session.close()


@api.get("/reports")
def reports() -> Response:
    session = _session()
    try:
        summary = {
            "dashboard": _dashboard_data(),
            "forecasts": _forecast_records(session),
            "sections": _section_records(session),
            "faculty_allocations": _faculty_allocation_records(session),
            "exceptions": [
                _record(item)
                for item in session.scalars(select(ExceptionRecord).order_by(ExceptionRecord.id))
            ],
            "validations": [
                _record(item)
                for item in session.scalars(select(ValidationRun).order_by(ValidationRun.id))
            ],
        }
        if "text/csv" in request.headers.get("Accept", ""):
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=("report_section", "record_json"))
            writer.writeheader()
            for section, records in summary.items():
                iterable = records if isinstance(records, list) else [records]
                for record in iterable:
                    writer.writerow(
                        {
                            "report_section": section,
                            "record_json": json.dumps(
                                record, ensure_ascii=False, sort_keys=True
                            ),
                        }
                    )
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": 'attachment; filename="academic-report.csv"'},
            )
        return Response(
            json.dumps(summary, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": 'attachment; filename="academic-report.json"'},
        )
    finally:
        session.close()


def _dashboard_data() -> dict[str, Any]:
    response = dashboard_summary()
    body = response.get_json()
    return body["data"]