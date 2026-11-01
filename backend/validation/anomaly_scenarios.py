from __future__ import annotations

from typing import Any


def _value(record: Any, key: str) -> Any:
    return record[key] if isinstance(record, dict) else getattr(record, key)


def _term_key(term: str) -> tuple[int, int]:
    year, season = term.split("-", 1)
    return int(year), {"Spring": 0, "Winter": 0, "Summer": 1, "Fall": 2}[season]


def build_anomaly_scenarios(
    *,
    courses: list[Any],
    faculty: list[Any],
    faculty_skills: list[Any],
    rooms: list[Any],
    sections: list[Any],
    prerequisites: list[Any],
) -> list[dict[str, Any]]:
    """Create isolated, labelled negative cases without mutating baseline rows."""
    if not courses or not faculty or not rooms or not sections:
        return []

    skill_pairs = {
        (_value(item, "faculty_id"), _value(item, "course_id"))
        for item in faculty_skills
    }
    incompatible_pair = next(
        (
            (_value(instructor, "id"), _value(course, "id"))
            for instructor in faculty
            for course in courses
            if (_value(instructor, "id"), _value(course, "id")) not in skill_pairs
        ),
        None,
    )
    if incompatible_pair is None:
        return []
    faculty_id, course_id = incompatible_pair
    faculty_record = next(item for item in faculty if _value(item, "id") == faculty_id)
    section = sections[0]
    section_id = _value(section, "id")
    room_id = _value(section, "room_id")
    room = next(item for item in rooms if _value(item, "id") == room_id)

    prerequisite = prerequisites[0] if prerequisites else {
        "course_id": _value(courses[-1], "id"),
        "required_course_id": _value(courses[0], "id"),
    }
    prerequisite_course_id = _value(prerequisite, "course_id")
    required_course_id = _value(prerequisite, "required_course_id")
    room_capacity = _value(room, "capacity")
    max_weekly_workload = _value(faculty_record, "max_weekly_workload")
    return [
        {
            "id": "GT-000001",
            "entity_id": course_id,
            "issue_type": "FACULTY_SKILL_MISMATCH",
            "description": f"Faculty {faculty_id} is assigned outside their skill set for course {course_id}.",
            "severity": "high",
            "ground_truth_label": True,
            "scenario": {
                "faculty_id": faculty_id,
                "course_id": course_id,
                "has_skill": False,
            },
        },
        {
            "id": "GT-000002",
            "entity_id": faculty_id,
            "issue_type": "FACULTY_WORKLOAD_EXCEEDED",
            "description": f"Simulated workload exceeds faculty {faculty_id}'s maximum by 3 hours.",
            "severity": "high",
            "ground_truth_label": True,
            "scenario": {
                "faculty_id": faculty_id,
                "assigned_hours": max_weekly_workload + 3,
                "max_hours": max_weekly_workload,
            },
        },
        {
            "id": "GT-000003",
            "entity_id": section_id,
            "issue_type": "SECTION_CAPACITY_TOO_LOW",
            "description": f"Simulated enrollment exceeds room {room_id} capacity.",
            "severity": "medium",
            "ground_truth_label": True,
            "scenario": {
                "section_id": section_id,
                "room_capacity": room_capacity,
                "enrollment": room_capacity + 1,
            },
        },
        {
            "id": "GT-000004",
            "entity_id": prerequisite_course_id,
            "issue_type": "PREREQUISITE_ORDER_VIOLATION",
            "description": "A simulated course section is scheduled before its prerequisite.",
            "severity": "high",
            "ground_truth_label": True,
            "scenario": {
                "course_id": prerequisite_course_id,
                "required_course_id": required_course_id,
                "course_term": "2026-Fall",
                "prerequisite_term": "2027-Fall",
            },
        },
        {
            "id": "GT-000005",
            "entity_id": section_id,
            "issue_type": "DUPLICATE_SECTION_ASSIGNMENT",
            "description": f"Section {section_id} is assigned twice in the isolated test case.",
            "severity": "medium",
            "ground_truth_label": True,
            "scenario": {"section_id": section_id, "assignment_count": 2},
        },
    ]


def detect_scenario(scenario: dict[str, Any]) -> bool:
    """Apply the same negative-rule semantics to an isolated ground-truth case."""
    issue_type = scenario["issue_type"]
    values = scenario["scenario"]
    if issue_type == "FACULTY_SKILL_MISMATCH":
        return not values["has_skill"]
    if issue_type == "FACULTY_WORKLOAD_EXCEEDED":
        return values["assigned_hours"] > values["max_hours"]
    if issue_type == "SECTION_CAPACITY_TOO_LOW":
        return values["enrollment"] > values["room_capacity"]
    if issue_type == "PREREQUISITE_ORDER_VIOLATION":
        return _term_key(values["course_term"]) < _term_key(
            values["prerequisite_term"]
        )
    if issue_type == "DUPLICATE_SECTION_ASSIGNMENT":
        return values["assignment_count"] > 1
    return False


def ground_truth_rows(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "entity_id": item["entity_id"],
            "issue_type": item["issue_type"],
            "description": item["description"],
            "severity": item["severity"],
            "ground_truth_label": item["ground_truth_label"],
        }
        for item in scenarios
    ]