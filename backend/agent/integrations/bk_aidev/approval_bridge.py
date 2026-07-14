"""Bridge tool confirmation blocks to the existing PIAP approval center."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

from cryptography.fernet import Fernet

from agent.integrations.bk_aidev.tool_safety import (
    configured_tool_safety_policy,
    sanitize_tool_output,
)
from app.core.config import settings


logger = logging.getLogger(__name__)


def encrypt_tool_arguments(arguments: dict[str, Any]) -> str:
    serialized = json.dumps(arguments, ensure_ascii=False, default=str).encode("utf-8")
    return _fernet().encrypt(serialized).decode("utf-8")


def decrypt_tool_arguments(token: str) -> dict[str, Any]:
    value = json.loads(_fernet().decrypt(token.encode("utf-8")).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("tool approval arguments must be a JSON object")
    return value


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.governance_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


async def create_tool_approval(
    *,
    db_session: Any,
    spec: Any,
    arguments: dict[str, Any],
    context: Any,
) -> dict[str, Any] | None:
    if db_session is None or not context.user_id:
        return None

    try:
        from app.schemas.approval import ApprovalCreate
        from app.services.approval_service import ApprovalService

        service = ApprovalService(db_session, context.org_id)
        requester_role = str(context.metadata.get("requester_role") or "user")
        existing_id = str(context.metadata.get("approval_id") or "").strip()
        if existing_id:
            approval = await service.get_approval(
                existing_id,
                current_role=requester_role,
                current_user_id=context.user_id,
            )
            return {
                "id": approval.id,
                "status": approval.status,
                "source_module": approval.source_module,
                "tool_name": spec.name,
            }

        contextual_secrets = context.metadata.get("sensitive_values") or []
        if isinstance(contextual_secrets, str):
            contextual_secrets = [contextual_secrets]
        redacted_arguments = sanitize_tool_output(
            arguments,
            configured_tool_safety_policy(contextual_secrets),
        )
        approval = await service.create_approval(
            requester_id=context.user_id,
            requester_role=requester_role,
            payload=ApprovalCreate(
                source_module="agent_tool",
                source_id=str(context.request_id or context.workflow_run_id or "") or None,
                operation_summary=f"执行工具「{spec.title or spec.name}」",
                risk_level=str(spec.risk_level or "medium"),
                payload_json={
                    "tool_name": spec.name,
                    "arguments_encrypted": encrypt_tool_arguments(arguments),
                    "arguments_redacted": redacted_arguments,
                    "agent": context.agent,
                    "surface": context.surface,
                    "request_id": context.request_id,
                    "session_id": context.session_id,
                    "workflow_run_id": context.workflow_run_id,
                    "trace_id": context.trace_id,
                    "allowed_modes": list(context.allowed_modes),
                },
            ),
        )
    except Exception:
        logger.exception("failed to create or resolve tool approval")
        return None

    context.metadata["approval_id"] = approval.id
    return {
        "id": approval.id,
        "status": approval.status,
        "source_module": approval.source_module,
        "tool_name": spec.name,
    }
