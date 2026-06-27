# Neo4j Graph Memory & Strict Error Implementation Design

> Parent spec: `docs/共享记忆图数据库化与短期记忆严格错误实现方案.md`
> Branch: `tgg`
> Date: 2026-06-14

## Architecture

```
Neo4j  → Graph relationship fact source (edges, propagation, conflicts, provenance)
MySQL  → Memory content & audit fact source (items, events, policies, rollbacks)
Qdrant → Semantic index (shared + candidate memory vectors)
STM    → Current session working state (NOT shared memory)
```

## Data Flow

```
User Message → ChatService._run_workflow()
  → ShortTermMemoryService.build_context()    [structured, strict errors]
  → MemoryService.search()                     [Neo4j for graph, Qdrant for vectors]
  → ChatExecutor (prompt with full working_state)
  → MemoryExtractionService.extract()          [with promotion gating]
  → MemoryService.write_candidate()
  → Neo4j (memory graph edges) + Qdrant (candidate vectors)
```

## Key Decisions

1. **No silent fallback** — any critical service failure throws structured error to frontend
2. **No `branch` rollback** — API returns 400, tool returns unsupported, frontend hides button
3. **Conflict edges bidirectional** in Neo4j
4. **Propagation only on provenance edges** (not CONFLICTS_WITH, SUPPORTED_BY, READ_BY)
5. **Short-term → shared promotion is gated** (confidence, scope, evidence, human confirmation)
6. **Session-local semantic recall** via Qdrant `piap_session_memory` collection

## Implementation Phases

1. **Strict Errors & Config** — memory_errors.py, ChatService error payload, STM structured errors, FastAPI handlers, frontend chat_error_v1
2. **Neo4j Enablement** — config defaults, verify_connectivity, ensure_schema, GraphHealthService, startup check
3. **Graph Read/Write Migration** — remove MySQL dep writes, governance→Neo4j, provenance→Neo4j, conflicts→Neo4j
4. **Historical Migration** — migrate script, verification, eventual table drop
5. **STM Enhancement** — structured context, pending_action state machine, prompt injection, session semantic recall, promotion gating

## Error Propagation

```
Service throws StructuredError (code + detail)
  → ChatService._build_error_payload()
  → DB: message_type="error", ui_schema="chat_error_v1"
  → SSE: {event: "run_failed", payload: {...}}
  → Frontend: red error card (error_code, message, detail, action buttons)
```
