from __future__ import annotations

import re
from typing import Any

from agent.router.contracts import AgentRouteDecision, AgentRouterInput

# 任务创建关键词（从 quality_judgement/graph.py 迁移并扩展）
TASK_KEYWORD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"创建任务", r"新建任务", r"发起检测", r"提交任务",
        r"检测任务", r"任务", r"task",
        r"(创建|新建|发起|提交).{0,8}(任务|检测|质检)",
        r"(帮我|给我).{0,8}(检测|质检)",
    ]
]

STRUCTURED_FILE_EXTENSIONS = {"xlsx", "csv", "json", "txt", "docx", "jsonl", "md"}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

TASK_INTENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(创建|新建|发起|提交|开始|启动|帮我|给我).{0,12}(任务|检测|质检)",
        r"(需要|想要).{0,8}(创建|发起).{0,8}(任务|检测)",
        r"^\s*(质量检测|质检|检测任务|开始检测|启动检测|quality inspection|inspection task)\s*[!！?.]?\s*$",
        r"(检测|质检).{0,6}(图片|照片|文件|这个|这份)",
    ]
]


class AgentRoutePolicy:
    """基于规则的路由策略。规则无法确定时走 QualityChatAgent 兜底。"""

    def decide(self, input_data: AgentRouterInput) -> AgentRouteDecision:
        query = str(input_data.query or "").strip()
        attachments = list(input_data.attachments or [])
        image_urls = list(input_data.image_urls or [])
        route_hints = {
            **dict(input_data.route_hints or {}),
            **dict((input_data.ext or {}).get("route_hints") or {}),
        }

        if route_hints.get("force_agent") == "inspection_task":
            return AgentRouteDecision(
                selected_agent="inspection_task",
                intent="task_create",
                reason="前端模式指定任务检测 Agent",
                route_source="manual",
            )
        if route_hints.get("force_agent") == "quality_chat":
            return AgentRouteDecision(
                selected_agent="quality_chat",
                intent="general_qa",
                confidence=1.0,
                reason="前端模式指定智能问答 Agent",
                route_source="manual",
            )

        has_non_pdf = False
        has_image_attachment = False
        for item in attachments:
            name = str(item.get("name") or "").lower()
            suffix = name.rsplit(".", 1)[-1] if "." in name else ""
            if suffix in STRUCTURED_FILE_EXTENSIONS:
                has_non_pdf = True
            if suffix in IMAGE_EXTENSIONS or item.get("kind") == "image":
                has_image_attachment = True

        has_task_keyword = any(p.search(query) for p in TASK_KEYWORD_PATTERNS)
        has_task_intent = any(p.search(query) for p in TASK_INTENT_PATTERNS)

        # 1. 结构化文件 → InspectionTaskAgent
        if has_non_pdf:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                intent="task_create" if has_task_keyword else "structured_inspection",
                reason="用户上传了结构化文件（xlsx/csv/json等）",
                route_source="rule",
            )

        # 2. 上传图片 + 要求检测 → InspectionTaskAgent
        if (has_image_attachment or image_urls) and has_task_keyword:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                intent="task_create",
                reason="用户上传图片并要求检测/创建任务",
                route_source="rule",
            )

        # 3. 明确任务创建意图关键词 → InspectionTaskAgent
        if has_task_intent:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                intent="task_create",
                reason="检测到任务创建意图关键词",
                route_source="rule",
            )

        # 4. 默认走 QualityChatAgent
        return AgentRouteDecision(
            selected_agent="quality_chat",
            intent="general_qa",
            confidence=0.85,
            reason="未匹配到检测/任务信号，路由到聊天 Agent",
            route_source="rule",
        )
