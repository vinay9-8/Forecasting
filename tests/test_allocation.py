from datetime import date, time

import pytest
from sqlalchemy import func, select

from backend.allocation.constraint_validator import validate_allocation
from backend.allocation.section_allocator import (
    AllocationInputError,
    allocate_sections,
)
from backend.database.db import create_database_engine, create_schema, session_factory
from backend.database.models import (
    AuditEvent,
    Availability,
    Course,
    Faculty,
    FacultySkill,
    Program,
    Room,
    Section,
    WorkloadAssignment,
)
from backend.generators.master_generator import DEFAULT_SEED, generate_dataset, persist_dataset


def populated_session(*, room_capacity=20, faculty_count=2, with_skills=True):
    engine = create_database_engine("sqlite://")
    create_schema(engine)
    session = session_factory(engine)()
    session.add(
        Program(
            id="PRG-000001",
            program_code="CSE-001",
            name="Computer Science BSc",
            department="Computer Science",
            degree_level="undergraduate",
        )
    )
    session.add(
        Course(
            id="CRS-000001",
            program_id="PRG-000001",
            course_code="CSE-001-001",
            name="Computer Science Foundations",
            credits=3,
            category="required",
            is_elective=False,
            max_section_size=30,
            popularity_score=0.6,
        )
    )
    session.add(
        Room(
            id="ROM-000001",
            room_code="SCI-101",
            building="North",
            capacity=room_capacity,
            room_type="lecture",
        )
    )
    faculty = []
    for index in range(faculty_count):
        instructor = Faculty(
            id=f"FAC-{index + 1:06d}",
            name=f"Faculty {index + 1}",
            department="Computer Science",
            years_experience=10 + index,
            max_weekly_workload=6,
        )
        faculty.append(instructor)
        session.add(instructor)
        if with_skills:
            session.add(
                FacultySkill(
                    id=f"FSK-{index + 1:06d}",
                    faculty_id=instructor.id,
                    course_id="CRS-000001",
                    proficiency="advanced",
                )
            )
        availability_id = index * 20
        for weekday in range(5):
            for start, end in (
                (
                    (time(8), time(10)),
                    (time(10), time(12)),
                    (time(13), time(15)),
                    (time(15), time(17)),
                )
            ):
                availability_id += 1
                session.add(
                    Availability(
                        id=f"AVL-{availability_id:07d}",
                        faculty_id=instructor.id,
                        weekday=weekday,
                        start_time=start,
                        end_time=end,
                        availability_type="available",
                    )
                )
    session.commit()
    return engine, session


def test_allocates_sections_and_faculty_within_room_and_workload_limits():
    engine, session = populated_session()
    try:
        plan = allocate_sections(
            session,
            {"CRS-000001": 45},
            term_code="2027-Fall",
        )
        session.commit()

        assert len(plan.sections) == 3
        assert sum(section.expected_enrollment for section in plan.sections) == 45
        assert all(section.capacity <= 20 for section in plan.sections)
        assert len(plan.assignments) == 3
        assert all(assignment.score is not None for assignment in plan.assignments)
        assert plan.metrics["faculty_allocation_success_rate"] == 1.0
        assert plan.metrics["total_unmet_demand"] == 0
        workload_by_faculty = {}
        for assignment in plan.assignments:
            workload_by_faculty[assignment.faculty_id] = (
                workload_by_faculty.get(assignment.faculty_id, 0)
                + assignment.weekly_hours
            )
        assert all(hours <= 6 for hours in workload_by_faculty.values())
        assert session.scalar(select(func.count()).select_from(Section)) == 3
        assert session.scalar(select(func.count()).select_from(WorkloadAssignment)) == 3
    finally:
        session.close()
        engine.dispose()


def test_residual_demand_is_reported_when_all_room_slots_are_used():
    engine, session = populated_session()
    try:
        plan = allocate_sections(
            session,
            {"CRS-000001": 500},
            term_code="2027-Fall",
        )

        assert len(plan.sections) == 20
        assert plan.unmet_demand == {"CRS-000001": 100}
        assert plan.metrics["total_unmet_demand"] == 100
        assert len(plan.exceptions) == 16
        assert all(section.capacity <= 20 for section in plan.sections)
    finally:
        session.close()
        engine.dispose()


def test_course_without_a_qualified_faculty_member_is_left_unassigned():
    engine, session = populated_session(faculty_count=1, with_skills=False)
    try:
        plan = allocate_sections(
            session,
            {"CRS-000001": 10},
            term_code="2027-Fall",
        )

        assert len(plan.sections) == 1
        assert plan.sections[0].lifecycle_state == "unassigned"
        assert plan.assignments == []
        assert plan.exceptions[0]["issue_type"] == "UNASSIGNED_FACULTY"
    finally:
        session.close()
        engine.dispose()


def test_faculty_leave_overrides_an_available_interval():
    engine, session = populated_session(faculty_count=1)
    try:
        leave_slot = session.scalar(
            select(Availability).where(
                Availability.faculty_id == "FAC-000001",
                Availability.weekday == 0,
                Availability.start_time == time(8),
            )
        )
        leave_slot.availability_type = "leave"
        session.commit()
        plan = allocate_sections(
            session,
            {"CRS-000001": 10},
            term_code="2027-Fall",
        )

        assert plan.sections[0].weekday == 0
        assert plan.sections[0].start_time == time(8)
        assert plan.assignments == []
        assert plan.exceptions[0]["issue_type"] == "UNASSIGNED_FACULTY"
    finally:
        session.close()
        engine.dispose()


def test_faculty_availability_must_cover_the_requested_term():
    engine, session = populated_session(faculty_count=1)
    try:
        availability = session.scalar(
            select(Availability).where(
                Availability.faculty_id == "FAC-000001",
                Availability.weekday == 0,
                Availability.start_time == time(8),
            )
        )
        availability.effective_to = date(2026, 12, 31)
        session.commit()
        plan = allocate_sections(
            session,
            {"CRS-000001": 10},
            term_code="2027-Fall",
        )

        assert plan.assignments == []
        assert plan.exceptions[0]["issue_type"] == "UNASSIGNED_FACULTY"
    finally:
        session.close()
        engine.dispose()


def test_allocation_runs_against_the_generated_starter_dataset():
    engine = create_database_engine("sqlite://")
    create_schema(engine)
    session = session_factory(engine)()
    try:
        dataset = generate_dataset("starter", DEFAULT_SEED)
        persist_dataset(session, dataset)
        session.commit()
        all_course_ids = {
            course.id for course in session.scalars(select(Course))
        }

        plan = allocate_sections(
            session,
            {course_id: 5 for course_id in all_course_ids},
            term_code="2026-Fall",
        )
        session.commit()

        assert len(plan.sections) == 24
        assert sum(section.expected_enrollment for section in plan.sections) == 120
        assert plan.unmet_demand == {}
        assert plan.metrics["constraint_violation_count"] == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2
    finally:
        session.close()
        engine.dispose()


def test_repeated_allocation_does_not_duplicate_already_covered_demand():
    engine, session = populated_session()
    try:
        first = allocate_sections(
            session,
            {"CRS-000001": 10},
            term_code="2027-Fall",
        )
        session.commit()
        second = allocate_sections(
            session,
            {"CRS-000001": 10},
            term_code="2027-Fall",
        )
        session.commit()

        assert len(first.sections) == 1
        assert second.sections == []
        assert second.unmet_demand == {}
        assert session.scalar(select(func.count()).select_from(Section)) == 1
        assert session.scalar(select(func.count()).select_from(WorkloadAssignment)) == 1
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize(
    "forecasts",
    [
        {},
        {"CRS-000001": -1},
        {"CRS-000001": float("inf")},
        {"CRS-000001": True},
        {"CRS-000001": 5, "CRS-999999": 2},
    ],
)
def test_invalid_forecast_inputs_are_rejected(forecasts):
    engine, session = populated_session()
    try:
        with pytest.raises(AllocationInputError):
            allocate_sections(session, forecasts, term_code="2027-Fall")
    finally:
        session.close()
        engine.dispose()


def test_invalid_room_capacity_is_reported_as_a_hard_constraint():
    engine, session = populated_session()
    try:
        course = session.get(Course, "CRS-000001")
        room = session.get(Room, "ROM-000001")
        section = Section(
            id="SEC-2027-000001",
            course_id=course.id,
            room_id=room.id,
            term_code="2027-Fall",
            section_number=1,
            capacity=21,
            expected_enrollment=10,
            weekday=0,
            start_time=time(8),
            end_time=time(10),
        )
        violations = validate_allocation(
            [section],
            [],
            courses_by_id={course.id: course},
            rooms_by_id={room.id: room},
            faculty_by_id={},
            skills=[],
            availability=[],
        )

        assert any(item.constraint == "room_capacity" for item in violations)
    finally:
        session.close()
        engine.dispose()


def test_build_plan_rejects_malformed_term():
    engine, session = populated_session()
    try:
        with pytest.raises(AllocationInputError, match="term_code"):
            allocate_sections(session, {"CRS-000001": 1}, term_code="Fall 2027")
    finally:
        session.close()
        engine.dispose()
