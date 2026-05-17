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

QUALITY_QA_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"质量|质检|缺陷|不合格|合格|判定|标准|规范|划痕|瑕疵",
        r"(这个|那个).{0,4}(算不算|是不是|能不能).{0,4}(缺陷|不合格|有问题)",
        r"(怎么|如何).{0,6}(判定|判断|检测|评估)",
        r"GB/T|ISO|标准.{0,4}要求|规范.{0,4}规定",
        r"(什么|哪些).{0,4}(情况|时候).{0,4}(缺陷|不合格|处理)",
        r"检测标准|质量要求|判定依据|判定规则",
    ]
]

GENERAL_RAG_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"总结|概括|归纳.{0,4}(文档|知识库|资料|这份)",
        r"(文档|知识库|资料).{0,4}(说什么|讲什么|内容|主要)",
        r"根据.{0,4}(文档|知识库|资料|选中)",
        r"(查|找|搜索).{0,4}(文档|知识库)",
        r"知识库|参考资料|参考文档",
    ]
]


class AgentRoutePolicy:
    """基于规则的路由策略。规则无法确定时走 QualityChatAgent 兜底。"""

    def _has_quality_signal(self, query: str) -> bool:
        return any(p.search(query) for p in QUALITY_QA_PATTERNS)

    def _has_general_rag_signal(self, query: str) -> bool:
        return any(p.search(query) for p in GENERAL_RAG_PATTERNS)

    def _has_selected_rag_space(self, ext: dict) -> bool:
        rag = ext.get("selected_rag_space") or {}
        return bool(rag.get("id"))

    def _is_ambiguous(self, query: str) -> bool:
        """检测模糊输入：短句、代词多、无明确信号"""
        if not query or len(query) < 4:
            return True
        ambiguous_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in [
                r"^(这个|那个|它|他|她)$",
                r"^(看看|帮我看看|看一下|处理一下|怎么办|有问题吗|能不能过)$",
                r"^(这个|那个).{0,3}(呢|吗|吧|啊)?$",
            ]
        ]
        return any(p.search(query.strip()) for p in ambiguous_patterns)

    def decide(self, input_data: AgentRouterInput) -> AgentRouteDecision:
        query = str(input_data.query or "").strip()
        attachments = list(input_data.attachments or [])
        image_urls = list(input_data.image_urls or [])
        ext = dict(input_data.ext or {})
        route_hints = {
            **dict(input_data.route_hints or {}),
            **dict(ext.get("route_hints") or {}),
        }

        # ── Manual override: force_agent ──
        if route_hints.get("force_agent") == "inspection_task":
            forced_sub = route_hints.get("force_sub_route") or "task_create"
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route=forced_sub,
                intent=forced_sub,
                reason="前端强制指定检测 Agent",
                route_source="manual",
            )
        if route_hints.get("force_agent") in {"chat", "quality_chat"}:
            forced_sub = route_hints.get("force_sub_route") or "general_chat"
            return AgentRouteDecision(
                selected_agent="chat",
                sub_route=forced_sub,
                intent=forced_sub,
                reason="前端强制指定聊天 Agent",
                route_source="manual",
            )

        # ── Attachment type detection ──
        has_structured_file = False
        has_image_attachment = False
        for item in attachments:
            name = str(item.get("name") or "").lower()
            suffix = name.rsplit(".", 1)[-1] if "." in name else ""
            if suffix in STRUCTURED_FILE_EXTENSIONS:
                has_structured_file = True
            if suffix in IMAGE_EXTENSIONS or item.get("kind") == "image":
                has_image_attachment = True

        has_task_signal = any(p.search(query) for p in TASK_INTENT_PATTERNS)
        has_quality_signal = self._has_quality_signal(query)
        has_rag_space = self._has_selected_rag_space(ext)
        has_rag_signal = self._has_general_rag_signal(query)
        is_ambiguous = self._is_ambiguous(query)

        # 1. 结构化文件 + 检测意图 → inspection_execute
        if has_structured_file and (has_task_signal or has_quality_signal):
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="inspection_execute",
                intent="inspection_execute",
                reason="结构化文件 + 检测意图",
                route_source="rule",
            )

        # 2. 图片 + 检测意图 → inspection_execute
        if (has_image_attachment or image_urls) and (has_task_signal or has_quality_signal):
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="inspection_execute",
                intent="inspection_execute",
                reason="图片 + 检测意图",
                route_source="rule",
            )

        # 3. 明确任务创建意图 → task_create
        if has_task_signal and not has_quality_signal:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="task_create",
                intent="task_create",
                reason="检测到任务创建意图关键词",
                route_source="rule",
            )

        # 4. 质检问答语义 → quality_qa
        if has_quality_signal:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="quality_qa",
                intent="quality_qa",
                reason="检测到质检问答语义",
                route_source="rule",
            )

        # 5. 选中RAG空间 或 明确知识库意图 → chat.rag_qa
        if has_rag_space or has_rag_signal:
            return AgentRouteDecision(
                selected_agent="chat",
                sub_route="rag_qa",
                intent="rag_qa",
                reason="选中知识库或知识库问答意图",
                route_source="rule",
            )

        # 6. 模糊输入 → 标记需要模型分类
        if is_ambiguous:
            return AgentRouteDecision(
                selected_agent="chat",
                sub_route="general_chat",
                intent="general_chat",
                confidence=0.5,
                reason="模糊输入，建议模型兜底分类",
                route_source="rule",
                fallback_agent="model_classifier",
            )

        # 7. 默认 → chat.general_chat
        return AgentRouteDecision(
            selected_agent="chat",
            sub_route="general_chat",
            intent="general_chat",
            confidence=0.85,
            reason="默认普通聊天",
            route_source="rule",
        )

    async def decide_with_model(
        self,
        input_data: AgentRouterInput,
        llm_client=None,
    ) -> AgentRouteDecision:
        decision = self.decide(input_data)
        if decision.fallback_agent == "model_classifier" and llm_client is not None:
            from agent.router.model_classifier import ModelClassifier
            classifier = ModelClassifier()
            return await classifier.classify(
                query=input_data.query,
                llm_client=llm_client,
                ext=input_data.ext,
            )
        return decision
