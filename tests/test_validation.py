from sqlalchemy import select

from backend.database.db import create_database_engine, create_schema, session_factory
from backend.database.models import (
    ExceptionRecord,
    Program,
    ValidationRun,
)
from backend.generators.master_generator import DEFAULT_SEED, generate_dataset, persist_dataset
from backend.validation.runner import run_validation


def test_validation_detects_all_five_isolated_ground_truth_anomalies():
    engine = create_database_engine("sqlite://")
    create_schema(engine)
    session = session_factory(engine)()
    try:
        dataset = generate_dataset("starter", DEFAULT_SEED)
        persist_dataset(session, dataset)
        session.commit()

        report = run_validation(session)
        session.commit()

        assert report["scenario_count"] == 5
        assert report["detected_scenarios"] == 5
        assert all(item["ground_truth_label"] is True for item in report["ground_truth"])
        assert report["total_checks"] >= 11
        assert report["passed_checks"] + report["failed_checks"] == report["total_checks"]
        truth_exceptions = list(
            session.scalars(
                select(ExceptionRecord).where(ExceptionRecord.ground_truth_label.is_(True))
            )
        )
        assert len(truth_exceptions) == 5
        assert {item.issue_type for item in truth_exceptions} == {
            "FACULTY_SKILL_MISMATCH",
            "FACULTY_WORKLOAD_EXCEEDED",
            "SECTION_CAPACITY_TOO_LOW",
            "PREREQUISITE_ORDER_VIOLATION",
            "DUPLICATE_SECTION_ASSIGNMENT",
        }
        assert len(list(session.scalars(select(ValidationRun)))) == 1
    finally:
        session.close()
        engine.dispose()


def test_validation_marks_empty_database_as_failed_without_injecting_anomalies():
    engine = create_database_engine("sqlite://")
    create_schema(engine)
    session = session_factory(engine)()
    try:
        report = run_validation(session)
        assert report["scenario_count"] == 0
        assert report["detected_scenarios"] == 0
        assert report["validation_status"] == "failed"
        assert report["failed_checks"] > 0
    finally:
        session.close()
        engine.dispose()


def test_validation_issues_are_retained_as_exception_history():
    engine = create_database_engine("sqlite://")
    create_schema(engine)
    session = session_factory(engine)()
    try:
        session.add(
            Program(
                id="PRG-000001",
                program_code="TEST-001",
                name="Test Program",
                department="Testing",
                degree_level="undergraduate",
            )
        )
        session.commit()
        first = run_validation(session)
        session.commit()
        second = run_validation(session)
        session.commit()

        assert first["run_id"] != second["run_id"]
        assert len(list(session.scalars(select(ValidationRun)))) == 2
        exceptions = list(session.scalars(select(ExceptionRecord)))
        assert len(exceptions) == 2
        assert all(item.issue_type == "DATASET_EMPTY" for item in exceptions)
        assert all(item.ground_truth_label is False for item in exceptions)
    finally:
        session.close()
        engine.dispose()