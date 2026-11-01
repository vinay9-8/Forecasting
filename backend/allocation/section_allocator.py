from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from numbers import Real
from typing import Mapping, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.allocation.constraint_validator import ConstraintViolation, validate_allocation
from backend.allocation.faculty_allocator import assign_faculty
from backend.database.models import (
    AuditEvent,
    Availability,
    Course,
    Faculty,
    FacultySkill,
    Room,
    Section,
    WorkloadAssignment,
)
from backend.scheduling import STANDARD_TIME_SLOTS

TERM_PATTERN = re.compile(r"^(?P<year>\d{4})-(Spring|Summer|Fall|Winter)$")


class AllocationInputError(ValueError):
    """Raised when forecast inputs cannot be safely used for allocation."""


class AllocationConstraintError(RuntimeError):
    def __init__(self, violations: Sequence[ConstraintViolation]):
        self.violations = tuple(violations)
        details = "; ".join(
            f"{item.constraint} ({item.entity_id}): {item.description}"
            for item in violations
        )
        super().__init__(f"Allocation violates hard constraints: {details}")


@dataclass
class AllocationPlan:
    term_code: str
    sections: list[Section] = field(default_factory=list)
    assignments: list[WorkloadAssignment] = field(default_factory=list)
    unmet_demand: dict[str, int] = field(default_factory=dict)
    exceptions: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, float | int] = field(default_factory=dict)


class EffectiveDated(Protocol):
    lifecycle_state: str
    effective_from: date
    effective_to: date | None


def _validated_demands(
    forecasts: Mapping[str, Real],
    courses: Sequence[Course],
    eligible_course_ids: set[str],
) -> dict[str, int]:
    all_course_ids = {course.id for course in courses}
    missing = eligible_course_ids - forecasts.keys()
    unknown = forecasts.keys() - all_course_ids
    ineligible = (forecasts.keys() & all_course_ids) - eligible_course_ids
    if missing or unknown or ineligible:
        details = []
        if missing:
            details.append(f"missing forecasts for {len(missing)} course(s)")
        if unknown:
            details.append(f"forecasts reference {len(unknown)} unknown course(s)")
        if ineligible:
            details.append(
                f"forecasts include {len(ineligible)} inactive or ineffective course(s)"
            )
        raise AllocationInputError("; ".join(details))

    demands: dict[str, int] = {}
    for course_id, raw_value in forecasts.items():
        if isinstance(raw_value, bool) or not isinstance(raw_value, Real):
            raise AllocationInputError(f"Forecast for {course_id} must be a finite number.")
        value = float(raw_value)
        if not math.isfinite(value) or value < 0:
            raise AllocationInputError(
                f"Forecast for {course_id} must be finite and non-negative."
            )
        demands[course_id] = math.ceil(value)
    return demands


def _term_start_date(term_code: str) -> date:
    match = TERM_PATTERN.fullmatch(term_code)
    if not match:
        raise AllocationInputError("term_code must use YYYY-Spring|Summer|Fall|Winter format.")
    month = {
        "Spring": 1,
        "Winter": 1,
        "Summer": 5,
        "Fall": 8,
    }[term_code.split("-", maxsplit=1)[1]]
    return date(int(match.group("year")), month, 1)


def _is_effective(record: EffectiveDated, effective_on: date) -> bool:
    return (
        record.lifecycle_state == "active"
        and record.effective_from <= effective_on
        and (
            record.effective_to is None or record.effective_to >= effective_on
        )
    )


def _next_numeric_id(ids: Sequence[str], prefix: str) -> int:
    numbers = []
    for identifier in ids:
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", identifier)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def build_allocation_plan(
    *,
    predicted_demand: Mapping[str, Real],
    term_code: str,
    courses: Sequence[Course],
    rooms: Sequence[Room],
    faculty: Sequence[Faculty],
    skills: Sequence[FacultySkill],
    availability: Sequence[Availability],
    existing_sections: Sequence[Section] = (),
    existing_assignments: Sequence[WorkloadAssignment] = (),
    section_id_start: int = 1,
    assignment_id_start: int = 1,
    year: int | None = None,
) -> AllocationPlan:
    term_match = TERM_PATTERN.fullmatch(term_code)
    if not term_match:
        raise AllocationInputError("term_code must use YYYY-Spring|Summer|Fall|Winter format.")
    term_year = int(term_match.group("year"))
    effective_on = _term_start_date(term_code)
    if year is not None and year != term_year:
        raise AllocationInputError("Allocation ID year must match the requested term.")
    year = term_year

    active_courses = [course for course in courses if _is_effective(course, effective_on)]
    demands = _validated_demands(
        predicted_demand, courses, {course.id for course in active_courses}
    )
    active_rooms = [room for room in rooms if _is_effective(room, effective_on)]
    course_by_id = {course.id: course for course in active_courses}
    room_by_id = {room.id: room for room in active_rooms}
    faculty_by_id = {
        item.id: item for item in faculty if _is_effective(item, effective_on)
    }
    active_skills = [item for item in skills if _is_effective(item, effective_on)]
    active_availability = [
        item for item in availability if _is_effective(item, effective_on)
    ]
    plan = AllocationPlan(term_code=term_code)
    remaining_by_course = dict(demands)
    for existing in existing_sections:
        if (
            existing.term_code == term_code
            and existing.lifecycle_state != "cancelled"
            and existing.course_id in remaining_by_course
        ):
            remaining_by_course[existing.course_id] = max(
                0,
                remaining_by_course[existing.course_id]
                - existing.expected_enrollment,
            )
    room_schedule: dict[tuple[str, int], list[tuple[time, time]]] = defaultdict(list)
    for existing in existing_sections:
        if existing.term_code == term_code and existing.lifecycle_state != "cancelled":
            room_schedule[(existing.room_id, existing.weekday)].append(
                (existing.start_time, existing.end_time)
            )

    ordered_courses = sorted(
        active_courses, key=lambda course: (-remaining_by_course[course.id], course.id)
    )
    for course in ordered_courses:
        remaining = remaining_by_course[course.id]
        if remaining == 0:
            continue
        section_number = max(
            (
                section.section_number
                for section in existing_sections
                if section.course_id == course.id and section.term_code == term_code
            ),
            default=0,
        )
        eligible_rooms = [
            room
            for room in active_rooms
            if min(room.capacity, course.max_section_size) > 0
        ]
        eligible_rooms.sort(
            key=lambda room: (min(room.capacity, course.max_section_size), room.id),
            reverse=True,
        )
        while remaining > 0:
            chosen: tuple[Room, int, time, time, int] | None = None
            for weekday in range(5):
                for start, end in STANDARD_TIME_SLOTS:
                    available_rooms = [
                        room
                        for room in eligible_rooms
                        if not any(
                            start < occupied_end and occupied_start < end
                            for occupied_start, occupied_end in room_schedule[
                                (room.id, weekday)
                            ]
                        )
                    ]
                    if available_rooms:
                        room = available_rooms[0]
                        chosen = (
                            room,
                            weekday,
                            start,
                            end,
                            min(room.capacity, course.max_section_size),
                        )
                        break
                if chosen:
                    break
            if chosen is None:
                plan.unmet_demand[course.id] = remaining
                break

            room, weekday, start, end, capacity = chosen
            section_number += 1
            section_id = f"SEC-{year}-{section_id_start + len(plan.sections):06d}"
            expected_enrollment = min(remaining, capacity)
            section = Section(
                id=section_id,
                course_id=course.id,
                room_id=room.id,
                term_code=term_code,
                section_number=section_number,
                capacity=capacity,
                expected_enrollment=expected_enrollment,
                weekday=weekday,
                start_time=start,
                end_time=end,
                lifecycle_state="scheduled",
            )
            plan.sections.append(section)
            room_schedule[(room.id, weekday)].append((start, end))
            remaining -= expected_enrollment

    plan.assignments, plan.exceptions = assign_faculty(
        plan.sections,
        courses_by_id=course_by_id,
        faculty_by_id=faculty_by_id,
        skills=active_skills,
        availability=active_availability,
        prior_assignments=existing_assignments,
        existing_sections=existing_sections,
        assignment_id_start=assignment_id_start,
        year=year,
    )

    violations = validate_allocation(
        plan.sections,
        plan.assignments,
        courses_by_id=course_by_id,
        rooms_by_id=room_by_id,
        faculty_by_id={item.id: item for item in faculty},
        skills=active_skills,
        availability=active_availability,
        existing_sections=existing_sections,
        existing_assignments=existing_assignments,
    )
    if violations:
        raise AllocationConstraintError(violations)

    capacity = sum(section.capacity for section in plan.sections)
    planned = sum(section.expected_enrollment for section in plan.sections)
    assigned_ids = {item.section_id for item in plan.assignments}
    projected_hours: dict[str, float] = defaultdict(float)
    for assignment in (*existing_assignments, *plan.assignments):
        if assignment.assignment_status == "assigned":
            projected_hours[assignment.faculty_id] += assignment.weekly_hours
    workload_capacity = sum(item.max_weekly_workload for item in faculty)
    total_projected_workload = sum(projected_hours.values())
    skill_pairs = {(item.faculty_id, item.course_id) for item in skills}
    section_course = {section.id: section.course_id for section in plan.sections}

    plan.metrics = {
        "sections_generated": len(plan.sections),
        "faculty_allocation_success_rate": (
            len(assigned_ids) / len(plan.sections) if plan.sections else 0.0
        ),
        "section_capacity_utilization": planned / capacity if capacity else 0.0,
        "total_unmet_demand": sum(plan.unmet_demand.values()),
        "faculty_workload_utilization": (
            total_projected_workload / workload_capacity if workload_capacity else 0.0
        ),
        "skill_matching_rate": (
            sum(
                (assignment.faculty_id, section_course[assignment.section_id])
                in skill_pairs
                for assignment in plan.assignments
            )
            / len(plan.assignments)
            if plan.assignments
            else 0.0
        ),
        "constraint_violation_count": 0,
    }
    return plan


def allocate_sections(
    session: Session,
    predicted_demand: Mapping[str, Real],
    *,
    term_code: str,
) -> AllocationPlan:
    """Plan and stage new sections/assignments; caller controls the transaction."""
    term_match = TERM_PATTERN.fullmatch(term_code)
    if not term_match:
        raise AllocationInputError("term_code must use YYYY-Spring|Summer|Fall|Winter format.")
    year = int(term_match.group("year"))

    courses = list(session.scalars(select(Course).order_by(Course.id)))
    rooms = list(session.scalars(select(Room).order_by(Room.id)))
    faculty = list(session.scalars(select(Faculty).order_by(Faculty.id)))
    skills = list(session.scalars(select(FacultySkill).order_by(FacultySkill.id)))
    availability = list(session.scalars(select(Availability).order_by(Availability.id)))
    existing_sections = list(
        session.scalars(select(Section).where(Section.term_code == term_code))
    )
    section_ids = list(session.scalars(select(Section.id)))
    assignment_query = (
        select(WorkloadAssignment)
        .join(Section, WorkloadAssignment.section_id == Section.id)
        .where(Section.term_code == term_code)
    )
    existing_assignments = list(session.scalars(assignment_query))
    assignment_ids = list(session.scalars(select(WorkloadAssignment.id)))
    audit_ids = list(session.scalars(select(AuditEvent.id)))

    plan = build_allocation_plan(
        predicted_demand=predicted_demand,
        term_code=term_code,
        courses=courses,
        rooms=rooms,
        faculty=faculty,
        skills=skills,
        availability=availability,
        existing_sections=existing_sections,
        existing_assignments=existing_assignments,
        section_id_start=_next_numeric_id(section_ids, f"SEC-{year}-"),
        assignment_id_start=_next_numeric_id(assignment_ids, f"WLA-{year}-"),
        year=year,
    )
    session.add_all(plan.sections)
    session.add_all(plan.assignments)
    now = datetime.now(timezone.utc)
    session.add(
        AuditEvent(
            id=f"AUD-{_next_numeric_id(audit_ids, 'AUD-'):06d}",
            entity_type="allocation",
            entity_id=f"{term_code}-{len(audit_ids) + 1:06d}",
            action="sections_allocated",
            details={
                "term_code": term_code,
                "metrics": plan.metrics,
                "unmet_demand": plan.unmet_demand,
                "exceptions": plan.exceptions,
            },
            occurred_at=now,
        )
    )
    return plan
