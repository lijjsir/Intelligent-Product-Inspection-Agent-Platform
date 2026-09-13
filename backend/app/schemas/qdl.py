from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


QDL_VERSION = "qdl-v2"
QDL_LEGACY_VERSION = "qdl-json-v1"

KnowledgeLevel = Literal["fact", "decision", "rule", "pattern", "concept", "hypothesis"]
PropertyLevel = Literal["low", "medium", "high", "unknown"]
ScopeType = Literal["meeting_room", "user", "agent", "org_space", "collab_thread"]
ExtractionMethod = Literal["llm", "heuristic", "mixed"]
GovernanceStatus = Literal[
    "candidate",
    "confirmed",
    "disputed",
    "active",
    "rejected",
    "isolated",
    "superseded",
    "discarded",
]


class QDLStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QDLClaim(QDLStrictModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=8000)
    type: str = Field(min_length=1, max_length=64)


class QDLPropertyAssessment(QDLStrictModel):
    level: PropertyLevel = "unknown"
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str | None = Field(default=None, max_length=500)


def _unknown_property() -> QDLPropertyAssessment:
    return QDLPropertyAssessment()


class QDLKnowledgeProperties(QDLStrictModel):
    abstraction: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    environment: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    boundary: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    dynamic: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    social: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    tacit: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    hierarchy: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    stability: QDLPropertyAssessment = Field(default_factory=_unknown_property)
    extensions: dict[str, QDLPropertyAssessment] = Field(default_factory=dict)


class QDLEntity(QDLStrictModel):
    entity_type: Literal["product", "batch", "task", "standard", "role", "other"]
    value: str = Field(min_length=1, max_length=256)
    entity_id: str | None = Field(default=None, max_length=256)
    name: str | None = Field(default=None, max_length=256)
    resolution_status: Literal["resolved", "ambiguous", "unresolved"] = "unresolved"
    confidence: float | None = Field(default=None, ge=0, le=1)


class QDLApplicability(QDLStrictModel):
    scope_type: ScopeType = "meeting_room"
    scope_id: str | None = Field(default=None, max_length=256)
    conditions: list[str] = Field(default_factory=list, max_length=30)
    business_tags: dict[str, list[str]] = Field(default_factory=dict)


class QDLEvidence(QDLStrictModel):
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str | None = Field(default=None, max_length=256)
    message_id: str | None = Field(default=None, max_length=256)
    quote_text: str | None = Field(default=None, max_length=8000)
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def ensure_locator(self) -> "QDLEvidence":
        if not self.source_id and not self.message_id:
            raise ValueError("evidence requires source_id or message_id")
        if self.span_start is not None and self.span_end is not None and self.span_end < self.span_start:
            raise ValueError("evidence span_end must not precede span_start")
        return self


class QDLRelation(QDLStrictModel):
    relation_type: Literal["supports", "contradicts", "supplements", "refines", "depends_on", "derived_from"]
    target_id: str = Field(min_length=1, max_length=256)
    status: str | None = Field(default=None, max_length=64)
    confidence: float | None = Field(default=None, ge=0, le=1)
    note: str | None = Field(default=None, max_length=1000)


class QDLProvenance(QDLStrictModel):
    org_id: str | None = Field(default=None, max_length=128)
    room_id: str = Field(min_length=1, max_length=128)
    message_ids: list[str] = Field(default_factory=list, max_length=100)
    extraction_method: ExtractionMethod
    model_id: str | None = Field(default=None, max_length=256)
    trace_id: str | None = Field(default=None, max_length=256)
    source_hash: str | None = Field(default=None, max_length=128)
    generated_at: datetime


class QDLGovernance(QDLStrictModel):
    status: GovernanceStatus = "candidate"
    requires_human_confirmation: bool = True
    confirmed_by: str | None = Field(default=None, max_length=128)
    confirmed_at: datetime | None = None
    disputed_by: str | None = Field(default=None, max_length=128)
    rejected_by: str | None = Field(default=None, max_length=128)


class QDLConsensus(QDLStrictModel):
    status: Literal["candidate", "confirmed", "disputed", "rejected"] = "candidate"
    support_count: int = Field(default=0, ge=0)
    oppose_count: int = Field(default=0, ge=0)
    confirmed_by: list[str] = Field(default_factory=list, max_length=100)


class QDLLifecycle(QDLStrictModel):
    revision: int = Field(default=1, ge=1)
    parent_memory_id: str | None = Field(default=None, max_length=128)
    effective_at: datetime | None = None
    supersedes_memory_id: str | None = Field(default=None, max_length=128)
    superseded_by_memory_id: str | None = Field(default=None, max_length=128)


class QDLDocument(QDLStrictModel):
    version: Literal["qdl-v2"] = QDL_VERSION
    knowledge_level: KnowledgeLevel
    claim: QDLClaim
    properties: QDLKnowledgeProperties = Field(default_factory=QDLKnowledgeProperties)
    entities: list[QDLEntity] = Field(default_factory=list, max_length=100)
    applicability: QDLApplicability
    evidence: list[QDLEvidence] = Field(min_length=1, max_length=100)
    relations: list[QDLRelation] = Field(default_factory=list, max_length=100)
    provenance: QDLProvenance
    governance: QDLGovernance = Field(default_factory=QDLGovernance)
    consensus: QDLConsensus = Field(default_factory=QDLConsensus)
    lifecycle: QDLLifecycle = Field(default_factory=QDLLifecycle)

    @model_validator(mode="after")
    def ensure_governance_consistency(self) -> "QDLDocument":
        expected = {
            "candidate": "candidate",
            "confirmed": "confirmed",
            "active": "confirmed",
            "disputed": "disputed",
            "rejected": "rejected",
            "discarded": "rejected",
        }.get(self.governance.status)
        if expected and self.consensus.status != expected:
            raise ValueError("governance and consensus status are inconsistent")
        if self.governance.status == "candidate" and not self.governance.requires_human_confirmation:
            raise ValueError("candidate knowledge must require human confirmation")
        return self


@dataclass(frozen=True)
class QDLParseResult:
    document: QDLDocument | None
    schema_version: str | None
    validation_status: Literal["valid", "legacy_mapped", "invalid", "missing"]
    errors: tuple[str, ...] = ()


def knowledge_level_for_memory_type(memory_type: str) -> KnowledgeLevel:
    normalized = str(memory_type or "").strip().lower()
    if normalized in {"quality_fact", "fact", "observation"}:
        return "fact"
    if normalized in {"rule", "standard", "constraint"}:
        return "rule"
    if normalized in {"quality_pattern", "pattern", "lesson"}:
        return "pattern"
    if normalized in {"concept", "definition"}:
        return "concept"
    if normalized in {"risk_insight", "hypothesis", "forecast"}:
        return "hypothesis"
    return "decision"


def parse_qdl(payload: Any) -> QDLParseResult:
    if not isinstance(payload, dict) or not payload:
        return QDLParseResult(None, None, "missing")
    version = str(payload.get("version") or "") or None
    try:
        if version == QDL_VERSION:
            return QDLParseResult(QDLDocument.model_validate(payload), version, "valid")
        if version == QDL_LEGACY_VERSION:
            return QDLParseResult(qdl_v1_to_v2(payload), version, "legacy_mapped")
        return QDLParseResult(None, version, "invalid", ("unsupported QDL version",))
    except ValidationError as exc:
        errors = tuple(
            f"{'.'.join(str(part) for part in item.get('loc') or ())}: {item.get('msg')}"
            for item in exc.errors()
        )
        return QDLParseResult(None, version, "invalid", errors)


def qdl_v1_to_v2(payload: dict[str, Any]) -> QDLDocument:
    claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else {}
    consensus = payload.get("consensus") if isinstance(payload.get("consensus"), dict) else {}
    concept = payload.get("concept") if isinstance(payload.get("concept"), dict) else {}
    conflict = payload.get("conflict") if isinstance(payload.get("conflict"), dict) else {}
    evidence_items: list[QDLEvidence] = []
    room_id = "legacy-unknown"
    message_ids: list[str] = []
    for raw in list(payload.get("evidence") or []):
        if not isinstance(raw, dict):
            continue
        source_type = str(raw.get("type") or raw.get("source_type") or "legacy_source")
        source_id = str(raw.get("id") or raw.get("source_id") or "") or None
        message_id = source_id if source_type == "meeting_message" else None
        if source_type == "meeting_room" and source_id:
            room_id = source_id
        if message_id:
            message_ids.append(message_id)
        evidence_items.append(
            QDLEvidence(
                source_type=source_type,
                source_id=source_id,
                message_id=message_id,
                quote_text=str(raw.get("text") or raw.get("quote_text") or "") or None,
            )
        )
    if not evidence_items:
        evidence_items.append(QDLEvidence(source_type="legacy_qdl", source_id=QDL_LEGACY_VERSION))

    tags = concept.get("tags") if isinstance(concept.get("tags"), dict) else {}
    entities: list[QDLEntity] = []
    tag_mapping = {
        "product_ids": "product",
        "batch_nos": "batch",
        "inspection_task_ids": "task",
        "task_ids": "task",
        "standard_ids": "standard",
    }
    for key, entity_type in tag_mapping.items():
        for value in list(tags.get(key) or []):
            entities.append(
                QDLEntity(
                    entity_type=entity_type,
                    value=str(value),
                    entity_id=str(value),
                    resolution_status="resolved",
                    confidence=1,
                )
            )

    relations: list[QDLRelation] = []
    conflicting_id = str(conflict.get("conflicting_memory_id") or "")
    if conflicting_id:
        relations.append(QDLRelation(relation_type="contradicts", target_id=conflicting_id))
    for memory_id in list(conflict.get("related_memory_ids") or []):
        target_id = str(memory_id or "")
        if target_id and target_id != conflicting_id:
            relations.append(QDLRelation(relation_type="supplements", target_id=target_id))

    is_confirmed = str(consensus.get("status") or "candidate") == "confirmed"
    confirmed_by = str(consensus.get("confirmed_by") or "") or None
    confirmed_at = consensus.get("confirmed_at")
    return QDLDocument(
        knowledge_level=knowledge_level_for_memory_type(str(claim.get("type") or concept.get("kind") or "decision")),
        claim=QDLClaim(
            title=str(claim.get("title") or concept.get("name") or "Legacy meeting knowledge"),
            text=str(claim.get("text") or claim.get("title") or concept.get("name") or "Legacy meeting knowledge"),
            type=str(claim.get("type") or concept.get("kind") or "decision"),
        ),
        properties=QDLKnowledgeProperties(),
        entities=entities,
        applicability=QDLApplicability(scope_type="meeting_room", scope_id=None if room_id == "legacy-unknown" else room_id, business_tags=tags),
        evidence=evidence_items,
        relations=relations,
        provenance=QDLProvenance(
            room_id=room_id,
            message_ids=message_ids,
            extraction_method="heuristic",
            generated_at=datetime.utcnow(),
        ),
        governance=QDLGovernance(
            status="confirmed" if is_confirmed else "candidate",
            requires_human_confirmation=not is_confirmed,
            confirmed_by=confirmed_by,
            confirmed_at=confirmed_at,
        ),
        consensus=QDLConsensus(
            status="confirmed" if is_confirmed else "candidate",
            confirmed_by=[confirmed_by] if confirmed_by else [],
        ),
        lifecycle=QDLLifecycle(),
    )
