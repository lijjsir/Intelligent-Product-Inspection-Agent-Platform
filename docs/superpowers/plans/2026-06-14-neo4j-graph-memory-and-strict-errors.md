# Neo4j Graph Memory & Strict Error Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Neo4j the sole graph relationship fact source, remove MySQL dependency edge writes, implement strict error propagation (no silent fallback), and enhance short-term memory structure.

**Architecture:** Neo4j for graph relationships, MySQL for memory content/audit, Qdrant for semantic index. All service failures throw structured errors propagated through ChatService → SSE → frontend error cards.

**Tech Stack:** Python/FastAPI backend, Neo4j (AsyncGraphDatabase), Vue 3/TypeScript frontend, Qdrant vector DB

---

## Phase 1: Strict Errors & Config

### Task 1.1: Create memory_errors.py with structured exception classes

**Files:**
- Create: `backend/app/errors/__init__.py`
- Create: `backend/app/errors/memory_errors.py`

- [ ] **Step 1: Create errors package init**

```python
# backend/app/errors/__init__.py
```

- [ ] **Step 2: Write memory_errors.py**

```python
# backend/app/errors/memory_errors.py
from __future__ import annotations


class ShortTermMemoryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "SHORT_TERM_MEMORY_FAILED",
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class SharedMemoryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "SHARED_MEMORY_FAILED",
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class GraphMemoryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "GRAPH_MEMORY_FAILED",
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/errors/ && git commit -m "feat: add structured memory error classes"
```

### Task 1.2: Add FastAPI exception handlers for memory errors

**Files:**
- Create: `backend/app/api/error_handlers.py`
- Modify: `backend/app/main.py` (or wherever the FastAPI app is created)

- [ ] **Step 1: Create error_handlers.py**

```python
# backend/app/api/error_handlers.py
from fastapi import Request
from fastapi.responses import JSONResponse

from app.errors.memory_errors import (
    ShortTermMemoryError,
    SharedMemoryError,
    GraphMemoryError,
)


async def memory_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error_code": getattr(exc, "code", "MEMORY_ERROR"),
            "message": str(exc),
            "detail": getattr(exc, "detail", {}),
            "recoverable": False,
        },
    )
```

- [ ] **Step 2: Find and read main.py to wire exception handlers**

```bash
grep -n "app\s*=\s*FastAPI\|add_exception_handler" backend/app/main.py
```

- [ ] **Step 3: Register exception handlers in main.py**

Add after the FastAPI app creation:
```python
from app.api.error_handlers import memory_error_handler
from app.errors.memory_errors import ShortTermMemoryError, SharedMemoryError, GraphMemoryError

app.add_exception_handler(ShortTermMemoryError, memory_error_handler)
app.add_exception_handler(SharedMemoryError, memory_error_handler)
app.add_exception_handler(GraphMemoryError, memory_error_handler)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/error_handlers.py backend/app/main.py && git commit -m "feat: add FastAPI exception handlers for memory errors"
```

### Task 1.3: Update ShortTermMemoryService with structured errors

**Files:**
- Modify: `backend/app/services/short_term_memory_service.py`

- [ ] **Step 1: Update build_context to throw ShortTermMemoryError instead of ValueError**

Replace the `ValueError` on line 55 and wrap repository calls in try/except:

```python
# In build_context(), replace:
#     raise ValueError("chat session not found for short-term memory")
# with:
from app.errors.memory_errors import ShortTermMemoryError

# Replace ValueError:
if not chat_session:
    raise ShortTermMemoryError(
        "读取聊天会话失败，无法构建短期记忆。",
        code="SHORT_TERM_SESSION_NOT_FOUND",
        detail={"session_id": session_id, "user_id": user_id},
    )
```

- [ ] **Step 2: Wrap the session read in try/except**

```python
try:
    chat_session = await session_repo.get(self._org_id, user_id, session_id)
except Exception as exc:
    raise ShortTermMemoryError(
        "读取聊天会话失败，无法构建短期记忆。",
        code="SHORT_TERM_SESSION_READ_FAILED",
        detail={"session_id": session_id, "user_id": user_id},
    ) from exc

if not chat_session:
    raise ShortTermMemoryError(...)
```

- [ ] **Step 3: Wrap message list read**

```python
try:
    rows = await msg_repo.list_for_session(...)
except Exception as exc:
    raise ShortTermMemoryError(
        "读取聊天消息失败，无法构建短期记忆。",
        code="SHORT_TERM_MESSAGES_READ_FAILED",
        detail={"session_id": session_id, "current_user_seq_no": current_user_seq_no},
    ) from exc
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/short_term_memory_service.py && git commit -m "feat: throw structured ShortTermMemoryError on session/message read failures"
```

### Task 1.4: Update ChatSessionSummaryService — fail on missing model or JSON parse error

**Files:**
- Modify: `backend/app/services/chat_session_summary_service.py`

- [ ] **Step 1: Replace silent fallback when runtime is None**

Replace `return "", {}` (line 98) with:
```python
from app.errors.memory_errors import ShortTermMemoryError

if not runtime:
    raise ShortTermMemoryError(
        "没有可用的总结模型，短期记忆摘要失败。",
        code="SHORT_TERM_SUMMARY_MODEL_NOT_FOUND",
        detail={"session_id": session_id},
    )
```

- [ ] **Step 2: Replace silent JSON parse failure fallback**

Replace `return raw[:200], {}` (line 123) with:
```python
except (json.JSONDecodeError, ValueError) as exc:
    raise ShortTermMemoryError(
        "短期记忆摘要模型返回格式错误，无法解析 JSON。",
        code="SHORT_TERM_SUMMARY_JSON_INVALID",
        detail={"raw_output": raw[:500]},
    ) from exc
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/chat_session_summary_service.py && git commit -m "feat: fail on missing summary model or JSON parse error instead of silent fallback"
```

### Task 1.5: Update ChatService error payload to chat_error_v1 format

**Files:**
- Modify: `backend/app/services/chat_service.py`

- [ ] **Step 1: Add _build_error_payload static method**

Add after the `_run_workflow` method:
```python
@staticmethod
def _build_error_payload(exc: Exception) -> dict:
    code = getattr(exc, "code", "CHAT_WORKFLOW_FAILED")
    detail = getattr(exc, "detail", {})
    return {
        "status": "failed",
        "message_type": "error",
        "error_code": code,
        "error": str(exc),
        "detail": detail,
        "ui_schema": "chat_error_v1",
        "recoverable": False,
    }
```

- [ ] **Step 2: Replace the failure_payload construction in the except block (around line 687-694)**

Replace the two-line duplicated `failure_payload` assignment with:
```python
failure_payload = self._build_error_payload(exc)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/chat_service.py && git commit -m "feat: build chat_error_v1 error payload with structured error codes"
```

### Task 1.6: Update frontend to display chat_error_v1 error cards

**Files:**
- Modify: `frontend/src/views/ChatView.vue`
- Modify: `frontend/src/types/chat.types.ts`

- [ ] **Step 1: Add error payload types**

In `frontend/src/types/chat.types.ts`, add:
```typescript
export interface ChatErrorPayload {
  status: string;
  message_type: string;
  error_code: string;
  error: string;
  detail: Record<string, unknown>;
  ui_schema: string;
  recoverable: boolean;
}
```

- [ ] **Step 2: Add error card template in ChatView.vue**

Add a template block for message_type === "error" with ui_schema === "chat_error_v1":
```vue
<div v-if="message.message_type === 'error' && message.payload?.ui_schema === 'chat_error_v1'" class="chat-error-card">
  <div class="error-header">
    <span class="error-icon">⚠</span>
    <span class="error-title">执行失败</span>
  </div>
  <div class="error-body">
    <div class="error-row"><span class="error-label">错误码：</span>{{ message.payload.error_code }}</div>
    <div class="error-row"><span class="error-label">错误信息：</span>{{ message.payload.error }}</div>
    <div v-if="message.payload.detail && Object.keys(message.payload.detail).length" class="error-detail">
      <div v-for="(v, k) in message.payload.detail" :key="k" class="error-detail-row">
        {{ k }}: {{ v }}
      </div>
    </div>
  </div>
  <div class="error-actions">
    <button @click="copyError(message)">复制错误</button>
    <button @click="resendMessage(message)">重新发送</button>
  </div>
</div>
```

- [ ] **Step 3: Add scoped styles for .chat-error-card**

```css
.chat-error-card {
  border: 1px solid #f56c6c;
  border-radius: 8px;
  padding: 16px;
  background: #fef0f0;
  margin: 8px 0;
}
.chat-error-card .error-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.chat-error-card .error-title { font-weight: 600; color: #f56c6c; font-size: 15px; }
.chat-error-card .error-body { margin-bottom: 12px; }
.chat-error-card .error-row { margin: 4px 0; font-size: 13px; }
.chat-error-card .error-label { color: #909399; }
.chat-error-card .error-detail { margin-top: 8px; padding: 8px; background: #fff; border-radius: 4px; font-size: 12px; color: #606266; }
.chat-error-card .error-actions { display: flex; gap: 8px; }
.chat-error-card .error-actions button { padding: 4px 12px; border-radius: 4px; border: 1px solid #dcdfe6; background: #fff; cursor: pointer; font-size: 12px; }
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/chat.types.ts frontend/src/views/ChatView.vue && git commit -m "feat: add chat_error_v1 error card display in frontend"
```

---

## Phase 2: Neo4j Real Enablement

### Task 2.1: Update config defaults for Neo4j

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Flip config values**

```python
# Change lines 100-108 from:
neo4j_enabled: bool = False
# ...
memory_graph_write_backend: str = "dual"
memory_graph_read_backend: str = "mysql"

# To:
neo4j_enabled: bool = True
neo4j_uri: str = "bolt://127.0.0.1:7687"
neo4j_username: str = "neo4j"
neo4j_password: str = "neo4j_password"
neo4j_database: str = "neo4j"
memory_graph_write_backend: str = "neo4j"
memory_graph_read_backend: str = "neo4j"
memory_strict_sync: bool = True
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/config.py && git commit -m "feat: enable Neo4j as default graph backend"
```

### Task 2.2: Add verify_connectivity and ensure_schema to Neo4jMemoryGraphStore

**Files:**
- Modify: `backend/app/services/neo4j_memory_graph_store.py`

- [ ] **Step 1: Add verify_connectivity method**

```python
async def verify_connectivity(self) -> None:
    async with self._driver.session(database=self._database) as session:
        result = await session.run("RETURN 1 AS ok")
        record = await result.single()
        if not record or record["ok"] != 1:
            raise RuntimeError("Neo4j returned invalid health check result")
```

- [ ] **Step 2: Add ensure_schema method**

```python
async def ensure_schema(self) -> None:
    cyphers = [
        "CREATE CONSTRAINT memory_id_unique IF NOT EXISTS FOR (m:Memory) REQUIRE m.memory_id IS UNIQUE",
        "CREATE INDEX memory_org_id_idx IF NOT EXISTS FOR (m:Memory) ON (m.org_id)",
        "CREATE INDEX memory_status_idx IF NOT EXISTS FOR (m:Memory) ON (m.status)",
        "CREATE INDEX memory_type_idx IF NOT EXISTS FOR (m:Memory) ON (m.memory_type)",
        "CREATE CONSTRAINT rag_chunk_id_unique IF NOT EXISTS FOR (c:RagChunk) REQUIRE c.chunk_id IS UNIQUE",
        "CREATE CONSTRAINT agent_run_id_unique IF NOT EXISTS FOR (a:AgentRun) REQUIRE a.run_id IS UNIQUE",
        "CREATE CONSTRAINT memory_event_id_unique IF NOT EXISTS FOR (e:MemoryEvent) REQUIRE e.event_id IS UNIQUE",
        "CREATE CONSTRAINT task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.task_id IS UNIQUE",
        "CREATE CONSTRAINT product_line_key_unique IF NOT EXISTS FOR (p:ProductLine) REQUIRE p.product_line_key IS UNIQUE",
        "CREATE CONSTRAINT standard_version_key_unique IF NOT EXISTS FOR (s:StandardVersion) REQUIRE s.standard_version_key IS UNIQUE",
    ]
    async with self._driver.session(database=self._database) as session:
        for cypher in cyphers:
            await session.run(cypher)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/neo4j_memory_graph_store.py && git commit -m "feat: add verify_connectivity and ensure_schema to Neo4j store"
```

### Task 2.3: Create GraphHealthService

**Files:**
- Create: `backend/app/services/graph_health_service.py`

- [ ] **Step 1: Write the service**

```python
# backend/app/services/graph_health_service.py
from app.core.config import settings
from app.services.neo4j_memory_graph_store import Neo4jMemoryGraphStore


class GraphHealthService:
    async def assert_neo4j_ready(self) -> None:
        if not settings.neo4j_enabled:
            raise RuntimeError("Neo4j is required but neo4j_enabled=False")

        store = Neo4jMemoryGraphStore(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )
        try:
            await store.verify_connectivity()
            await store.ensure_schema()
        except Exception as exc:
            raise RuntimeError(f"Neo4j connectivity check failed: {exc}") from exc
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/graph_health_service.py && git commit -m "feat: add GraphHealthService for startup Neo4j check"
```

### Task 2.4: Wire startup health check into FastAPI

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add startup event handler**

Find the FastAPI app creation and add:
```python
@app.on_event("startup")
async def startup_check():
    from app.services.graph_health_service import GraphHealthService
    await GraphHealthService().assert_neo4j_ready()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py && git commit -m "feat: add Neo4j health check on FastAPI startup"
```

### Task 2.5: Extend MemoryGraphStore abstract interface

**Files:**
- Modify: `backend/app/services/memory_graph_store.py`

- [ ] **Step 1: Add new abstract methods to MemoryGraphStore**

```python
@abstractmethod
async def list_downstream_memories(
    self, *, org_id: str, root_memory_id: str,
    edge_types: list[str], max_depth: int,
) -> list[dict]: ...

@abstractmethod
async def list_upstream_memories(
    self, *, org_id: str, memory_id: str,
    edge_types: list[str] | None = None, max_depth: int = 4,
) -> list[dict]: ...

@abstractmethod
async def list_conflict_edges(
    self, *, org_id: str, memory_id: str | None = None,
    include_resolved: bool = False,
) -> list[dict]: ...

@abstractmethod
async def soft_delete_memory_edges(
    self, *, org_id: str, memory_id: str,
    edge_types: list[str] | None = None,
) -> int: ...

@abstractmethod
async def mark_conflict_resolved(
    self, *, org_id: str, source_memory_id: str,
    target_memory_id: str, resolution: str, resolved_by: str,
) -> None: ...
```

- [ ] **Step 2: Add stub implementations to MySQLMemoryGraphStore**

```python
async def list_downstream_memories(self, *, org_id, root_memory_id, edge_types, max_depth):
    return []

async def list_upstream_memories(self, *, org_id, memory_id, edge_types=None, max_depth=4):
    return []

async def list_conflict_edges(self, *, org_id, memory_id=None, include_resolved=False):
    return []

async def soft_delete_memory_edges(self, *, org_id, memory_id, edge_types=None):
    return 0

async def mark_conflict_resolved(self, *, org_id, source_memory_id, target_memory_id, resolution, resolved_by):
    pass
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/memory_graph_store.py && git commit -m "feat: extend MemoryGraphStore interface with query/mutation methods"
```

---

## Phase 3: Graph Read/Write Migration

### Task 3.1: Remove MySQL dependency edge writes from MemoryService

**Files:**
- Modify: `backend/app/services/memory_service.py`

- [ ] **Step 1: Modify _record_write_dependencies to only write Neo4j**

In the `_record_write_dependencies` method, comment out/remove all `self._dep_repo.upsert_edge(...)` calls. Keep only the `self._sync_graph_memory_edge(...)` calls.

For each pattern (`version_parent_id`, `evidence_pointers`, `dependency_edges`), keep only the Neo4j sync call.

- [ ] **Step 2: Also check merge_conflicting_memories for dependency writes**

Find any `self._dep_repo.upsert_edge` calls in merge/resolve methods and remove them, keeping only graph sync.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/memory_service.py && git commit -m "feat: remove MySQL dependency edge writes, keep only Neo4j graph sync"
```

### Task 3.2: Implement downstream/upstream and conflict queries in Neo4j store

**Files:**
- Modify: `backend/app/services/neo4j_memory_graph_store.py`

- [ ] **Step 1: Implement list_downstream_memories**

```python
async def list_downstream_memories(
    self, *, org_id: str, root_memory_id: str,
    edge_types: list[str], max_depth: int,
) -> list[dict]:
    query = """
    MATCH path = (root:Memory {org_id: $org_id, memory_id: $root_memory_id})
                 <-[rels*1..$max_depth]-
                 (downstream:Memory {org_id: $org_id})
    WHERE ALL(r IN rels WHERE r.edge_type IN $edge_types AND coalesce(r.deleted_at, '') = '')
    RETURN
      downstream.memory_id AS memory_id,
      length(path) AS depth,
      [r IN rels | r.edge_type] AS edge_types,
      [r IN rels | coalesce(r.strength, 1.0)] AS strengths,
      [n IN nodes(path) | n.memory_id] AS path_memory_ids
    ORDER BY depth ASC
    LIMIT 500
    """
    records = await self._execute_read(query, {
        "org_id": org_id,
        "root_memory_id": root_memory_id,
        "edge_types": edge_types,
        "max_depth": max_depth,
    })
    return [dict(r) for r in records]
```

- [ ] **Step 2: Implement list_upstream_memories**

```python
async def list_upstream_memories(
    self, *, org_id: str, memory_id: str,
    edge_types: list[str] | None = None, max_depth: int = 4,
) -> list[dict]:
    et = edge_types or list(MEMORY_RELATIONSHIP_TYPES.keys())
    query = """
    MATCH path = (m:Memory {org_id: $org_id, memory_id: $memory_id})
                 -[rels*1..$max_depth]->
                 (upstream:Memory {org_id: $org_id})
    WHERE ALL(r IN rels WHERE r.edge_type IN $edge_types AND coalesce(r.deleted_at, '') = '')
    RETURN
      upstream.memory_id AS memory_id,
      length(path) AS depth,
      [r IN rels | r.edge_type] AS edge_types,
      [n IN nodes(path) | n.memory_id] AS path_memory_ids
    ORDER BY depth ASC
    LIMIT 500
    """
    records = await self._execute_read(query, {
        "org_id": org_id,
        "memory_id": memory_id,
        "edge_types": et,
        "max_depth": max_depth,
    })
    return [dict(r) for r in records]
```

- [ ] **Step 3: Implement list_conflict_edges**

```python
async def list_conflict_edges(
    self, *, org_id: str, memory_id: str | None = None,
    include_resolved: bool = False,
) -> list[dict]:
    resolved_filter = "" if include_resolved else "AND coalesce(r.resolved, false) = false"
    mem_filter = ""
    params: dict = {"org_id": org_id}
    if memory_id:
        mem_filter = "AND (a.memory_id = $memory_id OR b.memory_id = $memory_id)"
        params["memory_id"] = memory_id
    query = f"""
    MATCH (a:Memory {{org_id: $org_id}})-[r:CONFLICTS_WITH]->(b:Memory {{org_id: $org_id}})
    WHERE 1=1 {mem_filter} {resolved_filter}
    RETURN
      a.memory_id AS source_memory_id,
      b.memory_id AS target_memory_id,
      r.strength AS strength,
      r.reason AS reason,
      r.metadata_json AS metadata_json,
      r.created_at AS created_at
    ORDER BY r.created_at DESC
    LIMIT 500
    """
    records = await self._execute_read(query, params)
    return [dict(r) for r in records]
```

- [ ] **Step 4: Implement soft_delete_memory_edges**

```python
async def soft_delete_memory_edges(
    self, *, org_id: str, memory_id: str,
    edge_types: list[str] | None = None,
) -> int:
    et_filter = "AND r.edge_type IN $edge_types" if edge_types else ""
    query = f"""
    MATCH (m:Memory {{org_id: $org_id, memory_id: $memory_id}})-[r]-(:Memory)
    WHERE 1=1 {et_filter}
    SET r.deleted_at = datetime()
    RETURN count(r) AS deleted_count
    """
    records = await self._execute_read(query, {
        "org_id": org_id,
        "memory_id": memory_id,
        "edge_types": edge_types or [],
    })
    return records[0]["deleted_count"] if records else 0
```

- [ ] **Step 5: Implement mark_conflict_resolved**

```python
async def mark_conflict_resolved(
    self, *, org_id: str, source_memory_id: str,
    target_memory_id: str, resolution: str, resolved_by: str,
) -> None:
    query = """
    MATCH (a:Memory {org_id: $org_id, memory_id: $source_memory_id})
          -[r:CONFLICTS_WITH]-
          (b:Memory {org_id: $org_id, memory_id: $target_memory_id})
    SET r.resolved = true,
        r.resolution = $resolution,
        r.resolved_by = $resolved_by,
        r.resolved_at = datetime()
    """
    await self._execute(query, {
        "org_id": org_id,
        "source_memory_id": source_memory_id,
        "target_memory_id": target_memory_id,
        "resolution": resolution,
        "resolved_by": resolved_by,
    })
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/neo4j_memory_graph_store.py && git commit -m "feat: implement downstream/upstream/conflict query methods in Neo4j store"
```

### Task 3.3: Add implementations to DualWriteMemoryGraphStore

**Files:**
- Modify: `backend/app/services/memory_graph_factory.py`

- [ ] **Step 1: Delegate new methods to _reader**

Add to `DualWriteMemoryGraphStore`:
```python
async def list_downstream_memories(self, *args, **kwargs):
    return await self._reader.list_downstream_memories(*args, **kwargs)

async def list_upstream_memories(self, *args, **kwargs):
    return await self._reader.list_upstream_memories(*args, **kwargs)

async def list_conflict_edges(self, *args, **kwargs):
    return await self._reader.list_conflict_edges(*args, **kwargs)

async def soft_delete_memory_edges(self, *args, **kwargs):
    # Soft-delete in both stores for safety
    mysql_result = await self._mysql.soft_delete_memory_edges(*args, **kwargs)
    neo4j_result = await self._neo4j.soft_delete_memory_edges(*args, **kwargs)
    return neo4j_result

async def mark_conflict_resolved(self, *args, **kwargs):
    await self._reader.mark_conflict_resolved(*args, **kwargs)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/memory_graph_factory.py && git commit -m "feat: delegate new graph query methods in DualWrite store"
```

### Task 3.4: Update MemoryGovernanceService — Propagation BFS to use Neo4j

**Files:**
- Modify: `backend/app/services/memory_governance_service.py`

- [ ] **Step 1: Add graph_store to MemoryPropagationService.__init__**

```python
def __init__(self, session, org_id: str):
    self._session = session
    self._org_id = org_id
    self._dep_repo = MemoryDependencyRepository(session, org_id)
    self._item_repo = MemoryItemRepository(session, org_id)
    # Add graph_store for Neo4j-backed queries
    from app.services.memory_graph_factory import build_memory_graph_store
    self._graph_store = build_memory_graph_store(session, org_id)
```

- [ ] **Step 2: Update _bfs to use graph_store.list_downstream_memories instead of dep_repo.list_by_target**

Replace the BFS inner loop that calls `self._dep_repo.list_by_target(current)` with:
```python
downstream_edges = await self._graph_store.list_downstream_memories(
    org_id=self._org_id,
    root_memory_id=current,
    edge_types=edge_types,
    max_depth=1,  # one hop at a time for BFS
)
for edge in downstream_edges:
    downstream = edge["memory_id"]
    # use edge["edge_types"][0], edge["strengths"][0] etc.
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/memory_governance_service.py && git commit -m "feat: use Neo4j graph_store for propagation BFS"
```

### Task 3.5: Update MemoryProvenanceService — upstream query to use Neo4j

**Files:**
- Modify: `backend/app/services/memory_governance_service.py`

- [ ] **Step 1: Add graph_store to MemoryProvenanceService.__init__**

```python
def __init__(self, session, org_id: str):
    self._session = session
    self._org_id = org_id
    self._item_repo = MemoryItemRepository(session, org_id)
    self._event_repo = MemoryEventRepository(session, org_id)
    self._dep_repo = MemoryDependencyRepository(session, org_id)
    from app.services.memory_graph_factory import build_memory_graph_store
    self._graph_store = build_memory_graph_store(session, org_id)
```

- [ ] **Step 2: Replace dep_repo.list_by_target in trace_provenance**

Replace `edges = await self._dep_repo.list_by_target(memory_id)` with:
```python
upstream = await self._graph_store.list_upstream_memories(
    org_id=self._org_id,
    memory_id=memory_id,
    edge_types=[
        "version_of", "summarized_from", "merged_from",
        "derived_from", "cited_as_evidence", "planned_from",
        "rollback_depends_on",
    ],
    max_depth=4,
)
```

- [ ] **Step 3: Build upstream_edges from Neo4j results**

```python
upstream_edges = [
    {
        "source_memory_id": u["path_memory_ids"][-1],
        "edge_type": u["edge_types"][0],
        "depth": u["depth"],
    }
    for u in upstream
]
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/memory_governance_service.py && git commit -m "feat: use Neo4j graph_store for provenance tracing"
```

### Task 3.6: Update conflict API endpoints to use Neo4j

**Files:**
- Modify: `backend/app/api/v1/memory.py` (or `memory_helpers.py`)

- [ ] **Step 1: Update conflict list endpoint to call graph_store.list_conflict_edges**

Replace `MemoryDependencyRepository` conflict queries with:
```python
from app.services.memory_graph_factory import build_memory_graph_store
graph_store = build_memory_graph_store(session, org_id)
conflicts = await graph_store.list_conflict_edges(
    org_id=org_id,
    memory_id=memory_id,  # optional filter
    include_resolved=False,
)
```

- [ ] **Step 2: Update conflict resolve to use graph_store.mark_conflict_resolved**

```python
await graph_store.mark_conflict_resolved(
    org_id=org_id,
    source_memory_id=source_memory_id,
    target_memory_id=target_memory_id,
    resolution=resolution,
    resolved_by=resolved_by,
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/memory.py && git commit -m "feat: use Neo4j for conflict list and resolve operations"
```

### Task 3.7: Update rollback BRANCH validation and check

**Files:**
- Modify: `backend/app/services/memory_governance_service.py`
- Modify: `backend/app/api/v1/memory.py` (rollback endpoint)
- Frontend components related to rollback

- [ ] **Step 1: Ensure BRANCH validation exists**

In `MemoryRollbackService.plan_rollback()`, the check `if action == RollbackAction.BRANCH: raise ValueError(...)` already exists at line 222. Verify it's not bypassable.

- [ ] **Step 2: Add API-level BRANCH validation**

In the rollback API endpoint, add:
```python
if request.action == RollbackAction.BRANCH:
    raise HTTPException(
        status_code=400,
        detail={
            "error_code": "ROLLBACK_BRANCH_UNSUPPORTED",
            "message": "branch rollback is reserved and not implemented",
        },
    )
```

- [ ] **Step 3: Hide branch button in frontend**

In the rollback UI component, ensure branch action is not rendered.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/memory_governance_service.py backend/app/api/v1/memory.py && git commit -m "feat: hard-block BRANCH rollback at API, service, and strategy layers"
```

---

## Phase 4: Historical Data Migration

### Task 4.1: Add list_all method to MemoryDependencyRepository

**Files:**
- Modify: `backend/app/repositories/memory_repo.py`

- [ ] **Step 1: Add list_all method**

```python
async def list_all(self, *, org_id: str) -> list:
    from app.models.memory import MemoryDependencyEdge
    from sqlalchemy import select
    stmt = (
        select(MemoryDependencyEdge)
        .where(MemoryDependencyEdge.org_id == org_id)
        .where(MemoryDependencyEdge.deleted_at.is_(None))
    )
    result = await self._session.execute(stmt)
    return list(result.scalars().all())
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/repositories/memory_repo.py && git commit -m "feat: add list_all method to MemoryDependencyRepository"
```

### Task 4.2: Update migration script for verification

**Files:**
- Modify: `backend/scripts/migrate_memory_edges_to_neo4j.py`

- [ ] **Step 1: Review existing script and add verification**

If the script already exists, add a verification step after migration:
```python
async def verify(org_id: str) -> None:
    async with get_session() as session:
        dep_repo = MemoryDependencyRepository(session, org_id)
        graph = build_memory_graph_store(session, org_id)
        mysql_edges = await dep_repo.list_all(org_id=org_id)
        print(f"MySQL edges: {len(mysql_edges)}")
        # Sample 100 random edges and verify in Neo4j
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/migrate_memory_edges_to_neo4j.py && git commit -m "feat: add verification step to migration script"
```

### Task 4.3: Create Alembic migration to drop memory_dependency_edges table

**Files:**
- Create: `backend/migrations/versions/XXXX_drop_memory_dependency_edges.py`

- [ ] **Step 1: Generate and write migration**

```python
# backend/migrations/versions/XXXX_drop_memory_dependency_edges.py
"""Drop memory_dependency_edges table after Neo4j migration"""

revision = 'XXXX'
down_revision = 'PREVIOUS_REVISION'

from alembic import op

def upgrade():
    op.drop_table("memory_dependency_edges")

def downgrade():
    # Restore table schema if needed
    op.create_table(
        "memory_dependency_edges",
        ...
    )
```

Note: Only run this migration AFTER all read/write paths are on Neo4j and historical data has been migrated.

- [ ] **Step 2: Commit**

```bash
git add backend/migrations/versions/ && git commit -m "feat: add migration to drop memory_dependency_edges table (run only after Neo4j migration complete)"
```

---

## Phase 5: Short-Term Memory Enhancement

### Task 5.1: Restructure build_context output

**Files:**
- Modify: `backend/app/services/short_term_memory_service.py`

- [ ] **Step 1: Add new structured fields to return value**

In `build_context()`, after computing all values, restructure return to:
```python
session_summary = {
    "summary": conversation_summary,
    "confirmed_facts": session_facts,
    "open_questions": pending_state.get("open_questions") or [],
    "decisions_made": pending_state.get("decisions_made") or [],
    "warnings": pending_state.get("warnings") or [],
}

working_state = {
    "pending_action": pending_action,
    "awaiting_confirmation": pending_state.get("awaiting_confirmation"),
    "task_draft": pending_state.get("task_draft"),
    "task_form_defaults": pending_state.get("task_form_defaults"),
    "missing_slots": pending_state.get("missing_slots"),
    "paper_review_status": pending_state.get("paper_review_status"),
}

ui_state = {
    "selected_rag_space": selected_rag_space,
    "selected_files": [],
    "selected_images": [],
    "selected_inspection_task_ids": [],
}

return {
    # Backwards compatible
    "conversation_summary": session_summary["summary"],
    "session_facts": session_summary["confirmed_facts"],
    "recent_messages": [...],
    "pending_action": working_state["pending_action"],
    "awaiting_confirmation": working_state["awaiting_confirmation"],
    "task_draft": working_state["task_draft"],
    "task_form_defaults": working_state["task_form_defaults"],
    "missing_slots": working_state["missing_slots"],
    "paper_review_status": working_state["paper_review_status"],
    "selected_rag_space": ui_state["selected_rag_space"],
    "token_budget": {...},
    # New structured fields
    "short_term_memory": {
        "session_summary": session_summary,
        "recent_dialogue": recent_dialogue,
        "working_state": working_state,
        "ui_state": ui_state,
        "token_budget": token_budget,
    },
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/short_term_memory_service.py && git commit -m "feat: restructure build_context output with session_summary/working_state/ui_state"
```

### Task 5.2: Add pending_action state machine

**Files:**
- Modify: `backend/app/services/short_term_memory_service.py`

- [ ] **Step 1: Enhance _latest_pending_state to include state machine fields**

Update `_latest_pending_state` to include:
```python
pa = payload.get("pending_action")
if pa:
    state["pending_action"] = {
        "id": pa.get("id", f"pa_{uuid7()}"),
        "type": pa.get("type", "fill_slots"),
        "status": pa.get("status", "pending"),
        "created_at": pa.get("created_at"),
        "updated_at": pa.get("updated_at"),
        "expires_at": pa.get("expires_at"),
        "source_message_id": pa.get("source_message_id"),
        "source_seq_no": pa.get("source_seq_no"),
        "last_user_response_seq_no": pa.get("last_user_response_seq_no"),
        "missing_slots": pa.get("missing_slots", []),
        "task_draft": pa.get("task_draft", {}),
        "confirmation_policy": pa.get("confirmation_policy", "explicit"),
    }
```

- [ ] **Step 2: Add status filter for expired/completed actions**

```python
expires_at = pending_action.get("expires_at")
if expires_at:
    from datetime import datetime, timezone
    try:
        exp_dt = datetime.fromisoformat(str(expires_at))
        if exp_dt < datetime.now(timezone.utc):
            pending_action["status"] = "expired"
    except (ValueError, TypeError):
        pass
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/short_term_memory_service.py && git commit -m "feat: add pending_action state machine with status/expiry tracking"
```

### Task 5.3: Update ChatExecutor prompt injection with full working_state

**Files:**
- Modify: `backend/agent/router/executors/chat_executor.py`

- [ ] **Step 1: Update _short_term_context_text to include working_state and ui_state**

Replace the current `_short_term_context_text` with:
```python
@staticmethod
def _short_term_context_text(state: ManagerState) -> str:
    stm = state.short_term_memory or {}
    lines = []
    lines.append("[Short-Term Memory — current session only]")
    lines.append("Use this only for the current conversation. If it conflicts with the latest user message, follow the latest user message.")

    session_summary = stm.get("session_summary") or {}
    if session_summary:
        lines.append(f"Session summary: {session_summary.get('summary', '')}")
        facts = session_summary.get("confirmed_facts", {})
        if facts:
            lines.append(f"Confirmed facts: {json.dumps(facts, ensure_ascii=False)}")
        questions = session_summary.get("open_questions", [])
        if questions:
            lines.append(f"Open questions: {json.dumps(questions, ensure_ascii=False)}")
        decisions = session_summary.get("decisions_made", [])
        if decisions:
            lines.append(f"Decisions made: {json.dumps(decisions, ensure_ascii=False)}")

    working_state = stm.get("working_state") or {}
    if working_state:
        lines.append("[Working State]")
        lines.append(json.dumps(working_state, ensure_ascii=False, indent=2))

    ui_state = stm.get("ui_state") or {}
    if ui_state:
        lines.append("[UI State]")
        lines.append(json.dumps(ui_state, ensure_ascii=False, indent=2))

    return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/router/executors/chat_executor.py && git commit -m "feat: inject full working_state and ui_state into ChatExecutor prompt"
```

### Task 5.4: Create SessionMemoryVectorService for session-local semantic recall

**Files:**
- Create: `backend/app/services/session_memory_vector_service.py`

- [ ] **Step 1: Write the service**

```python
# backend/app/services/session_memory_vector_service.py
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

SESSION_MEMORY_COLLECTION = "piap_session_memory"


class SessionMemoryVectorService:
    def __init__(self, embedder_factory, org_id: str, user_id: str | None = None):
        self._embed = embedder_factory
        self._org_id = org_id
        self._user_id = user_id

    async def upsert_message(
        self, *, org_id: str, user_id: str, session_id: str,
        message_id: str, seq_no: int, role: str, content: str,
    ) -> None:
        from app.services.memory_vector_service import MemoryVectorService
        vector_svc = MemoryVectorService(
            collection=SESSION_MEMORY_COLLECTION,
            embedder_factory=self._embed,
            org_id=org_id,
            user_id=user_id,
        )
        embedding = await self._embed(content[:2000])
        await vector_svc.upsert_memory(
            memory_id=f"session_msg_{message_id}",
            org_id=org_id,
            user_id=user_id,
            memory_type="session_message",
            status="active",
            summary=content[:500],
            embedding=embedding,
            extra_payload={
                "session_id": session_id,
                "message_id": message_id,
                "seq_no": seq_no,
                "role": role,
            },
        )

    async def search_session(
        self, *, org_id: str, user_id: str, session_id: str,
        query: str, before_seq_no: int, top_k: int = 5,
    ) -> list[dict]:
        from app.services.memory_vector_service import MemoryVectorService
        vector_svc = MemoryVectorService(
            collection=SESSION_MEMORY_COLLECTION,
            embedder_factory=self._embed,
            org_id=org_id,
            user_id=user_id,
        )
        embedding = await self._embed(query[:2000])
        results = await vector_svc.search(
            embedding=embedding,
            org_id=org_id,
            filter_conditions={
                "must": [
                    {"key": "session_id", "match": {"value": session_id}},
                    {"key": "seq_no", "range": {"lt": before_seq_no}},
                ]
            },
            top_k=top_k,
        )
        return [
            {
                "role": r.get("role", ""),
                "content": r.get("summary", ""),
                "seq_no": r.get("seq_no", 0),
                "score": r.get("score", 0.0),
            }
            for r in results
        ]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/session_memory_vector_service.py && git commit -m "feat: add SessionMemoryVectorService for session-local semantic recall"
```

### Task 5.5: Integrate session semantic recall into ShortTermMemoryService

**Files:**
- Modify: `backend/app/services/short_term_memory_service.py`

- [ ] **Step 1: Add semantic recall to build_context**

In `build_context()`, after loading recent messages, add:
```python
semantic_recall = []
try:
    from app.services.session_memory_vector_service import SessionMemoryVectorService
    from agent.rag.embedder import Embedder

    embedder = Embedder(org_id=self._org_id, user_id=user_id, trace_id=None, allow_pseudo_fallback=False)
    async def embed_factory(text: str) -> list[float]:
        return await embedder.embed(text)

    session_vector_svc = SessionMemoryVectorService(embed_factory, self._org_id, user_id)
    semantic_recall = await session_vector_svc.search_session(
        org_id=self._org_id,
        user_id=user_id,
        session_id=session_id,
        query=current_query,  # need to accept this parameter
        before_seq_no=current_user_seq_no,
        top_k=5,
    )
except Exception:
    logger.debug("Session semantic recall skipped", exc_info=True)
```

- [ ] **Step 2: Add current_query parameter to build_context**

```python
async def build_context(
    self, *, user_id, session_id, current_user_seq_no,
    current_query: str = "",  # NEW
    max_recent_messages=20, max_prompt_chars=MAX_PROMPT_CHARS,
) -> dict:
```

- [ ] **Step 3: Include semantic_recall in return value**

```python
return {
    ...
    "semantic_recall": semantic_recall,
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/short_term_memory_service.py && git commit -m "feat: integrate session-local semantic recall into ShortTermMemoryService"
```

### Task 5.6: Add short-term to shared memory promotion gating

**Files:**
- Modify: `backend/app/services/memory_extraction_service.py`

- [ ] **Step 1: Add _is_promotable_from_short_term method**

```python
@staticmethod
def _is_promotable_from_short_term(candidate: dict, stm: dict | None) -> tuple[bool, str]:
    if not stm:
        return True, "no_stm_context"
    memory_type = candidate.get("memory_type", "")
    source = candidate.get("source", {})

    if candidate.get("derived_from_pending_action") and not candidate.get("human_confirmed"):
        return False, "pending_action_not_confirmed"

    if memory_type == "user_preference":
        if candidate.get("confidence", 0) >= 0.75:
            return True, "stable_user_preference"
        return False, "low_confidence_user_preference"

    if memory_type == "inspection_pattern":
        if candidate.get("task_id") or candidate.get("product_line"):
            return True, "inspection_pattern_with_scope"
        return False, "missing_inspection_scope"

    if memory_type == "rag_usage_memory":
        if candidate.get("rag_space_id") and candidate.get("evidence_pointers"):
            return True, "rag_usage_with_evidence"
        return False, "missing_rag_evidence"

    if memory_type == "agent_ops_memory":
        if candidate.get("trace_id"):
            return True, "agent_ops_with_trace"
        return False, "missing_trace"

    return False, "unsupported_memory_type"
```

- [ ] **Step 2: Apply gating in extract_from_chat_result**

```python
async def extract_from_chat_result(self, *, trace_id, user_message, assistant_answer, task_id=None, short_term_memory=None):
    candidates = await self._candidate_service.extract_from_chat_result(...)
    filtered = []
    for c in candidates:
        promotable, reason = self._is_promotable_from_short_term(
            {"memory_type": c.memory_type.value, "confidence": c.confidence, ...},
            short_term_memory,
        )
        if promotable:
            if c.evidence_pointers is None:
                c.evidence_pointers = {}
            c.evidence_pointers["promotion_reason"] = reason
            filtered.append(c)
    return filtered
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/memory_extraction_service.py && git commit -m "feat: add short-term to shared memory promotion gating"
```

### Task 5.7: Inject semantic recall into ChatExecutor prompt

**Files:**
- Modify: `backend/agent/router/executors/chat_executor.py`

- [ ] **Step 1: Add semantic recall section to _short_term_context_text**

After the session summary section, add:
```python
semantic_recall = stm.get("semantic_recall") or []
if semantic_recall:
    lines.append("")
    lines.append("[Session Semantic Recall]")
    lines.append("These snippets from earlier in the current chat may be relevant to the current query:")
    for sr in semantic_recall:
        lines.append(f"  - [{sr.get('role', '')} seq={sr.get('seq_no', 0)} score={sr.get('score', 0):.2f}] {sr.get('content', '')[:300]}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/router/executors/chat_executor.py && git commit -m "feat: inject session semantic recall into ChatExecutor prompt"
```

---

## Verification Tasks

### Task V.1: Verify Neo4j connectivity on startup

- [ ] **Step 1: Start the backend and verify it connects to Neo4j**

```bash
cd backend && python -c "import asyncio; from app.services.graph_health_service import GraphHealthService; asyncio.run(GraphHealthService().assert_neo4j_ready()); print('OK')"
```

### Task V.2: Verify no MySQL dependency edges on write

- [ ] **Step 1: Write a candidate memory and check MySQL**

```python
# Script to verify: after write_candidate, check that memory_dependency_edges has no new rows
```

### Task V.3: Verify propagation graph from Neo4j

- [ ] **Step 1: Call build_propagation_graph and verify source_backend is "neo4j"**

### Task V.4: Verify short-term memory error blocks chat

- [ ] **Step 1: Force a failure and verify frontend receives chat_error_v1**

---

## Final Acceptance Checklist

- [ ] Neo4j not running → backend startup fails
- [ ] Write candidate → Neo4j has Memory node
- [ ] Write dependency → Neo4j has edge, MySQL has NO new dependency edge
- [ ] Propagation graph reads from Neo4j
- [ ] Conflict list reads from Neo4j
- [ ] Short-term memory read failure → chat fails with chat_error_v1 in frontend
- [ ] Summary model unavailable → chat fails with SHORT_TERM_SUMMARY_MODEL_NOT_FOUND in frontend
- [ ] pending_action has status, expiry, and source tracking
- [ ] ChatExecutor prompt includes working_state and ui_state
- [ ] BRANCH rollback returns 400 from API
- [ ] Frontend does not display branch button
