from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.demo_risk_workflow import Strict


class LabDecision(Strict):
    assessment_id: UUID
    expected_basis_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_revision: int | None = Field(default=None, ge=1)
    mode: Literal["skip", "verify"]
    purpose: str = Field(min_length=1, max_length=2000)
    task_id: UUID | None = None
    verification_path: Literal['skip','report','task'] | None = None

    @model_validator(mode='after')
    def path_matches_mode(self):
        if self.verification_path:
            if (self.verification_path=='skip') != (self.mode=='skip'):
                raise ValueError('验证路径与验证方式不一致')
            if self.verification_path!='task' and self.task_id:
                raise ValueError('暂不验证或引用已有报告不需要检测任务')
        return self


class LabTaskCreate(Strict):
    expected_revision: int = Field(ge=1)
    expected_basis_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_key: UUID
    inspection_standard_id: UUID
    priority: int = Field(default=5,ge=1,le=10)


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
