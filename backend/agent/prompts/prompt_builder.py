from __future__ import annotations

import logging
from typing import Any

from infra.database.session import get_session

logger = logging.getLogger(__name__)


PROMPT_SPECS: dict[str, dict[str, Any]] = {
    "general_chat": {
        "prompt_key": "chat.general.system",
        "prompt_version": "chat_general_v1",
        "temperature": 0.7,
        "default_content": """你是 PIAP 平台的通用聊天助手。你可以解释平台功能、普通问题、知识库使用方式和检测任务入口。如果用户没有提出质检、任务创建、知识库引用需求，不要主动输出质检判定、检测标准、风险等级、缺陷结论等内容。回答应自然、简洁、面向用户操作。只返回 JSON：{\"answer\": string, \"summary\": string}。""",
    },
    "rag_qa": {
        "prompt_key": "chat.rag_answer.system",
        "prompt_version": "chat_rag_qa_v1",
        "temperature": 0.2,
        "default_content": """你是知识库问答助手。请基于检索到的知识库内容回答用户的问题。不要套用质量检测、任务检测、标准编号、产品型号、缺陷位置、风险等级等质检话术。如果证据不足，请说明知识库中没有足够相关内容，并给出可以继续补充的方向。只返回 JSON：{\"answer\": string, \"summary\": string}。""",
    },
    "file_summary": {
        "prompt_key": "chat.file_summary.system",
        "prompt_version": "chat_file_summary_v1",
        "temperature": 0.3,
        "default_content": """请对以下文件内容进行总结。要求：1. 提取关键信息点。2. 标注数据来源（页码或段落）。3. 对于检测相关文件，识别产品类型、检测项、判定标准。""",
    },
    "quality_qa": {
        "prompt_key": "inspection.quality_qa.system",
        "prompt_version": "inspection_quality_qa_v1",
        "temperature": 0.2,
        "default_content": """你是质量检测问答助手。请基于检索到的标准、规范、规则和历史检测依据回答用户的质检问题。回答必须包含：判定依据、不确定性说明、必要时的引用来源。证据不足时，请明确说明不能做最终判定，不要编造标准条款或检测结论。只返回 JSON：{\"answer\": string, \"summary\": string}。""",
    },
    "task_create": {
        "prompt_key": "inspection.task_create.system",
        "prompt_version": "inspection_task_create_v1",
        "temperature": 0.3,
        "default_content": """你是检测任务创建助手。你的职责是从用户输入中提取产品编号、检测标准、检测图片、优先级，并生成任务草稿。如果信息不足，只追问缺失字段，不要进行质量判定。如果信息完整，请展示任务草稿，并要求用户确认后再提交。只返回 JSON：{\"answer\": string, \"summary\": string}。""",
    },
    "inspection_execute": {
        "prompt_key": "inspection.inspection_execute.system",
        "prompt_version": "inspection_execute_v1",
        "temperature": 0.2,
        "default_content": """你是正式质量检测执行智能体。请基于图片、结构化文件、产品信息、检测标准和 RAG 证据完成检测。输出必须包含检测结论、依据、引用、风险等级、结果摘要。证据不足时，应进入人工复核或补充信息状态，不要强行 PASS/FAIL。只返回 JSON：{\"answer\": string, \"summary\": string}。""",
    },
}


def _format_task_draft(draft: dict[str, Any]) -> str:
    if not draft:
        return "无"
    lines = []
    for key, value in draft.items():
        if not key.startswith("_") and value:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines) if lines else "无"


def _slot_labels(slots: list[str]) -> list[str]:
    labels = {
        "product_id": "产品编号",
        "spec_code": "检测标准",
        "image_urls": "检测图片",
        "priority": "优先级",
    }
    return [labels.get(s, s) for s in slots]


def _prompt_spec(sub_route: str) -> dict[str, Any]:
    return PROMPT_SPECS.get(sub_route, PROMPT_SPECS["general_chat"])


async def _resolve_runtime_prompt(sub_route: str, org_id: str | None) -> tuple[str, str]:
    spec = _prompt_spec(sub_route)
    default_content = str(spec["default_content"])
    prompt_key = str(spec.get("prompt_key") or "").strip()
    prompt_version = str(spec.get("prompt_version") or sub_route or "prompt_default")
    if not org_id or not prompt_key:
        return default_content, prompt_version

    try:
        from app.services.prompt_admin_service import PromptResolver

        resolver = PromptResolver(get_session)
        content = await resolver.get(prompt_key, org_id=org_id)
        return content or default_content, prompt_version
    except Exception as exc:
        logger.warning("runtime prompt resolve failed prompt_key=%s org_id=%s: %s", prompt_key, org_id, exc)
        return default_content, prompt_version


class PromptBuilder:
    """按 agent + sub_route 生成系统提示词、用户消息和元数据。"""

    @staticmethod
    async def build_runtime(
        *,
        agent: str,
        sub_route: str,
        query: str,
        org_id: str | None = None,
        history: list[dict[str, Any]] | None = None,
        retrieved_docs: list[dict[str, Any]] | None = None,
        task_draft: dict[str, Any] | None = None,
        action_state: str = "",
        runtime_prompt_section: str = "",
    ) -> tuple[str, str, float, dict[str, Any]]:
        prompt_content, prompt_version = await _resolve_runtime_prompt(sub_route, org_id)
        return PromptBuilder.build(
            agent=agent,
            sub_route=sub_route,
            query=query,
            history=history,
            retrieved_docs=retrieved_docs,
            task_draft=task_draft,
            action_state=action_state,
            runtime_prompt_section=runtime_prompt_section,
            prompt_override=prompt_content,
            prompt_version_override=prompt_version,
        )

    @staticmethod
    def build(
        *,
        agent: str,
        sub_route: str,
        query: str,
        history: list[dict[str, Any]] | None = None,
        retrieved_docs: list[dict[str, Any]] | None = None,
        task_draft: dict[str, Any] | None = None,
        action_state: str = "",
        runtime_prompt_section: str = "",
        prompt_override: str | None = None,
        prompt_version_override: str | None = None,
    ) -> tuple[str, str, float, dict[str, Any]]:
        """返回 (system_prompt, user_message, temperature, metadata)"""
        prompt_config = _prompt_spec(sub_route)
        system_prompt = str(prompt_override or prompt_config["default_content"])
        temperature = float(prompt_config["temperature"])
        prompt_version = str(prompt_version_override or prompt_config["prompt_version"])

        if runtime_prompt_section:
            system_prompt = f"{system_prompt}\n\n{runtime_prompt_section}"

        history_lines = [
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in (history or [])[-6:]
            if item.get("content")
        ]
        history_text = "\n".join(history_lines) if history_lines else "无"

        user_message = f"用户消息:\n{query}\n\n历史对话:\n{history_text}"

        if retrieved_docs:
            doc_lines = [
                "\n".join(
                    [
                        f"[{i}] 标题: {doc.get('title', '')}",
                        f"来源: {doc.get('source', '')}",
                        f"内容: {str(doc.get('text', '') or '')[:600]}",
                    ]
                )
                for i, doc in enumerate(retrieved_docs, start=1)
            ]
            doc_text = "\n\n".join(doc_lines) if doc_lines else "无"
            user_message = f"问题:\n{query}\n\n历史对话:\n{history_text}\n\n检索证据:\n{doc_text}"

        if task_draft:
            draft_text = _format_task_draft(task_draft)
            missing = list(task_draft.get("_missing_slots") or [])
            label_hints = "、".join(_slot_labels(missing)) if missing else "无"
            task_context = (
                f"\n\n当前任务草稿：\n{draft_text}\n"
                f"缺失字段：{label_hints}\n"
                f"当前状态：{action_state}"
            )
            user_message += task_context

        metadata = {
            "prompt_version": prompt_version,
            "prompt_key": prompt_config["prompt_key"],
            "agent": agent,
            "sub_route": sub_route,
            "temperature": temperature,
        }

        return system_prompt, user_message, temperature, metadata
