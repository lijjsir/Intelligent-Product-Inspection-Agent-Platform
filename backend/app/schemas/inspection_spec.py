from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InspectionSpecItemBase(BaseModel):
    defect_type: str = Field(..., min_length=1, max_length=64)
    severity: str = Field(default="major", min_length=1, max_length=16)
    disposition: str = Field(default="fail", min_length=1, max_length=32)
    confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    zone_name: str | None = Field(default=None, max_length=64)
    max_count: int | None = Field(default=None, ge=1)
    description: str | None = None


class InspectionSpecItemCreate(InspectionSpecItemBase):
    pass


class InspectionSpecItemResponse(InspectionSpecItemBase):
    id: str
    created_at: datetime
    updated_at: datetime


class InspectionSpecBase(BaseModel):
    spec_code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(default="v1", min_length=1, max_length=32)
    product_id: str | None = Field(default=None, max_length=64)
    required_image_count: int = Field(default=1, ge=1, le=20)
    ai_gate_confidence_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    ai_gate_evidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    ai_gate_traceability_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    auto_pass_enabled: bool = False
    is_active: bool = True


class InspectionSpecCreate(InspectionSpecBase):
    org_id: str | None = None
    items: list[InspectionSpecItemCreate] = Field(..., min_length=1)


class InspectionSpecUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    version: str | None = Field(default=None, min_length=1, max_length=32)
    product_id: str | None = Field(default=None, max_length=64)
    required_image_count: int | None = Field(default=None, ge=1, le=20)
    ai_gate_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    ai_gate_evidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    ai_gate_traceability_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    auto_pass_enabled: bool | None = None
    is_active: bool | None = None
    items: list[InspectionSpecItemCreate] | None = Field(default=None, min_length=1)


class InspectionSpecResponse(InspectionSpecBase):
    id: str
    org_id: str | None = None
    items: list[InspectionSpecItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
