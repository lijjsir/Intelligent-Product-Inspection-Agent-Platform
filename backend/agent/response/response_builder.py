from __future__ import annotations

from typing import Any

UI_SCHEMA_MAP = {
    ("chat", "general_chat"): "chat_text_v1",
    ("chat", "rag_qa"): "rag_answer_v1",
    ("inspection_task", "quality_qa"): "quality_answer_v1",
    ("inspection_task", "task_create"): "task_action_v1",
    ("inspection_task", "inspection_execute"): "task_result_v1",
}


class ResponseBuilder:
    """统一构建 ChatAssistantPayload，保证所有流程返回结构一致。"""

    @staticmethod
    def build(
        *,
        agent: str,
        sub_route: str,
        answer: str,
        summary: str = "",
        message_type: str = "assistant_text",
        citations: list[dict[str, Any]] | None = None,
        quality: dict[str, Any] | None = None,
        rag_summary: dict[str, Any] | None = None,
        retrieval_metrics: dict[str, Any] | None = None,
        task_draft: dict[str, Any] | None = None,
        missing_slots: list[str] | None = None,
        awaiting_confirmation: bool = False,
        action_state: str = "answered",
        created_task: dict[str, Any] | None = None,
        result_card: dict[str, Any] | None = None,
        route_decision: dict[str, Any] | None = None,
        trace_id: str | None = None,
        trace_url: str | None = None,
        prompt_version: str = "",
        workflow_version: str = "quality_chat_v2",
        selected_rag_space: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ui_schema = UI_SCHEMA_MAP.get((agent, sub_route), "chat_text_v1")

        return {
            "answer": answer,
            "summary": summary,
            "agent": agent,
            "sub_route": sub_route,
            "intent": sub_route,
            "message_type": message_type,
            "ui_schema": ui_schema,
            "citations": list(citations or []),
            "rag_summary": rag_summary,
            "retrieval_metrics": retrieval_metrics,
            "quality": dict(quality or {}),
            "task_draft": task_draft,
            "task_form_defaults": task_draft,
            "missing_slots": list(missing_slots or []),
            "pending_action": None,
            "awaiting_confirmation": awaiting_confirmation,
            "action_state": action_state,
            "created_task": created_task,
            "result_card": result_card,
            "expectation_check": None,
            "route_decision": route_decision,
            "trace_id": trace_id,
            "trace_url": trace_url,
            "workflow_version": workflow_version,
            "prompt_version": prompt_version,
            "selected_rag_space": selected_rag_space,
            "status": "completed",
            "error": None,
        }
