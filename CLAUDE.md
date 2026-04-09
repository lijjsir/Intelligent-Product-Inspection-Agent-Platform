# PIAP 
## Claude Code 开发指引

## 规则

1. 全部用中文回复
2. 每次回复前用固定称呼开头
3. 不能写兼容性代码，除非我主动要求，可以询问我
4. 写代码前先描述方案，等我批准在执行
5. 需求模糊时，先提问澄清再写代码
6. 写完代码后，列出边缘情况和测试用例
7. 修改超过三个文件，先拆成小任务
8. 出bug时，先写能重现的测试再修复
9. 每次被纠正后，反思并制定不再犯的计划

---

## 技术栈

```
后端：Python 3.12 · FastAPI · SQLAlchemy 2.0（异步）· Alembic · Celery · mysqlclient
数据库：MySQL 8.0 · Redis（缓存 + 队列）
AI 追踪：Langfuse SDK（langfuse>=2.0）
前端：Vue 3 · Vite · Pinia · Element Plus · ECharts · TypeScript · Axios
容器：Docker · Docker Compose
```

## 

---

## 数据库设计（MySQL 8.0）

### 核心约定
- 主键：`BINARY(16)` 存储 UUIDv7，转换用 `UUID_TO_BIN(uuid, 1)`
- 时间：`DATETIME(3)` 存 UTC，禁用 `TIMESTAMP`
- 枚举：`VARCHAR(32)` + 应用层校验，禁用 MySQL ENUM
- 租户隔离：Service 层统一注入 `WHERE org_id = ?`，无 RLS

---

## 编码规范

### 后端

**分层规则（严格遵守，不可跨层）：**
```
api/ → services/ → repositories/ → models/
禁止：api/ 直接操作 ORM；services/ 直接写 SQL
```

**Service 层标准写法：**
```python
# 写操作必须包裹事务，事务内写 audit（如有），事务外推队列
async with self._db.begin():
    obj = await self._repo.create(...)
# 事务提交后再做异步操作
```

**错误处理：**
```python
# Service 层抛领域异常，不抛 HTTPException
raise NotFoundError("ModelConfig not found")
# api/ 层由全局 error_handler 统一转换为 ResponseEnvelope
```

**响应格式（所有接口统一）：**
```json
{ "code": 200, "message": "ok", "data": {...},
  "meta": { "request_id": "...", "page": 1, "total": 100 } }
```

### Langfuse 集成规则

- `LANGFUSE_ENABLED=false` 时零开销，不发任何网络请求
- 用 `@observe` 装饰器注入，不侵入函数核心逻辑
- 用户反馈提交时，MySQL 写入与 Langfuse Score 双写，双写失败不阻断主流程（异步补录）
- `trace_id` 来自 Langfuse，存入 `token_usage_ledger.trace_id` 供关联查询

### 前端

- 组件使用 `<script setup lang="ts">`，Props/Emits 必须有 TypeScript 接口
- 页面只通过 Store Action 获取数据，不直接调用 API
- 异步操作必须有 `loading` 状态，在 `finally` 中重置
- ECharts 实例统一用 `useECharts` composable 管理，不直接 `new ECharts()`
- 颜色值从常量文件引入，不在模板中硬编码

---

## 环境变量（.env）

```bash
# 数据库
DATABASE_URL=mysql+asyncmy://user:pass@localhost:3306/piap_governance
REDIS_URL=redis://localhost:6379/0

# JWT（与主平台共享密钥）
JWT_SECRET_KEY=your-secret
JWT_ALGORITHM=HS256

# Langfuse
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://127.0.0.1:3000
LANGFUSE_PUBLIC_KEY=pk-lf-piap-local
LANGFUSE_SECRET_KEY=sk-lf-piap-local-secret

# 加密（API Key 存储）
ENCRYPTION_KEY=base64-encoded-32-bytes

# 模型网关
MODEL_HEALTH_CHECK_INTERVAL=300
```

---

## 开发优先级

按以下顺序开发，每步完成后验证再继续：

```
Step 1  数据库 Migration（三张表建表脚本）
Step 2  ORM 模型（model_config / token_ledger / feedback）
Step 3  Repository 层（CRUD + 聚合查询）
Step 4  Service 层（含 Langfuse 双写逻辑）
Step 5  API 端点（含权限守卫）
Step 6  前端 Store + API 封装
Step 7  前端页面（ModelConfigView → BillingView → FeedbackWidget → QualityReportView）
```

---

## 常见问题速查

| 问题 | 定位文件 |
|------|---------|
| 权限不对/403 | `app/core/permissions.py` |
| 接口返回格式异常 | `app/schemas/common.py` ResponseEnvelope |
| Langfuse 不上报 | 检查 `LANGFUSE_ENABLED` 和 `infra/langfuse_tracer.py` |
| Token 成本计算错误 | `services/billing_service.py` 的聚合逻辑 |
| 租户数据互串 | `services/base.py` TenantAwareService 的 org_id 注入 |
| 前端图表不更新 | `useECharts` composable 的 watch 依赖 |
| 反馈重复提交 | `uk_actor_result` 唯一约束，捕获 `IntegrityError` 返回 409 |
