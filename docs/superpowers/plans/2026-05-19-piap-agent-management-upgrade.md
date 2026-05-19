# PIAP Agent 管理页面产品化改造 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Frontend 要求:** 前端任务使用 `impeccable` (frontend-design) 技能实现，确保 UI 设计品质。

**Goal:** 将 `/ops/agents` 从展示型页面升级为真实可信的 AgentOps 控制台（P0+P1 范围）

**Architecture:** 全栈逐层实施 — Alembic迁移 → ORM模型 → topology_catalog → AgentRuntimeGuard → AgentManager → Schemas → Repositories → Service → API → 前端类型/API/Store → 路由菜单 → AgentManageView大改

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (后端), Vue3/TypeScript/Pinia/ElementPlus/ECharts (前端)

**Spec:** `docs/superpowers/specs/2026-05-19-piap-agent-management-upgrade-design.md`

---

## 文件清单

| 操作 | 文件 |
|------|------|
| CREATE | `backend/migrations/versions/0035_agent_ops_productize.py` |
| MODIFY | `backend/app/models/agent_ops.py` |
| MODIFY | `backend/agent/topology_catalog.py` |
| CREATE | `backend/agent/router/runtime_guard.py` |
| MODIFY | `backend/agent/router/agent_manager.py` |
| MODIFY | `backend/app/schemas/agent_ops.py` |
| MODIFY | `backend/app/repositories/agent_ops_repo.py` |
| MODIFY | `backend/app/services/agent_ops_service.py` |
| MODIFY | `backend/app/api/v1/agent_ops.py` |
| MODIFY | `frontend/src/types/agent-ops.types.ts` |
| MODIFY | `frontend/src/api/agent-ops.api.ts` |
| MODIFY | `frontend/src/stores/agent-ops.store.ts` |
| MODIFY | `frontend/src/router/routes/ops.routes.ts` |
| MODIFY | `frontend/src/composables/useMenu.ts` |
| MODIFY | `frontend/src/views/ops/AgentManageView.vue` |

---

### Task 1: Alembic 迁移 0035 — 数据库字段变更

**Files:**
- CREATE: `backend/migrations/versions/0035_agent_ops_productize.py`

- [ ] **Step 1: 生成空迁移**

```bash
cd backend && alembic revision -m "agent_ops_productize"
```

- [ ] **Step 2: 编写迁移脚本**

```python
"""agent_ops_productize

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-19

Add lifecycle_status, group_key, route_enabled, supports_route_toggle, customer_visible_description
to agent_definitions. Add runtime_status, health check, error tracking fields to agent_runtime_instances.
Create agent_runtime_events table. Add blocked/blocked_reason to agent_route_logs.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agent_definitions 新增字段 ---
    op.add_column("agent_definitions", sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default="active", comment="active/partial/planned/legacy/deprecated"))
    op.add_column("agent_definitions", sa.Column("group_key", sa.String(32), nullable=False, server_default="core", comment="core/memory/planned/legacy"))
    op.add_column("agent_definitions", sa.Column("route_enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE"), comment="是否参与路由"))
    op.add_column("agent_definitions", sa.Column("supports_route_toggle", sa.Boolean(), nullable=False, server_default=sa.text("TRUE"), comment="是否允许暂停恢复路由"))
    op.add_column("agent_definitions", sa.Column("customer_visible_description", sa.Text(), nullable=True, comment="给客户看的能力说明"))

    # --- agent_runtime_instances 新增字段 ---
    op.add_column("agent_runtime_instances", sa.Column("runtime_status", sa.String(32), nullable=False, server_default="stopped", comment="running/stopped/degraded/maintenance/readonly"))
    op.add_column("agent_runtime_instances", sa.Column("last_health_check_at", sa.DateTime(), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("last_error_message", sa.Text(), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("last_error_at", sa.DateTime(), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("maintenance_reason", sa.Text(), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("updated_by", sa.dialects.mysql.BINARY(16), nullable=True))

    # 将现有 status 值同步到 runtime_status
    op.execute(sa.text("UPDATE agent_runtime_instances SET runtime_status = status WHERE runtime_status = 'stopped'"))

    # --- 新建 agent_runtime_events 表 ---
    op.create_table(
        "agent_runtime_events",
        sa.Column("id", sa.dialects.mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", sa.dialects.mysql.BINARY(16), nullable=False, index=True),
        sa.Column("agent_id", sa.dialects.mysql.BINARY(16), nullable=False, index=True),
        sa.Column("runtime_key", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False, comment="pause_route/resume_route/start/stop/maintenance"),
        sa.Column("before_status", sa.String(32), nullable=True),
        sa.Column("after_status", sa.String(32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("operator_id", sa.dialects.mysql.BINARY(16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )

    # --- agent_route_logs 新增字段 ---
    op.add_column("agent_route_logs", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("FALSE"), comment="是否被运行态阻止"))
    op.add_column("agent_route_logs", sa.Column("blocked_reason", sa.Text(), nullable=True, comment="阻止原因"))


def downgrade() -> None:
    op.drop_column("agent_route_logs", "blocked_reason")
    op.drop_column("agent_route_logs", "blocked")
    op.drop_table("agent_runtime_events")
    op.drop_column("agent_runtime_instances", "updated_by")
    op.drop_column("agent_runtime_instances", "maintenance_reason")
    op.drop_column("agent_runtime_instances", "last_error_at")
    op.drop_column("agent_runtime_instances", "last_error_message")
    op.drop_column("agent_runtime_instances", "last_health_check_at")
    op.drop_column("agent_runtime_instances", "runtime_status")
    op.drop_column("agent_definitions", "customer_visible_description")
    op.drop_column("agent_definitions", "supports_route_toggle")
    op.drop_column("agent_definitions", "route_enabled")
    op.drop_column("agent_definitions", "group_key")
    op.drop_column("agent_definitions", "lifecycle_status")
```

- [ ] **Step 3: 运行迁移**

```bash
cd backend && alembic upgrade head
```

Expected: 迁移成功，数据库表结构更新

- [ ] **Step 4: 验证迁移**

```bash
cd backend && alembic current
```

Expected: 显示 0035

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/0035_agent_ops_productize.py
git commit -m "feat(db): add agent productization fields — lifecycle_status, group_key, route_enabled, runtime_events table

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: ORM 模型更新

**Files:**
- MODIFY: `backend/app/models/agent_ops.py`

- [ ] **Step 1: 修改 AgentDefinition — 新增 5 个字段**

找到 `class AgentDefinition(Base, TimestampMixin):` 类，在 `current_version` 字段后添加：

```python
# 新增：产品化字段
lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", comment="active/partial/planned/legacy/deprecated")
group_key: Mapped[str] = mapped_column(String(32), nullable=False, default="core", comment="core/memory/planned/legacy")
route_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否参与路由")
supports_route_toggle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否允许暂停恢复路由")
customer_visible_description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="给客户看的能力说明")
```

- [ ] **Step 2: 修改 AgentRuntimeInstance — 新增 6 个字段**

找到 `class AgentRuntimeInstance(Base, TimestampMixin):` 类，在 `last_stopped_at` 字段后添加：

```python
# 新增：增强运行态字段
runtime_status: Mapped[str] = mapped_column(String(32), nullable=False, default="stopped", comment="running/stopped/degraded/maintenance/readonly")
last_health_check_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
last_error_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
maintenance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
updated_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
```

- [ ] **Step 3: 新增 AgentRuntimeEvent 模型**

在文件末尾（`AgentRouteLog` 类之后）添加：

```python
class AgentRuntimeEvent(Base, TimestampMixin):
    """Agent 运行态操作事件日志 — pause_route/resume_route/start/stop/maintenance"""
    __tablename__ = "agent_runtime_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    agent_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    runtime_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="pause_route/resume_route/start/stop/maintenance")
    before_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    after_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
```

- [ ] **Step 4: 修改 AgentRouteLog — 新增 2 个字段**

找到 `class AgentRouteLog(Base, TimestampMixin):` 类，在 `latency_ms` 字段后添加：

```python
# 新增：运行态阻止
blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否被运行态阻止")
blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="阻止原因")
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/agent_ops.py
git commit -m "feat(model): add productization fields to AgentDefinition, AgentRuntimeInstance, new AgentRuntimeEvent model

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: topology_catalog.py 补充产品化字段

**Files:**
- MODIFY: `backend/agent/topology_catalog.py`

- [ ] **Step 1: 为 9 个 Agent 补充产品字段**

将 `REGISTERED_SUBGRAPHS` 列表中每个 Agent 的字典替换为以下内容：

```python
REGISTERED_SUBGRAPHS: list[dict[str, Any]] = [
    {
        "name": "Agent Manager",
        "description": "统一入口路由，负责将请求分发给聊天或检测 Agent。",
        "workflow_binding": "agent_manager_v1",
        "subgraph_key": "agent_manager",
        "entry_graph": "AgentManagerService",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "customer_visible_description": "统一请求入口，负责将用户请求智能路由分发给对应的专业Agent处理。",
    },
    {
        "name": "Quality Chat",
        "description": "轻量级智能问答入口，支持附件上传和 RAG 空间选择。",
        "workflow_binding": "quality_chat_v2",
        "subgraph_key": "chat",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": True,
        "graph_version": "v2",
        "is_active": True,
        "lifecycle_status": "active",
        "group": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "customer_visible_description": "轻量级智能问答入口，支持附件上传和RAG知识空间检索，适用于日常产品质量咨询。",
    },
    {
        "name": "Inspection Task Agent",
        "description": "负责正式质检任务创建、文件/图片检测、结果落库。",
        "workflow_binding": "inspection_task_v1",
        "subgraph_key": "inspection_task",
        "entry_graph": "InspectionTaskGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "customer_visible_description": "负责正式质检任务的全流程：创建任务、图片/文件检测、结果计算与入库。",
    },
    {
        "name": "Quality Judgement",
        "description": "统一质量判定（合并 Legacy + LLM-native），支持 chat / file / task 多策略。",
        "workflow_binding": "quality_judgement_v2",
        "subgraph_key": "quality_judgement",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": True,
        "graph_version": "v2",
        "is_active": True,
        "lifecycle_status": "active",
        "group": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "customer_visible_description": "统一质量判定引擎，支持文本问答、文件解析、图片检测等多模式质检，自动合成判定证据。",
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
        "lifecycle_status": "planned",
        "group": "planned",
        "route_enabled": False,
        "supports_route_toggle": False,
        "customer_visible_description": "市场价格、销量、渠道异常检测与预警（规划中，暂未接入业务链路）。",
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
        "lifecycle_status": "planned",
        "group": "planned",
        "route_enabled": False,
        "supports_route_toggle": False,
        "customer_visible_description": "新闻、社交媒体、投诉举报等多渠道舆情采集与分析（规划中，暂未接入业务链路）。",
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
        "lifecycle_status": "planned",
        "group": "planned",
        "route_enabled": False,
        "supports_route_toggle": False,
        "customer_visible_description": "风险融合、趋势推演和情景预测（规划中，暂未接入业务链路）。",
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
        "lifecycle_status": "planned",
        "group": "planned",
        "route_enabled": False,
        "supports_route_toggle": False,
        "customer_visible_description": "抽检计划生成、样品管理和现场检查记录（规划中，暂未接入业务链路）。",
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
        "lifecycle_status": "planned",
        "group": "planned",
        "route_enabled": False,
        "supports_route_toggle": False,
        "customer_visible_description": "实验室样品检测指标解析和标准比对（规划中，暂未接入业务链路）。",
    },
]
```

- [ ] **Step 2: 修改 get_registered_subgraphs() 返回不裁剪字段**

当前函数使用 `get_registered_subgraphs()` 已返回完整 dict（`return [dict(item) for item in REGISTERED_SUBGRAPHS]`），不需修改。但确认 `agent_ops_service.py` 中 `_sync_registered_agents()` 使用 `dict(item)` 方式读取，能正确传递新字段。

- [ ] **Step 3: Commit**

```bash
git add backend/agent/topology_catalog.py
git commit -m "feat(catalog): add lifecycle_status, group, route_enabled, customer_visible_description to all 9 agents

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 新建 AgentRuntimeGuard

**Files:**
- CREATE: `backend/agent/router/runtime_guard.py`

- [ ] **Step 1: 创建 runtime_guard.py**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_ops import AgentDefinition, AgentRuntimeInstance


@dataclass
class RuntimeGuardResult:
    allowed: bool
    reason: str = ""
    customer_message: str = ""

    @classmethod
    def ok(cls) -> RuntimeGuardResult:
        return cls(allowed=True)

    @classmethod
    def blocked(cls, reason: str, customer_message: str) -> RuntimeGuardResult:
        return cls(allowed=False, reason=reason, customer_message=customer_message)


class AgentRuntimeGuard:
    """在执行前检查 Agent 运行时状态，确保暂停/停止操作真实生效。"""

    @staticmethod
    async def check(
        org_id: str,
        selected_agent: str,  # "chat" | "inspection_task"
        sub_route: str,
        session: AsyncSession,
    ) -> RuntimeGuardResult:
        subgraph_key = _agent_to_subgraph_key(selected_agent, sub_route)
        if not subgraph_key:
            return RuntimeGuardResult.ok()

        # 查询 Agent 定义
        def_result = await session.execute(
            select(AgentDefinition).where(
                AgentDefinition.org_id == org_id,
                AgentDefinition.subgraph_key == subgraph_key,
                AgentDefinition.deleted_at.is_(None),
            ).order_by(AgentDefinition.updated_at.desc()).limit(1)
        )
        agent_def = def_result.scalar_one_or_none()

        if not agent_def:
            return RuntimeGuardResult.blocked(
                reason=f"Agent subgraph '{subgraph_key}' not found in definitions",
                customer_message=f"服务暂不可用（{subgraph_key}），请联系管理员。",
            )

        if not agent_def.route_enabled:
            return RuntimeGuardResult.blocked(
                reason=f"Agent '{agent_def.name}' route_enabled=False",
                customer_message=f"{agent_def.name} 当前已暂停路由，请稍后重试或联系管理员恢复。",
            )

        # 查询运行时实例
        rt_result = await session.execute(
            select(AgentRuntimeInstance).where(
                AgentRuntimeInstance.org_id == org_id,
                AgentRuntimeInstance.agent_id == agent_def.id,
                AgentRuntimeInstance.deleted_at.is_(None),
            ).order_by(AgentRuntimeInstance.updated_at.desc()).limit(1)
        )
        runtime = rt_result.scalar_one_or_none()

        if runtime and runtime.runtime_status not in ("running", "degraded"):
            status_msg = {
                "stopped": "已停止运行",
                "maintenance": "正在维护中",
                "readonly": "当前为只读模式",
            }.get(runtime.runtime_status, "不可用")
            return RuntimeGuardResult.blocked(
                reason=f"Agent '{agent_def.name}' runtime_status={runtime.runtime_status}",
                customer_message=f"{agent_def.name} {status_msg}，暂时无法处理请求。",
            )

        return RuntimeGuardResult.ok()


def _agent_to_subgraph_key(selected_agent: str, sub_route: str) -> str | None:
    """将路由决策中的 agent+sub_route 映射到 subgraph_key"""
    if selected_agent == "chat":
        return "chat"
    if selected_agent == "inspection_task":
        return "inspection_task"
    # 兜底：尝试从 sub_route 推断
    if sub_route in ("general_chat", "rag_qa"):
        return "chat"
    if sub_route in ("quality_qa", "task_create", "inspection_execute"):
        return "inspection_task"
    return None
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/router/runtime_guard.py
git commit -m "feat(router): add AgentRuntimeGuard — runtime status check before agent execution

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: AgentManager 集成运行时守卫

**Files:**
- MODIFY: `backend/agent/router/agent_manager.py`

- [ ] **Step 1: 在 run() 方法中集成守卫**

需要获取数据库 session。修改 `run()` 方法签名增加可选的 `db_session` 参数，在 `decide()` 之后、agent 执行之前插入守卫：

```python
async def run(self, request: NormalizedRequest, db_session=None) -> AgentRouterOutput:
    router_input = AgentRouterInput(
        query=request.query,
        request_kind=request.request_kind,
        attachments=[item.model_dump() for item in request.attachments],
        image_urls=request.image_urls,
        route_hints=request.route_hints,
        ext=request.ext,
    )

    decision = self._route_policy.decide(router_input)
    if decision.fallback_agent == "model_classifier":
        decision = await self._route_policy.decide_with_model(
            router_input,
            llm_client=await self._build_model_classifier_client(request),
        )

    # ===== 新增: 运行时守卫检查 =====
    if db_session is not None:
        from agent.router.runtime_guard import AgentRuntimeGuard
        guard_result = await AgentRuntimeGuard.check(
            org_id=str(request.org_id),
            selected_agent=decision.selected_agent,
            sub_route=decision.sub_route,
            session=db_session,
        )
        if not guard_result.allowed:
            return AgentRouterOutput(
                route_decision=decision,
                agent_output={
                    "message_type": "agent_unavailable",
                    "answer": guard_result.customer_message,
                },
                status="blocked",
                degrade_reason=guard_result.reason,
            )
    # ===== 守卫结束 =====

    try:
        if decision.selected_agent == "inspection_task":
            agent_output = await self.task_agent.run(request, decision)
        else:
            agent_output = await self.chat_agent.run(request, decision)
    except Exception as exc:
        logger.exception(...)
        return AgentRouterOutput(...)

    return AgentRouterOutput(
        route_decision=decision,
        agent_output=agent_output if isinstance(agent_output, dict) else agent_output.model_dump(),
        status="completed",
    )
```

- [ ] **Step 2: 找到调用 AgentManager.run() 的地方传入 session**

搜索调用 `agent_manager.run()` 的代码（通常在 `agent_manager_service.py` 或 `quality_agent_orchestrator_service.py`），传递 `db_session`：

```python
# 原先: output = await agent_manager.run(request)
# 改为: output = await agent_manager.run(request, db_session=self._session)
```

- [ ] **Step 3: Commit**

```bash
git add backend/agent/router/agent_manager.py
git add backend/app/services/agent_manager_service.py  # 或其他调用文件
git commit -m "feat(agent-manager): integrate AgentRuntimeGuard — block execution when agent is paused/stopped

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Schemas 更新

**Files:**
- MODIFY: `backend/app/schemas/agent_ops.py`

- [ ] **Step 1: AgentDefinitionBase 新增字段**

```python
class AgentDefinitionBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(default=None)
    prompt_version_id: Optional[str] = Field(default=None)
    workflow_binding: Optional[str] = Field(default=None, max_length=100)
    intent_config_id: Optional[str] = Field(default=None)
    subgraph_key: str = Field(default="quality_judgement", max_length=64)
    entry_graph: Optional[str] = Field(default=None, max_length=128)
    supports_start_stop: bool = Field(default=True)
    graph_version: str = Field(default="v1", max_length=32)
    is_active: bool = Field(default=True)
    # 新增字段
    lifecycle_status: str = Field(default="active", max_length=32)
    group_key: str = Field(default="core", max_length=32)
    route_enabled: bool = Field(default=True)
    supports_route_toggle: bool = Field(default=True)
    customer_visible_description: Optional[str] = Field(default=None)
```

- [ ] **Step 2: AgentRuntimeInstanceResponse 新增字段**

```python
class AgentRuntimeInstanceResponse(BaseModel):
    runtime_key: str
    agent_id: str
    agent_name: str
    subgraph_key: str
    status: str
    runtime_status: str = "stopped"  # 新增
    supports_start_stop: bool
    is_active: bool
    lifecycle_status: Optional[str] = None  # 新增
    group_key: Optional[str] = None  # 新增
    route_enabled: bool = True  # 新增
    supports_route_toggle: bool = True  # 新增
    customer_visible_description: Optional[str] = None  # 新增
    execution_count: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    last_executed_at: Optional[datetime] = None
    last_started_at: Optional[datetime] = None
    last_stopped_at: Optional[datetime] = None
    last_error_message: Optional[str] = None  # 新增
    maintenance_reason: Optional[str] = None  # 新增
```

- [ ] **Step 3: 新增 AgentRuntimeEventResponse 和 AgentDetailResponse**

```python
class AgentRuntimeEventResponse(BaseModel):
    id: str
    org_id: str
    agent_id: str
    runtime_key: str
    event_type: str  # pause_route/resume_route/start/stop/maintenance
    before_status: Optional[str] = None
    after_status: Optional[str] = None
    reason: Optional[str] = None
    operator_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentDetailResponse(AgentDefinitionResponse):
    """Agent 详情 — 包含绑定资源和操作记录"""
    bound_prompt_version: Optional[PromptVersionResponse] = None
    bound_routes: list[IntentRouteResponse] = Field(default_factory=list)
    runtime_events: list[AgentRuntimeEventResponse] = Field(default_factory=list)
```

- [ ] **Step 4: AgentRuntimeOverviewResponse 新增字段**

```python
class AgentRuntimeOverviewResponse(BaseModel):
    active_agents: int = 0
    running_agents: int = 0
    stopped_agents: int = 0
    total_executions: int = 0
    avg_latency_ms: float = 0.0
    queued_tasks: int = 0
    completed_today: int = 0
    success_rate: float = 0.0  # 新增
    recent_errors: int = 0  # 新增
```

- [ ] **Step 5: 新增 pause/resume route 请求 Schema**

```python
class PauseRouteRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="暂停原因")


class TopologyQueryParams(BaseModel):
    mode: str = Field(default="design", description="design / runtime")
    include_planned: bool = Field(default=True)
    include_legacy: bool = Field(default=False)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/agent_ops.py
git commit -m "feat(schema): add productization fields to schemas — lifecycle, group, route, runtime events, detail response

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Repositories 增强

**Files:**
- MODIFY: `backend/app/repositories/agent_ops_repo.py`

- [ ] **Step 1: AgentDefinitionRepository — 更新 create 方法使用新字段**

在 `AgentDefinitionRepository.create()` 中，确保 `data` dict 中的新字段能被接受（当前实现使用 `**data` 展开，已自适应）。

- [ ] **Step 2: AgentRuntimeRepository — 新增事件记录方法**

在 `AgentRuntimeRepository` 类末尾添加：

```python
async def create_event(self, data: dict) -> AgentRuntimeEvent:
    from app.models.agent_ops import AgentRuntimeEvent
    obj = AgentRuntimeEvent(org_id=self._org_id, **data)
    self._session.add(obj)
    await self._session.flush()
    return obj

async def list_events(self, agent_id: str, limit: int = 20) -> list[AgentRuntimeEvent]:
    from app.models.agent_ops import AgentRuntimeEvent
    result = await self._session.execute(
        select(AgentRuntimeEvent).where(
            AgentRuntimeEvent.org_id == self._org_id,
            AgentRuntimeEvent.agent_id == agent_id,
            AgentRuntimeEvent.deleted_at.is_(None),
        ).order_by(AgentRuntimeEvent.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
```

- [ ] **Step 3: AgentRuntimeRepository — 增强 set_status 方法**

```python
async def set_runtime_status(self, runtime_key: str, runtime_status: str, *, updated_by: str | None = None) -> AgentRuntimeInstance | None:
    obj = await self.dedupe_by_runtime_key(runtime_key)
    if not obj:
        return None
    obj.runtime_status = runtime_status
    obj.updated_by = updated_by
    if runtime_status == "running":
        obj.last_started_at = datetime.utcnow()
    if runtime_status == "stopped":
        obj.last_stopped_at = datetime.utcnow()
    await self._session.flush()
    return obj
```

- [ ] **Step 4: 新增 AgentRuntimeEventRepository**

在文件末尾添加：

```python
class AgentRuntimeEventRepository(AgentOpsRepository):
    async def create(self, data: dict) -> AgentRuntimeEvent:
        from app.models.agent_ops import AgentRuntimeEvent
        obj = AgentRuntimeEvent(org_id=self._org_id, **data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_by_agent(self, agent_id: str, limit: int = 20) -> list[AgentRuntimeEvent]:
        from app.models.agent_ops import AgentRuntimeEvent
        result = await self._session.execute(
            select(AgentRuntimeEvent).where(
                AgentRuntimeEvent.org_id == self._org_id,
                AgentRuntimeEvent.agent_id == agent_id,
                AgentRuntimeEvent.deleted_at.is_(None),
            ).order_by(AgentRuntimeEvent.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
```

- [ ] **Step 5: 确保 AgentRuntimeRepository.ensure_for_agent 使用新字段**

修改 `ensure_for_agent()` 使之读取 `agent.route_enabled`、`agent.lifecycle_status`：

```python
async def ensure_for_agent(self, agent: AgentDefinition) -> AgentRuntimeInstance:
    runtime_key = f"{agent.name}:{agent.subgraph_key}"
    existing = await self.dedupe_by_agent_id(str(agent.id))
    if not existing:
        existing = await self.dedupe_by_runtime_key(runtime_key)
    if existing:
        existing.agent_id = str(agent.id)
        existing.runtime_key = runtime_key
        existing.subgraph_key = str(agent.subgraph_key or "quality_judgement")
        existing.status = "running" if agent.is_active else "stopped"
        existing.runtime_status = "running" if agent.is_active else "stopped"
        existing.supports_start_stop = bool(agent.supports_start_stop)
        existing.metadata_json = {"entry_graph": agent.entry_graph, "graph_version": agent.graph_version}
        await self._session.flush()
        return existing
    obj = AgentRuntimeInstance(
        org_id=self._org_id,
        agent_id=str(agent.id),
        runtime_key=runtime_key,
        subgraph_key=str(agent.subgraph_key or "quality_judgement"),
        status="running" if agent.is_active else "stopped",
        runtime_status="running" if agent.is_active else "stopped",
        supports_start_stop=bool(agent.supports_start_stop),
        metadata_json={"entry_graph": agent.entry_graph, "graph_version": agent.graph_version},
    )
    self._session.add(obj)
    await self._session.flush()
    await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
    return obj
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/agent_ops_repo.py
git commit -m "feat(repo): add runtime event repository, enhance set_runtime_status, ensure_for_agent with new fields

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Service 层改造

**Files:**
- MODIFY: `backend/app/services/agent_ops_service.py`

- [ ] **Step 1: _sync_registered_agents() — 增加旧 Agent 清理逻辑**

```python
async def _sync_registered_agents(self) -> None:
    catalog_subgraph_keys = {str(item["subgraph_key"]) for item in get_registered_subgraphs()}

    # 同步 catalog 中的 Agent
    for item in get_registered_subgraphs():
        existing = await self._agent_repo.dedupe_by_subgraph_key(str(item["subgraph_key"]))
        payload = dict(item)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            await self._session.flush()
            await self._runtime_repo.ensure_for_agent(existing)
            continue
        created = await self._agent_repo.create(payload)
        await self._runtime_repo.ensure_for_agent(created)

    # 新增：标记不在 catalog 中的 Agent 为 deprecated
    all_db_agents = await self._agent_repo.list_all_active()
    for db_agent in all_db_agents:
        if db_agent.subgraph_key not in catalog_subgraph_keys:
            db_agent.lifecycle_status = "deprecated"
            db_agent.route_enabled = False
            db_agent.is_active = False
            runtime = await self._runtime_repo.dedupe_by_agent_id(str(db_agent.id))
            if runtime:
                runtime.runtime_status = "stopped"
    await self._session.flush()
```

- [ ] **Step 2: set_runtime_status() — 增加审计日志**

```python
async def set_runtime_status(self, runtime_key: str, *, status: str) -> AgentRuntimeInstanceResponse:
    await self._sync_registered_agents()
    runtime = await self._runtime_repo.dedupe_by_runtime_key(runtime_key)
    if not runtime:
        raise NotFoundError(f"Runtime {runtime_key} not found")
    if not bool(runtime.supports_start_stop):
        raise ValidationError(f"Runtime {runtime_key} does not support start/stop")

    before_status = runtime.runtime_status
    runtime = await self._runtime_repo.set_runtime_status(runtime_key, status, updated_by=self._actor_id)
    if not runtime:
        raise NotFoundError(f"Runtime {runtime_key} not found")

    # 新增：写入审计事件
    await self._runtime_repo.create_event({
        "agent_id": str(runtime.agent_id),
        "runtime_key": runtime_key,
        "event_type": "start" if status == "running" else "stop",
        "before_status": before_status,
        "after_status": status,
        "operator_id": self._actor_id,
    })
    # ... 返回 response
```

- [ ] **Step 3: 新增 pause_route() 和 resume_route() 方法**

```python
async def pause_route(self, runtime_key: str, reason: str) -> AgentRuntimeInstanceResponse:
    await self._sync_registered_agents()
    runtime = await self._runtime_repo.dedupe_by_runtime_key(runtime_key)
    if not runtime:
        raise NotFoundError(f"Runtime {runtime_key} not found")
    agent = await self._agent_repo.get(str(runtime.agent_id))
    if not agent:
        raise NotFoundError(f"Agent {runtime.agent_id} not found")
    if not agent.supports_route_toggle:
        raise ValidationError(f"Agent {agent.name} does not support route toggle")

    agent.route_enabled = False
    await self._runtime_repo.create_event({
        "agent_id": str(agent.id),
        "runtime_key": runtime_key,
        "event_type": "pause_route",
        "before_status": "route_enabled",
        "after_status": "route_paused",
        "reason": reason,
        "operator_id": self._actor_id,
    })
    await self._session.flush()
    return await self._build_runtime_response(runtime, agent)

async def resume_route(self, runtime_key: str) -> AgentRuntimeInstanceResponse:
    await self._sync_registered_agents()
    runtime = await self._runtime_repo.dedupe_by_runtime_key(runtime_key)
    if not runtime:
        raise NotFoundError(f"Runtime {runtime_key} not found")
    agent = await self._agent_repo.get(str(runtime.agent_id))
    if not agent:
        raise NotFoundError(f"Agent {runtime.agent_id} not found")

    agent.route_enabled = True
    await self._runtime_repo.create_event({
        "agent_id": str(agent.id),
        "runtime_key": runtime_key,
        "event_type": "resume_route",
        "before_status": "route_paused",
        "after_status": "route_enabled",
        "operator_id": self._actor_id,
    })
    await self._session.flush()
    return await self._build_runtime_response(runtime, agent)
```

- [ ] **Step 4: list_runtime_agents() — 返回新字段**

```python
async def list_runtime_agents(self) -> list[AgentRuntimeInstanceResponse]:
    await self._sync_registered_agents()
    runtime_rows = await self._runtime_repo.list_with_agents()
    metrics_repo = AgentExecutionMetricsRepository(self._session, self._org_id)
    items: list[AgentRuntimeInstanceResponse] = []
    for runtime, agent in runtime_rows:
        metrics = await metrics_repo.get_metrics(str(agent.id)) or {}
        items.append(AgentRuntimeInstanceResponse(
            runtime_key=runtime.runtime_key,
            agent_id=str(agent.id),
            agent_name=agent.name,
            subgraph_key=runtime.subgraph_key,
            status=runtime.status,
            runtime_status=runtime.runtime_status or runtime.status,
            supports_start_stop=runtime.supports_start_stop,
            is_active=agent.is_active,
            lifecycle_status=agent.lifecycle_status,
            group_key=agent.group_key,
            route_enabled=agent.route_enabled,
            supports_route_toggle=agent.supports_route_toggle,
            customer_visible_description=agent.customer_visible_description,
            execution_count=int(metrics.get("execution_count") or 0),
            success_rate=float(metrics.get("success_rate") or 0.0),
            avg_latency_ms=float(metrics.get("avg_latency_ms") or 0.0),
            last_executed_at=metrics.get("last_executed_at"),
            last_started_at=runtime.last_started_at,
            last_stopped_at=runtime.last_stopped_at,
            last_error_message=runtime.last_error_message,
            maintenance_reason=runtime.maintenance_reason,
        ))
    return items
```

- [ ] **Step 5: 新增 get_agent_detail() 和 list_runtime_events()**

```python
async def get_agent_detail(self, agent_id: str) -> AgentDetailResponse:
    agent = await self.get_agent(agent_id)
    # 获取绑定的 Prompt
    bound_prompt = None
    if agent.prompt_version_id:
        bound_prompt = await self.get_prompt(agent.prompt_version_id)
    # 获取绑定的路由规则
    routes, _ = await self._route_repo.list_paged(
        filters={"agent_id": agent_id}, page=1, size=10
    )
    # 获取运行态事件
    events = await self._runtime_repo.list_events(agent_id, limit=20)
    return AgentDetailResponse(
        **agent.model_dump(),
        bound_prompt_version=bound_prompt,
        bound_routes=[IntentRouteResponse.model_validate(r) for r in routes],
        runtime_events=[AgentRuntimeEventResponse.model_validate(e) for e in events],
    )

async def list_runtime_events(self, agent_id: str, limit: int = 20) -> list[AgentRuntimeEventResponse]:
    events = await self._runtime_repo.list_events(agent_id, limit=limit)
    return [AgentRuntimeEventResponse.model_validate(e) for e in events]
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agent_ops_service.py
git commit -m "feat(service): add pause_route/resume_route, deprecated agent cleanup, audit events, detail endpoint

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: API 端点新增

**Files:**
- MODIFY: `backend/app/api/v1/agent_ops.py`

- [ ] **Step 1: 新增 pause-route 和 resume-route 端点**

```python
@router.post("/runtime/agents/{runtime_key}/pause-route", response_model=AgentRuntimeInstanceResponse)
async def pause_agent_route(
    runtime_key: str,
    body: PauseRouteRequest,
    org_id: str = Depends(require_org_scope),
    actor_id: str = Depends(require_actor_id),
    session: AsyncSession = Depends(get_session),
):
    """暂停 Agent 路由 — 该 Agent 不再接收新请求"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.pause_route(runtime_key, body.reason)


@router.post("/runtime/agents/{runtime_key}/resume-route", response_model=AgentRuntimeInstanceResponse)
async def resume_agent_route(
    runtime_key: str,
    org_id: str = Depends(require_org_scope),
    actor_id: str = Depends(require_actor_id),
    session: AsyncSession = Depends(get_session),
):
    """恢复 Agent 路由 — 该 Agent 重新接收请求"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.resume_route(runtime_key)
```

- [ ] **Step 2: 新增 Agent 详情端点**

```python
@router.get("/agents/{agent_id}/detail", response_model=AgentDetailResponse)
async def get_agent_detail(
    agent_id: str,
    org_id: str = Depends(require_org_scope),
    actor_id: str = Depends(require_actor_id),
    session: AsyncSession = Depends(get_session),
):
    """获取 Agent 完整详情（含绑定资源、操作记录）"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.get_agent_detail(agent_id)
```

- [ ] **Step 3: 新增运行态事件查询端点**

```python
@router.get("/runtime/events", response_model=list[AgentRuntimeEventResponse])
async def list_runtime_events(
    agent_id: str = Query(..., description="Agent ID"),
    limit: int = Query(default=20, ge=1, le=100),
    org_id: str = Depends(require_org_scope),
    actor_id: str = Depends(require_actor_id),
    session: AsyncSession = Depends(get_session),
):
    """查询 Agent 运行态操作事件日志"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.list_runtime_events(agent_id, limit=limit)
```

- [ ] **Step 4: 增强拓扑端点支持 mode 参数**

```python
@router.get("/agents/topology", response_model=AgentTopologyResponse)
async def get_agents_topology(
    subgraph_key: str = Query(default="all"),
    mode: str = Query(default="design", description="design / runtime"),
    include_planned: bool = Query(default=True),
    include_legacy: bool = Query(default=False),
    org_id: str = Depends(require_org_scope),
    actor_id: str = Depends(require_actor_id),
    session: AsyncSession = Depends(get_session),
):
    """获取 Agent 拓扑 — 支持 design(设计拓扑) / runtime(运行拓扑) 两种模式"""
    service = AgentOpsService(session, org_id, actor_id)
    topology = await service.get_agents_topology(subgraph_key=subgraph_key)
    if mode == "runtime":
        # 过滤：只保留 route_enabled 且 runtime_status=running 的节点
        runtime_agents = await service.list_runtime_agents()
        active_subgraph_keys = {
            ra.subgraph_key for ra in runtime_agents
            if ra.route_enabled and ra.runtime_status == "running"
        }
        topology.nodes = [n for n in topology.nodes if n.get("subgraph_key", n["id"]) in active_subgraph_keys or n["kind"] == "root"]
    return topology
```

- [ ] **Step 5: 确保导入新 Schema**

在文件头部导入新增的 Schema 类：
```python
from app.schemas.agent_ops import (
    # ... existing imports
    AgentDetailResponse,
    AgentRuntimeEventResponse,
    PauseRouteRequest,
)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/agent_ops.py
git commit -m "feat(api): add pause-route/resume-route, agent detail, runtime events, topology mode endpoints

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 10: 后端验证 — 运行测试

**Files:** (test existing)

- [ ] **Step 1: 运行现有 agent 相关测试**

```bash
cd backend && python -m pytest tests/test_quality_agent_routing.py -v --tb=short
```

Expected: 现有路由测试仍通过

- [ ] **Step 2: 验证 API 可启动**

```bash
cd backend && timeout 10 python -c "from app.main import app; print('OK')" 2>&1 || true
```

Expected: 无 import 错误

---

### Task 11: 前端类型定义更新

> **使用技能:** `impeccable` (frontend-design)

**Files:**
- MODIFY: `frontend/src/types/agent-ops.types.ts`

- [ ] **Step 1: 新增类型定义**

在文件顶部添加：

```typescript
export type AgentLifecycleStatus =
  | "active"
  | "partial"
  | "planned"
  | "legacy"
  | "deprecated";

export type AgentRuntimeStatus =
  | "running"
  | "stopped"
  | "degraded"
  | "maintenance"
  | "readonly";

export type AgentGroup = "core" | "memory" | "planned" | "legacy";
```

- [ ] **Step 2: 扩展 AgentDefinition 接口**

在现有 `AgentDefinition` 接口中添加：

```typescript
export interface AgentDefinition {
  // ... 现有字段保持
  lifecycle_status: AgentLifecycleStatus;
  group_key: AgentGroup;
  route_enabled: boolean;
  supports_route_toggle: boolean;
  customer_visible_description?: string;
}
```

- [ ] **Step 3: 扩展 AgentRuntimeInstance 接口**

```typescript
export interface AgentRuntimeInstance {
  // ... 现有字段保持
  runtime_status: AgentRuntimeStatus;
  lifecycle_status?: AgentLifecycleStatus;
  group_key?: AgentGroup;
  route_enabled: boolean;
  supports_route_toggle: boolean;
  customer_visible_description?: string;
  last_error_message?: string;
  maintenance_reason?: string;
}
```

- [ ] **Step 4: 新增类型**

```typescript
export interface AgentRuntimeEvent {
  id: string;
  agent_id: string;
  runtime_key: string;
  event_type: "pause_route" | "resume_route" | "start" | "stop" | "maintenance";
  before_status?: string;
  after_status?: string;
  reason?: string;
  operator_id?: string;
  created_at: string;
}

export interface AgentDetail extends AgentDefinition {
  bound_prompt_version?: PromptVersion;
  bound_routes: IntentRoute[];
  runtime_events: AgentRuntimeEvent[];
}

export interface PauseRouteRequest {
  reason: string;
}

export interface AgentRuntimeOverview {
  // ... 现有字段保持
  success_rate: number;
  recent_errors: number;
}
```

- [ ] **Step 5: 扩展 TopologyNode 接口**

```typescript
export interface TopologyNode {
  id: string;
  label: string;
  kind: string;
  // 新增
  status?: AgentRuntimeStatus;
  lifecycle_status?: AgentLifecycleStatus;
  execution_count?: number;
  avg_latency_ms?: number;
  error_rate?: number;
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/agent-ops.types.ts
git commit -m "feat(frontend-types): add lifecycle, group, route, runtime events, detail types

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 12: 前端 API 和 Store 更新

> **使用技能:** `impeccable` (frontend-design)

**Files:**
- MODIFY: `frontend/src/api/agent-ops.api.ts`
- MODIFY: `frontend/src/stores/agent-ops.store.ts`

- [ ] **Step 1: agent-ops.api.ts — 新增 API 调用**

```typescript
// 暂停路由
pauseAgentRoute: (runtimeKey: string, data: PauseRouteRequest) =>
  http.post<AgentRuntimeInstance>(`/v1/agent-ops/runtime/agents/${runtimeKey}/pause-route`, data),

// 恢复路由
resumeAgentRoute: (runtimeKey: string) =>
  http.post<AgentRuntimeInstance>(`/v1/agent-ops/runtime/agents/${runtimeKey}/resume-route`),

// Agent 详情
getAgentDetail: (agentId: string) =>
  http.get<AgentDetail>(`/v1/agent-ops/agents/${agentId}/detail`),

// 运行态事件
getRuntimeEvents: (agentId: string, limit?: number) =>
  http.get<AgentRuntimeEvent[]>(`/v1/agent-ops/runtime/events`, { params: { agent_id: agentId, limit } }),
```

- [ ] **Step 2: agent-ops.store.ts — 新增 state 和 actions**

```typescript
// state 新增
const agentDetail = ref<AgentDetail | null>(null);
const runtimeEvents = ref<AgentRuntimeEvent[]>([]);

// actions 新增
async function pauseRoute(runtimeKey: string, reason: string) {
  await agentOpsApi.pauseAgentRoute(runtimeKey, { reason });
}

async function resumeRoute(runtimeKey: string) {
  await agentOpsApi.resumeAgentRoute(runtimeKey);
}

async function fetchAgentDetail(agentId: string) {
  agentDetail.value = await agentOpsApi.getAgentDetail(agentId);
}

async function fetchRuntimeEvents(agentId: string, limit = 20) {
  runtimeEvents.value = await agentOpsApi.getRuntimeEvents(agentId, limit);
}

// return 中新增
return {
  // ... existing
  agentDetail,
  runtimeEvents,
  pauseRoute,
  resumeRoute,
  fetchAgentDetail,
  fetchRuntimeEvents,
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/agent-ops.api.ts frontend/src/stores/agent-ops.store.ts
git commit -m "feat(frontend-store): add pauseRoute/resumeRoute, agent detail, runtime events to store and API

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 13: 前端路由和菜单收敛

> **使用技能:** `impeccable` (frontend-design)

**Files:**
- MODIFY: `frontend/src/router/routes/ops.routes.ts`
- MODIFY: `frontend/src/composables/useMenu.ts`

- [ ] **Step 1: ops.routes.ts — 删除占位路由**

删除以下路由：
```typescript
// 删除
{ path: "agents/topology", ... },    // Placeholder topology
{ path: "workflows", ... },           // Placeholder workflows
{ path: "tools", ... },               // Placeholder tools
{ path: "releases", ... },            // Placeholder releases
```

确保保留：
```typescript
{ path: "agents", name: "ops-agents", component: () => import("@/views/ops/AgentManageView.vue"), meta: { title: "Agent 管理", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR] } },
{ path: "agents/intent-routes", name: "ops-agents-intent-routes", component: () => import("@/views/ops/IntentRouteView.vue"), meta: { title: "路由策略", roles: [ROLE_APP_DEVELOPER] } },
```

- [ ] **Step 2: useMenu.ts — 移除占位菜单项**

对于 APP_DEVELOPER 角色，移除：
```typescript
// 删除
{ title: "Agent 拓扑图", path: "/ops/agents/topology", placeholder: true },
```

对于 ADMIN/APP_DEVELOPER 角色，删除：
```typescript
// 删除
{ title: "流程节点", ... },
{ title: "工具注册", ... },
{ title: "发布管理", ... },
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router/routes/ops.routes.ts frontend/src/composables/useMenu.ts
git commit -m "feat(frontend-menu): remove placeholder routes — consolidate to single Agent Management entry

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 14: 前端 AgentManageView.vue 大改

> **使用技能:** `impeccable` (frontend-design) — UI 设计和实现

**Files:**
- MODIFY: `frontend/src/views/ops/AgentManageView.vue`

此任务包含 4 个子任务：定义Tab改造、运行态Tab改造、拓扑Tab改造、详情抽屉。

- [ ] **Step 1: 定义 Tab — 顶部概览卡片**

在 "定义" tab-pane 内、筛选卡片前添加：

```vue
<!-- 顶部概览卡片 -->
<div class="flex gap-4 mb-4">
  <div class="flex-1" v-for="card in definitionCards" :key="card.label">
    <el-card shadow="never" class="stat-card">
      <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
      <div class="stat-label">{{ card.label }}</div>
    </el-card>
  </div>
</div>
```

computed:
```typescript
const definitionCards = computed(() => {
  const agents = store.agents;
  return [
    { label: "核心 Agent", value: agents.filter(a => a.group_key === "core").length, color: "#16a34a" },
    { label: "规划中 Agent", value: agents.filter(a => a.group_key === "planned").length, color: "#d97706" },
    { label: "历史 Agent", value: agents.filter(a => a.group_key === "legacy" || a.lifecycle_status === "deprecated").length, color: "#9ca3af" },
    { label: "可控制 Agent", value: agents.filter(a => a.supports_route_toggle).length, color: "#2563eb" },
    { label: "异常 Agent", value: agents.filter(a => a.runtime_status === "degraded").length, color: "#dc2626" },
  ];
});
```

- [ ] **Step 2: 定义 Tab — 表格字段升级**

升级 el-table 列定义：

```vue
<el-table :data="store.agents" v-loading="loading" stripe @row-click="openDetailDrawer">
  <el-table-column prop="name" label="名称" min-width="160" />
  <el-table-column label="类型" width="100">
    <template #default="{ row }">
      <el-tag :type="groupTagType(row.group_key)" size="small">
        {{ groupLabel(row.group_key) }}
      </el-tag>
    </template>
  </el-table-column>
  <el-table-column prop="customer_visible_description" label="能力说明" min-width="240" show-overflow-tooltip />
  <el-table-column label="接入状态" width="100">
    <template #default="{ row }">
      <el-tag :type="lifecycleTagType(row.lifecycle_status)" size="small">
        {{ lifecycleLabel(row.lifecycle_status) }}
      </el-tag>
    </template>
  </el-table-column>
  <el-table-column label="参与路由" width="90">
    <template #default="{ row }">
      <el-tag :type="row.route_enabled ? 'success' : 'info'" size="small">
        {{ row.route_enabled ? '是' : '否' }}
      </el-tag>
    </template>
  </el-table-column>
  <el-table-column label="运行态" width="100">
    <template #default="{ row }">
      <el-tag :type="runtimeStatusTagType(row.runtime_status)" size="small">
        {{ row.runtime_status || 'unknown' }}
      </el-tag>
    </template>
  </el-table-column>
  <el-table-column label="指标" min-width="180">
    <template #default="{ row }">
      <div class="metric-line">执行 {{ row.metrics_summary?.execution_count ?? 0 }} | 成功率 {{ ((row.metrics_summary?.success_rate ?? 0) * 100).toFixed(1) }}%</div>
      <div class="metric-line">平均延迟 {{ row.metrics_summary?.avg_latency_ms ?? 0 }} ms</div>
    </template>
  </el-table-column>
</el-table>
```

Helper functions:
```typescript
function groupTagType(g: AgentGroup) {
  const map: Record<string, string> = { core: "", memory: "warning", planned: "info", legacy: "info" };
  return map[g] || "info";
}
function groupLabel(g: AgentGroup) {
  const map: Record<string, string> = { core: "核心", memory: "记忆治理", planned: "规划中", legacy: "历史" };
  return map[g] || g;
}
function lifecycleTagType(s: AgentLifecycleStatus) {
  const map: Record<string, string> = { active: "success", partial: "warning", planned: "info", legacy: "info", deprecated: "danger" };
  return map[s] || "info";
}
function lifecycleLabel(s: AgentLifecycleStatus) {
  const map: Record<string, string> = { active: "已接入", partial: "部分接入", planned: "规划中", legacy: "历史兼容", deprecated: "已废弃" };
  return map[s] || s;
}
function runtimeStatusTagType(s: AgentRuntimeStatus) {
  const map: Record<string, string> = { running: "success", stopped: "info", degraded: "warning", maintenance: "danger", readonly: "info" };
  return map[s] || "info";
}
```

- [ ] **Step 3: 运行态 Tab — 顶部卡片增强**

```vue
<div class="flex gap-4 mb-4">
  <div class="flex-1" v-for="card in runtimeCards" :key="card.label">
    <el-card shadow="never" class="stat-card">
      <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
      <div class="stat-label">{{ card.label }}</div>
    </el-card>
  </div>
</div>
```

```typescript
const runtimeCards = computed(() => {
  const o = store.runtimeOverview;
  return [
    { label: "运行中", value: o?.running_agents ?? 0, color: "#16a34a" },
    { label: "已暂停", value: (o?.active_agents ?? 0) - (o?.running_agents ?? 0), color: "#d97706" },
    { label: "今日执行", value: o?.completed_today ?? 0, color: "#2563eb" },
    { label: "成功率", value: ((o?.success_rate ?? 0) * 100).toFixed(1) + "%", color: "#059669" },
    { label: "平均延迟", value: (o?.avg_latency_ms ?? 0) + " ms", color: "#7c3aed" },
    { label: "最近错误", value: o?.recent_errors ?? 0, color: o?.recent_errors ? "#dc2626" : "#6b7280" },
  ];
});
```

- [ ] **Step 4: 运行态 Tab — 操作按钮升级**

替换操作列：

```vue
<el-table-column label="操作" width="200" fixed="right">
  <template #default="{ row }">
    <template v-if="row.lifecycle_status === 'planned'">
      <el-tag type="info" size="small">仅展示</el-tag>
    </template>
    <template v-else-if="row.lifecycle_status === 'legacy' || row.lifecycle_status === 'deprecated'">
      <el-tag type="danger" size="small">已废弃</el-tag>
    </template>
    <template v-else>
      <el-button
        v-if="row.supports_route_toggle"
        link
        :type="row.route_enabled ? 'warning' : 'success'"
        @click="handleRouteToggle(row)"
      >
        {{ row.route_enabled ? "暂停路由" : "恢复路由" }}
      </el-button>
      <el-button
        v-if="row.supports_start_stop"
        link
        type="primary"
        @click="handleRuntimeToggle(row)"
      >
        {{ row.runtime_status === "running" ? "停止" : "启动" }}
      </el-button>
    </template>
  </template>
</el-table-column>
```

- [ ] **Step 5: 运行态 Tab — 操作确认弹窗**

```vue
<el-dialog v-model="pauseDialog.visible" title="确认暂停路由" width="520px">
  <div class="pause-dialog-content">
    <p>你正在暂停 <strong>{{ pauseDialog.agentName }}</strong>。</p>
    <div class="impact-box">
      <div class="impact-title">影响范围：</div>
      <ul>
        <li>该 Agent 将不再接收新请求。</li>
        <li>已在执行中的请求不会被中断。</li>
        <li>系统可按配置 fallback 到其他 Agent 或返回不可用提示。</li>
      </ul>
    </div>
    <el-input
      v-model="pauseDialog.reason"
      type="textarea"
      :rows="2"
      placeholder="请输入暂停原因（必填）"
    />
  </div>
  <template #footer>
    <el-button @click="pauseDialog.visible = false">取消</el-button>
    <el-button type="warning" :disabled="!pauseDialog.reason.trim()" @click="confirmPauseRoute">
      确认暂停
    </el-button>
  </template>
</el-dialog>
```

- [ ] **Step 6: 拓扑 Tab — 二级切换（设计/运行拓扑）**

```vue
<div class="topology-toolbar">
  <el-radio-group v-model="topologyMode" @change="fetchTopology">
    <el-radio-button value="design">设计拓扑</el-radio-button>
    <el-radio-button value="runtime">运行拓扑</el-radio-button>
  </el-radio-group>
  <el-select v-model="topologySubgraph" style="width: 200px" @change="fetchTopology">
    <!-- subgraph options -->
  </el-select>
  <el-checkbox v-model="showPlannedInTopo" @change="fetchTopology">显示规划中</el-checkbox>
  <el-checkbox v-model="showLegacyInTopo" @change="fetchTopology">显示历史</el-checkbox>
</div>
```

拓扑节点颜色按状态：
```typescript
function topoNodeColor(node: TopologyNode) {
  if (!node.status || node.lifecycle_status === "planned") return "#d1d5db"; // 灰色-规划中
  if (node.lifecycle_status === "legacy" || node.lifecycle_status === "deprecated") return "#f97316"; // 橙色-历史
  if (node.status === "running") return "#16a34a"; // 绿色-运行
  if (node.status === "degraded") return "#eab308"; // 黄色-降级
  if (node.status === "stopped") return "#94a3b8"; // 灰色-停止
  return "#475569";
}
```

- [ ] **Step 7: 详情抽屉组件**

```vue
<el-drawer v-model="detailDrawer.visible" title="Agent 详情" size="560px">
  <template v-if="store.agentDetail">
    <div class="detail-section">
      <h4>基础信息</h4>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="名称">{{ store.agentDetail.name }}</el-descriptions-item>
        <el-descriptions-item label="类型">
          <el-tag :type="groupTagType(store.agentDetail.group_key)" size="small">{{ groupLabel(store.agentDetail.group_key) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="子图 Key">{{ store.agentDetail.subgraph_key }}</el-descriptions-item>
        <el-descriptions-item label="入口图">{{ store.agentDetail.entry_graph }}</el-descriptions-item>
        <el-descriptions-item label="工作流绑定">{{ store.agentDetail.workflow_binding }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ store.agentDetail.graph_version }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="detail-section">
      <h4>能力说明</h4>
      <p>{{ store.agentDetail.customer_visible_description || store.agentDetail.description }}</p>
    </div>

    <div class="detail-section">
      <h4>路由信息</h4>
      <p>参与路由：{{ store.agentDetail.route_enabled ? "是" : "否" }}</p>
      <p>绑定的路由规则：{{ store.agentDetail.bound_routes?.length || 0 }} 条</p>
    </div>

    <div class="detail-section">
      <h4>运行指标</h4>
      <p>执行次数：{{ store.agentDetail.metrics_summary?.execution_count ?? 0 }}</p>
      <p>成功率：{{ ((store.agentDetail.metrics_summary?.success_rate ?? 0) * 100).toFixed(1) }}%</p>
      <p>平均延迟：{{ store.agentDetail.metrics_summary?.avg_latency_ms ?? 0 }} ms</p>
    </div>

    <div class="detail-section">
      <h4>操作记录</h4>
      <el-timeline v-if="store.runtimeEvents.length">
        <el-timeline-item
          v-for="event in store.runtimeEvents.slice(0, 10)"
          :key="event.id"
          :timestamp="new Date(event.created_at).toLocaleString()"
        >
          {{ eventLabel(event.event_type) }}
          <span v-if="event.reason" class="text-zinc-400"> — {{ event.reason }}</span>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无操作记录" :image-size="40" />
    </div>
  </template>
</el-drawer>
```

- [ ] **Step 8: 整合所有 script 逻辑**

确保所有新的 reactive state、computed、functions 都定义在 `<script setup>` 中：
- `topologyMode`, `showPlannedInTopo`, `showLegacyInTopo`
- `pauseDialog`, `detailDrawer` reactive states
- `openDetailDrawer(row)`, `handleRouteToggle(row)`, `confirmPauseRoute()`
- All helper functions

- [ ] **Step 9: 添加样式**

```css
/* 详情抽屉 */
.detail-section { margin-bottom: 20px; }
.detail-section h4 { font-size: 15px; font-weight: 600; margin-bottom: 10px; color: #0f172a; }

/* 暂停确认弹窗 */
.impact-box { background: #fefce8; border: 1px solid #fde68a; border-radius: 8px; padding: 12px; margin: 12px 0; }
.impact-title { font-weight: 600; margin-bottom: 6px; }
.impact-box ul { margin: 0; padding-left: 18px; }
.impact-box li { font-size: 13px; color: #713f12; line-height: 1.7; }

/* 拓扑工具栏 */
.topology-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
```

- [ ] **Step 10: Commit**

```bash
git add frontend/src/views/ops/AgentManageView.vue
git commit -m "feat(frontend-view): overhaul AgentManageView — grouping cards, detail drawer, pause dialog, runtime/design topology

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 15: 最终验证

- [ ] **Step 1: 后端类型检查**

```bash
cd backend && python -c "
from app.models.agent_ops import AgentDefinition, AgentRuntimeInstance, AgentRuntimeEvent, AgentRouteLog
from agent.topology_catalog import REGISTERED_SUBGRAPHS
from agent.router.runtime_guard import AgentRuntimeGuard, RuntimeGuardResult
from app.schemas.agent_ops import AgentDetailResponse, AgentRuntimeEventResponse, PauseRouteRequest
print('All imports OK')
"
```

- [ ] **Step 2: 前端编译检查**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -30
```

Expected: 无类型错误

- [ ] **Step 3: 前端构建验证**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: 构建成功

- [ ] **Step 4: 端到端验证清单**

启动前后端服务后验证：

**定义模块：**
- [ ] Agent 按核心/规划中分组展示
- [ ] 状态标签正确（已接入/规划中）
- [ ] 4个核心Agent 参与路由=是，5个规划Agent 参与路由=否
- [ ] 点击行打开详情抽屉
- [ ] 详情抽屉显示基础信息、能力说明、路由信息、运行指标

**运行态模块：**
- [ ] 顶部卡片显示正确数值
- [ ] 核心Agent 显示暂停路由/恢复路由按钮
- [ ] 规划中Agent 显示"仅展示"
- [ ] 点击暂停路由弹出确认弹窗
- [ ] 确认暂停后，调用 API 验证 route_enabled=false
- [ ] 确认暂停后，AgentManager 真实阻止请求进入

**拓扑模块：**
- [ ] 可切换设计拓扑/运行拓扑
- [ ] 节点颜色按状态区分
- [ ] 可勾选显示/隐藏规划中Agent

- [ ] **Step 5: Commit 最终调整**

```bash
git add -A
git commit -m "chore: final verification adjustments for agent management productization

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 实施顺序总结

```
Task 1  → Alembic 迁移
Task 2  → ORM 模型
Task 3  → topology_catalog
Task 4  → AgentRuntimeGuard (新建)
Task 5  → AgentManager 集成守卫
Task 6  → Schemas
Task 7  → Repositories
Task 8  → Service
Task 9  → API 端点
Task 10 → 后端验证
Task 11 → 前端类型
Task 12 → 前端 API + Store
Task 13 → 前端路由菜单
Task 14 → 前端 AgentManageView 大改
Task 15 → 最终验证
```
