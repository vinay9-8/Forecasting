import math

import pytest
from sqlalchemy import select

from backend.database.db import create_database_engine, create_schema, session_factory
from backend.forecasting.demand_forecast import (
    ForecastInputError,
    forecast_course_demand,
    run_forecast,
)
from backend.database.models import (
    Course,
    ForecastRun,
    RegistrationInterest,
    StudentPlan,
)
from backend.generators.master_generator import DEFAULT_SEED, generate_dataset, persist_dataset


def populated_session():
    engine = create_database_engine("sqlite://")
    create_schema(engine)
    session = session_factory(engine)()
    data = generate_dataset("starter", DEFAULT_SEED)
    persist_dataset(session, data)
    session.commit()
    return engine, session


def test_random_forest_forecast_has_complete_output_and_evaluation_metrics():
    engine, session = populated_session()
    try:
        result = run_forecast(session, term_code="2027-Fall")

        assert result["algorithm"] in {"random_forest", "moving_average"}
        assert len(result["results"]) == 24
        assert result["metrics"]["train_samples"] > 0
        assert result["metrics"]["test_samples"] > 0
        assert result["metrics"]["zero_actual_test_samples"] >= 0
        assert set(result["metrics"]["random_forest"]) == {"mae", "rmse", "mape", "r2"}
        assert all(
            math.isfinite(value)
            for metrics in (
                result["metrics"]["random_forest"],
                result["metrics"]["moving_average"],
            )
            for value in metrics.values()
        )
        for item in result["results"]:
            assert item["predicted_enrollment"] >= 0
            assert item["uncertainty"] >= 0
            assert item["recommended_sections"] >= 0
            assert item["demand_category"] in {"High", "Medium", "Low"}
            assert "popularity_score" in item["explanation"]
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_forecast_runs_are_appended_instead_of_overwritten():
    engine, session = populated_session()
    try:
        first = run_forecast(session, term_code="2027-Fall")
        session.commit()
        second = run_forecast(session, term_code="2027-Fall")
        session.commit()

        assert first["run_id"] != second["run_id"]
        assert first["results"] == second["results"]
        assert len(list(session.scalars(select(ForecastRun)))) == 2
    finally:
        session.close()
        engine.dispose()


def test_forecast_rejects_malformed_or_pre_effective_terms():
    engine, session = populated_session()
    try:
        courses = list(session.scalars(select(Course)))
        registrations = list(session.scalars(select(RegistrationInterest)))
        plans = list(session.scalars(select(StudentPlan)))

        with pytest.raises(ForecastInputError, match="term_code"):
            forecast_course_demand(
                courses,
                registrations,
                plans,
                term_code="Fall 2027",
            )
        with pytest.raises(ForecastInputError, match="active courses"):
            forecast_course_demand(
                courses,
                registrations,
                plans,
                term_code="2024-Spring",
            )
    finally:
        session.close()
        engine.dispose()