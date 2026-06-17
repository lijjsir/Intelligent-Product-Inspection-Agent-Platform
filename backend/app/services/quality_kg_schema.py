from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


NODE_TYPES = (
    "DetectionDomain",
    "ProductCategory",
    "Standard",
    "StandardClause",
    "InspectionItem",
    "Metric",
    "DefectType",
    "RiskType",
    "Cause",
    "Action",
)

RELATION_TYPES = (
    "HAS_CATEGORY",
    "APPLIES_STANDARD",
    "HAS_CLAUSE",
    "REQUIRES_ITEM",
    "HAS_METRIC",
    "INDICATES_DEFECT",
    "LEADS_TO_RISK",
    "MAY_BE_CAUSED_BY",
    "CAUSE_HANDLED_BY",
    "RISK_REQUIRES_ACTION",
    "METRIC_ABNORMAL_ACTION",
    "DEFECT_SUGGESTS_ACTION",
    "ITEM_DIRECT_ACTION",
)


class QualityKnowledgeChain(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str = Field(..., min_length=1, max_length=80)
    product_category: str = Field(..., min_length=1, max_length=80)
    standard: str | None = Field(default=None, max_length=80)
    standard_clause: str | None = Field(default=None, max_length=80)
    inspection_item: str | None = Field(default=None, max_length=80)
    metric: str | None = Field(default=None, max_length=80)
    defect_type: str | None = Field(default=None, max_length=80)
    risk_type: str | None = Field(default=None, max_length=80)
    cause: str | None = Field(default=None, max_length=80)
    actions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="inspection_result", max_length=64)

    @field_validator(
        "standard",
        "standard_clause",
        "inspection_item",
        "metric",
        "defect_type",
        "risk_type",
        "cause",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("actions", mode="before")
    @classmethod
    def normalize_actions(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("actions must be a list")
        return [text for item in value if (text := str(item).strip())]


class QualityKnowledgeChainBatch(BaseModel):
    items: list[QualityKnowledgeChain] = Field(..., min_length=1)


class QualityKgRelationshipDelete(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    relation_type: str = Field(..., min_length=1, max_length=64)
    start_node_id: str = Field(..., min_length=1)
    end_node_id: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1, max_length=80)
    product_category: str = Field(default="", max_length=80)


class QualityKgNodeDelete(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    node_id: str = Field(..., min_length=1)


@dataclass(slots=True)
class QualityKgNode:
    id: str
    org_id: str
    type: str
    name: str
    normalized_name: str
    domain: str


@dataclass(slots=True)
class QualityKgRelationship:
    type: str
    start_node_id: str
    end_node_id: str
    org_id: str
    domain: str
    product_category: str
    confidence: float = 1.0
    source: str = "inspection_result"
