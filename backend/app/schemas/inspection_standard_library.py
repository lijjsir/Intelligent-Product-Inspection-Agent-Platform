from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InspectionStandardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    product_family: str = Field(..., min_length=1, max_length=128)
    inspection_spec_id: str | None = None
    spec_code: str | None = Field(default=None, max_length=64)
    applicable_product_line_ids: list[str] = Field(default_factory=list)
    applicable_product_sku_ids: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=2000)
    rag_space_ids: list[str] = Field(..., min_length=1)
    is_active: bool = True


class InspectionStandardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    product_family: str | None = Field(default=None, min_length=1, max_length=128)
    inspection_spec_id: str | None = None
    spec_code: str | None = Field(default=None, max_length=64)
    applicable_product_line_ids: list[str] | None = None
    applicable_product_sku_ids: list[str] | None = None
    description: str | None = Field(default=None, max_length=2000)
    rag_space_ids: list[str] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class InspectionStandardRagSpaceSummary(BaseModel):
    id: str
    name: str
    document_count: int = 0
    status: str | None = None


class InspectionStandardResponse(BaseModel):
    id: str
    org_id: str | None = None
    name: str
    product_family: str
    inspection_spec_id: str | None = None
    spec_code: str | None = None
    spec_name: str | None = None
    applicable_product_line_ids: list[str] = Field(default_factory=list)
    applicable_product_sku_ids: list[str] = Field(default_factory=list)
    required_image_count: int | None = None
    required_views: list[str] = Field(default_factory=list)
    auto_pass_enabled: bool | None = None
    ai_gate_confidence_threshold: float | None = None
    ai_gate_evidence_threshold: float | None = None
    ai_gate_traceability_threshold: float | None = None
    description: str | None = None
    rag_space_ids: list[str]
    rag_spaces: list[InspectionStandardRagSpaceSummary] = Field(default_factory=list)
    total_document_count: int = 0
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
