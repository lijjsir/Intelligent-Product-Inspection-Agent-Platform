# PIAP 产品智能检测 Agent 平台 — 文档总览与摘要

> 生成日期：2026-05-09 | 来源：工作区全部 9 份 .docx 设计文档

---

## 文档清单

| 序号 | 文档编号 | 文档名称 | 版本 | 日期 | 定位 |
|------|----------|----------|------|------|------|
| 1 | PIAP-SDD-001 | 软件开发技术规范 | v1.0.0 | 2026-03-16 | 总体架构与工程规范基线 |
| 2 | PIAP-SYS-002 | 系统设计文档（MySQL Edition） | v1.0.0 | 2026-03-16 | MySQL 主存储层详细设计 |
| 3 | PIAP-BAD-003 | 后端工程架构设计 | v1.0.0 | 2026-03-16 | 后端目录结构与模块职责 |
| 4 | PIAP-FED-004 | 前端架构与页面设计 | v1.0.0 | 2026-03-16 | 前端技术栈与组件规范 |
| 5 | PIAP-GOV-005 | 系统治理与质量监管 | — | — | 治理层设计（被 DEV-007 吸收） |
| 6 | PIAP-CHG-006 | 变更集 v1.0→v1.1 | v1.0.0 | 2026-03-23 | 治理层接入的增量变更 |
| 7 | PIAP-DEV-007 | 统一开发文档 | v1.1.0 | 2026-03-23 | **v1.1 主实施基线**（整合上述 6 份） |
| 8 | PIAP-INT-008 | 三端协作接口说明 | v1.0.0 | 2026-03-23 | A/B/C 三人并行开发协作规范 |
| 9 | PIAP-QS-009 | 产品检测与判定标准说明书 | v1.0.0 | 2026-03-24 | 检测标准体系与 AI 门禁 |
| 10 | — | 研究生综述报告 | — | 2026-04-24 | LLM 多智能体共享记忆溯源与回滚 |

---

## 1. PIAP-SDD-001 — 软件开发技术规范

### 核心内容

定义平台总体架构与工程规范，是 v1.0 的原始基线。

**五层架构：**
- L5 呈现层：Vue 3 SPA / Dashboard / 告警通知
- L4 API 网关层：FastAPI + JWT + 限流 + 路由
- L3 业务编排层：LangGraph Agent + 工具注册中心 + Session 管理
- L2 能力服务层：LLM/VLM 推理 + RAG + 稳定性分析器
- L1 数据基础层：PostgreSQL（原设计）/ Milvus / MinIO / Redis

**6 种角色（v1.0）：** super_admin / org_admin / inspector / analyst / api_service / auditor

**权限模型：** RBAC + ABAC，8 资源 × 6 角色权限矩阵

**稳定性分析：** 五维度评分模型（证据充分性 30%、输出一致性 25%、模型置信度 20%、溯源完整性 15%、异常模式检测 10%），四级风险（GREEN/YELLOW/ORANGE/RED）

**幻觉分类（v1.0 已有 4 类）：** 事实性、溯源性、一致性、过度泛化

**核心 API 接口：** 16 个端点，覆盖认证/用户/任务/结论/稳定性/预警/工具/统计/审计

**技术选型：** Python/FastAPI、LangGraph、ChromaDB→Milvus、PostgreSQL（后被 DEV-007 统一为 MySQL）、Redis Streams、MinIO/S3、Vue 3 + Vite + Pinia

**里程碑：** Phase 0-5，共 16 周（基础设施→权限→工具→编排→稳定性→上线）

---

## 2. PIAP-SYS-002 — 系统设计文档（MySQL Edition）

### 核心内容

将主存储从 PostgreSQL 迁至 MySQL 8.0+ 的完整设计。

**MySQL 选型理由：** 团队运维成熟、8.0+ 企业级特性（窗口函数/CTE/角色体系）、与现有 ERP/MES 一致

**关键约定：**
- 主键：BINARY(16) 存储 UUIDv7（时序可排序）
- 时间字段：DATETIME(3) UTC（禁用 TIMESTAMP 防 2038 问题）
- 软删除：全表 deleted_at DATETIME(3) NULL
- 租户隔离：所有业务表含 org_id BINARY(16)，Service 层统一注入
- 枚举：禁用 MySQL ENUM，用 VARCHAR(32) + 应用层约束
- JSON 列：配合生成列建立函数索引
- 读写分离：写走主库，读默认走从库，主从延迟 >500ms 回退主库

**三个数据库：**
- piap_main：核心业务（用户/任务/结论/工具）
- piap_audit：审计日志（独立库，仅追加写，禁 UPDATE/DELETE）
- piap_analytics：分析聚合（ETL 写入，只读查询）

**核心业务表 9 张：** organizations / users / inspection_tasks / inspection_results / stability_reports / alert_events / tool_registry / tool_executions / audit_logs

**高可用：** 1 主 2 从 + HAProxy + Keepalived + Orchestrator 自动选主，半同步复制

**备份策略：** XtraBackup 全量（每日）+ 增量（每 6h）+ mysqldump 逻辑备份（每周）+ Binlog 实时归档

**恢复目标：** 主库故障 RTO < 3min / RPO < 1s，整体机房 RTO < 4h / RPO < 5min

**容量规划：** tool_executions 日增 8 万行（按月分区，90 天归档），audit_logs 日增 5 万行

**安全加固：** 最小权限账号体系、AES-256-GCM 敏感字段加密、TLS 1.2+ 传输加密、InnoDB 表空间加密

**Alembic 迁移规范：** 版本化 DDL，生产大表用 pt-online-schema-change 或 gh-ost

---

## 3. PIAP-BAD-003 — 后端工程架构设计

### 核心内容

完整目录结构与模块职责，遵循 DDD 分层。

**六大顶层目录：**
- `app/`：API 路由、Schema、Service、Repository、ORM 模型、core 横切
- `agent/`：LangGraph 图定义、工具注册/执行、LLM 接入、RAG、稳定性分析
- `infra/`：MySQL（读写分离）、Redis、MinIO、Milvus、通知渠道
- `worker/`：Celery 后台任务、Outbox 消费、告警分发
- `tests/`：单元/集成/E2E/AI 质量评估
- `scripts/` & `ops/`：运维工具、Docker、K8s 清单、监控配置

**依赖规则：** app/api → app/services → app/repositories → app/models；禁止 models/ → services/、infra/ → app/、agent/ → app/api/

**关键模块职责表（16 张）：**
- 路由层：9 个端点文件（auth/users/tasks/results/stability/alerts/tools/analytics + deps + router）
- Core 层：config / security / permissions / exceptions / error_handlers / middleware / logging / events
- Domain 层：7 个领域实体（含状态机与枚举）
- Schemas 层：10 个 Pydantic 请求/响应模型
- Services 层：10 个业务服务（含 TenantAwareService 基类）
- Repositories 层：9 个数据访问（含 BaseRepository 通用 CRUD）
- Models 层：10 个 SQLAlchemy ORM
- Agent 系统：graph/（5 个节点 + state）、tools/（8 个工具 + registry + executor）、llm/（client/prompt_manager/token_counter）、rag/（embedder/retriever/reranker/citation_tracker）、stability/（5 维度评分 + scorer + alert_trigger）
- Infra 层：database/cache/queue/storage/vector_db/notification
- Worker 层：4 个任务 + 2 个 Consumer
- Tests 层：unit/integration/e2e/ai_quality

**快速定位表：** 按功能需求映射到具体文件（共 12 类场景）

---

## 4. PIAP-FED-004 — 前端架构与页面设计

### 核心内容

Vue 3 前端完整架构、路由、组件树与页面级设计规范。

**技术栈：** Vue 3.4+ / Vite 5 / Pinia 2 / Vue Router 4 / Element Plus 2 / Tailwind CSS 3 / Axios / ECharts 5 / SSE / Vitest + Playwright

**完整目录树：**
- `src/router/`：11 个路由模块 + guards
- `src/layouts/`：DefaultLayout / AuthLayout + AppSidebar / AppHeader / AppBreadcrumb / AppNotificationDrawer
- `src/views/`：auth(3) / dashboard(1) / task(3) / result(2) / stability(2) / alert(2) / analytics(1) / tool(2) / user(2) / settings(2) / error(2)
- `src/components/business/`：task(4) / result(4) / stability(4) / alert(3) / analytics(4) / user(3)
- `src/components/common/`：10 个通用组件（PageHeader / SearchBar / FilterPanel / DataTable 等）
- `src/stores/`：9 个 Pinia Store（auth / task / result / stability / alert / analytics / tool / user / ui）
- `src/api/`：9 个 Axios 封装模块 + client.ts 拦截器
- `src/composables/`：10 个组合式函数（useAuth / useSSE / useUpload / usePermission / useECharts 等）
- `src/utils/`：6 个工具库 + `src/types/`：9 个类型文件 + `src/constants/`：4 个常量文件
- `src/assets/`：样式变量 + SVG 图标 + 空状态插图

**路由权限矩阵：** 19 条路由，最低权限从公开→inspector→analyst→org_admin→super_admin

**9 个 Store 职责：** auth（认证）/ task（任务+SSE）/ result / stability / alert（含未读计数）/ analytics / tool / user / ui（侧边栏+主题+通知）

**页面设计规范（15 页详细说明）：** 登录页 / 仪表盘 / 任务列表 / 任务详情（SSE 实时推理链） / 结论详情（缺陷标注+溯源引用+复核） / 稳定性详情（五维雷达图+仪表盘+处置） / 预警中心 / 统计分析（通过率趋势+幻觉率+模型对比） / 用户管理

**组件 Props 约定：** 7 个核心业务组件 Props/Emits 定义（TaskStatusBadge / VerdictBadge / RiskLevelBadge / DefectAnnotator / CitationPanel / RadarChart / TaskProgressTimeline）

**API 集成规范：** Axios 拦截器（Token 注入 + 401 刷新 + 403 提示 + 500 通用错误）、SSE 集成（指数退避重连 + unmounted 自动断开）、图像上传（预签名 URL 直传 MinIO + 进度回调）

**部署：** Nginx:alpine 静态服务 + try_files History 模式 + upstream 代理 + CDN 静态资源 + Sentry 错误上报

---

## 5. PIAP-CHG-006 — 变更集 v1.0→v1.1

### 核心内容

因引入 C.1 Platform Admin 和 C.2 AI Quality 角色而对四份文档（SDD/SYS/BAD/FED）产生的全部增量修改。

**变更统计：** 新增 32 项 / 修改 14 项 / 扩展 8 项

**SDD 变更（12 项）：** 术语表增 4 词、架构层次增 2 行、技术选型增 3 行、角色定义增 2 行、权限矩阵扩为 8×8、新增模型配置与用户反馈权限、幻觉分类增第 5 类"成本幻觉"、评估指标增 2 项、分析维度增第六维"用户反馈"、新增 §6.7 反馈闭环、接口清单增 6 条、K8s 清单增 3 服务、里程碑增 Phase 6

**SYS 变更（8 项）：** 新增 3 张表（model_configs / token_usage_ledger / result_feedbacks）、扩展 Schema 规划、新增 model_configs 索引说明、修改容量规划、扩展账号权限、新增治理层监控指标

**BAD 变更（21 项）：** client.py→client_legacy.py + 新增 gateway.py / model_selector.py / health_checker.py / langfuse_tracer.py + 3 个 ORM + 3 个 Repository + 4 个 Service + 4 个 API 端点 + router.py 修改 + permissions.py 新增 + 2 个 Worker 任务 + 3 个迁移脚本

**FED 变更（16 项）：** 新增 6 个视图（ModelConfig / TokenBilling / GpuMonitor / QualityTracing / QualityReport / FeedbackList）+ FeedbackWidget + 4 个 Store + 4 个 API 封装 + governance.types.ts + 路由扩展 + AppSidebar 治理菜单 + roles 常量

---

## 6. PIAP-DEV-007 — 统一开发文档（v1.1 主基线）

### 核心内容

整合 SDD-001 / SYS-002 / BAD-003 / FED-004 / GOV-005 / CHG-006 六份文档，形成 v1.1 唯一实施基线。**若本文件与历史文档冲突，以本文件为准。**

**12 项统一决策（U-01 ~ U-12）：**
- U-01：主存储统一为 MySQL 8.0.35/8.4 LTS
- U-02：租户隔离用 Service 层注入 + DB 视图
- U-03：主键统一 UUIDv7(BINARY(16)) + DATETIME(3) UTC
- U-04：实时协议统一 SSE（不用 WebSocket）
- U-05：SSE 鉴权禁 Bearer Token 在 URL，改用短期 stream token
- U-06：权限模型统一为 7 控制台角色 + 1 服务主体 api_service
- U-07：platform_admin 只读系统/治理日志，不读完整业务审计
- U-08：ModelGateway 查询修正 (org_id IS NULL OR org_id = ?)
- U-09：token_usage_ledger 必须分区 + 幂等写入
- U-10：治理层升级为控制面（发布审批/灰度/回滚/预算/熔断）
- U-11：Langfuse 生产默认私有化部署
- U-12：物理幻觉纳入领域化分类与门禁

**角色扩展为 8 个：** super_admin / platform_admin / org_admin / inspector / ai_quality / analyst / auditor / api_service（服务主体）

**权限矩阵扩为两表：** 业务资源 8×8 + 治理资源 8×8

**前端路由分区：** 业务域 / 平台治理域(/admin/*) / 质量治理域(/quality/*) / 安全与个人域

**Agent 编排增强：** 5 个 LangGraph 节点（planner→vision→knowledge→reasoning→finalizer），新增 ModelGateway 选路策略与发布单灰度流程（Draft→Review→Approved→Shadow→Canary→Full）

**治理实体新增：** model_configs / token_usage_ledger / result_feedbacks / model_releases / budget_policies / gpu_runtime_snapshots

**三轨质量闭环：** 模型自评（稳定性分析器）+ 人工反馈（FeedbackWidget）+ 过程追踪（Langfuse）

**质量门禁指标：** Accuracy ≥95% / Hallucination ≤2% / Faithfulness ≥0.85 / Answer Relevancy ≥0.80 / 点踩率 ≤5% / P95 延迟 ≤基线+20%

**物理幻觉 7 类：** 尺寸公差 / 单位换算 / 材料属性 / 装配状态 / 标准误引 / 捏造缺陷 / 漏检缺陷

**里程碑扩展到 Phase 7：** Phase 6 治理层接入 + Phase 7 控制面硬化（新增）

**核心接口 17 组：** 认证/用户/任务/结果/稳定性/预警/工具/统计/治理-模型/治理-计费/治理-反馈/治理-质量/治理-追踪/实时/审计

---

## 7. PIAP-INT-008 — 三端协作接口说明

### 核心内容

补充 PIAP-DEV-007 的实施细节，定义 A/B/C 三端并行开发的协作规范。

**三端定义：**
- A 端（用户工作台）：End User 提交检测、查看结果、私有 RAG、反馈
- B 端（运营工作台）：Agent Operator 配置 Agent/Prompt/Workflow、A/B 实验、召回分析
- C 端（治理工作台）：Platform Admin + AI Quality，模型发布/预算/GPU/Trace/质量

**身份三要素拆分：** role（决定工作台入口）+ plan_tier（basic/premium/expert 决定配额）+ capabilities（private_rag/gpu_priority/custom_workflow 等能力开关）

**新增角色 agent_operator：** B 端独立角色，负责 Agent 配置与实验，禁止修改治理控制面

**前端合并方案：** 一个仓库、一个登录入口、三套 workspace shell（app/ops/governance），C 端内含 /admin 与 /quality 两组路由

**后端域划分：** A 域（消费层）/ B 域（应用层）/ C 域（治理层）/ 共享域

**B→C 发布链路：** B 产 Draft → C 审批→灰度→全量/回滚，复用 model_releases 状态机

**共享数据表 ownership：** 
- 共享：organizations / users / user_entitlements
- A 域：rag_spaces / inspection_tasks / inspection_results / result_feedbacks
- B 域：agent_apps / prompt_versions / workflow_versions / intent_configs / ab_experiments
- C 域：model_configs / model_releases / budget_policies / token_usage_ledger

**跨端统一主键链：** request_id → task_id → trace_id → ledger_id，要求 A/B/C 一致实现

**SSE 共享事件：** task.progress / task.complete / release.status_changed / budget.warn / quality.alert / model.degraded / trace.ready

**协作 RACI 建议：** 共享模块三人共管，各端页面各自主责，migration 变更至少两人评审

**联合验收清单（6 项）：** 身份与菜单 / A→C 反馈闭环 / B→C 发布链路 / 同库协作 / 统一主键链 / 治理控制生效

---

## 8. PIAP-QS-009 — 产品检测与判定标准说明书

### 核心内容

定义平台在制造业质检场景的统一检测与判定标准。

**三层标准体系：**
- L1 外部强制标准（国标/行标/客户图纸）— 最高优先级
- L2 企业检测标准包（spec_id + version）— 平台执行直接依据
- L3 AI 交付门禁标准 — 决定自动化结论能否生效

**spec_id 标准主数据模型：** spec_id / version / product_family / applicable_sku / zone_map / required_views / inspection_items / aggregation_rules / ai_gate_rules

**五类检测项：** 外观缺陷 / 尺寸规格 / 标识OCR / 装配完整性 / 标准一致性

**四级缺陷模型：** Critical（致命）/ Major（严重）/ Minor（轻微）/ Observe（观察项）

**四类业务判定：** PASS / FAIL / UNCERTAIN / MANUAL_REQUIRED

**AI 交付门禁阈值：** Confidence ≥0.85 / Evidence Coverage =1.00 / Traceability ≥0.90 / Faithfulness ≥0.85 / 物理幻觉率 ≤0.02

**AI 风险等级与交付策略：** GREEN 唯一允许自动放行 / YELLOW 待复核 / ORANGE 必须人工 / RED 拦截升级

**核心原则：** 无正式标准不自动 PASS；只有同时满足业务判定 + AI 门禁才能自动交付

**物理幻觉 7 类编码：** physical_hallucination.{dimension, unit, material, assembly, standard_ref, false_defect, missed_defect}

**推荐数据表 8 张：** inspection_specs / inspection_spec_items / defect_taxonomy / product_zone_maps / spec_aggregation_rules / manual_review_policies / spec_change_logs / inspection_result_evidence

---

## 9. 研究生综述报告 — LLM 多智能体共享记忆溯源与回滚

### 核心内容

谭古古同学的硕士综述报告，研究方向为智能体通信。

**核心问题：** 共享记忆污染——低可信信息进入共享状态后，经检索、规划、工具调用和智能体转述持续扩散的系统级可靠性失效。

**核心观点：** 共享记忆不是普通缓存，而是多智能体可靠协作的状态基础设施；治理重点应从检测转向来源追踪、影响范围估计、局部回滚与恢复验证。

**四大研究问题：**
1. 污染入口与长期化机制
2. 来源链构建（消息→证据→工具调用→内部通道事件的可查询链路）
3. 局部回滚（不简单清空上下文或退回系统快照）
4. 恢复验证（降低污染残留 + 不破坏协作能力）

**第二章 理论基础（5 条线索）：**
- 黑板系统→SharedPlans→KQML/FIPA：共享状态需回答"谁写入、为何写入、影响了谁、如何恢复"
- LLM Agent 记忆（Generative Agents/MemGPT/A-MEM/H-MEM）：记忆从个体能力→团队状态载体
- RAG 污染（PoisonedRAG/Corpus Poisoning/LogicPoison）：污染沿检索→排序→摘要→再利用潜伏变形
- 溯源与版本控制（PROV-DM/Provenance Semirings/OrpheusDB/noWorkflow）：来源字段+版本父节点+依赖边+恢复轨迹
- 治理六属性：来源可识别、过程可复现、影响可估计、版本可比较、权限可约束、恢复可验证

**第三章 主体内容（4 节）：**
- 3.1 污染形成与长期潜伏：五类污染（内容/来源/权限/版本/传播），生命周期（进入→写入→跨Agent传播→长期固化→恢复触发）
- 3.2 来源链与状态日志：记忆条目结构化建模（内容/来源/权限/依赖/恢复五类字段），事件采集五步骤
- 3.3 局部回滚策略：六种回滚方式（删除/降权/隔离/补丁/分支/权限感知），事务化回滚，语义一致性修复
- 3.4 内部扩散防护与恢复验证：写入前门控+回滚闭环，评测五维度（安全性/可用性/协作一致性/审计解释/系统开销）

**第四章 不足与展望：**
- 版本化恢复缺少污染语义（AgentGit/Git Context Controller/StatePlane）
- 错误传播分析缺少回滚边界（From Spark to Fire）
- 执行溯源缺少恢复能力（Agent-Sentry/CodeTracer/TraceSafe）
- 事务化回滚对共享记忆修复不足（Atomix/ACRFence）
- 下一步：轻量级溯源图→传播子图→权限感知局部回滚→恢复后协作一致性评测

**参考文献：** 59 篇（涵盖黑板系统、记忆机制、RAG 安全、数据溯源、版本控制、提示注入、Agent 安全等方向）

---

## 文档关系图

```
PIAP-SDD-001 (v1.0 基线) ─┐
PIAP-SYS-002 (MySQL设计)  │
PIAP-BAD-003 (后端架构)   ├── 被吸收 ──→ PIAP-DEV-007 (v1.1 统一开发文档)
PIAP-FED-004 (前端架构)   │                   │
PIAP-GOV-005 (治理设计)   │                   │
PIAP-CHG-006 (变更集)    ─┘                   │
                                               ├── PIAP-INT-008 (三端协作规范)
                                               └── PIAP-QS-009 (检测判定标准)
```

**效力说明：** PIAP-DEV-007 为 v1.1 主实施基线，若与历史文档冲突以它为准。PIAP-INT-008 为其补充实施件。PIAP-QS-009 为检测标准领域的独立规范。

**研究生报告** 为独立学术工作，研究方向与本平台共享记忆 / Agent 可靠性治理有概念交叉。
