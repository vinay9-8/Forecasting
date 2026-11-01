from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


GENERATION_DATE = date(2026, 10, 22)
LIFECYCLE_STATES = (
    "active",
    "draft",
    "scheduled",
    "assigned",
    "unassigned",
    "completed",
    "cancelled",
    "inactive",
    "retired",
)


class Base(DeclarativeBase):
    pass


class LifecycleMixin:
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    effective_from: Mapped[date] = mapped_column(
        Date, nullable=False, default=GENERATION_DATE
    )
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Program(LifecycleMixin, Base):
    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint("program_code", name="uq_programs_program_code"),
        CheckConstraint(
            "degree_level IN ('undergraduate', 'graduate')",
            name="ck_programs_degree_level",
        ),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    program_code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    department: Mapped[str] = mapped_column(String(80), nullable=False)
    degree_level: Mapped[str] = mapped_column(String(20), nullable=False)
    courses: Mapped[list[Course]] = relationship(back_populates="program")
    student_plans: Mapped[list[StudentPlan]] = relationship(back_populates="program")


class Course(LifecycleMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("course_code", name="uq_courses_course_code"),
        CheckConstraint("credits BETWEEN 1 AND 6", name="ck_courses_credits"),
        CheckConstraint(
            "max_section_size BETWEEN 1 AND 500",
            name="ck_courses_max_section_size",
        ),
        CheckConstraint(
            "category IN ('required', 'elective')", name="ck_courses_category"
        ),
        CheckConstraint(
            "popularity_score BETWEEN 0 AND 1",
            name="ck_courses_popularity_score",
        ),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_code: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    is_elective: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_section_size: Mapped[int] = mapped_column(Integer, nullable=False)
    popularity_score: Mapped[float] = mapped_column(Float, nullable=False)
    program: Mapped[Program] = relationship(back_populates="courses")
    prerequisites: Mapped[list[Prerequisite]] = relationship(
        foreign_keys="Prerequisite.course_id", back_populates="course"
    )
    registration_interests: Mapped[list[RegistrationInterest]] = relationship(
        back_populates="course"
    )
    faculty_skills: Mapped[list[FacultySkill]] = relationship(back_populates="course")
    sections: Mapped[list[Section]] = relationship(back_populates="course")


class Prerequisite(LifecycleMixin, Base):
    __tablename__ = "prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "required_course_id", name="uq_prerequisites_course_pair"
        ),
        CheckConstraint("course_id <> required_course_id", name="ck_prerequisites_no_self"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    required_course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    minimum_grade: Mapped[str] = mapped_column(String(2), nullable=False, default="D")
    course: Mapped[Course] = relationship(
        foreign_keys=[course_id], back_populates="prerequisites"
    )
    required_course: Mapped[Course] = relationship(foreign_keys=[required_course_id])


class StudentPlan(LifecycleMixin, Base):
    __tablename__ = "student_plans"
    __table_args__ = (
        CheckConstraint("cohort_year BETWEEN 2000 AND 2100", name="ck_student_cohort"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cohort_year: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_term: Mapped[str] = mapped_column(String(12), nullable=False)
    program: Mapped[Program] = relationship(back_populates="student_plans")
    registration_interests: Mapped[list[RegistrationInterest]] = relationship(
        back_populates="student_plan"
    )


class RegistrationInterest(LifecycleMixin, Base):
    __tablename__ = "registration_interests"
    __table_args__ = (
        UniqueConstraint(
            "student_plan_id",
            "course_id",
            "term_code",
            name="uq_registration_student_course_term",
        ),
        CheckConstraint(
            "interest_status IN "
            "('interested', 'registered', 'completed', 'waitlisted', 'withdrawn')",
            name="ck_registration_interest_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    student_plan_id: Mapped[str] = mapped_column(
        ForeignKey("student_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    term_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    interest_status: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    student_plan: Mapped[StudentPlan] = relationship(
        back_populates="registration_interests"
    )
    course: Mapped[Course] = relationship(back_populates="registration_interests")


class Faculty(LifecycleMixin, Base):
    __tablename__ = "faculty"
    __table_args__ = (
        CheckConstraint(
            "years_experience BETWEEN 0 AND 60", name="ck_faculty_experience"
        ),
        CheckConstraint(
            "max_weekly_workload BETWEEN 1 AND 60", name="ck_faculty_workload"
        ),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    department: Mapped[str] = mapped_column(String(80), nullable=False)
    years_experience: Mapped[int] = mapped_column(Integer, nullable=False)
    max_weekly_workload: Mapped[int] = mapped_column(Integer, nullable=False)
    skills: Mapped[list[FacultySkill]] = relationship(back_populates="faculty")
    availabilities: Mapped[list[Availability]] = relationship(back_populates="faculty")
    workload_assignments: Mapped[list[WorkloadAssignment]] = relationship(
        back_populates="faculty"
    )


class FacultySkill(LifecycleMixin, Base):
    __tablename__ = "faculty_skills"
    __table_args__ = (
        UniqueConstraint("faculty_id", "course_id", name="uq_faculty_course_skill"),
        CheckConstraint(
            "proficiency IN ('beginner', 'intermediate', 'advanced', 'expert')",
            name="ck_faculty_skill_proficiency",
        ),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    faculty_id: Mapped[str] = mapped_column(
        ForeignKey("faculty.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    proficiency: Mapped[str] = mapped_column(String(20), nullable=False)
    faculty: Mapped[Faculty] = relationship(back_populates="skills")
    course: Mapped[Course] = relationship(back_populates="faculty_skills")


class Availability(LifecycleMixin, Base):
    __tablename__ = "availabilities"
    __table_args__ = (
        UniqueConstraint(
            "faculty_id", "weekday", "start_time", "effective_from",
            name="uq_availability_faculty_slot",
        ),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_weekday"),
        CheckConstraint(
            "availability_type IN ('available', 'leave')",
            name="ck_availability_type",
        ),
        CheckConstraint("start_time < end_time", name="ck_availability_time_order"),
    )

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    faculty_id: Mapped[str] = mapped_column(
        ForeignKey("faculty.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    availability_type: Mapped[str] = mapped_column(String(12), nullable=False)
    faculty: Mapped[Faculty] = relationship(back_populates="availabilities")


class Room(LifecycleMixin, Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("room_code", name="uq_rooms_room_code"),
        CheckConstraint("capacity BETWEEN 1 AND 1000", name="ck_rooms_capacity"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    room_code: Mapped[str] = mapped_column(String(16), nullable=False)
    building: Mapped[str] = mapped_column(String(80), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    room_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sections: Mapped[list[Section]] = relationship(back_populates="room")


class Section(LifecycleMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "term_code", "section_number",
            name="uq_section_course_term_number",
        ),
        CheckConstraint("capacity BETWEEN 1 AND 1000", name="ck_section_capacity"),
        CheckConstraint(
            "expected_enrollment BETWEEN 0 AND capacity",
            name="ck_section_expected_enrollment",
        ),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_section_weekday"),
        CheckConstraint("start_time < end_time", name="ck_section_time_order"),
    )

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    room_id: Mapped[str] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    term_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    section_number: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_enrollment: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    course: Mapped[Course] = relationship(back_populates="sections")
    room: Mapped[Room] = relationship(back_populates="sections")
    workload_assignments: Mapped[list[WorkloadAssignment]] = relationship(
        back_populates="section"
    )


class WorkloadAssignment(LifecycleMixin, Base):
    __tablename__ = "workload_assignments"
    __table_args__ = (
        UniqueConstraint("faculty_id", "section_id", name="uq_workload_faculty_section"),
        CheckConstraint("weekly_hours BETWEEN 0 AND 60", name="ck_workload_hours"),
        CheckConstraint(
            "assignment_status IN ('assigned', 'unassigned')",
            name="ck_workload_assignment_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    faculty_id: Mapped[str] = mapped_column(
        ForeignKey("faculty.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    section_id: Mapped[str] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    weekly_hours: Mapped[float] = mapped_column(Float, nullable=False)
    assignment_status: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    faculty: Mapped[Faculty] = relationship(back_populates="workload_assignments")
    section: Mapped[Section] = relationship(back_populates="workload_assignments")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    term_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    algorithm: Mapped[str] = mapped_column(String(40), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    results: Mapped[list[ForecastResult]] = relationship(back_populates="run")


class ForecastResult(Base):
    __tablename__ = "forecast_results"
    __table_args__ = (
        UniqueConstraint("run_id", "course_id", name="uq_forecast_run_course"),
        CheckConstraint(
            "historical_enrollment >= 0 AND current_interest >= 0 "
            "AND predicted_enrollment >= 0 AND uncertainty >= 0 "
            "AND recommended_sections >= 0",
            name="ck_forecast_non_negative",
        ),
        CheckConstraint(
            "demand_category IN ('High', 'Medium', 'Low')",
            name="ck_forecast_demand_category",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    historical_enrollment: Mapped[int] = mapped_column(Integer, nullable=False)
    current_interest: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_enrollment: Mapped[int] = mapped_column(Integer, nullable=False)
    uncertainty: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_sections: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_unmet_demand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    demand_category: Mapped[str] = mapped_column(String(12), nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    run: Mapped[ForecastRun] = relationship(back_populates="results")
    course: Mapped[Course] = relationship()


class ExceptionRecord(Base):
    __tablename__ = "exceptions"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_exception_severity",
        ),
        CheckConstraint(
            "resolution_status IN ('open', 'in_progress', 'resolved', 'dismissed')",
            name="ck_exception_resolution_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ground_truth_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resolution_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open"
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="validation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    total_checks: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_checks: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_checks: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    details: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
