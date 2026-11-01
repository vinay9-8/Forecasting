from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from backend.scheduling import STANDARD_TIME_SLOTS
from backend.database.models import (
    AuditEvent,
    Availability,
    Course,
    Faculty,
    FacultySkill,
    Prerequisite,
    Program,
    RegistrationInterest,
    Room,
    Section,
    StudentPlan,
    WorkloadAssignment,
)

DEFAULT_SEED = 20261022
FIXED_TIMESTAMP = datetime(2026, 10, 22, tzinfo=timezone.utc)
CURRENT_TERM = "2026-Fall"
TERMS = ("2024-Fall", "2025-Spring", "2025-Fall", CURRENT_TERM)

DEPARTMENTS = (
    "Computer Science",
    "Mathematics",
    "Business",
    "Engineering",
    "Biology",
    "Economics",
    "Psychology",
    "Physics",
    "Chemistry",
    "History",
)
COURSE_NAMES = (
    "Foundations",
    "Principles",
    "Methods",
    "Analysis",
    "Applications",
    "Advanced Topics",
    "Laboratory",
    "Research",
    "Design",
    "Seminar",
)
FIRST_NAMES = (
    "Avery", "Jordan", "Morgan", "Riley", "Casey", "Taylor", "Quinn", "Cameron",
    "Reese", "Parker", "Rowan", "Skyler", "Devon", "Jamie", "Alex", "Sage",
)
LAST_NAMES = (
    "Adams", "Bennett", "Chen", "Diaz", "Ellis", "Foster", "Gupta", "Hayes",
    "Ibrahim", "Jones", "Kim", "Lopez", "Miller", "Nair", "Patel", "Reed",
)
@dataclass(frozen=True)
class GenerationConfig:
    program_count: int
    courses_per_program: int
    faculty_count: int
    student_plan_count: int
    room_count: int

    @classmethod
    def for_mode(cls, mode: str) -> GenerationConfig:
        if mode == "starter":
            return cls(4, 6, 12, 160, 8)
        if mode == "full":
            return cls(100, 10, 500, 20_000, 80)
        raise ValueError(f"Unsupported generation mode: {mode!r}")


ENTITY_MODELS = {
    "programs": Program,
    "courses": Course,
    "prerequisites": Prerequisite,
    "student_plans": StudentPlan,
    "registration_interests": RegistrationInterest,
    "faculty": Faculty,
    "faculty_skills": FacultySkill,
    "availabilities": Availability,
    "rooms": Room,
    "sections": Section,
    "workload_assignments": WorkloadAssignment,
    "audit_events": AuditEvent,
}


def _row(
    identifier: str,
    *,
    lifecycle_state: str = "active",
    effective_from: date = date(2026, 1, 1),
    effective_to: date | None = None,
    **values: Any,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "lifecycle_state": lifecycle_state,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "created_at": FIXED_TIMESTAMP,
        "updated_at": FIXED_TIMESTAMP,
        **values,
    }


def _weighted_sample(
    rng: random.Random,
    candidates: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    remaining = list(candidates)
    chosen: list[dict[str, Any]] = []
    for _ in range(min(count, len(remaining))):
        selected = rng.choices(
            remaining,
            weights=[candidate["popularity_score"] + 0.15 for candidate in remaining],
            k=1,
        )[0]
        chosen.append(selected)
        remaining.remove(selected)
    return chosen


def generate_dataset(mode: str = "starter", seed: int = DEFAULT_SEED) -> dict[str, list[dict[str, Any]]]:
    """Build every core table as deterministic, JSON/CSV-friendly row dictionaries."""
    config = GenerationConfig.for_mode(mode)
    rng = random.Random(seed)
    data: dict[str, list[dict[str, Any]]] = {name: [] for name in ENTITY_MODELS}

    for index in range(config.program_count):
        department = DEPARTMENTS[index % len(DEPARTMENTS)]
        program_id = f"PRG-{index + 1:06d}"
        data["programs"].append(
            _row(
                program_id,
                program_code=f"{department[:3].upper()}-{index + 1:03d}",
                name=f"{department} {('BSc', 'BA', 'MSc', 'BEng')[index % 4]}",
                department=department,
                degree_level="graduate" if index % 4 == 2 else "undergraduate",
            )
        )

    for program_index, program in enumerate(data["programs"]):
        program_courses: list[dict[str, Any]] = []
        for course_index in range(config.courses_per_program):
            number = program_index * config.courses_per_program + course_index + 1
            elective = course_index >= max(2, config.courses_per_program // 2)
            course = _row(
                f"CRS-{number:06d}",
                program_id=program["id"],
                course_code=f"{program['program_code']}-{course_index + 1:03d}",
                name=f"{program['department']} {COURSE_NAMES[course_index % len(COURSE_NAMES)]}",
                credits=rng.choice((3, 3, 3, 4)),
                category="elective" if elective else "required",
                is_elective=elective,
                max_section_size=rng.choice((24, 30, 36, 40, 48)),
                popularity_score=round(
                    rng.uniform(0.75, 1.0) if elective and course_index % 3 == 0
                    else rng.uniform(0.05, 0.9),
                    4,
                ),
            )
            program_courses.append(course)
            data["courses"].append(course)

            if course_index and rng.random() < 0.3:
                prerequisite_course = program_courses[rng.randrange(course_index)]
                data["prerequisites"].append(
                    _row(
                        f"PRE-{len(data['prerequisites']) + 1:06d}",
                        course_id=course["id"],
                        required_course_id=prerequisite_course["id"],
                        minimum_grade=rng.choice(("D", "C")),
                    )
                )

    course_by_program: dict[str, list[dict[str, Any]]] = {}
    for course in data["courses"]:
        course_by_program.setdefault(course["program_id"], []).append(course)

    faculty_by_program: dict[str, list[str]] = {}
    skill_counter = 0
    faculty_per_program = config.faculty_count // config.program_count
    for index in range(config.faculty_count):
        program = data["programs"][index // faculty_per_program]
        faculty_id = f"FAC-{index + 1:06d}"
        faculty_by_program.setdefault(program["id"], []).append(faculty_id)
        data["faculty"].append(
            _row(
                faculty_id,
                name=f"{FIRST_NAMES[index % len(FIRST_NAMES)]} "
                f"{LAST_NAMES[(index * 7) % len(LAST_NAMES)]}",
                department=program["department"],
                years_experience=rng.randint(1, 35),
                max_weekly_workload=rng.choice((9, 12, 15)),
            )
        )

    proficiency_levels = ("intermediate", "advanced", "expert")
    for program in data["programs"]:
        faculties = faculty_by_program[program["id"]]
        courses = course_by_program[program["id"]]
        skills_by_faculty: dict[str, set[str]] = {faculty_id: set() for faculty_id in faculties}
        for course_index, course in enumerate(courses):
            faculty_id = faculties[course_index % len(faculties)]
            skills_by_faculty[faculty_id].add(course["id"])
        for faculty_id in faculties:
            desired_count = min(len(courses), max(2, len(courses) // 2))
            for course in rng.sample(courses, desired_count):
                skills_by_faculty[faculty_id].add(course["id"])
            for course_id in sorted(skills_by_faculty[faculty_id]):
                skill_counter += 1
                data["faculty_skills"].append(
                    _row(
                        f"FSK-{skill_counter:06d}",
                        faculty_id=faculty_id,
                        course_id=course_id,
                        proficiency=rng.choice(proficiency_levels),
                    )
                )

    for index in range(config.room_count):
        room_type = rng.choice(("lecture", "lecture", "lab", "seminar"))
        data["rooms"].append(
            _row(
                f"ROM-{index + 1:06d}",
                room_code=f"{('SCI', 'ART', 'ENG', 'BUS')[index % 4]}-{101 + index:03d}",
                building=("North", "Central", "South", "Innovation")[index % 4],
                capacity=rng.choice((24, 30, 40, 60, 90, 120)),
                room_type=room_type,
            )
        )

    availability_counter = 0
    for faculty in data["faculty"]:
        leave_slot = rng.randrange(20) if rng.random() < 0.08 else None
        for weekday in range(5):
            for slot_index, (start_time, end_time) in enumerate(STANDARD_TIME_SLOTS):
                availability_counter += 1
                flat_slot = weekday * len(STANDARD_TIME_SLOTS) + slot_index
                data["availabilities"].append(
                    _row(
                        f"AVL-{availability_counter:07d}",
                        faculty_id=faculty["id"],
                        weekday=weekday,
                        start_time=start_time,
                        end_time=end_time,
                        availability_type="leave" if flat_slot == leave_slot else "available",
                    )
                )

    for index in range(config.student_plan_count):
        program = rng.choice(data["programs"])
        data["student_plans"].append(
            _row(
                f"PLN-{index + 1:06d}",
                program_id=program["id"],
                cohort_year=rng.randint(2022, 2026),
                entry_term=f"{rng.randint(2022, 2026)}-Fall",
            )
        )

    interest_counter = 0
    historical_statuses = ("completed", "completed", "registered", "withdrawn")
    for plan in data["student_plans"]:
        program_courses = course_by_program[plan["program_id"]]
        for term_index, term_code in enumerate(TERMS):
            count = rng.randint(2, min(4, len(program_courses)))
            for course in _weighted_sample(rng, program_courses, count):
                interest_counter += 1
                status = (
                    rng.choice(historical_statuses)
                    if term_index < len(TERMS) - 1
                    else rng.choice(("interested", "interested", "registered", "waitlisted"))
                )
                year, season = term_code.split("-")
                month = 8 if season == "Fall" else 1
                data["registration_interests"].append(
                    _row(
                        f"INT-{interest_counter:09d}",
                        effective_from=date(int(year), month, 1),
                        student_plan_id=plan["id"],
                        course_id=course["id"],
                        term_code=term_code,
                        interest_status=status,
                        requested_at=datetime(
                            int(year), month, 1, 9, 0, tzinfo=timezone.utc
                        ),
                    )
                )

    faculty_skills = {
        faculty_id: {row["course_id"] for row in data["faculty_skills"] if row["faculty_id"] == faculty_id}
        for faculty_id in (faculty["id"] for faculty in data["faculty"])
    }
    faculty_availability = {
        (row["faculty_id"], row["weekday"], row["start_time"])
        for row in data["availabilities"]
        if row["availability_type"] == "available"
    }
    room_slots: set[tuple[str, int, time]] = set()
    faculty_slots: set[tuple[str, int, time]] = set()
    faculty_hours: dict[str, float] = {faculty["id"]: 0 for faculty in data["faculty"]}
    faculty_limits = {
        faculty["id"]: faculty["max_weekly_workload"] for faculty in data["faculty"]
    }
    section_counter = 0
    assignment_counter = 0
    slot_options = [
        (weekday, start, end)
        for weekday in range(5)
        for start, end in STANDARD_TIME_SLOTS
    ]

    for program in data["programs"]:
        program_courses = course_by_program[program["id"]]
        course = max(program_courses, key=lambda item: item["popularity_score"])
        possible_rooms = sorted(
            data["rooms"],
            key=lambda room: (room["capacity"], room["id"]),
        )
        course_rooms = [
            room for room in possible_rooms
            if room["capacity"] <= course["max_section_size"]
        ]
        if not course_rooms:
            course_rooms = [possible_rooms[0]]
        assigned_slot = None
        assigned_room = None
        for room in course_rooms:
            candidates = list(slot_options)
            rng.shuffle(candidates)
            for weekday, start, end in candidates:
                if (room["id"], weekday, start) not in room_slots:
                    assigned_room = room
                    assigned_slot = (weekday, start, end)
                    break
            if assigned_slot:
                break
        if not assigned_slot or not assigned_room:
            continue

        weekday, start, end = assigned_slot
        section_counter += 1
        section_id = f"SEC-2026-{section_counter:06d}"
        section_capacity = min(course["max_section_size"], assigned_room["capacity"])
        data["sections"].append(
            _row(
                section_id,
                lifecycle_state="scheduled",
                course_id=course["id"],
                room_id=assigned_room["id"],
                term_code=CURRENT_TERM,
                section_number=1,
                capacity=section_capacity,
                expected_enrollment=0,
                weekday=weekday,
                start_time=start,
                end_time=end,
            )
        )
        room_slots.add((assigned_room["id"], weekday, start))

        candidates = [
            faculty["id"]
            for faculty in data["faculty"]
            if course["id"] in faculty_skills[faculty["id"]]
            and (faculty["id"], weekday, start) in faculty_availability
            and (faculty["id"], weekday, start) not in faculty_slots
            and faculty_hours[faculty["id"]] + 3 <= faculty_limits[faculty["id"]]
        ]
        if candidates:
            faculty_id = min(candidates, key=lambda item: (faculty_hours[item], item))
            faculty_slots.add((faculty_id, weekday, start))
            faculty_hours[faculty_id] += 3
            assignment_counter += 1
            data["workload_assignments"].append(
                _row(
                    f"WLA-2026-{assignment_counter:06d}",
                    lifecycle_state="assigned",
                    faculty_id=faculty_id,
                    section_id=section_id,
                    weekly_hours=3.0,
                    assignment_status="assigned",
                    score=1.0,
                    explanation="Seeded baseline assignment; faculty skill and availability match.",
                )
            )

    counts = {name: len(rows) for name, rows in data.items() if name != "audit_events"}
    data["audit_events"].append(
        {
            "id": "AUD-000001",
            "entity_type": "dataset",
            "entity_id": f"{mode}-{seed}",
            "action": "generated",
            "details": {"mode": mode, "seed": seed, "row_counts": counts},
            "occurred_at": FIXED_TIMESTAMP,
        }
    )
    validate_dataset(data)
    return data


def validate_dataset(data: dict[str, list[dict[str, Any]]]) -> None:
    """Fail fast if generated primary keys or foreign-key relationships are invalid."""
    expected_tables = set(ENTITY_MODELS)
    if set(data) != expected_tables:
        raise ValueError(f"Dataset tables mismatch: expected {sorted(expected_tables)}")
    for table, rows in data.items():
        ids = [row["id"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate primary key in {table}")

    references = {
        "courses": (("program_id", "programs"),),
        "prerequisites": (
            ("course_id", "courses"),
            ("required_course_id", "courses"),
        ),
        "student_plans": (("program_id", "programs"),),
        "registration_interests": (
            ("student_plan_id", "student_plans"),
            ("course_id", "courses"),
        ),
        "faculty_skills": (
            ("faculty_id", "faculty"),
            ("course_id", "courses"),
        ),
        "availabilities": (("faculty_id", "faculty"),),
        "sections": (("course_id", "courses"), ("room_id", "rooms")),
        "workload_assignments": (
            ("faculty_id", "faculty"),
            ("section_id", "sections"),
        ),
    }
    for table, foreign_keys in references.items():
        for field, referenced_table in foreign_keys:
            valid_ids = {row["id"] for row in data[referenced_table]}
            if any(row[field] not in valid_ids for row in data[table]):
                raise ValueError(f"Invalid {field} reference in {table}")

    course_program = {row["id"]: row["program_id"] for row in data["courses"]}
    plan_program = {row["id"]: row["program_id"] for row in data["student_plans"]}
    for interest in data["registration_interests"]:
        if course_program[interest["course_id"]] != plan_program[interest["student_plan_id"]]:
            raise ValueError("Registration interest course and student plan programs differ")


def persist_dataset(session: Session, data: dict[str, list[dict[str, Any]]]) -> None:
    """Insert a complete dataset transactionally; existing records are never replaced."""
    validate_dataset(data)
    for table, model in ENTITY_MODELS.items():
        rows = data[table]
        if rows:
            session.execute(insert(model), rows)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _canonical_row(row: dict[str, Any]) -> str:
    return json.dumps(row, default=_json_value, sort_keys=True, separators=(",", ":"))


def export_dataset(data: dict[str, list[dict[str, Any]]], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "seed": None,
        "mode": None,
        "generated_at": FIXED_TIMESTAMP.isoformat(),
        "entities": {},
    }
    audit = data["audit_events"][0]
    manifest["seed"] = audit["details"]["seed"]
    manifest["mode"] = audit["details"]["mode"]

    for table, rows in data.items():
        if not rows:
            columns = []
        else:
            columns = list(rows[0])
        csv_path = output_dir / f"{table}.csv"
        json_path = output_dir / f"{table}.json"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(
                {key: _json_value(value) for key, value in row.items()} for row in rows
            )
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, default=_json_value, ensure_ascii=False, indent=2)
            handle.write("\n")

        checksum = hashlib.sha256()
        for row in rows:
            checksum.update(_canonical_row(row).encode("utf-8"))
            checksum.update(b"\n")
        manifest["entities"][table] = {
            "row_count": len(rows),
            "sha256": checksum.hexdigest(),
            "csv_file": csv_path.name,
            "json_file": json_path.name,
        }

    from backend.validation.anomaly_scenarios import (
        build_anomaly_scenarios,
        ground_truth_rows,
    )

    scenarios = build_anomaly_scenarios(
        courses=data["courses"],
        faculty=data["faculty"],
        faculty_skills=data["faculty_skills"],
        rooms=data["rooms"],
        sections=data["sections"],
        prerequisites=data["prerequisites"],
    )
    truth_rows = ground_truth_rows(scenarios)
    truth_csv = output_dir / "ground_truth.csv"
    truth_json = output_dir / "ground_truth.json"
    truth_columns = [
        "id",
        "entity_id",
        "issue_type",
        "description",
        "severity",
        "ground_truth_label",
    ]
    with truth_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=truth_columns)
        writer.writeheader()
        writer.writerows(truth_rows)
    truth_json.write_text(
        json.dumps(truth_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    truth_checksum = hashlib.sha256(
        "\n".join(_canonical_row(row) for row in truth_rows).encode("utf-8")
    ).hexdigest()
    manifest["ground_truth"] = {
        "row_count": len(truth_rows),
        "sha256": truth_checksum,
        "csv_file": truth_csv.name,
        "json_file": truth_json.name,
    }

    manifest_path = output_dir / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
