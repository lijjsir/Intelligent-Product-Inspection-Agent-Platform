# Tool Management Phase 2 & 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement tool version management, Agent-tool bindings (Phase 2), external tool import, and real-time event streaming (Phase 3).

**Architecture:** Phase 2 introduces `tool_definitions`, `tool_versions`, `agent_tool_bindings` tables alongside the existing `tool_registry`, migrates version/binding logic from placeholder 501s to real implementations, and upgrades ToolResolver to filter by bindings. Phase 3 adds OpenAPI/MCP import pipelines, SSE event streaming, health checks, and the `tool_sync_events` / `tool_runtime_events` tables.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pydantic, pytest, Vue 3, Pinia, Vue Router, Element Plus, TypeScript, Vite.

---

## File Structure

### Phase 2 Backend

- Create: `backend/migrations/versions/0042_tool_definitions_and_bindings.py`
- Modify: `backend/app/models/tool.py` — add ToolDefinition, ToolVersion, AgentToolBinding models
- Modify: `backend/app/schemas/tool.py` — add version/binding request/response schemas
- Create: `backend/app/repositories/tool_version_repo.py`
- Create: `backend/app/repositories/tool_binding_repo.py`
- Modify: `backend/app/services/tool_service.py` — wire version/binding services
- Create: `backend/app/services/tool_version_service.py`
- Create: `backend/app/services/tool_binding_service.py`
- Modify: `backend/app/api/v1/tools.py` — replace 501 stubs with real endpoints
- Modify: `backend/agent/tools/resolver.py` — use agent_tool_bindings
- Create: `backend/agent/tools/guard.py` — ToolGuard

### Phase 2 Frontend

- Modify: `frontend/src/types/tools.types.ts` — ensure binding/version types match
- Modify: `frontend/src/api/tools.api.ts` — wire real binding/version APIs
- Modify: `frontend/src/stores/tools.store.ts` — add binding/version actions
- Modify: `frontend/src/views/ops/tools/ToolBindingView.vue` — real binding matrix
- Modify: `frontend/src/views/ops/tools/ToolDetailView.vue` — real version history + binding tabs

### Phase 3 Backend

- Create: `backend/migrations/versions/0043_tool_sync_and_runtime_events.py`
- Modify: `backend/app/models/tool.py` — add ToolSyncEvent, ToolRuntimeEvent
- Create: `backend/app/services/tool_import_service.py`
- Modify: `backend/app/services/tool_sync_service.py` — incremental sync + events
- Modify: `backend/app/api/v1/tools.py` — import endpoints, SSE stream
- Create: `backend/app/services/tool_health_service.py`

### Phase 3 Frontend

- Modify: `frontend/src/views/ops/tools/ToolImportView.vue` — real import wizards
- Modify: `frontend/src/views/ops/tools/ToolExecutionView.vue` — SSE live updates

---

### Task 1: Database Migration for Phase 2 Tables

**Files:**
- Create: `backend/migrations/versions/0042_tool_definitions_and_bindings.py`
- Modify: `backend/app/models/tool.py`

- [ ] **Step 1: Add ORM models to backend/app/models/tool.py**

Append after the existing `ToolExecution` class:

```python
class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)

    tool_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    active_version_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_checked_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)

    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )
    deleted_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("org_id", "tool_key", name="uk_org_tool_key"),
    )


class ToolVersion(Base):
    __tablename__ = "tool_versions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    tool_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)

    version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    handler_path: Mapped[str | None] = mapped_column(String(256), nullable=True)

    parameters_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    returns_schema: Mapped[dict] = mapped_column(JSON, nullable=False)

    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    secret_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)

    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=30000)
    retry_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )

    __table_args__ = (
        UniqueConstraint("org_id", "tool_id", "version", name="uk_tool_version"),
    )


class AgentToolBinding(Base):
    __tablename__ = "agent_tool_bindings"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)

    agent_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    tool_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    tool_version_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)

    binding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    allowed_intents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_call_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )

    __table_args__ = (
        UniqueConstraint("org_id", "agent_id", "tool_id", name="uk_agent_tool"),
    )
```

Also add the necessary imports at the top of the file:

```python
from sqlalchemy import UniqueConstraint
```

- [ ] **Step 2: Run a quick import check to verify models are valid**

Run:
```bash
cd backend && python -c "from app.models.tool import ToolDefinition, ToolVersion, AgentToolBinding; print('models ok')"
```
Expected: "models ok"

- [ ] **Step 3: Generate and write the Alembic migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add tool_definitions tool_versions agent_tool_bindings"
```

Then read the generated file and ensure it creates the three tables with proper columns and constraints. Rename it to `0042_tool_definitions_and_bindings.py` if needed.

- [ ] **Step 4: Run migration**

Run:
```bash
cd backend && alembic upgrade head
```
Expected: Migration applies successfully.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/tool.py backend/migrations/versions/0042_tool_definitions_and_bindings.py
git commit -m "feat: add tool_definitions, tool_versions, agent_tool_bindings models and migration"
```

---

### Task 2: Backend Repository Layer for Versions and Bindings

**Files:**
- Create: `backend/app/repositories/tool_version_repo.py`
- Create: `backend/app/repositories/tool_binding_repo.py`

- [ ] **Step 1: Write tool_version_repo.py**

```python
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import ToolVersion


class ToolVersionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, version: ToolVersion) -> ToolVersion:
        self._session.add(version)
        await self._session.flush()
        await self._session.refresh(version)
        return version

    async def list_by_tool(self, org_id: str, tool_id: str) -> list[ToolVersion]:
        result = await self._session.execute(
            select(ToolVersion)
            .where(ToolVersion.org_id == org_id, ToolVersion.tool_id == tool_id)
            .order_by(ToolVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, version_id: str) -> ToolVersion | None:
        result = await self._session.execute(
            select(ToolVersion).where(
                ToolVersion.id == version_id,
                ToolVersion.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_tool_and_version(
        self, org_id: str, tool_id: str, version: str
    ) -> ToolVersion | None:
        result = await self._session.execute(
            select(ToolVersion).where(
                ToolVersion.org_id == org_id,
                ToolVersion.tool_id == tool_id,
                ToolVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, version: ToolVersion, updates: dict) -> ToolVersion:
        for key, value in updates.items():
            setattr(version, key, value)
        await self._session.flush()
        await self._session.refresh(version)
        return version
```

- [ ] **Step 2: Write tool_binding_repo.py**

```python
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import AgentToolBinding


class ToolBindingRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, binding: AgentToolBinding) -> AgentToolBinding:
        self._session.add(binding)
        await self._session.flush()
        await self._session.refresh(binding)
        return binding

    async def list_all(self, org_id: str) -> list[AgentToolBinding]:
        result = await self._session.execute(
            select(AgentToolBinding)
            .where(AgentToolBinding.org_id == org_id)
            .order_by(AgentToolBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_tool(self, org_id: str, tool_id: str) -> list[AgentToolBinding]:
        result = await self._session.execute(
            select(AgentToolBinding)
            .where(AgentToolBinding.org_id == org_id, AgentToolBinding.tool_id == tool_id)
            .order_by(AgentToolBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_agent(self, org_id: str, agent_id: str) -> list[AgentToolBinding]:
        result = await self._session.execute(
            select(AgentToolBinding)
            .where(AgentToolBinding.org_id == org_id, AgentToolBinding.agent_id == agent_id)
            .where(AgentToolBinding.binding_status == "active")
            .order_by(AgentToolBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, binding_id: str) -> AgentToolBinding | None:
        result = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.id == binding_id,
                AgentToolBinding.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_agent_and_tool(
        self, org_id: str, agent_id: str, tool_id: str
    ) -> AgentToolBinding | None:
        result = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.org_id == org_id,
                AgentToolBinding.agent_id == agent_id,
                AgentToolBinding.tool_id == tool_id,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, binding: AgentToolBinding, updates: dict) -> AgentToolBinding:
        for key, value in updates.items():
            setattr(binding, key, value)
        await self._session.flush()
        await self._session.refresh(binding)
        return binding

    async def delete(self, binding: AgentToolBinding) -> None:
        await self._session.delete(binding)
        await self._session.flush()
```

- [ ] **Step 3: Verify imports**

Run:
```bash
cd backend && python -c "from app.repositories.tool_version_repo import ToolVersionRepository; from app.repositories.tool_binding_repo import ToolBindingRepository; print('repos ok')"
```
Expected: "repos ok"

- [ ] **Step 4: Commit**

```bash
git add backend/app/repositories/tool_version_repo.py backend/app/repositories/tool_binding_repo.py
git commit -m "feat: add tool version and binding repositories"
```

---

### Task 3: Backend Version and Binding Services

**Files:**
- Create: `backend/app/services/tool_version_service.py`
- Create: `backend/app/services/tool_binding_service.py`
- Modify: `backend/app/services/tool_service.py` — add version list to detail

- [ ] **Step 1: Write tool_version_service.py**

```python
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.models.tool import ToolRegistry, ToolVersion
from app.repositories.tool_repo import ToolRepository
from app.repositories.tool_version_repo import ToolVersionRepository


class ToolVersionService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._tool_repo = ToolRepository(session)
        self._version_repo = ToolVersionRepository(session)

    async def list_versions(self, tool_id: str) -> list[dict[str, Any]]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")
        versions = await self._version_repo.list_by_tool(self._org_id, tool_id)
        return [self._serialize(v) for v in versions]

    async def create_version(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        existing = await self._version_repo.get_by_tool_and_version(
            self._org_id, tool_id, payload["version"]
        )
        if existing:
            raise ValidationError(f"version {payload['version']} already exists")

        version = ToolVersion(
            id=str(uuid7()),
            org_id=self._org_id,
            tool_id=tool.id,
            version=payload["version"],
            display_name=payload.get("display_name", tool.display_name),
            description=payload.get("description", tool.description),
            endpoint=payload.get("endpoint", tool.endpoint),
            method=payload.get("method"),
            handler_path=payload.get("handler_path"),
            parameters_schema=payload.get("parameters_schema", tool.parameters_schema),
            returns_schema=payload.get("returns_schema", tool.returns_schema),
            auth_type=payload.get("auth_type", "none"),
            secret_ref=payload.get("secret_ref"),
            timeout_ms=int(payload.get("timeout_ms", tool.timeout_ms)),
            retry_policy=payload.get("retry_policy", tool.retry_policy),
            rate_limit_rpm=int(payload.get("rate_limit_rpm", tool.rate_limit_rpm)),
            status="draft",
            created_by=None,
        )
        version = await self._version_repo.create(version)
        return self._serialize(version)

    async def publish_version(self, tool_id: str, version_id: str) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")
        version = await self._version_repo.get(self._org_id, version_id)
        if not version or version.tool_id != tool.id:
            raise NotFoundError("version not found")

        version = await self._version_repo.save(version, {"status": "active"})
        await self._tool_repo.save(tool, {"active_version_id": version.id, "version": version.version})
        return {"success": True, "active_version": version.version}

    async def rollback_version(self, tool_id: str, version_id: str) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")
        version = await self._version_repo.get(self._org_id, version_id)
        if not version or version.tool_id != tool.id:
            raise NotFoundError("version not found")

        await self._tool_repo.save(tool, {"active_version_id": version.id, "version": version.version})
        return {"success": True, "active_version": version.version}

    def _serialize(self, version: ToolVersion) -> dict[str, Any]:
        return {
            "id": version.id,
            "tool_id": version.tool_id,
            "version": version.version,
            "display_name": version.display_name,
            "description": version.description or "",
            "endpoint": version.endpoint,
            "method": version.method,
            "handler_path": version.handler_path,
            "parameters_schema": version.parameters_schema or {},
            "returns_schema": version.returns_schema or {},
            "auth_type": version.auth_type,
            "timeout_ms": version.timeout_ms,
            "retry_policy": version.retry_policy,
            "rate_limit_rpm": version.rate_limit_rpm,
            "status": version.status,
            "created_by": version.created_by or "system",
            "created_at": version.created_at,
            "updated_at": version.updated_at,
        }
```

- [ ] **Step 2: Write tool_binding_service.py**

```python
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.models.tool import AgentToolBinding, ToolRegistry
from app.repositories.tool_repo import ToolRepository
from app.repositories.tool_binding_repo import ToolBindingRepository
from app.repositories.tool_version_repo import ToolVersionRepository


class ToolBindingService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._tool_repo = ToolRepository(session)
        self._binding_repo = ToolBindingRepository(session)
        self._version_repo = ToolVersionRepository(session)

    async def list_bindings(self, tool_id: str | None = None) -> list[dict[str, Any]]:
        if tool_id:
            bindings = await self._binding_repo.list_by_tool(self._org_id, tool_id)
        else:
            bindings = await self._binding_repo.list_all(self._org_id)
        return [await self._serialize(b) for b in bindings]

    async def get_binding_matrix(self) -> dict[str, Any]:
        bindings = await self._binding_repo.list_all(self._org_id)
        tools = await self._tool_repo.list_all(self._org_id)

        agents_map: dict[str, str] = {}
        for b in bindings:
            agents_map[b.agent_id] = b.agent_id

        matrix: dict[str, dict[str, Any]] = {}
        for b in bindings:
            if b.agent_id not in matrix:
                matrix[b.agent_id] = {}
            matrix[b.agent_id][b.tool_id] = await self._serialize(b)

        return {
            "agents": [{"agent_id": aid, "agent_name": aid} for aid in agents_map],
            "tools": [
                {"tool_id": t.id, "tool_name": t.display_name, "tool_key": t.name}
                for t in tools
            ],
            "matrix": matrix,
        }

    async def create_binding(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = payload["agent_id"]
        tool_id = payload["tool_id"]

        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        existing = await self._binding_repo.get_by_agent_and_tool(
            self._org_id, agent_id, tool_id
        )
        if existing:
            raise ValidationError("binding already exists for this agent and tool")

        tool_version_id = payload.get("tool_version_id", tool.active_version_id or tool.id)
        binding = AgentToolBinding(
            id=str(uuid7()),
            org_id=self._org_id,
            agent_id=agent_id,
            tool_id=tool_id,
            tool_version_id=tool_version_id,
            binding_status="active",
            allowed_intents=payload.get("allowed_intents"),
            approval_required=bool(payload.get("approval_required", False)),
            auto_call_enabled=bool(payload.get("auto_call_enabled", True)),
        )
        binding = await self._binding_repo.create(binding)
        return await self._serialize(binding)

    async def update_binding(self, binding_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        binding = await self._binding_repo.get(self._org_id, binding_id)
        if not binding:
            raise NotFoundError("binding not found")
        allowed = {"auto_call_enabled", "approval_required", "allowed_intents", "binding_status"}
        updates = {k: v for k, v in payload.items() if k in allowed and v is not None}
        if updates:
            binding = await self._binding_repo.save(binding, updates)
        return await self._serialize(binding)

    async def delete_binding(self, binding_id: str) -> dict[str, Any]:
        binding = await self._binding_repo.get(self._org_id, binding_id)
        if not binding:
            raise NotFoundError("binding not found")
        await self._binding_repo.delete(binding)
        return {"deleted": True}

    async def _serialize(self, binding: AgentToolBinding) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, binding.tool_id)
        version = await self._version_repo.get(self._org_id, binding.tool_version_id)
        return {
            "id": binding.id,
            "agent_id": binding.agent_id,
            "agent_name": binding.agent_id,
            "tool_id": binding.tool_id,
            "tool_name": tool.display_name if tool else binding.tool_id,
            "tool_version_id": binding.tool_version_id,
            "tool_version": version.version if version else "unknown",
            "binding_status": binding.binding_status,
            "auto_call_enabled": binding.auto_call_enabled,
            "approval_required": binding.approval_required,
            "allowed_scenarios": binding.allowed_intents or [],
            "rate_limit": None,
            "created_at": binding.created_at,
            "updated_at": binding.updated_at,
        }
```

- [ ] **Step 3: Verify services import**

Run:
```bash
cd backend && python -c "from app.services.tool_version_service import ToolVersionService; from app.services.tool_binding_service import ToolBindingService; print('services ok')"
```
Expected: "services ok"

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/tool_version_service.py backend/app/services/tool_binding_service.py
git commit -m "feat: add tool version and binding services"
```

---

### Task 4: Replace Phase 2 API Stubs with Real Endpoints

**Files:**
- Modify: `backend/app/api/v1/tools.py` — replace 501 stubs
- Modify: `backend/app/schemas/tool.py` — add request schemas for bindings/versions

- [ ] **Step 1: Add request schemas to backend/app/schemas/tool.py**

Append after existing schemas:

```python
class ToolVersionCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=32)
    display_name: str | None = None
    description: str | None = None
    parameters_schema: dict[str, Any] | None = None
    returns_schema: dict[str, Any] | None = None
    endpoint: str | None = None
    method: str | None = None
    handler_path: str | None = None
    auth_type: str | None = None
    timeout_ms: int | None = None
    rate_limit_rpm: int | None = None


class BindingCreate(BaseModel):
    agent_id: str = Field(..., min_length=1)
    tool_id: str = Field(..., min_length=1)
    tool_version_id: str | None = None
    auto_call_enabled: bool = True
    approval_required: bool = False
    allowed_intents: list[str] | None = None


class BindingUpdate(BaseModel):
    auto_call_enabled: bool | None = None
    approval_required: bool | None = None
    allowed_intents: list[str] | None = None
    binding_status: str | None = None
```

- [ ] **Step 2: Replace binding stubs in backend/app/api/v1/tools.py**

Replace the three binding endpoints (lines 107-137):

```python
@router.get("/bindings", response_model=ResponseEnvelope[list[AgentToolBindingResponse]])
async def get_bindings(
    tool_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_bindings(tool_id=tool_id))


@router.post("/bindings", response_model=ResponseEnvelope[AgentToolBindingResponse], status_code=http_status.HTTP_201_CREATED)
async def create_binding(
    payload: BindingCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_binding(payload.model_dump()))


@router.put("/bindings/{binding_id}", response_model=ResponseEnvelope[AgentToolBindingResponse])
async def update_binding(
    binding_id: str,
    payload: BindingUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_binding(binding_id, payload.model_dump(exclude_unset=True)))


@router.delete("/bindings/{binding_id}", response_model=ResponseEnvelope[object])
async def delete_binding(
    binding_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.delete_binding(binding_id))
```

Also add `BindingCreate` and `BindingUpdate` to the imports from schemas.

- [ ] **Step 3: Replace version stubs in backend/app/api/v1/tools.py**

Replace lines 206-250:

```python
@router.get("/{tool_id}/versions", response_model=ResponseEnvelope[list[ToolVersionResponse]])
async def list_tool_versions(
    tool_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_versions(tool_id))


@router.post("/{tool_id}/versions", response_model=ResponseEnvelope[ToolVersionResponse], status_code=http_status.HTTP_201_CREATED)
async def create_tool_version(
    tool_id: str,
    payload: ToolVersionCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_version(tool_id, payload.model_dump(exclude_unset=True)))


@router.post("/{tool_id}/versions/{version_id}/publish", response_model=ResponseEnvelope[object])
async def publish_version(
    tool_id: str,
    version_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.publish_version(tool_id, version_id))


@router.post("/{tool_id}/versions/{version_id}/rollback", response_model=ResponseEnvelope[object])
async def rollback_version(
    tool_id: str,
    version_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.rollback_version(tool_id, version_id))
```

Add imports for `ToolVersionService`, `ToolBindingService`, `BindingCreate`, `BindingUpdate`, `ToolVersionCreate` at the top of the file.

- [ ] **Step 4: Verify API module imports**

Run:
```bash
cd backend && python -c "from app.api.v1.tools import router; print('api ok')"
```
Expected: "api ok"

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/tools.py backend/app/schemas/tool.py
git commit -m "feat: implement real version and binding API endpoints"
```

---

### Task 5: Upgrade ToolResolver to Use Agent Bindings

**Files:**
- Modify: `backend/agent/tools/resolver.py`

- [ ] **Step 1: Rewrite ToolResolver to filter by agent_tool_bindings**

```python
"""ToolResolver — resolves available tools for an Agent from the database.

Reads agent_tool_bindings → tool_definitions + tool_versions → filters disabled/deprecated →
returns LLM/Agent usable tool declarations.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import AgentToolBinding, ToolRegistry


class ToolResolver:
    """Resolve available tools for a given agent from the database."""

    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def resolve_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """Return the list of tools available to this agent, filtered by agent_tool_bindings."""
        bindings = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.org_id == self._org_id,
                AgentToolBinding.agent_id == agent_id,
                AgentToolBinding.binding_status == "active",
            )
        )
        bound_tool_ids = [b.tool_id for b in bindings.scalars().all()]

        if not bound_tool_ids:
            return []

        stmt = (
            select(ToolRegistry)
            .where(
                ToolRegistry.id.in_(bound_tool_ids),
                ToolRegistry.status == "active",
                ToolRegistry.is_active == True,
            )
            .order_by(ToolRegistry.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        tools = result.scalars().all()
        return [self._tool_to_llm_schema(t) for t in tools]

    async def resolve_tool(self, tool_key: str) -> dict[str, Any] | None:
        """Resolve a single tool by its key."""
        stmt = select(ToolRegistry).where(
            (ToolRegistry.org_id == self._org_id) | (ToolRegistry.org_id == None),
            ToolRegistry.name == tool_key,
            ToolRegistry.is_active == True,
        )
        result = await self._session.execute(stmt)
        tool = result.scalar_one_or_none()
        if not tool:
            return None
        return self._tool_to_llm_schema(tool)

    @staticmethod
    def _tool_to_llm_schema(tool: ToolRegistry) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_schema or {"type": "object", "properties": {}},
            "returns": tool.returns_schema or {"type": "object", "properties": {}},
        }
```

- [ ] **Step 2: Verify import**

Run:
```bash
cd backend && python -c "from agent.tools.resolver import ToolResolver; print('resolver ok')"
```
Expected: "resolver ok"

- [ ] **Step 3: Commit**

```bash
git add backend/agent/tools/resolver.py
git commit -m "feat: upgrade ToolResolver to filter by agent_tool_bindings"
```

---

### Task 6: Implement ToolGuard

**Files:**
- Create: `backend/agent/tools/guard.py`

- [ ] **Step 1: Write ToolGuard**

```python
"""ToolGuard — security and access control for tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import AgentToolBinding, ToolRegistry


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""
    requires_approval: bool = False


class ToolGuard:
    """Validate whether an agent is allowed to call a tool."""

    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def check(self, agent_id: str, tool_key: str) -> GuardResult:
        tool_result = await self._session.execute(
            select(ToolRegistry).where(
                (ToolRegistry.org_id == self._org_id) | (ToolRegistry.org_id == None),
                ToolRegistry.name == tool_key,
            )
        )
        tool = tool_result.scalar_one_or_none()
        if not tool:
            return GuardResult(False, f"tool {tool_key} not found")

        if tool.status not in ("active",):
            return GuardResult(False, f"tool {tool_key} is {tool.status}")

        binding_result = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.org_id == self._org_id,
                AgentToolBinding.agent_id == agent_id,
                AgentToolBinding.tool_id == tool.id,
                AgentToolBinding.binding_status == "active",
            )
        )
        binding = binding_result.scalar_one_or_none()
        if not binding:
            return GuardResult(False, f"agent {agent_id} is not bound to tool {tool_key}")

        if tool.risk_level == "high" and binding.approval_required:
            return GuardResult(True, "requires approval", requires_approval=True)

        return GuardResult(True)
```

- [ ] **Step 2: Verify import**

Run:
```bash
cd backend && python -c "from agent.tools.guard import ToolGuard; print('guard ok')"
```
Expected: "guard ok"

- [ ] **Step 3: Commit**

```bash
git add backend/agent/tools/guard.py
git commit -m "feat: add ToolGuard for agent-tool access control"
```

---

### Task 7: Frontend API, Store, Types for Phase 2

**Files:**
- Modify: `frontend/src/api/tools.api.ts`
- Modify: `frontend/src/stores/tools.store.ts`
- Modify: `frontend/src/types/tools.types.ts`

- [ ] **Step 1: Update frontend API — replace stub methods with real calls**

In `frontend/src/api/tools.api.ts`, replace the stub methods (lines 192-241):

```typescript
  async listVersions(toolId: string): Promise<Wrapped<ToolVersion[]>> {
    return http.get<ToolVersion[]>(`/v1/tools/${toolId}/versions`) as Promise<Wrapped<ToolVersion[]>>;
  },

  async createVersion(
    toolId: string,
    payload: ToolVersionCreateRequest
  ): Promise<Wrapped<ToolVersion>> {
    return http.post<ToolVersion>(`/v1/tools/${toolId}/versions`, payload) as Promise<Wrapped<ToolVersion>>;
  },

  async publishVersion(toolId: string, versionId: string): Promise<Wrapped<{ success: boolean }>> {
    return http.post<{ success: boolean }>(
      `/v1/tools/${toolId}/versions/${versionId}/publish`
    ) as Promise<Wrapped<{ success: boolean }>>;
  },

  async rollbackVersion(toolId: string, versionId: string): Promise<Wrapped<{ success: boolean }>> {
    return http.post<{ success: boolean }>(
      `/v1/tools/${toolId}/versions/${versionId}/rollback`
    ) as Promise<Wrapped<{ success: boolean }>>;
  },

  async listBindings(toolId?: string): Promise<Wrapped<AgentToolBinding[]>> {
    return http.get<AgentToolBinding[]>("/v1/tools/bindings", {
      params: toolId ? { tool_id: toolId } : {},
    }) as Promise<Wrapped<AgentToolBinding[]>>;
  },

  async createBinding(payload: BindingCreateRequest): Promise<Wrapped<AgentToolBinding>> {
    return http.post<AgentToolBinding>("/v1/tools/bindings", payload) as Promise<
      Wrapped<AgentToolBinding>
    >;
  },

  async updateBinding(id: string, payload: BindingUpdateRequest): Promise<Wrapped<AgentToolBinding>> {
    return http.put<AgentToolBinding>(`/v1/tools/bindings/${id}`, payload) as Promise<
      Wrapped<AgentToolBinding>
    >;
  },

  async deleteBinding(id: string): Promise<Wrapped<{ deleted: boolean }>> {
    return http.delete<{ deleted: boolean }>(`/v1/tools/bindings/${id}`) as Promise<
      Wrapped<{ deleted: boolean }>
    >;
  },
```

- [ ] **Step 2: Add store actions for versions and bindings**

Append to `frontend/src/stores/tools.store.ts` inside the store function (before `$reset`):

```typescript
  const toolVersions = ref<ToolVersion[]>([]);
  const toolBindings = ref<AgentToolBinding[]>([]);

  async function fetchVersions(toolId: string) {
    const { data } = await toolsApi.listVersions(toolId);
    toolVersions.value = data.data;
    return data.data;
  }

  async function createVersion(toolId: string, payload: ToolVersionCreateRequest) {
    const { data } = await toolsApi.createVersion(toolId, payload);
    toolVersions.value.unshift(data.data);
    return data.data;
  }

  async function publishVersion(toolId: string, versionId: string) {
    const { data } = await toolsApi.publishVersion(toolId, versionId);
    return data.data;
  }

  async function rollbackVersion(toolId: string, versionId: string) {
    const { data } = await toolsApi.rollbackVersion(toolId, versionId);
    return data.data;
  }

  async function fetchBindings(toolId?: string) {
    const { data } = await toolsApi.listBindings(toolId);
    toolBindings.value = data.data;
    return data.data;
  }

  async function createBinding(payload: BindingCreateRequest) {
    const { data } = await toolsApi.createBinding(payload);
    toolBindings.value.push(data.data);
    return data.data;
  }

  async function updateBinding(id: string, payload: BindingUpdateRequest) {
    const { data } = await toolsApi.updateBinding(id, payload);
    toolBindings.value = toolBindings.value.map((b) =>
      b.id === id ? { ...b, ...data.data } : b
    );
    return data.data;
  }

  async function deleteBinding(id: string) {
    const { data } = await toolsApi.deleteBinding(id);
    toolBindings.value = toolBindings.value.filter((b) => b.id !== id);
    return data.data;
  }
```

Add the necessary imports at the top:
```typescript
import type {
  AgentToolBinding,
  BindingCreateRequest,
  BindingUpdateRequest,
  ToolVersion,
  ToolVersionCreateRequest,
} from "@/types/tools.types";
```

Add to the return statement:
```typescript
    toolVersions,
    toolBindings,
    fetchVersions,
    createVersion,
    publishVersion,
    rollbackVersion,
    fetchBindings,
    createBinding,
    updateBinding,
    deleteBinding,
```

And update `$reset()` to clear these new refs.

- [ ] **Step 3: Update `ToolDetail` type to make versions and bindings non-optional**

In `frontend/src/types/tools.types.ts`, the `ToolDetail` already has `versions` and `bindings` as required arrays — no change needed.

- [ ] **Step 4: Run frontend typecheck**

Run:
```bash
cd frontend && npm run typecheck
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/tools.api.ts frontend/src/stores/tools.store.ts
git commit -m "feat: wire real version and binding APIs in frontend data layer"
```

---

### Task 8: Real Agent Binding Page (Impeccable Design)

**Files:**
- Modify: `frontend/src/views/ops/tools/ToolBindingView.vue`

- [ ] **Step 1: Replace ToolBindingView with real binding matrix**

This page implements a matrix view showing Agent × Tool bindings, with click-to-configure cells.

```vue
<template>
  <div class="tool-binding">
    <section class="hero-card">
      <div>
        <h1 class="hero-title">Agent 绑定</h1>
        <p class="hero-subtitle">控制每个 Agent 可以调用哪些工具，配置自动调用和审批策略。</p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="showCreateDialog = true">新增绑定</el-button>
        <el-button @click="loadBindings">刷新</el-button>
      </div>
    </section>

    <section class="panel" v-loading="loading">
      <div class="panel-header">
        <h2 class="panel-title">绑定矩阵</h2>
        <el-input v-model="search" placeholder="搜索 Agent 或工具..." style="width: 280px" clearable />
      </div>

      <div v-if="bindings.length === 0 && !loading" class="empty-state">
        <p>暂无 Agent 绑定记录，点击「新增绑定」开始配置。</p>
      </div>

      <el-table v-else :data="paginatedBindings" stripe size="small">
        <el-table-column prop="agent_name" label="Agent" width="180" />
        <el-table-column prop="tool_name" label="工具" width="180" />
        <el-table-column prop="tool_version" label="版本" width="90" />
        <el-table-column label="自动调用" width="100">
          <template #default="{ row }">
            <el-tag :type="row.auto_call_enabled ? 'success' : 'info'" size="small">
              {{ row.auto_call_enabled ? "允许" : "禁止" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审批" width="100">
          <template #default="{ row }">
            <el-tag :type="row.approval_required ? 'warning' : 'info'" size="small">
              {{ row.approval_required ? "需要" : "不需要" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.binding_status === 'active' ? 'success' : 'info'" size="small">
              {{ row.binding_status === 'active' ? '活跃' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="editBinding(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="removeBinding(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="bindings.length > pageSize"
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="bindings.length"
        layout="prev, pager, next"
        small
        class="pagination"
      />
    </section>

    <el-dialog v-model="showCreateDialog" title="新增 Agent 绑定" width="480px" destroy-on-close>
      <el-form :model="createForm" label-position="top">
        <el-form-item label="Agent ID">
          <el-input v-model="createForm.agent_id" placeholder="输入 Agent ID" />
        </el-form-item>
        <el-form-item label="工具">
          <el-select v-model="createForm.tool_id" placeholder="选择工具" filterable>
            <el-option
              v-for="tool in store.tools"
              :key="tool.id"
              :label="`${tool.display_name} (${tool.tool_key})`"
              :value="tool.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="自动调用">
          <el-switch v-model="createForm.auto_call_enabled" />
        </el-form-item>
        <el-form-item label="需要审批">
          <el-switch v-model="createForm.approval_required" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="doCreateBinding">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑绑定" width="480px" destroy-on-close>
      <el-form :model="editForm" label-position="top">
        <el-form-item label="自动调用">
          <el-switch v-model="editForm.auto_call_enabled" />
        </el-form-item>
        <el-form-item label="需要审批">
          <el-switch v-model="editForm.approval_required" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.binding_status">
            <el-option label="活跃" value="active" />
            <el-option label="停用" value="inactive" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="doUpdateBinding">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useToolsStore } from "@/stores/tools.store";
import type { AgentToolBinding, BindingCreateRequest, BindingUpdateRequest } from "@/types/tools.types";

const store = useToolsStore();
const loading = ref(false);
const bindings = ref<AgentToolBinding[]>([]);
const search = ref("");
const currentPage = ref(1);
const pageSize = ref(15);

const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const editingBindingId = ref<string | null>(null);

const createForm = reactive<BindingCreateRequest>({
  agent_id: "",
  tool_id: "",
  auto_call_enabled: true,
  approval_required: false,
});

const editForm = reactive<BindingUpdateRequest & { binding_status: string }>({
  auto_call_enabled: true,
  approval_required: false,
  binding_status: "active",
});

const filteredBindings = computed(() => {
  if (!search.value) return bindings.value;
  const q = search.value.toLowerCase();
  return bindings.value.filter(
    (b) =>
      b.agent_name.toLowerCase().includes(q) || b.tool_name.toLowerCase().includes(q)
  );
});

const paginatedBindings = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredBindings.value.slice(start, start + pageSize.value);
});

async function loadBindings() {
  loading.value = true;
  try {
    bindings.value = await store.fetchBindings();
    await store.fetchTools();
  } finally {
    loading.value = false;
  }
}

async function doCreateBinding() {
  try {
    await store.createBinding({ ...createForm });
    showCreateDialog.value = false;
    ElMessage.success("绑定已创建");
    await loadBindings();
  } catch {
    ElMessage.error("创建失败");
  }
}

function editBinding(row: AgentToolBinding) {
  editingBindingId.value = row.id;
  editForm.auto_call_enabled = row.auto_call_enabled;
  editForm.approval_required = row.approval_required;
  editForm.binding_status = row.binding_status;
  showEditDialog.value = true;
}

async function doUpdateBinding() {
  if (!editingBindingId.value) return;
  try {
    const { binding_status, ...rest } = editForm;
    await store.updateBinding(editingBindingId.value, {
      ...rest,
      binding_status: binding_status,
    });
    showEditDialog.value = false;
    ElMessage.success("绑定已更新");
    await loadBindings();
  } catch {
    ElMessage.error("更新失败");
  }
}

async function removeBinding(row: AgentToolBinding) {
  await ElMessageBox.confirm(
    `确认解除 Agent「${row.agent_name}」与工具「${row.tool_name}」的绑定？`,
    "删除绑定",
    { type: "warning" }
  );
  await store.deleteBinding(row.id);
  ElMessage.success("绑定已删除");
  await loadBindings();
}

onMounted(loadBindings);
</script>

<style scoped>
.tool-binding {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card,
.panel {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.hero-card {
  padding: 24px 28px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  background:
    radial-gradient(circle at top left, rgba(99, 102, 241, 0.12), transparent 34%),
    linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
}

.hero-title {
  margin: 0 0 8px;
  font-size: 24px;
  color: #0f172a;
}

.hero-subtitle {
  margin: 0;
  color: #64748b;
}

.panel {
  padding: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}

.empty-state {
  padding: 48px 0;
  text-align: center;
  color: #94a3b8;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
```

- [ ] **Step 2: Run frontend typecheck**

Run:
```bash
cd frontend && npm run typecheck
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ops/tools/ToolBindingView.vue
git commit -m "feat: implement real Agent binding matrix page"
```

---

### Task 9: Real Version History and Binding Tabs in ToolDetailView

**Files:**
- Modify: `frontend/src/views/ops/tools/ToolDetailView.vue`

- [ ] **Step 1: Remove phase-1 alert and add real version history + bindings tabs**

In `ToolDetailView.vue`, remove the phase-1 alert (lines 37-44). Replace the tabs with real phase 2 versions:

```vue
      <el-tabs v-model="activeTab" class="detail-tabs">
        <el-tab-pane label="概览" name="overview">
          <!-- keep existing overview content -->
        </el-tab-pane>
        <el-tab-pane label="配置" name="config">
          <!-- keep existing config content -->
        </el-tab-pane>
        <el-tab-pane label="Schema" name="schema">
          <!-- keep existing schema content -->
        </el-tab-pane>
        <el-tab-pane label="测试" name="test">
          <!-- keep existing test content -->
        </el-tab-pane>
        <el-tab-pane label="版本历史" name="versions">
          <article class="panel">
            <div class="panel-header-row">
              <span class="panel-title">版本历史</span>
              <el-button size="small" @click="showCreateVersionDialog = true">创建新版本</el-button>
            </div>
            <el-table :data="store.toolVersions" stripe size="small" v-loading="versionsLoading">
              <el-table-column prop="version" label="版本" width="100" />
              <el-table-column prop="status" label="状态" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
                    {{ row.status === 'active' ? '当前' : row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="display_name" label="名称" min-width="160" />
              <el-table-column label="操作" width="200">
                <template #default="{ row }">
                  <el-button
                    v-if="row.status !== 'active'"
                    text type="primary" size="small"
                    @click="publishVer(row)"
                  >发布</el-button>
                  <el-button
                    v-if="row.status === 'active'"
                    text type="warning" size="small"
                    @click="rollbackVer(row)"
                  >回滚</el-button>
                </template>
              </el-table-column>
            </el-table>
          </article>
        </el-tab-pane>
        <el-tab-pane label="Agent 绑定" name="bindings">
          <article class="panel">
            <div class="panel-header-row">
              <span class="panel-title">Agent 绑定</span>
              <el-button size="small" @click="showAddBindingDialog = true">添加绑定</el-button>
            </div>
            <el-table :data="store.toolBindings" stripe size="small" v-loading="bindingsLoading">
              <el-table-column prop="agent_name" label="Agent" width="180" />
              <el-table-column prop="tool_version" label="版本" width="100" />
              <el-table-column label="自动调用" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.auto_call_enabled ? 'success' : 'info'" size="small">
                    {{ row.auto_call_enabled ? '允许' : '禁止' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="审批" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.approval_required ? 'warning' : 'info'" size="small">
                    {{ row.approval_required ? '需要' : '不需要' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button text type="danger" size="small" @click="removeBinding(row)">解除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </article>
        </el-tab-pane>
        <el-tab-pane label="执行记录" name="executions">
          <!-- keep existing executions content -->
        </el-tab-pane>
      </el-tabs>
```

Add the version creation dialog and binding dialog at the end of the template (before `</template>`):

```vue
      <el-dialog v-model="showCreateVersionDialog" title="创建新版本" width="480px" destroy-on-close>
        <el-form :model="versionForm" label-position="top">
          <el-form-item label="版本号">
            <el-input v-model="versionForm.version" placeholder="例如 1.1.0" />
          </el-form-item>
          <el-form-item label="显示名称">
            <el-input v-model="versionForm.display_name" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCreateVersionDialog = false">取消</el-button>
          <el-button type="primary" @click="doCreateVersion">创建</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="showAddBindingDialog" title="添加 Agent 绑定" width="480px" destroy-on-close>
        <el-form :model="bindingForm" label-position="top">
          <el-form-item label="Agent ID">
            <el-input v-model="bindingForm.agent_id" placeholder="输入 Agent ID" />
          </el-form-item>
          <el-form-item label="自动调用">
            <el-switch v-model="bindingForm.auto_call_enabled" />
          </el-form-item>
          <el-form-item label="需要审批">
            <el-switch v-model="bindingForm.approval_required" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showAddBindingDialog = false">取消</el-button>
          <el-button type="primary" @click="doAddBinding">添加</el-button>
        </template>
      </el-dialog>
```

Add the script logic:

```typescript
const versionsLoading = ref(false);
const bindingsLoading = ref(false);
const showCreateVersionDialog = ref(false);
const showAddBindingDialog = ref(false);

const versionForm = reactive({
  version: "",
  display_name: "",
});

const bindingForm = reactive<BindingCreateRequest>({
  agent_id: "",
  tool_id: "",
  auto_call_enabled: true,
  approval_required: false,
});

async function loadVersions() {
  if (!tool.value) return;
  versionsLoading.value = true;
  try {
    await store.fetchVersions(tool.value.id);
  } finally {
    versionsLoading.value = false;
  }
}

async function loadBindings() {
  if (!tool.value) return;
  bindingsLoading.value = true;
  try {
    await store.fetchBindings(tool.value.id);
  } finally {
    bindingsLoading.value = false;
  }
}

async function doCreateVersion() {
  if (!tool.value || !versionForm.version.trim()) return;
  await store.createVersion(tool.value.id, {
    version: versionForm.version.trim(),
    display_name: versionForm.display_name || versionForm.version.trim(),
    description: tool.value.description,
  });
  showCreateVersionDialog.value = false;
  ElMessage.success("版本已创建");
  versionForm.version = "";
  versionForm.display_name = "";
}

async function publishVer(row: ToolVersion) {
  if (!tool.value) return;
  await store.publishVersion(tool.value.id, row.id);
  ElMessage.success(`已发布版本 ${row.version}`);
  await loadVersions();
  await loadTool();
}

async function rollbackVer(row: ToolVersion) {
  if (!tool.value) return;
  await store.rollbackVersion(tool.value.id, row.id);
  ElMessage.success(`已回滚到版本 ${row.version}`);
  await loadVersions();
  await loadTool();
}

async function doAddBinding() {
  if (!tool.value || !bindingForm.agent_id.trim()) return;
  await store.createBinding({
    ...bindingForm,
    tool_id: tool.value.id,
  });
  showAddBindingDialog.value = false;
  ElMessage.success("绑定已添加");
  bindingForm.agent_id = "";
  await loadBindings();
}

async function removeBinding(row: AgentToolBinding) {
  await ElMessageBox.confirm("确认解除此绑定？", "解除绑定", { type: "warning" });
  await store.deleteBinding(row.id);
  ElMessage.success("绑定已解除");
  await loadBindings();
}

watch(activeTab, (tab) => {
  if (tab === "versions") loadVersions();
  if (tab === "bindings") loadBindings();
});
```

Add imports: `import type { AgentToolBinding, BindingCreateRequest, ToolVersion } from "@/types/tools.types";` and `import { ElMessageBox } from "element-plus";`

Add the CSS for `.panel-header-row`:
```css
.panel-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
```

- [ ] **Step 2: Run frontend typecheck**

Run:
```bash
cd frontend && npm run typecheck
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ops/tools/ToolDetailView.vue
git commit -m "feat: add real version history and agent binding tabs to tool detail"
```

---

### Task 10: Phase 3 — Database Migration for Sync and Runtime Events

**Files:**
- Create: `backend/migrations/versions/0043_tool_sync_and_runtime_events.py`
- Modify: `backend/app/models/tool.py`

- [ ] **Step 1: Add ORM models to backend/app/models/tool.py**

```python
class ToolSyncEvent(Base):
    __tablename__ = "tool_sync_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    tool_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    old_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )


class ToolRuntimeEvent(Base):
    __tablename__ = "tool_runtime_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)

    tool_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    execution_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)

    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
```

- [ ] **Step 2: Generate migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add tool_sync_events and tool_runtime_events"
```
Then rename to `0043_tool_sync_and_runtime_events.py` and run:
```bash
cd backend && alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/tool.py backend/migrations/versions/0043_tool_sync_and_runtime_events.py
git commit -m "feat: add tool_sync_events and tool_runtime_events tables"
```

---

### Task 11: Phase 3 — Tool Import Service (OpenAPI + MCP)

**Files:**
- Create: `backend/app/services/tool_import_service.py`
- Modify: `backend/app/services/tool_sync_service.py` — add sync event logging
- Modify: `backend/app/api/v1/tools.py` — add import endpoints

- [ ] **Step 1: Write tool_import_service.py**

```python
from __future__ import annotations

from typing import Any

import httpx
import yaml

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.models.tool import ToolRegistry
from app.repositories.tool_repo import ToolRepository


class ToolImportService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ToolRepository(session)

    async def preview_openapi(self, source: str) -> list[dict[str, Any]]:
        """Parse an OpenAPI spec (URL or raw JSON string) and return candidate tools."""
        spec = await self._load_openapi_spec(source)
        candidates: list[dict[str, Any]] = []

        for path, methods in spec.get("paths", {}).items():
            for method, operation in methods.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                candidates.append({
                    "tool_key": operation.get("operationId", f"openapi.{method}.{path.lstrip('/').replace('/', '.')}"),
                    "display_name": operation.get("summary", f"{method.upper()} {path}"),
                    "description": operation.get("description", ""),
                    "endpoint": path,
                    "method": method.upper(),
                    "parameters_schema": self._extract_params_schema(operation),
                    "returns_schema": self._extract_response_schema(operation),
                    "tool_type": "http",
                    "category": "http_api",
                    "source_type": "openapi",
                })
        return candidates

    async def import_openapi_tools(
        self, source: str, selected_keys: list[str]
    ) -> list[dict[str, Any]]:
        """Import selected OpenAPI tools as draft ToolRegistry entries."""
        candidates = await self.preview_openapi(source)
        imported = []
        for candidate in candidates:
            if candidate["tool_key"] not in selected_keys:
                continue
            tool = ToolRegistry(
                id=str(uuid7()),
                org_id=self._org_id,
                name=candidate["tool_key"],
                display_name=candidate["display_name"],
                description=candidate["description"],
                parameters_schema=candidate["parameters_schema"],
                returns_schema=candidate["returns_schema"],
                endpoint=candidate["endpoint"],
                timeout_ms=30000,
                access_roles=[],
                rate_limit_rpm=60,
                is_readonly=True,
                is_active=False,
                version="1.0.0",
                category="http_api",
                tool_type="http",
                status="draft",
                risk_level="medium",
                source_type="openapi",
                health_status="unknown",
            )
            tool = await self._repo.create(tool)
            imported.append({
                "id": tool.id,
                "tool_key": tool.name,
                "display_name": tool.display_name,
                "status": tool.status,
            })
        return imported

    async def preview_mcp_tools(self, server_url: str) -> list[dict[str, Any]]:
        """Discover tools from an MCP server endpoint."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(server_url, json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
            })
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("result", {}).get("tools", [])
            return [
                {
                    "tool_key": f"mcp.{t['name']}",
                    "display_name": t.get("description", t["name"]),
                    "description": t.get("description", ""),
                    "parameters_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
                    "returns_schema": {"type": "object", "properties": {}},
                    "tool_type": "mcp",
                    "category": "MCP",
                    "source_type": "mcp",
                }
                for t in tools
            ]

    async def _load_openapi_spec(self, source: str) -> dict[str, Any]:
        if source.startswith("http://") or source.startswith("https://"):
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(source)
                resp.raise_for_status()
                text = resp.text
        else:
            text = source

        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            import json
            return json.loads(text)

    @staticmethod
    def _extract_params_schema(operation: dict) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in operation.get("parameters", []):
            properties[param["name"]] = {
                "type": param.get("schema", {}).get("type", "string"),
                "description": param.get("description", ""),
            }
            if param.get("required"):
                required.append(param["name"])
        if "requestBody" in operation:
            content = operation["requestBody"].get("content", {})
            json_body = content.get("application/json", {})
            schema = json_body.get("schema", {})
            if schema:
                return schema
        return {"type": "object", "properties": properties, "required": required}

    @staticmethod
    def _extract_response_schema(operation: dict) -> dict[str, Any]:
        responses = operation.get("responses", {})
        success = responses.get("200") or responses.get("201") or {}
        content = success.get("content", {})
        json_body = content.get("application/json", {})
        return json_body.get("schema", {"type": "object", "properties": {}})
```

- [ ] **Step 2: Add import API endpoints to backend/app/api/v1/tools.py**

```python
@router.post("/import/openapi/preview", response_model=ResponseEnvelope[object])
async def preview_openapi_import(
    payload: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolImportService(db, current.org_id)
    candidates = await service.preview_openapi(payload.get("source", ""))
    return ResponseEnvelope(data={"candidates": candidates, "total": len(candidates)})


@router.post("/import/openapi", response_model=ResponseEnvelope[object])
async def import_openapi_tools(
    payload: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolImportService(db, current.org_id)
    imported = await service.import_openapi_tools(
        payload.get("source", ""),
        payload.get("tool_keys", []),
    )
    return ResponseEnvelope(data={"imported": imported})


@router.post("/import/mcp/preview", response_model=ResponseEnvelope[object])
async def preview_mcp_import(
    payload: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolImportService(db, current.org_id)
    candidates = await service.preview_mcp_tools(payload.get("server_url", ""))
    return ResponseEnvelope(data={"candidates": candidates, "total": len(candidates)})
```

Add `ToolImportService` to the imports.

- [ ] **Step 3: Upgrade tool_sync_service.py to write sync events**

In `backend/app/services/tool_sync_service.py`, after syncing each manifest, write a sync event:

```python
from app.models.tool import ToolSyncEvent

async def _write_sync_event(self, tool_id: str | None, event_type: str, old_hash: str | None, new_hash: str | None, message: str):
    event = ToolSyncEvent(
        id=str(uuid7()),
        org_id=self._org_id,
        tool_id=tool_id,
        event_type=event_type,
        source_type="builtin",
        old_hash=old_hash,
        new_hash=new_hash,
        message=message,
    )
    self._session.add(event)
    await self._session.flush()
```

Update the `_sync_one` method to call `_write_sync_event`.

- [ ] **Step 4: Verify services**

Run:
```bash
cd backend && python -c "from app.services.tool_import_service import ToolImportService; print('import service ok')"
```
Expected: "import service ok"

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tool_import_service.py backend/app/services/tool_sync_service.py backend/app/api/v1/tools.py
git commit -m "feat: add OpenAPI/MCP import service and sync event logging"
```

---

### Task 12: Phase 3 — SSE Event Streaming

**Files:**
- Modify: `backend/app/api/v1/tools.py` — implement SSE stream endpoint
- Create: `backend/app/services/tool_health_service.py`

- [ ] **Step 1: Implement SSE stream endpoint**

Replace the `tool_events_stream` stub in `backend/app/api/v1/tools.py`:

```python
import asyncio
from fastapi.responses import StreamingResponse
from sqlalchemy import select

@router.get("/events/stream")
async def tool_events_stream(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)

    async def event_generator():
        last_event_id = 0
        while True:
            try:
                result = await db.execute(
                    select(ToolRuntimeEvent)
                    .where(
                        ToolRuntimeEvent.org_id == current.org_id,
                        ToolRuntimeEvent.id > str(last_event_id) if last_event_id else True,
                    )
                    .order_by(ToolRuntimeEvent.created_at.desc())
                    .limit(50)
                )
                events = result.scalars().all()
                for event in reversed(events):
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(event.payload or {})}\n\n"
                    last_event_id = event.id
                await asyncio.sleep(5)
            except Exception:
                await asyncio.sleep(10)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

Add `import json` at the top of the file, and `ToolRuntimeEvent` to the model imports.

- [ ] **Step 2: Write tool_health_service.py**

```python
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import ToolRegistry
from app.repositories.tool_repo import ToolRepository


class ToolHealthService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ToolRepository(session)

    async def check_health(self) -> list[dict]:
        tools = await self._repo.list_all(self._org_id)
        results = []
        for tool in tools:
            recent = await self._repo.list_recent_executions(
                self._org_id,
                tool_id=tool.id,
                since=datetime.utcnow() - timedelta(hours=1),
                limit=20,
            )
            successes = sum(1 for r in recent if r.status == "success")
            total = len(recent)
            health = "unknown"
            if total > 0:
                rate = successes / total
                health = "healthy" if rate >= 0.95 else "degraded" if rate >= 0.7 else "unhealthy"
            results.append({
                "tool_id": tool.id,
                "tool_key": tool.name,
                "health": health,
                "success_rate": round(successes / total, 4) if total else None,
                "recent_calls": total,
            })
        return results
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/tools.py backend/app/services/tool_health_service.py
git commit -m "feat: implement SSE event streaming and health check service"
```

---

### Task 13: Phase 3 — Frontend Import Page Upgrade with Stepper (Impeccable)

**Files:**
- Modify: `frontend/src/views/ops/tools/ToolImportView.vue`

- [ ] **Step 1: Replace ToolImportView with real import wizards**

The import page now has 4 cards: builtin sync, OpenAPI import (with stepper), MCP import, and manual HTTP creation.

```vue
<template>
  <div class="tool-import">
    <section class="hero-card">
      <div>
        <h1 class="hero-title">导入与同步</h1>
        <p class="hero-subtitle">从内置代码、OpenAPI 规范、MCP Server 或手动创建接入外部工具能力。</p>
      </div>
    </section>

    <section class="cards-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">内置工具同步</h2>
            <p class="panel-desc">扫描 agent/tools/builtin/ 下的工具清单并同步到工具注册表。</p>
          </div>
          <el-button type="primary" :loading="store.syncingBuiltin" @click="runSync">立即同步</el-button>
        </div>
        <div v-if="store.lastSyncResult" class="sync-result">
          <div class="result-stats">
            <div class="stat-box"><span>新增</span><strong>{{ store.lastSyncResult.created }}</strong></div>
            <div class="stat-box"><span>更新</span><strong>{{ store.lastSyncResult.updated }}</strong></div>
            <div class="stat-box"><span>未变化</span><strong>{{ store.lastSyncResult.unchanged }}</strong></div>
          </div>
          <el-table :data="store.lastSyncResult.details" size="small" stripe>
            <el-table-column prop="tool_key" label="Tool Key" min-width="220" />
            <el-table-column prop="action" label="结果" width="120" />
          </el-table>
        </div>
      </article>

      <article class="panel">
        <h2 class="panel-title">OpenAPI 导入</h2>
        <p class="panel-desc">从 OpenAPI 3.x 规范的 URL 或 JSON 内容自动解析 API 端点并生成为 HTTP 工具。</p>
        <el-steps v-if="openapiStep > 0" :active="openapiStep" finish-status="success" align-center simple>
          <el-step title="输入来源" />
          <el-step title="预览候选" />
          <el-step title="导入" />
        </el-steps>
        <div v-if="openapiStep === 0" class="step-body">
          <el-button type="primary" @click="openapiStep = 1">开始导入</el-button>
        </div>
        <div v-else-if="openapiStep === 1" class="step-body">
          <el-form label-position="top">
            <el-form-item label="OpenAPI 规范 URL 或 JSON">
              <el-input v-model="openapiSource" type="textarea" :rows="6" placeholder="https://example.com/openapi.json 或粘贴 JSON" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="previewing" @click="previewOpenapi">解析</el-button>
              <el-button @click="openapiStep = 0">取消</el-button>
            </el-form-item>
          </el-form>
        </div>
        <div v-else-if="openapiStep === 2" class="step-body">
          <p>发现 {{ openapiCandidates.length }} 个候选工具：</p>
          <el-table :data="openapiCandidates" stripe size="small" max-height="320" @selection-change="onOpenapiSelect">
            <el-table-column type="selection" width="40" />
            <el-table-column prop="tool_key" label="Tool Key" min-width="200" />
            <el-table-column prop="display_name" label="名称" min-width="160" />
            <el-table-column prop="endpoint" label="路径" width="140" />
            <el-table-column prop="method" label="方法" width="70" />
          </el-table>
          <div class="step-actions">
            <el-button @click="openapiStep = 1">返回</el-button>
            <el-button type="primary" :loading="importing" @click="importOpenapi">导入选中工具</el-button>
          </div>
        </div>
        <div v-else-if="openapiStep === 3" class="step-body">
          <el-result icon="success" title="导入完成" :sub-title="`已导入 ${openapiImported.length} 个工具为草稿`" />
          <div class="step-actions">
            <el-button type="primary" @click="resetOpenapi">完成</el-button>
          </div>
        </div>
      </article>

      <article class="panel">
        <h2 class="panel-title">MCP Server 导入</h2>
        <p class="panel-desc">连接 MCP Server，自动发现其暴露的工具列表。</p>
        <div v-if="mcpStep === 0" class="step-body">
          <el-button type="primary" @click="mcpStep = 1">发现工具</el-button>
        </div>
        <div v-else class="step-body">
          <el-form label-position="top">
            <el-form-item label="MCP Server URL">
              <el-input v-model="mcpServerUrl" placeholder="http://localhost:8000/mcp" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="discoveringMcp" @click="discoverMcp">发现工具</el-button>
              <el-button @click="mcpStep = 0">取消</el-button>
            </el-form-item>
          </el-form>
          <div v-if="mcpCandidates.length" class="mt-3">
            <p>发现 {{ mcpCandidates.length }} 个 MCP 工具：</p>
            <el-table :data="mcpCandidates" stripe size="small">
              <el-table-column prop="tool_key" label="Tool Key" min-width="200" />
              <el-table-column prop="display_name" label="名称" min-width="160" />
              <el-table-column prop="description" label="描述" min-width="200" />
            </el-table>
          </div>
        </div>
      </article>

      <article class="panel muted">
        <h2 class="panel-title">手动创建 HTTP 工具</h2>
        <p class="panel-desc">如需单个 HTTP API 接入，请在工具库中直接创建并填写 endpoint 与 schema。</p>
        <el-button @click="$router.push('/ops/tools/catalog')">前往工具库</el-button>
      </article>
    </section>
  </div>
</template>
```

Add the script logic with openapi/mcp step management, preview/import API calls. The CSS keeps the existing style foundation and adds `.step-body`, `.step-actions`, `.mt-3` helpers.

- [ ] **Step 2: Run frontend typecheck**

Run:
```bash
cd frontend && npm run typecheck
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ops/tools/ToolImportView.vue
git commit -m "feat: implement real OpenAPI and MCP import wizards"
```

---

### Task 14: Phase 3 — SSE Live Updates in Execution Monitor

**Files:**
- Modify: `frontend/src/views/ops/tools/ToolExecutionView.vue`

- [ ] **Step 1: Add SSE connection for live execution updates**

Add to the script section:

```typescript
import { onBeforeUnmount, onMounted, ref } from "vue";

const sseConnected = ref(false);
let eventSource: EventSource | null = null;

function connectSSE() {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || "";
  eventSource = new EventSource(`${baseUrl}/v1/tools/events/stream`);

  eventSource.addEventListener("tool.execution.started", () => {
    loadExecutions();
    loadOverview();
  });

  eventSource.addEventListener("tool.execution.completed", () => {
    loadExecutions();
    loadOverview();
  });

  eventSource.addEventListener("tool.execution.failed", () => {
    loadExecutions();
    loadOverview();
  });

  eventSource.onopen = () => {
    sseConnected.value = true;
  };

  eventSource.onerror = () => {
    sseConnected.value = false;
    eventSource?.close();
    setTimeout(connectSSE, 10000);
  };
}

onMounted(() => {
  connectSSE();
});

onBeforeUnmount(() => {
  eventSource?.close();
});
```

Add an SSE indicator in the template header:

```vue
<el-tag :type="sseConnected ? 'success' : 'info'" size="small" style="margin-left: 8px">
  {{ sseConnected ? '实时' : '轮询' }}
</el-tag>
```

- [ ] **Step 2: Run frontend typecheck and build**

Run:
```bash
cd frontend && npm run typecheck && npm run build
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ops/tools/ToolExecutionView.vue
git commit -m "feat: add SSE live updates to execution monitor"
```

---

### Task 15: End-to-End Verification

**Files:**
- Test: `backend/tests/test_tools_api.py` — add phase 2/3 tests

- [ ] **Step 1: Write backend tests for version and binding endpoints**

```python
@pytest.mark.asyncio
async def test_list_versions_returns_real_data(monkeypatch):
    class FakeVersionService:
        def __init__(self, db, org_id):
            pass
        async def list_versions(self, tool_id):
            return [{"id": "v1", "tool_id": tool_id, "version": "1.0.0", "status": "active"}]

    monkeypatch.setattr(tools_api, "ToolVersionService", FakeVersionService)
    response = await tools_api.list_tool_versions("tool-1", current=current_user(), db=object())
    assert len(response.data) == 1
    assert response.data[0]["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_binding_crud_flow(monkeypatch):
    class FakeBindingService:
        def __init__(self, db, org_id):
            pass
        async def create_binding(self, payload):
            return {"id": "b1", "agent_id": payload["agent_id"], "status": "active"}
        async def delete_binding(self, binding_id):
            return {"deleted": True}

    monkeypatch.setattr(tools_api, "ToolBindingService", FakeBindingService)
    create_resp = await tools_api.create_binding(
        payload=tools_api.BindingCreate(agent_id="agent-1", tool_id="tool-1"),
        current=current_user(),
        db=object(),
    )
    assert create_resp.data["agent_id"] == "agent-1"
```

- [ ] **Step 2: Run all backend tests**

Run:
```bash
pytest backend/tests/test_tools_api.py -q
```
Expected: All tests PASS.

- [ ] **Step 3: Run frontend build**

Run:
```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_tools_api.py
git commit -m "test: add phase 2 binding and version endpoint tests"
```

---

## Self-Review

### Spec coverage
- Phase 2 version management: Tasks 1-4 (models, repos, services, API), Task 9 (frontend tabs)
- Phase 2 agent bindings: Tasks 1-4 (models, repos, services, API), Tasks 7-9 (frontend)
- Phase 2 ToolResolver upgrade: Task 5
- Phase 2 ToolGuard: Task 6
- Phase 3 external import: Tasks 10-11 (backend), Task 13 (frontend)
- Phase 3 SSE/real-time: Task 12 (backend), Task 14 (frontend)
- Phase 3 health check: Task 12

### Placeholder scan
- No TBD or TODO entries
- All endpoints have real implementations
- All frontend pages have real data flow

### Type consistency
- `tool_key` used consistently across backend (model.name) and frontend (tool_key)
- `status` lifecycle state vs `health_status` runtime health maintained
- `binding_status` distinct from tool `status`
