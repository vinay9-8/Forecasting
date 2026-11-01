from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.allocation.constraint_validator import validate_allocation


def _term_key(term: str) -> tuple[int, int]:
    year, season = term.split("-", 1)
    order = {"Winter": 0, "Spring": 1, "Summer": 2, "Fall": 3}
    return int(year), order[season]


def allocation_issues(tables: dict[str, list[Any]]) -> list[dict[str, str]]:
    courses = {item.id: item for item in tables["courses"]}
    rooms = {item.id: item for item in tables["rooms"]}
    faculty = {item.id: item for item in tables["faculty"]}
    skills = tables["faculty_skills"]
    availability = tables["availabilities"]
    assignments_by_term: dict[str, list[Any]] = defaultdict(list)
    sections_by_term: dict[str, list[Any]] = defaultdict(list)
    section_by_id = {item.id: item for item in tables["sections"]}
    for section in tables["sections"]:
        sections_by_term[section.term_code].append(section)
    for assignment in tables["workload_assignments"]:
        section = section_by_id.get(assignment.section_id)
        if section:
            assignments_by_term[section.term_code].append(assignment)

    issues: list[dict[str, str]] = []
    for term_code, sections in sections_by_term.items():
        violations = validate_allocation(
            sections,
            assignments_by_term[term_code],
            courses_by_id=courses,
            rooms_by_id=rooms,
            faculty_by_id=faculty,
            skills=skills,
            availability=availability,
        )
        issues.extend(
            {
                "entity_id": violation.entity_id,
                "issue_type": violation.constraint.upper(),
                "description": violation.description,
                "severity": "high",
            }
            for violation in violations
        )

    for prerequisite in tables["prerequisites"]:
        if prerequisite.lifecycle_state != "active":
            continue
        course_terms = [
            section.term_code
            for section in tables["sections"]
            if section.course_id == prerequisite.course_id
        ]
        required_terms = [
            section.term_code
            for section in tables["sections"]
            if section.course_id == prerequisite.required_course_id
        ]
        if course_terms and required_terms:
            earliest_course_term = min(course_terms, key=_term_key)
            latest_required_term = max(required_terms, key=_term_key)
            if _term_key(earliest_course_term) < _term_key(latest_required_term):
                issues.append(
                    {
                        "entity_id": prerequisite.course_id,
                        "issue_type": "PREREQUISITE_ORDER_VIOLATION",
                        "description": (
                            f"Course {prerequisite.course_id} is scheduled in "
                            f"{earliest_course_term} before prerequisite "
                            f"{prerequisite.required_course_id} in {latest_required_term}."
                        ),
                        "severity": "high",
                    }
                )

    for section in tables["sections"]:
        course = courses.get(section.course_id)
        room = rooms.get(section.room_id)
        if course and section.capacity > course.max_section_size:
            issues.append(
                {
                    "entity_id": section.id,
                    "issue_type": "COURSE_CAPACITY_EXCEEDED",
                    "description": "Section capacity is above the course's maximum section size.",
                    "severity": "high",
                }
            )
        if room and section.capacity > room.capacity:
            issues.append(
                {
                    "entity_id": section.id,
                    "issue_type": "ROOM_CAPACITY_EXCEEDED",
                    "description": "Section capacity exceeds room capacity.",
                    "severity": "high",
                }
            )
        if section.lifecycle_state == "unassigned":
            issues.append(
                {
                    "entity_id": section.id,
                    "issue_type": "UNASSIGNED_FACULTY",
                    "description": f"Section {section.id} does not have a faculty assignment.",
                    "severity": "medium",
                }
            )
    return issues