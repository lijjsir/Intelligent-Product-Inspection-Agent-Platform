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
        r"(检测|质检).{0,6}(图片|照片|图|文件|这个|这份)",
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
        r"总结|概括|归纳.{0,4}(文档|知识库|资料|文件|这份)",
        r"(文档|知识库|资料|文件).{0,4}(说什么|讲什么|讲|内容|主要|什么)",
        r"根据.{0,4}(文档|知识库|资料|文件|选中)",
        r"(查|找|搜索).{0,4}(文档|知识库|文件)",
        r"知识库|参考资料|参考文档|参考文件",
    ]
]


class AgentRoutePolicy:
    """Rule-based route policy. Ambiguous inputs can fall back to the model classifier."""

    # ── Introspection API (keep in sync with decide() below) ──

    @staticmethod
    def get_signals() -> list[dict[str, Any]]:
        """Return metadata for every signal the engine detects."""
        return [
            {
                "key": "has_task_keyword",
                "label": "任务意图关键词",
                "description": "检测文本中的任务创建意图关键词（创建任务、新建任务、发起检测、提交任务等），驱动规则 1/2/4。",
                "source_stage": "route_signal_builder",
            },
            {
                "key": "has_images",
                "label": "图片附件",
                "description": "检测请求中的图片附件（.png/.jpg/.jpeg/.webp/.gif）或图片 URL，驱动规则 2/3。",
                "source_stage": "route_signal_builder",
            },
            {
                "key": "has_structured_file",
                "label": "结构化文件",
                "description": "检测非图片文件（xlsx/csv/json/txt/docx/jsonl/md），驱动规则 1。",
                "source_stage": "route_signal_builder",
            },
            {
                "key": "has_quality_signal",
                "label": "质检语义",
                "description": "检测质量/质检/缺陷/合格/标准/划痕/瑕疵等语义关键词，驱动规则 1/3/5。",
                "source_stage": "route_signal_builder",
            },
            {
                "key": "has_rag_signal",
                "label": "知识库检索意图",
                "description": "检测知识库检索意图（总结文档、搜索知识库、根据文档回答等），驱动规则 6。",
                "source_stage": "route_signal_builder",
            },
            {
                "key": "has_rag_space",
                "label": "RAG 空间已选",
                "description": "用户显式选择了 RAG 知识空间，驱动规则 6。",
                "source_stage": "route_signal_builder",
            },
            {
                "key": "is_ambiguous",
                "label": "模糊输入",
                "description": "检测短句（<4 字）、代词为主、无明确意图信号的输入，触发规则 7 模型兜底。",
                "source_stage": "route_signal_builder",
            },
        ]

    @staticmethod
    def get_rules() -> list[dict[str, Any]]:
        """Return the structured auto-routing rule definitions in priority order (mirrors decide())."""
        return [
            {
                "priority": 1,
                "name": "结构化文件 + 检测意图",
                "condition_summary": "xlsx/csv/json/txt/docx/jsonl/md 文件 + 任务/质检信号",
                "target_agent": "inspection_task",
                "target_sub_route": "inspection_execute",
                "route_source": "rule",
                "examples": ["上传 Excel + 创建检测任务", "csv 文件 + 质量检测"],
                "stop_on_match": True,
            },
            {
                "priority": 2,
                "name": "图片 + 任务创建意图",
                "condition_summary": "图片附件/URL + 任务意图关键词信号",
                "target_agent": "inspection_task",
                "target_sub_route": "task_create",
                "route_source": "rule",
                "examples": ["图片 + 帮我检测", "图片 + 创建任务"],
                "stop_on_match": True,
            },
            {
                "priority": 3,
                "name": "图片 + 质检问答",
                "condition_summary": "图片附件/URL + 质检语义信号",
                "target_agent": "inspection_task",
                "target_sub_route": "quality_qa",
                "route_source": "rule",
                "examples": ["图片 + 这个算不算缺陷", "图片 + 质量判定问题"],
                "stop_on_match": True,
            },
            {
                "priority": 4,
                "name": "任务创建意图（纯文本）",
                "condition_summary": "任务意图关键词信号存在，无质检语义",
                "target_agent": "inspection_task",
                "target_sub_route": "task_create",
                "route_source": "rule",
                "examples": ["创建任务", "帮我检测这个产品"],
                "stop_on_match": True,
            },
            {
                "priority": 5,
                "name": "质检问答意图（纯文本）",
                "condition_summary": "质检语义信号存在",
                "target_agent": "inspection_task",
                "target_sub_route": "quality_qa",
                "route_source": "rule",
                "examples": ["这个算不算缺陷", "按照 GB/T 标准判定"],
                "stop_on_match": True,
            },
            {
                "priority": 6,
                "name": "RAG 知识库问答",
                "condition_summary": "RAG 空间已选 或 知识库检索意图信号",
                "target_agent": "chat",
                "target_sub_route": "rag_qa",
                "route_source": "rule",
                "examples": ["根据知识库回答", "查一下文档里的标准"],
                "stop_on_match": True,
            },
            {
                "priority": 7,
                "name": "模糊输入兜底",
                "condition_summary": "短句/代词/无法明确分类的输入",
                "target_agent": "chat",
                "target_sub_route": "general_chat",
                "route_source": "rule",
                "examples": ["这个呢", "看看"],
                "stop_on_match": True,
            },
            {
                "priority": 8,
                "name": "默认普通聊天",
                "condition_summary": "未命中以上所有规则",
                "target_agent": "chat",
                "target_sub_route": "general_chat",
                "route_source": "rule",
                "examples": ["你好", "今天天气怎么样"],
                "stop_on_match": True,
            },
        ]

    @staticmethod
    def get_agents() -> list[dict[str, Any]]:
        """Return the agents the engine dispatches to."""
        return [
            {
                "key": "chat",
                "label": "Quality Chat",
                "sub_routes": ["general_chat", "rag_qa"],
            },
            {
                "key": "inspection_task",
                "label": "Inspection Task Agent",
                "sub_routes": ["task_create", "inspection_execute", "quality_qa"],
            },
        ]

    @staticmethod
    def get_rule_for_decision(selected_agent: str, sub_route: str, route_source: str = "rule", fallback_agent: str = "") -> tuple[str, int]:
        """Map a routing decision back to the rule name and priority that produced it."""
        rules = AgentRoutePolicy.get_rules()
        for rule in rules:
            if rule["target_agent"] != selected_agent:
                continue
            if rule["route_source"] != route_source:
                continue
            target_sub = rule["target_sub_route"]
            if target_sub == sub_route:
                # Distinguish ambiguous fallback (rule 7) from default (rule 8) for chat/general_chat
                if sub_route == "general_chat" and selected_agent == "chat":
                    if fallback_agent == "model_classifier":
                        if "模糊" in rule["name"] or "Ambiguous" in rule["name"]:
                            return (rule["name"], rule["priority"])
                        continue
                    else:
                        if "默认" in rule["name"] or "Default" in rule["name"]:
                            return (rule["name"], rule["priority"])
                        continue
                return (rule["name"], rule["priority"])
        # fallback: match on sub_route only
        for rule in rules:
            if rule["target_sub_route"] == sub_route:
                return (rule["name"], rule["priority"])
        return ("Unknown rule", 0)

    # ── Private signal detectors ──

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

    def detect_signals(self, input_data: AgentRouterInput) -> dict[str, bool]:
        """Detect all signals for a given input (mirrors the pre-routing logic in decide())."""
        query = str(input_data.query or "").strip()
        attachments = list(input_data.attachments or [])
        image_urls = list(input_data.image_urls or [])
        ext = dict(input_data.ext or {})

        has_structured_file = False
        has_image_attachment = False
        for item in attachments:
            name = str(item.get("name") or "").lower()
            suffix = name.rsplit(".", 1)[-1] if "." in name else ""
            if suffix in STRUCTURED_FILE_EXTENSIONS:
                has_structured_file = True
            if suffix in IMAGE_EXTENSIONS or item.get("kind") == "image":
                has_image_attachment = True

        return {
            "has_task_keyword": any(p.search(query) for p in TASK_INTENT_PATTERNS),
            "has_images": bool(has_image_attachment or image_urls),
            "has_structured_file": has_structured_file,
            "has_quality_signal": self._has_quality_signal(query),
            "has_rag_signal": self._has_general_rag_signal(query),
            "has_rag_space": self._has_selected_rag_space(ext),
            "is_ambiguous": self._is_ambiguous(query),
        }

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
        if route_hints.get("force_agent") == "inspection_task" and route_hints.get("force_sub_route"):
            forced_sub = route_hints.get("force_sub_route")
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route=forced_sub,
                intent=forced_sub,
                reason="前端强制指定检测 Agent",
                route_source="manual",
            )
        if route_hints.get("force_agent") == "chat":
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

        if route_hints.get("force_agent") == "inspection_task":
            forced_sub_route = "quality_qa" if has_quality_signal and not has_task_signal else "task_create"
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route=forced_sub_route,
                intent=forced_sub_route,
                reason="front-end selected inspection workspace; policy kept confirmation gate",
                route_source="manual",
            )

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
        if (has_image_attachment or image_urls) and has_task_signal:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="task_create",
                intent="task_create",
                reason="图片 + 检测意图",
                route_source="rule",
            )

        # 3. 明确任务创建意图 → task_create
        if (has_image_attachment or image_urls) and has_quality_signal:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="quality_qa",
                intent="quality_qa",
                reason="image plus quality question; answer before formal task submission",
                route_source="rule",
            )

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
