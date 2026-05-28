# 论文查非 5 阶段升级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将论文查非从基础格式检查升级为模板驱动的规则化审阅系统，去掉冗余模型调用、增强规则引擎、建立模板条款 RAG 索引、增强文档解析能力。

**Architecture:** 规则引擎负责判断 → RAG 负责提供模板条款依据 → 模型只负责解释和生成 AI Review 报告 → 前端展示成功或明确失败。单次模型调用，无兜底策略。

**Tech Stack:** Python 3.12+, SQLAlchemy 2.0 async, Qdrant (httpx REST), Alembic, python-docx, PyMuPDF

---

## 文件结构总览

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/agent/router/executors/file_executor.py` | 修改 | 跳过 _try_chat_summary，AI Review 纳入主流程 |
| `backend/agent/tools/paper_format_checker.py` | 修改 | 扩展 RuleIssue 字段，新增规则 |
| `backend/agent/tools/paper_review_ai.py` | 修改 | 删除 fallback，模型失败抛异常，约束 prompt |
| `backend/agent/tools/paper_review_evidence.py` | 修改 | Evidence Pack 标准化 |
| `backend/agent/tools/paper_template_evidence.py` | 重写 | 改为按 issue 检索 RAG 条款 |
| `backend/agent/tools/paper_format_templates.py` | 修改 | 模板配置扩展 |
| `backend/app/services/paper_review_enrichment_service.py` | 修改 | 不吞异常 |
| `backend/app/models/paper_template.py` | 新建 | MySQL ORM 模型 |
| `backend/app/repositories/paper_template_repo.py` | 新建 | 模板和条款仓储 |
| `backend/agent/tools/paper_template_indexer.py` | 新建 | 写作指南条款切分与索引 |
| `backend/app/services/paper_template_index_service.py` | 新建 | 模板条款入 MySQL + Qdrant |
| `backend/agent/rag/paper_template_clause_retriever.py` | 新建 | Qdrant 检索模板条款 |
| `backend/app/api/v1/paper_templates.py` | 新建 | 模板导入、重建索引 API |
| `backend/agent/tools/paper_docx_parser.py` | 新建 | 增强 DOCX 解析 |
| `backend/agent/tools/paper_pdf_parser.py` | 新建 | 增强 PDF 解析 |
| `backend/app/core/config.py` | 修改 | 新增 paper_template Qdrant collection 配置 |

---

### Task P1-1: 删除 _fallback_output，新增 PaperReviewModelError

**Files:**
- Modify: `backend/agent/tools/paper_review_ai.py`

- [ ] **Step 1: 新增异常类，删除 _fallback_output，改为抛异常**

在 `paper_review_ai.py` 顶部新增异常类：

```python
class PaperReviewModelError(RuntimeError):
    """论文查非 AI Review 模型调用失败。不上报兜底结果，直接向前端报错。"""
    pass
```

修改 `generate_ai_review_output()` — 所有 `return _fallback_output(...)` 改为 `raise PaperReviewModelError(...)`：

```python
async def generate_ai_review_output(
    *,
    evidence_pack: dict[str, Any],
    guide_evidence: dict[str, Any] | None = None,
    query: str,
    db_session: Any,
    org_id: str,
    trace_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    if db_session is None:
        raise PaperReviewModelError("未传入数据库会话，无法读取模型配置。")

    try:
        models = await ModelConfigService(db_session, org_id).list_runtime_models()
        runtime = await LLMGateway().select_runtime(
            models=models,
            model_types={"chat"},
            reserve=False,
        )
    except Exception as exc:
        raise PaperReviewModelError(f"读取模型配置失败：{exc}") from exc

    if not runtime:
        raise PaperReviewModelError("未找到可用的聊天模型配置。")

    prompt = await _resolve_system_prompt(org_id=org_id)
    client = LLMClient(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        model_id=runtime.get("model_id"),
        provider=runtime.get("provider"),
        trace_id=trace_id,
        task_id=task_id,
        org_id=org_id,
        input_price_per_million=runtime.get("input_price_per_million"),
        output_price_per_million=runtime.get("output_price_per_million"),
    )

    try:
        messages = build_ai_review_messages(
            query=query,
            evidence_pack=evidence_pack,
            guide_evidence=guide_evidence,
            system_prompt=prompt,
        )
        response = await client.chat(
            messages,
            temperature=0.2,
            observation_name="paper.ai_review",
            observation_metadata={
                "prompt_key": PROMPT_KEY,
                "document_type": (evidence_pack.get("document") or {}).get("document_type"),
                "template_id": (evidence_pack.get("document") or {}).get("template_id"),
            },
        )
    except Exception as exc:
        raise PaperReviewModelError(f"Ai-Review 模型调用失败：{exc}") from exc

    normalized = normalize_ai_review_output(response)
    if not normalized.get("markdown_report"):
        raise PaperReviewModelError("Ai-Review 返回内容缺少 markdown_report。")

    if isinstance(response.get("__meta__"), dict):
        normalized["model_meta"] = response["__meta__"]

    normalized["model_used"] = True
    if guide_evidence:
        normalized.setdefault("review_sources", {})
        normalized["review_sources"] = {
            **dict(normalized.get("review_sources") or {}),
            "rule_template": str((evidence_pack.get("document") or {}).get("template_id") or ""),
            "writing_guide": str(guide_evidence.get("file_name") or ""),
        }
        normalized.setdefault("limitations", []).append(
            f"已参考模板写作指南：{guide_evidence.get('file_name', '')}"
        )
    return normalized
```

删除 `_fallback_output()` 函数。

- [ ] **Step 2: 验证语法正确**

Run: `cd backend && python -c "from agent.tools.paper_review_ai import PaperReviewModelError, generate_ai_review_output; print('OK')"`

- [ ] **Step 3: Commit**

---

### Task P1-2: 跳过论文查非的 _try_chat_summary

**Files:**
- Modify: `backend/agent/router/executors/file_executor.py:69-73`

- [ ] **Step 1: 论文查非路径跳过模型总结**

修改 `FileExecutor.execute()` 中 model_summary 调用：

```python
# 原代码第 73 行:
# model_summary = await self._try_chat_summary(parsed_files, state, request, db_session=db_session)

# 改为:
model_summary = None
if step.capability_key != "file.paper_format_check":
    model_summary = await self._try_chat_summary(parsed_files, state, request, db_session=db_session)
```

- [ ] **Step 2: Commit**

---

### Task P1-3: AI Review 纳入主流程，删除异步 enrichment

**Files:**
- Modify: `backend/agent/router/executors/file_executor.py:80-117`
- Modify: `backend/app/services/paper_review_enrichment_service.py`
- Modify: `backend/app/services/quality_agent_orchestrator_service.py:339-409`

- [ ] **Step 1: 在 file_executor.py 中，论文查非路径内联调用 AI Review**

修改 `execute()` 中 `step.capability_key == "file.paper_format_check"` 分支：

```python
if step.capability_key == "file.paper_format_check":
    merged = self._merge_paper_reports(paper_reports, unsupported=unsupported, parsed_files=parsed_files, model_summary=model_summary)
    self._finalize_paper_report_counts(merged)

    # 构造 Evidence Pack
    review_evidence_pack = {}
    if merged.get("issues") and parsed_files:
        parsed_for_evidence = {
            **{k: v for k, v in parsed_files[0].get("metadata", {}).items()},
            "kind": parsed_files[0].get("kind"),
            "text": parsed_files[0].get("text", ""),
        }
        from agent.tools.paper_review_evidence import build_review_evidence_pack
        review_evidence_pack = build_review_evidence_pack(
            parsed=parsed_for_evidence,
            check_result=merged,
            file_name=str(parsed_files[0].get("name") or ""),
        )

    # 加载模板指南 evidence（走 RAG 或 fallback 全文本）
    guide_evidence = None
    effective_template_id = str(merged.get("template_id") or template_id or "")
    if effective_template_id:
        from agent.tools.paper_template_evidence import load_writing_guide_evidence
        guide_evidence = load_writing_guide_evidence(effective_template_id)
        if guide_evidence:
            merged["writing_guide_evidence"] = guide_evidence
            if guide_evidence.get("error"):
                merged.setdefault("template_errors", []).append(
                    guide_evidence.get("error_message", "模板文件加载失败")
                )

    # 同步调用 AI Review
    ai_review_output = None
    try:
        from agent.tools.paper_review_ai import generate_ai_review_output, PaperReviewModelError
        ai_review_output = await generate_ai_review_output(
            evidence_pack=review_evidence_pack,
            guide_evidence=guide_evidence if guide_evidence and not guide_evidence.get("error") else None,
            query=state.original_query,
            db_session=db_session,
            org_id=request.org_id,
            trace_id=state.trace_id or state.workflow_run_id or state.request_id,
            task_id=state.session_id,
        )
        merged["ai_review_output"] = ai_review_output
        merged["model_used"] = True
        if ai_review_output.get("summary"):
            merged["summary"] = str(ai_review_output.get("summary"))
            merged["model_summary"] = str(ai_review_output.get("summary"))
        ai_limitations = [str(item) for item in list(ai_review_output.get("limitations") or []) if str(item).strip()]
        if ai_limitations:
            merged["limitations"] = list(dict.fromkeys([*list(merged.get("limitations") or []), *ai_limitations]))
    except PaperReviewModelError:
        raise  # 直接向上传播，前端展示错误
    except Exception as exc:
        raise PaperReviewModelError(f"论文查非 AI Review 失败：{exc}") from exc

    # 生成报告文件
    try:
        report_files = await self._save_report_files(
            merged=merged,
            state=state,
            request=request,
        )
        merged["report_files"] = report_files
    except Exception:
        merged["report_files"] = []

    content = merged
    obs_summary = str(merged.get("summary") or "") or "已完成论文查非分析"
    confidence = 0.8
```

注意：需要在 `execute()` 顶部 import `PaperReviewModelError`。

- [ ] **Step 2: 简化 paper_review_enrichment_service.py — 改为直接抛异常**

```python
class PaperReviewEnrichmentService:
    async def enrich(
        self,
        *,
        paper_report: dict[str, Any],
        request: NormalizedRequest,
        emit_patch: Callable[..., Awaitable[None]] | None = None,
        db_session: Any = None,
    ) -> dict[str, Any]:
        """Deprecated: AI Review 已移到主流程。保留此方法用于向后兼容，直接返回原报告。"""
        merged = dict(paper_report or {})
        merged.pop("enrichment_payload", None)
        FileExecutor._finalize_paper_report_counts(merged)
        if callable(emit_patch):
            await emit_patch(
                content=str(merged.get("chat_advice") or ""),
                message_type="file_answer",
                payload={"paper_format_report": merged},
            )
        return merged
```

- [ ] **Step 3: 简化 quality_agent_orchestrator_service.py 的 _enqueue_paper_review_enrichment**

保持调用不报错即可，AI Review 已在主流程完成。如果 enrichment_payload 不存在则跳过。

- [ ] **Step 4: Commit**

---

### Task P2-1: RuleIssue 增加 expected/actual/source_clause_ids/parser_confidence

**Files:**
- Modify: `backend/agent/tools/paper_format_checker.py`

- [ ] **Step 1: 扩展 RuleIssue dataclass**

```python
@dataclass(frozen=True)
class RuleIssue:
    code: str
    title: str
    severity: str
    category: str
    message: str
    evidence: str
    location: dict[str, Any]
    suggestion: str
    expected: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None
    source_clause_ids: list[str] | None = None
    parser_confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        result = {
            "code": self.code,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "evidence": self.evidence,
            "location": dict(self.location),
            "suggestion": self.suggestion,
            "parser_confidence": self.parser_confidence,
        }
        if self.expected:
            result["expected"] = dict(self.expected)
        if self.actual:
            result["actual"] = dict(self.actual)
        if self.source_clause_ids:
            result["source_clause_ids"] = list(self.source_clause_ids)
        return result
```

- [ ] **Step 2: 更新现有规则调用以填充新字段**

逐条更新 `_check_docx_style()` 和 `_check_template_rules()` 中的 RuleIssue 构造，添加 `expected`/`actual`/`parser_confidence` 字段。

示例 — 页边距规则：
```python
RuleIssue(
    code="style.margin_outlier",
    title="页边距疑似异常",
    severity="medium",
    category="style",
    message=f"{margin_key}={value}cm，超出常见论文模板范围。",
    evidence=f"{margin_key}={value}",
    location={"page_layout": margin_key},
    suggestion="核对页边距设置是否符合模板要求。",
    expected={"margin_cm": 2.5},
    actual={margin_key: value},
    parser_confidence="high",
)
```

示例 — 字体规则：
```python
RuleIssue(
    code="template.body_font_mismatch",
    title="正文字体或字号与学校模板不一致",
    severity="medium",
    category="template",
    message="识别到正文段落字体或字号与模板建议不一致。",
    evidence=f"段落 {paragraph.get('index')}: font={paragraph.get('font_name')}, size={paragraph.get('font_size_pt')}",
    location={**_issue_location_from_paragraph(paragraph), "template_id": template_id},
    suggestion="按学校模板统一正文字体和字号。",
    expected={"zh_font": "宋体", "en_font": "Times New Roman", "font_size_pt": 12},
    actual={"font_name": paragraph.get("font_name"), "font_size_pt": paragraph.get("font_size_pt")},
    source_clause_ids=["cqupt_2022_body_font"],
    parser_confidence="medium",
)
```

- [ ] **Step 3: Commit**

---

### Task P2-2: 更新 AI Review prompt 约束模型行为

**Files:**
- Modify: `backend/agent/tools/paper_review_ai.py`

- [ ] **Step 1: 替换 DEFAULT_AI_REVIEW_PROMPT**

```python
DEFAULT_AI_REVIEW_PROMPT = """你是论文格式与规范审阅助手。

你只能基于 rule_report 中的 issues、evidence、retrieved_template_clauses 生成审阅报告。
规则引擎已经完成客观判断，你不需要重新判断论文是否违规。

严格规则：
1. 每条 issue 必须给出：问题描述 → 违规证据 → 模板依据 → 影响 → 具体修改方案
2. 模板依据必须来自 retrieved_template_clauses，不得编造模板条款
3. 不得新增没有 evidence 支撑的问题
4. 不得编造论文内容、学校名称、参考文献信息
5. 没有证据支撑的问题必须拒绝输出
6. 输出必须是合法 JSON，不要输出 JSON 之外的任何文本

返回 JSON 格式（所有字段必填）：
{
  "answer": "不超过200字的简要总结",
  "summary": "一句话结论",
  "markdown_report": "完整 Markdown 审阅报告，包含总体评价、逐问题详述、模板对比结论、局限性说明、修改优先级建议。不得少于500字。",
  "issues": [
    {
      "code": "issue code",
      "title": "问题简述",
      "severity": "high|medium|low",
      "location": "具体段落/章节位置",
      "evidence": "实际违规证据文本",
      "template_basis": "模板条款依据（引用自retrieved_template_clauses）",
      "impact": "不符合模板/规范的后果说明",
      "suggestion": "具体的、可执行的修改建议",
      "need_human_review": false
    }
  ],
  "limitations": ["当前检查的局限性说明"],
  "download_title": "论文查非与格式审阅报告"
}"""
```

- [ ] **Step 2: 更新 build_ai_review_messages 构造更结构化的输入**

```python
def build_ai_review_messages(
    *,
    query: str,
    evidence_pack: dict[str, Any],
    guide_evidence: dict[str, Any] | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    document = evidence_pack.get("document") or {}
    issues = list(evidence_pack.get("issues") or [])
    # 精简 issues，控制 token
    trimmed_issues = _trim_issues_for_model(issues, max_high=20, max_medium=10, max_low_abstract=5)
    
    clauses_section = ""
    if guide_evidence and not guide_evidence.get("error"):
        clauses = guide_evidence.get("clauses") or []
        if clauses:
            clauses_section = (
                "\n\n检索到的模板条款（你只能引用这些条款作为依据）：\n"
                f"{json.dumps(clauses, ensure_ascii=False, default=str)}"
            )
    
    model_input = {
        "task": {"type": "paper_format_ai_review", "language": "zh-CN", "output_format": "json"},
        "document": document,
        "rule_report": {
            "score": evidence_pack.get("score", 0),
            "issue_count": len(issues),
            "high_count": sum(1 for i in issues if i.get("severity") == "high"),
            "medium_count": sum(1 for i in issues if i.get("severity") == "medium"),
            "low_count": sum(1 for i in issues if i.get("severity") == "low"),
            "issues": trimmed_issues,
        },
        "style_summary": evidence_pack.get("style_summary") or {},
        "limitations": list(evidence_pack.get("limitations") or []),
    }
    
    user_content = (
        f"当前日期：{_TODAY}\n\n"
        f"用户问题：\n{query or '请进行论文查非与格式审阅'}\n\n"
        f"Review Evidence Pack：\n{json.dumps(model_input, ensure_ascii=False, default=str)}"
        f"{clauses_section}\n\n"
        "请基于以上证据生成完整审阅报告 JSON。"
        "markdown_report 必须详细充实，不少于500字。"
        "不得编造任何不在 issues 或 template_clauses 中的内容。"
        "不要输出 JSON 以外的文本。"
    )
    return [
        {"role": "system", "content": system_prompt or DEFAULT_AI_REVIEW_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _trim_issues_for_model(
    issues: list[dict[str, Any]],
    max_high: int = 20,
    max_medium: int = 10,
    max_low_abstract: int = 5,
) -> list[dict[str, Any]]:
    high = [i for i in issues if i.get("severity") == "high"][:max_high]
    medium = [i for i in issues if i.get("severity") == "medium"][:max_medium]
    low = [i for i in issues if i.get("severity") == "low"]
    low_abstract = low[:max_low_abstract]
    if len(low) > max_low_abstract:
        low_abstract.append({
            "code": "summary.low_severity_omitted",
            "title": f"另有 {len(low) - max_low_abstract} 个低严重性问题",
            "severity": "low",
            "message": f"完整列表共 {len(low)} 项低严重性问题，此处仅展示前 {max_low_abstract} 项。",
        })
    return high + medium + low_abstract
```

删除 `build_writing_guide_review_messages()` 和 `merge_ai_review_outputs()` — 不再需要两次模型调用。

- [ ] **Step 3: Commit**

---

### Task P3-1: 创建 MySQL 模型 paper_template

**Files:**
- Create: `backend/app/models/paper_template.py`

- [ ] **Step 1: 创建模型文件**

```python
from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, UUIDBinary


class PaperTemplate(Base, TimestampMixin):
    __tablename__ = "paper_templates"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    template_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    degree_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_bucket: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PaperTemplateClause(Base, TimestampMixin):
    __tablename__ = "paper_template_clauses"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    template_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    clause_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_clause_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clause_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rule_codes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(191), nullable=True)


class PaperTemplateRule(Base, TimestampMixin):
    __tablename__ = "paper_template_rules"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    template_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    expected: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_clause_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

- [ ] **Step 2: Commit**

---

### Task P3-2: 创建数据库迁移

**Files:**
- Create: `backend/migrations/versions/0073_add_paper_template_tables.py`

- [ ] **Step 1: 创建迁移文件**（略，标准 Alembic 迁移创建三张表加索引）

- [ ] **Step 2: Commit**

---

### Task P3-3: 创建 Repository

**Files:**
- Create: `backend/app/repositories/paper_template_repo.py`

- [ ] **Step 1: 创建仓储**

```python
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_template import PaperTemplate, PaperTemplateClause, PaperTemplateRule
from app.repositories.base import BaseRepository


class PaperTemplateRepository(BaseRepository[PaperTemplate]):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_template_id(self, template_id: str) -> PaperTemplate | None:
        stmt = select(PaperTemplate).where(PaperTemplate.template_id == template_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_template(self, template: PaperTemplate) -> PaperTemplate:
        existing = await self.get_by_template_id(template.template_id)
        if existing:
            for key, value in template.__dict__.items():
                if key != "id" and not key.startswith("_"):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        self._session.add(template)
        await self._session.flush()
        await self._session.refresh(template)
        return template


class PaperTemplateClauseRepository(BaseRepository[PaperTemplateClause]):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_template_and_clause(self, template_id: str, clause_id: str) -> PaperTemplateClause | None:
        stmt = select(PaperTemplateClause).where(
            PaperTemplateClause.template_id == template_id,
            PaperTemplateClause.clause_id == clause_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_template(self, template_id: str) -> list[PaperTemplateClause]:
        stmt = select(PaperTemplateClause).where(PaperTemplateClause.template_id == template_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_template(self, template_id: str) -> int:
        result = await self._session.execute(
            select(PaperTemplateClause).where(PaperTemplateClause.template_id == template_id)
        )
        clauses = result.scalars().all()
        for clause in clauses:
            await self._session.delete(clause)
        return len(clauses)

    async def upsert_clause(self, clause: PaperTemplateClause) -> PaperTemplateClause:
        existing = await self.get_by_template_and_clause(clause.template_id, clause.clause_id)
        if existing:
            for key, value in clause.__dict__.items():
                if key != "id" and not key.startswith("_"):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        self._session.add(clause)
        await self._session.flush()
        await self._session.refresh(clause)
        return clause


class PaperTemplateRuleRepository(BaseRepository[PaperTemplateRule]):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def list_enabled_by_template(self, template_id: str) -> list[PaperTemplateRule]:
        stmt = select(PaperTemplateRule).where(
            PaperTemplateRule.template_id == template_id,
            PaperTemplateRule.enabled == True,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_template(self, template_id: str) -> int:
        result = await self._session.execute(
            select(PaperTemplateRule).where(PaperTemplateRule.template_id == template_id)
        )
        rules = result.scalars().all()
        for rule in rules:
            await self._session.delete(rule)
        return len(rules)

    async def upsert_rule(self, rule: PaperTemplateRule) -> PaperTemplateRule:
        stmt = select(PaperTemplateRule).where(
            PaperTemplateRule.template_id == rule.template_id,
            PaperTemplateRule.rule_code == rule.rule_code,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in rule.__dict__.items():
                if key != "id" and not key.startswith("_"):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        self._session.add(rule)
        await self._session.flush()
        await self._session.refresh(rule)
        return rule
```

- [ ] **Step 2: Commit**

---

### Task P3-4: 创建 Qdrant Clause Retriever

**Files:**
- Create: `backend/agent/rag/paper_template_clause_retriever.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: 新增配置项**

在 `config.py` 的 Settings 中添加：
```python
paper_template_qdrant_collection: str = "paper_template_clauses"
```

- [ ] **Step 2: 创建 retriever**

```python
from __future__ import annotations

from typing import Any

import httpx

from agent.rag.embedder import Embedder
from app.core.config import settings


class PaperTemplateClauseRetriever:
    def __init__(self, *, trace_id: str | None = None, task_id: str | None = None, org_id: str | None = None) -> None:
        self._embedder = Embedder(trace_id=trace_id, task_id=task_id, org_id=org_id)
        self._qdrant_url = settings.qdrant_url.rstrip("/")
        self._qdrant_api_key = settings.qdrant_api_key
        self._collection = settings.paper_template_qdrant_collection

    async def retrieve_for_issues(
        self,
        *,
        template_id: str,
        issues: list[dict[str, Any]],
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        """根据 issues 检索最相关的模板条款。"""
        if not issues:
            return []

        query_text = _build_retrieval_query(issues)
        try:
            vector = await self._embedder.embed(query_text)
        except Exception:
            return []

        if not vector:
            return []

        payload: dict[str, Any] = {
            "vector": vector,
            "limit": top_k,
            "with_payload": True,
            "filter": {
                "must": [
                    {"key": "template_id", "match": {"value": template_id}}
                ]
            },
        }

        headers: dict[str, str] = {}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key

        try:
            async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
                response = await client.post(
                    f"{self._qdrant_url}/collections/{self._collection}/points/search",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            return []

        points = data.get("result") or []
        return [
            {
                "clause_id": p["payload"].get("clause_id", ""),
                "section_title": p["payload"].get("section_title", ""),
                "clause_title": p["payload"].get("clause_title", ""),
                "text": p["payload"].get("clause_text", ""),
                "category": p["payload"].get("category", ""),
                "target_type": p["payload"].get("target_type", ""),
                "rule_codes": p["payload"].get("rule_codes", []),
                "severity": p["payload"].get("severity", ""),
                "score": float(p.get("score", 0.0)),
            }
            for p in points
            if p.get("score", 0) > 0.5
        ]

    async def retrieve_by_clause_ids(
        self,
        *,
        template_id: str,
        clause_ids: list[str],
    ) -> list[dict[str, Any]]:
        """按 clause_id 精确检索条款（用于前端展示或调试）。"""
        # 直接从 Qdrant 按 payload filter 检索
        payload: dict[str, Any] = {
            "vector": [0.0] * 1024,  # dummy vector, filter-based search
            "limit": len(clause_ids),
            "with_payload": True,
            "filter": {
                "must": [
                    {"key": "template_id", "match": {"value": template_id}},
                    {"key": "clause_id", "match": {"any": clause_ids}},
                ]
            },
        }
        # ... (implementation similar to above)


def _build_retrieval_query(issues: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for issue in issues:
        parts.append(f"{issue.get('code', '')} {issue.get('title', '')} {issue.get('category', '')}")
        if issue.get("target_type"):
            parts.append(str(issue["target_type"]))
    return " ".join(parts)[:2000]
```

- [ ] **Step 3: Commit**

---

### Task P3-5: 创建模板索引服务

**Files:**
- Create: `backend/agent/tools/paper_template_indexer.py`
- Create: `backend/app/services/paper_template_index_service.py`

- [ ] **Step 1: 创建 clause 切分器 (paper_template_indexer.py)**

```python
"""写作指南条款切分与索引。"""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from agent.tools.file_parsers import parse_file_content


def split_guide_into_clauses(
    parsed: dict[str, Any],
    *,
    template_id: str,
    source_file_name: str = "writing-guide.docx",
) -> list[dict[str, Any]]:
    """将解析后的写作指南按标题层级切分为 clause 列表。"""
    paragraphs = list(parsed.get("paragraphs") or [])
    clauses: list[dict[str, Any]] = []
    current_section = ""
    current_clause_parts: list[str] = []
    current_clause_title = ""
    current_target_type = ""
    current_category = ""

    for p in paragraphs:
        text = str(p.get("text") or "").strip()
        if not text:
            continue

        heading_level = p.get("heading_level") or 0
        if heading_level >= 1:
            # 保存上一个 clause
            if current_clause_parts:
                clauses.append(_build_clause(
                    template_id=template_id,
                    section_title=current_section,
                    clause_title=current_clause_title,
                    clause_text="\n".join(current_clause_parts),
                    target_type=current_target_type,
                    category=current_category,
                    source_file_name=source_file_name,
                ))
                current_clause_parts = []

            if heading_level == 1:
                current_section = text
            current_clause_title = text
            current_target_type, current_category = _infer_target_and_category(text)
        else:
            current_clause_parts.append(text)

    # 最后一个 clause
    if current_clause_parts:
        clauses.append(_build_clause(
            template_id=template_id,
            section_title=current_section,
            clause_title=current_clause_title,
            clause_text="\n".join(current_clause_parts),
            target_type=current_target_type,
            category=current_category,
            source_file_name=source_file_name,
        ))

    return clauses


def _build_clause(
    *,
    template_id: str,
    section_title: str,
    clause_title: str,
    clause_text: str,
    target_type: str,
    category: str,
    source_file_name: str,
) -> dict[str, Any]:
    clause_id = _stable_clause_id(template_id, section_title, clause_title)
    source_hash = hashlib.sha256(clause_text.encode()).hexdigest()[:32]
    normalized = " ".join(clause_text.split())

    text_for_vector = f"{section_title} {clause_title} {normalized} {target_type} {category}"
    
    return {
        "clause_id": clause_id,
        "section_title": section_title,
        "clause_title": clause_title,
        "clause_text": clause_text,
        "normalized_text": normalized,
        "vector_text": text_for_vector[:2000],
        "target_type": target_type,
        "category": category,
        "rule_codes": _infer_rule_codes(target_type, category, normalized),
        "source_file_name": source_file_name,
        "source_hash": source_hash,
    }


def _stable_clause_id(template_id: str, section: str, title: str) -> str:
    raw = f"{template_id}:{section}:{title}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def _infer_target_and_category(text: str) -> tuple[str, str]:
    mapping = {
        "封面": ("cover", "structure"),
        "声明": ("statement", "structure"),
        "摘要": ("abstract", "structure"),
        "关键词": ("keywords", "structure"),
        "目录": ("toc", "structure"),
        "正文": ("body_paragraph", "style"),
        "字体": ("body_paragraph", "style"),
        "字号": ("body_paragraph", "style"),
        "行距": ("body_paragraph", "style"),
        "标题": ("heading", "style"),
        "页边距": ("page_layout", "style"),
        "页眉": ("header_footer", "style"),
        "页脚": ("header_footer", "style"),
        "页码": ("page_number", "style"),
        "图": ("figure", "structure"),
        "表": ("table", "structure"),
        "公式": ("formula", "structure"),
        "参考文献": ("references", "structure"),
        "引用": ("citation", "structure"),
        "致谢": ("acknowledgement", "structure"),
        "附录": ("appendix", "structure"),
    }
    for keyword, (target, cat) in mapping.items():
        if keyword in text:
            return target, cat
    return ("body_paragraph", "style")


def _infer_rule_codes(target_type: str, category: str, text: str) -> list[str]:
    codes = []
    if "字体" in text:
        codes.append(f"template.{target_type}.font_mismatch")
    if "字号" in text or "小四" in text or "号" in text:
        codes.append(f"template.{target_type}.font_size_mismatch")
    if "行距" in text or "倍行距" in text:
        codes.append(f"template.{target_type}.line_spacing_mismatch")
    return codes
```

- [ ] **Step 2: 创建索引入口服务 (paper_template_index_service.py)**

```python
from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from agent.rag.embedder import Embedder
from agent.tools.file_parsers import parse_file_content
from agent.tools.paper_template_indexer import split_guide_into_clauses
from app.core.config import settings
from app.models.paper_template import PaperTemplate, PaperTemplateClause, PaperTemplateRule
from app.repositories.paper_template_repo import (
    PaperTemplateClauseRepository,
    PaperTemplateRepository,
    PaperTemplateRuleRepository,
)


class PaperTemplateIndexService:
    def __init__(self, session: AsyncSession, *, org_id: str | None = None):
        self._session = session
        self._template_repo = PaperTemplateRepository(session)
        self._clause_repo = PaperTemplateClauseRepository(session)
        self._rule_repo = PaperTemplateRuleRepository(session)
        self._embedder = Embedder(org_id=org_id)
        self._qdrant_url = settings.qdrant_url.rstrip("/")
        self._qdrant_api_key = settings.qdrant_api_key
        self._collection = settings.paper_template_qdrant_collection

    async def index_template(
        self,
        *,
        template_id: str,
        template_name: str,
        guide_file_bytes: bytes,
        guide_file_name: str = "writing-guide.docx",
        school_name: str | None = None,
        degree_type: str | None = None,
        version: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        # 1. 解析写作指南
        parsed = parse_file_content(guide_file_name, guide_file_bytes)

        # 2. 切分 clause
        clauses = split_guide_into_clauses(
            parsed,
            template_id=template_id,
            source_file_name=guide_file_name,
        )

        # 3. 写入 MySQL
        template = PaperTemplate(
            template_id=template_id,
            template_name=template_name,
            school_name=school_name,
            degree_type=degree_type,
            version=version,
            description=description,
        )
        await self._template_repo.upsert_template(template)

        # 清理旧数据
        await self._clause_repo.delete_by_template(template_id)
        await self._rule_repo.delete_by_template(template_id)

        for clause_data in clauses:
            clause = PaperTemplateClause(
                template_id=template_id,
                clause_id=clause_data["clause_id"],
                section_title=clause_data.get("section_title", ""),
                clause_title=clause_data.get("clause_title", ""),
                clause_text=clause_data["clause_text"],
                normalized_text=clause_data.get("normalized_text", ""),
                target_type=clause_data.get("target_type", ""),
                category=clause_data.get("category", ""),
                rule_codes=clause_data.get("rule_codes", []),
                source_file_name=guide_file_name,
                source_hash=clause_data.get("source_hash", ""),
            )
            await self._clause_repo.upsert_clause(clause)

        # 4. 向量化并写入 Qdrant
        await self._ensure_qdrant_collection()
        points = []
        for clause_data in clauses:
            vector_text = clause_data.get("vector_text", clause_data["clause_text"])[:2000]
            try:
                vector = await self._embedder.embed(vector_text)
            except Exception:
                continue
            if not vector:
                continue
            points.append({
                "id": str(clause_data["clause_id"]),
                "vector": vector,
                "payload": {
                    "template_id": template_id,
                    "clause_id": clause_data["clause_id"],
                    "section_title": clause_data.get("section_title", ""),
                    "clause_title": clause_data.get("clause_title", ""),
                    "clause_text": clause_data["clause_text"],
                    "category": clause_data.get("category", ""),
                    "target_type": clause_data.get("target_type", ""),
                    "rule_codes": clause_data.get("rule_codes", []),
                    "severity": "medium",
                    "source_file_name": guide_file_name,
                },
            })

        if points:
            await self._upsert_qdrant_points(points)

        await self._session.commit()
        return {
            "template_id": template_id,
            "clause_count": len(clauses),
            "qdrant_points": len(points),
            "status": "success",
        }

    async def _ensure_qdrant_collection(self) -> None:
        headers = {"Content-Type": "application/json"}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key
        payload = {"vectors": {"size": 1024, "distance": "Cosine"}}
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}",
                json=payload,
                headers=headers,
            )

    async def _upsert_qdrant_points(self, points: list[dict[str, Any]]) -> None:
        headers = {"Content-Type": "application/json"}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key
        payload = {"points": points}
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}/points",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
```

- [ ] **Step 3: Commit**

---

### Task P3-6: 集成到主流程 — 用 RAG 替代 12000 字全文传入

**Files:**
- Modify: `backend/agent/tools/paper_template_evidence.py`
- Modify: `backend/agent/router/executors/file_executor.py`

- [ ] **Step 1: 重写 paper_template_evidence.py**

```python
"""加载模板指南 evidence。优先走 RAG 检索相关条款，fallback 走全文截断（兼容旧模板）。"""
from __future__ import annotations

from typing import Any

from agent.tools.paper_format_templates import get_paper_template


async def load_writing_guide_evidence(
    template_id: str | None,
    *,
    issues: list[dict[str, Any]] | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
    org_id: str | None = None,
    max_chars: int = 12000,
) -> dict[str, Any] | None:
    """加载模板写作指南 evidence。
    
    如果有 issues 且 Qdrant 可用，按 issue 检索相关条款。
    否则 fallback 到全文截断（兼容未索引的模板）。
    """
    template = get_paper_template(template_id)
    if template is None:
        return None

    # 尝试 RAG 检索
    if issues:
        try:
            from agent.rag.paper_template_clause_retriever import PaperTemplateClauseRetriever
            retriever = PaperTemplateClauseRetriever(
                trace_id=trace_id, task_id=task_id, org_id=org_id
            )
            retrieved = await retriever.retrieve_for_issues(
                template_id=str(template.get("template_id") or template_id),
                issues=issues,
                top_k=10,
            )
            if retrieved:
                return {
                    "template_id": str(template.get("template_id") or template_id),
                    "template_name": str(template.get("name") or ""),
                    "source": "qdrant_rag",
                    "clauses": retrieved,
                    "clause_count": len(retrieved),
                }
        except Exception:
            pass  # RAG 不可用时 fallback 到全文

    # Fallback: 从对象存储加载全文
    return _load_full_text_evidence(template, template_id, max_chars)


def _load_full_text_evidence(
    template: dict[str, Any],
    template_id: str | None,
    max_chars: int,
) -> dict[str, Any] | None:
    """兼容旧逻辑：从对象存储加载写作指南全文（截断）。"""
    storage = dict(template.get("storage") or {})
    bucket = str(storage.get("bucket") or "").strip()
    guide = _template_file_by_role(template, "writing_guide")
    if not storage or not bucket:
        return None
    if not guide:
        return _error_result(template, template_id, "模板存储配置中缺少 writing_guide 文件定义")

    object_key = str(guide.get("object_key") or "").strip()
    file_name = str(guide.get("file_name") or "writing-guide.docx")
    if not object_key:
        return _error_result(template, template_id, "模板缺少 object_key")

    try:
        from app.services.object_storage.factory import build_object_storage
        payload = build_object_storage().get_bytes(bucket=bucket, object_key=object_key)
    except Exception as exc:
        return _error_result(template, template_id, f"对象存储读取失败：{exc}")

    if payload is None:
        return _error_result(template, template_id,
            f"MinIO 中未找到文件：{file_name}（bucket={bucket}, key={object_key}）")

    content, content_type = payload
    try:
        parsed = parse_file_content(file_name, content)
    except Exception as exc:
        return _error_result(template, template_id, f"模板文件解析失败：{exc}")

    text = str(parsed.get("text") or "").strip()
    if not text:
        return _error_result(template, template_id, f"模板文件 {file_name} 解析后无文本内容")

    return {
        "template_id": str(template.get("template_id") or template_id or ""),
        "template_name": str(template.get("name") or ""),
        "source": "object_storage_full_text",
        "role": "writing_guide",
        "file_name": file_name,
        "clause_count": 0,
        "full_text": text[:max_chars],
    }


# 保留原 helper 函数 _template_file_by_role, _error_result
```

注意：`load_writing_guide_evidence` 现在变成 async 函数。

- [ ] **Step 2: 更新 file_executor.py 中 guide_evidence 调用为 await**

```python
guide_evidence = await load_writing_guide_evidence(
    effective_template_id,
    issues=merged.get("issues"),
    trace_id=state.trace_id,
    task_id=state.session_id,
    org_id=request.org_id,
)
```

- [ ] **Step 3: Commit**

---

### Task P3-7: 创建模板管理 API

**Files:**
- Create: `backend/app/api/v1/paper_templates.py`

- [ ] **Step 1: 创建 API 路由**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.paper_template_index_service import PaperTemplateIndexService

router = APIRouter(prefix="/paper-templates", tags=["paper-templates"])


@router.post("/import")
async def import_template(
    template_id: str = Form(...),
    template_name: str = Form(...),
    guide_file: UploadFile = File(...),
    school_name: str | None = Form(None),
    degree_type: str | None = Form(None),
    version: str | None = Form(None),
    description: str | None = Form(None),
    org_id: str = Form("default"),
    db: AsyncSession = Depends(get_db),
):
    """导入写作指南，切分 clause 并索引到 MySQL + Qdrant。"""
    content = await guide_file.read()
    service = PaperTemplateIndexService(db, org_id=org_id)
    result = await service.index_template(
        template_id=template_id,
        template_name=template_name,
        guide_file_bytes=content,
        guide_file_name=guide_file.filename or "writing-guide.docx",
        school_name=school_name,
        degree_type=degree_type,
        version=version,
        description=description,
    )
    return result


@router.post("/rebuild-index")
async def rebuild_index(
    template_id: str = Form(...),
    org_id: str = Form("default"),
    db: AsyncSession = Depends(get_db),
):
    """从已存储的 MySQL clause 数据重建 Qdrant 索引。"""
    # ... implementation
    pass


@router.get("/{template_id}/clauses")
async def list_clauses(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """列出模板的所有 clause。"""
    from app.repositories.paper_template_repo import PaperTemplateClauseRepository
    repo = PaperTemplateClauseRepository(db)
    clauses = await repo.list_by_template(template_id)
    return {"template_id": template_id, "clauses": [
        {"clause_id": c.clause_id, "section_title": c.section_title,
         "clause_title": c.clause_title, "category": c.category, "target_type": c.target_type}
        for c in clauses
    ]}
```

- [ ] **Step 2: 注册路由到主应用**

在 `backend/app/api/v1/__init__.py` 或主路由文件中注册。

- [ ] **Step 3: Commit**

---

### Task P4-1: 扩展规则 — 结构规则

**Files:**
- Modify: `backend/agent/tools/paper_format_checker.py`
- Modify: `backend/agent/tools/paper_format_templates.py`

- [ ] **Step 1: 重写模板规则的 required_sections 支持更细粒度的结构检查**

扩展 `_check_template_rules()` 使其支持所有结构规则 code。在模板配置中为 `cqupt_graduate_thesis_2022` 添加完整的 required_sections：

```python
"docx_rules": {
    "required_sections": [
        {"key": "cover", "label": "封面", "aliases": ["封面", "硕士学位论文"], "severity": "high", "match_mode": "heading_or_text"},
        {"key": "originality_statement", "label": "独创性声明", "aliases": ["独创性声明", "原创性声明"], "severity": "high", "match_mode": "heading_or_text"},
        {"key": "authorization_statement", "label": "授权声明", "aliases": ["学位论文版权使用授权书", "授权声明"], "severity": "medium", "match_mode": "heading_or_text"},
        {"key": "cn_abstract", "label": "中文摘要", "aliases": ["摘要", "中文摘要"], "severity": "high", "match_mode": "heading_or_text"},
        {"key": "en_abstract", "label": "英文摘要", "aliases": ["Abstract", "ABSTRACT"], "severity": "high", "match_mode": "heading_or_text"},
        {"key": "cn_keywords", "label": "中文关键词", "aliases": ["关键词", "关键字"], "severity": "medium", "match_mode": "heading_or_text"},
        {"key": "en_keywords", "label": "英文关键词", "aliases": ["Keywords", "Key words"], "severity": "medium", "match_mode": "heading_or_text"},
        {"key": "toc", "label": "目录", "aliases": ["目录"], "severity": "medium", "match_mode": "heading_or_text"},
        {"key": "body", "label": "正文", "aliases": ["引言", "绪论", "研究内容", "实验结果", "结论"], "severity": "medium", "match_mode": "body_between_sections"},
        {"key": "references", "label": "参考文献", "aliases": ["参考文献"], "severity": "high", "match_mode": "heading_or_text"},
        {"key": "acknowledgements", "label": "致谢", "aliases": ["致谢", "致 謝"], "severity": "medium", "match_mode": "heading_or_text"},
        {"key": "appendix", "label": "附录", "aliases": ["附录"], "severity": "low", "match_mode": "heading_or_text"},
    ],
    # ... 其余配置不变
}
```

同时更新 `_check_docx_structure()` 中的 RuleIssue code 使用规范的命名：
- `structure.abstract_missing` → `structure.cn_abstract_missing`
- `structure.keywords_missing` → `structure.cn_keywords_missing`

- [ ] **Step 2: 增加英文摘要和英文关键词检查**

在 `_check_docx_structure()` 中：
```python
if not _contains_any(text, ["Abstract", "ABSTRACT"]):
    issues.append(RuleIssue(
        code="structure.en_abstract_missing",
        title="缺少英文摘要",
        severity="high",
        category="structure",
        message="文档中未识别到英文摘要（Abstract）。",
        evidence="未找到 Abstract 标题",
        location={"section": "en_abstract"},
        suggestion="补充英文摘要（Abstract）并按模板放在前置部分。",
        parser_confidence="high",
    ))
```

- [ ] **Step 3: Commit**

---

### Task P4-2: 扩展规则 — 标题规则、图表公式规则、参考文献规则

**Files:**
- Modify: `backend/agent/tools/paper_format_checker.py`

- [ ] **Step 1: 新增 `_check_heading_rules()`**

```python
def _check_heading_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues = []
    headings = list(parsed.get("headings") or [])
    
    # 检查编号连续性
    prev_number = None
    for heading in headings:
        text = str(heading.get("text") or "")
        match = re.match(r"^(\d+(?:\.\d+)*)\s", text)
        if match:
            current = match.group(1)
            if prev_number:
                prev_parts = prev_number.split(".")
                cur_parts = current.split(".")
                # 同级标题编号跳变检查
                if len(prev_parts) == len(cur_parts):
                    prev_num = int(prev_parts[-1])
                    cur_num = int(cur_parts[-1])
                    if cur_num > prev_num + 1:
                        issues.append(RuleIssue(
                            code="heading.numbering_discontinuous",
                            title="标题编号不连续",
                            severity="medium",
                            category="structure",
                            message=f"标题编号从 {prev_number} 跳到 {current}，可能遗漏中间章节。",
                            evidence=text,
                            location=_issue_location_from_paragraph(
                                next((p for p in list(parsed.get("paragraphs") or [])
                                      if p.get("index") == heading.get("paragraph_index")), None)
                            ),
                            suggestion="检查标题编号是否连续。",
                            parser_confidence="high",
                        ))
            prev_number = current

        # 标题末尾标点检查
        if text.endswith(tuple(_ZH_PUNCT + _EN_PUNCT)):
            issues.append(RuleIssue(
                code="heading.trailing_punctuation",
                title="标题末尾不应有标点",
                severity="low",
                category="text",
                message="标题末尾通常不应保留句末标点。",
                evidence=text,
                location=_issue_location_from_paragraph(
                    next((p for p in list(parsed.get("paragraphs") or [])
                          if p.get("index") == heading.get("paragraph_index")), None)
                ),
                suggestion="移除标题末尾标点。",
                parser_confidence="high",
            ))
    
    return issues
```

- [ ] **Step 2: 新增 `_check_figure_table_rules()`**

```python
def _check_figure_table_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues = []
    paragraphs = list(parsed.get("paragraphs") or [])
    figure_count = 0
    table_count = 0
    
    for p in paragraphs:
        text = str(p.get("text") or "").strip()
        # 检测图题格式
        if re.match(r"^(图|Fig(?:ure)?)\s*\d+", text, re.I):
            figure_count += 1
            # 图题应在图下方 — word 中无法精确判断，标记 confidence
        # 检测表题格式
        if re.match(r"^(表|Table)\s*\d+", text, re.I):
            table_count += 1
    
    # 检查图题编号连续性
    figure_numbers = []
    for p in paragraphs:
        text = str(p.get("text") or "").strip()
        m = re.match(r"^(?:图|Fig(?:ure)?)\s*(\d+)", text, re.I)
        if m:
            figure_numbers.append((int(m.group(1)), text, p))
    
    for i in range(1, len(figure_numbers)):
        if figure_numbers[i][0] != figure_numbers[i-1][0] + 1:
            issues.append(RuleIssue(
                code="figure.numbering_discontinuous",
                title="图号不连续",
                severity="medium",
                category="structure",
                message=f"图号从 {figure_numbers[i-1][0]} 跳到 {figure_numbers[i][0]}。",
                evidence=f"{figure_numbers[i-1][1]} → {figure_numbers[i][1]}",
                location=_issue_location_from_paragraph(figure_numbers[i][2]),
                suggestion="检查图号是否连续。",
                parser_confidence="medium",
            ))
            break
    
    return issues
```

- [ ] **Step 3: 新增 `_check_reference_rules()`**

```python
def _check_reference_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues = []
    text = str(parsed.get("text") or "")
    paragraphs = list(parsed.get("paragraphs") or [])
    
    # 抽取正文引用编号
    citations = re.findall(r"\[(\d+(?:[,，\-]\d+)*)\]", text)
    cited_numbers = set()
    for c in citations:
        for part in re.split(r"[,，]", c):
            part = part.strip()
            if "-" in part or "–" in part:
                try:
                    a, b = re.split(r"[-–]", part)
                    cited_numbers.update(range(int(a), int(b) + 1))
                except ValueError:
                    pass
            else:
                try:
                    cited_numbers.add(int(part))
                except ValueError:
                    pass
    
    # 抽取参考文献编号
    ref_numbers = set()
    for line in text.splitlines():
        m = re.match(r"^\[(\d+)\]", line.strip())
        if m:
            ref_numbers.add(int(m.group(1)))
    
    # 正文引用但文末缺失
    missing_in_bib = cited_numbers - ref_numbers
    if missing_in_bib:
        issues.append(RuleIssue(
            code="references.citation_missing_in_bibliography",
            title="正文引用在参考文献列表中缺失",
            severity="high",
            category="structure",
            message=f"正文中引用了编号 {sorted(missing_in_bib)[:10]}，但文末参考文献列表中未找到对应条目。",
            evidence=f"正文引用: {sorted(cited_numbers)[:20]}, 文献列表: {sorted(ref_numbers)[:20]}",
            location={"display_text": "参考文献章节"},
            suggestion="确保正文中每条引用在参考文献列表中都有对应条目。",
            parser_confidence="medium",
            expected={"cited": sorted(cited_numbers), "listed": sorted(ref_numbers)},
            actual={"missing_in_bib": sorted(missing_in_bib)},
        ))
    
    # 文末有但正文未引用
    unused = ref_numbers - cited_numbers
    if unused and len(ref_numbers) > 5:
        issues.append(RuleIssue(
            code="references.unused_reference",
            title="参考文献列表中部分文献未被引用",
            severity="low",
            category="structure",
            message=f"参考文献列表中编号 {sorted(unused)[:10]} 的条目未在正文中被引用。",
            evidence=f"未引用编号: {sorted(unused)[:10]}",
            location={"display_text": "参考文献章节"},
            suggestion="确认这些文献是否确实需要列入，或补充正文引用。",
            parser_confidence="medium",
        ))
    
    return issues
```

- [ ] **Step 4: 在 `check_paper_format()` 中调用新规则**

在 DOCX 分支添加：
```python
if document_type == "docx":
    issues.extend(_check_docx_structure(parsed))
    issues.extend(_check_docx_style(parsed))
    issues.extend(_check_text_norms(parsed))
    issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
    issues.extend(_check_heading_rules(parsed))
    issues.extend(_check_figure_table_rules(parsed))
    issues.extend(_check_reference_rules(parsed))
```

- [ ] **Step 5: Commit**

---

### Task P5-1: 增强 DOCX 解析 — 样式继承

**Files:**
- Create: `backend/agent/tools/paper_docx_parser.py`
- Modify: `backend/agent/tools/file_parsers.py`

- [ ] **Step 1: 创建增强解析器**

```python
"""增强 DOCX 解析：样式继承展开、表格、页眉页脚、引用抽取。"""
from __future__ import annotations

from io import BytesIO
from typing import Any


def parse_docx_enhanced(content: bytes) -> dict[str, Any]:
    """增强版 DOCX 解析，合并样式继承。"""
    from docx import Document
    from docx.oxml.ns import qn
    
    doc = Document(BytesIO(content))
    
    # 构建样式继承链
    style_cache = _build_style_cache(doc)
    
    paragraphs = []
    headings = []
    figure_titles = []
    
    current_section_title = ""
    current_section_level = 0
    current_section_index = 0
    current_paragraph_no = 0
    
    for index, paragraph in enumerate(doc.paragraphs):
        text = (paragraph.text or "").strip()
        style_name = str(getattr(paragraph.style, "name", "") or "")
        heading_level = _heading_level(style_name)
        
        # 字体解析（含继承）
        font_name_raw, font_name_resolved, style_source = _resolve_font(
            paragraph, style_cache, style_name
        )
        font_size_raw, font_size_resolved, size_source = _resolve_font_size(
            paragraph, style_cache, style_name
        )
        
        # 段落格式
        para_format = paragraph.paragraph_format
        line_spacing = _to_float(getattr(para_format, "line_spacing", None))
        first_line_indent = _to_pt(getattr(para_format, "first_line_indent", None))
        
        if heading_level:
            current_section_title = text
            current_section_level = heading_level
            current_section_index += 1
            current_paragraph_no = 0
        elif text:
            current_paragraph_no += 1
        
        item = {
            "index": index,
            "text": text,
            "style_name": style_name,
            "heading_level": heading_level,
            "font_name_raw": font_name_raw,
            "font_name_resolved": font_name_resolved,
            "font_style_source": style_source,
            "font_size_raw": font_size_raw,
            "font_size_resolved": font_size_resolved,
            "font_size_source": size_source,
            "line_spacing": line_spacing,
            "first_line_indent_pt": first_line_indent,
            "section_title": current_section_title,
            "section_level": current_section_level,
            "section_index": current_section_index,
            "paragraph_no": current_paragraph_no if text and not heading_level else 0,
        }
        paragraphs.append(item)
        
        if heading_level:
            headings.append({
                "text": text,
                "level": heading_level,
                "paragraph_index": index,
                "font_name": font_name_resolved or font_name_raw,
                "font_size_pt": font_size_resolved or font_size_raw,
            })
        
        if text and _is_figure_caption(text):
            figure_titles.append(text)
    
    # 表格解析
    tables = _parse_tables(doc)
    
    # 页眉页脚
    sections_data = _parse_sections_enhanced(doc)
    
    # 引用抽取
    citations = _extract_citations("\n".join(p["text"] for p in paragraphs if p["text"]))
    
    text_lines = [p["text"] for p in paragraphs if p["text"]]
    
    return {
        "kind": "docx",
        "paragraphs": paragraphs,
        "headings": headings,
        "figure_titles": figure_titles,
        "tables": tables,
        "sections": sections_data,
        "page_layout": sections_data[0] if sections_data else {},
        "citations": citations,
        "text": "\n".join(text_lines),
    }


def _build_style_cache(doc) -> dict[str, dict[str, Any]]:
    """构建样式缓存，展开样式继承链。"""
    cache = {}
    for style in doc.styles:
        style_info = {
            "name": str(style.name) if style.name else "",
            "type": str(style.type) if style.type else "",
        }
        try:
            font = style.font
            style_info["font_name"] = font.name
            style_info["font_size"] = font.size
            style_info["bold"] = font.bold
        except Exception:
            style_info["font_name"] = None
            style_info["font_size"] = None
            style_info["bold"] = None
        try:
            pf = style.paragraph_format
            style_info["line_spacing"] = _to_float(getattr(pf, "line_spacing", None))
        except Exception:
            style_info["line_spacing"] = None
        cache[str(style.name)] = style_info
    return cache


def _resolve_font(paragraph, style_cache: dict, style_name: str) -> tuple:
    """解析字体：run → paragraph style → inherited styles → document default。"""
    # 1. 尝试从 run 获取
    for run in paragraph.runs:
        if run.font.name:
            return run.font.name, run.font.name, "run"
    
    # 2. 从 paragraph style
    if style_name and style_name in style_cache:
        fn = style_cache[style_name].get("font_name")
        if fn:
            return None, fn, "paragraph_style"
    
    # 3. 从 Normal 样式
    if "Normal" in style_cache:
        fn = style_cache["Normal"].get("font_name")
        if fn:
            return None, fn, "normal_style"
    
    return None, None, "unresolved"


def _resolve_font_size(paragraph, style_cache: dict, style_name: str) -> tuple:
    """解析字号，同上逻辑。"""
    for run in paragraph.runs:
        if run.font.size:
            size_pt = round(run.font.size.pt, 2)
            return size_pt, size_pt, "run"
    
    if style_name and style_name in style_cache:
        fs = style_cache[style_name].get("font_size")
        if fs:
            try:
                return None, round(fs.pt, 2), "paragraph_style"
            except Exception:
                pass
    
    return None, None, "unresolved"


def _parse_tables(doc) -> list[dict[str, Any]]:
    tables = []
    for t_idx, table in enumerate(doc.tables):
        rows = []
        for row in table.rows:
            cells = [cell.text for cell in row.cells]
            rows.append(cells)
        tables.append({"index": t_idx, "rows": rows, "row_count": len(rows)})
    return tables


def _parse_sections_enhanced(doc) -> list[dict[str, Any]]:
    sections = []
    for section in doc.sections:
        sections.append({
            "page_width_cm": _to_cm(getattr(section, "page_width", None)),
            "page_height_cm": _to_cm(getattr(section, "page_height", None)),
            "top_margin_cm": _to_cm(getattr(section, "top_margin", None)),
            "bottom_margin_cm": _to_cm(getattr(section, "bottom_margin", None)),
            "left_margin_cm": _to_cm(getattr(section, "left_margin", None)),
            "right_margin_cm": _to_cm(getattr(section, "right_margin", None)),
            "header_text": "\n".join(
                (p.text or "").strip() for p in section.header.paragraphs if (p.text or "").strip()
            ),
            "footer_text": "\n".join(
                (p.text or "").strip() for p in section.footer.paragraphs if (p.text or "").strip()
            ),
        })
    return sections


def _extract_citations(text: str) -> list[dict[str, Any]]:
    citations = []
    for m in re.finditer(r"\[(\d+(?:[,，\-]\d+)*)\]", text):
        raw = m.group(0)
        inner = m.group(1)
        numbers = []
        for part in re.split(r"[,，]", inner):
            part = part.strip()
            if "-" in part or "–" in part:
                try:
                    a, b = re.split(r"[-–]", part)
                    numbers.extend(range(int(a), int(b) + 1))
                except ValueError:
                    pass
            else:
                try:
                    numbers.append(int(part))
                except ValueError:
                    pass
        citations.append({"raw": raw, "numbers": numbers, "offset": m.start()})
    return citations


# Reuse helpers from file_parsers
import re as _re

def _heading_level(style_name: str) -> int:
    match = _re.search(r"heading\s*(\d+)", style_name, _re.I)
    if match:
        return int(match.group(1))
    if "标题" in style_name:
        zh_match = _re.search(r"标题\s*(\d+)", style_name)
        if zh_match:
            return int(zh_match.group(1))
        return 1
    return 0


def _is_figure_caption(text: str) -> bool:
    return bool(_re.match(r"^(图|Figure)\s*\d+", text, _re.I))


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_pt(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value.pt), 2)
    except Exception:
        return None


def _to_cm(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value.cm), 2)
    except Exception:
        return None
```

- [ ] **Step 2: 修改 file_parsers.py 的 parse_docx_bytes 使用增强版解析**

在 `parse_docx_bytes()` 末尾，将 `parse_docx_enhanced` 作为可选升级路径（先保持兼容，后续逐步替换）。

- [ ] **Step 3: Commit**

---

### Task P5-2: 增强 PDF 解析 — PyMuPDF

**Files:**
- Create: `backend/agent/tools/paper_pdf_parser.py`

- [ ] **Step 1: 创建增强 PDF 解析器**

```python
"""增强 PDF 解析：字体、字号、坐标、页面布局，使用 PyMuPDF。"""
from __future__ import annotations

from io import BytesIO
from typing import Any


def parse_pdf_enhanced(content: bytes) -> dict[str, Any]:
    """使用 PyMuPDF 进行增强 PDF 解析。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ValueError("PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")

    doc = fitz.open(stream=content, filetype="pdf")
    pages_data = []
    all_text_parts = []
    font_summary: dict[str, int] = {}
    font_size_summary: dict[str, int] = {}

    for page_no, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        page_text_parts = []
        page_blocks = []

        for block in blocks:
            if block.get("type") != 0:  # text block only
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    font_name = span.get("font", "")
                    font_size = round(span.get("size", 0), 1)
                    bbox = list(span.get("bbox", []))

                    font_summary[font_name] = font_summary.get(font_name, 0) + 1
                    size_key = str(font_size)
                    font_size_summary[size_key] = font_size_summary.get(size_key, 0) + 1

                    page_blocks.append({
                        "type": "text",
                        "text": text,
                        "bbox": bbox,
                        "font": font_name,
                        "size": font_size,
                        "is_bold": "Bold" in font_name or "bold" in font_name,
                    })
                    page_text_parts.append(text)

        page_text = " ".join(page_text_parts)
        all_text_parts.append(page_text)
        pages_data.append({
            "page_no": page_no,
            "width_pt": page.rect.width,
            "height_pt": page.rect.height,
            "blocks": page_blocks,
            "text": page_text,
        })

    # 估算页面布局
    layout = _estimate_pdf_layout(pages_data)
    text = "\n".join(all_text_parts)

    return {
        "kind": "pdf",
        "page_count": len(doc),
        "pages": pages_data,
        "headings": _extract_pdf_headings_enhanced(pages_data),
        "font_summary": dict(sorted(font_summary.items(), key=lambda x: -x[1])[:10]),
        "font_size_summary": dict(sorted(font_size_summary.items(), key=lambda x: -x[1])[:10]),
        "layout_summary": layout,
        "text": text,
    }


def _estimate_pdf_layout(pages: list[dict[str, Any]]) -> dict[str, Any]:
    if not pages:
        return {}
    first_page = pages[0]
    width = first_page.get("width_pt", 595)
    height = first_page.get("height_pt", 842)
    
    # 通过文本块位置估算页边距
    all_bboxes = []
    for page in pages[:5]:
        for block in page.get("blocks", []):
            if block.get("bbox"):
                all_bboxes.append(block["bbox"])
    
    if not all_bboxes:
        return {"page_size": _page_size_name(width, height)}
    
    left = min(b[0] for b in all_bboxes)
    top = min(b[1] for b in all_bboxes)
    right = max(b[2] for b in all_bboxes)
    bottom = max(b[3] for b in all_bboxes)
    
    return {
        "page_size": _page_size_name(width, height),
        "estimated_margins": {
            "top_cm": round(top * 0.035, 1),
            "bottom_cm": round((height - bottom) * 0.035, 1),
            "left_cm": round(left * 0.035, 1),
            "right_cm": round((width - right) * 0.035, 1),
        },
    }


def _page_size_name(width_pt: float, height_pt: float) -> str:
    if abs(width_pt - 595) < 5 and abs(height_pt - 842) < 5:
        return "A4"
    if abs(width_pt - 612) < 5 and abs(height_pt - 792) < 5:
        return "Letter"
    return f"{width_pt:.0f}x{height_pt:.0f}pt"


def _extract_pdf_headings_enhanced(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    headings = []
    for page in pages:
        for block in page.get("blocks", []):
            text = block.get("text", "").strip()
            if not text:
                continue
            # 基于字体大小和模式判断标题
            size = block.get("size", 12)
            is_bold = block.get("is_bold", False)
            if size >= 14 or (is_bold and _is_heading_pattern(text)):
                headings.append({
                    "text": text,
                    "level": 1 if size >= 16 else 2 if size >= 14 else 3,
                    "page": page["page_no"],
                    "font_size": size,
                })
    return headings


def _is_heading_pattern(text: str) -> bool:
    import re
    return bool(re.match(r"^(?:第[一二三四五六七八九十\d]+章|第[一二三四五六七八九十\d]+节|\d+(?:\.\d+)*\s)", text))
```

- [ ] **Step 2: 在 file_parsers.py 中集成增强版 PDF 解析**

修改 `parse_pdf_bytes()`，优先使用 `parse_pdf_enhanced`，失败时 fallback 到原有 pypdf 解析。

- [ ] **Step 3: Commit**

---

### 最终：更新测试与验证

**Files:**
- Modify: `backend/tests/test_paper_format_manager_flow.py`

- [ ] **Step 1: 更新测试以适配新的主流程（不再使用异步 enrichment）**

- [ ] **Step 2: Commit**
```

