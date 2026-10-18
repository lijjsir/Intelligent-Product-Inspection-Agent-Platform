from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class RiskCollaborationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    assessment_id: UUID
    expected_basis_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_key: UUID
    coordinator_id: UUID
    participant_ids: list[UUID] = Field(default_factory=list, max_length=8)
    purpose: str = Field(min_length=1, max_length=2000)
