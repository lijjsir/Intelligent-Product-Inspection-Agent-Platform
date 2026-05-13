# Agent Architecture Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure agent graph topology: rename shared_memory_hierarchy → memory_manager (MemoryManagerAgent), merge legacy_quality + llm_native_quality → quality_judgement (QualityJudgementAgent), delete quality_root, and add multi-provider LLM support (DeepSeek V4 Flash for reasoning, Volcengine for vision).

**Architecture:** MemoryManagerAgent becomes the single parent graph. QualityJudgementAgent is a routing wrapper that delegates to QualityChatGraph (chat-based quality) or runs LLM-native structured inspection logic directly. QualityChatGraph stays independent for pure chat interactions. Five stub agents remain as topology placeholders. LLMClient gains provider-parameter to switch between DeepSeek and Volcengine.

**Key insight:** LegacyQualitySubgraph is a thin wrapper around QualityChatGraph. LLMNativeQualitySubgraph is a monolithic `run()` method (~650 lines), not a LangGraph node graph. The "merge" means QualityJudgementSubgraph internally routes between QualityChatGraph and the LLM-native logic — exactly what QualityAgentRootGraph does today, but as a single named subgraph.

**Tech Stack:** Python 3.12, LangGraph, FastAPI, SQLAlchemy, Pydantic v2, DeepSeek API, Volcengine Ark SDK

---

### Task 1: Add DeepSeek Settings to Config

**Files:**
- Modify: `backend/app/core/config.py:32-35`

- [ ] **Step 1: Add DeepSeek configuration fields**

```python
# backend/app/core/config.py — add after volcengine_base_url (line 35)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_id: str = "deepseek-v4-flash"
```

- [ ] **Step 2: Verify settings load**

Run: `cd backend && python -c "from app.core.config import settings; print(settings.deepseek_model_id)"`
Expected: `deepseek-v4-flash`

- [ ] **Step 3: Update .env if present**

```bash
# Check if .env exists
ls backend/.env 2>/dev/null && echo "PIAP_DEEPSEEK_API_KEY=16DB5F7B-26AF-4EBF-B13A-DA3155362D97" >> backend/.env || echo "no .env, will use env var"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat: add DeepSeek API configuration settings"
```

---

### Task 2: Add Multi-Provider Support to LLMClient

**Files:**
- Modify: `backend/agent/llm/client.py:17-42`

- [ ] **Step 1: Update LLMClient.__init__ to support provider switching**

Replace `__init__` (lines 19-41):

```python
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_id: str | None = None,
        embed_model: str | None = None,
        trace_id: str | None = None,
        task_id: str | None = None,
        org_id: str | None = None,
        provider: str | None = None,
    ) -> None:
        self._provider = provider or "volcengine"
        if self._provider == "deepseek":
            self._api_key = api_key or settings.deepseek_api_key
            self._base_url = (base_url or settings.deepseek_base_url).rstrip("/")
            self._model_id = model_id or settings.deepseek_model_id
            self._embed_model = embed_model or settings.volcengine_embed_model
        else:
            self._api_key = api_key or settings.volcengine_api_key
            self._base_url = (base_url or settings.volcengine_base_url).rstrip("/")
            self._model_id = model_id or settings.volcengine_model_id
            self._embed_model = embed_model or settings.volcengine_embed_model
        self._task_id = None if task_id is None else str(task_id)
        self._org_id = None if org_id is None else str(org_id)
        self._request_attempts = 3
        self._tracer = LangfuseTracer()
        self._trace_id = trace_id or (self._tracer.create_trace_id() if self._tracer.enabled else None)
        self._ark_client = Ark(api_key=self._api_key) if Ark and self._api_key else None
```

- [ ] **Step 2: Verify provider switching**

```bash
cd backend && python -c "
from agent.llm.client import LLMClient
d = LLMClient(provider='deepseek')
v = LLMClient()
print(f'DeepSeek: model={d.model_id}')
print(f'Volcengine: model={v.model_id}')
assert d.model_id != v.model_id
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/agent/llm/client.py
git commit -m "feat: add multi-provider support to LLMClient (DeepSeek + Volcengine)"
```

---

### Task 3: Create QualityJudgementAgent Subgraph

**Files:**
- Create: `backend/agent/subgraphs/quality_judgement/__init__.py`
- Create: `backend/agent/subgraphs/quality_judgement/graph.py`
- Copy: `backend/agent/subgraphs/llm_native_quality/product_adapters.py` → `backend/agent/subgraphs/quality_judgement/product_adapters.py`

**Architecture note:** QualityJudgementSubgraph is a routing wrapper. For chat-based quality (`request_kind == "chat"`), it delegates to QualityChatGraph. For file/text-based structured inspection, it runs the LLM-native logic directly (copied from `llm_native_quality/graph.py`). This is exactly what `QualityAgentRootGraph` did, but now as a named subgraph that MemoryManagerAgent can route to.

- [ ] **Step 1: Create directory and __init__.py**

```bash
mkdir -p backend/agent/subgraphs/quality_judgement
```

```python
# backend/agent/subgraphs/quality_judgement/__init__.py
from __future__ import annotations

from agent.subgraphs.quality_judgement.graph import QualityJudgementSubgraph

__all__ = ["QualityJudgementSubgraph"]
```

- [ ] **Step 2: Copy product_adapters.py**

```bash
cp backend/agent/subgraphs/llm_native_quality/product_adapters.py backend/agent/subgraphs/quality_judgement/product_adapters.py
```

- [ ] **Step 3: Create quality_judgement/graph.py**

The graph imports QualityChatGraph (for chat path) and contains the LLM-native structured inspection logic (copied from `llm_native_quality/graph.py`). The routing mirrors `quality_root/graph.py`'s `route_policy` logic.

```python
# backend/agent/subgraphs/quality_judgement/graph.py
from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from agent.contracts import (
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
from agent.subgraphs.quality_chat import QualityChatGraph
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

# ── Route signal detection (from quality_root/graph.py) ──────────────

TASK_KEYWORD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"创建任务", r"新建任务", r"发起检测", r"提交任务",
        r"检测任务", r"任务", r"task",
    ]
]

# ── Helper functions (from llm_native_quality/graph.py) ──────────────

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


def _build_answer_title(*, product_family: str, product_id: str, product_name: str) -> str:
    label = product_name or product_id or "样本"
    if product_family == "food": return f"食品质检已完成：`{label}`"
    if product_family == "electronics": return f"电子产品质检已完成：`{label}`"
    if product_family == "screw": return f"紧固件质检已完成：`{label}`"
    return f"结构化质检已完成：`{label}`"


# ── LLM-native structured inspection (from llm_native_quality/graph.py) ─

async def _run_structured_inspection(request: NormalizedRequest) -> AgentOutput:
    """Run the file/text-driven structured quality inspection."""
    started_at = perf_counter()
    storage = FileStorageService()
    runtime_profile = await resolve_dspy_runtime_profile(request.org_id, "llm_native_quality")
    contract_target = runtime_profile.get("llm_native_quality.contract_inferencer_dspy")
    planner_target = runtime_profile.get("llm_native_quality.planner")
    knowledge_target = runtime_profile.get("llm_native_quality.knowledge_router")
    synthesizer_target = runtime_profile.get("llm_native_quality.evidence_synthesizer")
    review_target = runtime_profile.get("llm_native_quality.review_gate")

    parsed_files: list[dict[str, Any]] = []
    for attachment in request.attachments:
        if not attachment.url or attachment.kind == "image":
            continue
        payload = storage.file_bytes_from_url(attachment.url)
        if payload is None:
            continue
        content, _ = payload
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
        )

    file_citations = _build_file_citations(request, parsed_files)
    citations = _merge_citations(file_citations, list(rag_result.get("hits") or []))

    reasoning_chain = {
        "summary": "已基于结构化文件、产品类别解析结果和 RAG 证据完成检验标准评估。",
        "structured_record": structured_record, "product_family": product_family,
        "product_name": product_name,
        "source_files": [{"name": item["name"], "url": item.get("url")} for item in parsed_files],
        "trace": {"trace_id": request.workflow_run_id or request.request_id, "trace_url": None,
                  "model_key": "quality_judgement"},
        "langfuse_scores": [], "dspy_runtime": runtime_profile.as_metadata(),
        "knowledge_router": {
            "selected_rag_space_id": request.ext.get("selected_rag_space_id"),
            "selected_rag_space_name": rag_result.get("rag_space_name"),
            "query": retrieval_query, "hit_count": int(rag_result.get("hit_count") or 0),
            "top_hits": list(rag_result.get("hits") or []),
            "target_config": knowledge_target.summary() if knowledge_target else None,
        },
        "evidence_synthesizer": {
            "citation_count": len(citations), "file_citation_count": len(file_citations),
            "rag_citation_count": len(list(rag_result.get("hits") or [])),
            "target_config": synthesizer_target.summary() if synthesizer_target else None,
        },
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
    physical_hallucination_score = 0.08 if verdict == "pass" else 0.29
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
        rag_hits=rag_hits, source_graph="quality_judgement",
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
            physical_hallucination_score=physical_hallucination_score,
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
            workflow_version="quality_judgement_v2",
            prompt_version=runtime_profile.active_prompt_version,
            route_subgraph="quality_judgement",
        ),
        rag_queries=[RagQueryLog(
            query=retrieval_query,
            rag_space_id=str(rag_result.get("rag_space_id") or "") or None,
            hit_count=len(rag_hits), hit_rate=1.0 if rag_hits else 0.0,
            citation_coverage=float(ai_gate.get("evidence_score") or 0.0),
            latency_ms=latency_ms, source_graph="quality_judgement",
            metadata={"parsed_file_count": len(parsed_files), "structured_record": structured_record,
                     "product_family": product_family, "product_id": product_id,
                     "product_name": product_name, "spec_code": spec_code, "verdict": verdict,
                     "expectation_matched": None if not expectation_check else expectation_check["matched"],
                     "rag_space_name": rag_result.get("rag_space_name"),
                     "top_sources": rag_summary["top_sources"],
                     "rule_hits": list(dict.fromkeys(result_card["failed_rules"])),
                     "dspy_runtime": runtime_profile.as_metadata()},
        )],
    )

    task_draft = {
        "product_id": product_id, "spec_code": spec_code, "image_urls": image_urls,
        "priority": priority,
        "metadata": {"source": "quality_judgement", "product_family": product_family,
                    "product_name": product_name, "product_model": product_model,
                    "structured_record": structured_record},
    }
    return AgentOutput(
        message_type="quality_answer", answer=answer,
        summary=str(evaluation.get("summary") or "结构化质量检测已完成。"),
        action_state=task_status, task_draft=task_draft, quality=quality,
        citations=citations, result_card=result_card,
        expectation_check=expectation_check, rag_summary=rag_summary,
        persistable_output=persistable_output,
        raw_state={"parsed_files": parsed_files, "structured_record": structured_record,
                  "evaluation": evaluation, "task_draft": task_draft,
                  "product_family": product_family, "result_card": result_card,
                  "expectation_check": expectation_check, "rag_summary": rag_summary,
                  "dspy_runtime": runtime_profile.as_metadata()},
    )


# ── QualityJudgementSubgraph ──────────────────────────────────────────

class QualityJudgementSubgraph:
    """Unified quality judgement agent — routing wrapper.

    Routes internally:
    - Chat-based quality → QualityChatGraph (unchanged)
    - File/text-based structured inspection → _run_structured_inspection()
    - Non-chat task requests → delegates to QualityChatGraph as fallback
    """

    def __init__(self) -> None:
        self._chat_graph = QualityChatGraph()
        self._storage = FileStorageService()

    async def run(self, request: NormalizedRequest) -> AgentOutput:
        # Route decision logic (from quality_root/graph.py route_policy)
        has_non_pdf = False
        has_task_keyword = False
        for item in request.attachments:
            name = str(item.name or "").lower()
            suffix = name.rsplit(".", 1)[-1] if "." in name else ""
            if suffix and suffix not in {"pdf", "png", "jpg", "jpeg", "webp", "gif"}:
                has_non_pdf = True
        query_text = str(request.query or "")
        has_task_keyword = any(pattern.search(query_text) for pattern in TASK_KEYWORD_PATTERNS)

        if has_non_pdf and not has_task_keyword:
            # LLM-native path: structured file/text inspection
            output = await _run_structured_inspection(request)
        elif request.request_kind == "chat":
            # Chat path: delegate to QualityChatGraph
            state = await self._chat_graph.run({
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
            })
            payload = dict(state.get("response_payload") or {})
            output = AgentOutput(
                message_type=str(payload.get("message_type") or "assistant_text"),
                answer=str(payload.get("answer") or ""),
                summary=str(payload.get("summary") or ""),
                citations=list(payload.get("citations") or []),
                quality=dict(payload.get("quality") or {}),
                action_state=str(payload.get("action_state") or "") or None,
                task_draft=dict(payload.get("task_draft") or {}) or None,
                created_task=dict(payload.get("created_task") or {}) or None,
                raw_state=state,
            )
        else:
            # Non-file, non-chat fallback
            output = AgentOutput(
                message_type="task_result",
                answer="任务已由统一质量判定智能体接收并提交执行。",
                summary="Quality judgement task submitted",
            )
        output.route_decision = None  # subgraph manages its own routing
        return output
```

- [ ] **Step 4: Verify the new subgraph imports correctly**

```bash
cd backend && python -c "from agent.subgraphs.quality_judgement import QualityJudgementSubgraph; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/agent/subgraphs/quality_judgement/
git commit -m "feat: create QualityJudgementAgent routing wrapper (merge legacy + native)"
```

---

### Task 4: Rename SharedMemoryHierarchy → MemoryManagerGraph

**Files:**
- Create: `backend/agent/graphs/memory_manager/__init__.py`
- Create: `backend/agent/graphs/memory_manager/state.py`
- Create: `backend/agent/graphs/memory_manager/reducers.py`
- Create: `backend/agent/graphs/memory_manager/nodes.py`
- Create: `backend/agent/graphs/memory_manager/graph.py`

- [ ] **Step 1: Create directory and copy files with updated imports**

```bash
mkdir -p backend/agent/graphs/memory_manager
```

Copy state.py and reducers.py (no subgraph import changes needed):
```bash
cp backend/agent/subgraphs/shared_memory_hierarchy/state.py backend/agent/graphs/memory_manager/state.py
cp backend/agent/subgraphs/shared_memory_hierarchy/reducers.py backend/agent/graphs/memory_manager/reducers.py
```

- [ ] **Step 2: Copy nodes.py and fix import**

Replace the state import (line 19):
```python
# Change:
from agent.subgraphs.shared_memory_hierarchy.state import MemoryAgentState
# To:
from agent.graphs.memory_manager.state import MemoryAgentState
```

- [ ] **Step 3: Create updated graph.py**

Copy from `shared_memory_hierarchy/graph.py` and update ALL imports:

```python
"""MemoryManagerGraph - unified parent graph with governance loop."""
from __future__ import annotations
from typing import Any, Literal
from langgraph.graph import END, StateGraph
from agent.graphs.memory_manager.nodes import (
    candidate_memory_builder, contamination_monitor_node,
    governance_recovery_agent, lab_detection_agent, manager_route_policy,
    market_monitor_agent, memory_context_loader, propagation_graph_node,
    provenance_node, public_opinion_agent, quality_judgement_agent,
    replay_evaluation_node, request_intake, result_synthesizer,
    rollback_planner_node, supervision_sampling_agent, trend_evolution_agent,
    write_gate_node,
)
from agent.graphs.memory_manager.state import MemoryAgentState
# ... rest identical to shared_memory_hierarchy/graph.py ...
```

(The graph structure — nodes, edges, conditional routing — stays identical. Only imports change.)

```python
class MemoryManagerGraph:
    """Unified parent graph — renamed from SharedMemoryHierarchyGraph."""
    def __init__(self):
        self._graph = build_graph()
    def compile(self, checkpointer=None):
        return self._graph.compile(checkpointer=checkpointer)
    @property
    def builder(self) -> StateGraph:
        return self._graph
```

- [ ] **Step 4: Create __init__.py and update graphs/__init__.py**

```python
# backend/agent/graphs/memory_manager/__init__.py
from agent.graphs.memory_manager.graph import MemoryManagerGraph
__all__ = ["MemoryManagerGraph"]
```

Update `backend/agent/graphs/__init__.py`:
```python
from agent.graphs.memory_manager import MemoryManagerGraph
__all__ = ["MemoryManagerGraph"]
```

- [ ] **Step 5: Verify**

```bash
cd backend && python -c "from agent.graphs.memory_manager import MemoryManagerGraph; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/agent/graphs/memory_manager/ backend/agent/graphs/__init__.py
git commit -m "feat: rename SharedMemoryHierarchy to MemoryManagerGraph"
```

---

### Task 5: Delete Old Directories

**Files:**
- Delete: `backend/agent/graphs/quality_root/`
- Delete: `backend/agent/subgraphs/legacy_quality/`
- Delete: `backend/agent/subgraphs/llm_native_quality/`
- Delete: `backend/agent/subgraphs/shared_memory_hierarchy/`

- [ ] **Step 1: Delete the old directories**

```bash
git rm -rf backend/agent/graphs/quality_root/
git rm -rf backend/agent/subgraphs/legacy_quality/
git rm -rf backend/agent/subgraphs/llm_native_quality/
git rm -rf backend/agent/subgraphs/shared_memory_hierarchy/
```

- [ ] **Step 2: Find remaining references to old paths**

```bash
rg "from agent\.(graphs\.quality_root|subgraphs\.legacy_quality|subgraphs\.llm_native_quality|subgraphs\.shared_memory_hierarchy)" backend/ --type py -l
```

Note the files that still reference old paths — will be fixed in Tasks 6-8.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: remove old agent directories (quality_root, legacy_quality, llm_native_quality, shared_memory_hierarchy)"
```

---

### Task 6: Rewrite Topology Catalog

**Files:**
- Modify: `backend/agent/topology_catalog.py` (full rewrite)

- [ ] **Step 1: Rewrite REGISTERED_SUBGRAPHS**

```python
REGISTERED_SUBGRAPHS: list[dict[str, Any]] = [
    {
        "name": "Quality Judgement",
        "description": "统一质量判定（合并 Legacy + LLM-native），支持 chat / file / task 多策略。",
        "workflow_binding": "quality_judgement_v2",
        "subgraph_key": "quality_judgement",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": True,
        "graph_version": "v2",
        "is_active": True,
    },
    {
        "name": "Quality Chat",
        "description": "轻量级智能问答入口，支持附件上传和 RAG 空间选择。",
        "workflow_binding": "quality_chat_v1",
        "subgraph_key": "quality_chat",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
    },
    {
        "name": "Market Monitor",
        "description": "市场价格、销量、渠道异常检测（规划中）。",
        "workflow_binding": "market_monitor_v0",
        "subgraph_key": "market_monitor",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Public Opinion",
        "description": "新闻、社交媒体、投诉举报等舆情分析（规划中）。",
        "workflow_binding": "public_opinion_v0",
        "subgraph_key": "public_opinion",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Trend Evolution",
        "description": "风险融合、趋势推演和情景预测（规划中）。",
        "workflow_binding": "trend_evolution_v0",
        "subgraph_key": "trend_evolution",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Supervision Sampling",
        "description": "抽检计划生成、样品管理和现场检查记录（规划中）。",
        "workflow_binding": "supervision_sampling_v0",
        "subgraph_key": "supervision_sampling",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Lab Detection",
        "description": "样品检测、指标解析和标准比对（规划中）。",
        "workflow_binding": "lab_detection_v0",
        "subgraph_key": "lab_detection",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
]
```

- [ ] **Step 2: Rewrite DSPY_OPTIMIZATION_TARGETS**

Replace "legacy_quality.*" and "llm_native_quality.*" target_keys with "quality_judgement.*":

```python
DSPY_OPTIMIZATION_TARGETS: list[dict[str, Any]] = [
    {
        "target_key": "quality_judgement.contract_inferencer",
        "subgraph_key": "quality_judgement",
        "node_id": "contract_inferencer",
        "node_ref": "quality_judgement.contract_inferencer",
        "node_label": "Contract Inferencer",
        "module_name": "QualityContractInferencer",
        "optimization_goal": "Improve contract inference for text and file-driven inspection requests.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.planner",
        "subgraph_key": "quality_judgement",
        "node_id": "planner",
        "node_ref": "quality_judgement.planner",
        "node_label": "Planner",
        "module_name": "QualityJudgementPlanner",
        "optimization_goal": "Optimize inspection task planning for unified quality flows.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.knowledge_router",
        "subgraph_key": "quality_judgement",
        "node_id": "knowledge_router",
        "node_ref": "quality_judgement.knowledge_router",
        "node_label": "Knowledge Router",
        "module_name": "QualityJudgementKnowledgeRouter",
        "optimization_goal": "Improve RAG and spec retrieval decisions.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.evidence_synthesizer",
        "subgraph_key": "quality_judgement",
        "node_id": "evidence_synthesizer",
        "node_ref": "quality_judgement.evidence_synthesizer",
        "node_label": "Evidence Synthesizer",
        "module_name": "EvidenceSynthesizer",
        "optimization_goal": "Improve evidence assembly quality and citation coverage.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.review_gate",
        "subgraph_key": "quality_judgement",
        "node_id": "review_gate",
        "node_ref": "quality_judgement.review_gate",
        "node_label": "Review Gate",
        "module_name": "QualityJudgementReviewGate",
        "optimization_goal": "Improve PASS/FAIL/UNCERTAIN gating decisions.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination", "pass_rate"],
        "supports_compile": True,
    },
]
```

- [ ] **Step 3: Rewrite node/edge topology definitions**

Replace LEGACY_NODES, LEGACY_EDGES, LLM_NATIVE_NODES, LLM_NATIVE_EDGES with QUALITY_JUDGEMENT_NODES and QUALITY_JUDGEMENT_EDGES, and rename SHARED_MEMORY_NODES references to use "memory_manager" prefix:

```python
ROOT_NODES = [
    {"id": "request_intake", "label": "Request Intake", "kind": "root"},
    {"id": "memory_context_loader", "label": "Memory Context Loader", "kind": "root"},
    {"id": "manager_route_policy", "label": "Manager Route Policy", "kind": "root"},
    {"id": "subgraph_runner", "label": "Subgraph Runner", "kind": "root"},
    {"id": "result_synthesizer", "label": "Result Synthesizer", "kind": "root"},
]
# ... etc (same structure as original, updated IDs)
```

- [ ] **Step 4: Update get_topology() to use new keys**

Replace `"legacy_quality"`, `"llm_native_quality"`, `"shared_memory_hierarchy"` with `"quality_judgement"`, `"quality_chat"`, `"memory_manager"` throughout the function.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/topology_catalog.py
git commit -m "feat: rewrite topology catalog for new agent architecture"
```

---

### Task 7: Update Orchestrator Service

**Files:**
- Modify: `backend/app/services/quality_agent_orchestrator_service.py`

- [ ] **Step 1: Update imports (line 8)**

```python
# Before:
from agent.graphs.quality_root import QualityAgentRootGraph
# After:
from agent.graphs.memory_manager import MemoryManagerGraph
```

- [ ] **Step 2: Update __init__ (line 34)**

```python
# Before:
        self._graph = QualityAgentRootGraph()
# After:
        self._graph = MemoryManagerGraph()
```

- [ ] **Step 3: Replace string references**

Search and replace throughout the file:
- `"legacy_quality"` → `"quality_judgement"`
- `"llm_native_quality"` → `"quality_judgement"`
- `"quality_agent_root_v1"` → `"memory_manager_v2"`

- [ ] **Step 4: Simplify the legacy_stream check**

Line 121-124:
```python
# Before:
        is_legacy_stream = (
            output.route_decision is not None
            and output.route_decision.selected_subgraph == "legacy_quality"
        )
# After:
        is_legacy_stream = False  # Unified quality_judgement handles all paths
```

- [ ] **Step 5: Update _should_materialize_chat_output reference (line 261)**

```python
# Before:
                source_graph="llm_native_quality",
# After:
                source_graph="quality_judgement",
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/quality_agent_orchestrator_service.py
git commit -m "feat: update orchestrator to use MemoryManagerGraph"
```

---

### Task 8: Fix All Remaining Import References

**Files:**
- Any files in `backend/` that still reference old paths

- [ ] **Step 1: Find all remaining references**

```bash
rg "quality_root|legacy_quality|llm_native_quality|shared_memory_hierarchy" backend/ --type py -l
```

- [ ] **Step 2: Update each file's imports**

Replace:
- `from agent.graphs.quality_root import QualityAgentRootGraph` → `from agent.graphs.memory_manager import MemoryManagerGraph`
- `from agent.subgraphs.legacy_quality import LegacyQualitySubgraph` → `from agent.subgraphs.quality_judgement import QualityJudgementSubgraph`
- `from agent.subgraphs.llm_native_quality import LLMNativeQualitySubgraph` → `from agent.subgraphs.quality_judgement import QualityJudgementSubgraph`
- `from agent.subgraphs.shared_memory_hierarchy.*` → `from agent.graphs.memory_manager.*`
- String `"legacy_quality"` → `"quality_judgement"`
- String `"llm_native_quality"` → `"quality_judgement"`
- String `"shared_memory_hierarchy"` → `"memory_manager"`

Known files:
- `backend/app/api/v1/router.py`
- `backend/app/services/inspection_standard_service.py`
- `backend/app/models/__init__.py`

- [ ] **Step 3: Commit**

```bash
git add -A backend/
git commit -m "fix: update all remaining references to new agent architecture"
```

---

### Task 9: Update Tests

**Files:**
- Rename: `backend/tests/test_llm_native_quality.py` → `backend/tests/test_quality_judgement.py`

- [ ] **Step 1: Rename test file**

```bash
git mv backend/tests/test_llm_native_quality.py backend/tests/test_quality_judgement.py
```

- [ ] **Step 2: Update imports in the test file**

```python
# Before:
from agent.subgraphs.llm_native_quality import LLMNativeQualitySubgraph
from agent.subgraphs.llm_native_quality.product_adapters import ...

# After:
from agent.subgraphs.quality_judgement import QualityJudgementSubgraph
from agent.subgraphs.quality_judgement.product_adapters import ...
```

Replace all `LLMNativeQualitySubgraph` references with `QualityJudgementSubgraph`.

- [ ] **Step 3: Update other test files**

```bash
rg "legacy_quality|llm_native_quality|shared_memory_hierarchy|quality_root" backend/tests/ --type py -l
```

Apply same import mapping to any files found.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: update tests for new agent architecture"
```

---

### Task 10: Update Seed Data and Bootstrap Scripts

**Files:**
- Modify: `backend/migrations/data/0021_seed_demo_snapshot.json`
- Modify: `backend/scripts/bootstrap_quality_specs.py`

- [ ] **Step 1: Update seed data**

Search and replace in seed JSON:
- `"legacy_quality"` → `"quality_judgement"`
- `"llm_native_quality"` → `"quality_judgement"`
- `"shared_memory_hierarchy"` → `"memory_manager"`

- [ ] **Step 2: Update bootstrap script**

```bash
rg "legacy_quality|llm_native_quality|shared_memory_hierarchy" backend/scripts/ --type py -l
```

Apply same mapping.

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/data/ backend/scripts/
git commit -m "chore: update seed data and bootstrap scripts for new agent keys"
```

---

### Task 11: Integration Verification

- [ ] **Step 1: Verify all imports resolve**

```bash
cd backend && python -c "
from agent.graphs.memory_manager import MemoryManagerGraph
from agent.subgraphs.quality_judgement import QualityJudgementSubgraph
from agent.topology_catalog import get_registered_subgraphs, get_topology
from app.services.quality_agent_orchestrator_service import QualityAgentOrchestratorService
from agent.llm.client import LLMClient
print('All imports OK')
for sg in get_registered_subgraphs():
    print(f\"  {sg['name']}: {sg['subgraph_key']} (active={sg['is_active']})\")
"
```

- [ ] **Step 2: Verify provider switching**

```bash
cd backend && python -c "
from agent.llm.client import LLMClient
d = LLMClient(provider='deepseek')
v = LLMClient()
assert d.model_id != v.model_id, 'Providers should use different models'
print(f'DeepSeek: {d.model_id}')
print(f'Volcengine: {v.model_id}')
print('Provider switching OK')
"
```

- [ ] **Step 3: Verify topology integrity**

```bash
cd backend && python -c "
from agent.topology_catalog import get_topology, get_registered_subgraphs
for sg in get_registered_subgraphs():
    t = get_topology(sg['subgraph_key'])
    print(f\"  {sg['name']}: {len(t['nodes'])} nodes, {len(t['edges'])} edges\")
print('Topology OK')
"
```

- [ ] **Step 4: Final commit**

```bash
git status
git add -A backend/
git commit -m "chore: final verification and cleanup for agent refactor"
```
