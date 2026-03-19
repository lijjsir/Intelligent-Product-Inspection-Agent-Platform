---
name: piap-backend-codegen
description: >
  产品智能检测 Agent 平台后端代码生成技能（Python / FastAPI / LangGraph / MySQL）。
  当用户提出以下任意需求时，务必调用本技能：
  - 为 PIAP 平台生成任意后端代码（API 路由、Service、Repository、ORM 模型、Agent 节点、工具、稳定性分析器）
  - 生成 FastAPI 端点、Pydantic Schema、SQLAlchemy 模型
  - 编写 LangGraph 图节点、工具注册、Agent 编排逻辑
  - 实现 RAG 检索、LLM 调用、稳定性五维度评分
  - 生成 MySQL 迁移脚本（Alembic）、数据库查询
  - 编写 Celery 异步任务、Redis 操作、MinIO 存储代码
  - 任何涉及 piap-backend/ 目录下文件的新增或修改
---

# PIAP 后端代码生成技能

本技能指导 Claude 按照 PIAP 平台架构规范生成高质量、可直接集成的后端代码。
生成前须先理解请求涉及哪个架构层，再按对应模板输出。

---

## 一、架构层速查

```
用户请求 → 判断目标层 → 选择对应模板 → 生成代码
```

| 关键词 | 目标层 | 输出文件位置 |
|--------|--------|-------------|
| 端点 / 路由 / API | api/ 路由层 | app/api/v1/{resource}.py |
| 业务逻辑 / 用例 / Service | 业务服务层 | app/services/{resource}_service.py |
| 查询 / 数据库 / Repository | 数据访问层 | app/repositories/{resource}_repo.py |
| 表 / ORM / Model | ORM 模型层 | app/models/{resource}.py |
| Schema / 请求体 / 响应体 | Schema 层 | app/schemas/{resource}.py |
| 节点 / 图 / Agent / LangGraph | Agent 编排层 | agent/graph/nodes/{node}.py |
| 工具 / Tool | 工具层 | agent/tools/{tool_name}.py |
| 稳定性 / 风险 / 评分 | 稳定性分析层 | agent/stability/dimensions/{dim}.py |
| 迁移 / DDL / 建表 | 数据库迁移 | migrations/versions/{id}_{desc}.py |
| 异步任务 / Celery / Worker | 任务层 | worker/tasks/{task}.py |

---

## 二、各层代码模板

### 2.1 API 路由层模板

```python
# app/api/v1/{resource}.py
from fastapi import APIRouter, Depends, Query, Path
from app.api.deps import get_current_user, get_db, require_role
from app.schemas.{resource} import {Resource}Create, {Resource}Response, {Resource}ListQuery
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.services.{resource}_service import {Resource}Service
from app.domain.user import Role

router = APIRouter(prefix="/{resources}", tags=["{Resource}"])


@router.get("", response_model=ResponseEnvelope[PagedResponse[{Resource}Response]])
async def list_{resources}(
    query: {Resource}ListQuery = Depends(),
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    svc = {Resource}Service(db, current_user.org_id)
    data, total = await svc.list(query)
    return ResponseEnvelope.ok(PagedResponse(items=data, total=total, **query.page_meta))


@router.post("", response_model=ResponseEnvelope[{Resource}Response], status_code=201)
async def create_{resource}(
    body: {Resource}Create,
    current_user=Depends(require_role(Role.INSPECTOR)),
    db=Depends(get_db),
):
    svc = {Resource}Service(db, current_user.org_id)
    result = await svc.create(body, actor_id=current_user.id)
    return ResponseEnvelope.ok(result)


@router.get("/{id}", response_model=ResponseEnvelope[{Resource}Response])
async def get_{resource}(
    id: str = Path(...),
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    svc = {Resource}Service(db, current_user.org_id)
    return ResponseEnvelope.ok(await svc.get(id))
```

**路由层规则：**
- 不写任何业务逻辑，只做参数解析 → 调用 Service → 包装响应
- 权限守卫用 `require_role(Role.XXX)` 装饰器，不在路由函数内判断
- 响应统一用 `ResponseEnvelope.ok(data)` 包装
- 路由文件生成后须在 `app/api/v1/router.py` 中注册：`router.include_router({resource}.router)`

---

### 2.2 业务服务层模板

```python
# app/services/{resource}_service.py
from app.services.base import TenantAwareService
from app.repositories.{resource}_repo import {Resource}Repository
from app.schemas.{resource} import {Resource}Create, {Resource}Response
from app.core.exceptions import NotFoundError, ConflictError
from app.services.audit_service import AuditService


class {Resource}Service(TenantAwareService):

    def __init__(self, db, org_id: bytes):
        super().__init__(db, org_id)
        self._repo = {Resource}Repository(db, org_id)

    async def list(self, query) -> tuple[list, int]:
        return await self._repo.list_paged(
            filters=query.to_filters(),
            page=query.page,
            size=query.page_size,
        )

    async def get(self, id: str):
        obj = await self._repo.get_by_id(id)
        if not obj:
            raise NotFoundError(f"{Resource} {id} not found")
        return {Resource}Response.model_validate(obj)

    async def create(self, body: {Resource}Create, actor_id: bytes):
        async with self._db.begin():
            obj = await self._repo.create(body.model_dump(), org_id=self._org_id)
            await AuditService(self._db).log(
                actor_id=actor_id,
                resource_type="{resource}",
                resource_id=obj.id,
                action="create",
            )
        # 事务提交后触发异步任务（如需要）
        return {Resource}Response.model_validate(obj)
```

**Service 层规则：**
- 必须继承 `TenantAwareService`，构造时绑定 `org_id`
- 所有写操作用 `async with self._db.begin():` 包裹事务
- 写操作事务内同时写 `audit_outbox`（通过 `AuditService`）
- 事务提交后再触发队列/通知，不在事务内推送
- 抛出 `NotFoundError` / `ConflictError` 等领域异常，不直接抛 HTTPException

---

### 2.3 数据访问层模板

```python
# app/repositories/{resource}_repo.py
from sqlalchemy import select, func, and_
from app.repositories.base import BaseRepository
from app.models.{resource} import {Resource}


class {Resource}Repository(BaseRepository[{Resource}]):

    model = {Resource}

    async def list_by_status(
        self, status: str, page: int = 1, size: int = 20
    ) -> tuple[list[{Resource}], int]:
        """按状态分页查询，利用 idx_org_status_created 联合索引"""
        base = self._base_query().filter({Resource}.status == status)
        total = await self._db.scalar(select(func.count()).select_from(base.subquery()))
        items = (
            await self._db.execute(
                base.order_by({Resource}.priority.desc(), {Resource}.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).scalars().all()
        return items, total
```

**Repository 层规则：**
- 每个查询方法注释说明命中的索引名（便于 DBA 审查）
- 不写业务判断，只做数据读写
- `_base_query()` 已自动注入 `org_id` 和 `deleted_at IS NULL` 过滤，不要重复添加
- 复杂聚合（窗口函数、CTE）写在 `analytics_repo.py`，不散落在业务 Repository

---

### 2.4 ORM 模型层模板

```python
# app/models/{resource}.py
from sqlalchemy import Column, String, DateTime, JSON, BINARY, TINYINT, text
from sqlalchemy.orm import relationship
from app.models.base import Base, TenantMixin, TimestampMixin, SoftDeleteMixin
from app.infra.database.engine import generate_uuid_v7


class {Resource}(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    """
    {resource} 表
    索引：
      - PRIMARY KEY (id)
      - idx_org_status_created (org_id, status, created_at DESC)
    """
    __tablename__ = "{resources}"

    id         = Column(BINARY(16), primary_key=True, default=generate_uuid_v7)
    # org_id 来自 TenantMixin
    status     = Column(String(32),  nullable=False, default="pending")
    metadata_  = Column("metadata", JSON, nullable=True)

    # 关联关系
    # children = relationship("ChildModel", back_populates="parent", lazy="select")
```

**ORM 规则：**
- 继承 `TenantMixin`（org_id）、`TimestampMixin`（created_at/updated_at）、`SoftDeleteMixin`（deleted_at）三个 Mixin
- 主键统一 `BINARY(16)` + `generate_uuid_v7()`
- JSON 列命名冲突时用 `Column("metadata", JSON)` 映射
- 类 docstring 注释关联索引名
- 枚举字段用 `String(32)`，不用 `Enum` 类型

---

### 2.5 Pydantic Schema 模板

```python
# app/schemas/{resource}.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from app.schemas.common import UUIDStr, PageParams


class {Resource}Base(BaseModel):
    """公共字段，Create 和 Response 共同继承"""
    product_id: str = Field(..., max_length=64, description="产品编号")
    spec_id:    str = Field(..., max_length=64, description="检测标准 ID")


class {Resource}Create({Resource}Base):
    image_urls: list[str] = Field(..., min_length=1, max_length=10)
    priority:   int       = Field(default=5, ge=1, le=10)
    metadata:   Optional[dict] = None


class {Resource}Response({Resource}Base):
    id:         UUIDStr
    org_id:     UUIDStr
    status:     str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}  # 支持 ORM 对象直接 validate


class {Resource}ListQuery(PageParams):
    status:     Optional[str] = None
    product_id: Optional[str] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "page_size"}).items() if v is not None}
```

---

### 2.6 LangGraph 节点模板

```python
# agent/graph/nodes/{node_name}.py
from typing import Annotated
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from agent.graph.state import InspectionState
from agent.tools.executor import ToolExecutor


async def {node_name}_node(state: InspectionState) -> dict:
    """
    {节点功能描述}

    输入 state 字段：{读取的字段列表}
    输出 state 更新：{写入的字段列表}
    """
    # 1. 从 state 读取上下文
    task_id   = state["task_id"]
    image_urls = state["image_urls"]

    # 2. 构造工具调用或 LLM 请求
    executor = ToolExecutor(org_id=state["org_id"])
    result = await executor.run(
        tool_name="vision_defect_detect",
        input={"image_url": image_urls[0], "threshold": 0.6},
        task_id=task_id,
    )

    # 3. 返回 state 增量更新（LangGraph 自动 merge）
    return {
        "defects": result.get("defects", []),
        "node_logs": state.get("node_logs", []) + [
            {"node": "{node_name}", "status": "done", "output_summary": f"{len(result.get('defects',[]))} defects found"}
        ],
    }
```

**节点规则：**
- 函数签名固定：`async def {name}_node(state: InspectionState) -> dict`
- 只返回需要更新的字段，不返回完整 state（LangGraph merge 语义）
- 每个节点在 `node_logs` 追加一条执行记录，供前端 SSE 推送
- 节点内不直接操作数据库，通过 state 传递数据，由 `finalizer_node` 统一持久化
- 节点抛出异常时，LangGraph 会路由至 error 边，须在 graph 定义中配置

---

### 2.7 工具实现模板

```python
# agent/tools/{tool_name}.py
from pydantic import BaseModel, Field
from typing import Any


# ── 输入/输出 Schema ──────────────────────────────
class {ToolName}Input(BaseModel):
    image_url: str  = Field(..., description="待检测图像的 URL")
    threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="置信度阈值")


class {ToolName}Output(BaseModel):
    defects: list[dict] = Field(default_factory=list)
    latency_ms: int


# ── Tool Manifest（注册到 ToolRegistry 的元数据）──
TOOL_MANIFEST = {
    "name":        "{tool_name}",          # snake_case，全局唯一
    "display_name": "{工具展示名}",
    "description":  "{详细功能描述，Agent 规划时依据此字段选工具}",
    "parameters":   {ToolName}Input.model_json_schema(),
    "returns":      {ToolName}Output.model_json_schema(),
    "timeout_ms":   30_000,
    "retry_policy": {"max_attempts": 2, "backoff_ms": 500, "jitter": True},
    "access_roles": ["inspector", "org_admin", "super_admin"],
    "rate_limit_rpm": 60,
    "is_readonly":  True,
}


# ── 执行函数（由 ToolExecutor 调用）─────────────────
async def execute(input_data: dict, context: dict) -> dict:
    """
    实际工具执行逻辑。
    context 包含：org_id, task_id, actor_id
    """
    params = {ToolName}Input(**input_data)
    # TODO: 调用实际外部服务
    return {ToolName}Output(defects=[], latency_ms=0).model_dump()
```

---

### 2.8 稳定性维度评分模板

```python
# agent/stability/dimensions/{dimension}.py
from dataclasses import dataclass
from agent.graph.state import InspectionState


@dataclass
class {Dimension}Score:
    raw_score:  float       # [0, 1]
    weight:     float = 0.XX  # 在总分中的权重，与设计文档一致
    evidence:   list[str] = None  # 支撑证据描述
    passed:     bool = True       # 是否达到及格阈值


THRESHOLD = 0.XX   # 维度及格阈值，低于此值即使总分不高也单独触发预警


async def compute(state: InspectionState) -> {Dimension}Score:
    """
    {维度名称}评分计算。

    算法：{简要描述算法逻辑}
    数据来源：state["{来源字段}"]
    触发预警条件：raw_score < THRESHOLD
    """
    # TODO: 实现评分逻辑
    score = 0.0
    evidence = []

    return {Dimension}Score(
        raw_score=score,
        evidence=evidence,
        passed=score >= THRESHOLD,
    )
```

**五维度权重（不可修改）：**
```
evidence      = 0.30   # 证据充分性
consistency   = 0.25   # 输出一致性
confidence    = 0.20   # 模型置信度
traceability  = 0.15   # 溯源完整性
anomaly       = 0.10   # 异常模式检测
```

---

### 2.9 Alembic 迁移脚本模板

```python
# migrations/versions/{timestamp}_{description}.py
"""{描述变更内容}

Revision ID: {自动生成}
Revises: {父版本 ID}
Create Date: {日期}
"""
from alembic import op
import sqlalchemy as sa

revision = "{id}"
down_revision = "{parent_id}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 新建表 ──
    op.create_table(
        "{table_name}",
        sa.Column("id",         sa.BINARY(16),  nullable=False),
        sa.Column("org_id",     sa.BINARY(16),  nullable=False),
        sa.Column("status",     sa.String(32),  nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(3), nullable=False,
                  server_default=sa.text("UTC_TIMESTAMP(3)")),
        sa.Column("updated_at", sa.DateTime(3), nullable=False,
                  server_default=sa.text("UTC_TIMESTAMP(3) ON UPDATE UTC_TIMESTAMP(3)")),
        sa.Column("deleted_at", sa.DateTime(3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="{表注释}",
    )
    op.create_index("idx_org_status_created", "{table_name}",
                    ["org_id", "status", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_org_status_created", "{table_name}")
    op.drop_table("{table_name}")
```

---

## 三、跨层生成规范

### 3.1 新增一个完整资源的标准顺序
生成新资源（如新增 `spec` 规格标准模块）时，**严格按以下顺序**生成，避免依赖缺失：

```
1. app/models/spec.py          （ORM，无依赖）
2. migrations/versions/xxx.py  （建表 DDL）
3. app/domain/spec.py          （领域实体，无 IO 依赖）
4. app/schemas/spec.py         （Pydantic Schema）
5. app/repositories/spec_repo.py
6. app/services/spec_service.py
7. app/api/v1/specs.py         （路由）
8. app/api/v1/router.py        （注册路由，追加一行）
```

### 3.2 UUID 处理规范
```python
# 所有 ID 字段在 API 层用字符串暴露，ORM 层用 BINARY(16) 存储
# 转换统一在 schemas/common.py 的 UUIDStr 类型中处理

from app.utils.uuid import uuid_to_bin, bin_to_uuid

# Service 层：字符串 → bytes（写入 DB）
org_id_bytes = uuid_to_bin(org_id_str)

# Schema 层：bytes → 字符串（返回 API）
# 通过 model_config = {"from_attributes": True} + UUIDStr 类型自动转换
```

### 3.3 错误处理规范
```python
# 领域异常定义在 app/core/exceptions.py
class NotFoundError(Exception): status_code = 404
class ConflictError(Exception): status_code = 409
class ForbiddenError(Exception): status_code = 403

# Service 层抛出领域异常
raise NotFoundError(f"Task {task_id} not found")

# 路由层不 try-catch，由 app/core/error_handlers.py 统一捕获并转换为 ResponseEnvelope
```

### 3.4 类型注解规范
- 所有函数必须有完整参数类型注解和返回值注解
- `bytes` 用于内部 BINARY(16) ID，`str` 用于 API 暴露的 UUID 字符串
- 异步函数统一 `async def`，无 IO 的纯计算函数用同步 `def`

---

## 四、代码质量检查清单

生成代码后自我检查：

- [ ] 是否继承了正确的基类（TenantAwareService / BaseRepository / Base+Mixin）
- [ ] 写操作是否包裹在 `async with db.begin():` 事务中
- [ ] 是否在事务内调用了 `AuditService.log()`
- [ ] ORM 模型是否声明了必要的索引注释
- [ ] API 路由是否注册到了 `router.py`
- [ ] Alembic 脚本是否包含对应的 `downgrade()` 实现
- [ ] 新增工具是否填写了完整的 `TOOL_MANIFEST`
- [ ] LangGraph 节点是否在 `node_logs` 追加了执行记录
- [ ] 稳定性维度权重是否与设计文档一致（总和 = 1.0）
