from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=12, ge=1, le=200)
    keyword: str | None = None
    category: str | None = None
    status: str | None = None
    risk_level: str | None = None
    has_binding: bool | None = None
    source_type: str | None = None
    sort_by: str | None = None
    sort_order: str | None = None


class ToolExecutionListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)
    tool_id: str | None = None
    agent_id: str | None = None
    status: str | None = None
    execution_type: str | None = None


class ToolCreate(BaseModel):
    tool_key: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    category: str | None = None
    tool_type: str | None = None
    risk_level: str | None = None
    is_readonly: bool = True
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    returns_schema: dict[str, Any] = Field(default_factory=dict)
    access_roles: list[str] = Field(default_factory=list)
    endpoint: str | None = None
    method: str | None = None
    handler_path: str | None = None
    auth_type: str | None = None
    timeout_ms: int = Field(default=30000, ge=1)
    rate_limit_rpm: int = Field(default=60, ge=1)


class ToolUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    category: str | None = None
    risk_level: str | None = None
    is_readonly: bool | None = None


class ToolStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)


class ToolTestRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ToolVersionCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=32)
    display_name: str | None = None
    description: str | None = None
    parameters_schema: dict[str, Any] | None = None
    returns_schema: dict[str, Any] | None = None
    endpoint: str | None = None
    method: str | None = None
    handler_path: str | None = None
    auth_type: str | None = None
    timeout_ms: int | None = None
    rate_limit_rpm: int | None = None


class BindingCreate(BaseModel):
    agent_id: str = Field(..., min_length=1)
    tool_id: str = Field(..., min_length=1)
    tool_version_id: str | None = None
    auto_call_enabled: bool = True
    approval_required: bool = False
    allowed_intents: list[str] | None = None


class BindingUpdate(BaseModel):
    auto_call_enabled: bool | None = None
    approval_required: bool | None = None
    allowed_intents: list[str] | None = None
    binding_status: str | None = None


class TrendPoint(BaseModel):
    time: str
    value: float


class ToolVersionResponse(BaseModel):
    id: str
    tool_id: str
    version: str
    display_name: str
    description: str
    endpoint: str | None = None
    method: str | None = None
    handler_path: str | None = None
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    returns_schema: dict[str, Any] = Field(default_factory=dict)
    auth_type: str = "none"
    timeout_ms: int
    retry_policy: dict[str, Any] | None = None
    rate_limit_rpm: int
    status: str
    created_by: str = "system"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ToolExecutionResponse(BaseModel):
    id: str
    tool_id: str
    tool_name: str
    agent_id: str = ""
    agent_name: str = "未绑定"
    task_id: str | None = None
    execution_type: str = "runtime"
    status: str
    duration_ms: int = 0
    input_summary: str = ""
    output_summary: str = ""
    error_message: str | None = None
    trace_id: str
    created_at: datetime | None = None


class AgentToolBindingResponse(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    tool_id: str
    tool_name: str
    tool_version_id: str
    tool_version: str
    binding_status: str
    auto_call_enabled: bool
    approval_required: bool
    allowed_scenarios: list[str] = Field(default_factory=list)
    rate_limit: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AuditLogEntryResponse(BaseModel):
    id: str
    tool_id: str
    action: str
    operator: str
    detail: str
    created_at: datetime | None = None


class ToolResponse(BaseModel):
    id: str
    tool_key: str
    display_name: str
    description: str
    category: str
    tool_type: str
    status: str
    risk_level: str
    is_readonly: bool
    source_type: str
    health_status: str
    active_version: str
    bound_agent_names: list[str] = Field(default_factory=list)
    today_calls: int = 0
    success_rate: float = 0.0
    avg_latency_ms: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ToolDetailResponse(ToolResponse):
    active_version_id: str
    versions: list[ToolVersionResponse] = Field(default_factory=list)
    executions: list[ToolExecutionResponse] = Field(default_factory=list)
    bindings: list[AgentToolBindingResponse] = Field(default_factory=list)
    endpoint: str | None = None
    method: str | None = None
    handler_path: str | None = None
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    returns_schema: dict[str, Any] = Field(default_factory=dict)
    auth_type: str = "none"
    secret_ref: str | None = None
    timeout_ms: int = 30000
    retry_policy: dict[str, Any] | None = None
    rate_limit_rpm: int = 60
    audit_logs: list[AuditLogEntryResponse] = Field(default_factory=list)


class ToolOverviewResponse(BaseModel):
    total_tools: int
    active_tools: int
    error_tools: int
    today_calls: int
    avg_latency_ms: int
    high_risk_tools: int
    call_trend: list[TrendPoint]
    health_distribution: dict[str, int]
    error_trend: list[TrendPoint]
    top_failing: list[dict[str, Any]]
    high_latency: list[dict[str, Any]]
    pending_risk_tools: list[dict[str, Any]]
    critical_dependencies: list[dict[str, Any]]


class ToolExecutionOverviewResponse(BaseModel):
    today_calls: int
    success_rate: float
    avg_latency_ms: int
    failed_count: int
    call_trend: list[TrendPoint]
    error_trend: list[TrendPoint]
    latency_trend: list[TrendPoint]


class ToolTestResultResponse(BaseModel):
    status: str
    duration_ms: int
    output: Any = None
    error: str | None = None
    trace_id: str
