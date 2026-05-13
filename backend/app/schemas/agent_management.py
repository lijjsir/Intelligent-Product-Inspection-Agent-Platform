from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import PageParams


class AgentMetricsResponse(BaseModel):
    execution_count: int = Field(..., description="Total execution count")
    success_count: int = Field(..., description="Successful execution count")
    success_rate: float = Field(..., description="Success rate (0-1)")
    avg_latency_ms: float = Field(..., description="Average latency in milliseconds")
    last_executed_at: Optional[datetime] = Field(None, description="Last execution time")

    model_config = {"from_attributes": True}


class AgentConfigVersionResponse(BaseModel):
    id: str
    agent_id: str
    version: int
    config_snapshot: dict
    created_by: Optional[str]
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class BatchUpdateStatusRequest(BaseModel):
    agent_ids: list[str] = Field(..., min_length=1, description="List of agent IDs to update")
    is_active: bool = Field(..., description="Target status")


class BatchDeleteRequest(BaseModel):
    agent_ids: list[str] = Field(..., min_length=1, description="List of agent IDs to delete")


class BatchOperationResponse(BaseModel):
    success_count: int = Field(..., description="Number of successfully updated agents")
    failed_count: int = Field(..., description="Number of failed updates")
    total_count: int = Field(..., description="Total agents in request")


class CreateConfigVersionRequest(BaseModel):
    prompt_version_id: Optional[str] = None
    workflow_binding: Optional[str] = None
    intent_config_id: Optional[str] = None


class RollbackConfigRequest(BaseModel):
    version: int = Field(..., ge=1, description="Version to rollback to")


class ConfigVersionListQuery(PageParams):
    agent_id: str = Field(..., description="Agent ID")

    def to_filters(self) -> dict:
        return {"agent_id": self.agent_id}
