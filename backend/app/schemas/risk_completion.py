from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.demo_risk_workflow import Strict


class LabDecision(Strict):
    assessment_id: UUID
    expected_basis_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_revision: int | None = Field(default=None, ge=1)
    mode: Literal["skip", "verify"]
    purpose: str = Field(min_length=1, max_length=2000)
    task_id: UUID | None = None


class LabReturn(Strict):
    expected_revision: int = Field(ge=1)
    record_ids: list[UUID] = Field(min_length=1, max_length=20)
    note: str = Field(min_length=1, max_length=2000)


class LabExecutionReturn(Strict):
    expected_revision: int = Field(ge=1)
    run_id: UUID
    expected_run_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    note: str = Field(min_length=1, max_length=2000)


class LabExecutionWithdraw(Strict):
    expected_revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)


class RiskReportCreate(Strict):
    assessment_id: UUID
    expected_basis_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RiskReportExport(Strict):
    format: Literal["pdf", "docx"]
