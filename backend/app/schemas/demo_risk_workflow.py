"""Manual demo workflow inputs. Formal decisions and probability are not inputs."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DemoDraftContent(Strict):
    summary: str = Field(default="", max_length=4000)
    reasoning: str = Field(default="", max_length=8000)
    limitations: str = Field(default="", max_length=4000)
    risk_type: str | None = Field(default=None, max_length=128)
    risk_level: Literal["unknown", "low", "medium", "high", "critical"] = "unknown"
    cited_record_ids: list[UUID] = Field(default_factory=list, max_length=500)
    missing_inputs: list[str] = Field(default_factory=list, max_length=100)
    recommendations: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("cited_record_ids")
    @classmethod
    def unique_citations(cls, values):
        return list(dict.fromkeys(values))

    @field_validator("missing_inputs", "recommendations")
    @classmethod
    def clean_lines(cls, values):
        values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v) > 1000 for v in values):
            raise ValueError("每项内容不能超过 1000 字")
        return values


class DemoDraftCreate(Strict):
    base_assessment_id: UUID | None = None
    expected_basis_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_key: UUID


class DemoDraftSave(Strict):
    expected_revision: int = Field(ge=1)
    content: DemoDraftContent


class DemoDraftSubmit(Strict):
    expected_revision: int = Field(ge=1)


class DemoDraftReview(Strict):
    expected_revision: int = Field(ge=1)
    decision: Literal["approve", "revise", "request_evidence"]
    comment: str = Field(min_length=1, max_length=4000)
