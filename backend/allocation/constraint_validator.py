from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import time
from typing import Sequence

from backend.database.models import (
    Availability,
    Course,
    Faculty,
    FacultySkill,
    Room,
    Section,
    WorkloadAssignment,
)


@dataclass(frozen=True)
class ConstraintViolation:
    constraint: str
    entity_id: str
    description: str


def intervals_overlap(
    first_start: time, first_end: time, second_start: time, second_end: time
) -> bool:
    return first_start < second_end and second_start < first_end


def validate_allocation(
    sections: Sequence[Section],
    assignments: Sequence[WorkloadAssignment],
    *,
    courses_by_id: dict[str, Course],
    rooms_by_id: dict[str, Room],
    faculty_by_id: dict[str, Faculty],
    skills: Sequence[FacultySkill],
    availability: Sequence[Availability],
    existing_sections: Sequence[Section] = (),
    existing_assignments: Sequence[WorkloadAssignment] = (),
) -> list[ConstraintViolation]:
    """Return all hard-constraint violations in the proposed allocation."""
    violations: list[ConstraintViolation] = []
    skill_pairs = {(item.faculty_id, item.course_id) for item in skills}
    assigned_section_ids = [item.section_id for item in assignments]
    duplicate_sections = {
        section_id
        for section_id, count in Counter(assigned_section_ids).items()
        if count > 1
    }

    section_by_id = {section.id: section for section in (*existing_sections, *sections)}
    workload: dict[str, float] = defaultdict(float)
    for assignment in (*existing_assignments, *assignments):
        if assignment.assignment_status == "assigned":
            workload[assignment.faculty_id] += assignment.weekly_hours

    for section in sections:
        course = courses_by_id.get(section.course_id)
        room = rooms_by_id.get(section.room_id)
        if course is None:
            violations.append(
                ConstraintViolation("course_exists", section.id, "Section references an unknown course.")
            )
        if room is None:
            violations.append(
                ConstraintViolation("room_exists", section.id, "Section references an unknown room.")
            )
        if course and section.capacity > course.max_section_size:
            violations.append(
                ConstraintViolation(
                    "course_capacity",
                    section.id,
                    f"Section capacity {section.capacity} exceeds course limit {course.max_section_size}.",
                )
            )
        if room and section.capacity > room.capacity:
            violations.append(
                ConstraintViolation(
                    "room_capacity",
                    section.id,
                    f"Section capacity {section.capacity} exceeds room capacity {room.capacity}.",
                )
            )
        if not 0 <= section.expected_enrollment <= section.capacity:
            violations.append(
                ConstraintViolation(
                    "section_enrollment",
                    section.id,
                    "Expected enrollment must be between zero and section capacity.",
                )
            )
        for other in (*existing_sections, *sections):
            if other.id == section.id or other.room_id != section.room_id:
                continue
            if (
                other.term_code == section.term_code
                and other.weekday == section.weekday
                and intervals_overlap(
                    section.start_time, section.end_time, other.start_time, other.end_time
                )
            ):
                violations.append(
                    ConstraintViolation(
                        "room_schedule",
                        section.id,
                        f"Room {section.room_id} overlaps section {other.id}.",
                    )
                )

    availability_by_faculty: dict[str, list[Availability]] = defaultdict(list)
    for record in availability:
        availability_by_faculty[record.faculty_id].append(record)

    for section_id in duplicate_sections:
        violations.append(
            ConstraintViolation(
                "one_assignment_per_section",
                section_id,
                "A section has more than one faculty assignment.",
            )
        )

    assigned_slots: dict[str, list[tuple[str, int, time, time, str]]] = defaultdict(list)
    for assignment in assignments:
        if assignment.assignment_status != "assigned":
            continue
        section = section_by_id.get(assignment.section_id)
        faculty = faculty_by_id.get(assignment.faculty_id)
        if section is None:
            violations.append(
                ConstraintViolation(
                    "section_exists", assignment.id, "Assignment references an unknown section."
                )
            )
            continue
        if faculty is None:
            violations.append(
                ConstraintViolation(
                    "faculty_exists", assignment.id, "Assignment references unknown faculty."
                )
            )
            continue
        course = courses_by_id.get(section.course_id)
        if course and (faculty.id, course.id) not in skill_pairs:
            violations.append(
                ConstraintViolation(
                    "faculty_skill",
                    assignment.id,
                    f"Faculty {faculty.id} is not qualified for course {course.id}.",
                )
            )
        faculty_availability = availability_by_faculty.get(faculty.id, [])
        if not any(
            item.weekday == section.weekday
            and item.availability_type == "available"
            and item.start_time <= section.start_time
            and item.end_time >= section.end_time
            for item in faculty_availability
        ) or any(
            item.weekday == section.weekday
            and item.availability_type == "leave"
            and intervals_overlap(
                section.start_time, section.end_time, item.start_time, item.end_time
            )
            for item in faculty_availability
        ):
            violations.append(
                ConstraintViolation(
                    "faculty_availability",
                    assignment.id,
                    f"Faculty {faculty.id} is unavailable for section {section.id}.",
                )
            )
        assigned_slots[faculty.id].append(
            (
                section.term_code,
                section.weekday,
                section.start_time,
                section.end_time,
                section.id,
            )
        )

    for assignment in existing_assignments:
        if assignment.assignment_status != "assigned":
            continue
        section = section_by_id.get(assignment.section_id)
        if section:
            assigned_slots[assignment.faculty_id].append(
                (
                    section.term_code,
                    section.weekday,
                    section.start_time,
                    section.end_time,
                    section.id,
                )
            )

    for faculty_id, hours in workload.items():
        faculty = faculty_by_id.get(faculty_id)
        if faculty and hours > faculty.max_weekly_workload:
            violations.append(
                ConstraintViolation(
                    "faculty_workload",
                    faculty_id,
                    f"Assigned workload {hours:g} exceeds limit {faculty.max_weekly_workload}.",
                )
            )

    for faculty_id, slots in assigned_slots.items():
        for index, first in enumerate(slots):
            for second in slots[index + 1 :]:
                if (
                    first[0] == second[0]
                    and first[1] == second[1]
                    and intervals_overlap(first[2], first[3], second[2], second[3])
                ):
                    violations.append(
                        ConstraintViolation(
                            "faculty_schedule",
                            second[4],
                            f"Faculty {faculty_id} overlaps section {first[4]}.",
                        )
                    )

    return violations
