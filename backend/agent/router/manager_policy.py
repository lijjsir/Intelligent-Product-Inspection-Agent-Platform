from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.capability_registry import CAPABILITIES, SURFACE_MODE_POLICY, capabilities_for_surface
from agent.router.contracts import AgentPlanStep, AgentRoutePlan
from agent.router.manager_state import ManagerState
from agent.router.node_registry import attachment_kind


TASK_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"(创建|新建|发起|提交|开始|启动|执行).{0,12}(任务|检测|质检)",
        r"(正式).{0,8}(检测|质检|任务)",
        r"quality inspection|inspection task|start inspection",
    ]
]
REPORT_PATTERNS = [re.compile(pattern, re.I) for pattern in [r"报告|上次检测|检测结果|失败原因|任务状态|status|report"]]
SUMMARY_PATTERNS = [re.compile(pattern, re.I) for pattern in [r"总结|概括|摘要|summary"]]
PAPER_FORMAT_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"查非",
        r"论文.{0,6}(格式|排版|模板|规范).{0,4}(检查|检测|审查|审阅)",
        r"(格式|排版|模板).{0,4}(检查|检测|审查|审阅)",
        r"错别字|病句|标点错误|格式错误|标点符号",
        r"paper format|format check|proofread",
    ]
]
RAG_PATTERNS = [re.compile(pattern, re.I) for pattern in [r"知识库|RAG|根据.{0,8}(资料|文档|知识库|标准)|AQL|标准"]]
DATA_PATTERNS = [re.compile(pattern, re.I) for pattern in [r"数据分析|统计|趋势|分析数据|报表分析"]]
RAG_INGEST_PATTERNS = [re.compile(pattern, re.I) for pattern in [r"(加入|写入|导入|入库).{0,8}(知识库|RAG)|rag ingest|ingest"]]

TASK_ID_PATTERN = re.compile(r"(?:任务|task)\s*(?:id|编号|号)?\s*[:：]?\s*([A-Za-z0-9\-_]{4,36})", re.I)
PRODUCT_ID_PATTERN = re.compile(r"(?:产品|product)\s*(?:id|编号|号)?\s*[:：]?\s*([A-Za-z0-9\-_]{2,36})", re.I)
TIME_RANGE_PATTERNS = [
    (re.compile(p, re.I), label)
    for p, label in [
        (r"最近|最新|latest|recent", "latest"),
        (r"今天|today", "today"),
        (r"昨天|昨天|yesterday", "yesterday"),
        (r"本周|这周|this week", "this_week"),
        (r"上周|last week", "last_week"),
    ]
]


@dataclass
class Understanding:
    goal: str
    intent: str
    needs: list[str]
    missing_inputs: list[str]
    entities: dict[str, Any]
    risk: str = "low"


class ManagerPolicy:

    @staticmethod
    def get_intents() -> list[dict[str, Any]]:
        """Return the intent-understanding rules in priority order (mirrors understand())."""
        return [
            {
                "priority": 1,
                "name": "RAG 入库请求",
                "condition": "命中 RAG_INGEST_PATTERNS（加入/写入/导入知识库）",
                "intent": "rag_ingest",
                "target_agent": "chat",
                "needs": ["rag.ingest"],
                "risk": "high",
                "stop_on_match": True,
                "description": "请求把文件写入 RAG 空间，需要显式确认且不能在聊天页直接执行",
            },
            {
                "priority": 2,
                "name": "聊天页任务意图拦截",
                "condition": "surface=chat 且命中 TASK_PATTERNS（创建/发起任务等）",
                "intent": "action_blocked",
                "target_agent": "chat",
                "needs": ["chat.response.compose"],
                "risk": "medium",
                "stop_on_match": True,
                "description": "阻止聊天页正式业务动作，提示用户前往质量检测任务页面",
            },
            {
                "priority": 3,
                "name": "检测页任务执行",
                "condition": "surface=quality_task 且命中 TASK_PATTERNS",
                "intent": "inspection_execute",
                "target_agent": "inspection_task",
                "needs": ["quality.inspection.execute"],
                "risk": "high",
                "stop_on_match": True,
                "description": "正式执行质量检测任务（需确认 action_intent）",
            },
            {
                "priority": 4,
                "name": "图片理解",
                "condition": "附件包含 image 类型",
                "intent": "image_understanding",
                "target_agent": "inspection_task",
                "needs": ["image.understanding", "chat.response.compose"],
                "risk": "low",
                "stop_on_match": True,
                "description": "对图片进行非正式理解和初步判断（非正式检测）",
            },
            {
                "priority": 5,
                "name": "论文查非/格式检查",
                "condition": "附件包含 document 且命中 PAPER_FORMAT_PATTERNS",
                "intent": "paper_format_check",
                "target_agent": "chat",
                "needs": ["file.paper_format_check", "chat.response.compose"],
                "risk": "low",
                "stop_on_match": True,
                "description": "对论文文档执行结构、格式、文字规范检查",
            },
            {
                "priority": 6,
                "name": "文档/文件处理",
                "condition": "附件包含 document 或 structured_file 类型",
                "intent": "file_summary / file_qa",
                "target_agent": "chat",
                "needs": ["file.summary", "chat.response.compose"],
                "risk": "low",
                "stop_on_match": True,
                "description": "处理聊天上传文件：命中 SUMMARY_PATTERNS 则总结，否则文件问答",
            },
            {
                "priority": 7,
                "name": "报告/任务状态查询",
                "condition": "命中 REPORT_PATTERNS（报告/上次检测/检测结果/任务状态等）",
                "intent": "quality_report_query",
                "target_agent": "inspection_task",
                "needs": ["quality.report.query", "chat.response.compose"],
                "risk": "low",
                "stop_on_match": True,
                "description": "只读查询质量检测报告或任务状态",
            },
            {
                "priority": 8,
                "name": "RAG 知识库问答",
                "condition": "已选择 RAG 空间，或命中 RAG_PATTERNS（知识库/RAG/根据资料/AQL/标准等）",
                "intent": "rag_qa",
                "target_agent": "chat",
                "needs": ["rag.retrieve", "chat.response.compose"],
                "risk": "low",
                "stop_on_match": True,
                "description": "基于可用知识源检索证据并回答",
            },
            {
                "priority": 9,
                "name": "数据分析",
                "condition": "命中 DATA_PATTERNS（数据分析/统计/趋势等）",
                "intent": "data_analysis",
                "target_agent": "chat",
                "needs": ["data.analysis", "chat.response.compose"],
                "risk": "low",
                "stop_on_match": True,
                "description": "预留数据分析 Agent 只读分析能力",
            },
            {
                "priority": 10,
                "name": "默认普通聊天",
                "condition": "未命中以上所有规则",
                "intent": "general_chat",
                "target_agent": "chat",
                "needs": ["chat.general"],
                "risk": "low",
                "stop_on_match": True,
                "description": "回答普通聊天问题，无特殊能力需求",
            },
        ]

    def initialize_state(self, request: NormalizedRequest) -> ManagerState:
        ext = dict(request.ext or {})
        surface = self._surface(request)
        surface_policy = SURFACE_MODE_POLICY.get(surface, SURFACE_MODE_POLICY["chat"])
        allowed_modes = list(ext.get("allowed_modes") or surface_policy["allowed_modes"])
        forbidden_modes = list(ext.get("forbidden_modes") or surface_policy.get("forbidden_modes") or [])
        budget = self._budget_for_surface(surface)
        return ManagerState(
            request_id=request.request_id,
            workflow_run_id=request.workflow_run_id or request.request_id,
            surface=surface,
            original_query=request.query,
            normalized_query=self._clean(request.query),
            org_id=request.org_id,
            user_id=request.user_id,
            session_id=request.session_id,
            assistant_message_id=request.assistant_message_id,
            attachments=[item.model_dump() for item in request.attachments],
            history_messages=list(ext.get("history_messages") or []),
            inspection_context=dict(ext.get("inspection_context") or {}) or None,
            selected_rag_space=self._selected_rag_space(ext),
            rag_scope=dict(ext.get("rag_scope") or {}) or None,
            force_web_search=bool(ext.get("force_web_search")),
            template_id=str(ext.get("template_id") or "") or None,
            allowed_modes=allowed_modes,
            forbidden_modes=forbidden_modes,
            action_intent=str(ext.get("action_intent") or "") or None,
            **budget,
        )

    async def understand(self, state: ManagerState) -> Understanding:
        query = state.normalized_query
        attachment_kinds = [attachment_kind(item) for item in state.attachments]

        if self._matches(query, RAG_INGEST_PATTERNS):
            return Understanding(
                goal="请求把文件写入 RAG 空间，需要显式确认且不能在聊天页直接执行",
                intent="rag_ingest",
                needs=["rag.ingest"],
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
                risk="high",
            )
        if state.surface == "chat" and self._has_task_intent(query):
            return Understanding(
                goal="阻止聊天页正式业务动作，并提示用户前往质量检测任务页面",
                intent="action_blocked",
                needs=["chat.response.compose"],
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
                risk="medium",
            )
        if state.surface == "quality_task" and self._has_task_intent(query):
            missing = []
            if not state.action_intent:
                missing.append("action_intent")
            return Understanding(
                goal="正式执行质量检测任务",
                intent="inspection_execute",
                needs=["quality.inspection.execute"],
                missing_inputs=missing,
                entities=self._extract_entities(query, state.attachments),
                risk="high",
            )
        if "image" in attachment_kinds:
            return Understanding(
                goal="对图片进行非正式理解和初步判断",
                intent="image_understanding",
                needs=self._with_forced_web_search(["image.understanding", "chat.response.compose"], state),
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
            )
        if any(kind == "document" for kind in attachment_kinds) and self._matches(query, PAPER_FORMAT_PATTERNS):
            return Understanding(
                goal="检查论文文档的格式、结构和文字规范问题",
                intent="paper_format_check",
                needs=self._with_forced_web_search(["file.paper_format_check", "chat.response.compose"], state),
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
            )
        if any(kind in {"document", "structured_file"} for kind in attachment_kinds):
            capability = "file.summary" if self._matches(query, SUMMARY_PATTERNS) else "file.qa"
            return Understanding(
                goal="处理聊天上传文件并返回辅助分析",
                intent=capability.replace(".", "_"),
                needs=self._with_forced_web_search([capability, "chat.response.compose"], state),
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
            )
        if self._matches(query, REPORT_PATTERNS):
            capability = "quality.task.status" if "状态" in query or "status" in query.lower() else "quality.report.query"
            return Understanding(
                goal="只读查询质量检测报告或任务状态",
                intent=capability.replace(".", "_"),
                needs=self._with_forced_web_search([capability, "chat.response.compose"], state),
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
            )
        if state.selected_rag_space or self._matches(query, RAG_PATTERNS):
            return Understanding(
                goal="基于可用知识源检索证据并回答",
                intent="rag_qa",
                needs=self._with_forced_web_search(["rag.retrieve", "chat.response.compose"], state),
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
            )
        if self._matches(query, DATA_PATTERNS):
            return Understanding(
                goal="预留数据分析 Agent 只读分析能力",
                intent="data_analysis",
                needs=self._with_forced_web_search(["data.analysis", "chat.response.compose"], state),
                missing_inputs=[],
                entities=self._extract_entities(query, state.attachments),
            )
        return Understanding(
            goal="回答普通聊天问题",
            intent="general_chat",
            needs=self._with_forced_web_search(["chat.general"], state),
            missing_inputs=[],
            entities={},
        )

    @staticmethod
    def _with_forced_web_search(needs: list[str], state: ManagerState) -> list[str]:
        if not state.force_web_search:
            return needs
        if "web.search" in needs:
            return needs
        if "chat.response.compose" in needs:
            compose_index = needs.index("chat.response.compose")
            return [*needs[:compose_index], "web.search", *needs[compose_index:]]
        if needs == ["chat.general"]:
            return ["web.search", "chat.response.compose"]
        return [*needs, "web.search", "chat.response.compose"]

    _SUCCESS_CRITERIA: dict[str, list[str]] = {
        "rag.retrieve": ["hit_count > 0", "top_score meets threshold"],
        "rag.ingest": ["confirmed by user", "documents indexed"],
        "file.summary": ["parsed_text is not empty", "summary is not empty"],
        "file.qa": ["parsed_text is not empty", "answer references file content"],
        "file.paper_format_check": ["paper issues are structured", "summary explains key findings"],
        "image.understanding": ["vision_result is not empty", "informal disclaimer present"],
        "quality.report.query": ["found related report", "verdict is not empty", "can explain conclusion"],
        "quality.task.status": ["task_id resolved", "status returned"],
        "quality.inspection.execute": ["task_id is not empty", "status in queued/running/done"],
        "chat.general": ["generate non-empty answer"],
        "chat.response.compose": ["answer includes citations where applicable", "ui_schema is set"],
        "data.analysis": ["analysis_result is not empty"],
    }

    async def plan(self, state: ManagerState, understanding: Understanding) -> AgentRoutePlan:
        state.goal = understanding.goal
        state.missing_inputs = list(understanding.missing_inputs)
        available = capabilities_for_surface(state.surface, state.allowed_modes)
        steps: list[AgentPlanStep] = []
        previous_step_id: str | None = None
        for index, key in enumerate(understanding.needs, start=1):
            capability = available.get(key) or CAPABILITIES.get(key)
            if capability is None:
                continue
            step_id = f"s{index}"
            depends_on = [previous_step_id] if previous_step_id and capability.agent == "chat" else []
            steps.append(
                AgentPlanStep(
                    step_id=step_id,
                    capability_key=key,
                    agent=capability.agent,
                    operation=capability.operation,
                    mode=capability.mode,
                    input=self._step_input(key, state),
                    depends_on=[item for item in depends_on if item],
                )
            )
            previous_step_id = step_id
        return AgentRoutePlan(
            plan_id=f"plan_{state.workflow_run_id}_{state.iteration + 1}",
            surface=state.surface,
            goal=understanding.goal,
            steps=steps,
            success_criteria=self._resolve_criteria(understanding.needs, understanding.goal),
            confidence=0.9 if understanding.risk == "low" else 0.7,
            reason=understanding.intent,
            max_iterations=state.max_iterations,
        )

    @classmethod
    def _resolve_criteria(cls, needs: list[str], goal: str) -> list[str]:
        criteria: list[str] = []
        for key in needs:
            specific = cls._SUCCESS_CRITERIA.get(key)
            if specific:
                criteria.extend(specific)
        return criteria or [goal]

    def _surface(self, request: NormalizedRequest) -> str:
        ext = dict(request.ext or {})
        surface = str(ext.get("surface") or "").strip()
        if surface:
            return surface
        if request.workspace == "quality_task" or request.request_kind == "task":
            return "quality_task"
        return "chat"

    @staticmethod
    def _budget_for_surface(surface: str) -> dict[str, int]:
        if surface == "quality_task":
            return {"max_iterations": 5, "max_tool_calls": 8, "max_llm_calls": 5, "timeout_ms": 60000}
        return {"max_iterations": 2, "max_tool_calls": 3, "max_llm_calls": 2, "timeout_ms": 30000}

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _matches(query: str, patterns: list[re.Pattern[str]]) -> bool:
        return any(pattern.search(query) for pattern in patterns)

    def _has_task_intent(self, query: str) -> bool:
        return self._matches(query, TASK_PATTERNS)

    @staticmethod
    def _selected_rag_space(ext: dict[str, Any]) -> dict[str, Any] | None:
        selected = ext.get("selected_rag_space")
        if isinstance(selected, dict) and selected.get("id"):
            return selected
        rag_scope = ext.get("rag_scope")
        if isinstance(rag_scope, dict) and rag_scope.get("rag_space_id"):
            return {"id": str(rag_scope["rag_space_id"]), "name": str(rag_scope.get("rag_space_name") or "")}
        rag_space_id = str(ext.get("selected_rag_space_id") or "").strip()
        if rag_space_id:
            return {"id": rag_space_id, "name": str(ext.get("selected_rag_space_name") or "")}
        return None

    @staticmethod
    def _extract_entities(query: str, attachments: list[dict[str, Any]]) -> dict[str, Any]:
        entities: dict[str, Any] = {}
        attachment_ids = [item.get("id") for item in attachments if item.get("id")]
        if attachment_ids:
            entities["attachment_ids"] = attachment_ids
        match = TASK_ID_PATTERN.search(query)
        if match:
            entities["task_id"] = match.group(1).strip()
        match = PRODUCT_ID_PATTERN.search(query)
        if match:
            entities["product_id"] = match.group(1).strip()
        for pattern, label in TIME_RANGE_PATTERNS:
            if pattern.search(query):
                entities["time_range"] = label
                break
        if "失败" in query or "失败原因" in query or "failed" in query.lower():
            entities["focus"] = "failures"
        return entities

    @staticmethod
    def _step_input(key: str, state: ManagerState) -> dict[str, Any]:
        if key == "rag.retrieve":
            return {
                "query": state.original_query,
                "selected_rag_space": state.selected_rag_space,
                "rag_scope": state.rag_scope,
            }
        if key.startswith("file."):
            return {
                "attachments": state.attachments,
                "query": state.original_query,
                "template_id": state.template_id or str((state.inspection_context or {}).get("template_id") or "") or None,
            }
        if key == "image.understanding":
            return {"attachments": state.attachments, "query": state.original_query}
        if key == "quality.inspection.execute":
            return {"query": state.original_query, "attachments": state.attachments}
        return {"query": state.original_query}
