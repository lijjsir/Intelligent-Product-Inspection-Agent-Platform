"""MemoryService - write gate, retrieval, status management, event recording.

Orchestrates MySQL persistence via repositories and Qdrant indexing via MemoryVectorService.
Never bypassed by LangGraph nodes or tools.
"""
from __future__ import annotations

import uuid
import logging
import hashlib
from datetime import datetime, timedelta, timezone

from app.core.ids import uuid7
from app.models.memory import (
    MemoryCandidateSupport,
    MemoryDependencyEdge,
    MemoryEvent,
    MemoryItem,
)
from app.repositories.memory_repo import (
    MemoryCandidateSupportRepository,
    MemoryDependencyRepository,
    MemoryEventRepository,
    MemoryItemRepository,
    MemoryPolicyRepository,
)
from app.schemas.memory import (
    ConflictRelation,
    EventType,
    CandidateListItem,
    CandidateSupportCreate,
    MemoryEventPayload,
    MemoryContext,
    PromotionEvaluationResponse,
    MemorySearchResponse,
    MemoryType,
    MemoryWriteRequest,
    MemoryWriteResponse,
    MemoryStatus,
    MemorySearchRequest,
    MemorySearchItem,
    ScopeFilter,
    MemoryScope,
    EdgeType,
)
from app.services.memory_vector_service import MemoryVectorService, MemoryVectorServiceError

logger = logging.getLogger(__name__)


class MemoryService:
    """Central service for shared memory write gate, retrieval, and lifecycle."""

    def __init__(
        self,
        session,
        org_id: str,
        vector_service: MemoryVectorService | None = None,
        candidate_vector_service: MemoryVectorService | None = None,
    ):
        self._session = session
        self._org_id = org_id
        self._item_repo = MemoryItemRepository(session, org_id)
        self._support_repo = MemoryCandidateSupportRepository(session, org_id)
        self._event_repo = MemoryEventRepository(session, org_id)
        self._dep_repo = MemoryDependencyRepository(session, org_id)
        self._policy_repo = MemoryPolicyRepository(session, org_id)
        self._vector = vector_service
        self._candidate_vector = candidate_vector_service

    # ------------------------------------------------------------------
    # Write Gate
    # ------------------------------------------------------------------

    async def _resolve_policy(self, policy_type: str) -> dict:
        """Load active policy config, falling back to defaults."""
        try:
            policy = await self._policy_repo.get_active(
                policy_key=policy_type,
                policy_type=policy_type,
            )
            if policy and policy.config_json:
                return {**policy.config_json, "version": str(policy.version)}
        except Exception:
            pass
        from agent.contracts.memory_contracts import MemoryPolicyContract
        return MemoryPolicyContract.defaults(policy_type)


    async def write_candidate(self, request: MemoryWriteRequest) -> MemoryWriteResponse:
        """Submit a memory through the candidate gate.

        All reusable long-term memories first land as candidate memories. The
        promotion evaluator may immediately promote a candidate when strong
        evidence is present, but creation and support accumulation still happen
        in the candidate state first.
        """
        warnings: list[str] = []

        # 1. Reject missing required fields
        if not request.trace_id:
            return await self._reject(request, "missing trace_id")
        if not request.source or not request.source.kind:
            return await self._reject(request, "missing source")

        # 2. Check for sensitive content
        sens_check = self._check_sensitive(request.content.summary)
        if sens_check:
            return await self._reject(request, f"sensitive content: {sens_check}")

        if request.confidence < 0.4:
            return await self._reject(request, "confidence_below_candidate_threshold")

        if not request.scope:
            return await self._reject(request, "missing scope")

        # 3. Load policy for write gate metadata
        policy = await self._resolve_policy("write_gate")
        isolate_on_rag = bool(policy.get("isolate_on_rag_conflict", True))

        # 4. Check RAG / standard conflicts (policy-driven)
        if isolate_on_rag:
            if any("conflict_with_rag" in w.lower() or "conflict with rag" in w.lower() for w in request.content.warnings):
                warnings.append("conflicts_with_rag")

        # 5. Determine trust_score and canonical candidate identity
        trust_score = request.confidence
        if any("conflict" in w.lower() for w in request.content.warnings):
            trust_score *= 0.6

        canonical_claim, candidate_key = self._canonicalize_candidate(request)

        idempotency_key = self._make_idempotency_key(request)
        existing = await self._item_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return MemoryWriteResponse(
                memory_id=existing.memory_id,
                status=MemoryStatus(existing.status),
                trust_score=float(existing.trust_score) if existing.trust_score is not None else None,
                confidence=float(existing.confidence) if existing.confidence is not None else None,
                warnings=["idempotent_replay"],
                policy_key=existing.policy_key or "write_gate",
                policy_version=existing.policy_version or str(policy.get("version", "default:v1")),
            )

        matched = await self._item_repo.find_candidate_by_key(
            memory_type=request.memory_type.value,
            candidate_key=candidate_key,
            user_id=request.user_id,
            scope=request.scope.model_dump(exclude_none=True) if request.scope else {},
        )
        if matched:
            support = self._support_from_request(request, matched.memory_id)
            await self.add_candidate_support(matched.memory_id, support, evaluate=False)
            evaluation = await self.evaluate_candidate_promotion(matched.memory_id)
            status = evaluation.status
            return MemoryWriteResponse(
                memory_id=matched.memory_id,
                status=status,
                trust_score=float(getattr(matched, "trust_score", 0) or 0),
                confidence=float(getattr(matched, "confidence", 0) or 0),
                warnings=warnings,
                policy_key=matched.policy_key or "write_gate",
                policy_version=matched.policy_version or str(policy.get("version", "default:v1")),
            )

        semantic_match = await self._match_candidate_semantic(request)
        if semantic_match:
            matched, similarity, conflicted, conflict_keys = semantic_match
            if conflicted:
                await self.contest_candidate(
                    matched.memory_id,
                    trace_id=request.trace_id,
                    reason=f"candidate_slot_conflict:{','.join(conflict_keys)}",
                )
                return MemoryWriteResponse(
                    memory_id=matched.memory_id,
                    status=MemoryStatus.CONTESTED,
                    trust_score=float(getattr(matched, "trust_score", 0) or 0),
                    confidence=float(getattr(matched, "confidence", 0) or 0),
                    warnings=[f"candidate_slot_conflict:{','.join(conflict_keys)}"],
                    policy_key=matched.policy_key or "write_gate",
                    policy_version=matched.policy_version or str(policy.get("version", "default:v1")),
                )

            support = self._support_from_request(request, matched.memory_id)
            support.similarity = similarity
            support.evidence_pointer = {
                **(support.evidence_pointer or {}),
                "matched_by": "candidate_vector",
                "incoming_candidate_key": candidate_key,
            }
            await self.add_candidate_support(matched.memory_id, support, evaluate=False)
            await self._record_event(
                event_type=EventType.MEMORY_CANDIDATE_MERGED,
                memory_id=matched.memory_id,
                trace_id=request.trace_id,
                user_id=request.user_id,
                source_kind=request.source.kind,
                payload={
                    "match_type": "semantic",
                    "similarity": similarity,
                    "incoming_candidate_key": candidate_key,
                },
            )
            evaluation = await self.evaluate_candidate_promotion(matched.memory_id)
            current = await self._item_repo.get_by_memory_id(matched.memory_id)
            return MemoryWriteResponse(
                memory_id=matched.memory_id,
                status=evaluation.status,
                trust_score=float(getattr(current or matched, "trust_score", 0) or 0),
                confidence=float(getattr(current or matched, "confidence", 0) or 0),
                warnings=warnings,
                policy_key=matched.policy_key or "write_gate",
                policy_version=matched.policy_version or str(policy.get("version", "default:v1")),
            )

        # 6. Generate memory_id
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"

        # 7. Persist to MySQL
        expires_at = self._ttl_expiry(request.ttl_policy)
        item = MemoryItem(
            id=str(uuid7()),
            memory_id=memory_id,
            org_id=request.org_id,
            user_id=request.user_id,
            memory_type=request.memory_type.value,
            scope_json=request.scope.model_dump() if request.scope else None,
            content_summary=request.content.summary,
            content_json={
                "facts": request.content.facts,
                "preferences": request.content.preferences,
                "warnings": request.content.warnings,
                "risk_notes": request.content.risk_notes,
            },
            source_event_ids=[request.trace_id] if request.trace_id else None,
            evidence_pointers=request.evidence_pointers,
            version_parent_id=request.version_parent_id,
            candidate_key=candidate_key,
            canonical_claim=canonical_claim,
            support_count=0,
            negative_count=0,
            conflict_count=0,
            rag_evidence_count=0,
            agent_verifier_count=0,
            human_approved=False,
            promotion_score=None,
            last_supported_at=None,
            trust_score=trust_score,
            confidence=request.confidence,
            usage_policy="context_only",
            ttl_policy=request.ttl_policy,
            privacy_level=request.privacy_level.value if hasattr(request.privacy_level, 'value') else request.privacy_level,
            status=MemoryStatus.CANDIDATE.value,
            created_by=self._uuid_or_none(request.created_by),
            created_by_type=request.created_by_type,
            trace_id=request.trace_id,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            source_trace_id=request.source.trace_id or request.trace_id,
            source_task_id=request.source.task_id,
            index_status="pending",
            index_error=None,
            policy_key="write_gate",
            policy_version=str(policy.get("version", "default:v1")),
            last_accessed_at=datetime.now(timezone.utc),
            access_count=0,
        )
        await self._item_repo.create(item)

        # 8. Record event
        await self._record_event(
            event_type=EventType.MEMORY_CANDIDATE_CREATED,
            memory_id=memory_id,
            trace_id=request.trace_id,
            user_id=request.user_id,
            source_kind=request.source.kind,
            payload={
                "candidate_key": candidate_key,
                "canonical_claim": canonical_claim,
            },
        )

        # 8b. Write provenance dependency edges
        await self._record_write_dependencies(
            memory_id=memory_id,
            request=request,
        )

        support = self._support_from_request(request, memory_id)
        await self.add_candidate_support(memory_id, support, evaluate=False)
        await self._sync_candidate_vector(item)

        if warnings:
            await self._item_repo.update_status(memory_id, MemoryStatus.CONTESTED.value)
            return MemoryWriteResponse(
                memory_id=memory_id,
                status=MemoryStatus.CONTESTED,
                trust_score=trust_score,
                confidence=request.confidence,
                warnings=warnings,
                policy_key="write_gate",
                policy_version=str(policy.get("version", "default:v1")),
            )

        evaluation = await self.evaluate_candidate_promotion(memory_id)
        memory = await self._item_repo.get_by_memory_id(memory_id)
        warnings.extend(evaluation.blocked_reasons if evaluation.status == MemoryStatus.CONTESTED else [])
        if memory and getattr(memory, "index_status", None) == "failed" and getattr(memory, "index_error", None):
            warnings.append("qdrant_sync_failed")

        return MemoryWriteResponse(
            memory_id=memory_id,
            status=evaluation.status,
            trust_score=float(getattr(memory, "trust_score", trust_score) or trust_score),
            confidence=request.confidence,
            warnings=warnings,
            policy_key="write_gate",
            policy_version=str(policy.get("version", "default:v1")),
        )

    @staticmethod
    def _make_idempotency_key(request: MemoryWriteRequest) -> str:
        raw = "\n".join([
            request.org_id or "",
            request.trace_id or "",
            request.memory_type.value,
            request.content.summary or "",
        ])
        return f"memory:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _uuid_or_none(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return str(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            return None

    async def _reject(self, request: MemoryWriteRequest, reason: str) -> MemoryWriteResponse:
        await self._record_event(
            event_type=EventType.MEMORY_WRITE_REJECTED,
            trace_id=request.trace_id,
            user_id=request.user_id,
            source_kind=request.source.kind if request.source else None,
            payload={"reason": reason},
        )
        return MemoryWriteResponse(
            memory_id="",
            status=MemoryStatus.CANDIDATE,
            trust_score=0.0,
            confidence=request.confidence,
            warnings=[reason],
        )

    async def _isolate(self, request: MemoryWriteRequest, warnings: list[str]) -> MemoryWriteResponse:
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        idempotency_key = self._make_idempotency_key(request)
        item = MemoryItem(
            id=str(uuid7()),
            memory_id=memory_id,
            org_id=request.org_id,
            user_id=request.user_id,
            memory_type=request.memory_type.value,
            scope_json=request.scope.model_dump() if request.scope else None,
            content_summary=request.content.summary,
            content_json={
                "facts": request.content.facts,
                "preferences": request.content.preferences,
                "warnings": request.content.warnings,
            },
            source_event_ids=[request.trace_id] if request.trace_id else None,
            evidence_pointers=request.evidence_pointers,
            confidence=request.confidence,
            trust_score=request.confidence * 0.3,
            status=MemoryStatus.ISOLATED.value,
            created_by_type=request.created_by_type,
            trace_id=request.trace_id,
            ttl_policy=request.ttl_policy,
            expires_at=self._ttl_expiry(request.ttl_policy),
            idempotency_key=idempotency_key,
            source_trace_id=request.source.trace_id or request.trace_id if request.source else request.trace_id,
            source_task_id=request.source.task_id if request.source else None,
            index_status="pending",
            last_accessed_at=datetime.now(timezone.utc),
            access_count=0,
        )
        await self._item_repo.create(item)
        await self._record_event(
            event_type=EventType.MEMORY_CANDIDATE_CREATED,
            memory_id=memory_id,
            trace_id=request.trace_id,
        )
        return MemoryWriteResponse(
            memory_id=memory_id,
            status=MemoryStatus.ISOLATED,
            trust_score=request.confidence * 0.3,
            confidence=request.confidence,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Candidate Store / Promotion
    # ------------------------------------------------------------------

    async def list_candidates(
        self,
        *,
        status: str = "candidate",
        memory_type: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CandidateListItem]:
        items = await self._item_repo.list_by_org(
            status=status,
            memory_type=memory_type,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        return [self._to_candidate_item(item) for item in items]

    async def add_candidate_support(
        self,
        memory_id: str,
        support: CandidateSupportCreate,
        *,
        evaluate: bool = True,
    ) -> PromotionEvaluationResponse | None:
        memory = await self._item_repo.get_by_memory_id(memory_id)
        if not memory:
            raise ValueError(f"Memory {memory_id} not found")

        record = MemoryCandidateSupport(
            id=str(uuid7()),
            org_id=self._org_id,
            candidate_memory_id=memory_id,
            support_type=support.support_type,
            source_kind=support.source_kind,
            source_agent=support.source_agent,
            task_id=support.task_id,
            trace_id=support.trace_id,
            rag_space_id=support.rag_space_id,
            document_id=support.document_id,
            chunk_id=support.chunk_id,
            evidence_pointer=support.evidence_pointer,
            confidence=support.confidence,
            similarity=support.similarity,
            weight=support.weight,
        )
        await self._support_repo.create(record)

        stats = await self._support_repo.stats_for_candidate(memory_id)
        update_values = {
            "support_count": int(stats.get("support_count") or 0),
            "negative_count": int(stats.get("negative_count") or 0),
            "conflict_count": int(stats.get("conflict_count") or 0),
            "rag_evidence_count": int(stats.get("rag_evidence_count") or 0),
            "agent_verifier_count": int(stats.get("agent_verifier_count") or 0),
            "last_supported_at": datetime.now(timezone.utc),
        }
        if support.support_type == "human_approved":
            update_values["human_approved"] = True
        await self._item_repo.update_candidate_stats(memory_id, **update_values)

        await self._record_event(
            event_type=EventType.MEMORY_CANDIDATE_SUPPORTED,
            memory_id=memory_id,
            trace_id=support.trace_id,
            user_id=getattr(memory, "user_id", None),
            source_kind=support.source_kind,
            payload={
                "support_type": support.support_type,
                "source_agent": support.source_agent,
                "task_id": support.task_id,
                "rag_space_id": support.rag_space_id,
            },
        )

        if evaluate:
            return await self.evaluate_candidate_promotion(memory_id)
        return None

    async def approve_candidate(
        self,
        memory_id: str,
        *,
        reviewer_id: str,
        trace_id: str | None = None,
    ) -> PromotionEvaluationResponse:
        await self.add_candidate_support(
            memory_id,
            CandidateSupportCreate(
                support_type="human_approved",
                source_kind="human_review",
                source_agent=reviewer_id,
                trace_id=trace_id,
                confidence=1.0,
                weight=1.0,
            ),
            evaluate=False,
        )
        return await self.evaluate_candidate_promotion(memory_id)

    async def reject_candidate(
        self,
        memory_id: str,
        *,
        reviewer_id: str,
        trace_id: str | None = None,
        reason: str | None = None,
    ) -> PromotionEvaluationResponse:
        await self.add_candidate_support(
            memory_id,
            CandidateSupportCreate(
                support_type="negative",
                source_kind="human_review",
                source_agent=reviewer_id,
                trace_id=trace_id,
                evidence_pointer={"reason": reason} if reason else None,
                confidence=1.0,
            ),
            evaluate=False,
        )
        await self._item_repo.update_status(memory_id, MemoryStatus.DISABLED.value)
        await self._record_event(
            event_type=EventType.MEMORY_CANDIDATE_REJECTED,
            memory_id=memory_id,
            trace_id=trace_id,
            payload={"reviewer_id": reviewer_id, "reason": reason},
        )
        return PromotionEvaluationResponse(
            memory_id=memory_id,
            status=MemoryStatus.DISABLED,
            promotion_score=0.0,
            promoted=False,
            reason="rejected",
            blocked_reasons=["human_rejected"],
        )

    async def isolate_candidate(
        self,
        memory_id: str,
        *,
        trace_id: str | None = None,
        reason: str | None = None,
    ) -> PromotionEvaluationResponse:
        await self._item_repo.update_status(memory_id, MemoryStatus.ISOLATED.value)
        await self._delete_candidate_vector(memory_id)
        return PromotionEvaluationResponse(
            memory_id=memory_id,
            status=MemoryStatus.ISOLATED,
            promotion_score=0.0,
            promoted=False,
            reason=reason or "isolated",
            blocked_reasons=["isolated"],
        )

    async def contest_candidate(
        self,
        memory_id: str,
        *,
        trace_id: str | None = None,
        reason: str | None = None,
    ) -> PromotionEvaluationResponse:
        await self.add_candidate_support(
            memory_id,
            CandidateSupportCreate(
                support_type="conflict",
                source_kind="governance",
                trace_id=trace_id,
                evidence_pointer={"reason": reason} if reason else None,
                confidence=1.0,
            ),
            evaluate=False,
        )
        await self._item_repo.update_status(memory_id, MemoryStatus.CONTESTED.value)
        return PromotionEvaluationResponse(
            memory_id=memory_id,
            status=MemoryStatus.CONTESTED,
            promotion_score=0.0,
            promoted=False,
            reason=reason or "contested",
            blocked_reasons=["unresolved_conflict"],
        )

    async def evaluate_candidate_promotion(self, memory_id: str) -> PromotionEvaluationResponse:
        memory = await self._item_repo.get_by_memory_id(memory_id)
        if not memory:
            raise ValueError(f"Memory {memory_id} not found")

        if memory.status == MemoryStatus.ACTIVE.value:
            score = float(getattr(memory, "promotion_score", 0) or 0)
            return PromotionEvaluationResponse(
                memory_id=memory_id,
                status=MemoryStatus.ACTIVE,
                promotion_score=score,
                promoted=False,
                reason="already_active",
            )
        if memory.status != MemoryStatus.CANDIDATE.value:
            score = float(getattr(memory, "promotion_score", 0) or 0)
            return PromotionEvaluationResponse(
                memory_id=memory_id,
                status=MemoryStatus(memory.status),
                promotion_score=score,
                promoted=False,
                blocked_reasons=[f"status_{memory.status}"],
            )

        stats = await self._support_repo.stats_for_candidate(memory_id)
        support_count = int(stats.get("support_count") or getattr(memory, "support_count", 0) or 0)
        negative_count = int(stats.get("negative_count") or getattr(memory, "negative_count", 0) or 0)
        conflict_count = int(stats.get("conflict_count") or getattr(memory, "conflict_count", 0) or 0)
        rag_evidence_count = int(stats.get("rag_evidence_count") or getattr(memory, "rag_evidence_count", 0) or 0)
        agent_verifier_count = int(stats.get("agent_verifier_count") or getattr(memory, "agent_verifier_count", 0) or 0)
        unique_task_count = int(stats.get("unique_task_count") or 0)
        avg_confidence = float(stats.get("avg_confidence") or getattr(memory, "confidence", 0) or 0)
        human_approved = bool(getattr(memory, "human_approved", False))

        promotion_score = (
            (1.0 if human_approved else 0.0)
            + rag_evidence_count * 0.8
            + agent_verifier_count * 0.5
            + unique_task_count * 0.3
            + avg_confidence * 0.5
            - conflict_count * 0.8
            - negative_count * 0.6
        )

        blocked: list[str] = []
        if conflict_count > 0:
            blocked.append("unresolved_conflict")
        if negative_count > 0:
            blocked.append("negative_support")
        if float(getattr(memory, "confidence", 0) or 0) < 0.4:
            blocked.append("low_confidence")
        if not getattr(memory, "scope_json", None):
            blocked.append("missing_scope")

        await self._item_repo.update_candidate_stats(
            memory_id,
            support_count=support_count,
            negative_count=negative_count,
            conflict_count=conflict_count,
            rag_evidence_count=rag_evidence_count,
            agent_verifier_count=agent_verifier_count,
            promotion_score=promotion_score,
        )

        reason: str | None = None
        if not blocked:
            if human_approved:
                reason = "human_approved"
            elif rag_evidence_count >= 1 and avg_confidence >= 0.7:
                reason = "rag_evidence"
            elif unique_task_count >= 5:
                reason = "repeated_tasks"
            elif agent_verifier_count >= 2 and avg_confidence >= 0.75:
                reason = "agent_verification"
            elif promotion_score >= 1.5:
                reason = "promotion_score"

        if reason:
            warnings = await self.promote_candidate(memory_id, reason=reason, promotion_score=promotion_score)
            return PromotionEvaluationResponse(
                memory_id=memory_id,
                status=MemoryStatus.ACTIVE,
                promotion_score=promotion_score,
                promoted=True,
                reason=reason,
                blocked_reasons=warnings,
            )

        await self._record_event(
            event_type=EventType.MEMORY_EVALUATION_COMPLETED,
            memory_id=memory_id,
            trace_id=getattr(memory, "trace_id", None),
            payload={
                "promotion_score": promotion_score,
                "blocked_reasons": blocked,
            },
        )
        return PromotionEvaluationResponse(
            memory_id=memory_id,
            status=MemoryStatus.CANDIDATE,
            promotion_score=promotion_score,
            promoted=False,
            blocked_reasons=blocked,
        )

    async def evaluate_batch_candidates(self, *, limit: int = 100) -> list[PromotionEvaluationResponse]:
        candidates = await self._item_repo.list_promotion_candidates(limit=limit)
        results: list[PromotionEvaluationResponse] = []
        for candidate in candidates:
            results.append(await self.evaluate_candidate_promotion(candidate.memory_id))
        return results

    async def promote_candidate(
        self,
        memory_id: str,
        *,
        reason: str,
        promotion_score: float | None = None,
    ) -> list[str]:
        memory = await self._item_repo.get_by_memory_id(memory_id)
        if not memory:
            raise ValueError(f"Memory {memory_id} not found")

        confidence = float(getattr(memory, "confidence", 0) or 0)
        trust_score = min(1.0, max(confidence, float(promotion_score or 0) / 2.0))
        await self._item_repo.update_candidate_stats(
            memory_id,
            promotion_score=promotion_score,
            trust_score=trust_score,
        )
        await self._item_repo.update_status(memory_id, MemoryStatus.ACTIVE.value)

        warnings: list[str] = []
        try:
            await self._upsert_active_vector(memory, trust_score=trust_score)
            await self._item_repo.update_index_status(memory_id, "success")
        except Exception as exc:
            error = str(exc)
            await self._item_repo.update_index_status(memory_id, "failed", error)
            warnings.append("qdrant_sync_failed")

        await self._delete_candidate_vector(memory_id)
        await self._record_event(
            event_type=EventType.MEMORY_PROMOTED_TO_ACTIVE,
            memory_id=memory_id,
            trace_id=getattr(memory, "trace_id", None),
            user_id=getattr(memory, "user_id", None),
            payload={
                "reason": reason,
                "trust_score": trust_score,
                "promotion_score": promotion_score,
            },
        )
        return warnings

    def _support_from_request(
        self,
        request: MemoryWriteRequest,
        memory_id: str,
    ) -> CandidateSupportCreate:
        evidence = dict(request.evidence_pointers or {})
        scope = request.scope or MemoryScope()
        return CandidateSupportCreate(
            support_type=self._infer_support_type(request),
            source_kind=request.source.kind,
            source_agent=request.source.agent_id or request.created_by_type,
            task_id=request.source.task_id or scope.task_id,
            trace_id=request.source.trace_id or request.trace_id,
            rag_space_id=scope.rag_space_id or evidence.get("rag_space_id"),
            document_id=evidence.get("document_id"),
            chunk_id=evidence.get("chunk_id"),
            evidence_pointer=evidence or None,
            confidence=request.confidence,
            weight=min(1.0, max(0.1, request.confidence)),
        )

    @staticmethod
    def _infer_support_type(request: MemoryWriteRequest) -> str:
        if request.source.kind == "rag" or request.memory_type == MemoryType.RAG_USAGE_MEMORY:
            return "rag_evidence"
        if request.source.kind == "human_review":
            return "human_approved"
        if request.source.kind in {"agent_message", "tool"}:
            return "agent_verifier"
        return "support"

    @staticmethod
    def _canonicalize_candidate(request: MemoryWriteRequest) -> tuple[dict, str]:
        scope = request.scope.model_dump(exclude_none=True) if request.scope else {}
        summary = " ".join(request.content.summary.lower().split())
        facts = [" ".join(f.lower().split()) for f in request.content.facts[:5]]
        canonical = {
            "memory_type": request.memory_type.value,
            "scope": scope,
            "summary": summary[:240],
            "facts": facts,
        }
        for key in ("product_line", "rag_space_id", "task_id", "role"):
            if key in scope:
                canonical[key] = scope[key]
        candidate_key_parts = [
            request.memory_type.value,
            str(request.user_id or "org"),
            str(scope.get("product_line") or ""),
            str(scope.get("rag_space_id") or ""),
            str(scope.get("task_id") or ""),
            summary[:160],
        ]
        candidate_key = ":".join(
            MemoryService._normalize_key_part(part)
            for part in candidate_key_parts
            if str(part).strip()
        )[:256]
        return canonical, candidate_key

    async def _match_candidate_semantic(
        self,
        request: MemoryWriteRequest,
    ) -> tuple[MemoryItem, float, bool, list[str]] | None:
        if not self._candidate_vector:
            return None

        try:
            vector_results = await self._candidate_vector.search(
                query=request.content.summary,
                org_id=request.org_id,
                top_k=8,
                status=MemoryStatus.CANDIDATE.value,
                user_id=request.user_id,
                memory_types=[request.memory_type.value],
            )
        except Exception:
            logger.debug("Candidate semantic match skipped", exc_info=True)
            return None

        incoming_scope = request.scope.model_dump(exclude_none=True) if request.scope else {}
        for result in vector_results:
            score = float(result.get("score") or 0.0)
            if score < 0.82:
                continue
            memory_id = str(result.get("memory_id") or "").strip()
            if not memory_id:
                continue
            item = await self._item_repo.get_by_memory_id(memory_id)
            if not item or item.status != MemoryStatus.CANDIDATE.value:
                continue
            if item.memory_type != request.memory_type.value:
                continue

            existing_scope = dict(getattr(item, "scope_json", None) or {})
            conflicts = self._critical_slot_conflicts(incoming_scope, existing_scope)
            if conflicts:
                return item, score, True, conflicts
            if self._same_candidate_slots(incoming_scope, existing_scope):
                return item, score, False, []
        return None

    @staticmethod
    def _same_candidate_slots(incoming_scope: dict, existing_scope: dict) -> bool:
        for key in ("task_id", "product_line", "rag_space_id", "role"):
            incoming = incoming_scope.get(key)
            existing = existing_scope.get(key)
            if bool(incoming) != bool(existing):
                return False
            if incoming and existing and str(incoming) != str(existing):
                return False
        return True

    @staticmethod
    def _critical_slot_conflicts(incoming_scope: dict, existing_scope: dict) -> list[str]:
        conflicts: list[str] = []
        for key in ("task_id", "product_line", "rag_space_id", "role"):
            incoming = incoming_scope.get(key)
            existing = existing_scope.get(key)
            if incoming and existing and str(incoming) != str(existing):
                conflicts.append(key)
        return conflicts

    @staticmethod
    def _normalize_key_part(value: object) -> str:
        import re
        normalized = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+", "_", str(value).lower())
        return normalized.strip("_") or "none"

    async def _sync_candidate_vector(self, memory: MemoryItem) -> None:
        if not self._candidate_vector:
            return
        scope = MemoryScope.model_validate(memory.scope_json or {})
        try:
            await self._candidate_vector.upsert_memory(
                memory_id=memory.memory_id,
                org_id=self._org_id,
                user_id=str(memory.user_id or ""),
                memory_type=memory.memory_type,
                status=MemoryStatus.CANDIDATE.value,
                summary=memory.content_summary or "",
                trust_score=float(memory.trust_score or 0),
                confidence=float(memory.confidence or 0),
                expires_at=memory.expires_at.isoformat() if memory.expires_at else "",
                product_line=scope.product_line or "",
                rag_space_id=scope.rag_space_id or "",
                task_id=scope.task_id or "",
            )
        except Exception:
            logger.debug("Candidate vector upsert skipped", exc_info=True)

    async def _upsert_active_vector(self, memory: MemoryItem, *, trust_score: float) -> None:
        if not self._vector:
            return
        scope = MemoryScope.model_validate(memory.scope_json or {})
        await self._vector.upsert_memory(
            memory_id=memory.memory_id,
            org_id=self._org_id,
            user_id=str(memory.user_id or ""),
            memory_type=memory.memory_type,
            status=MemoryStatus.ACTIVE.value,
            summary=memory.content_summary or "",
            trust_score=trust_score,
            confidence=float(memory.confidence or 0),
            expires_at=memory.expires_at.isoformat() if memory.expires_at else "",
            product_line=scope.product_line or "",
            rag_space_id=scope.rag_space_id or "",
            task_id=scope.task_id or "",
        )

    async def _delete_candidate_vector(self, memory_id: str) -> None:
        if not self._candidate_vector:
            return
        try:
            await self._candidate_vector.delete_memory(memory_id)
        except Exception:
            logger.debug("Candidate vector delete skipped", exc_info=True)

    @staticmethod
    def _to_candidate_item(item: MemoryItem) -> CandidateListItem:
        return CandidateListItem(
            memory_id=item.memory_id,
            memory_type=item.memory_type,
            status=item.status,
            summary=item.content_summary or "",
            candidate_key=getattr(item, "candidate_key", None),
            canonical_claim=getattr(item, "canonical_claim", None),
            support_count=int(getattr(item, "support_count", 0) or 0),
            negative_count=int(getattr(item, "negative_count", 0) or 0),
            conflict_count=int(getattr(item, "conflict_count", 0) or 0),
            rag_evidence_count=int(getattr(item, "rag_evidence_count", 0) or 0),
            agent_verifier_count=int(getattr(item, "agent_verifier_count", 0) or 0),
            human_approved=bool(getattr(item, "human_approved", False)),
            promotion_score=float(item.promotion_score) if getattr(item, "promotion_score", None) is not None else None,
            confidence=float(item.confidence) if getattr(item, "confidence", None) is not None else None,
            trust_score=float(item.trust_score) if getattr(item, "trust_score", None) is not None else None,
            created_at=getattr(item, "created_at", None),
            updated_at=getattr(item, "updated_at", None),
            last_supported_at=getattr(item, "last_supported_at", None),
        )

    # ------------------------------------------------------------------
    # Dependency Edge Writing
    # ------------------------------------------------------------------

    async def _record_write_dependencies(
        self,
        *,
        memory_id: str,
        request: MemoryWriteRequest,
    ) -> None:
        """Write provenance dependency edges from structured context, not model judgment."""
        now_iso = datetime.now(timezone.utc).isoformat()
        base_metadata = {
            "edge_group": "provenance",
            "relation_source": "memory_write",
            "trace_id": request.trace_id,
            "created_by_type": request.created_by_type,
            "observed_count": 1,
            "last_observed_at": now_iso,
        }

        # 1. version_parent_id -> version_of
        if request.version_parent_id:
            await self._dep_repo.upsert_edge(
                source_memory_id=memory_id,
                target_memory_id=request.version_parent_id,
                edge_type=EdgeType.VERSION_OF.value,
                strength=1.0,
                metadata_json={
                    **base_metadata,
                    "reason": "new memory version replaces parent memory",
                },
            )

        # 2. evidence_pointers.memory_ids -> cited_as_evidence
        for target_id in self._extract_evidence_memory_ids(request.evidence_pointers):
            await self._dep_repo.upsert_edge(
                source_memory_id=memory_id,
                target_memory_id=target_id,
                edge_type=EdgeType.CITED_AS_EVIDENCE.value,
                strength=0.9,
                metadata_json={
                    **base_metadata,
                    "reason": "target memory cited as evidence",
                },
            )

        # 3. explicit dependency_edges from request
        for dep in request.dependency_edges:
            if dep.target_memory_id == memory_id:
                continue

            await self._dep_repo.upsert_edge(
                source_memory_id=memory_id,
                target_memory_id=dep.target_memory_id,
                edge_type=dep.edge_type.value,
                strength=dep.strength,
                metadata_json={
                    **base_metadata,
                    "reason": dep.reason,
                    "extra": dep.metadata,
                },
            )

    @staticmethod
    def _extract_evidence_memory_ids(evidence_pointers: dict | None) -> list[str]:
        """Extract memory IDs from evidence_pointers in various formats."""
        if not evidence_pointers:
            return []

        keys = ["memory_ids", "memories", "used_memory_ids", "cited_memory_ids"]
        ids: list[str] = []
        for key in keys:
            value = evidence_pointers.get(key)
            if isinstance(value, list):
                ids.extend(str(v) for v in value if v)

        return sorted(set(ids))

    # ------------------------------------------------------------------
    # Controlled Retrieval
    # ------------------------------------------------------------------

    async def search(self, request: MemorySearchRequest) -> MemorySearchResponse:
        """Controlled retrieval: MySQL pre-filter -> Qdrant semantic recall -> MySQL verify -> rerank."""

        memory_types = (
            [mt.value for mt in request.scope_filter.memory_type]
            if request.scope_filter and request.scope_filter.memory_type
            else None
        )

        # 1. Load retrieval policy
        policy = await self._resolve_policy("retrieval")
        max_top_k = int(policy.get("max_top_k", 10))
        effective_top_k = min(request.top_k, max_top_k)

        # 2. MySQL: get eligible memories (tenant + scope + status + TTL)
        eligible = await self._item_repo.list_retrievable_by_scope(
            memory_types=memory_types,
            user_id=request.user_id,
            task_id=request.scope_filter.task_id if request.scope_filter else None,
            product_line=request.scope_filter.product_line if request.scope_filter else None,
            rag_space_id=request.scope_filter.rag_space_id if request.scope_filter else None,
            limit=100,
        )

        if not eligible:
            return MemorySearchResponse(
                memory_context=MemoryContext(),
                items=[],
                policy_version="default:v1",
                trace_id=request.trace_id,
            )

        # 2. Qdrant semantic recall — over-fetch then MySQL verify
        if self._vector is None:
            raise MemoryVectorServiceError("vector service is required for shared memory search")

        items: list[MemorySearchItem] = []
        if self._vector:
            semantic_top_k = min(effective_top_k * 10, 100)
            try:
                vector_results = await self._vector.search(
                    query=request.query,
                    org_id=request.org_id,
                    top_k=semantic_top_k,
                    user_id=request.user_id,
                    memory_types=memory_types,
                    product_line=request.scope_filter.product_line if request.scope_filter else None,
                    rag_space_id=request.scope_filter.rag_space_id if request.scope_filter else None,
                    task_id=request.scope_filter.task_id if request.scope_filter else None,
                )
                # Cross-reference with eligible memories from MySQL
                eligible_ids = {m.memory_id for m in eligible}
                for vr in vector_results:
                    if vr.get("memory_id") in eligible_ids:
                        match = next(
                            (m for m in eligible if m.memory_id == vr.get("memory_id")),
                            None,
                        )
                        if match:
                            items.append(self._to_search_item(match, vr.get("score", 0.0)))
                # Rerank: vector_score * 0.55 + trust_score * 0.30 + confidence * 0.15
                items.sort(
                    key=lambda x: (x.score or 0) * 0.55
                    + (x.trust_score or 0) * 0.30
                    + (x.confidence or 0) * 0.15,
                    reverse=True,
                )
                items = items[:effective_top_k]
            except MemoryVectorServiceError:
                logger.debug("Memory vector search failed; falling back to MySQL text search", exc_info=True)
                items = self._fallback_search(eligible, request.query, request.top_k)
                for item in items:
                    item.warnings.append("vector_search_failed_fallback")
        else:
            items = self._fallback_search(eligible, request.query, request.top_k)

        # 2a. Existing conflict edges let us avoid repeated LLM conflict checks.
        conflict_info: dict = {}
        if items and len(items) >= 2:
            existing_relations = await self._existing_conflict_relations(items)
            if existing_relations:
                conflict_info = {
                    "contested_count": len({
                        relation["source_memory_id"]
                        for relation in existing_relations
                    } | {
                        relation["target_memory_id"]
                        for relation in existing_relations
                    }),
                    "relations": existing_relations,
                }
                self._mark_conflicted_items(items, {
                    relation["source_memory_id"]
                    for relation in existing_relations
                } | {
                    relation["target_memory_id"]
                    for relation in existing_relations
                })

        # 2b. Run LLM conflict detection only when no known conflict edge exists.
        if items and len(items) >= 2 and not conflict_info:
            try:
                from app.services.memory_conflict_service import ConflictDetectionService
                detector = ConflictDetectionService(
                    org_id=self._org_id,
                    user_id=request.user_id,
                    trace_id=request.trace_id,
                )
                item_dicts = [
                    {
                        "memory_id": item.memory_id,
                        "summary": item.summary,
                        "score": item.score,
                        "memory_type": item.memory_type,
                    }
                    for item in items
                ]
                detection = await detector.detect(item_dicts)

                if detection.contested_ids:
                    for pair in detection.pairs:
                        if pair.relation != ConflictRelation.CONTRADICTS:
                            continue

                        strength = pair.confidence or min(pair.source_score, pair.target_score) or 1.0
                        now_iso = datetime.now(timezone.utc).isoformat()
                        base_meta = {
                            "edge_group": "semantic",
                            "relation_source": "conflict_detection",
                            "judge": "llm",
                            "trace_id": request.trace_id,
                            "query": request.query,
                            "reason": pair.reason,
                            "observed_count": 1,
                            "last_observed_at": now_iso,
                        }
                        # Bidirectional upsert — conflicts_with is symmetric
                        await self._dep_repo.upsert_edge(
                            source_memory_id=pair.source_memory_id,
                            target_memory_id=pair.target_memory_id,
                            edge_type=EdgeType.CONFLICTS_WITH.value,
                            strength=strength,
                            metadata_json=base_meta,
                        )
                        await self._dep_repo.upsert_edge(
                            source_memory_id=pair.target_memory_id,
                            target_memory_id=pair.source_memory_id,
                            edge_type=EdgeType.CONFLICTS_WITH.value,
                            strength=strength,
                            metadata_json=base_meta,
                        )
                        await self._record_event(
                            event_type=EventType.MEMORY_CONFLICT_DETECTED,
                            memory_id=pair.source_memory_id,
                            trace_id=request.trace_id,
                            payload={
                                "conflict_with": pair.target_memory_id,
                                "relation": pair.relation.value,
                            },
                        )

                # Build conflict_info with relation details (all pairs for transparency)
                relations_list = [
                    {
                        "source_memory_id": p.source_memory_id,
                        "target_memory_id": p.target_memory_id,
                        "relation": EdgeType.CONFLICTS_WITH.value,
                        "strength": p.confidence or min(p.source_score, p.target_score),
                        "source": "llm_detection",
                    }
                    for p in detection.pairs
                    if p.relation == ConflictRelation.CONTRADICTS
                ]
                conflict_info = {
                    "contested_count": len(detection.contested_ids),
                    "relations": relations_list,
                }

                # Add warnings to items that have conflict edges
                self._mark_conflicted_items(items, set(detection.contested_ids))
            except Exception:
                logger.debug("Conflict detection skipped", exc_info=True)

        # 3. Record retrieval event
        await self._record_event(
            event_type=EventType.MEMORY_RETRIEVAL_COMPLETED,
            user_id=request.user_id,
            payload={
                "query": request.query,
                "top_k": request.top_k,
                "result_count": len(items),
            },
        )

        return MemorySearchResponse(
            memory_context=MemoryContext(items=items),
            items=items,
            policy_version=f"retrieval:v{policy.get('version', '1')}",
            trace_id=request.trace_id,
            conflict_info=conflict_info if conflict_info else None,
        )

    async def _existing_conflict_relations(self, items: list[MemorySearchItem]) -> list[dict]:
        item_ids = {item.memory_id for item in items}
        relations: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for item in items:
            edges = await self._dep_repo.list_by_edge_type(
                item.memory_id,
                [EdgeType.CONFLICTS_WITH.value],
                direction="source",
            )
            for edge in edges:
                if edge.target_memory_id not in item_ids:
                    continue
                key = (edge.source_memory_id, edge.target_memory_id)
                if key in seen:
                    continue
                seen.add(key)
                relations.append({
                    "source_memory_id": edge.source_memory_id,
                    "target_memory_id": edge.target_memory_id,
                    "relation": EdgeType.CONFLICTS_WITH.value,
                    "strength": float(edge.strength) if edge.strength is not None else None,
                    "source": "existing_edge",
                })

        return relations

    @staticmethod
    def _mark_conflicted_items(items: list[MemorySearchItem], conflicted_ids: set[str]) -> None:
        for item in items:
            if item.memory_id in conflicted_ids and "has_conflict_edges" not in item.warnings:
                item.warnings.append("has_conflict_edges")

    # ------------------------------------------------------------------
    # Dependency Edges
    # ------------------------------------------------------------------

    async def record_dependency(
        self,
        source_memory_id: str,
        target_memory_id: str,
        edge_type: EdgeType,
        strength: float = 0.5,
        source_event_id: str | None = None,
        target_event_id: str | None = None,
    ) -> MemoryDependencyEdge:
        return await self._dep_repo.upsert_edge(
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            edge_type=edge_type.value,
            strength=strength,
            source_event_id=source_event_id,
            target_event_id=target_event_id,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def record_event(self, payload: MemoryEventPayload) -> MemoryEvent:
        event = MemoryEvent(
            id=str(uuid7()),
            event_id=payload.event_id,
            org_id=payload.org_id,
            user_id=payload.user_id,
            event_type=payload.event_type.value,
            source_kind=payload.source_kind,
            agent_id=payload.agent_id,
            role=payload.role,
            task_id=payload.task_id,
            trace_id=payload.trace_id,
            memory_id=payload.memory_id,
            payload_ref=payload.payload_ref,
            payload_json=payload.payload_json,
            risk_tags=payload.risk_tags,
            parent_event_ids=payload.parent_event_ids,
        )
        return await self._event_repo.create(event)

    async def get_events(
        self,
        memory_id: str | None = None,
        event_type: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEvent]:
        return await self._event_repo.list_by_org(
            memory_id=memory_id,
            event_type=event_type,
            trace_id=trace_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    async def update_status(self, memory_id: str, status: MemoryStatus) -> None:
        await self._item_repo.update_status(memory_id, status.value)
        if self._vector and status in (MemoryStatus.DELETED, MemoryStatus.DISABLED):
            try:
                await self._vector.delete_memory(memory_id)
            except Exception:
                pass

    async def batch_update_status(self, memory_ids: list[str], status: MemoryStatus) -> int:
        return await self._item_repo.batch_update_status(memory_ids, status.value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _record_event(
        self,
        event_type: EventType,
        memory_id: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        source_kind: str | None = None,
        payload: dict | None = None,
    ) -> None:
        event = MemoryEvent(
            id=str(uuid7()),
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            org_id=self._org_id,
            user_id=user_id,
            event_type=event_type.value,
            source_kind=source_kind,
            trace_id=trace_id,
            memory_id=memory_id,
            payload_json=payload,
        )
        await self._event_repo.create(event)

    @staticmethod
    def _check_sensitive(summary: str) -> str | None:
        import re
        if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', summary):
            return "email_detected"
        if re.search(r'\b1[3-9]\d{9}\b', summary):
            return "phone_detected"
        return None

    @staticmethod
    def _ttl_expiry(ttl_policy: str) -> datetime | None:
        if ttl_policy == "never":
            return None
        if ttl_policy == "task_only":
            return datetime.now(timezone.utc) + timedelta(hours=12)
        days = int(ttl_policy.replace("d", "")) if ttl_policy.endswith("d") else 90
        return datetime.now(timezone.utc) + timedelta(days=days)

    def _to_search_item(self, item: MemoryItem, score: float) -> MemorySearchItem:
        return MemorySearchItem(
            memory_id=item.memory_id,
            memory_type=item.memory_type,
            summary=item.content_summary or "",
            score=score,
            confidence=float(item.confidence) if item.confidence else None,
            trust_score=float(item.trust_score) if item.trust_score else None,
            source={
                "task_id": item.scope_json.get("task_id") if item.scope_json else None,
                "trace_id": item.trace_id,
            },
            usage_policy=item.usage_policy,
        )

    def _fallback_search(
        self, eligible: list[MemoryItem], query: str, top_k: int
    ) -> list[MemorySearchItem]:
        query_tokens = set(query.lower().split())
        scored = []
        for mem in eligible:
            summary = (mem.content_summary or "").lower()
            if not summary:
                continue
            mem_tokens = set(summary.split())
            if not query_tokens:
                continue
            jaccard = len(query_tokens & mem_tokens) / len(query_tokens | mem_tokens)
            confidence = float(mem.confidence) if mem.confidence else 0.5
            score = jaccard * 0.5 + confidence * 0.5
            scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._to_search_item(mem, score) for score, mem in scored[:top_k]]
