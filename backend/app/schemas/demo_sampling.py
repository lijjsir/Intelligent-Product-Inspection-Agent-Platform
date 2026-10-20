"""Inputs for isolated, manually authored demo sampling suggestions."""
from uuid import UUID

from pydantic import Field

from app.schemas.demo_risk_workflow import Strict


class DemoSamplingCreate(Strict):
    assessment_id: UUID
    collaboration_id: UUID | None = None  # Legacy snapshot compatibility; new APIs use the reviewed assessment.
    expected_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class DemoSamplingContent(Strict):
    rationale: str = Field(default="", max_length=4000)
    focus: str = Field(default="", max_length=4000)
    limitations: str = Field(default="", max_length=4000)
    # Unknown execution details must remain unknown; this is not a task order.
    sample_quantity: int | None = Field(default=None, ge=1, le=100000)
    batch: str | None = Field(default=None, min_length=1, max_length=500)
    location: str | None = Field(default=None, min_length=1, max_length=500)
    proposed_time: str | None = Field(default=None, min_length=1, max_length=500)


class DemoSamplingSave(Strict):
    expected_revision: int = Field(ge=1)
    content: DemoSamplingContent


class DemoSamplingConfirm(Strict):
    expected_revision: int = Field(ge=1)
