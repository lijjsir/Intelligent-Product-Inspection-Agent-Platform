from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypedDict


class QualityChatState(TypedDict, total=False):
    schema_version: str
    request_id: str
    workflow_run_id: str
    session_id: str
    assistant_message_id: str
    org_id: str
    user_id: str
    plan_tier: str
    capabilities: list[str]
    workspace: str
    query: str
    metadata: dict[str, Any]
    ext: dict[str, Any]
    history: list[dict[str, Any]]
    intent: str
    intent_confidence: float
    pending_action: str | None
    action_state: str
    task_draft: dict[str, Any]
    missing_slots: list[str]
    awaiting_confirmation: bool
    created_task: dict[str, Any]
    retrieved_chunks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    retrieval_metrics: dict[str, Any]
    reasoning: dict[str, Any]
    response_payload: dict[str, Any]
    quality: dict[str, Any]
    trace: dict[str, Any]
    prompt_version: str
    workflow_version: str
    runtime_error: dict[str, Any]
    trust_scoring_payload: dict[str, Any] | None
    trust_scoring_task: asyncio.Task | None
    emit: Callable[[dict[str, Any]], Awaitable[None]]
