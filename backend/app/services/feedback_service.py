from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from agent.llm.langfuse_tracer import LangfuseTracer
from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError
from app.core.ids import uuid7
from app.models.chat import ChatMessage, ChatSession
from app.models.meeting import MeetingMessage, MeetingRoomMember
from app.repositories.memory_repo import MemoryItemRepository, MemorySyncOutboxRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.result_repo import ResultRepository
from app.schemas.memory import MemoryContent, MemoryScope, MemorySource, MemoryType, MemoryWriteRequest
from app.services.memory_vector_service import CANDIDATE_MEMORY_COLLECTION
from app.services.base import TenantAwareService
from worker.tasks.langfuse_sync_task import sync_langfuse_score


class FeedbackService(TenantAwareService):
    def __init__(self, session, org_id: str):
        super().__init__(session, org_id)
        self._repo = FeedbackRepository(session)
        self._result_repo = ResultRepository(session)

    async def submit(self, result_id: str, actor_id: str, payload: dict):
        result = await self._result_repo.get_by_id(self._org_id, result_id)
        if not result:
            raise NotFoundError("result not found")
        now = utcnow()
        feedback = await self._repo.save(
            {
                "id": str(uuid7()),
                "org_id": self._org_id,
                "result_id": result_id,
                "actor_id": actor_id,
                "feedback_type": payload["feedback_type"],
                "rating": payload.get("rating"),
                "category": payload.get("category"),
                "comment": payload.get("comment"),
                "severity": payload.get("severity"),
                "status": "pending",
                "source_type": payload.get("source_type", "result"),
                "task_id": payload.get("task_id") or (str(result.task_id) if result.task_id else None),
                "created_at": now,
                "updated_at": now,
            }
        )
        trace_id = self._extract_trace_id(result)
        score_event = LangfuseTracer().score(
            trace_id=trace_id,
            name="user_feedback",
            value=self._score_value(payload),
            comment=payload.get("comment"),
            metadata={
                "result_id": result_id,
                "actor_id": actor_id,
                "feedback_type": payload["feedback_type"],
                "rating": payload.get("rating"),
                "category": payload.get("category"),
            },
            scored_at=now.isoformat(),
        )
        result.reasoning_chain = self._append_score_event(result.reasoning_chain, score_event, actor_id)
        await self._session.flush()
        self._queue_score_sync(score_event)
        return feedback

    async def list_feedbacks(self, page: int, size: int, result_id: str | None = None, feedback_type: str | None = None, status: str | None = None, severity: str | None = None, source_type: str | None = None, category: str | None = None, assigned_to: str | None = None):
        return await self._repo.list_feedbacks(self._org_id, page, size, result_id, feedback_type, status, severity, source_type, category, assigned_to)

    async def get_detail(self, feedback_id: str):
        fb = await self._repo.get_by_id(feedback_id)
        if not fb or fb.org_id != self._org_id:
            raise NotFoundError("feedback not found")
        return fb

    async def update_status(self, feedback_id: str, status: str, resolution: str | None = None):
        fb = await self._repo.get_by_id(feedback_id)
        if not fb or fb.org_id != self._org_id:
            raise NotFoundError("feedback not found")
        fb.status = status
        if resolution:
            fb.resolution = resolution
        if status == "resolved":
            fb.resolved_at = utcnow()
        await self._session.flush()
        return fb

    async def delete(self, feedback_id: str) -> None:
        fb = await self._repo.get_by_id(feedback_id)
        if not fb or fb.org_id != self._org_id:
            raise NotFoundError("feedback not found")
        await self._repo.delete(fb)

    async def summary(self):
        return await self._repo.summary(self._org_id)

    async def submit_message_feedback(self, target_type: str, target_id: str, actor_id: str, payload: dict):
        normalized_type = target_type.strip().lower()
        target = await self._ensure_feedback_target(normalized_type, target_id, actor_id)
        now = utcnow()
        feedback = await self._repo.save_message_feedback(
            {
                "id": str(uuid7()),
                "org_id": self._org_id,
                "target_type": normalized_type,
                "target_id": target_id,
                "actor_id": actor_id,
                "feedback_type": payload["feedback_type"],
                "rating": payload.get("rating"),
                "category": payload.get("category"),
                "comment": payload.get("comment"),
                "metadata_json": self._build_message_feedback_metadata(
                    target_type=normalized_type,
                    target=target,
                    captured_at=now,
                ),
                "created_at": now,
                "updated_at": now,
            }
        )
        # Feedback is also a knowledge-governance signal.  Keep this best effort:
        # a temporary graph/index outage must not make a user's reaction fail.
        knowledge_update = await self._apply_message_feedback_knowledge_update(
            target_type=normalized_type,
            target_id=target_id,
            actor_id=actor_id,
            feedback=feedback,
            feedback_type=str(payload.get("feedback_type") or "").strip().lower(),
            captured_metadata=dict(getattr(feedback, "metadata_json", None) or {}),
        )
        metadata = dict(getattr(feedback, "metadata_json", None) or {})
        metadata["knowledge_update"] = knowledge_update
        feedback.metadata_json = metadata
        flush = getattr(self._session, "flush", None)
        if callable(flush):
            await flush()
        return feedback

    async def _apply_message_feedback_knowledge_update(
        self,
        *,
        target_type: str,
        target_id: str,
        actor_id: str,
        feedback,
        feedback_type: str,
        captured_metadata: dict,
    ) -> dict:
        """Turn a positive answer signal into a candidate, never active memory.

        Negative feedback deliberately leaves active memory untouched and records
        a review signal.  This preserves a human decision point for conflict and
        rollback governance instead of silently deleting evidence.
        """
        base = {
            "feedback_id": str(getattr(feedback, "id", "") or ""),
            "target_type": target_type,
            "target_id": target_id,
            "feedback_type": feedback_type,
            "candidate_memory_id": None,
            "index_status": "unchanged",
            "needs_human_review": False,
        }
        if feedback_type == "down":
            return {
                **base,
                "status": "needs_human_review",
                "needs_human_review": True,
                "reason": "negative_feedback_does_not_mutate_active_memory",
            }
        if feedback_type != "up":
            return {**base, "status": "ignored_feedback_type"}

        target = await self._ensure_feedback_target(target_type, target_id, actor_id)
        if not self._is_agent_answer_target(target_type, target):
            return {**base, "status": "skipped_not_agent_answer"}

        answer = str(getattr(target, "content", "") or "").strip()
        if len(answer) < 10:
            return {**base, "status": "skipped_empty_answer"}

        trust = captured_metadata.get("trust_protocol")
        trust = trust if isinstance(trust, dict) else {}
        trust_status = str(
            trust.get("status")
            or captured_metadata.get("manager_status")
            or captured_metadata.get("status")
            or "unknown"
        ).strip().lower()
        if trust_status in {"blocked", "failed", "unavailable"}:
            return {
                **base,
                "status": "needs_human_review",
                "needs_human_review": True,
                "reason": f"answer_status_{trust_status}",
            }
        if trust_status not in {"trusted", "completed", "success", "degraded", "unknown"}:
            return {
                **base,
                "status": "needs_human_review",
                "needs_human_review": True,
                "reason": f"unrecognized_answer_status_{trust_status}",
            }

        trace_id = str(
            captured_metadata.get("trace_id")
            or captured_metadata.get("workflow_run_id")
            or trust.get("trace_id")
            or f"feedback:{getattr(feedback, 'id', target_id)}"
        ).strip()
        try:
            confidence = float(trust.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        # User feedback is evidence of usefulness, not proof of truth.  Keep the
        # candidate below automatic activation thresholds and require governance.
        confidence = max(0.4, min(0.85, confidence))

        room_id = str(getattr(target, "room_id", "") or "").strip() or None
        source_kind = "meeting" if target_type == "meeting" else "chat"
        scope = MemoryScope(meeting_room_id=room_id) if room_id and target_type == "meeting" else MemoryScope()
        citations = captured_metadata.get("citations")
        if not isinstance(citations, list):
            citations = []
        source_refs = captured_metadata.get("source_refs")
        if not isinstance(source_refs, list):
            source_refs = []
        evidence = {
            "channel": target_type,
            "source_message_id": target_id,
            "feedback_id": str(getattr(feedback, "id", "") or ""),
            "feedback_type": "up",
            "trace_id": trace_id,
            "workflow_run_id": captured_metadata.get("workflow_run_id"),
            "citations": citations,
            "source_refs": source_refs,
            "conflict_ref_ids": list(captured_metadata.get("conflict_ref_ids") or []),
            "trust_protocol": trust,
        }
        request = MemoryWriteRequest(
            org_id=self._org_id,
            user_id=(None if target_type == "meeting" else str(getattr(target, "user_id", "") or actor_id)),
            source=MemorySource(
                kind=source_kind,
                trace_id=trace_id,
                agent_id=str(getattr(target, "agent_id", "") or "") or None,
            ),
            memory_type=MemoryType.AGENT_OPS_MEMORY,
            scope=scope,
            content=MemoryContent(
                summary=answer[:500],
                facts=[answer[:500]],
                warnings=(
                    ["answer_was_degraded"]
                    if trust_status == "degraded"
                    else []
                ),
            ),
            evidence_pointers=evidence,
            confidence=confidence,
            ttl_policy="90d",
            created_by_type="feedback",
            created_by=actor_id,
            trace_id=trace_id,
        )

        try:
            from app.services.memory_service import MemoryService

            # Do not synchronously call Embedding/Qdrant here.  The candidate is
            # durable in MySQL first; the worker consumes the pending outbox row.
            memory_service = MemoryService(self._session, self._org_id)
            response = await memory_service.write_candidate(request)
            result = {
                **base,
                "status": "candidate_created",
                "candidate_memory_id": response.memory_id or None,
                "candidate_state": str(getattr(response.status, "value", response.status) or "candidate"),
                "warnings": list(response.warnings or []),
                "needs_human_review": True,
            }
            if not response.memory_id:
                result["status"] = "candidate_rejected"
                result["reason"] = ";".join(response.warnings or []) or "memory_write_gate_rejected"
                return result

            item_repo = MemoryItemRepository(self._session, self._org_id)
            item = await item_repo.get_by_memory_id(response.memory_id)
            if item is None:
                return {**result, "index_status": "not_queued", "reason": "candidate_not_found_after_write"}

            outbox = MemorySyncOutboxRepository(self._session, self._org_id)
            scope_json = dict(getattr(item, "scope_json", None) or {})
            payload = {
                "collection": CANDIDATE_MEMORY_COLLECTION,
                "memory_id": str(item.memory_id),
                "org_id": self._org_id,
                "user_id": str(getattr(item, "user_id", None) or ""),
                "memory_type": str(getattr(item, "memory_type", "") or ""),
                "status": "candidate",
                "summary": str(getattr(item, "content_summary", "") or ""),
                "trust_score": float(getattr(item, "trust_score", 0) or 0),
                "confidence": float(getattr(item, "confidence", 0) or 0),
                "expires_at": getattr(item, "expires_at", None).isoformat() if getattr(item, "expires_at", None) else "",
                "product_line": str(getattr(item, "product_line", None) or scope_json.get("product_line") or ""),
                "rag_space_id": str(getattr(item, "rag_space_id", None) or scope_json.get("rag_space_id") or ""),
                "task_id": str(getattr(item, "task_id", None) or getattr(item, "source_task_id", None) or scope_json.get("task_id") or ""),
                "extra_payload": {
                    "review_status": str(getattr(item, "review_status", "candidate") or "candidate"),
                    "applicability": dict(getattr(item, "applicability_json", None) or {}),
                    "feedback_id": str(getattr(feedback, "id", "") or ""),
                    "source_message_id": target_id,
                },
            }
            await outbox.create_pending(
                memory_id=response.memory_id,
                action="UPSERT_CANDIDATE_VECTOR",
                target_backend="qdrant",
                payload=payload,
                trace_id=trace_id,
            )
            return {**result, "index_status": "queued", "needs_human_review": True}
        except Exception as exc:
            return {
                **base,
                "status": "candidate_write_failed",
                "needs_human_review": True,
                "reason": type(exc).__name__,
                "error": str(exc)[:300],
            }

    @staticmethod
    def _is_agent_answer_target(target_type: str, target) -> bool:
        message_type = str(getattr(target, "message_type", "") or "").strip().lower()
        role = str(getattr(target, "role", "") or "").strip().lower()
        if target_type == "meeting":
            return message_type in {"agent", "assistant", "agent_streaming"}
        return role == "assistant" or message_type in {"assistant", "agent", "agent_streaming"}

    async def list_message_feedbacks(
        self,
        *,
        target_type: str,
        actor_id: str,
        target_ids: list[str] | None = None,
    ):
        normalized_type = target_type.strip().lower()
        if normalized_type not in {"chat", "meeting"}:
            raise NotFoundError("feedback target not found")
        return await self._repo.list_message_feedbacks(
            org_id=self._org_id,
            target_type=normalized_type,
            actor_id=actor_id,
            target_ids=target_ids,
        )

    async def _ensure_feedback_target(self, target_type: str, target_id: str, actor_id: str):
        if target_type == "chat":
            stmt = (
                select(ChatMessage)
                .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                .where(
                    ChatMessage.org_id == self._org_id,
                    ChatMessage.id == target_id,
                    ChatMessage.deleted_at.is_(None),
                    ChatSession.org_id == self._org_id,
                    ChatSession.user_id == actor_id,
                    ChatSession.deleted_at.is_(None),
                )
            )
            target = (await self._session.execute(stmt)).scalar_one_or_none()
            if target:
                return target
        if target_type == "meeting":
            stmt = (
                select(MeetingMessage)
                .join(
                    MeetingRoomMember,
                    MeetingRoomMember.room_id == MeetingMessage.room_id,
                )
                .where(
                    MeetingMessage.org_id == self._org_id,
                    MeetingMessage.id == target_id,
                    MeetingMessage.deleted_at.is_(None),
                    MeetingRoomMember.org_id == self._org_id,
                    MeetingRoomMember.user_id == actor_id,
                    MeetingRoomMember.deleted_at.is_(None),
                )
            )
            target = (await self._session.execute(stmt)).scalar_one_or_none()
            if target:
                return target
        raise NotFoundError("feedback target not found")

    @staticmethod
    def _build_message_feedback_metadata(*, target_type: str, target, captured_at) -> dict:
        """Capture reproducible answer provenance without copying message text."""
        metadata = (
            dict(getattr(target, "metadata_json", None) or {})
            if target_type == "meeting"
            else dict(getattr(target, "payload", None) or {})
        )
        llm_meta = dict(metadata.get("llm_meta") or {})
        langfuse = dict(llm_meta.get("langfuse") or metadata.get("langfuse") or {})
        citations = metadata.get("citations") or metadata.get("source_refs") or []
        if not isinstance(citations, list):
            citations = []
        source_refs = metadata.get("source_scope_refs") or metadata.get("memory_sources") or citations
        if not isinstance(source_refs, list):
            source_refs = []
        conflict_ref_ids = metadata.get("conflict_ref_ids") or metadata.get("conflict_ids") or []
        if not isinstance(conflict_ref_ids, list):
            conflict_ref_ids = [str(conflict_ref_ids)] if conflict_ref_ids else []

        qdl = metadata.get("qdl") if isinstance(metadata.get("qdl"), dict) else {}
        qdl_version = (
            metadata.get("qdl_version")
            or qdl.get("version")
            or metadata.get("qdl_schema_version")
        )
        knowledge_version = (
            metadata.get("knowledge_version")
            or metadata.get("memory_version")
            or metadata.get("knowledge_snapshot_version")
        )
        return {
            "target_type": target_type,
            "target_id": str(getattr(target, "id", "") or ""),
            "message_type": str(getattr(target, "message_type", "") or ""),
            "agent_id": str(getattr(target, "agent_id", "") or "") or None,
            "trace_id": str(metadata.get("trace_id") or langfuse.get("trace_id") or "") or None,
            "trace_url": metadata.get("trace_url") or langfuse.get("trace_url"),
            "workflow_run_id": metadata.get("workflow_run_id"),
            "selected_subgraph": metadata.get("selected_subgraph"),
            "manager_status": metadata.get("manager_status") or metadata.get("status"),
            "source_refs": source_refs,
            "citations": citations,
            "conflict_ref_ids": [str(item) for item in conflict_ref_ids if item],
            "qdl_version": str(qdl_version) if qdl_version is not None else None,
            "knowledge_version": str(knowledge_version) if knowledge_version is not None else None,
            "captured_at": captured_at.isoformat() if hasattr(captured_at, "isoformat") else str(captured_at),
        }

    @staticmethod
    def _extract_trace_id(result) -> str:
        reasoning_chain = result.reasoning_chain or {}
        if isinstance(reasoning_chain, dict):
            trace = reasoning_chain.get("trace")
            if isinstance(trace, dict) and trace.get("trace_id"):
                return str(trace["trace_id"])
        return str(result.task_id)

    @staticmethod
    def _score_value(payload: dict) -> float:
        if payload["feedback_type"] == "up":
            return 1.0
        rating = payload.get("rating")
        if rating is None:
            return 0.0
        normalized = max(0.0, min(1.0, (float(rating) - 1.0) / 4.0))
        return round(normalized, 4)

    @staticmethod
    def _append_score_event(reasoning_chain, score_event: dict, actor_id: str) -> dict:
        chain = dict(reasoning_chain or {})
        events = chain.get("langfuse_scores")
        normalized_events = [item for item in events if isinstance(item, dict)] if isinstance(events, list) else []
        normalized_events = [item for item in normalized_events if str(item.get("metadata", {}).get("actor_id")) != actor_id]
        normalized_events.append(score_event)
        normalized_events.sort(key=lambda item: item.get("scored_at") or "", reverse=True)
        chain["langfuse_scores"] = normalized_events
        return chain

    @staticmethod
    def _queue_score_sync(score_event: dict) -> None:
        try:
            sync_langfuse_score.delay(score_event)
        except Exception:
            LangfuseTracer().sync_score(score_event)
