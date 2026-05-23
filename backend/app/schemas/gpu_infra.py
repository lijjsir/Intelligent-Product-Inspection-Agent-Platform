from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


GPU_NODE_STATUSES = {"online", "offline", "error", "disabled"}


class GpuComputeNodeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    host: str = Field(..., min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: str = Field(..., min_length=1, max_length=128)
    ssh_password: str | None = None
    ssh_private_key: str | None = None
    total_gpu_count: int = Field(default=1, ge=1, le=64)
    metadata_json: dict[str, Any] | None = None

    @field_validator("name", "host", "ssh_username")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("must not be blank")
        return text


class GpuComputeNodeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, min_length=1, max_length=128)
    ssh_password: str | None = None
    ssh_private_key: str | None = None
    total_gpu_count: int | None = Field(default=None, ge=1, le=64)
    metadata_json: dict[str, Any] | None = None


class GpuNodeHeartbeatRequest(BaseModel):
    cpu_usage: float | None = Field(default=None, ge=0, le=100)
    memory_usage: float | None = Field(default=None, ge=0, le=100)
    gpu_usage: float | None = Field(default=None, ge=0, le=100)
    gpu_bitmap: str | None = None


class GpuComputeNodeResponse(BaseModel):
    id: str
    org_id: str
    created_by: str | None = None
    name: str
    host: str
    ssh_port: int
    ssh_username: str
    total_gpu_count: int
    available_gpu_count: int
    gpu_bitmap: str
    cpu_usage: float | None = None
    memory_usage: float | None = None
    gpu_usage: float | None = None
    status: str
    last_heartbeat: datetime | None = None
    last_probe_at: datetime | None = None
    last_probe_error: str | None = None
    probe_status: str | None = None
    hardware_summary: dict[str, Any] | None = None
    gpu_devices: list[dict[str, Any]] = Field(default_factory=list)
    load_score: float | None = None
    metadata_json: dict[str, Any] | None = None
    has_ssh_password: bool = False
    has_ssh_private_key: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class GpuNodeMetricRefreshResponse(BaseModel):
    node: GpuComputeNodeResponse
    metrics: dict[str, Any] = Field(default_factory=dict)


class GpuNodeConnectionTestResponse(BaseModel):
    success: bool
    message: str
