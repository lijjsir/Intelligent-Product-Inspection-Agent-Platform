from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RevisionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    request_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("需填写实际核对或操作说明")
        return value.strip()

    @field_validator("evidence_refs")
    @classmethod
    def clean_evidence_refs(cls, values):
        return [v.strip() for v in values if v.strip()]


class RevisionReview(RevisionAction):
    decision: Literal["approve", "needs_information", "dispute", "reject"]
    conflict_resolution: str = Field(default="", max_length=4000)


class ReviewAssignment(RevisionAction):
    operation: Literal["assign", "claim", "release"]
    reviewer_id: str | None = None
    due_at: str | None = None


class CandidateReview(RevisionAction):
    candidate_id: str
    decision: Literal["confirm", "needs_information", "reject"]


class RevisionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    base_revision_id: str
    standard_no: str = Field(min_length=1, max_length=100)
    standard_name: str = Field(min_length=1, max_length=255)
    domain: str = Field(default="", max_length=100)
    product_category: str | None = Field(default=None, max_length=100)
    resource_type: Literal["standard", "reference", "unverified"] = "unverified"
    standard_level: str = Field(max_length=32)
    standard_status: Literal["待核实", "现行", "即将实施", "被代替", "废止"] = "待核实"
    source_url: str = Field(default="", max_length=2000)
    publisher: str = Field(default="", max_length=255)
    effective_from: str | None = None
    effective_to: str | None = None
    production_from: str | None = None
    production_to: str | None = None
    scope_notes: str = Field(default="", max_length=4000)


class CandidateEdit(RevisionAction):
    candidate_id: str
    status: Literal["pending", "confirmed", "rejected"] = "pending"
    candidate_type:Literal["inspection_requirement","method_condition","body_clause","unclassified"]|None=None
    indicator: str = Field(default="", max_length=255)
    method: str = Field(default="", max_length=4000)
    conditions: str = Field(default="", max_length=4000)
    unit: str = Field(default="", max_length=100)
    requirement: str = Field(default="", max_length=4000)
    operator: Literal["le", "ge", "range", "eq", "text", "unresolved"] = "unresolved"
    measurement_key: str = Field(default="", max_length=128)
    applicability: str = Field(default="", max_length=4000)
    execution_mode: Literal["manual","numeric"] = "manual"
    numeric_lower: float|None = Field(default=None,strict=True,allow_inf_nan=False)
    numeric_upper: float|None = Field(default=None,strict=True,allow_inf_nan=False)
    numeric_target: float|None = Field(default=None,strict=True,allow_inf_nan=False)
    decision_mode: Literal["direct","interval"] = "direct"
    numeric_aggregation: Literal["all","mean"] = "all"
    minimum_observations: int = Field(default=1,ge=1,le=1000)
    expected_conditions: dict = Field(default_factory=dict)
