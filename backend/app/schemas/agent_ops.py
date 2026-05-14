from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.schemas.common import PageParams


class AgentDefinitionBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., max_length=100, description="Agent name")
    description: Optional[str] = Field(default=None, description="Agent description")
    prompt_version_id: Optional[str] = Field(default=None, description="Associated prompt version ID")
    workflow_binding: Optional[str] = Field(default=None, max_length=100, description="Workflow binding")
    intent_config_id: Optional[str] = Field(default=None, description="Intent config ID")
    is_active: bool = Field(default=True, description="Whether agent is active")

    @field_validator("description", "prompt_version_id", "workflow_binding", "intent_config_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


class AgentDefinitionCreate(AgentDefinitionBase):
    pass


class AgentDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    prompt_version_id: Optional[str] = None
    workflow_binding: Optional[str] = None
    intent_config_id: Optional[str] = None
    is_active: Optional[bool] = None


class AgentDefinitionResponse(AgentDefinitionBase):
    id: str
    org_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentDefinitionListQuery(PageParams):
    name: Optional[str] = None
    is_active: Optional[bool] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}


class PromptVersionBase(BaseModel):
    name: str = Field(..., max_length=100, description="Prompt name")
    content: str = Field(..., description="Prompt content")
    version: int = Field(default=1, ge=1, description="Version number")
    status: str = Field(default="draft", description="Status: draft/review/approved/deprecated")


class PromptVersionCreate(PromptVersionBase):
    pass


class PromptVersionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    content: Optional[str] = None
    version: Optional[int] = None
    status: Optional[str] = None


class PromptVersionResponse(PromptVersionBase):
    id: str
    org_id: str
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptVersionListQuery(PageParams):
    name: Optional[str] = None
    status: Optional[str] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}


class IntentRouteBase(BaseModel):
    intent_name: str = Field(..., max_length=100, description="Intent name")
    agent_id: Optional[str] = Field(None, description="Associated agent ID")
    priority: int = Field(default=0, ge=0, description="Priority for routing")
    sample_count: int = Field(default=0, ge=0, description="Number of samples")
    is_active: bool = Field(default=True, description="Whether route is active")


class IntentRouteCreate(IntentRouteBase):
    pass


class IntentRouteUpdate(BaseModel):
    intent_name: Optional[str] = Field(None, max_length=100)
    agent_id: Optional[str] = None
    priority: Optional[int] = None
    sample_count: Optional[int] = None
    is_active: Optional[bool] = None


class IntentRouteResponse(IntentRouteBase):
    id: str
    org_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntentRouteListQuery(PageParams):
    intent_name: Optional[str] = None
    is_active: Optional[bool] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}


class RagAnalysisStats(BaseModel):
    total_queries: int = Field(default=0, description="Total RAG queries")
    avg_hit_rate: float = Field(default=0.0, description="Average hit rate")
    avg_citation_coverage: float = Field(default=0.0, description="Average citation coverage")
    empty_recall_count: int = Field(default=0, description="Empty recall count")
    avg_latency_ms: float = Field(default=0.0, description="Average latency in ms")


class RagAnalysisItem(BaseModel):
    task_id: str
    session_id: Optional[str] = None
    query: Optional[str] = Field(default=None, description="Query text if available")
    rag_space_id: Optional[str] = None
    rag_space_name: Optional[str] = None
    product_family: Optional[str] = None
    product_id: Optional[str] = None
    verdict: Optional[str] = None
    source_graph: Optional[str] = None
    top_sources: list[str] = Field(default_factory=list)
    rule_hits: list[str] = Field(default_factory=list)
    hit_rate: float
    citation_coverage: float
    latency_ms: float
    created_at: datetime


class RagAnalysisBreakdownItem(BaseModel):
    key: str
    count: int = 0


class RagEvidenceImpactItem(BaseModel):
    rule_key: str
    count: int = 0


class RagAnalysisResponse(BaseModel):
    stats: RagAnalysisStats
    recent_items: list[RagAnalysisItem]
    space_breakdown: list[RagAnalysisBreakdownItem] = Field(default_factory=list)
    source_graph_breakdown: list[RagAnalysisBreakdownItem] = Field(default_factory=list)
    product_family_breakdown: list[RagAnalysisBreakdownItem] = Field(default_factory=list)
    evidence_impact: list[RagEvidenceImpactItem] = Field(default_factory=list)
