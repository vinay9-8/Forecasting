from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TERM_PATTERN = r"^\d{4}-(Spring|Summer|Fall|Winter)$"


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerationRequest(RequestModel):
    mode: Literal["starter", "full"] = "starter"
    seed: int = Field(default=20261022, ge=0, le=4_294_967_295)


class TermRequest(RequestModel):
    term_code: str = Field(pattern=TERM_PATTERN)


class ForecastRequest(TermRequest):
    seed: int = Field(default=20261022, ge=0, le=4_294_967_295)


class ProgramCreate(RequestModel):
    program_code: str = Field(min_length=2, max_length=16)
    name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=80)
    degree_level: Literal["undergraduate", "graduate"]


class CourseCreate(RequestModel):
    program_id: str = Field(min_length=1, max_length=16)
    course_code: str = Field(min_length=2, max_length=24)
    name: str = Field(min_length=1, max_length=160)
    credits: int = Field(ge=1, le=6)
    category: Literal["required", "elective"]
    is_elective: bool
    max_section_size: int = Field(ge=1, le=500)
    popularity_score: float = Field(ge=0, le=1)


class FacultyCreate(RequestModel):
    name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=80)
    years_experience: int = Field(ge=0, le=60)
    max_weekly_workload: int = Field(ge=1, le=60)