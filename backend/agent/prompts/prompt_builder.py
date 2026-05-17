from __future__ import annotations

from typing import Any

from agent.prompts.chat import CHAT_PROMPTS
from agent.prompts.inspection import INSPECTION_PROMPTS

ALL_PROMPTS = {**CHAT_PROMPTS, **INSPECTION_PROMPTS}


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


class PromptBuilder:
    """按 agent + sub_route 生成系统提示词、用户消息和元数据。"""

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
    ) -> tuple[str, str, float, dict[str, Any]]:
        """返回 (system_prompt, user_message, temperature, metadata)"""
        prompt_config = ALL_PROMPTS.get(sub_route, CHAT_PROMPTS["general_chat"])
        system_prompt = prompt_config["system"]
        temperature = prompt_config["temperature"]

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
                "\n".join([
                    f"[{i}] 标题: {doc.get('title', '')}",
                    f"来源: {doc.get('source', '')}",
                    f"内容: {str(doc.get('text', '') or '')[:600]}",
                ])
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
            "prompt_version": prompt_config["version"],
            "agent": agent,
            "sub_route": sub_route,
            "temperature": temperature,
        }

        return system_prompt, user_message, temperature, metadata
