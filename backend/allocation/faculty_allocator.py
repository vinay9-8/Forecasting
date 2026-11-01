from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from backend.allocation.constraint_validator import intervals_overlap
from backend.database.models import (
    Availability,
    Course,
    Faculty,
    FacultySkill,
    Section,
    WorkloadAssignment,
)

SKILL_WEIGHTS = {"beginner": 0.5, "intermediate": 0.7, "advanced": 0.85, "expert": 1.0}


@dataclass(frozen=True)
class FacultyChoice:
    faculty_id: str
    score: float
    explanation: str


def _is_available(
    faculty_id: str,
    section: Section,
    availability_by_faculty: dict[str, list[Availability]],
) -> bool:
    records = availability_by_faculty.get(faculty_id, [])
    has_available_interval = any(
        item.weekday == section.weekday
        and item.availability_type == "available"
        and item.start_time <= section.start_time
        and item.end_time >= section.end_time
        for item in records
    )
    has_leave_overlap = any(
        item.weekday == section.weekday
        and item.availability_type == "leave"
        and intervals_overlap(
            section.start_time, section.end_time, item.start_time, item.end_time
        )
        for item in records
    )
    return has_available_interval and not has_leave_overlap


def choose_faculty(
    section: Section,
    *,
    faculty_by_id: dict[str, Faculty],
    course_credits: int,
    skills: Sequence[FacultySkill],
    availability: Sequence[Availability],
    prior_assignments: Sequence[WorkloadAssignment],
    existing_sections: Sequence[Section] = (),
) -> FacultyChoice | None:
    """Choose a qualified, available, conflict-free instructor within workload."""
    skill_levels = {
        item.faculty_id: item.proficiency
        for item in skills
        if item.course_id == section.course_id
    }
    availability_by_faculty: dict[str, list[Availability]] = defaultdict(list)
    for record in availability:
        availability_by_faculty[record.faculty_id].append(record)

    workload: dict[str, float] = defaultdict(float)
    for assignment in prior_assignments:
        if assignment.assignment_status == "assigned":
            workload[assignment.faculty_id] += assignment.weekly_hours

    assigned_sections_by_faculty: dict[str, list[Section]] = defaultdict(list)
    section_lookup = {item.id: item for item in existing_sections}
    section_lookup[section.id] = section
    for assignment in prior_assignments:
        if assignment.assignment_status == "assigned":
            assigned_section = section_lookup.get(assignment.section_id)
            if assigned_section is not None:
                assigned_sections_by_faculty[assignment.faculty_id].append(assigned_section)

    candidates: list[tuple[float, str, str]] = []
    for faculty_id, proficiency in skill_levels.items():
        faculty = faculty_by_id.get(faculty_id)
        if faculty is None or faculty.lifecycle_state != "active":
            continue
        if not _is_available(faculty_id, section, availability_by_faculty):
            continue
        if any(
            prior.term_code == section.term_code
            and prior.weekday == section.weekday
            and intervals_overlap(
                prior.start_time, prior.end_time, section.start_time, section.end_time
            )
            for prior in assigned_sections_by_faculty[faculty_id]
        ):
            continue
        if workload[faculty_id] + course_credits > faculty.max_weekly_workload:
            continue

        skill_score = SKILL_WEIGHTS.get(proficiency, 0.5)
        availability_score = 1.0
        experience_score = min(faculty.years_experience / 30.0, 1.0)
        workload_score = max(
            0.0,
            1.0
            - (workload[faculty_id] + course_credits)
            / faculty.max_weekly_workload,
        )
        score = (
            0.35 * skill_score
            + 0.15 * availability_score
            + 0.20 * experience_score
            + 0.30 * workload_score
        )
        explanation = (
            f"{proficiency} course skill; available for weekday {section.weekday} "
            f"{section.start_time:%H:%M}-{section.end_time:%H:%M}; "
            f"{faculty.years_experience} years' experience; "
            f"{workload[faculty_id]:g}/{faculty.max_weekly_workload} weekly hours before assignment."
        )
        candidates.append((score, faculty_id, explanation))

    if not candidates:
        return None
    score, faculty_id, explanation = max(
        candidates, key=lambda candidate: (candidate[0], candidate[1])
    )
    return FacultyChoice(faculty_id, round(score, 4), explanation)


def assign_faculty(
    sections: Sequence[Section],
    *,
    courses_by_id: dict[str, Course],
    faculty_by_id: dict[str, Faculty],
    skills: Sequence[FacultySkill],
    availability: Sequence[Availability],
    prior_assignments: Sequence[WorkloadAssignment],
    existing_sections: Sequence[Section] = (),
    assignment_id_start: int = 1,
    year: int = 2026,
) -> tuple[list[WorkloadAssignment], list[dict[str, str]]]:
    assignments: list[WorkloadAssignment] = []
    exceptions: list[dict[str, str]] = []
    working_assignments = list(prior_assignments)
    for section in sections:
        course = courses_by_id[section.course_id]
        choice = choose_faculty(
            section,
            faculty_by_id=faculty_by_id,
            course_credits=course.credits,
            skills=skills,
            availability=availability,
            prior_assignments=working_assignments,
            existing_sections=(*existing_sections, *sections),
        )
        if choice is None:
            section.lifecycle_state = "unassigned"
            exceptions.append(
                {
                    "entity_id": section.id,
                    "issue_type": "UNASSIGNED_FACULTY",
                    "description": (
                        f"No qualified, available faculty member with workload capacity "
                        f"could be assigned to section {section.id}."
                    ),
                    "severity": "high",
                }
            )
            continue
        assignment = WorkloadAssignment(
            id=f"WLA-{year}-{assignment_id_start + len(assignments):06d}",
            faculty_id=choice.faculty_id,
            section_id=section.id,
            weekly_hours=float(course.credits),
            assignment_status="assigned",
            score=choice.score,
            explanation=choice.explanation,
            lifecycle_state="assigned",
        )
        assignments.append(assignment)
        working_assignments.append(assignment)

    return assignments, exceptions
