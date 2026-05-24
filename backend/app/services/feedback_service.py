from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from agent.llm.langfuse_tracer import LangfuseTracer
from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError
from app.core.ids import uuid7
from app.models.chat import ChatMessage, ChatSession
from app.models.meeting import MeetingMessage, MeetingRoomMember
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.result_repo import ResultRepository
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
        await self._ensure_feedback_target(normalized_type, target_id, actor_id)
        now = utcnow()
        return await self._repo.save_message_feedback(
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
                "created_at": now,
                "updated_at": now,
            }
        )

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

    async def _ensure_feedback_target(self, target_type: str, target_id: str, actor_id: str) -> None:
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
            if (await self._session.execute(stmt)).scalar_one_or_none():
                return
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
            if (await self._session.execute(stmt)).scalar_one_or_none():
                return
        raise NotFoundError("feedback target not found")

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
