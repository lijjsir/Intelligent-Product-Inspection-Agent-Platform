from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, AsyncIterator

from fastapi import Header, Query

from app.core.datetime import utcnow, utcnow_iso
from app.core.exceptions import ForbiddenError, NotFoundError, ServiceUnavailableError
from app.core.ids import uuid7
from app.core.permissions import ROLE_ADMIN, ROLE_EXPERT, ROLE_USER, require_role
from app.core.security import create_stream_token, safe_decode_token
from app.repositories.chat_repo import ChatMessageRepository, ChatOpsRepository, ChatSessionRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.chat import (
    ChatMessageResponse,
    ChatMessageSendRequest,
    ChatSendResponse,
    ChatSessionResponse,
    ChatTaskResultAppendRequest,
    ChatTaskSubmitRequest,
)
from agent.contracts import NormalizedAttachment
from app.schemas.stream import StreamSessionResponse
from app.schemas.user import CurrentUser
from app.services.chat_context_service import ChatContextService
from app.services.quality_agent_orchestrator_service import QualityAgentOrchestratorService
from app.services.rag_space_service import RagSpaceService
from app.services.stream_service import chat_stream_broker
from infra.database.session import get_session

logger = logging.getLogger(__name__)

_ACTIVE_CHAT_WORKFLOWS: dict[str, asyncio.Task[None]] = {}
_ACTIVE_CHAT_MESSAGE_TO_WORKFLOW: dict[str, str] = {}


@lru_cache(maxsize=1)
def get_quality_agent_orchestrator() -> QualityAgentOrchestratorService:
    return QualityAgentOrchestratorService()


def _track_chat_workflow(workflow_run_id: str, assistant_message_id: str, task: asyncio.Task[None]) -> None:
    _ACTIVE_CHAT_WORKFLOWS[workflow_run_id] = task
    _ACTIVE_CHAT_MESSAGE_TO_WORKFLOW[assistant_message_id] = workflow_run_id

    def cleanup(_task: asyncio.Task[None]) -> None:
        _ACTIVE_CHAT_WORKFLOWS.pop(workflow_run_id, None)
        _ACTIVE_CHAT_MESSAGE_TO_WORKFLOW.pop(assistant_message_id, None)

    task.add_done_callback(cleanup)


def get_current_user_for_stream(
    authorization: str = Header(default=""),
    token: str = Query(default=""),
) -> CurrentUser:
    raw_token = ""
    if authorization.startswith("Bearer "):
        raw_token = authorization.split(" ", 1)[1]
    elif token:
        raw_token = token
    if not raw_token:
        raise ForbiddenError("missing stream token")
    payload = safe_decode_token(raw_token)
    if payload.get("typ") != "stream":
        raise ForbiddenError("invalid stream token type")
    return CurrentUser(
        user_id=str(payload.get("user_id") or payload.get("sub") or ""),
        org_id=str(payload.get("org_id") or ""),
        role=str(payload.get("role") or ""),
        roles=[str(item) for item in (payload.get("roles") or [])],
        plan_tier=str(payload.get("plan_tier") or "basic"),
        capabilities=[str(item) for item in (payload.get("capabilities") or [])],
        workspaces=[str(item) for item in (payload.get("workspaces") or [])],
        default_workspace=str(payload.get("default_workspace") or "app"),
        stream_resource=str(payload.get("resource") or ""),
        stream_resource_id=str(payload.get("resource_id") or ""),
    )


def _make_embedder_factory(org_id: str, user_id: str | None, trace_id: str | None):
    from agent.rag.embedder import Embedder

    async def factory(text: str) -> list[float]:
        embedder = Embedder(
            org_id=org_id,
            user_id=user_id,
            trace_id=trace_id,
            allow_pseudo_fallback=False,
        )
        return await embedder.embed(text)

    return factory


class ChatService:
    def __init__(self, *, org_id: str, user_id: str, current: CurrentUser):
        self._org_id = org_id
        self._user_id = user_id
        self._current = current
        self._orchestrator = get_quality_agent_orchestrator()

    async def create_session(self, title: str | None = None) -> ChatSessionResponse:
        async with get_session() as session:
            repo = ChatSessionRepository(session)
            default_title = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            obj = await repo.create(self._org_id, self._user_id, title=title or default_title)
            await session.commit()
            return ChatSessionResponse.model_validate(obj)

    async def list_sessions(self, limit: int = 100) -> list[ChatSessionResponse]:
        async with get_session() as session:
            repo = ChatSessionRepository(session)
            rows = await repo.list_for_user(self._org_id, self._user_id, limit=limit)
            return [ChatSessionResponse.model_validate(item) for item in rows]

    async def list_messages(
        self,
        session_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> list[ChatMessageResponse]:
        async with get_session() as session:
            session_repo = ChatSessionRepository(session)
            if not await session_repo.get(self._org_id, self._user_id, session_id):
                raise NotFoundError("chat session not found")
            repo = ChatMessageRepository(session)
            rows = await repo.list_for_session(
                org_id=self._org_id,
                session_id=session_id,
                after_seq=after_seq,
                limit=limit,
            )
            return [ChatMessageResponse.model_validate(item) for item in rows]

    async def get_inspection_context(self) -> dict[str, Any]:
        try:
            async with get_session() as session:
                context_service = ChatContextService(
                    session,
                    org_id=self._org_id,
                    user_id=self._user_id,
                    role=self._current.role,
                )
                return await context_service.build_inspection_context(recent_limit=6, summary_window=12)
        except Exception as exc:
            logger.warning("chat inspection context endpoint failed: %s", exc, exc_info=True)
            return self._empty_inspection_context(scope="unavailable", error="质检上下文暂不可用，可手动选择任务加入 AI 上下文。")

    async def delete_session(self, session_id: str) -> bool:
        async with get_session() as session:
            repo = ChatSessionRepository(session)
            deleted = await repo.soft_delete(self._org_id, self._user_id, session_id)
            await session.commit()
            return deleted

    async def create_stream_session(self, *, resource: str, resource_id: str) -> StreamSessionResponse:
        require_role("chat" if resource in ("chat", "meeting") else "task", self._current.role)
        async with get_session() as session:
            if resource == "chat":
                session_repo = ChatSessionRepository(session)
                if not await session_repo.get(self._org_id, self._user_id, resource_id):
                    raise NotFoundError("chat session not found")
            elif resource == "meeting":
                from app.repositories.meeting_repo import MeetingRepository
                meeting_repo = MeetingRepository(session)
                member = await meeting_repo.get_member(self._org_id, resource_id, self._user_id)
                if not member:
                    raise ForbiddenError("you are not a member of this meeting room")
            else:
                task_repo = TaskRepository(session)
                owner_user_id = self._user_id if self._current.role in (ROLE_USER, ROLE_EXPERT) else None
                org_scope = None if self._current.role == ROLE_ADMIN else self._org_id
                if not await task_repo.get_for_user(org_scope, resource_id, owner_user_id=owner_user_id):
                    raise NotFoundError("task not found")
        expires_at = utcnow() + timedelta(minutes=10)
        token = create_stream_token(
            self._user_id,
            extra={
                "org_id": self._org_id,
                "user_id": self._user_id,
                "role": self._current.role,
                "roles": self._current.roles,
                "plan_tier": self._current.plan_tier,
                "capabilities": self._current.capabilities,
                "workspaces": self._current.workspaces,
                "default_workspace": self._current.default_workspace,
                "resource": resource,
                "resource_id": resource_id,
            },
            ttl_seconds=600,
        )
        return StreamSessionResponse(
            stream_token=token,
            expires_at=expires_at.replace(microsecond=0),
            resource=resource,
            resource_id=resource_id,
        )

    async def send_message(self, session_id: str, payload: ChatMessageSendRequest) -> ChatSendResponse:
        workflow_run_id = str(uuid7())
        ext_payload = dict(payload.ext or {})

        async with get_session() as session:
            session_repo = ChatSessionRepository(session)
            message_repo = ChatMessageRepository(session)
            ops_repo = ChatOpsRepository(session, self._org_id)
            chat_session = await session_repo.get(self._org_id, self._user_id, session_id)
            if not chat_session:
                raise NotFoundError("chat session not found")
            await ops_repo.ensure_chat_binding()

            rag_space_id = str(ext_payload.get("selected_rag_space_id") or "").strip()
            if rag_space_id:
                rag_service = RagSpaceService(session, org_id=self._org_id, user_id=self._user_id)
                try:
                    await rag_service.note_selected(rag_space_id)
                except NotFoundError:
                    for key in (
                        "selected_rag_space_id",
                        "selected_rag_space_name",
                        "selected_rag_space_description",
                        "selected_rag_space",
                    ):
                        ext_payload.pop(key, None)
                except ServiceUnavailableError:
                    pass

            user_message = await message_repo.create(
                session_id=session_id,
                org_id=self._org_id,
                user_id=self._user_id,
                role="user",
                content=payload.message.strip(),
                message_type="text",
                payload={
                    "schema_version": payload.schema_version,
                    "metadata": payload.metadata or {},
                    "ext": ext_payload,
                },
            )
            assistant_message = await message_repo.create(
                session_id=session_id,
                org_id=self._org_id,
                user_id=None,
                role="assistant",
                content="",
                message_type="streaming",
                payload={
                    "status": "running",
                    "workflow_run_id": workflow_run_id,
                },
            )
            await session_repo.touch(self._org_id, self._user_id, session_id)
            await session.commit()

        workflow_task = asyncio.create_task(
            self._run_workflow(
                session_id=session_id,
                user_message_id=str(user_message.id),
                assistant_message_id=str(assistant_message.id),
                request=payload.model_copy(update={"ext": ext_payload}),
                workflow_run_id=workflow_run_id,
                current_user_seq_no=int(user_message.seq_no or 0),
                assistant_message_seq_no=int(assistant_message.seq_no or 0),
            )
        )
        _track_chat_workflow(workflow_run_id, str(assistant_message.id), workflow_task)

        return ChatSendResponse(
            session=ChatSessionResponse.model_validate(chat_session),
            user_message=ChatMessageResponse.model_validate(user_message),
            assistant_message_id=str(assistant_message.id),
            workflow_run_id=workflow_run_id,
        )

    async def cancel_message(self, session_id: str, message_id: str) -> ChatMessageResponse:
        content = "已中断本次回答。你可以编辑上一条问题后重新发送。"
        now = utcnow_iso()
        async with get_session() as session:
            session_repo = ChatSessionRepository(session)
            if not await session_repo.get(self._org_id, self._user_id, session_id):
                raise NotFoundError("chat session not found")

            message_repo = ChatMessageRepository(session)
            message = await message_repo.get(self._org_id, message_id)
            if not message or str(message.session_id) != session_id or message.role != "assistant":
                raise NotFoundError("assistant message not found")

            payload = dict(message.payload or {})
            workflow_run_id = str(payload.get("workflow_run_id") or _ACTIVE_CHAT_MESSAGE_TO_WORKFLOW.get(message_id) or "")
            if workflow_run_id:
                task = _ACTIVE_CHAT_WORKFLOWS.get(workflow_run_id)
                if task and not task.done():
                    task.cancel()

            payload.update(
                {
                    "status": "interrupted",
                    "message_type": "interrupted",
                    "interrupted_at": now,
                    "workflow_run_id": workflow_run_id or payload.get("workflow_run_id"),
                }
            )
            updated = await message_repo.update_assistant_message(
                org_id=self._org_id,
                message_id=message_id,
                content=content,
                message_type="interrupted",
                payload=payload,
            )
            await session_repo.touch(self._org_id, self._user_id, session_id)
            await session.commit()

        event = {
            "event": "message_final",
            "session_id": session_id,
            "message_id": message_id,
            "workflow_run_id": workflow_run_id,
            "content": content,
            "payload": payload,
            "ts": now,
        }
        await chat_stream_broker.publish(session_id, event)
        return ChatMessageResponse.model_validate(updated)

    async def append_task_result(
        self,
        *,
        session_id: str,
        payload: ChatTaskResultAppendRequest,
    ) -> ChatMessageResponse:
        async with get_session() as session:
            session_repo = ChatSessionRepository(session)
            if not await session_repo.get(self._org_id, self._user_id, session_id):
                raise NotFoundError("chat session not found")
            message_repo = ChatMessageRepository(session)
            content = (
                "检测任务已创建成功。\n\n"
                f"任务 ID：{payload.task_id}\n"
                f"产品编号：{payload.product_id}\n"
                f"检测标准：{payload.spec_code}\n"
                f"当前状态：{payload.status}\n"
                f"图片数量：{payload.image_count}"
            )
            message = await message_repo.create(
                session_id=session_id,
                org_id=self._org_id,
                user_id=None,
                role="assistant",
                content=content,
                message_type="task_result",
                payload={
                    "answer": content,
                    "summary": "任务创建成功",
                    "action_state": "task_created",
                    "created_task": {
                        "id": payload.task_id,
                        "status": payload.status,
                        "product_id": payload.product_id,
                        "spec_code": payload.spec_code,
                        "priority": payload.priority,
                        "image_count": payload.image_count,
                    },
                },
            )
            await session_repo.touch(self._org_id, self._user_id, session_id)
            await session.commit()
            return ChatMessageResponse.model_validate(message)

    async def submit_task(
        self,
        *,
        session_id: str,
        payload: ChatTaskSubmitRequest,
    ) -> ChatMessageResponse:
        content = (
            "聊天页面不能创建或执行正式质量检测任务。\n\n"
            "请前往质量检测任务页面提交正式检测；聊天页只保留任务草稿、解释和辅助分析。"
        )
        async with get_session() as session:
            session_repo = ChatSessionRepository(session)
            if not await session_repo.get(self._org_id, self._user_id, session_id):
                raise NotFoundError("chat session not found")

            message_repo = ChatMessageRepository(session)
            message = await message_repo.create(
                session_id=session_id,
                org_id=self._org_id,
                user_id=None,
                role="assistant",
                content=content,
                message_type="action_blocked",
                payload={
                    "answer": content,
                    "summary": "聊天页禁止正式质检 action",
                    "message_type": "action_blocked",
                    "action_state": "blocked",
                    "task_draft": {
                        "product_id": payload.product_id.strip(),
                        "spec_code": payload.spec_code.strip(),
                        "image_urls": [item for item in payload.image_urls if item],
                        "priority": payload.priority,
                        "metadata": {
                            "source": "chat_draft",
                            "chat_source_message_id": payload.source_message_id,
                            **dict(payload.metadata or {}),
                        },
                    },
                    "task_form_defaults": {
                        "product_id": payload.product_id.strip(),
                        "spec_code": payload.spec_code.strip(),
                        "image_urls": [item for item in payload.image_urls if item],
                        "priority": payload.priority,
                        "metadata": dict(payload.metadata or {}),
                    },
                    "created_task": None,
                    "ui_schema": "chat_answer_v2",
                    "route_trace": {
                        "surface": "chat",
                        "capabilities_used": [],
                        "satisfied": False,
                        "errors": [{"message": "chat surface forbids action"}],
                    },
                },
            )
            await session_repo.touch(self._org_id, self._user_id, session_id)
            await session.commit()
            return ChatMessageResponse.model_validate(message)

    async def _run_workflow(
        self,
        *,
        session_id: str,
        assistant_message_id: str,
        request: ChatMessageSendRequest,
        workflow_run_id: str,
        current_user_seq_no: int,
        assistant_message_seq_no: int,
        user_message_id: str | None = None,
    ) -> None:
        async def emit(event: dict[str, Any]) -> None:
            event.setdefault("ts", utcnow_iso())
            await chat_stream_broker.publish(session_id, event)

        await emit(
            {
                "event": "run_started",
                "session_id": session_id,
                "message_id": assistant_message_id,
                "workflow_run_id": workflow_run_id,
            }
        )

        try:
            ext_payload = dict(request.ext or {})
            ext_payload["emit"] = emit
            ext_payload["current_user_seq_no"] = current_user_seq_no
            ext_payload["assistant_message_seq_no"] = assistant_message_seq_no
            ext_payload["idempotency_key"] = (
                f"{self._org_id}:{session_id}:{assistant_message_id}:{workflow_run_id}"
            )
            try:
                await self._index_session_message(
                    session_id=session_id,
                    message_id=user_message_id or "",
                    seq_no=current_user_seq_no,
                    role="user",
                    content=request.message.strip(),
                    trace_id=workflow_run_id,
                )
            except Exception as exc:
                from app.errors.memory_errors import ShortTermMemoryError
                raise ShortTermMemoryError(
                    "会话语义召回索引失败，本次聊天已停止。",
                    code="SHORT_TERM_SESSION_RECALL_FAILED",
                    detail={
                        "session_id": session_id,
                        "message_id": user_message_id,
                        "seq_no": current_user_seq_no,
                        "cause": str(exc),
                    },
                ) from exc

            # Load shared memory context for this query
            ext_payload["shared_memory_context"] = None
            try:
                from app.schemas.memory import MemorySearchRequest
                from app.services.memory_service import MemoryService
                from app.services.memory_vector_service import MemoryVectorService, MemoryVectorServiceError
                from app.errors.memory_errors import SharedMemoryError

                memory_search_req = MemorySearchRequest(
                    org_id=self._org_id,
                    user_id=self._user_id,
                    query=request.message.strip(),
                    scope_filter=None,
                    top_k=5,
                )
                vector_svc = MemoryVectorService(
                    embedder_factory=_make_embedder_factory(self._org_id, self._user_id, None),
                    org_id=self._org_id,
                    user_id=self._user_id,
                )
                async with get_session() as mem_session:
                    memory_svc = MemoryService(mem_session, self._org_id, vector_service=vector_svc)
                    result = await memory_svc.search(memory_search_req)
                    if result.items:
                        ext_payload["shared_memory_context"] = {
                            "items": [
                                {
                                    "memory_id": item.memory_id,
                                    "memory_type": item.memory_type,
                                    "summary": item.summary,
                                    "score": item.score,
                                    "confidence": item.confidence,
                                    "trust_score": item.trust_score,
                                }
                                for item in result.items
                            ],
                            "policy_version": result.policy_version,
                        }
                        # Apply lightweight conflict guard to shared memory results
                        if result.items:
                            from app.services.retrieval_conflict_guard import RetrievalConflictGuard
                            guard = RetrievalConflictGuard(
                                org_id=self._org_id,
                                user_id=self._user_id,
                                trace_id=None,
                            )
                            mem_dicts = [
                                {
                                    "memory_id": item.memory_id,
                                    "memory_type": item.memory_type,
                                    "summary": item.summary,
                                    "score": item.score,
                                    "confidence": item.confidence,
                                    "trust_score": item.trust_score,
                                    "source": item.source,
                                    "warnings": item.warnings,
                                }
                                for item in result.items
                            ]
                            guard_result = guard.check_sync(
                                query=request.message.strip(),
                                memory_hits=mem_dicts,
                                session_facts=ext_payload.get("session_facts"),
                            )
                            ext_payload["shared_memory_context"]["conflict_guard"] = {
                                "conflicts": guard_result["conflicts"],
                                "suppressed_memory_ids": guard_result["suppressed_memory_ids"],
                                "downranked_memory_ids": guard_result["downranked_memory_ids"],
                            }
            except MemoryVectorServiceError as exc:
                raise SharedMemoryError(
                    "共享记忆检索失败，本次聊天已停止。",
                    code="SHARED_MEMORY_SEARCH_FAILED",
                    detail={"session_id": session_id, "cause": str(exc)},
                ) from exc
            except Exception:
                raise

            # Load short-term memory context (replaces raw DB history read)
            ext_payload["history_messages"] = []
            ext_payload["conversation_summary"] = None
            ext_payload["session_facts"] = {}
            ext_payload["pending_action"] = None
            ext_payload["short_term_memory"] = None
            try:
                from app.services.short_term_memory_service import ShortTermMemoryService

                async with get_session() as stm_session:
                    stm_svc = ShortTermMemoryService(stm_session, self._org_id)
                    stm = await stm_svc.build_context(
                        user_id=self._user_id,
                        session_id=session_id,
                        current_user_seq_no=current_user_seq_no,
                        current_query=request.message.strip(),
                    )
                    ext_payload["history_messages"] = stm["recent_messages"]
                    ext_payload["conversation_summary"] = stm["conversation_summary"]
                    ext_payload["session_facts"] = stm["session_facts"]
                    ext_payload["pending_action"] = stm["pending_action"]
                    structured_stm = dict(stm.get("short_term_memory") or {})
                    structured_stm["semantic_recall"] = list(stm.get("semantic_recall") or [])
                    ext_payload["short_term_memory"] = structured_stm
            except Exception:
                raise

            # Load inspection context
            if ext_payload.get("inspection_context_enabled") is True:
                try:
                    async with get_session() as ctx_session:
                        context_service = ChatContextService(
                            ctx_session,
                            org_id=self._org_id,
                            user_id=self._user_id,
                            role=self._current.role,
                        )
                        selected_task_ids = [
                            str(item)
                            for item in list(ext_payload.get("selected_inspection_task_ids") or [])
                            if str(item).strip()
                        ]
                        ext_payload["inspection_context"] = await context_service.build_inspection_context(
                            selected_task_ids=selected_task_ids
                        )
                except Exception:
                    logger.debug("chat inspection context build skipped", exc_info=True)
                    ext_payload["inspection_context"] = self._empty_inspection_context(scope="unavailable")
            else:
                ext_payload.pop("inspection_context", None)
                ext_payload.pop("selected_inspection_task_ids", None)
            result = await self._orchestrator.run_chat(
                {
                    "request_id": str(uuid7()),
                    "workflow_run_id": workflow_run_id,
                    "session_id": session_id,
                    "assistant_message_id": assistant_message_id,
                    "org_id": self._org_id,
                    "user_id": self._user_id,
                    "plan_tier": self._current.plan_tier,
                    "capabilities": self._current.capabilities,
                    "query": request.message.strip(),
                    "metadata": dict(request.metadata or {}),
                    "ext": ext_payload,
                    "attachments": [
                        NormalizedAttachment.model_validate(item).model_dump()
                        for item in list(ext_payload.get("attachments") or [])
                    ],
                    "image_urls": [
                        str(item.get("url") or "").strip()
                        for item in list(ext_payload.get("attachments") or [])
                        if isinstance(item, dict) and str(item.get("kind") or "").lower() == "image" and str(item.get("url") or "").strip()
                    ],
                }
            )
            # After successful orchestration, extract and persist reusable candidate memories.
            from app.services.memory_extraction_service import MemoryExtractionService
            from app.services.memory_service import MemoryService
            from app.services.memory_vector_service import CANDIDATE_MEMORY_COLLECTION, MemoryVectorService

            agent_output = result.get("agent_output", {})
            answer_text = str(agent_output.get("answer") or agent_output.get("summary") or "")
            if answer_text.strip():
                try:
                    await self._index_session_message(
                        session_id=session_id,
                        message_id=assistant_message_id,
                        seq_no=assistant_message_seq_no,
                        role="assistant",
                        content=answer_text,
                        trace_id=workflow_run_id,
                    )
                except Exception as exc:
                    from app.errors.memory_errors import ShortTermMemoryError
                    raise ShortTermMemoryError(
                        "会话语义召回索引失败，本次聊天已停止。",
                        code="SHORT_TERM_SESSION_RECALL_FAILED",
                        detail={
                            "session_id": session_id,
                            "message_id": assistant_message_id,
                            "seq_no": assistant_message_seq_no,
                            "cause": str(exc),
                        },
                    ) from exc
            task_id = str(
                ext_payload.get("selected_inspection_task_ids", [None])[0]
            ) if ext_payload.get("selected_inspection_task_ids") else None

            extraction_svc = MemoryExtractionService(
                org_id=self._org_id,
                user_id=self._user_id,
            )
            candidates = await extraction_svc.extract_from_chat_result(
                trace_id=workflow_run_id,
                user_message=request.message.strip(),
                assistant_answer=answer_text,
                task_id=task_id,
                short_term_memory=ext_payload.get("short_term_memory"),
            )
            if candidates:
                async with get_session() as mem_session:
                    vector_svc = MemoryVectorService(
                        embedder_factory=_make_embedder_factory(self._org_id, self._user_id, workflow_run_id),
                        org_id=self._org_id,
                        user_id=self._user_id,
                    )
                    candidate_vector_svc = MemoryVectorService(
                        collection=CANDIDATE_MEMORY_COLLECTION,
                        embedder_factory=_make_embedder_factory(self._org_id, self._user_id, workflow_run_id),
                        org_id=self._org_id,
                        user_id=self._user_id,
                    )
                    memory_svc = MemoryService(
                        mem_session,
                        self._org_id,
                        vector_service=vector_svc,
                        candidate_vector_service=candidate_vector_svc,
                    )
                    for candidate in candidates:
                        await memory_svc.write_candidate(candidate)
                    await mem_session.commit()

            # Trigger session summarization
            try:
                from app.services.chat_session_summary_service import ChatSessionSummaryService
                from app.errors.memory_errors import ShortTermMemoryError
                async with get_session() as summary_session:
                    summary_svc = ChatSessionSummaryService(summary_session, self._org_id, self._user_id)
                    await summary_svc.maybe_summarize(session_id)
                    await summary_session.commit()
            except ShortTermMemoryError:
                raise
            except Exception as exc:
                raise RuntimeError(f"short-term memory summary failed: {exc}") from exc

        except Exception as exc:
            logger.exception(
                "chat workflow failed session_id=%s assistant_message_id=%s workflow_run_id=%s",
                session_id,
                assistant_message_id,
                workflow_run_id,
            )
            failure_payload = self._build_error_payload(exc)
            error_message = str(exc) or exc.__class__.__name__
            content = f"聊天任务执行失败：{error_message}"
            async with get_session() as session:
                repo = ChatMessageRepository(session)
                await repo.update_assistant_message(
                    org_id=self._org_id,
                    message_id=assistant_message_id,
                    content=content,
                    message_type="error",
                    payload=failure_payload,
                )
                await session.commit()
            await emit(
                {
                    "event": "run_failed",
                    "session_id": session_id,
                    "message_id": assistant_message_id,
                    "workflow_run_id": workflow_run_id,
                    "content": content,
                    "payload": failure_payload,
                }
            )

    @staticmethod
    def _build_error_payload(exc: Exception) -> dict:
        code = getattr(exc, "code", "CHAT_WORKFLOW_FAILED")
        detail = getattr(exc, "detail", {})
        return {
            "status": "failed",
            "message_type": "error",
            "error_code": code,
            "error": str(exc),
            "detail": detail,
            "ui_schema": "chat_error_v1",
            "recoverable": False,
        }

    async def _index_session_message(
        self,
        *,
        session_id: str,
        message_id: str,
        seq_no: int,
        role: str,
        content: str,
        trace_id: str | None,
    ) -> None:
        text = str(content or "").strip()
        if not text:
            return
        from app.services.session_memory_vector_service import SessionMemoryVectorService

        session_vector_svc = SessionMemoryVectorService(
            _make_embedder_factory(self._org_id, self._user_id, trace_id),
            self._org_id,
            self._user_id,
        )
        await session_vector_svc.upsert_message(
            org_id=self._org_id,
            user_id=self._user_id,
            session_id=session_id,
            message_id=message_id or f"{role}_{seq_no}",
            seq_no=seq_no,
            role=role,
            content=text,
        )

    @staticmethod
    def _empty_inspection_context(*, scope: str, error: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scope": scope,
            "summary_window": 0,
            "stats": {},
            "recent_tasks": [],
            "recent_failures": [],
            "latest_task": None,
            "selected_tasks": [],
        }
        if error:
            payload["error"] = error
        return payload

    async def stream_events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        async for event in chat_stream_broker.subscribe(session_id):
            yield event
