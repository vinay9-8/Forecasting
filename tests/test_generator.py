import csv
import json

from sqlalchemy import func, select

from backend.database.db import create_database_engine, create_schema, session_factory
from backend.database.models import Course, Program, RegistrationInterest, StudentPlan
from backend.exports.data_export import export_database_snapshot
from backend.generators.master_generator import (
    DEFAULT_SEED,
    export_dataset,
    generate_dataset,
    persist_dataset,
    validate_dataset,
)
from backend.validation.runner import run_validation


def test_starter_dataset_has_related_rows_and_is_deterministic():
    first = generate_dataset("starter", DEFAULT_SEED)
    second = generate_dataset("starter", DEFAULT_SEED)

    assert first == second
    assert len(first["programs"]) == 4
    assert len(first["courses"]) == 24
    assert len(first["faculty"]) == 12
    assert len(first["student_plans"]) == 160
    assert len(first["rooms"]) == 8
    assert len(first["registration_interests"]) >= 160 * 4 * 2
    assert first["audit_events"][0]["details"]["seed"] == DEFAULT_SEED
    validate_dataset(first)


def test_full_mode_meets_required_baseline_counts():
    data = generate_dataset("full", DEFAULT_SEED)

    assert len(data["programs"]) == 100
    assert len(data["courses"]) == 1_000
    assert len(data["faculty"]) == 500
    assert len(data["student_plans"]) == 20_000
    assert len(data["registration_interests"]) >= 20_000 * 4 * 2


def test_export_writes_csv_json_and_stable_manifest(tmp_path):
    data = generate_dataset("starter", DEFAULT_SEED)

    manifest = export_dataset(data, tmp_path)

    assert manifest["seed"] == DEFAULT_SEED
    assert manifest["entities"]["courses"]["row_count"] == 24
    with (tmp_path / "courses.csv").open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 24
    exported_courses = json.loads((tmp_path / "courses.json").read_text(encoding="utf-8"))
    assert exported_courses[0]["id"] == "CRS-000001"
    assert (tmp_path / "source_manifest.json").exists()


def test_dataset_persists_to_sqlite_with_foreign_keys():
    data = generate_dataset("starter", DEFAULT_SEED)
    engine = create_database_engine("sqlite://")
    try:
        create_schema(engine)
        session = session_factory(engine)()
        try:
            persist_dataset(session, data)
            session.commit()
            assert session.scalar(select(func.count()).select_from(Program)) == 4
            assert session.scalar(select(func.count()).select_from(Course)) == 24
            assert session.scalar(select(func.count()).select_from(StudentPlan)) == 160
            assert session.scalar(
                select(func.count()).select_from(RegistrationInterest)
            ) == len(data["registration_interests"])
        finally:
            session.close()
    finally:
        engine.dispose()


def test_database_snapshot_exports_each_table_ground_truth_and_sql(tmp_path):
    data = generate_dataset("starter", DEFAULT_SEED)
    engine = create_database_engine("sqlite://")
    try:
        create_schema(engine)
        session = session_factory(engine)()
        try:
            persist_dataset(session, data)
            session.commit()
            run_validation(session)
            session.commit()

            manifest = export_database_snapshot(session, tmp_path)

            assert manifest["entities"]["forecast_runs"]["row_count"] == 0
            assert manifest["entities"]["courses"]["row_count"] == 24
            assert manifest["ground_truth"]["row_count"] == 5
            assert (tmp_path / "courses.csv").exists()
            assert (tmp_path / "courses.json").exists()
            assert (tmp_path / "forecast_results.csv").exists()
            assert (tmp_path / "exceptions.json").exists()
            assert (tmp_path / "ground_truth.csv").exists()
            assert "INSERT INTO `programs`" in (tmp_path / "seed.sql").read_text(
                encoding="utf-8"
            )
        finally:
            session.close()
    finally:
        engine.dispose()
