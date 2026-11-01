from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.validation.anomaly_scenarios import (
    build_anomaly_scenarios,
    detect_scenario,
    ground_truth_rows,
)
from backend.validation.business_rules import allocation_issues
from backend.validation.integrity import (
    foreign_key_issues,
    identifier_issues,
    lifecycle_issues,
    primary_key_issues,
)
from backend.validation.report import build_report


def _check(
    name: str,
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    warning_details = [item["description"] for item in warnings or []]
    return {
        "name": name,
        "passed": not issues,
        "issue_count": len(issues),
        "details": [item["description"] for item in issues],
        "warning_count": len(warning_details),
        "warnings": warning_details,
    }


def validate_tables(tables: dict[str, list[Any]]) -> dict[str, Any]:
    """Run structural, referential, lifecycle, and allocation checks."""
    allocation = allocation_issues(tables)
    by_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    for issue in allocation:
        by_type[issue["issue_type"]].append(issue)

    checks = [
        _check(
            "dataset_presence",
            [] if tables["programs"] and tables["courses"] else [
                {
                    "entity_id": "dataset",
                    "description": "At least one program and course are required.",
                }
            ],
        ),
        _check("primary_key_uniqueness", primary_key_issues(tables)),
        _check("foreign_key_integrity", foreign_key_issues(tables)),
        _check("id_format", identifier_issues(tables)),
        _check("lifecycle_and_date_ordering", lifecycle_issues(tables)),
        _check(
            "prerequisite_ordering",
            by_type["PREREQUISITE_ORDER_VIOLATION"],
        ),
        _check(
            "workload_reconciliation",
            by_type["FACULTY_WORKLOAD"] + by_type["FACULTY_SCHEDULE"],
        ),
        _check(
            "room_capacity_and_schedule",
            by_type["ROOM_CAPACITY"]
            + by_type["COURSE_CAPACITY"]
            + by_type["ROOM_SCHEDULE"],
        ),
        _check(
            "faculty_skill_matching",
            by_type["FACULTY_SKILL"],
        ),
        _check(
            "faculty_availability",
            by_type["FACULTY_AVAILABILITY"],
        ),
        _check(
            "section_assignment",
            by_type["ONE_ASSIGNMENT_PER_SECTION"]
            + by_type["SECTION_EXISTS"]
            + by_type["FACULTY_EXISTS"],
            warnings=by_type["UNASSIGNED_FACULTY"],
        ),
        _check(
            "section_enrollment_capacity",
            by_type["SECTION_ENROLLMENT"],
        ),
    ]

    issues: list[dict[str, str]] = []
    for issue in allocation:
        issues.append(
            {
                "entity_id": issue["entity_id"],
                "issue_type": issue["issue_type"],
                "description": issue["description"],
                "severity": issue.get("severity", "high"),
                "ground_truth_label": "false",
                "source": "dataset_validation",
            }
        )
    for check in checks:
        if check["name"] in {
            "primary_key_uniqueness",
            "foreign_key_integrity",
            "id_format",
            "lifecycle_and_date_ordering",
        }:
            for description in check["details"]:
                issues.append(
                    {
                        "entity_id": "dataset",
                        "issue_type": check["name"].upper(),
                        "description": description,
                        "severity": "high",
                        "ground_truth_label": "false",
                        "source": "dataset_validation",
                    }
                )

    scenarios = build_anomaly_scenarios(
        courses=tables["courses"],
        faculty=tables["faculty"],
        faculty_skills=tables["faculty_skills"],
        rooms=tables["rooms"],
        sections=tables["sections"],
        prerequisites=tables["prerequisites"],
    )
    scenario_issues: list[dict[str, str]] = []
    for scenario in scenarios:
        detected = detect_scenario(scenario)
        if detected:
            scenario_issues.append(
                {
                    "entity_id": scenario["entity_id"],
                    "issue_type": scenario["issue_type"],
                    "description": scenario["description"],
                    "severity": scenario["severity"],
                    "ground_truth_label": "true",
                    "source": "isolated_ground_truth",
                }
            )
    checks.append(
        {
            "name": "ground_truth_scenario_detection",
            "passed": len(scenario_issues) == len(scenarios) and bool(scenarios),
            "issue_count": len(scenarios) - len(scenario_issues),
            "details": (
                []
                if scenarios and len(scenario_issues) == len(scenarios)
                else ["One or more isolated anomaly scenarios were not detected."]
            ),
        }
    )
    if not tables["programs"] or not tables["courses"]:
        issues.append(
            {
                "entity_id": "dataset",
                "issue_type": "DATASET_EMPTY",
                "description": "At least one program and course are required.",
                "severity": "high",
                "ground_truth_label": "false",
                "source": "dataset_validation",
            }
        )
    issues.extend(scenario_issues)
    report = build_report(checks, issues)
    report["ground_truth"] = ground_truth_rows(scenarios)
    report["detected_scenarios"] = len(scenario_issues)
    report["scenario_count"] = len(scenarios)
    return report