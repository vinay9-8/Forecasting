from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import mean, pstdev
from typing import Any, Sequence

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import (
    AuditEvent,
    Course,
    ForecastResult,
    ForecastRun,
    RegistrationInterest,
    StudentPlan,
)

TERM_PATTERN = re.compile(r"^(?P<year>\d{4})-(Spring|Summer|Fall|Winter)$")
TERM_SEASONS = {"Winter": 0, "Spring": 1, "Summer": 2, "Fall": 3}
ACTUAL_STATUSES = {"registered", "completed"}
INTEREST_STATUSES = {"interested", "waitlisted"}
DEFAULT_SEED = 20261022
MIN_TRAIN_SAMPLES = 5


class ForecastInputError(ValueError):
    """Raised when a requested forecast term is invalid."""


def _term_key(term_code: str) -> tuple[int, int]:
    match = TERM_PATTERN.fullmatch(term_code)
    if not match:
        raise ForecastInputError(
            "term_code must use YYYY-Spring|Summer|Fall|Winter format."
        )
    return int(match.group("year")), TERM_SEASONS[term_code.split("-", 1)[1]]


def _feature_vector(
    course: Course,
    *,
    term_code: str,
    previous_actuals: Sequence[int],
    current_interest: int,
    program_plan_count: int,
) -> list[float]:
    year, season = _term_key(term_code)
    history = list(previous_actuals[-3:])
    average_history = mean(history) if history else 0.0
    prior_demand = float(history[-1]) if history else 0.0
    return [
        prior_demand,
        average_history,
        float(current_interest),
        float(course.popularity_score),
        float(program_plan_count),
        float(season),
        float(year % 10),
        float(course.credits),
        float(course.is_elective),
    ]


def _evaluation_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    if not actual:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "r2": 0.0}
    nonzero_pairs = [
        (real, guess) for real, guess in zip(actual, predicted) if real != 0
    ]
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(math.sqrt(mean_squared_error(actual, predicted))),
        "mape": (
            float(
                mean(
                    abs(real - guess) / abs(real) * 100
                    for real, guess in nonzero_pairs
                )
            )
            if nonzero_pairs
            else 0.0
        ),
        "r2": float(r2_score(actual, predicted)) if len(actual) >= 2 else 0.0,
    }


def _term_date(term_code: str) -> date:
    year, season = term_code.split("-", 1)
    month = {"Spring": 1, "Winter": 1, "Summer": 5, "Fall": 8}[season]
    return date(int(year), month, 1)


def forecast_course_demand(
    courses: Sequence[Course],
    registrations: Sequence[RegistrationInterest],
    student_plans: Sequence[StudentPlan],
    *,
    term_code: str,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Train/evaluate a Random Forest against a moving-average baseline and forecast every course."""
    target_key = _term_key(term_code)
    active_courses = [
        course
        for course in courses
        if course.lifecycle_state == "active"
        and course.effective_from <= _term_date(term_code)
        and (course.effective_to is None or course.effective_to >= _term_date(term_code))
    ]
    if not active_courses:
        raise ForecastInputError("No active courses are effective for the requested term.")

    terms_by_course: dict[str, set[str]] = defaultdict(set)
    actual_counts: dict[tuple[str, str], int] = defaultdict(int)
    interest_counts: dict[tuple[str, str], int] = defaultdict(int)
    for registration in registrations:
        if registration.lifecycle_state != "active":
            continue
        key = (registration.course_id, registration.term_code)
        terms_by_course[registration.course_id].add(registration.term_code)
        if registration.interest_status in ACTUAL_STATUSES:
            actual_counts[key] += 1
        elif registration.interest_status in INTEREST_STATUSES:
            interest_counts[key] += 1

    plans_per_program: dict[str, int] = defaultdict(int)
    target_date = _term_date(term_code)
    for plan in student_plans:
        if (
            plan.lifecycle_state == "active"
            and plan.effective_from <= target_date
            and (plan.effective_to is None or plan.effective_to >= target_date)
        ):
            plans_per_program[plan.program_id] += 1

    all_historical_terms = sorted(
        {
            term
            for term_set in terms_by_course.values()
            for term in term_set
            if _term_key(term) < target_key
        },
        key=_term_key,
    )
    if not all_historical_terms:
        raise ForecastInputError(
            "No historical registration terms exist before the requested forecast term."
        )

    training_features: list[list[float]] = []
    training_targets: list[float] = []
    baseline_values: list[float] = []
    for course in active_courses:
        course_terms = sorted(
            (
                term
                for term in terms_by_course.get(course.id, ())
                if _term_key(term) < target_key
            ),
            key=_term_key,
        )
        history: list[int] = []
        for historical_term in course_terms:
            interest = interest_counts[(course.id, historical_term)]
            actual = actual_counts[(course.id, historical_term)]
            training_features.append(
                _feature_vector(
                    course,
                    term_code=historical_term,
                    previous_actuals=history,
                    current_interest=interest,
                    program_plan_count=plans_per_program[course.program_id],
                )
            )
            training_targets.append(float(actual))
            baseline_values.append(float(mean(history[-3:])) if history else 0.0)
            history.append(actual)

    if len(training_targets) < MIN_TRAIN_SAMPLES:
        raise ForecastInputError(
            f"At least {MIN_TRAIN_SAMPLES} historical course-term observations are required."
        )

    indices = np.arange(len(training_targets))
    train_indices, test_indices = train_test_split(
        indices, test_size=0.2, random_state=seed
    )
    x = np.asarray(training_features, dtype=float)
    y = np.asarray(training_targets, dtype=float)
    evaluation_forest = RandomForestRegressor(
        n_estimators=160,
        min_samples_leaf=2,
        random_state=seed,
        n_jobs=1,
    )
    evaluation_forest.fit(x[train_indices], y[train_indices])
    forest_test = np.maximum(0, evaluation_forest.predict(x[test_indices]))
    baseline_test = np.asarray(
        [baseline_values[index] for index in test_indices], dtype=float
    )
    actual_test = y[test_indices]
    metrics = {
        "random_forest": _evaluation_metrics(actual_test.tolist(), forest_test.tolist()),
        "moving_average": _evaluation_metrics(
            actual_test.tolist(), baseline_test.tolist()
        ),
        "train_samples": int(len(train_indices)),
        "test_samples": int(len(test_indices)),
        "zero_actual_test_samples": int(np.count_nonzero(actual_test == 0)),
        "seed": seed,
    }
    algorithm = (
        "random_forest"
        if metrics["random_forest"]["mae"] <= metrics["moving_average"]["mae"]
        else "moving_average"
    )
    forest = RandomForestRegressor(
        n_estimators=160,
        min_samples_leaf=2,
        random_state=seed,
        n_jobs=1,
    )
    forest.fit(x, y)

    predictions: list[dict[str, Any]] = []
    latest_term = all_historical_terms[-1]
    for course in active_courses:
        history = [
            actual_counts[(course.id, term)]
            for term in sorted(
                (
                    term
                    for term in terms_by_course.get(course.id, ())
                    if _term_key(term) < target_key
                ),
                key=_term_key,
            )
        ]
        course_latest_term = max(
            (
                term
                for term in terms_by_course.get(course.id, ())
                if _term_key(term) < target_key
            ),
            key=_term_key,
            default=latest_term,
        )
        recent_interest = interest_counts[(course.id, course_latest_term)]
        vector = np.asarray(
            [
                _feature_vector(
                    course,
                    term_code=term_code,
                    previous_actuals=history,
                    current_interest=recent_interest,
                    program_plan_count=plans_per_program[course.program_id],
                )
            ],
            dtype=float,
        )
        tree_predictions = np.asarray(
            [estimator.predict(vector)[0] for estimator in forest.estimators_],
            dtype=float,
        )
        rf_prediction = max(0.0, float(tree_predictions.mean()))
        baseline_prediction = mean(history[-3:]) if history else 0.0
        raw_prediction = (
            rf_prediction if algorithm == "random_forest" else baseline_prediction
        )
        predicted_enrollment = max(0, int(round(raw_prediction)))
        historical_average = mean(history[-3:]) if history else 0.0
        recommended_sections = math.ceil(
            predicted_enrollment / course.max_section_size
        )
        if predicted_enrollment >= 0.7 * course.max_section_size:
            demand_category = "High"
        elif predicted_enrollment >= 0.3 * course.max_section_size:
            demand_category = "Medium"
        else:
            demand_category = "Low"
        actual_last = history[-1] if history else 0
        predictions.append(
            {
                "course_id": course.id,
                "course_code": course.course_code,
                "course_name": course.name,
                "historical_enrollment": actual_last,
                "current_interest": recent_interest,
                "predicted_enrollment": predicted_enrollment,
                "uncertainty": round(float(pstdev(tree_predictions)), 4),
                "recommended_sections": recommended_sections,
                "expected_unmet_demand": 0,
                "demand_category": demand_category,
                "explanation": {
                    "algorithm": algorithm,
                    "historical_average": round(historical_average, 2),
                    "previous_semester_demand": actual_last,
                    "registration_interest": recent_interest,
                    "popularity_score": course.popularity_score,
                    "program_enrollment": plans_per_program[course.program_id],
                    "course_category": course.category,
                },
            }
        )

    return {
        "term_code": term_code,
        "algorithm": algorithm,
        "metrics": metrics,
        "results": predictions,
    }


def _next_id(existing_ids: Sequence[str], prefix: str) -> int:
    numbers: list[int] = []
    for identifier in existing_ids:
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", identifier)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def run_forecast(session: Session, *, term_code: str, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Calculate a forecast and append an immutable run and result snapshot."""
    courses = list(session.scalars(select(Course).order_by(Course.id)))
    registrations = list(session.scalars(select(RegistrationInterest)))
    plans = list(session.scalars(select(StudentPlan)))
    forecast = forecast_course_demand(
        courses, registrations, plans, term_code=term_code, seed=seed
    )
    run_ids = list(session.scalars(select(ForecastRun.id)))
    event_ids = list(session.scalars(select(AuditEvent.id)))
    run_number = _next_id(run_ids, f"FRN-{term_code[:4]}-")
    run_id = f"FRN-{term_code[:4]}-{run_number:06d}"
    now = datetime.now(timezone.utc)
    run = ForecastRun(
        id=run_id,
        term_code=term_code,
        algorithm=forecast["algorithm"],
        metrics=forecast["metrics"],
        created_at=now,
    )
    session.add(run)
    for index, result in enumerate(forecast["results"], start=1):
        session.add(
            ForecastResult(
                id=f"FCR-{term_code[:4]}-{run_number:06d}-{index:06d}",
                run_id=run_id,
                course_id=result["course_id"],
                historical_enrollment=result["historical_enrollment"],
                current_interest=result["current_interest"],
                predicted_enrollment=result["predicted_enrollment"],
                uncertainty=result["uncertainty"],
                recommended_sections=result["recommended_sections"],
                expected_unmet_demand=result["expected_unmet_demand"],
                demand_category=result["demand_category"],
                explanation=result["explanation"],
            )
        )
    session.add(
        AuditEvent(
            id=f"AUD-{_next_id(event_ids, 'AUD-'):06d}",
            entity_type="forecast_run",
            entity_id=run_id,
            action="forecast_created",
            details={
                "term_code": term_code,
                "algorithm": forecast["algorithm"],
                "metrics": forecast["metrics"],
                "result_count": len(forecast["results"]),
            },
            occurred_at=now,
        )
    )
    session.flush()
    return {**forecast, "run_id": run_id, "created_at": now.isoformat()}
