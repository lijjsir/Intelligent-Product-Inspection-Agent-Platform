---
name: piap-platform-docs
description: >
  产品智能检测 Agent 平台全栈开发文档生成技能。适用于需要为 AI Agent 系统、LLM 驱动的工业检测/质检平台、多模态智能分析系统编写完整技术文档的场景。覆盖软件开发规范（SDD）、系统设计（MySQL 版）、后端架构设计（Python/FastAPI/LangGraph）、前端架构设计（Vue 3/Pinia）四类文档的结构规范、内容要点与交付标准。

  当用户提出以下任意需求时，务必调用本技能：
  - 为 AI Agent / LLM 应用编写开发文档、技术规范、架构设计
  - 涉及 FastAPI + LangGraph + MySQL + Vue 3 全栈组合的项目文档
  - 需要规范用户权限管理、工具注册中心、稳定性分析、幻觉抑制等 AI 工程模块的文档化
  - 为产品检测、质量管理、工业 AI 系统编写软件设计文档
  - 用户要求生成 .docx 格式的技术文档且涉及多个架构层次
---

# PIAP 全栈 AI Agent 平台文档技能

本技能指导 Claude 为产品智能检测 Agent 平台（及同类 LLM 驱动的工业 AI 系统）生成结构完整、内容专业的技术文档集。

**在开始任何文档生成之前，先阅读 `/mnt/skills/public/docx/SKILL.md`**，以获取 Word 文档创建的底层工具规范。

---

## 一、文档集概览

本平台文档体系由四份相互引用的技术文档构成，编号与依赖关系如下：

```
PIAP-SDD-001  软件开发规范文档（总纲）
    └─ PIAP-SYS-002  系统设计文档（MySQL Edition）
         └─ PIAP-BAD-003  后端架构设计
              └─ PIAP-FED-004  前端架构设计 & 页面设计
```

每份文档均需包含：封面元数据表、页眉、各章节标题层级（H1/H2/H3）、深色代码块、两色交替数据表、页脚版权行。

---

## 二、各文档内容规范

### 2.1 SDD — 软件开发规范文档

**必含章节（12章）：**

| 章节 | 核心内容 |
|------|----------|
| 1. 项目概述 | 背景目标、业务范畴（5条）、术语约定表 |
| 2. 系统总体架构 | L1-L5五层架构表、9步数据流、技术选型对比（11行） |
| 3. 用户权限管理 | 6种角色定义、权限矩阵（8资源×6角色）、JWT+TOTP认证、多租户RLS、审计日志字段（11列） |
| 4. 工具注册与执行 | 8个内置工具目录、Tool Manifest规范、8步执行流程、gVisor沙箱参数 |
| 5. AI精确性与幻觉抑制 | 4类幻觉分类表、4层抑制策略（Prompt/RAG/推理/后处理）、6项评估指标+目标阈值 |
| 6. 稳定性分析与预警 | 5维度加权评分模型（证据/一致性/置信度/溯源/异常）、4级风险分级、单次+批次双预警、根因分析5步流程、6个Dashboard视图 |
| 7. 数据库设计 | ER关系摘要、核心表字段定义 |
| 8. API接口规范 | 16个接口清单、统一响应Envelope |
| 9. 部署方案 | 三环境分层、K8s服务清单（7个服务）、可观测三位一体 |
| 10. 测试策略 | 7层测试矩阵、AI专项测试4步流程 |
| 11. 安全合规 | 传输/静态加密、Prompt注入防护、4框架合规对齐 |
| 12. 附录 | 16周里程碑、术语缩写表 |

**关键设计决策：**
- 幻觉分4类：事实性/溯源性/一致性/过度泛化，危害等级各异
- 稳定性评分权重：证据充分性30%、输出一致性25%、模型置信度20%、溯源完整性15%、异常检测10%
- Risk Score 0-100，GREEN(0-30)自动交付、YELLOW(31-60)附免责标注、ORANGE(61-80)阻断+人工复核、RED(81-100)根因分析

---

### 2.2 SYS — 系统设计文档（MySQL Edition）

**必含章节（12章）：**

| 章节 | 核心内容 |
|------|----------|
| 1. 概述 | MySQL选型说明、版本要求（8.0.28+）、6条关键约定 |
| 2. 系统架构 | MySQL在架构中的职责边界（存什么/不存什么）、读写分离策略 |
| 3. 数据库详细设计 | 3个Database规划、UUID主键BINARY(16)方案、租户隔离实现、9张核心表DDL |
| 4. 索引设计 | 5条设计原则、高频查询执行计划、生成列优化、大表分区策略 |
| 5. ORM层设计 | 连接池6项参数配置、SQLAlchemy ORM模型、Service层租户注入中间件 |
| 6. 事务设计 | 隔离级别选择、任务提交事务、稳定性报告+预警联动事务、跨库一致性(Outbox Pattern) |
| 7. 高可用与备份 | 主从拓扑（1主2从+VIP）、半同步复制配置、4类备份策略、5场景RTO/RPO |
| 8. 性能基准 | 写入/读取QPS目标、18个月容量规划（6张表） |
| 9. 安全加固 | 最小权限账号（5个）、加固配置清单、AES-256-GCM敏感字段加密 |
| 10. 变更管理 | Alembic三阶段流程、Online DDL（pt-osc）、回滚预案 |
| 11. 监控指标 | 10项核心MySQL指标+告警阈值、4项业务层监控 |
| 12. 附录 | ER图、my.cnf关键参数、依赖版本锁定 |

**核心表（9张，务必全部包含DDL）：**
```
organizations / users / inspection_tasks / inspection_results
/ stability_reports / alert_events / tool_registry
/ tool_executions / audit_logs（独立库 piap_audit）
```

**MySQL vs PostgreSQL 关键适配点：**
- 无 RLS → Service层 TenantAwareService 基类统一注入 `WHERE org_id = ?`
- JSONB → JSON列 + 生成列(Generated Column) + 函数索引
- UUID → `BINARY(16)` + `UUID_TO_BIN(uuid, 1)`（时序交换位）
- ENUM → `VARCHAR(32)` + 应用层约束
- TIMESTAMPTZ → `DATETIME(3)` + 应用层统一UTC
- 审计库独立，跨库一致性用 Outbox Pattern 保证

---

### 2.3 BAD — 后端架构设计

**必含章节（5章）：**

| 章节 | 核心内容 |
|------|----------|
| 1. 架构总览 | 技术选型（12项）、6个顶层目录职责表 |
| 2. 完整目录结构 | 深色代码块树形图，约130个文件，每行附灰色注释 |
| 3. 各层职责说明 | 10个目录的文件说明表（文件名+职责两列） |
| 4. 模块依赖关系 | 单向依赖规则表、禁止依赖方向（红色标题行） |
| 5. 关键入口速查 | 按功能需求定位文件（15条速查行） |

**目录结构必须包含的6个顶层模块：**

```
app/         # api/ core/ domain/ schemas/ services/ repositories/ models/
agent/       # graph/ tools/ llm/ rag/ stability/
infra/       # database/ cache/ queue/ storage/ vector_db/ notification/
worker/      # tasks/ consumers/
tests/       # unit/ integration/ e2e/ ai_quality/
migrations/ scripts/ ops/
```

**分层依赖规则（禁止违反）：**
- `api/ → services/ → repositories/ → models/`（单向）
- `agent/` 不依赖 `app/api/`（通过队列异步解耦）
- `infra/` 不依赖任何业务层
- 通用组件（`common/`）不引用任何 Store

**agent/ 子模块必须细化：**
```
graph/nodes/    # planner / vision / knowledge / reasoning / finalizer
tools/          # 8个内置工具 + registry + executor
llm/prompts/    # system_inspector.md / planner.md / reasoning.md / few_shot_examples.md
rag/            # embedder / retriever / reranker / citation_tracker
stability/dimensions/  # evidence / consistency / confidence / traceability / anomaly
```

---

### 2.4 FED — 前端架构设计 & 页面设计

**必含章节（8章）：**

| 章节 | 核心内容 |
|------|----------|
| 1. 技术总览 | 12项技术选型表、11个顶层目录职责 |
| 2. 完整目录结构 | 深色代码块树形图，约130个文件 |
| 3. 路由与权限 | 19条路由表（路径/组件/布局/最低权限/说明）、4条守卫逻辑 |
| 4. 状态管理 | 8个 Pinia Store 职责表（State核心字段+主要Action）、跨Store通信规范 |
| 5. 页面设计规范 | 9个页面的区域/组件/数据来源/交互说明（四列表格） |
| 6. 组件规范 | 8个业务组件Props/Emits表、通用组件6条规范、样式规范 |
| 7. API集成 | Axios拦截器6条、SSE集成4条、图像上传4条 |
| 8. 构建与部署 | Vite配置4条、6项生产部署方案 |

**9个页面必须设计（每页含区域拆解表）：**
```
LoginView          # 品牌左侧60% + 表单右侧40% + SSO入口
DashboardView      # 4个StatCard + 趋势图 + 风险分布 + 待处理预警 + 快捷操作
TaskListView       # 状态Tab + 筛选栏 + 分页表格 + 优先级条形
TaskDetailView     # 基本信息 + 图像轮播 + SSE推理链时间线
ResultDetailView   # 综合结论头 + DefectAnnotator(Canvas) + 溯源引用 + 复核表单
StabilityDetailView # 风险横幅 + 得分仪表盘 + 五维度雷达图 + 采样记录
AlertListView      # 统计条 + 严重级别Tab + 快速ACK
AnalyticsView      # 时间范围选择 + 核心指标卡 + 幻觉率趋势 + 模型对比
UserListView       # 角色筛选 + 用户表 + 行内角色变更
```

**组件颜色规范（必须一致）：**
```
风险等级：GREEN=#16A34A / YELLOW=#D97706 / ORANGE=#EA580C / RED=#DC2626
Verdict： pass=#16A34A / fail=#DC2626 / uncertain=#D97706
任务状态：pending=#9CA3AF / running=#3B82F6 / done=#16A34A / failed=#DC2626
主色调：  navy=#1B3A5C / blue=#2563A8 / teal=#0E7490
```

---

## 三、文档通用排版规范

### 3.1 颜色系统
```javascript
const C = {
  navy:  "1B3A5C",  // H1 标题、封面主标题
  blue:  "2563A8",  // H2 标题、超链接、主按钮
  teal:  "0E7490",  // H3 标题、强调文字
  gray:  "374151",  // 正文
  lgray: "F3F4F6",  // 交替行底色（偶数行）
  mgray: "9CA3AF",  // 次要文字、页脚
  white: "FFFFFF",  // 表头文字
  navy_hdr: "1B3A5C", // 表头背景
  code:  "1E2D3D",  // 代码块背景
  codeText: "C9D1E0", // 代码文字
  codeComment: "5C6B7A", // 代码注释（# 之后）
}
```

### 3.2 代码块规范
- 背景色 `1E2D3D`，代码文字 `C9D1E0`，注释文字 `5C6B7A`
- 使用 `Courier New` 字体，字号 18（约 9pt）
- 实现方式：单列 Table，每行一个 TableRow，borders 全部设为 NONE
- 行内注释以 `#` 分割，`#` 之前用亮色，`#` 之后用灰色
- 目录树行间距：`before: 14, after: 14`

### 3.3 数据表规范
- 表头：`navy` 背景，白色粗体文字，`bAll(C.blue)` 边框
- 数据行：偶数行白色，奇数行 `lgray`，`bAll(C.mgray)` 边框
- 第一列（文件名/代码）使用 `Courier New`，其余列使用 `Arial`
- 单元格内边距：`margins: { top:60, bottom:60, left:120, right:120 }`
- **必须同时设置 `columnWidths` 数组和每个 TableCell 的 `width`，两者总和须一致**

### 3.4 特殊信息框
- 蓝色信息框：`fill: D6E8F7`，标签行 `fill: 2563A8`
- 黄色警告框：`fill: FEF3C7`，标签行 `fill: D97706`
- 红色错误框：`fill: FEF2F2`，标签行 `fill: DC2626`
- 均为单列 Table，第一行为标签行，后续行为内容行

### 3.5 页面与间距
- 纸张：A4（`width:11906, height:16838` DXA）
- 页边距：`top:1440, right:1260, bottom:1440, left:1260`（约 1英寸/0.875英寸）
- 内容宽度：`9026` DXA
- H1前间距：`before: 480`，H1后：`before: 200`
- H2前间距：`before: 320`，H3前：`before: 240`
- 正文行间距：`before: 60, after: 60`

---

## 四、生成流程

### 步骤1：确认文档范围
根据用户需求判断需要生成哪些文档：
- 仅需概述 → SDD（PIAP-SDD-001）
- 需要数据库设计 → SDD + SYS（PIAP-SYS-002）
- 需要后端目录结构 → SDD + SYS + BAD（PIAP-BAD-003）
- 需要完整全栈文档 → 四份全部生成

### 步骤2：读取 docx SKILL.md
```
view /mnt/skills/public/docx/SKILL.md
```
确认 `docx@9.5.3` 可用（`npm list -g docx`），否则先安装。

### 步骤3：编写生成脚本
每份文档对应一个独立的 `.js` 脚本，放置在 `/home/claude/`：
```
gen_sdd.js      → PIAP_SDD_001.docx
gen_sysdesign.js → PIAP_SYS_002_MySQL.docx
gen_backend.js  → PIAP_BAD_003_Architecture.docx
gen_frontend.js → PIAP_FED_004_Frontend.docx
```

脚本顶部必须引入所有用到的 docx 组件，并定义颜色常量 `C`、边框帮助函数 `b1/bAll/bNones`、段落帮助函数 `h1/h2/h3/p/bul/sp/hr`。

### 步骤4：校验与输出
```bash
node gen_*.js && cp /home/claude/*.docx /mnt/user-data/outputs/
```
每个脚本执行后检查 `returncode === 0`，失败则读取错误信息修复（常见错误：PageNumber构造函数调用方式、ENUM类型列引用）。

### 步骤5：交付
使用 `present_files` 工具依次呈现所有生成的 `.docx` 文件，并简要说明每份文档的章节数和核心内容。

---

## 五、常见错误与修复

| 错误 | 原因 | 修复 |
|------|------|------|
| `PageNumber is not a constructor` | docx v9 中 PageNumber 用法变更 | 删除 PageNumber 引用或改为 TextRun 静态文字 |
| 表格列宽不一致 | columnWidths 与 TableCell width 总和不匹配 | 确保两者加总相等 |
| 代码块背景显示为白色 | `type: ShadingType.SOLID` 导致覆盖 | 改为 `type: ShadingType.CLEAR` |
| 中文字符乱码 | 未使用 utf8mb4 或字体回退 | 确保 font 设置 "Arial"（包含中文回退） |
| 黑色表格背景 | ShadingType.SOLID 将颜色当前景色处理 | 统一改为 `ShadingType.CLEAR` |
| 列表显示为方块 | 使用了 Unicode 字符 `•` | 必须用 `LevelFormat.BULLET` + numbering config |

---

## 六、业务领域关键约定（跨文档一致性）

以下术语和设计决策在所有文档中必须保持一致：

**角色体系（6种，不可增减）：**
`super_admin > org_admin > inspector > analyst > api_service > auditor`

**任务状态机（单向流转）：**
`pending → running → done | failed | reviewing`

**风险等级（4级，颜色固定）：**
`GREEN → YELLOW → ORANGE → RED`（对应 Risk Score 0-30/31-60/61-80/81-100）

**Verdict 枚举（4个）：**
`pass / fail / uncertain / manual_required`

**五维度评分（权重固定）：**
```
证据充分性(30%) + 输出一致性(25%) + 模型置信度(20%)
+ 溯源完整性(15%) + 异常模式(10%) = Risk Score [0,100]
```

**数据库三库分离：**
```
piap_main   → 核心业务数据
piap_audit  → 审计日志（只追加，独立库）
piap_analytics → ETL 分析数据（只读）
```

**API 统一 Envelope：**
```json
{ "code": 200, "message": "ok", "data": {...},
  "meta": { "page": 1, "page_size": 20, "total": 348, "request_id": "req_..." } }
```

**SSE 消息格式：**
```json
{ "type": "node_start|node_done|complete|error", "data": {...} }
```

---

## 七、扩展场景参考

本技能的文档模式可适配以下同类平台，只需调整业务领域词汇：

- **医疗影像 AI 审核平台**：将"产品缺陷"替换为"影像异常"，工具替换为DICOM读取/病灶分割
- **金融风控 Agent 平台**：将"检测结论"替换为"风险评级"，稳定性分析聚焦于模型漂移监控
- **法律文档合规检测**：将"规格标准"替换为"法规条文"，RAG知识库替换为法规数据库
- **代码安全扫描平台**：将"图像检测"替换为"AST分析"，工具替换为SAST/DAST工具链

扩展时保持架构层次（SDD→SYS→BAD→FED）和命名约定不变，仅替换业务实体名称和领域特定工具列表。
