from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import PageParams


# ── Enums ──

SyncStatus = str  # "synced" | "code_changed" | "db_override" | "conflict" | "missing_in_code"
VersionStatus = str  # "draft" | "review" | "approved" | "deprecated"
PromptSource = str  # "code_default" | "database"


# ── PromptDefinition ──

class PromptDefinitionSummary(BaseModel):
    id: str
    prompt_key: str
    display_name: str
    usage_location: Optional[str] = None
    agent_name: Optional[str] = None
    stage_name: Optional[str] = None
    source_file: Optional[str] = None
    sync_status: str = "synced"
    current_source: str = "code_default"
    active_version: Optional[int] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PromptVersionItem(BaseModel):
    id: str
    version: int
    content: str
    content_hash: str
    status: str = "draft"
    change_summary: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptDefinitionDetail(BaseModel):
    id: str
    prompt_key: str
    display_name: str
    description: Optional[str] = None
    agent_key: Optional[str] = None
    agent_name: Optional[str] = None
    stage_key: Optional[str] = None
    stage_name: Optional[str] = None
    usage_location: Optional[str] = None
    source_file: Optional[str] = None
    source_symbol: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    current_source: str = "code_default"
    sync_status: str = "synced"
    code_default_content: str = ""
    active_content: str = ""
    active_version: Optional[int] = None
    active_content_hash: str = ""
    versions: list[PromptVersionItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PromptDefinitionListQuery(PageParams):
    agent_key: Optional[str] = None
    stage_key: Optional[str] = None
    keyword: Optional[str] = None
    sync_status: Optional[str] = None
    source: Optional[str] = None


# ── Version Create / Publish ──

class CreateVersionRequest(BaseModel):
    content: str
    change_summary: Optional[str] = None
    base_hash: Optional[str] = None


class PublishVersionResponse(BaseModel):
    version_id: str
    version: int
    status: str = "approved"


class RollbackRequest(BaseModel):
    target_version_id: str


# ── Diff ──

class DiffRequest(BaseModel):
    left: str = "code_default"  # "code_default" | "active" | "draft"
    right: str = "active"


class DiffResponse(BaseModel):
    left_label: str
    right_label: str
    left_content: str
    right_content: str


# ── Sync ──

class SyncScanResponse(BaseModel):
    scanned: int
    created: int
    updated: int
    missing: int


# ── Overview ──

class PromptOverviewResponse(BaseModel):
    total: int = 0
    db_override: int = 0
    code_changed: int = 0
    conflict: int = 0
    missing_in_code: int = 0
