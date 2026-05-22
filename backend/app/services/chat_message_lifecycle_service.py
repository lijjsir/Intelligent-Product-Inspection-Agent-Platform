from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.repositories.chat_repo import ChatMessageRepository, ChatSessionRepository


class ChatMessageLifecycleService:
    def __init__(
        self,
        session,
        *,
        message_repository_cls: type | None = None,
        session_repository_cls: type | None = None,
    ) -> None:
        self._session = session
        message_repository_cls = message_repository_cls or ChatMessageRepository
        session_repository_cls = session_repository_cls or ChatSessionRepository
        self._messages = message_repository_cls(session)
        self._sessions = session_repository_cls(session)

    async def complete_turn(
        self,
        *,
        org_id: str,
        user_id: str,
        session_id: str,
        assistant_message_id: str,
        content: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> bool:
        get_message = getattr(self._messages, "get", None)
        current_message = await get_message(org_id, assistant_message_id) if callable(get_message) else None
        current_payload = (
            current_message.payload
            if current_message and isinstance(current_message.payload, dict)
            else {}
        )
        if current_payload.get("status") == "interrupted":
            return False
        await self._messages.update_assistant_message(
            org_id=org_id,
            message_id=assistant_message_id,
            content=content,
            message_type=message_type,
            payload=payload,
        )
        await self._sessions.touch(org_id, user_id, session_id)
        return True

    @staticmethod
    async def emit_final(
        emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
        *,
        session_id: str | None,
        assistant_message_id: str | None,
        workflow_run_id: str | None,
        content: str,
        payload: dict[str, Any],
        quality: dict[str, Any] | None = None,
    ) -> None:
        if not callable(emit):
            return
        await emit(
            {
                "event": "message_final",
                "session_id": session_id,
                "message_id": assistant_message_id,
                "workflow_run_id": workflow_run_id,
                "content": content,
                "payload": payload,
                "quality": dict(quality or {}),
            }
        )
