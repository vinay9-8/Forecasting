import csv
import io
import json

import pytest

from backend.app import create_app


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_URL": "sqlite://",
            "DATA_OUTPUT_DIR": tmp_path,
        }
    )
    yield application
    application.extensions["database_engine"].dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_and_request_validation_are_structured(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}

    response = client.post("/api/forecast/run", json={"term_code": "Fall 2027"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REQUEST"
    assert response.get_json()["error"]["details"]


def test_complete_phase_workflow_and_exports(client):
    generated = client.post(
        "/api/data/generate",
        json={"mode": "starter", "seed": 20261022},
    )
    assert generated.status_code == 201
    generated_data = generated.get_json()["data"]
    assert generated_data["entity_counts"]["courses"] == 24
    assert generated_data["ground_truth_count"] == 5

    summary = client.get("/api/dashboard/summary")
    assert summary.status_code == 200
    assert summary.get_json()["data"]["courses"] == 24
    assert summary.get_json()["data"]["students"] == 160

    forecast = client.post(
        "/api/forecast/run",
        json={"term_code": "2027-Fall", "seed": 20261022},
    )
    assert forecast.status_code == 201, forecast.get_json()
    assert len(forecast.get_json()["data"]["results"]) == 24
    assert len(client.get("/api/forecast/results").get_json()["data"]) == 24

    sections = client.post(
        "/api/allocations/sections", json={"term_code": "2027-Fall"}
    )
    assert sections.status_code == 201, sections.get_json()
    assert client.get("/api/allocations/sections").status_code == 200
    faculty = client.post(
        "/api/allocations/faculty", json={"term_code": "2027-Fall"}
    )
    assert faculty.status_code == 201, faculty.get_json()
    assert client.get("/api/allocations/faculty").status_code == 200

    validation = client.post("/api/validation/run")
    assert validation.status_code == 201, validation.get_json()
    assert validation.get_json()["data"]["detected_scenarios"] == 5
    assert validation.get_json()["data"]["failed_checks"] == 0
    validation_results = client.get("/api/validation/results")
    assert validation_results.status_code == 200
    assert len(validation_results.get_json()["data"]) == 1

    exceptions_response = client.get("/api/exceptions")
    assert exceptions_response.status_code == 200
    exceptions = exceptions_response.get_json()["data"]
    assert len(exceptions) >= 5
    first_exception_id = exceptions[0]["id"]
    resolved = client.patch(f"/api/exceptions/{first_exception_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["resolution_status"] == "resolved"

    csv_response = client.get("/api/export/csv")
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.content_type
    csv_rows = list(csv.DictReader(io.StringIO(csv_response.get_data(as_text=True))))
    assert any(row["entity"] == "forecast_results" for row in csv_rows)
    assert any(row["entity"] == "exceptions" for row in csv_rows)

    json_response = client.get("/api/export/json")
    assert json_response.status_code == 200
    exported = json.loads(json_response.get_data(as_text=True))
    assert len(exported["forecast_results"]) == 24
    assert len(exported["validation_runs"]) == 1

    csv_report = client.get("/api/reports", headers={"Accept": "text/csv"})
    assert "text/csv" in csv_report.content_type
    json_report = client.get("/api/reports", headers={"Accept": "application/json"})
    assert "application/json" in json_report.content_type
    assert "dashboard" in json.loads(json_report.get_data(as_text=True))


def test_data_generation_conflict_never_overwrites_existing_ids(client):
    body = {"mode": "starter", "seed": 20261022}
    assert client.post("/api/data/generate", json=body).status_code == 201

    response = client.post("/api/data/generate", json=body)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "DATA_ALREADY_EXISTS"


def test_section_generation_requires_forecast(client):
    client.post("/api/data/generate", json={"mode": "starter", "seed": 20261022})

    response = client.post(
        "/api/allocations/sections", json={"term_code": "2027-Fall"}
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "FORECAST_REQUIRED"


def test_program_course_and_faculty_create_endpoints_validate_and_persist(client):
    program = client.post(
        "/api/programs",
        json={
            "program_code": "CSE-201",
            "name": "Computer Science BSc",
            "department": "Computer Science",
            "degree_level": "undergraduate",
        },
    )
    assert program.status_code == 201
    program_id = program.get_json()["data"]["id"]

    course = client.post(
        "/api/courses",
        json={
            "program_id": program_id,
            "course_code": "CSE-201-001",
            "name": "Data Structures",
            "credits": 3,
            "category": "required",
            "is_elective": False,
            "max_section_size": 30,
            "popularity_score": 0.6,
        },
    )
    assert course.status_code == 201
    assert course.get_json()["data"]["program_id"] == program_id

    faculty = client.post(
        "/api/faculty",
        json={
            "name": "Faculty One",
            "department": "Computer Science",
            "years_experience": 8,
            "max_weekly_workload": 12,
        },
    )
    assert faculty.status_code == 201

    invalid = client.post(
        "/api/programs",
        json={
            "program_code": "BAD-001",
            "name": "Invalid",
            "department": "Testing",
            "degree_level": "certificate",
        },
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "INVALID_REQUEST"
    assert len(client.get("/api/programs").get_json()["data"]) == 1
    assert len(client.get("/api/courses").get_json()["data"]) == 1
    assert len(client.get("/api/faculty").get_json()["data"]) == 1