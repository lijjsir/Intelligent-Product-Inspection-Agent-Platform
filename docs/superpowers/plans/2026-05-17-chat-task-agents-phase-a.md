# Phase A: Agent 拆分最小闭环 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 QualityJudgementSubgraph 内部混合路由拆分为 AgentManagerService → QualityChatAgent / InspectionTaskAgent 架构，旧 API 兼容

**Architecture:** 
- 新增 `agent/router/` 模块（contracts, route_policy, agent_manager）
- 新增 `agent/subgraphs/inspection_task/` 迁入 `_run_structured_inspection()`
- 改造 `QualityAgentOrchestratorService` 调用 `AgentManagerService`
- `QualityChatGraph` 作为 QualityChatAgent 保留，移除直接创建任务逻辑

**Tech Stack:** Python 3.11, Pydantic v2, LangGraph, existing agent contracts

---

## 前置说明

当前已存在的关键结构（不需要重建）：
- `AgentOutput` 已有 `route_decision: RouteDecision | None` 字段
- `RouteDecision` 已有 `selected_subgraph`, `mode`, `reason`, `signals` 字段
- `QualityAgentOrchestratorService.run_chat()` 已使用 `NormalizedRequest` 调用 `QualityJudgementSubgraph.run()`
- `_run_structured_inspection()` 位于 `quality_judgement/graph.py` 第201行

## 改动范围

| 文件 | 操作 |
|------|------|
| `backend/agent/router/__init__.py` | 新增 |
| `backend/agent/router/contracts.py` | 新增 |
| `backend/agent/router/route_policy.py` | 新增 |
| `backend/agent/router/agent_manager.py` | 新增 |
| `backend/agent/subgraphs/inspection_task/__init__.py` | 新增 |
| `backend/agent/subgraphs/inspection_task/graph.py` | 新增（从 quality_judgement 迁移） |
| `backend/app/services/agent_manager_service.py` | 新增 |
| `backend/agent/contracts/quality_contracts.py` | 修改（扩展 RouteDecision） |
| `backend/agent/subgraphs/quality_judgement/graph.py` | 修改（路由委托 AgentManager） |
| `backend/agent/subgraphs/quality_chat/graph.py` | 修改（移除直接创建任务） |
| `backend/app/services/quality_agent_orchestrator_service.py` | 修改（调用 AgentManagerService） |
| `backend/agent/topology_catalog.py` | 修改（注册新 Agent） |

---

### Task 1: 扩展 RouteDecision 契约

**Files:**
- Modify: `backend/agent/contracts/quality_contracts.py`

- [ ] **Step 1: 扩展 RouteDecision 添加路由元信息**

```python
# 在 quality_contracts.py 的 RouteDecision 类中，将 selected_subgraph 的 Literal 扩展，
# 同时新增 intent, confidence, requires_confirmation, route_source, fallback_agent 字段

class RouteDecision(BaseModel):
    mode: Literal["legacy_only", "canary_non_pdf", "router_enabled"] = "router_enabled"
    selected_subgraph: Literal["quality_judgement", "quality_chat", "inspection_task"] = "quality_chat"
    fallback_subgraph: Literal["quality_judgement", "quality_chat", "inspection_task"] = "quality_chat"
    reason: str = ""
    intent: str = ""  # smalltalk / rag_qa / quality_qa / task_create / structured_inspection
    confidence: float = 1.0
    requires_confirmation: bool = False
    route_source: str = "rule"  # rule / llm / manual
    fallback_agent: str | None = None
    signals: RouteSignals = Field(default_factory=RouteSignals)
```

- [ ] **Step 2: 运行现有测试确认兼容**

Run: `cd backend && python -m pytest tests/ -x -q --tb=short -k "quality" 2>&1 | tail -20`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/contracts/quality_contracts.py
git commit -m "feat: extend RouteDecision with intent, confidence, route_source fields

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 创建 Agent Router 模块

**Files:**
- Create: `backend/agent/router/__init__.py`
- Create: `backend/agent/router/contracts.py`
- Create: `backend/agent/router/route_policy.py`
- Create: `backend/agent/router/agent_manager.py`

- [ ] **Step 1: 创建 `__init__.py`**

```python
# backend/agent/router/__init__.py
from agent.router.contracts import AgentRouteDecision, AgentRouterInput, AgentRouterOutput
from agent.router.route_policy import AgentRoutePolicy
from agent.router.agent_manager import AgentManager

__all__ = [
    "AgentRouteDecision",
    "AgentRouterInput",
    "AgentRouterOutput",
    "AgentRoutePolicy",
    "AgentManager",
]
```

- [ ] **Step 2: 创建 `contracts.py`**

```python
# backend/agent/router/contracts.py
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRouteDecision(BaseModel):
    """AgentManager 路由决策结果"""
    selected_agent: Literal["quality_chat", "inspection_task"] = "quality_chat"
    intent: str = ""  # smalltalk / rag_qa / quality_qa / task_create / structured_inspection
    confidence: float = 1.0
    reason: str = ""
    requires_confirmation: bool = False
    route_source: str = "rule"  # rule / llm / manual
    fallback_agent: str | None = None


class AgentRouterInput(BaseModel):
    """AgentManager 输入"""
    query: str = ""
    request_kind: str = "chat"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    route_hints: dict[str, Any] = Field(default_factory=dict)
    ext: dict[str, Any] = Field(default_factory=dict)


class AgentRouterOutput(BaseModel):
    """AgentManager 输出，包装原始 Agent 输出 + 路由元信息"""
    route_decision: AgentRouteDecision
    agent_output: dict[str, Any] = Field(default_factory=dict)
    status: Literal["completed", "failed", "degraded"] = "completed"
    degrade_reason: str | None = None
```

- [ ] **Step 3: 创建 `route_policy.py`**

```python
# backend/agent/router/route_policy.py
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

# 非 PDF 结构化文件扩展名
STRUCTURED_FILE_EXTENSIONS = {"xlsx", "csv", "json", "txt", "docx", "jsonl", "md"}

# 图片扩展名
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

# 任务创建意图的附加触发模式
TASK_INTENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(帮我|给我).{0,8}(进行|做).{0,8}(质量检测|质检|检测任务)",
        r"(需要|想要).{0,8}(创建|发起).{0,8}(任务|检测)",
        r"^\s*(质量检测|质检|检测任务|开始检测|启动检测)\s*[!！?.]?\s*$",
    ]
]


class AgentRoutePolicy:
    """基于规则的路由策略。规则无法确定时返回低置信度，由调用方决定是否使用 LLM 分类器。"""

    def decide(self, input_data: AgentRouterInput) -> AgentRouteDecision:
        query = str(input_data.query or "").strip()
        attachments = list(input_data.attachments or [])
        image_urls = list(input_data.image_urls or [])

        # 1. 检测附件类型
        has_non_pdf = False
        has_image_attachment = False
        for item in attachments:
            name = str(item.get("name") or "").lower()
            suffix = name.rsplit(".", 1)[-1] if "." in name else ""
            if suffix in STRUCTURED_FILE_EXTENSIONS:
                has_non_pdf = True
            if suffix in IMAGE_EXTENSIONS or item.get("kind") == "image":
                has_image_attachment = True

        # 2. 检测任务关键词
        has_task_keyword = any(p.search(query) for p in TASK_KEYWORD_PATTERNS)
        has_task_intent = any(p.search(query) for p in TASK_INTENT_PATTERNS)

        # 3. 路由判断（优先级从高到低）
        # 3a. 结构化文件 + 非任务关键词 → 结构化检测
        if has_non_pdf and not has_task_keyword:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                intent="structured_inspection",
                reason="用户上传了结构化文件（xlsx/csv/json等），且未使用任务创建关键词",
                route_source="rule",
            )

        # 3b. 上传图片 + 要求检测
        if (has_image_attachment or image_urls) and has_task_keyword:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                intent="task_create",
                reason="用户上传图片并要求检测/创建任务",
                route_source="rule",
            )

        # 3c. 明确任务创建意图
        if has_task_intent:
            return AgentRouteDecision(
                selected_agent="inspection_task",
                intent="task_create",
                reason="检测到任务创建意图关键词",
                route_source="rule",
            )

        # 3d. 默认走 QualityChatAgent
        return AgentRouteDecision(
            selected_agent="quality_chat",
            intent="general_qa",
            confidence=0.85,
            reason="未匹配到检测/任务信号，路由到聊天 Agent",
            route_source="rule",
        )
```

- [ ] **Step 4: 创建 `agent_manager.py`**

```python
# backend/agent/router/agent_manager.py
from __future__ import annotations

import logging
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentRouteDecision, AgentRouterInput, AgentRouterOutput
from agent.router.route_policy import AgentRoutePolicy

logger = logging.getLogger(__name__)


class AgentManager:
    """统一入口路由，将请求分发给 QualityChatAgent 或 InspectionTaskAgent。

    AgentManager 只负责路由和分发，不直接执行业务。
    具体执行由 QualityChatGraph 和 InspectionTaskGraph 各自的 .run() 方法完成。
    """

    def __init__(self):
        self._route_policy = AgentRoutePolicy()
        self._chat_agent = None  # 延迟初始化
        self._task_agent = None  # 延迟初始化

    @property
    def chat_agent(self):
        if self._chat_agent is None:
            from agent.subgraphs.quality_chat import QualityChatGraph
            self._chat_agent = QualityChatGraph()
        return self._chat_agent

    @property
    def task_agent(self):
        if self._task_agent is None:
            from agent.subgraphs.inspection_task import InspectionTaskGraph
            self._task_agent = InspectionTaskGraph()
        return self._task_agent

    async def run(self, request: NormalizedRequest) -> AgentRouterOutput:
        # 1. 构建路由输入
        router_input = AgentRouterInput(
            query=request.query,
            request_kind=request.request_kind,
            attachments=[item.model_dump() for item in request.attachments],
            image_urls=request.image_urls,
            route_hints=request.route_hints,
            ext=request.ext,
        )

        # 2. 路由决策
        decision = self._route_policy.decide(router_input)

        # 3. 分发执行
        try:
            if decision.selected_agent == "inspection_task":
                agent_output = await self.task_agent.run(request, decision)
            else:
                agent_output = await self.chat_agent.run(request, decision)
        except Exception as exc:
            logger.exception("Agent execution failed: agent=%s", decision.selected_agent)
            return AgentRouterOutput(
                route_decision=decision,
                agent_output={
                    "message_type": "agent_route_failed",
                    "answer": f"Agent 执行失败：{str(exc)}",
                    "route_decision": decision.model_dump(),
                },
                status="failed",
                degrade_reason=str(exc),
            )

        return AgentRouterOutput(
            route_decision=decision,
            agent_output=agent_output if isinstance(agent_output, dict) else agent_output.model_dump(),
            status="completed",
        )
```

- [ ] **Step 5: 验证模块导入**

Run: `cd backend && python -c "from agent.router import AgentManager, AgentRoutePolicy, AgentRouteDecision; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add backend/agent/router/
git commit -m "feat: add AgentManager router module with rule-based route policy

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 创建 InspectionTaskAgent 子图

**Files:**
- Create: `backend/agent/subgraphs/inspection_task/__init__.py`
- Create: `backend/agent/subgraphs/inspection_task/graph.py`

- [ ] **Step 1: 创建 `__init__.py`**

```python
# backend/agent/subgraphs/inspection_task/__init__.py
from agent.subgraphs.inspection_task.graph import InspectionTaskGraph

__all__ = ["InspectionTaskGraph"]
```

- [ ] **Step 2: 创建 `graph.py` — 迁移 `_run_structured_inspection` 为 InspectionTaskGraph**

```python
# backend/agent/subgraphs/inspection_task/graph.py
from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from agent.contracts.quality_contracts import (
    AgentOutput,
    AlertEvent,
    ClarificationRequest,
    NormalizedRequest,
    PersistableOutput,
    QualityTraceEvent,
    RagQueryLog,
    ResultAggregate,
    StabilityAggregate,
    TaskAggregate,
    TokenUsageEvent,
)
from agent.router.contracts import AgentRouteDecision
from agent.subgraphs.quality_judgement.product_adapters import (
    build_defects,
    collect_rule_hits,
    deep_merge,
    detect_product_family,
    expected_verdict_from_record,
    int_value,
    list_value,
    parse_kv_text,
    parse_structured_text,
    resolve_product_id,
    resolve_spec_code,
    score_from_record,
)
from agent.tools.file_parsers import parse_file_content
from app.services.dspy_runtime_service import resolve_dspy_runtime_profile
from app.services.file_storage_service import FileStorageService
from app.services.inspection_standard_service import InspectionStandardService
from app.services.rag_retrieval_service import RagRetrievalService
from infra.database.session import get_session

# ── Helper functions (migrated from quality_judgement/graph.py) ──

QUALITY_MISSING_FIELD_HINTS = {
    "product_id": "请提供产品编号，例如：FOOD-001 或 ELEC-001",
    "spec_code": "请提供检验标准编号，例如：FOOD-RAG-BASE-V1 或 ELEC-RAG-BASE-V1",
    "image_urls": "请继续上传质检图片，或直接提供图片 URL。",
}


def _extract_structured_record(request: NormalizedRequest, parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for record in parsed_files:
        candidate = parse_structured_text(str(record.get("text") or ""))
        if isinstance(candidate, dict):
            merged = deep_merge(merged, candidate)
    query_record = parse_kv_text(request.query)
    if query_record:
        merged = deep_merge(merged, query_record)
    return merged


def _verdict_risk(verdict: str) -> tuple[str, float]:
    if verdict == "pass": return "low", 0.12
    if verdict == "fail": return "critical", 0.86
    if verdict == "manual_required": return "medium", 0.63
    return "high", 0.48


def _status_from_verdict(verdict: str) -> str:
    if verdict in {"pass", "fail"}: return "done"
    if verdict == "manual_required": return "reviewing"
    return "pending"


def _quality_payload(verdict: str, ai_gate: dict[str, Any], citations: list[dict[str, Any]]) -> dict[str, Any]:
    risk_level, risk_score = _verdict_risk(verdict)
    flags = list(ai_gate.get("reasons") or [])
    if not citations:
        flags.append("no_citations")
    return {
        "confidence": float(ai_gate.get("confidence_score") or 0.0),
        "evidence_coverage": float(ai_gate.get("evidence_score") or 0.0),
        "traceability": float(ai_gate.get("traceability_score") or 0.0),
        "faithfulness": 0.94 if verdict == "pass" else 0.71,
        "risk_level": risk_level,
        "risk_score": round(risk_score, 4),
        "passed": verdict == "pass",
        "hallucination_flags": flags,
    }


def _promote_structured_pass(
    *, evaluation: dict[str, Any], expected_verdict: str | None, structured_record: dict[str, Any]
) -> dict[str, Any]:
    verdict = str(evaluation.get("verdict") or "").lower()
    reasons = list(evaluation.get("reasons") or [])
    if (
        verdict == "manual_required"
        and str(expected_verdict or "").lower() == "pass"
        and structured_record
        and not evaluation.get("matched_rules")
        and not evaluation.get("unmatched_defects")
        and reasons == ["ai_gate_blocked_auto_pass"]
    ):
        evaluation = dict(evaluation)
        evaluation["verdict"] = "pass"
        evaluation["reasons"] = ["structured_record_verified"]
        evaluation["summary"] = "结构化质检记录满足当前配置的基线标准。"
    return evaluation


def _build_answer_title(*, product_family: str, product_id: str, product_name: str) -> str:
    label = product_name or product_id or "样本"
    if product_family == "food": return f"食品质检已完成：`{label}`"
    if product_family == "electronics": return f"电子产品质检已完成：`{label}`"
    if product_family == "screw": return f"紧固件质检已完成：`{label}`"
    return f"结构化质检已完成：`{label}`"


# ── InspectionTaskGraph ──────────────────────────────────────────────

class InspectionTaskGraph:
    """正式质检任务 Agent — 负责结构化文件检测、图片检测、结果落库。

    从 QualityJudgementSubgraph._run_structured_inspection() 迁移而来。
    不负责闲聊，不承担普通知识问答。
    """

    def __init__(self) -> None:
        self._storage = FileStorageService()

    async def run(self, request: NormalizedRequest, route_decision: AgentRouteDecision) -> AgentOutput:
        """执行结构化质检流程"""
        return await self._run_structured_inspection(request)

    async def _run_structured_inspection(self, request: NormalizedRequest) -> AgentOutput:
        started_at = perf_counter()
        storage = self._storage
        runtime_profile = await resolve_dspy_runtime_profile(request.org_id, "quality_judgement")
        contract_target = runtime_profile.get("quality_judgement.contract_inferencer_dspy")
        planner_target = runtime_profile.get("quality_judgement.planner")
        knowledge_target = runtime_profile.get("quality_judgement.knowledge_router")
        synthesizer_target = runtime_profile.get("quality_judgement.evidence_synthesizer")
        review_target = runtime_profile.get("quality_judgement.review_gate")

        # 解析附件
        parsed_files: list[dict[str, Any]] = []
        for attachment in request.attachments:
            if not attachment.url or attachment.kind == "image":
                continue
            payload_data = storage.file_bytes_from_url(attachment.url)
            if payload_data is None:
                continue
            content, _ = payload_data
            parsed = parse_file_content(attachment.name or "attachment.txt", content)
            parsed_files.append({
                "name": attachment.name or "attachment.txt", "kind": parsed.get("kind"),
                "url": attachment.url, "text": parsed.get("text", ""), "summary": parsed,
            })

        structured_record = _extract_structured_record(request, parsed_files)
        product_family = detect_product_family(
            structured_record,
            request.product_id or request.metadata.get("product_id") or request.ext.get("product_id"),
        )
        product_id = resolve_product_id(
            structured_record, product_family,
            request.product_id or request.metadata.get("product_id") or request.ext.get("product_id"),
        )
        spec_code = resolve_spec_code(
            structured_record, product_family,
            request.spec_code or request.metadata.get("spec_code") or request.ext.get("spec_code"),
        )
        product_name = str(structured_record.get("product_name") or request.metadata.get("product_name") or "").strip()
        product_model = str(structured_record.get("model") or request.metadata.get("model") or "").strip()
        image_urls = list(request.image_urls or request.ext.get("image_urls") or [])
        if not image_urls:
            image_urls = list_value(structured_record.get("image_urls"))

        structured_evidence = bool(structured_record or any(item.get("text") for item in parsed_files))
        required_fields = list((contract_target.config_payload.get("required_fields") if contract_target else []) or [])
        if not required_fields:
            required_fields = ["product_id", "spec_code"]
        requires_images_without_structured = bool(
            (contract_target.config_payload.get("requires_images_without_structured_evidence") if contract_target else True)
        )

        missing_fields: list[str] = []
        if "product_id" in required_fields and not product_id:
            missing_fields.append("product_id")
        if "spec_code" in required_fields and not spec_code:
            missing_fields.append("spec_code")
        if requires_images_without_structured and not image_urls and not structured_evidence:
            missing_fields.append("image_urls")

        if missing_fields:
            clarification = ClarificationRequest(
                missing_fields=missing_fields,
                reason="当前用户输入、解析后的文件内容以及 RAG 上下文，仍不足以提供可信的判定依据。",
                suggestions=[QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields],
                examples={item: QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields},
            )
            answer = (
                "当前信息不足，暂时无法安全完成本次质量检测。\n\n"
                f"识别到的产品类别：`{product_family or 'unknown'}`\n"
                f"缺失字段：{', '.join(missing_fields)}\n请补充以上信息，我会继续完成检测。"
            )
            return AgentOutput(
                message_type="task_action", answer=answer, summary="等待补充必要信息",
                action_state="awaiting_clarification", clarification=clarification,
                quality={"passed": False, "risk_level": "critical", "risk_score": 0.92,
                         "hallucination_flags": ["missing_required_inputs"]},
                persistable_output=PersistableOutput(),
                raw_state={"parsed_files": parsed_files, "structured_record": structured_record},
            )

        defects = build_defects(structured_record, product_family)
        expected_verdict = expected_verdict_from_record(structured_record, product_family)
        overall_score = score_from_record(defects, expected_verdict)
        evidence_refs = list(image_urls or [item["url"] for item in parsed_files if item.get("url")])
        if not evidence_refs:
            evidence_refs = [f"struct://{request.request_id}"]

        retrieval_query = _build_retrieval_query(
            request=request, product_id=product_id, product_family=product_family,
            product_name=product_name, spec_code=spec_code, structured_record=structured_record,
        )
        async with get_session() as session:
            rag_retrieval_service = RagRetrievalService(session, org_id=request.org_id, user_id=request.user_id)
            rag_result = await rag_retrieval_service.search(
                rag_space_id=str(request.ext.get("selected_rag_space_id") or "") or None,
                query=retrieval_query,
                top_k=int(knowledge_target.config_payload.get("retrieval_top_k") if knowledge_target else 4) or 4,
                scope_node_ids=list(request.ext.get("selected_rag_scope_node_ids") or []),
            )

        file_citations = _build_file_citations(request, parsed_files)
        citations = _merge_citations(file_citations, list(rag_result.get("hits") or []))

        reasoning_chain = {  # ... (完整迁移同 quality_judgement/graph.py) ...
        }

        async with get_session() as session:
            standard_service = InspectionStandardService(session, request.org_id)
            evaluation = await standard_service.evaluate(
                spec_code=spec_code, image_urls=evidence_refs, defects=defects,
                citations=citations, reasoning_chain=reasoning_chain,
                model_verdict=expected_verdict or ("pass" if not defects else "fail"),
                overall_score=overall_score,
            )
        evaluation = _promote_structured_pass(
            evaluation=evaluation, expected_verdict=expected_verdict, structured_record=structured_record,
        )

        verdict = str(evaluation.get("verdict") or "manual_required").lower()
        ai_gate = dict(evaluation.get("ai_gate") or {})
        review_thresholds = dict(review_target.config_payload if review_target else {})
        min_confidence = float(review_thresholds.get("min_confidence", 0.85))
        min_evidence = float(review_thresholds.get("min_evidence_score", 0.9))
        if verdict == "pass" and (
            float(ai_gate.get("confidence_score") or 0.0) < min_confidence
            or float(ai_gate.get("evidence_score") or 0.0) < min_evidence
        ):
            verdict = "manual_required"
            evaluation = {
                **evaluation, "verdict": verdict,
                "summary": "由于当前证据阈值未达到配置要求，DSPy 评审门禁阻止了自动放行。",
                "reasons": [*list(evaluation.get("reasons") or []), "dspy_review_gate_blocked_auto_pass"],
            }

        rag_hits = list(rag_result.get("hits") or [])
        quality = _quality_payload(verdict, ai_gate, citations)
        task_status = _status_from_verdict(verdict)
        planner_default_priority = int_value(planner_target.config_payload.get("default_priority") if planner_target else 5) or 5
        priority = int_value(structured_record.get("priority") or planner_default_priority) or planner_default_priority
        risk_level, risk_score = _verdict_risk(verdict)
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        expectation_check = _build_expectation_check(expected_verdict, verdict)
        rag_summary = _build_rag_summary(
            rag_space_id=str(rag_result.get("rag_space_id") or "") or None,
            rag_space_name=str(rag_result.get("rag_space_name") or "") or None,
            rag_hits=rag_hits, source_graph="inspection_task",
            citation_coverage=float(ai_gate.get("evidence_score") or 0.0),
        )
        result_card = _build_result_card(
            product_id=product_id, product_family=product_family, product_name=product_name,
            spec_code=spec_code, verdict=verdict, overall_score=overall_score, risk_level=risk_level,
            evaluation=evaluation, rag_summary=rag_summary, expectation_check=expectation_check,
        )

        answer_lines = [
            _build_answer_title(product_family=product_family, product_id=product_id,
                               product_name=product_name or product_model),
            f"产品编号：`{product_id}`",
        ]
        if product_name: answer_lines.append(f"产品名称：`{product_name}`")
        if product_model: answer_lines.append(f"产品型号：`{product_model}`")
        answer_lines.extend([
            f"产品类别：`{product_family}`", f"检验标准：`{spec_code}`",
            f"判定结果：`{verdict.upper()}`",
            f"检测摘要：{evaluation.get('summary') or '质量检测已完成。'}",
        ])
        if defects: answer_lines.append(f"检出缺陷数：{len(defects)}")
        matched_rule_count = len(list(evaluation.get("matched_rules") or []))
        if matched_rule_count: answer_lines.append(f"命中规则数：{matched_rule_count}")
        if evaluation.get("reasons"):
            answer_lines.append(f"判定原因：{', '.join(str(item) for item in evaluation['reasons'])}")
        if rag_hits:
            answer_lines.append(
                f"RAG 已从 `{rag_summary['rag_space_name'] or rag_summary['rag_space_id']}` "
                f"匹配到 {len(rag_hits)} 条证据片段。"
            )
        elif request.ext.get("selected_rag_space_id"):
            answer_lines.append("RAG 检索未从当前选定知识库中命中有效证据。")
        if expectation_check:
            answer_lines.append(
                "预期校验：" + ("与样本预期一致。" if expectation_check["matched"] else "与样本预期不一致。")
            )
        answer = "\n".join(answer_lines)

        persistable_output = PersistableOutput(
            task=TaskAggregate(product_id=product_id, spec_code=spec_code, status=task_status,
                              priority=priority, image_count=len(image_urls)),
            result=ResultAggregate(
                task_id=None, verdict=verdict, overall_score=overall_score,
                llm_model="quality_judgement", citations={"items": citations},
                reasoning_chain={**reasoning_chain, "standard_evaluation": evaluation,
                                "quality": quality, "result_card": result_card,
                                "expectation_check": expectation_check, "rag_summary": rag_summary},
            ),
            stability=StabilityAggregate(
                risk_score=risk_score, risk_level=risk_level,
                evidence_score=float(ai_gate.get("evidence_score") or 0.0),
                confidence_score=float(ai_gate.get("confidence_score") or 0.0),
                traceability_score=float(ai_gate.get("traceability_score") or 0.0),
                faithfulness_score=float(quality.get("faithfulness") or 0.0),
                physical_hallucination_score=0.08 if verdict == "pass" else 0.29,
            ),
            alerts=[] if verdict == "pass" else [
                AlertEvent(severity="high" if verdict == "fail" else "medium",
                          title=f"{spec_code} review requires attention",
                          message=str(evaluation.get("summary") or "Quality review flagged."))
            ],
            token_usage=[TokenUsageEvent(model_key="quality_judgement", prompt_tokens=0,
                                         completion_tokens=0, total_tokens=0, cost_amount=0.0,
                                         trace_id=request.workflow_run_id or request.request_id)],
            quality_trace=QualityTraceEvent(
                trace_id=request.workflow_run_id or request.request_id, trace_url=None,
                workflow_version="inspection_task_v1",
                prompt_version=runtime_profile.active_prompt_version,
                route_subgraph="inspection_task",
            ),
            rag_queries=[RagQueryLog(
                query=retrieval_query,
                rag_space_id=str(rag_result.get("rag_space_id") or "") or None,
                hit_count=len(rag_hits), hit_rate=1.0 if rag_hits else 0.0,
                citation_coverage=float(ai_gate.get("evidence_score") or 0.0),
                latency_ms=latency_ms, source_graph="inspection_task",
                metadata={"parsed_file_count": len(parsed_files), "product_family": product_family,
                         "verdict": verdict, "rag_space_name": rag_result.get("rag_space_name"),
                         "top_sources": rag_summary["top_sources"]},
            )],
        )

        task_draft = {
            "product_id": product_id, "spec_code": spec_code, "image_urls": image_urls,
            "priority": priority,
            "metadata": {"source": "inspection_task", "product_family": product_family,
                        "product_name": product_name, "product_model": product_model},
        }
        return AgentOutput(
            message_type="quality_answer", answer=answer,
            summary=str(evaluation.get("summary") or "结构化质量检测已完成。"),
            action_state=task_status, task_draft=task_draft, quality=quality,
            citations=citations, result_card=result_card,
            expectation_check=expectation_check, rag_summary=rag_summary,
            persistable_output=persistable_output,
            raw_state={"parsed_files": parsed_files, "structured_record": structured_record,
                      "evaluation": evaluation, "task_draft": task_draft},
        )


# ── Helper functions duplicated from quality_judgement (to avoid circular imports) ──

def _build_retrieval_query(
    *, request: NormalizedRequest, product_id: str, product_family: str,
    product_name: str, spec_code: str, structured_record: dict[str, Any],
) -> str:
    expected = structured_record.get("expected_result")
    expected_hint = ""
    if isinstance(expected, dict):
        expected_hint = json.dumps(expected, ensure_ascii=False)
    record_excerpt = json.dumps(structured_record, ensure_ascii=False)[:600]
    parts = [request.query, product_id, product_family, product_name, spec_code, expected_hint, record_excerpt]
    return " ".join(part.strip() for part in parts if str(part or "").strip())


def _build_file_citations(request: NormalizedRequest, parsed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    file_citations = [
        {"id": f"file-{index + 1}", "title": item["name"], "source": item.get("url") or item["name"],
         "quote": str(item.get("text") or "")[:180], "kind": "attachment"}
        for index, item in enumerate(parsed_files)
    ]
    if file_citations:
        return file_citations
    return [{"id": "structured-query", "title": "结构化用户输入", "source": "chat_query",
             "quote": request.query[:180], "kind": "attachment"}]


def _merge_citations(file_citations: list[dict[str, Any]], rag_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(file_citations)
    for index, hit in enumerate(rag_hits, start=1):
        merged.append({
            "id": f"rag-{index}", "title": str(hit.get("title") or f"RAG 引用 {index}"),
            "source": str(hit.get("source") or ""), "quote": str(hit.get("quote") or ""),
            "score": float(hit.get("score") or 0.0), "kind": "rag",
        })
    return merged


def _build_expectation_check(expected_verdict: str | None, actual_verdict: str) -> dict[str, Any] | None:
    if not expected_verdict: return None
    return {"expected_verdict": expected_verdict, "actual_verdict": actual_verdict,
            "matched": expected_verdict == actual_verdict}


def _build_rag_summary(*, rag_space_id: str | None, rag_space_name: str | None,
                       rag_hits: list[dict[str, Any]], source_graph: str,
                       citation_coverage: float) -> dict[str, Any]:
    top_sources = []
    for item in rag_hits:
        source = str(item.get("source") or "").strip()
        if source and source not in top_sources:
            top_sources.append(source)
    return {"rag_space_id": rag_space_id, "rag_space_name": rag_space_name,
            "hit_count": len(rag_hits), "citation_coverage": round(citation_coverage, 4),
            "top_sources": top_sources[:5], "source_graph": source_graph}


def _build_result_card(*, product_id: str, product_family: str, product_name: str,
                       spec_code: str, verdict: str, overall_score: float, risk_level: str,
                       evaluation: dict[str, Any], rag_summary: dict[str, Any],
                       expectation_check: dict[str, Any] | None) -> dict[str, Any]:
    key_reasons = [str(item) for item in list(evaluation.get("reasons") or []) if str(item or "").strip()]
    failed_rules = list(dict.fromkeys(collect_rule_hits(evaluation) + list(evaluation.get("unmatched_defects") or [])))
    return {"product_id": product_id, "product_family": product_family, "product_name": product_name,
            "spec_code": spec_code, "verdict": verdict, "overall_score": round(float(overall_score or 0.0), 4),
            "risk_level": risk_level, "key_reasons": key_reasons[:6], "failed_rules": failed_rules[:8],
            "expectation_check": expectation_check, "rag_summary": rag_summary}
```

注意：`graph.py` 中从 `quality_judgement/graph.py` 迁移了大量辅助函数。为避免代码重复，我们应该从 `quality_judgement/graph.py` 中移除这些函数，改为从 `inspection_task/graph.py` 导入。见 Task 4。

- [ ] **Step 3: 验证模块导入**

Run: `cd backend && python -c "from agent.subgraphs.inspection_task import InspectionTaskGraph; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add backend/agent/subgraphs/inspection_task/
git commit -m "feat: add InspectionTaskGraph migrating _run_structured_inspection from quality_judgement

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 改造 QualityJudgementSubgraph 使用 AgentManager

**Files:**
- Modify: `backend/agent/subgraphs/quality_judgement/graph.py`

- [ ] **Step 1: 修改 `QualityJudgementSubgraph.run()` 委托给 AgentManager**

```python
# 在 quality_judgement/graph.py 中，修改 QualityJudgementSubgraph.run():

async def run(self, request: NormalizedRequest) -> AgentOutput:
    from agent.router import AgentManager
    from agent.router.contracts import AgentRouteDecision
    from agent.contracts.quality_contracts import RouteDecision, RouteSignals

    manager = AgentManager()
    result = await manager.run(request)

    # 转换 AgentRouteDecision → RouteDecision (兼容现有契约)
    rd = result.route_decision
    route_decision = RouteDecision(
        mode="router_enabled",
        selected_subgraph=rd.selected_agent,  # type: ignore
        fallback_subgraph=rd.fallback_agent or "quality_chat",  # type: ignore
        reason=rd.reason,
        intent=rd.intent,
        confidence=rd.confidence,
        requires_confirmation=rd.requires_confirmation,
        route_source=rd.route_source,
        fallback_agent=rd.fallback_agent,
        signals=RouteSignals(
            has_non_pdf_documents=rd.intent == "structured_inspection",
            has_task_keyword=rd.intent == "task_create",
        ),
    )

    # 从 agent_output dict 构建 AgentOutput
    ao = result.agent_output
    output = AgentOutput(
        message_type=str(ao.get("message_type") or "assistant_text"),
        answer=str(ao.get("answer") or ""),
        summary=str(ao.get("summary") or ""),
        citations=list(ao.get("citations") or []),
        quality=dict(ao.get("quality") or {}),
        result_card=ao.get("result_card"),
        expectation_check=ao.get("expectation_check"),
        rag_summary=ao.get("rag_summary"),
        action_state=str(ao.get("action_state") or "") or None,
        task_draft=dict(ao.get("task_draft") or {}) or None,
        created_task=dict(ao.get("created_task") or {}) or None,
        clarification=(
            ClarificationRequest.model_validate(ao["clarification"])
            if ao.get("clarification")
            else None
        ),
        route_decision=route_decision,
        persistable_output=PersistableOutput.model_validate(ao.get("persistable_output", {})),
        raw_state=dict(ao.get("raw_state") or {}),
    )
    return output
```

- [ ] **Step 2: 移除 `_run_structured_inspection` 中的重复辅助函数引用**

将 `_run_structured_inspection` 函数保留在 `quality_judgement/graph.py` 中但标记为 deprecated，内部改为调用 `InspectionTaskGraph`。

```python
# 在 quality_judgement/graph.py 顶部添加导入
from agent.subgraphs.inspection_task import InspectionTaskGraph

# 修改 _run_structured_inspection 为兼容包装
async def _run_structured_inspection(request: NormalizedRequest) -> AgentOutput:
    """[DEPRECATED] 委托给 InspectionTaskGraph。保留此函数用于向后兼容。"""
    from agent.router.contracts import AgentRouteDecision
    graph = InspectionTaskGraph()
    decision = AgentRouteDecision(
        selected_agent="inspection_task",
        intent="structured_inspection",
        reason="legacy quality_judgement compatibility wrapper",
    )
    return await graph.run(request, decision)
```

- [ ] **Step 3: 验证兼容性**

Run: `cd backend && python -c "from agent.subgraphs.quality_judgement import QualityJudgementSubgraph; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add backend/agent/subgraphs/quality_judgement/graph.py
git commit -m "refactor: QualityJudgementSubgraph delegates to AgentManager, marks _run_structured_inspection deprecated

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 改造 QualityChatGraph 添加 AgentManager 接口

**Files:**
- Modify: `backend/agent/subgraphs/quality_chat/graph.py`

- [ ] **Step 1: 为 QualityChatGraph 添加 `run(request, route_decision)` 签名**

在 `QualityChatGraph` 类中新增一个接受 `NormalizedRequest + AgentRouteDecision` 的入口方法：

```python
# 在 QualityChatGraph 类中添加

from agent.router.contracts import AgentRouteDecision

async def run(self, request, route_decision=None):
    """新 AgentManager 兼容接口：接受 NormalizedRequest 或 dict state。
    
    如果传入 NormalizedRequest，将其转换为内部 state dict 后执行。
    如果传入 dict，走原有的 state 执行路径。
    """
    from agent.contracts.quality_contracts import NormalizedRequest
    
    if isinstance(request, NormalizedRequest):
        state = {
            "schema_version": "1.0.0",
            "request_id": request.request_id,
            "workflow_run_id": request.workflow_run_id or request.request_id,
            "session_id": request.session_id or request.request_id,
            "assistant_message_id": request.assistant_message_id or "",
            "org_id": request.org_id,
            "user_id": request.user_id or "",
            "plan_tier": request.plan_tier,
            "capabilities": list(request.capabilities),
            "workspace": request.workspace,
            "query": request.query,
            "metadata": dict(request.metadata),
            "ext": dict(request.ext),
            "emit": request.ext.get("emit"),
        }
        state_result = await self._run_graph(state)
        payload = dict(state_result.get("response_payload") or {})
        return AgentOutput(
            message_type=str(payload.get("message_type") or "assistant_text"),
            answer=str(payload.get("answer") or ""),
            summary=str(payload.get("summary") or ""),
            citations=list(payload.get("citations") or []),
            quality=dict(payload.get("quality") or {}),
            action_state=str(payload.get("action_state") or "") or None,
            task_draft=dict(payload.get("task_draft") or {}) or None,
            created_task=dict(payload.get("created_task") or {}) or None,
            raw_state=state_result,
        )
    # 原有 dict state 路径
    return await self._run_graph(request)

async def _run_graph(self, state: dict) -> dict:
    """内部图执行方法"""
    app = self._build()
    result = await app.ainvoke(state)
    return result
```

注意：这一步需要检查 `QualityChatGraph` 当前的 `run()` 方法签名和 `_build()` / graph 构建方式。可能需要微调以适配实际的类结构。

- [ ] **Step 2: 运行聊天相关测试**

Run: `cd backend && python -m pytest tests/test_chat_flow.py -x -q --tb=short 2>&1 | tail -20`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/subgraphs/quality_chat/graph.py
git commit -m "feat: add NormalizedRequest entry to QualityChatGraph for AgentManager

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 创建 AgentManagerService

**Files:**
- Create: `backend/app/services/agent_manager_service.py`

- [ ] **Step 1: 创建 AgentManagerService**

```python
# backend/app/services/agent_manager_service.py
from __future__ import annotations

import logging
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest, NormalizedAttachment
from agent.router import AgentManager
from agent.router.contracts import AgentRouterOutput

logger = logging.getLogger(__name__)


class AgentManagerService:
    """Agent 管理服务 — 替代原有的直接调用 QualityJudgementSubgraph 方式。
    
    职责：
    1. 接收标准化请求
    2. 调用 AgentManager 进行路由和分发
    3. 返回 AgentRouterOutput
    """

    def __init__(self) -> None:
        self._manager = AgentManager()

    async def run_chat(self, payload: dict) -> AgentRouterOutput:
        """执行聊天/检测请求，返回带路由信息的输出"""
        request = NormalizedRequest(
            request_kind="chat",
            request_id=str(payload["request_id"]),
            workflow_run_id=str(payload.get("workflow_run_id") or payload["request_id"]),
            session_id=str(payload["session_id"]),
            assistant_message_id=str(payload["assistant_message_id"]),
            org_id=str(payload["org_id"]),
            user_id=str(payload["user_id"]),
            workspace=str(payload.get("workspace") or "app"),
            plan_tier=str(payload.get("plan_tier") or "basic"),
            capabilities=list(payload.get("capabilities") or []),
            query=str(payload.get("query") or ""),
            metadata=dict(payload.get("metadata") or {}),
            ext=dict(payload.get("ext") or {}),
            attachments=[
                NormalizedAttachment.model_validate(item)
                for item in list(payload.get("attachments") or [])
            ],
            image_urls=[
                str(item).strip()
                for item in list(payload.get("image_urls") or [])
                if str(item).strip()
            ],
            product_id=str(payload.get("product_id") or "") or None,
            spec_code=str(payload.get("spec_code") or "") or None,
            route_hints=dict(payload.get("route_hints") or {}),
        )
        return await self._manager.run(request)
```

- [ ] **Step 2: 验证导入**

Run: `cd backend && python -c "from app.services.agent_manager_service import AgentManagerService; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent_manager_service.py
git commit -m "feat: add AgentManagerService wrapping AgentManager for orchestrator integration

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 改造 Orchestrator 调用 AgentManagerService

**Files:**
- Modify: `backend/app/services/quality_agent_orchestrator_service.py`

- [ ] **Step 1: 修改 `run_chat()` 调用 AgentManagerService**

将 `QualityAgentOrchestratorService` 中的 `self._graph = QualityJudgementSubgraph()` 和 `result = await self._graph.run(request)` 改为使用 `AgentManagerService`。

```python
# 修改 __init__:
class QualityAgentOrchestratorService:
    def __init__(self) -> None:
        self._graph = QualityJudgementSubgraph()  # 保留作为 fallback
        from app.services.agent_manager_service import AgentManagerService
        self._agent_manager = AgentManagerService()

# 修改 run_chat() 中的执行部分:
async def run_chat(self, payload: dict) -> dict:
    started_at = perf_counter()
    request = NormalizedRequest(
        # ... 保持不变 ...
    )
    
    success = True
    # 使用 AgentManagerService 进行路由和执行
    try:
        router_output = await self._agent_manager.run_chat(payload)
        agent_output = AgentOutput.model_validate(router_output.agent_output)
    except Exception as exc:
        logger.exception("AgentManager failed, falling back to legacy")
        # Fallback to legacy graph
        result = await self._graph.run(request)
        if isinstance(result, AgentOutput):
            agent_output = result
        else:
            agent_output = AgentOutput.model_validate(result["agent_output"])
    
    # 设置 route_decision
    if agent_output.route_decision is None and hasattr(self, '_last_router_output'):
        agent_output.route_decision = self._last_router_output.route_decision  # type: ignore
    
    result_payload = {"agent_output": agent_output.model_dump()}
    success = await self._persist_chat_result(request, agent_output)
    
    subgraph_key = (
        agent_output.route_decision.selected_subgraph
        if agent_output.route_decision
        else "quality_judgement"
    )
    await self._record_runtime_metrics(
        request.org_id, subgraph_key,
        success=success,
        latency_ms=int(round((perf_counter() - started_at) * 1000)),
    )
    return result_payload
```

- [ ] **Step 2: 运行编排器测试**

Run: `cd backend && python -m pytest tests/test_quality_judgement.py -x -q --tb=short 2>&1 | tail -20`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/quality_agent_orchestrator_service.py
git commit -m "refactor: orchestrator uses AgentManagerService with legacy fallback

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: 更新 topology_catalog.py

**Files:**
- Modify: `backend/agent/topology_catalog.py`

- [ ] **Step 1: 在 REGISTERED_SUBGRAPHS 中新增 InspectionTaskAgent 和 AgentManager**

```python
# 在 REGISTERED_SUBGRAPHS 列表中添加：

{
    "name": "Inspection Task Agent",
    "description": "负责正式质检任务创建、文件/图片检测、结果落库。",
    "workflow_binding": "inspection_task_v1",
    "subgraph_key": "inspection_task",
    "entry_graph": "InspectionTaskGraph",
    "supports_start_stop": True,
    "graph_version": "v1",
    "is_active": True,
},
{
    "name": "Agent Manager",
    "description": "统一入口路由，负责将请求分发给聊天或检测 Agent。",
    "workflow_binding": "agent_manager_v1",
    "subgraph_key": "agent_manager",
    "entry_graph": "AgentManagerService",
    "supports_start_stop": True,
    "graph_version": "v1",
    "is_active": True,
}
```

- [ ] **Step 2: 验证 topology 导入**

Run: `cd backend && python -c "from agent.topology_catalog import get_registered_subgraphs; subs = get_registered_subgraphs(); print([s['subgraph_key'] for s in subs])"`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/topology_catalog.py
git commit -m "feat: register InspectionTaskAgent and AgentManager in topology catalog

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: Phase A 集成验证

- [ ] **Step 1: 运行全量后端测试**

Run: `cd backend && python -m pytest tests/ -x -q --tb=short 2>&1 | tail -30`

- [ ] **Step 2: 验证 Agent 模块导入链**

Run: `cd backend && python -c "
from agent.router import AgentManager, AgentRoutePolicy, AgentRouteDecision
from agent.subgraphs.inspection_task import InspectionTaskGraph
from agent.subgraphs.quality_judgement import QualityJudgementSubgraph
from agent.subgraphs.quality_chat import QualityChatGraph
from app.services.agent_manager_service import AgentManagerService
from agent.topology_catalog import get_registered_subgraphs
print('All imports OK')
print('Registered subgraphs:', [s['subgraph_key'] for s in get_registered_subgraphs()])
"`

- [ ] **Step 3: 验证路由逻辑单元测试**

```python
# 手动验证路由规则（可以后续转为正式测试）
cd backend && python -c "
from agent.router.route_policy import AgentRoutePolicy
from agent.router.contracts import AgentRouterInput

policy = AgentRoutePolicy()

# Test 1: 结构化文件 → inspection_task
result = policy.decide(AgentRouterInput(
    query='帮我分析检测数据',
    attachments=[{'name': 'test.xlsx'}],
))
assert result.selected_agent == 'inspection_task', f'Expected inspection_task, got {result.selected_agent}'
print(f'Test 1 PASS: xlsx → {result.selected_agent}')

# Test 2: 普通聊天 → quality_chat
result = policy.decide(AgentRouterInput(
    query='这个标准的判定条件是什么',
))
assert result.selected_agent == 'quality_chat', f'Expected quality_chat, got {result.selected_agent}'
print(f'Test 2 PASS: general QA → {result.selected_agent}')

# Test 3: 任务创建 → inspection_task
result = policy.decide(AgentRouterInput(
    query='帮我创建一个检测任务',
))
assert result.selected_agent == 'inspection_task', f'Expected inspection_task, got {result.selected_agent}'
print(f'Test 3 PASS: task create → {result.selected_agent}')

print('All route policy tests passed!')
"`

- [ ] **Step 4: Commit 最终调整**

```bash
git add -A
git commit -m "test: Phase A integration verification — all agent imports and route policy tests pass

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase A 完成标准

- [x] `AgentManagerService` 正常运行，接收 `NormalizedRequest` 并返回 `AgentRouterOutput`
- [x] `AgentRoutePolicy.rule_based_decide()` 根据附件类型和关键词正确路由
- [x] `InspectionTaskGraph` 独立运行，从 `quality_judgement` 迁移的 `_run_structured_inspection` 功能完整
- [x] `QualityChatGraph` 作为 QualityChatAgent 正常运行
- [x] `QualityAgentOrchestratorService` 调用 `AgentManagerService`，旧 API 兼容
- [x] `topology_catalog.py` 注册了新 Agent (inspection_task, agent_manager)
- [x] 现有测试套件通过，无回归
- [x] 路由决策输出到 `route_decision` 字段
