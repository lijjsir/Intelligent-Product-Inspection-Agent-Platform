# Langfuse 完全迁移 + 功能测试 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 质量追踪数据源从 piap-mysql 完全迁移到 Langfuse API，添加删除功能，修复链接，评测模型用 DB 配置，验证全部功能

**Architecture:** Langfuse API 作为质量数据的唯一数据源，通过 tags/metadata 过滤实现租户隔离和来源区分。删除操作通过 Langfuse API 级联删除。

**Tech Stack:** Python FastAPI, Langfuse REST API, Vue 3 + Element Plus, Playwright

---

### Task 1: 补全 trace 创建时的 metadata

**Files:**
- Modify: `backend/agent/llm/langfuse_tracer.py:153-188`

- [ ] **Step 1: 在 start_trace 中补全 metadata**

将 `start_trace` 方法中的 metadata 增加 `source_type` 和 `verdict`，同时用 tags 标记 source_type 便于列表 API 过滤：

```python
# langfuse_tracer.py:153-188 修改 trace 创建部分
if callable(trace_factory):
    metadata = {
        key: value
        for key, value in {
            "task_id": payload["task_id"],
            "org_id": payload["org_id"],
            "model_key": payload["model_key"],
            "source_type": kwargs.get("source_type", "inspection"),
            "verdict": kwargs.get("verdict"),
        }.items()
        if value is not None
    }
    tags = [
        f"source_type:{kwargs.get('source_type', 'inspection')}",
        f"org_id:{payload['org_id']}" if payload.get("org_id") else None,
    ]
    tags = [t for t in tags if t is not None]
    try:
        trace_factory(
            id=trace_id,
            name=payload["name"],
            session_id=str(payload["task_id"]) if payload["task_id"] else None,
            user_id=str(payload["org_id"]) if payload["org_id"] else None,
            metadata=metadata or None,
            tags=tags or None,
            input=kwargs.get("input"),
        )
    except TypeError:
        # 旧版 SDK 可能不支持 tags 参数
        kwargs.pop("tags", None)
        trace_factory(
            id=trace_id,
            name=payload["name"],
            session_id=str(payload["task_id"]) if payload["task_id"] else None,
            user_id=str(payload["org_id"]) if payload["org_id"] else None,
            metadata=metadata or None,
            input=kwargs.get("input"),
        )
    except Exception as exc:
        logger.warning("Langfuse trace creation failed: %s", exc)
```

- [ ] **Step 2: 更新 start_trace 调用处传入 source_type 和 verdict**

查找并更新 `start_trace` 的调用处，传入 `source_type` 和 `verdict` 参数。

- [ ] **Step 3: 运行测试验证**

```bash
cd backend && python -m pytest tests/ -q --tb=short
```
Expected: 128 passed

---

### Task 2: 改写 list_traces 使用 Langfuse API

**Files:**
- Modify: `backend/app/services/quality_report_service.py:60-95`

- [ ] **Step 1: 新增 _fetch_traces_from_langfuse 方法**

```python
async def _fetch_traces_from_langfuse(self, source: str, limit: int) -> list[dict]:
    api_client = LangfuseApiClient()
    if not api_client.enabled:
        return []
    
    tags = []
    if self._org_id:
        tags.append(f"org_id:{self._org_id}")
    if source != "all":
        tags.append(f"source_type:{source}")
    
    all_traces: list[dict] = []
    page = 1
    while len(all_traces) < limit:
        try:
            resp = await api_client.list_traces(page=page, limit=min(50, limit), tags=tags or None)
        except LangfuseApiError:
            break
        data = resp.get("data", [])
        if not data:
            break
        for t in data:
            trace = self._langfuse_trace_to_item(t)
            if trace:
                all_traces.append(trace)
        meta = resp.get("meta", {})
        if page >= meta.get("totalPages", 1):
            break
        page += 1
    return all_traces[:limit]

@staticmethod
def _langfuse_trace_to_item(trace: dict) -> dict | None:
    tid = trace.get("id", "")
    if not tid:
        return None
    metadata = trace.get("metadata") or {}
    scores = trace.get("scores") or []
    obs = trace.get("observations") or []
    
    trust_score = None
    hallucination_risk = None
    overconfidence = None
    has_citation = None
    review_model = None
    feedback_count = 0
    last_score_value = None
    last_score_at = None
    
    for s in scores:
        name = s.get("name", "")
        if name == "trust_score":
            trust_score = float(s.get("value", 0))
        elif name == "hallucination_risk":
            hallucination_risk = float(s.get("value", 0))
        elif name == "overconfidence":
            overconfidence = float(s.get("value", 0))
        elif name == "has_citation":
            has_citation = bool(s.get("value", 0))
        elif name == "user_feedback":
            feedback_count += 1
            last_score_value = float(s.get("value", 0))
            last_score_at = s.get("timestamp")
    
    total_tokens = sum(
        int((o.get("usage") or {}).get("total", 0))
        for o in obs if o.get("type") == "GENERATION"
    )
    model_key = metadata.get("model_key", "")
    if not model_key and obs:
        model_key = obs[0].get("model", "")
    
    api_client = LangfuseApiClient()
    
    return {
        "source_type": metadata.get("source_type", "inspection"),
        "trace_id": tid,
        "trace_url": api_client.build_trace_url(tid),
        "result_id": metadata.get("task_id"),
        "task_id": metadata.get("task_id"),
        "assistant_message_id": None,
        "session_id": trace.get("sessionId"),
        "observation_id": obs[0].get("id") if obs else None,
        "verdict": metadata.get("verdict"),
        "model_key": model_key,
        "total_tokens": total_tokens,
        "feedback_count": feedback_count,
        "thumbs_down_count": 0,
        "last_score_value": last_score_value,
        "last_score_at": last_score_at,
        "trust_score": trust_score,
        "hallucination_risk": hallucination_risk,
        "overconfidence": overconfidence,
        "has_citation": has_citation,
        "score_status": "scored" if trust_score is not None else None,
        "review_model": review_model,
        "langfuse_status": "synced",
        "langfuse_synced": True,
        "created_at": trace.get("timestamp"),
    }
```

- [ ] **Step 2: 重写 list_traces 方法**

```python
async def list_traces(self, limit: int = 100, source: str = "all") -> list[dict]:
    api_client = LangfuseApiClient()
    if api_client.enabled:
        traces = await self._fetch_traces_from_langfuse(source=source, limit=limit)
        if traces:
            return traces
    
    # Fallback: 使用旧逻辑（Langfuse 未启用时）
    results = await self._result_repo.list_by_range(self._org_id)
    feedbacks = await self._feedback_repo.list_by_range(self._org_id)
    ledger_items = await self._token_ledger_repo.list_filtered(self._org_id)
    chat_scores = await self._chat_score_repo.list_by_range(self._org_id, limit=limit)
    chat_messages = await self._chat_message_repo.list_assistant_for_org(self._org_id, limit=limit)
    if source == "inspection":
        chat_scores, chat_messages = [], []
    if source == "chat":
        results, feedbacks = [], []
    
    trace_exists_cache: dict[str, bool | None] = {}
    tracer = LangfuseTracer()
    
    def langfuse_trace_exists(trace_id: str | None) -> bool | None:
        if not trace_id:
            return None
        trace_key = str(trace_id)
        if trace_key not in trace_exists_cache:
            trace_exists_cache[trace_key] = tracer.trace_exists(trace_key)
        return trace_exists_cache[trace_key]
    
    def build_trace_url(trace_id: str | None) -> str | None:
        if not trace_id:
            return None
        if api_client.enabled:
            return api_client.build_trace_url(str(trace_id))
        return tracer.get_trace_url(str(trace_id))
    
    return self._build_quality_traces(
        results, feedbacks, ledger_items, limit=limit,
        chat_scores=chat_scores, chat_messages=chat_messages,
        langfuse_trace_exists=langfuse_trace_exists,
        build_trace_url=build_trace_url,
    )
```

- [ ] **Step 3: 运行测试验证**

```bash
cd backend && python -m pytest tests/ -q --tb=short
```
Expected: 全部通过

---

### Task 3: 清理废弃的 piap-mysql 代码

**Files:**
- Create: `backend/migrations/versions/0025_drop_quality_tables.py`
- Modify: 清理 repository 文件中的废弃方法

- [ ] **Step 1: 创建 Alembic 迁移删除旧表**

不自动执行，生成脚本供人工确认后运行。表中数据的 trace 信息已全部在 Langfuse 中。

- [ ] **Step 2: 清理 QualityReportService 中不再被 Langfuse 路径使用的 fallback 代码引用**

保留 fallback 路径（Langfuse 未启用时使用），暂不删除 repository 导入。

---

### Task 4: 更新测试确保 Langfuse API 路径可测

**Files:**
- Modify: `backend/tests/test_governance_logic.py`

- [ ] **Step 1: 新增 test_langfuse_trace_to_item 测试**

```python
def test_langfuse_trace_to_item_parses_inspection_trace():
    trace = {
        "id": "trace-1",
        "timestamp": "2026-05-16T10:00:00Z",
        "sessionId": "task-1",
        "metadata": {
            "source_type": "inspection",
            "verdict": "fail",
            "model_key": "model-a",
            "task_id": "task-1",
            "org_id": "org-1",
        },
        "scores": [
            {"name": "trust_score", "value": 0.85, "timestamp": "2026-05-16T10:01:00Z"},
            {"name": "hallucination_risk", "value": 0.1, "timestamp": "2026-05-16T10:01:00Z"},
            {"name": "overconfidence", "value": 0.15, "timestamp": "2026-05-16T10:01:00Z"},
            {"name": "user_feedback", "value": 0.8, "timestamp": "2026-05-16T10:02:00Z"},
        ],
        "observations": [
            {"id": "obs-1", "type": "GENERATION", "model": "model-a", "usage": {"total": 150}}
        ],
    }
    item = QualityReportService._langfuse_trace_to_item(trace)
    assert item is not None
    assert item["trace_id"] == "trace-1"
    assert item["source_type"] == "inspection"
    assert item["verdict"] == "fail"
    assert item["model_key"] == "model-a"
    assert item["trust_score"] == 0.85
    assert item["total_tokens"] == 150
    assert item["feedback_count"] == 1
    assert item["langfuse_status"] == "synced"
```

---

### Task 5: 端到端测试 — 启动 Langfuse 验证功能

**Files:**
- 使用 Playwright 测试前端

- [ ] **Step 1: 确保 Langfuse Docker 已启动**

```bash
docker ps --filter name=piap-langfuse
```

若未启动，运行：
```bash
docker compose -f docker-compose.langfuse.yml up -d
```

- [ ] **Step 2: 测试 Langfuse Web UI 可访问**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000
```
Expected: 200

- [ ] **Step 3: 测试 Langfuse API 认证**

```bash
# 使用配置的 public/secret key 测试
curl -s -u "${PIAP_LANGFUSE_PUBLIC_KEY}:${PIAP_LANGFUSE_SECRET_KEY}" \
  "http://127.0.0.1:3000/api/public/traces?limit=1"
```
Expected: JSON response with data/meta

- [ ] **Step 4: 使用 Playwright 测试前端质量追踪页面**

打开分析中心 → 质量追踪 tab → 验证列表加载、删除按钮、Langfuse 链接跳转
