"""Backfill unified memory governance provenance, evidence, scopes and sync outbox.

Run after Alembic revision 0095:
    PYTHONPATH=. python scripts/backfill_memory_governance.py --dry-run
    PYTHONPATH=. python scripts/backfill_memory_governance.py --report-path memory_governance_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.ids import uuid7
from app.models.meeting import MemoryScopeBinding
from app.models.memory import MemoryCandidateSupport, MemoryEvidence, MemoryItem, MemoryOrigin
from app.repositories.memory_repo import (
    MemoryEvidenceRepository,
    MemoryOriginRepository,
    MemorySyncOutboxRepository,
    UnifiedMemoryGovernanceRepository,
)
from app.services.memory_governance_domain import (
    calculate_readiness,
    default_governance_target,
    default_home_scope,
    evidence_role_from_legacy_support,
    legacy_review_status,
    normalize_source_kind,
)
from app.services.memory_vector_service import CANDIDATE_MEMORY_COLLECTION, MEMORY_COLLECTION
from infra.database.session import get_session


def _text(value: Any) -> str:
    return str(value or "").strip()


def _uuid_text(value: Any) -> str | None:
    raw = _text(value)
    return raw or None


def _dedupe_key(*parts: Any) -> str:
    raw = "\x1f".join(_text(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _source_kind(item: MemoryItem) -> str:
    content = dict(item.content_json or {})
    evidence = dict(item.evidence_pointers or {})
    raw = (
        content.get("source_type")
        or evidence.get("source_kind")
        or evidence.get("source")
        or ("meeting" if str(item.memory_id).startswith("mem_meeting_") else None)
        or item.created_by_type
    )
    return normalize_source_kind(_text(raw))


def _source_spans(item: MemoryItem) -> list[dict[str, Any]]:
    content = dict(item.content_json or {})
    return [dict(row) for row in list(content.get("source_spans") or []) if isinstance(row, dict)]


def _origin_specs(item: MemoryItem, source_kind: str) -> list[dict[str, Any]]:
    content = dict(item.content_json or {})
    evidence = dict(item.evidence_pointers or {})
    spans = _source_spans(item)
    specs: list[dict[str, Any]] = []
    for span in spans:
        source_id = _text(span.get("message_id") or span.get("id"))
        if source_id:
            specs.append({
                "source_type": "meeting_message" if source_kind == "meeting" else "source_span",
                "source_id": source_id,
                "source_span": span,
                "metadata": {"source_room_id": content.get("source_id") or evidence.get("meeting_room_id")},
            })
    if not specs:
        message_id = _text(content.get("source_message_id") or item.source_message_id or evidence.get("source_message_id"))
        if message_id:
            specs.append({
                "source_type": "meeting_message" if source_kind == "meeting" else "message",
                "source_id": message_id,
                "source_span": None,
                "metadata": {"source_room_id": content.get("source_id") or evidence.get("meeting_room_id")},
            })
    if not specs:
        source_id = (
            _text(item.source_task_id or item.task_id)
            or _text(item.rag_space_id)
            or _text(content.get("source_id"))
            or _text(evidence.get("meeting_room_id"))
            or _text(item.user_id)
            or _text(item.source_trace_id or item.trace_id)
        )
        source_type = {
            "meeting": "meeting_room",
            "task": "inspection_task",
            "rag": "rag_space",
            "chat": "user",
            "agent": "agent",
            "human_review": "user",
        }.get(source_kind, "trace")
        if source_id:
            specs.append({"source_type": source_type, "source_id": source_id, "source_span": None, "metadata": {}})
    return specs


def _applicability(item: MemoryItem) -> dict[str, Any]:
    existing = dict(item.applicability_json or {})
    scope = dict(item.scope_json or {})
    content = dict(item.content_json or {})
    business = content.get("business_context") if isinstance(content.get("business_context"), dict) else {}
    values = {
        "task_id": item.task_id,
        "product_line": item.product_line,
        "rag_space_id": item.rag_space_id,
        "standard_code": item.standard_code,
        "standard_version": item.standard_version,
        "target_market": item.target_market,
        "product_category": item.product_category,
        "task_ids": scope.get("task_ids") or business.get("task_ids"),
        "product_ids": scope.get("product_ids") or business.get("product_ids"),
        "batch_nos": scope.get("batch_nos") or business.get("batch_nos"),
        "standard_ids": scope.get("standard_ids") or business.get("standard_ids"),
    }
    for key, value in values.items():
        if value not in (None, "", []):
            existing[key] = value
    return existing


def _home_scope(item: MemoryItem, source_kind: str) -> tuple[str | None, str | None]:
    content = dict(item.content_json or {})
    evidence = dict(item.evidence_pointers or {})
    scope = dict(item.scope_json or {})
    return default_home_scope(
        source_kind=source_kind,
        org_id=str(item.org_id),
        user_id=_uuid_text(item.user_id),
        meeting_room_id=_text(
            content.get("source_id")
            or evidence.get("meeting_room_id")
            or scope.get("meeting_room_id")
            or scope.get("room_id")
        ) or None,
        task_id=_text(item.task_id or item.source_task_id) or None,
        rag_space_id=_text(item.rag_space_id) or None,
        agent_id=_text(evidence.get("agent_id") or content.get("agent_id")) or None,
    )


def _vector_payload(item: MemoryItem, *, collection: str, status: str, bindings: list[MemoryScopeBinding]) -> dict[str, Any]:
    return {
        "collection": collection,
        "memory_id": item.memory_id,
        "org_id": str(item.org_id),
        "user_id": str(item.user_id or ""),
        "memory_type": item.memory_type,
        "status": status,
        "summary": item.content_summary or "",
        "trust_score": float(item.trust_score or 0),
        "confidence": float(item.confidence or 0),
        "expires_at": item.expires_at.isoformat() if item.expires_at else "",
        "product_line": item.product_line or "",
        "rag_space_id": item.rag_space_id or "",
        "task_id": item.task_id or item.source_task_id or "",
        "extra_payload": {
            "review_status": item.review_status,
            "scope_bindings": [
                {
                    "scope_type": row.scope_type,
                    "scope_id": row.scope_id,
                    "binding_kind": row.binding_kind,
                    "binding_status": row.binding_status,
                }
                for row in bindings
                if row.binding_status == "active"
            ],
        },
    }


async def _backfill(*, dry_run: bool) -> dict[str, Any]:
    report: Counter[str] = Counter()
    review_reasons: Counter[str] = Counter()
    async with get_session() as session:
        result = await session.execute(
            select(MemoryItem).where(MemoryItem.deleted_at.is_(None)).order_by(MemoryItem.created_at.asc())
        )
        items = list(result.scalars().all())
        report["total"] = len(items)

        for item in items:
            source_kind = _source_kind(item)
            origin_repo = MemoryOriginRepository(session, str(item.org_id))
            evidence_repo = MemoryEvidenceRepository(session, str(item.org_id))
            governance_repo = UnifiedMemoryGovernanceRepository(session, str(item.org_id))
            outbox_repo = MemorySyncOutboxRepository(session, str(item.org_id))

            review_status, migration_required, migration_reason = legacy_review_status(item.status)
            if item.review_status in {"approved", "disputed", "rejected", "isolated", "superseded"}:
                review_status = item.review_status
            item.review_status = review_status
            item.applicability_json = _applicability(item)
            content_type = _text((item.content_json or {}).get("memory_type"))
            if content_type:
                item.memory_type = content_type

            origins_created = 0
            for spec in _origin_specs(item, source_kind):
                dedupe = _dedupe_key(source_kind, spec["source_type"], spec["source_id"])
                origin, created = await origin_repo.create_if_absent(
                    MemoryOrigin(
                        id=str(uuid7()),
                        org_id=item.org_id,
                        memory_id=item.memory_id,
                        origin_kind=source_kind,
                        source_type=spec["source_type"],
                        source_id=spec["source_id"],
                        trace_id=item.source_trace_id or item.trace_id,
                        dedupe_key=dedupe,
                        source_span=spec.get("source_span"),
                        metadata_json=spec.get("metadata"),
                        occurred_at=item.created_at,
                    )
                )
                if created:
                    origins_created += 1
                _, evidence_created = await evidence_repo.create_if_absent(
                    MemoryEvidence(
                        id=str(uuid7()),
                        org_id=item.org_id,
                        memory_id=item.memory_id,
                        evidence_role="origin",
                        source_kind=source_kind,
                        source_type=origin.source_type,
                        source_id=origin.source_id,
                        independence_key=dedupe,
                        trace_id=item.source_trace_id or item.trace_id,
                        task_id=item.task_id or item.source_task_id,
                        rag_space_id=item.rag_space_id,
                        evidence_pointer={
                            "origin_id": str(origin.id),
                            "source_span": origin.source_span,
                            "metadata": origin.metadata_json,
                        },
                        confidence=item.confidence,
                        weight=1.0,
                        occurred_at=item.created_at,
                    )
                )
                if evidence_created:
                    report["origin_evidence_created"] += 1
            report["origins_created"] += origins_created

            legacy_result = await session.execute(
                select(MemoryCandidateSupport).where(
                    MemoryCandidateSupport.org_id == item.org_id,
                    MemoryCandidateSupport.candidate_memory_id == item.memory_id,
                )
            )
            for support in legacy_result.scalars().all():
                role = evidence_role_from_legacy_support(support.support_type)
                source_id = _text(
                    support.source_agent
                    or support.task_id
                    or support.rag_space_id
                    or support.document_id
                    or support.chunk_id
                    or support.trace_id
                    or support.id
                )
                independence = _dedupe_key(role, support.source_kind, source_id)
                _, created = await evidence_repo.create_if_absent(
                    MemoryEvidence(
                        id=str(uuid7()),
                        org_id=item.org_id,
                        memory_id=item.memory_id,
                        evidence_role=role,
                        source_kind=normalize_source_kind(support.source_kind),
                        source_type=_text(support.source_kind) or "legacy_support",
                        source_id=source_id,
                        independence_key=independence,
                        trace_id=support.trace_id,
                        task_id=support.task_id,
                        rag_space_id=support.rag_space_id,
                        document_id=support.document_id,
                        chunk_id=support.chunk_id,
                        evidence_pointer=support.evidence_pointer,
                        confidence=support.confidence,
                        weight=support.weight,
                        occurred_at=support.created_at,
                    )
                )
                if created:
                    report["legacy_evidence_migrated"] += 1

            home_type, home_id = _home_scope(item, source_kind)
            bindings = await governance_repo.list_scope_bindings([item.memory_id])
            if home_type and home_id:
                home = next(
                    (row for row in bindings if row.scope_type == home_type and row.scope_id == home_id),
                    None,
                )
                if home is None:
                    home = MemoryScopeBinding(
                        org_id=item.org_id,
                        memory_id=item.memory_id,
                        scope_type=home_type,
                        scope_id=home_id,
                        permission="read",
                        binding_kind="home",
                        binding_status="active",
                        approved_by=item.created_by,
                        approved_at=item.created_at,
                        created_by=item.created_by,
                    )
                    session.add(home)
                    await session.flush()
                    bindings.append(home)
                    report["home_bindings_created"] += 1
                else:
                    home.binding_kind = "home"
                    # Preserve an explicit historical revocation.  Only rows
                    # lacking the new status (from pre-0095 schemas) default
                    # to active.
                    if not getattr(home, "binding_status", None):
                        home.binding_status = "active"
            else:
                migration_required = True
                migration_reason = migration_reason or "home scope could not be inferred"

            for binding in bindings:
                if binding.scope_type == "inspection_task":
                    item.applicability_json = {
                        **(item.applicability_json or {}),
                        "legacy_inspection_task_id": binding.scope_id,
                    }
                    binding.binding_status = "revoked"
                    binding.revoked_at = datetime.now(timezone.utc)
                elif binding.scope_type == "project":
                    item.applicability_json = {
                        **(item.applicability_json or {}),
                        "legacy_project_scope": binding.scope_id,
                    }
                    binding.binding_status = "revoked"
                    binding.revoked_at = datetime.now(timezone.utc)
                    migration_required = True
                    migration_reason = migration_reason or "legacy project access scope requires review"
                elif binding.binding_kind != "home":
                    binding.binding_kind = "shared"

            target_type, target_id = default_governance_target(source_kind, str(item.org_id))
            if item.governance_target_scope_type is None and target_type:
                item.governance_target_scope_type = target_type
                item.governance_target_scope_id = target_id

            stats = await evidence_repo.stats_for_memory(item.memory_id)
            item.origin_evidence_count = int(stats["origin_evidence_count"] or 0)
            item.independent_support_count = int(stats["independent_support_count"] or 0)
            item.support_count = int(stats["support_count"] or 0)
            item.rag_evidence_count = int(stats["rag_evidence_count"] or 0)
            item.agent_verifier_count = int(stats["agent_verifier_count"] or 0)
            item.human_confirmation_count = int(stats["human_confirmation_count"] or 0)
            item.opposition_count = int(stats["opposition_count"] or 0)
            item.negative_count = item.opposition_count
            item.conflict_count = int(stats["conflict_count"] or 0)
            item.human_approved = item.human_confirmation_count > 0 or item.review_status == "approved"
            item.last_evidence_at = stats["last_evidence_at"]
            item.last_supported_at = stats["last_evidence_at"]
            if item.origin_evidence_count < 1:
                migration_required = True
                migration_reason = migration_reason or "missing origin evidence"
            item.migration_review_required = migration_required
            item.migration_review_reason = migration_reason
            if migration_reason:
                review_reasons[migration_reason] += 1

            readiness = calculate_readiness(
                stats,
                review_status=item.review_status,
                migration_review_required=migration_required,
            )
            item.readiness_status = readiness.status
            item.readiness_blockers = readiness.blockers
            item.promotion_score = readiness.score

            active_bindings = [row for row in bindings if row.binding_status == "active"]
            if item.review_status == "approved" and active_bindings:
                await outbox_repo.create_pending(
                    memory_id=item.memory_id,
                    action="UPSERT_ACTIVE_VECTOR",
                    target_backend="qdrant",
                    payload=_vector_payload(item, collection=MEMORY_COLLECTION, status="active", bindings=bindings),
                    trace_id=item.trace_id,
                )
                report["active_vector_outbox"] += 1
            elif item.review_status == "candidate" and item.origin_evidence_count > 0:
                await outbox_repo.create_pending(
                    memory_id=item.memory_id,
                    action="UPSERT_CANDIDATE_VECTOR",
                    target_backend="qdrant",
                    payload=_vector_payload(item, collection=CANDIDATE_MEMORY_COLLECTION, status="candidate", bindings=bindings),
                    trace_id=item.trace_id,
                )
                report["candidate_vector_outbox"] += 1
            await outbox_repo.create_pending(
                memory_id=item.memory_id,
                action="UPSERT_MEMORY_NODE",
                target_backend="neo4j",
                payload={
                    "memory_id": item.memory_id,
                    "org_id": str(item.org_id),
                    "memory_type": item.memory_type,
                    "status": item.review_status,
                    "trust_score": float(item.trust_score or 0),
                    "confidence": float(item.confidence or 0),
                    "scope_key": "|".join(f"{row.scope_type}:{row.scope_id}" for row in active_bindings),
                    "review_status": item.review_status,
                    "origin_kind": source_kind,
                    "scope_bindings_json": json.dumps(
                        [
                            {
                                "scope_type": row.scope_type,
                                "scope_id": row.scope_id,
                                "binding_kind": row.binding_kind,
                                "binding_status": row.binding_status,
                            }
                            for row in bindings
                        ],
                        ensure_ascii=False,
                    ),
                    "applicability_json": json.dumps(item.applicability_json or {}, ensure_ascii=False),
                    "sync_version": 2,
                },
                trace_id=item.trace_id,
            )
            report["graph_outbox"] += 1
            report[f"review_status_{item.review_status}"] += 1
            report[f"readiness_{item.readiness_status}"] += 1
            report["backfilled"] += 1

        await session.flush()
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return {
        **dict(sorted(report.items())),
        "migration_review_reasons": dict(sorted(review_reasons.items())),
        "dry_run": dry_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill unified memory governance data")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-path", type=Path)
    args = parser.parse_args()
    report = asyncio.run(_backfill(dry_run=args.dry_run))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(rendered)
    if args.report_path:
        args.report_path.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
