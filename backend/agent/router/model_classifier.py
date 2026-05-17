from __future__ import annotations

import json
import logging
from typing import Any

from agent.router.contracts import AgentRouteDecision

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """你是 PIAP 平台的消息路由分类器。
只根据用户输入判断它属于哪种意图，不生成回答。

输出严格 JSON：
{
  "selected_agent": "chat" | "inspection_task",
  "sub_route": "general_chat" | "rag_qa" | "quality_qa" | "task_create" | "inspection_execute",
  "confidence": 0.0 ~ 1.0,
  "reason": "简短理由"
}

分类标准：
- general_chat: 普通闲聊、问候、平台功能询问，无质检/任务/知识库意图
- rag_qa: 想查询知识库、总结文档、根据资料回答问题，无质检信号
- quality_qa: 询问质量判定、缺陷标准、是否合格、检测规范
- task_create: 想创建检测任务、发起质检流程
- inspection_execute: 上传了文件/图片并明确要进行检测
"""


class ModelClassifier:
    """小模型兜底分类器，仅用于规则无法确定的模糊输入。"""

    async def classify(
        self,
        query: str,
        llm_client: Any,
        ext: dict[str, Any] | None = None,
    ) -> AgentRouteDecision:
        ext = ext or {}
        has_rag_space = bool((ext.get("selected_rag_space") or {}).get("id"))
        has_attachments = bool(ext.get("attachments"))

        user_context = f"用户输入: {query}"
        if has_rag_space:
            user_context += "\n[用户已选择RAG知识库]"
        if has_attachments:
            user_context += "\n[用户上传了附件]"

        try:
            result = await llm_client.chat(
                system_prompt=CLASSIFIER_SYSTEM_PROMPT,
                user_message=user_context,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            data = json.loads(result.get("content", "{}"))
            return AgentRouteDecision(
                selected_agent=data.get("selected_agent", "chat"),
                sub_route=data.get("sub_route", "general_chat"),
                intent=data.get("sub_route", "general_chat"),
                confidence=float(data.get("confidence", 0.5)),
                reason=str(data.get("reason", "模型分类")),
                route_source="model",
            )
        except Exception as exc:
            logger.warning("Model classifier failed, fallback to general_chat: %s", exc)
            return AgentRouteDecision(
                selected_agent="chat",
                sub_route="general_chat",
                intent="general_chat",
                confidence=0.3,
                reason=f"模型分类失败回退: {exc}",
                route_source="fallback",
            )
