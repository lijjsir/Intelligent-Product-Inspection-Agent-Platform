# 算法工程师 - 训练任务、评测与模型部署开发设计文档

> **版本**: v1.0
> **日期**: 2026-05-20
> **角色**: algorithm_engineer
> **状态**: 设计阶段
> **依赖文档**: [数据接入功能开发设计文档](./algorithm_engineer_data_import_design.md)

---

## 目录

1. [概述](#1-概述)
2. [业务场景与需求](#2-业务场景与需求)
3. [技术架构](#3-技术架构)
4. [数据库设计](#4-数据库设计)
5. [API接口设计](#5-api接口设计)
6. [训练任务模块](#6-训练任务模块)
7. [微调管理模块](#7-微调管理模块)
8. [离线评测模块](#8-离线评测模块)
9. [在线验证模块](#9-在线验证模块)
10. [实验追踪模块](#10-实验追踪模块)
11. [模型部署模块](#11-模型部署模块)
12. [前端页面设计](#12-前端页面设计)
13. [开发计划](#13-开发计划)

---

## 1. 概述

### 1.1 功能定位

本文档覆盖算法工程师工作台中**训练任务、微调管理、离线评测、在线验证、实验追踪、模型部署**六大功能模块。这些模块承接数据接入阶段的产出（已对齐、已增强的多模态数据集），完成从"数据就绪"到"模型上线服务检测任务"的完整闭环。

### 1.2 与数据接入文档的关系

```
数据接入文档（上游）                本文档（下游）
├─ 数据集管理                       ├─ 训练任务（引用数据集）
├─ 知识图谱构建                     ├─ 微调管理（引用训练产出）
├─ 跨媒体对齐                       ├─ 离线评测（引用测试集）
├─ 数据增强                         ├─ 在线验证（引用部署模型）
└─ 数据导出                         ├─ 实验追踪（贯穿全流程）
                                    └─ 模型部署（产出服务化模型）
```

### 1.3 核心能力矩阵

| 能力维度 | 功能点 | 优先级 | 说明 |
|----------|--------|--------|------|
| **测试集管理** | 从数据集选取样本组成评测集 | P0 | 支持图片/文本/多模态样本快照 |
| **训练任务** | 配置并启动模型训练/微调 | P0 | 对接平台GPU集群，异步执行 |
| **微调管理** | 基于训练任务产出进行模型微调 | P0 | 支持多模态大模型微调 |
| **离线评测** | 在测试集上评估模型性能 | P0 | 支持自定义指标和内置指标 |
| **在线验证** | 对部署中的模型进行A/B验证 | P1 | 影子流量对比验证 |
| **实验追踪** | 记录超参数、指标、产出物 | P1 | 自研轻量实现，不依赖MLflow |
| **模型部署** | 将模型注册为检测Agent可用服务 | P0 | 部署后模型可被检测任务调用 |

### 1.4 目标用户

- **算法工程师**：配置训练参数、启动任务、分析结果
- **团队负责人**：查看实验对比、审批模型部署
- **检测系统**：调用部署后的模型执行产品缺陷检测

---

## 2. 业务场景与需求

### 2.1 典型使用流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    算法工程师模型开发工作流                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: 准备测试集                                              │
│    ├── 从已接入的数据集中选取代表性样本                          │
│    ├── 确认标注完整性（图片+文本+对齐关系）                      │
│    └── 冻结测试集版本（防止训练时数据泄露）                      │
│                                                                 │
│  Step 2: 创建训练任务                                            │
│    ├── 选择训练数据集（来自数据接入模块）                        │
│    ├── 选择基础模型配置（平台已注册的视觉大模型）                │
│    ├── 选择评测数据集（可选，用于训练过程中验证）                │
│    ├── 配置训练超参数（学习率、批次大小、轮数等）                │
│    └── 关联实验（用于后续对比追踪）                              │
│                                                                 │
│  Step 3: 启动训练                                                │
│    ├── 任务进入队列，等待GPU资源                                 │
│    ├── 训练过程中实时输出日志和指标                              │
│    └── 训练完成后自动保存模型权重和训练报告                      │
│                                                                 │
│  Step 4: 微调优化（可选）                                        │
│    ├── 基于训练任务产出创建微调任务                              │
│    ├── 使用更小学习率进行精细调整                                │
│    └── 产出最终候选模型                                          │
│                                                                 │
│  Step 5: 离线评测                                                │
│    ├── 在独立测试集上运行模型推理                                │
│    ├── 计算Accuracy / F1 / mAP / IoU / AR等指标                  │
│    ├── 生成错误案例分析报告                                      │
│    └── 与历史版本进行指标对比                                    │
│                                                                 │
│  Step 6: 模型部署                                                │
│    ├── 选择通过评测的模型版本                                    │
│    ├── 配置部署参数（推理批次大小、并发限制等）                  │
│    ├── 部署到模型服务集群                                        │
│    └── 注册到检测Agent可用模型列表                               │
│                                                                 │
│  Step 7: 在线验证（可选）                                        │
│    ├── 对部署后的模型进行影子流量测试                            │
│    ├── 对比新旧模型的线上表现                                    │
│    └── 确认无误后切换生产流量                                    │
│                                                                 │
│  Step 8: 实验追踪                                                │
│    ├── 查看同一实验下的多次运行对比                              │
│    ├── 分析超参数对指标的影响                                    │
│    └── 导出实验报告用于论文/专利                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 业务规则

#### 2.2.1 状态机规则

```
训练任务 / 微调 / 评测 / 部署 / 在线验证 共用统一状态机：

draft ──launch──> queued ──worker pickup──> running ──success──> completed
   │                    │                       │
   │                    │                       └──error──> failed
   │                    │
   │                    └──cancel──> cancelled
   │
   └──delete──> (soft delete)

可编辑状态: draft, failed
可取消状态: queued, running
可删除状态: draft, completed, failed, cancelled
```

#### 2.2.2 数据引用规则

| 资源类型 | 可引用上游 | 引用约束 |
|----------|-----------|----------|
| 测试集 | 数据集样本 | 样本必须属于同一数据集，创建时快照冻结 |
| 训练任务 | 数据集、模型配置、测试集(可选)、实验(可选) | 数据集状态须为active，模型配置须为active且类型为chat/multimodal |
| 微调任务 | 训练任务、模型配置、实验(可选) | 训练任务须为completed状态 |
| 离线评测 | 测试集、训练任务/微调/部署 | 目标资源须为completed状态 |
| 在线验证 | 部署记录、实验(可选) | 部署须为completed状态 |
| 部署记录 | 微调任务/训练任务 | 源资源须为completed状态 |

#### 2.2.3 权限与协作规则

- 所有资源按 `org_id + created_by` 隔离，算法工程师只能查看自己创建的资源
- 实验(Experiment)作为逻辑分组，同一实验下的不同资源可被统一查看
- 部署后的模型对检测Agent全局可见（跨用户共享）

---

## 3. 技术架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ 测试集   │ │ 训练任务 │ │ 离线评测 │ │ 模型部署 │         │
│  │ 管理     │ │ 管理     │ │ 管理     │ │ 管理     │         │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                      │
│  │ 微调管理 │ │ 在线验证 │ │ 实验追踪 │                      │
│  └──────────┘ └──────────┘ └──────────┘                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI 后端服务                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐  │
│  │ EvalSet API │ │ TrainingJob │ │ FineTune / Eval /       │  │
│  │ Service     │ │ API Service │ │ Deploy API Service      │  │
│  └─────────────┘ └─────────────┘ └─────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    执行引擎层                               │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │  │
│  │  │ GPU Job      │  │ Model        │  │ Evaluation     │  │  │
│  │  │ Scheduler    │  │ Registry     │  │ Engine         │  │  │
│  │  │ (Celery/     │  │ (部署管理)   │  │ (指标计算)     │  │  │
│  │  │  Local)      │  │              │  │                │  │  │
│  │  └──────────────┘  └──────────────┘  └────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │   MySQL     │     │    MinIO    │     │  GPU Cluster│
   │  任务/指标  │     │  模型权重   │     │  训练/推理  │
   └─────────────┘     └─────────────┘     └─────────────┘
                              │
                        ┌─────────────┐
                        │    Redis    │
                        │  任务队列   │
                        └─────────────┘
```

### 3.2 技术选型

| 层次 | 技术 | 版本要求 | 说明 |
|------|------|----------|------|
| **前端框架** | Vue 3 + Vite | ^3.4 | Composition API + TypeScript |
| **UI组件库** | Element Plus | ^2.4 | 表格、表单、进度条、标签页 |
| **图表可视化** | ECharts | ^5.4 | 指标趋势图、对比柱状图 |
| **后端框架** | FastAPI | ^0.104 | 异步高性能API |
| **ORM** | SQLAlchemy | ^2.0 | 异步支持 |
| **关系数据库** | MySQL | 8.0+ | 存储任务、指标、实验 |
| **对象存储** | MinIO | latest | 存储模型权重、训练日志 |
| **任务队列** | Celery + Redis | 5.x | 异步GPU任务调度 |
| **训练执行** | Python subprocess / SSH | - | 调用GPU集群训练脚本 |
| **模型服务** | vLLM / TGI / 自研 | - | 部署后提供推理API |

### 3.3 目录结构规划

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── algo_workspace.py        # 已有：统一算法资源API
│   │   └── model_configs.py         # 已有：模型配置管理
│   │
│   ├── schemas/
│   │   └── algo_resources.py        # 已有：Pydantic Schema
│   │
│   ├── services/
│   │   ├── algo_workspace_service.py # 已有：核心业务逻辑
│   │   ├── gpu_job_service.py        # 新增：GPU任务调度
│   │   ├── evaluation_engine.py      # 新增：评测指标计算
│   │   └── model_registry_service.py # 新增：模型注册管理
│   │
│   ├── repositories/
│   │   └── algo_resource_repo.py     # 已有：数据访问层
│   │
│   ├── models/
│   │   └── algo_resources.py         # 已有：ORM模型
│   │
│   └── engines/
│       ├── training_runner.py        # 新增：训练任务执行器
│       ├── evaluation_runner.py      # 新增：评测任务执行器
│       └── deployment_manager.py     # 新增：部署管理器
│
├── worker/
│   └── tasks/
│       └── algo_tasks.py             # 新增：Celery异步任务
│
frontend/src/
├── views/ops/
│   ├── TrainingJobsView.vue          # 训练任务列表
│   ├── TrainingJobDetailView.vue     # 训练任务详情
│   ├── FineTuneView.vue              # 微调管理
│   ├── EvalSetsView.vue              # 测试集管理
│   ├── OfflineEvalView.vue           # 离线评测
│   ├── OnlineValidationView.vue      # 在线验证
│   ├── ExperimentsView.vue           # 实验追踪
│   └── DeploymentsView.vue           # 模型部署
│
├── components/business/training/
│   ├── TrainingJobCard.vue           # 任务卡片
│   ├── MetricsChart.vue              # 指标图表
│   ├── LogViewer.vue                 # 日志查看器
│   ├── EvalResultTable.vue           # 评测结果表格
│   ├── ExperimentCompare.vue         # 实验对比
│   └── DeploymentStatus.vue          # 部署状态
│
├── stores/
│   └── training.store.ts             # 训练/评测/部署Store
│
├── api/
│   └── algo_workspace.api.ts         # 算法工作台API封装
│
└── types/
    └── training.types.ts             # 类型定义
```

---

## 4. 数据库设计

### 4.1 已有表（来自数据接入文档和现有代码）

以下表已在现有代码中定义，本文档直接使用：

| 表名 | 说明 | 位置 |
|------|------|------|
| `datasets` | 数据集主表 | `app/models/dataset.py` |
| `dataset_samples` | 数据样本表 | `app/models/dataset.py` |
| `model_configs` | 模型配置表 | `app/models/model_config.py` |

### 4.2 新增/已有算法资源表

以下表已在 `app/models/algo_resources.py` 中定义：

#### 4.2.1 evaluation_datasets（测试集）

```python
class EvaluationDataset(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "evaluation_datasets"

    source_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    # 继承字段：id, org_id, created_by, name, description, status, config_json, result_summary
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `source_dataset_id` | UUID | 来源数据集ID（关联datasets表） |
| `status` | VARCHAR | draft / queued / running / completed / failed / cancelled |
| `config_json` | JSON | 创建配置（样本选取策略等） |
| `result_summary` | JSON | 统计信息（样本数、类型分布等） |

#### 4.2.2 evaluation_dataset_items（测试集样本项）

```python
class EvaluationDatasetItem(Base, TimestampMixin):
    __tablename__ = "evaluation_dataset_items"

    evaluation_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    source_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_sample_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    item_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `evaluation_dataset_id` | UUID | 所属测试集ID |
| `dataset_sample_id` | UUID | 来源样本ID（关联dataset_samples） |
| `payload_json` | JSON | 样本快照（sample_type, file_url, annotation_data等） |
| `item_order` | INT | 排序序号 |

> **设计意图**：使用快照机制（`payload_json`），即使原始样本被删除或修改，测试集内容保持不变，防止数据泄露。

#### 4.2.3 training_jobs（训练任务）

```python
class TrainingJob(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "training_jobs"

    source_dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    model_config_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    eval_set_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_dataset_id` | UUID | 训练数据集ID |
| `model_config_id` | UUID | 基础模型配置ID |
| `eval_set_id` | UUID | 评测数据集ID（可选，用于训练过程验证） |
| `experiment_id` | UUID | 所属实验ID（可选） |
| `status` | VARCHAR | draft / queued / running / completed / failed / cancelled |
| `execution_mode` | VARCHAR | celery / local_background |
| `executor_job_id` | VARCHAR | Celery任务ID或本地进程标识 |
| `started_at` | DATETIME | 开始时间 |
| `completed_at` | DATETIME | 完成时间 |
| `config_json` | JSON | 训练超参数配置 |
| `result_summary` | JSON | 训练结果（artifacts, metrics, logs） |

#### 4.2.4 fine_tune_runs（微调任务）

```python
class FineTuneRun(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "fine_tune_runs"

    training_job_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    model_config_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `training_job_id` | UUID | 关联的训练任务ID |
| `model_config_id` | UUID | 微调目标模型配置ID |
| `experiment_id` | UUID | 所属实验ID（可选） |

#### 4.2.5 offline_evaluations（离线评测）

```python
class OfflineEvaluation(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "offline_evaluations"

    eval_set_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    target_type: Mapped[str] = mapped_column(String(64), default="training_job")
    target_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `eval_set_id` | UUID | 测试集ID |
| `target_type` | VARCHAR | 评测目标类型：training_job / fine_tune / deployment |
| `target_id` | UUID | 评测目标ID |
| `result_summary` | JSON | 评测指标结果 |

#### 4.2.6 online_validations（在线验证）

```python
class OnlineValidation(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "online_validations"

    deployment_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `deployment_id` | UUID | 关联的部署记录ID |
| `result_summary` | JSON | 在线验证指标（延迟、吞吐量、准确率等） |

#### 4.2.7 experiments（实验）

```python
class Experiment(Base, TimestampMixin, AlgoResourceMixin):
    __tablename__ = "experiments"

    # 仅继承AlgoResourceMixin字段
    # 作为逻辑分组容器，不关联具体执行
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | VARCHAR | draft / active / archived |
| `config_json` | JSON | 实验目标、假设等描述 |

#### 4.2.8 model_deployments（模型部署）

```python
class ModelDeployment(Base, TimestampMixin, AlgoResourceMixin, AlgoExecutionMixin):
    __tablename__ = "model_deployments"

    source_type: Mapped[str] = mapped_column(String(64), default="fine_tune")
    source_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    experiment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_type` | VARCHAR | 来源类型：fine_tune / training_job |
| `source_id` | UUID | 来源任务ID |
| `result_summary` | JSON | 部署信息（服务地址、状态、调用统计） |

### 4.3 索引设计

```sql
-- 测试集索引
CREATE INDEX idx_eval_dataset_source ON evaluation_datasets(source_dataset_id, status);

-- 训练任务索引
CREATE INDEX idx_training_job_dataset ON training_jobs(source_dataset_id, status);
CREATE INDEX idx_training_job_model ON training_jobs(model_config_id, status);
CREATE INDEX idx_training_job_experiment ON training_jobs(experiment_id, status);

-- 评测索引
CREATE INDEX idx_offline_eval_target ON offline_evaluations(target_type, target_id, status);
CREATE INDEX idx_offline_eval_evalset ON offline_evaluations(eval_set_id, status);

-- 部署索引
CREATE INDEX idx_deployment_source ON model_deployments(source_type, source_id, status);
```

---

## 5. API接口设计

### 5.1 接口概览

| 模块 | 接口数量 | 基础路径 |
|------|----------|----------|
| 测试集管理 | 8 | `/api/v1/eval-datasets` |
| 训练任务 | 7 | `/api/v1/training-jobs` |
| 微调管理 | 6 | `/api/v1/fine-tunes` |
| 离线评测 | 6 | `/api/v1/offline-evaluations` |
| 在线验证 | 6 | `/api/v1/online-validations` |
| 实验追踪 | 5 | `/api/v1/experiments` |
| 模型部署 | 6 | `/api/v1/deployments` |

### 5.2 测试集管理接口

#### 5.2.1 创建测试集

```http
POST /api/v1/eval-datasets
Content-Type: application/json

{
  "name": "缺陷检测测试集 v1",
  "description": "用于Q2模型迭代的基准测试",
  "source_dataset_id": "ds_xxx",
  "sample_ids": ["sample_1", "sample_2", "sample_3"],
  "config_json": {
    "selection_strategy": "stratified",
    "stratify_by": "defect_type"
  }
}
```

**响应：**

```json
{
  "code": 201,
  "message": "created",
  "data": {
    "id": "eval_xxx",
    "org_id": "org_xxx",
    "name": "缺陷检测测试集 v1",
    "description": "用于Q2模型迭代的基准测试",
    "status": "draft",
    "source_dataset_id": "ds_xxx",
    "sample_count": 3,
    "samples_preview": [...],
    "created_at": "2026-05-20T10:00:00Z"
  }
}
```

#### 5.2.2 获取测试集详情

```http
GET /api/v1/eval-datasets/{resource_id}
```

#### 5.2.3 更新测试集

```http
PATCH /api/v1/eval-datasets/{resource_id}
Content-Type: application/json

{
  "name": "缺陷检测测试集 v1.1",
  "sample_ids": ["sample_1", "sample_2", "sample_3", "sample_4"]
}
```

> 更新sample_ids时会重新生成快照，替换原有样本项。

#### 5.2.4 删除测试集

```http
DELETE /api/v1/eval-datasets/{resource_id}
```

#### 5.2.5 列出测试集样本

```http
GET /api/v1/eval-datasets/{resource_id}/samples?page=1&size=24&sample_type=image
```

#### 5.2.6 追加样本

```http
POST /api/v1/eval-datasets/{resource_id}/samples
Content-Type: application/json

{
  "sample_ids": ["sample_5", "sample_6"]
}
```

#### 5.2.7 删除单个样本

```http
DELETE /api/v1/eval-datasets/{resource_id}/samples/{item_id}
```

#### 5.2.8 列出自己的测试集

```http
GET /api/v1/eval-datasets?page=1&size=20&keyword=缺陷&status=draft
```

### 5.3 训练任务接口

#### 5.3.1 创建训练任务

```http
POST /api/v1/training-jobs
Content-Type: application/json

{
  "name": "ResNet50-缺陷检测-第1轮",
  "description": "使用增强后的数据集训练",
  "source_dataset_id": "ds_xxx",
  "model_config_id": "mc_xxx",
  "eval_set_id": "eval_xxx",
  "experiment_id": "exp_xxx",
  "config_json": {
    "hyperparameters": {
      "learning_rate": 0.001,
      "batch_size": 32,
      "epochs": 50,
      "optimizer": "adam",
      "scheduler": "cosine"
    },
    "data_config": {
      "train_val_split": [0.8, 0.2],
      "augmentation": true
    },
    "hardware": {
      "gpu_count": 2,
      "gpu_type": "A100"
    }
  }
}
```

**约束校验：**
- `source_dataset_id` 必须存在且状态为 active
- `model_config_id` 必须存在且 `is_active=true`，`model_type` 为 chat 或 multimodal
- `eval_set_id` 如提供，必须存在
- `experiment_id` 如提供，必须存在

#### 5.3.2 启动训练任务

```http
POST /api/v1/training-jobs/{resource_id}/launch
```

**行为：**
1. 校验状态为 draft 或 failed
2. 检查是否有活跃的Celery worker
3. 状态更新为 queued，记录 execution_mode
4. 创建异步任务执行训练

#### 5.3.3 取消训练任务

```http
POST /api/v1/training-jobs/{resource_id}/cancel
```

#### 5.3.4 获取训练任务详情

```http
GET /api/v1/training-jobs/{resource_id}
```

**响应包含：**

```json
{
  "id": "tj_xxx",
  "name": "ResNet50-缺陷检测-第1轮",
  "status": "running",
  "source_dataset_id": "ds_xxx",
  "model_config_id": "mc_xxx",
  "model_config_ref": {
    "id": "mc_xxx",
    "display_name": "ResNet50-ImageNet",
    "model_key": "resnet50",
    "model_type": "multimodal"
  },
  "eval_set_id": "eval_xxx",
  "experiment_id": "exp_xxx",
  "execution_mode": "celery",
  "executor_job_id": "celery_task_xxx",
  "started_at": "2026-05-20T10:00:00Z",
  "result_summary": {
    "summary": {
      "status": "running",
      "execution_mode": "celery",
      "started_at": "2026-05-20T10:00:00Z",
      "completed_at": null,
      "model_config_id": "mc_xxx"
    },
    "artifacts": [
      {"type": "checkpoint", "path": "minio://checkpoints/epoch_10.pt", "epoch": 10}
    ],
    "metrics": {
      "train_loss": [2.3, 1.8, 1.5, ...],
      "val_accuracy": [0.65, 0.72, 0.78, ...]
    },
    "logs": ["Epoch 1/50 started...", "Loss: 2.3"]
  }
}
```

#### 5.3.5 更新训练任务（仅draft/failed状态）

```http
PATCH /api/v1/training-jobs/{resource_id}
Content-Type: application/json

{
  "name": "新名称",
  "model_config_id": "mc_new",
  "config_json": {"hyperparameters": {"learning_rate": 0.0005}}
}
```

#### 5.3.6 删除训练任务

```http
DELETE /api/v1/training-jobs/{resource_id}
```

#### 5.3.7 列出训练任务

```http
GET /api/v1/training-jobs?page=1&size=20&status=completed
```

### 5.4 微调管理接口

#### 5.4.1 创建微调任务

```http
POST /api/v1/fine-tunes
Content-Type: application/json

{
  "name": "ResNet50-微调-学习率0.0001",
  "description": "基于第1轮训练结果进行微调",
  "training_job_id": "tj_xxx",
  "model_config_id": "mc_xxx",
  "experiment_id": "exp_xxx",
  "config_json": {
    "hyperparameters": {
      "learning_rate": 0.0001,
      "batch_size": 16,
      "epochs": 20,
      "freeze_layers": ["conv1", "layer1"]
    }
  }
}
```

#### 5.4.2 启动/取消/获取/更新/删除/列出

与训练任务接口模式一致：

```http
POST /api/v1/fine-tunes/{resource_id}/launch
POST /api/v1/fine-tunes/{resource_id}/cancel
GET /api/v1/fine-tunes/{resource_id}
PATCH /api/v1/fine-tunes/{resource_id}
DELETE /api/v1/fine-tunes/{resource_id}
GET /api/v1/fine-tunes?page=1&size=20
```

### 5.5 离线评测接口

#### 5.5.1 创建离线评测

```http
POST /api/v1/offline-evaluations
Content-Type: application/json

{
  "name": "模型v1.2离线评测",
  "description": "在基准测试集上评估",
  "eval_set_id": "eval_xxx",
  "target_type": "training_job",
  "target_id": "tj_xxx",
  "experiment_id": "exp_xxx",
  "config_json": {
    "metrics": ["accuracy", "f1", "mAP", "IoU", "AR"],
    "batch_size": 32,
    "device": "cuda"
  }
}
```

**target_type 枚举：**
- `training_job` - 评测训练任务产出
- `fine_tune` - 评测微调任务产出
- `deployment` - 评测已部署模型

#### 5.5.2 启动/取消/获取/更新/删除/列出

```http
POST /api/v1/offline-evaluations/{resource_id}/launch
POST /api/v1/offline-evaluations/{resource_id}/cancel
GET /api/v1/offline-evaluations/{resource_id}
PATCH /api/v1/offline-evaluations/{resource_id}
DELETE /api/v1/offline-evaluations/{resource_id}
GET /api/v1/offline-evaluations?page=1&size=20
```

### 5.6 在线验证接口

#### 5.6.1 创建在线验证

```http
POST /api/v1/online-validations
Content-Type: application/json

{
  "name": "部署v1影子验证",
  "description": "对比新旧模型线上表现",
  "deployment_id": "deploy_xxx",
  "experiment_id": "exp_xxx",
  "config_json": {
    "validation_type": "shadow",
    "sample_rate": 0.1,
    "duration_hours": 24,
    "metrics": ["latency_p99", "throughput", "accuracy"]
  }
}
```

#### 5.6.2 启动/取消/获取/更新/删除/列出

```http
POST /api/v1/online-validations/{resource_id}/launch
POST /api/v1/online-validations/{resource_id}/cancel
GET /api/v1/online-validations/{resource_id}
PATCH /api/v1/online-validations/{resource_id}
DELETE /api/v1/online-validations/{resource_id}
GET /api/v1/online-validations?page=1&size=20
```

### 5.7 实验追踪接口

#### 5.7.1 创建实验

```http
POST /api/v1/experiments
Content-Type: application/json

{
  "name": "Q2缺陷检测模型迭代",
  "description": "尝试不同骨干网络和训练策略",
  "config_json": {
    "goal": "提升小缺陷检出率",
    "hypothesis": "使用更深的网络能提升特征表达能力"
  }
}
```

#### 5.7.2 获取实验详情（含关联资源）

```http
GET /api/v1/experiments/{resource_id}
```

**响应扩展（建议实现）：**

```json
{
  "id": "exp_xxx",
  "name": "Q2缺陷检测模型迭代",
  "status": "active",
  "related_resources": {
    "training_jobs": [{"id": "tj_1", "name": "...", "status": "completed"}],
    "fine_tunes": [{"id": "ft_1", "name": "...", "status": "completed"}],
    "evaluations": [{"id": "ev_1", "name": "...", "metrics": {"accuracy": 0.92}}],
    "deployments": [{"id": "dp_1", "name": "...", "status": "completed"}]
  }
}
```

#### 5.7.3 更新/删除/列出实验

```http
PATCH /api/v1/experiments/{resource_id}
DELETE /api/v1/experiments/{resource_id}
GET /api/v1/experiments?page=1&size=20
```

> 实验为逻辑分组，删除实验不影响关联资源，仅解除关联。

### 5.8 模型部署接口

#### 5.8.1 创建部署记录

```http
POST /api/v1/deployments
Content-Type: application/json

{
  "name": "缺陷检测模型-v1.2-生产",
  "description": "Q2迭代最终部署版本",
  "source_type": "fine_tune",
  "source_id": "ft_xxx",
  "experiment_id": "exp_xxx",
  "config_json": {
    "service_config": {
      "max_batch_size": 8,
      "max_concurrency": 16,
      "timeout_ms": 5000
    },
    "hardware": {
      "gpu_type": "A100",
      "gpu_count": 1
    },
    "scaling": {
      "min_replicas": 1,
      "max_replicas": 3
    }
  }
}
```

#### 5.8.2 启动部署

```http
POST /api/v1/deployments/{resource_id}/launch
```

**行为：**
1. 校验源任务状态为 completed
2. 从MinIO拉取模型权重
3. 启动模型服务容器（vLLM/TGI）
4. 注册到服务发现/负载均衡
5. 更新模型配置表，标记为检测Agent可用

#### 5.8.3 取消部署（下线）

```http
POST /api/v1/deployments/{resource_id}/cancel
```

#### 5.8.4 获取部署详情

```http
GET /api/v1/deployments/{resource_id}
```

**响应：**

```json
{
  "id": "deploy_xxx",
  "name": "缺陷检测模型-v1.2-生产",
  "status": "completed",
  "source_type": "fine_tune",
  "source_id": "ft_xxx",
  "execution_mode": "celery",
  "result_summary": {
    "summary": {
      "status": "completed",
      "service_url": "http://model-svc:8000/v1/models/defect-detection-v1-2",
      "health_status": "healthy"
    },
    "artifacts": [
      {"type": "model_weights", "path": "minio://models/defect-detection-v1-2.safetensors"}
    ],
    "metrics": {
      "avg_latency_ms": 120,
      "throughput_qps": 25
    }
  }
}
```

#### 5.8.5 更新/删除/列出部署

```http
PATCH /api/v1/deployments/{resource_id}
DELETE /api/v1/deployments/{resource_id}
GET /api/v1/deployments?page=1&size=20
```

---

## 6. 训练任务模块

### 6.1 执行流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   用户创建   │────>│   配置校验   │────>│  保存为draft │
│  训练任务    │     │ (数据集/模型)│     │             │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                │
┌─────────────┐     ┌─────────────┐     ┌──────▼──────┐
│   执行完成   │<────│  GPU集群执行 │<────│  用户启动   │
│ 更新completed│     │  (Celery)   │     │   launch    │
└─────────────┘     └─────────────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│  保存产出物  │
│ (权重/日志)  │
└─────────────┘
```

### 6.2 训练执行器实现

```python
# backend/app/engines/training_runner.py

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.services.object_storage.factory import build_object_storage


class TrainingRunner:
    """训练任务执行器 - 调用GPU集群训练脚本"""

    def __init__(self, org_id: str, user_id: str):
        self._org_id = org_id
        self._user_id = user_id
        self._storage = build_object_storage()

    async def run(
        self,
        *,
        job_id: str,
        dataset_id: str,
        model_config_id: str,
        eval_set_id: str | None,
        hyperparameters: dict[str, Any],
        hardware: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行训练任务。

        当前实现为骨架代码，实际训练逻辑需根据具体训练框架补充。
        设计为可替换为真实训练调用（如LLaVA-Factory、PyTorch DDP等）。
        """
        # 1. 准备数据路径
        dataset_path = await self._prepare_dataset(dataset_id)

        # 2. 准备模型配置
        model_info = await self._get_model_info(model_config_id)

        # 3. 构建训练命令
        train_cmd = self._build_train_command(
            dataset_path=dataset_path,
            model_key=model_info["model_key"],
            hyperparameters=hyperparameters,
            hardware=hardware,
            output_dir=f"/tmp/training/{job_id}",
        )

        # 4. 执行训练（当前为模拟）
        metrics = await self._execute_training(train_cmd, job_id=job_id)

        # 5. 上传产出物到MinIO
        artifacts = await self._upload_artifacts(job_id, output_dir=f"/tmp/training/{job_id}")

        return {
            "metrics": metrics,
            "artifacts": artifacts,
            "logs": ["Training completed successfully"],
        }

    async def _prepare_dataset(self, dataset_id: str) -> str:
        """从MinIO下载数据集到本地路径"""
        # 实际实现：查询dataset_samples，下载到本地目录
        return f"/tmp/datasets/{dataset_id}"

    async def _get_model_info(self, model_config_id: str) -> dict[str, Any]:
        """获取模型配置信息"""
        # 实际实现：查询model_configs表
        return {"model_key": "resnet50", "model_type": "multimodal"}

    def _build_train_command(
        self,
        *,
        dataset_path: str,
        model_key: str,
        hyperparameters: dict[str, Any],
        hardware: dict[str, Any],
        output_dir: str,
    ) -> list[str]:
        """构建训练命令"""
        cmd = [
            "python", "-m", "torch.distributed.launch",
            f"--nproc_per_node={hardware.get('gpu_count', 1)}",
            "train.py",
            "--model", model_key,
            "--data", dataset_path,
            "--output", output_dir,
            "--lr", str(hyperparameters.get("learning_rate", 0.001)),
            "--batch-size", str(hyperparameters.get("batch_size", 32)),
            "--epochs", str(hyperparameters.get("epochs", 50)),
        ]
        return cmd

    async def _execute_training(self, cmd: list[str], job_id: str) -> dict[str, Any]:
        """执行训练命令并收集指标"""
        # 当前为模拟实现
        # 实际应使用 subprocess 或 SSH 到GPU集群执行
        await asyncio.sleep(2)  # 模拟训练时间

        return {
            "train_loss": [2.3, 1.8, 1.5, 1.2, 1.0],
            "val_accuracy": [0.65, 0.72, 0.78, 0.82, 0.85],
            "val_f1": [0.60, 0.68, 0.75, 0.80, 0.83],
        }

    async def _upload_artifacts(self, job_id: str, output_dir: str) -> list[dict[str, Any]]:
        """上传训练产出物到MinIO"""
        artifacts = []
        output_path = Path(output_dir)

        if output_path.exists():
            for epoch_file in sorted(output_path.glob("epoch_*.pt")):
                key = f"training/{self._org_id}/{job_id}/{epoch_file.name}"
                await self._storage.upload_file(str(epoch_file), key)
                artifacts.append({
                    "type": "checkpoint",
                    "path": f"minio://{key}",
                    "epoch": int(epoch_file.stem.split("_")[1]),
                })

        return artifacts
```

### 6.3 与Celery集成

```python
# backend/worker/tasks/algo_tasks.py

from celery import shared_task

from app.engines.training_runner import TrainingRunner
from app.engines.evaluation_runner import EvaluationRunner
from app.engines.deployment_manager import DeploymentManager


@shared_task(bind=True, max_retries=3)
def run_training_job(self, org_id: str, user_id: str, job_id: str, config: dict):
    """异步执行训练任务"""
    runner = TrainingRunner(org_id, user_id)
    try:
        result = asyncio.run(runner.run(job_id=job_id, **config))
        return {"status": "completed", "result": result}
    except Exception as exc:
        if self.request.retries < 3:
            raise self.retry(exc=exc, countdown=60)
        return {"status": "failed", "error": str(exc)}


@shared_task(bind=True, max_retries=3)
def run_evaluation(self, org_id: str, user_id: str, eval_id: str, config: dict):
    """异步执行评测任务"""
    runner = EvaluationRunner(org_id, user_id)
    try:
        result = asyncio.run(runner.run(eval_id=eval_id, **config))
        return {"status": "completed", "result": result}
    except Exception as exc:
        if self.request.retries < 3:
            raise self.retry(exc=exc, countdown=60)
        return {"status": "failed", "error": str(exc)}


@shared_task(bind=True, max_retries=2)
def run_deployment(self, org_id: str, user_id: str, deploy_id: str, config: dict):
    """异步执行部署任务"""
    manager = DeploymentManager(org_id, user_id)
    try:
        result = asyncio.run(manager.deploy(deploy_id=deploy_id, **config))
        return {"status": "completed", "result": result}
    except Exception as exc:
        if self.request.retries < 2:
            raise self.retry(exc=exc, countdown=30)
        return {"status": "failed", "error": str(exc)}
```

---

## 7. 微调管理模块

### 7.1 与训练任务的区别

| 维度 | 训练任务 | 微调任务 |
|------|----------|----------|
| **输入** | 数据集 + 基础模型 | 训练任务产出 + 模型配置 |
| **学习率** | 通常较大（1e-3） | 通常较小（1e-4 ~ 1e-5） |
| **冻结层** | 不冻结 | 可冻结底层特征提取层 |
| **数据量** | 完整数据集 | 可更小（精细调整） |
| **目的** | 从头/预训练权重训练 | 在训练基础上精细优化 |

### 7.2 实现说明

微调任务复用训练任务的执行框架（`TrainingRunner`），差异仅在：

1. **配置校验**：必须关联已完成的训练任务
2. **默认超参数**：学习率自动缩小10倍（如训练用1e-3，微调默认1e-4）
3. **权重加载**：从训练任务的最新checkpoint开始

```python
# 在 TrainingRunner.run() 中增加微调逻辑分支

if fine_tune_source_id:
    # 加载训练任务的最新checkpoint
    source_artifacts = await self._get_training_artifacts(fine_tune_source_id)
    latest_checkpoint = max(source_artifacts, key=lambda x: x["epoch"])
    cmd.extend(["--resume", latest_checkpoint["path"]])
```

---

## 8. 离线评测模块

### 8.1 评测指标定义

#### 8.1.1 分类任务指标

| 指标 | 公式/定义 | 适用场景 |
|------|-----------|----------|
| **Accuracy** | (TP+TN)/(TP+TN+FP+FN) | 类别平衡的分类 |
| **Precision** | TP/(TP+FP) | 关注减少误报 |
| **Recall** | TP/(TP+FN) | 关注减少漏检 |
| **F1-Score** | 2*Precision*Recall/(Precision+Recall) | 综合平衡 |

#### 8.1.2 目标检测/缺陷检测指标

| 指标 | 公式/定义 | 适用场景 |
|------|-----------|----------|
| **mAP@0.5** | IoU阈值0.5时的平均精度均值 | 标准检测评测 |
| **mAP@0.5:0.95** | IoU从0.5到0.95的平均mAP | 严格检测评测 |
| **IoU** | 交集面积/并集面积 | 定位精度 |
| **AR (Average Recall)** | 每类平均召回率 | 检测完整性 |

#### 8.1.3 多模态/VLM指标

| 指标 | 定义 | 适用场景 |
|------|------|----------|
| **BLEU** | n-gram精确度 | 文本生成质量 |
| **CIDEr** | 基于TF-IDF的n-gram相似度 | 图像描述 |
| **METEOR** | 考虑同义词的F1 | 语义相似度 |

### 8.2 评测执行器实现

```python
# backend/app/engines/evaluation_runner.py

import asyncio
from typing import Any

import numpy as np

from app.services.object_storage.factory import build_object_storage


class EvaluationRunner:
    """离线评测执行器"""

    def __init__(self, org_id: str, user_id: str):
        self._org_id = org_id
        self._user_id = user_id
        self._storage = build_object_storage()

    async def run(
        self,
        *,
        eval_id: str,
        eval_set_id: str,
        target_type: str,
        target_id: str,
        metrics: list[str],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """执行离线评测"""
        # 1. 加载测试集
        eval_samples = await self._load_eval_set(eval_set_id)

        # 2. 加载模型
        model = await self._load_model(target_type, target_id)

        # 3. 执行推理
        predictions = await self._run_inference(model, eval_samples, config)

        # 4. 计算指标
        results = self._compute_metrics(predictions, eval_samples, metrics)

        # 5. 生成错误案例
        error_cases = self._extract_error_cases(predictions, eval_samples)

        return {
            "metrics": results,
            "error_cases": error_cases[:100],  # 最多100个错误案例
            "total_samples": len(eval_samples),
            "evaluated_at": datetime.utcnow().isoformat(),
        }

    def _compute_metrics(
        self,
        predictions: list[dict],
        ground_truth: list[dict],
        metrics: list[str],
    ) -> dict[str, float]:
        """计算评测指标"""
        results = {}

        if "accuracy" in metrics:
            correct = sum(
                1 for p, g in zip(predictions, ground_truth)
                if p.get("label") == g.get("label")
            )
            results["accuracy"] = correct / len(ground_truth)

        if "f1" in metrics:
            results["f1"] = self._compute_f1(predictions, ground_truth)

        if "mAP" in metrics:
            results["mAP"] = self._compute_map(predictions, ground_truth)

        if "IoU" in metrics:
            results["mean_IoU"] = self._compute_mean_iou(predictions, ground_truth)

        if "AR" in metrics:
            results["AR"] = self._compute_ar(predictions, ground_truth)

        return results

    def _compute_f1(self, predictions: list[dict], ground_truth: list[dict]) -> float:
        """计算F1分数"""
        # 简化实现，实际需按类别计算
        tp = sum(1 for p, g in zip(predictions, ground_truth) if p["label"] == g["label"])
        fp = sum(1 for p, g in zip(predictions, ground_truth) if p["label"] != g["label"])
        fn = len(ground_truth) - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    def _compute_map(self, predictions: list[dict], ground_truth: list[dict]) -> float:
        """计算mAP（简化实现）"""
        # 实际实现需使用pycocotools或类似库
        return 0.75  # placeholder

    def _compute_mean_iou(self, predictions: list[dict], ground_truth: list[dict]) -> float:
        """计算平均IoU"""
        ious = []
        for p, g in zip(predictions, ground_truth):
            p_box = p.get("bbox", [0, 0, 0, 0])
            g_box = g.get("bbox", [0, 0, 0, 0])
            iou = self._compute_iou(p_box, g_box)
            ious.append(iou)
        return float(np.mean(ious)) if ious else 0.0

    @staticmethod
    def _compute_iou(box_a: list[float], box_b: list[float]) -> float:
        """计算两个bbox的IoU"""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0
```

---

## 9. 在线验证模块

### 9.1 验证策略

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| **Shadow** | 新模型接收生产流量副本，不返回结果 | 安全验证新模型 |
| **Canary** | 小部分流量路由到新模型 | 渐进式上线 |
| **A/B Test** | 50/50流量对比 | 严格效果对比 |

### 9.2 实现说明

在线验证依赖部署后的模型服务。当前设计为骨架，实际需与模型服务网关集成：

```python
# backend/app/engines/online_validation_runner.py

class OnlineValidationRunner:
    """在线验证执行器"""

    async def run_shadow_validation(
        self,
        deployment_id: str,
        duration_hours: int,
        sample_rate: float,
    ) -> dict[str, Any]:
        """
        执行影子验证。

        实际实现需与API网关集成，在网关层复制流量到验证模型。
        当前为设计骨架。
        """
        return {
            "validation_type": "shadow",
            "duration_hours": duration_hours,
            "sample_rate": sample_rate,
            "metrics": {
                "latency_p99_ms": 125,
                "throughput_qps": 28,
                "error_rate": 0.001,
            },
            "status": "completed",
        }
```

---

## 10. 实验追踪模块

### 10.1 实验数据模型

实验(Experiment)是一个逻辑容器，不直接执行任何操作。其核心价值在于：

1. **资源分组**：将同一目标下的多次训练、评测、部署关联
2. **对比分析**：横向对比不同超参数配置的效果
3. **报告导出**：生成完整的实验报告

### 10.2 实验对比实现

```python
# backend/app/services/experiment_service.py (建议新增)

class ExperimentService:
    """实验追踪服务"""

    async def get_experiment_comparison(self, experiment_id: str) -> dict[str, Any]:
        """获取实验下所有资源的对比数据"""
        # 1. 查询实验下所有训练任务
        training_jobs = await self._list_training_jobs(experiment_id)

        # 2. 查询关联的评测结果
        evaluations = await self._list_evaluations(experiment_id)

        # 3. 构建对比表
        comparison = {
            "experiment_id": experiment_id,
            "runs": [],
            "metric_comparison": {},
        }

        for job in training_jobs:
            job_evals = [e for e in evaluations if e.target_id == job.id]
            run_data = {
                "training_job": {
                    "id": job.id,
                    "name": job.name,
                    "hyperparameters": job.config_json.get("hyperparameters", {}),
                },
                "evaluations": [
                    {
                        "eval_set_name": e.eval_set_name,
                        "metrics": e.result_summary.get("metrics", {}),
                    }
                    for e in job_evals
                ],
            }
            comparison["runs"].append(run_data)

        # 4. 构建指标对比矩阵
        all_metrics = set()
        for run in comparison["runs"]:
            for eval in run["evaluations"]:
                all_metrics.update(eval["metrics"].keys())

        for metric in all_metrics:
            comparison["metric_comparison"][metric] = [
                {
                    "run_name": run["training_job"]["name"],
                    "value": next(
                        (e["metrics"].get(metric) for e in run["evaluations"]),
                        None,
                    ),
                }
                for run in comparison["runs"]
            ]

        return comparison
```

---

## 11. 模型部署模块

### 11.1 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                      检测Agent                                │
│  ┌─────────────┐                                            │
│  │  推理请求   │───┐                                        │
│  └─────────────┘   │                                        │
│                    ▼                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              模型服务网关 (vLLM/TGI)                 │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │  │ 模型v1.0 │  │ 模型v1.1 │  │ 模型v1.2 │          │   │
│  │  │ (部署A)  │  │ (部署B)  │  │ (部署C)  │          │   │
│  │  └──────────┘  └──────────┘  └──────────┘          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 11.2 部署管理器实现

```python
# backend/app/engines/deployment_manager.py

import asyncio
from typing import Any

from app.services.object_storage.factory import build_object_storage


class DeploymentManager:
    """模型部署管理器"""

    def __init__(self, org_id: str, user_id: str):
        self._org_id = org_id
        self._user_id = user_id
        self._storage = build_object_storage()

    async def deploy(
        self,
        *,
        deploy_id: str,
        source_type: str,
        source_id: str,
        service_config: dict[str, Any],
        hardware: dict[str, Any],
    ) -> dict[str, Any]:
        """
        部署模型为推理服务。

        当前为骨架实现，实际需集成：
        - 容器编排（K8s/Docker）
        - 模型服务框架（vLLM/Text Generation Inference）
        - 服务注册与发现
        """
        # 1. 获取模型权重路径
        model_path = await self._get_model_artifact(source_type, source_id)

        # 2. 准备服务配置
        service_name = f"model-{deploy_id}"

        # 3. 启动模型服务（模拟）
        await self._start_model_service(
            service_name=service_name,
            model_path=model_path,
            config=service_config,
            hardware=hardware,
        )

        # 4. 注册到检测Agent可用模型列表
        await self._register_model(
            deploy_id=deploy_id,
            service_name=service_name,
            endpoint=f"http://model-svc:8000/v1/models/{service_name}",
        )

        return {
            "service_name": service_name,
            "service_url": f"http://model-svc:8000/v1/models/{service_name}",
            "status": "running",
            "health_status": "healthy",
        }

    async def _get_model_artifact(self, source_type: str, source_id: str) -> str:
        """获取模型权重路径"""
        # 实际实现：查询训练/微调任务的result_summary.artifacts
        return f"minio://models/{self._org_id}/{source_type}/{source_id}/final.safetensors"

    async def _start_model_service(
        self,
        service_name: str,
        model_path: str,
        config: dict[str, Any],
        hardware: dict[str, Any],
    ) -> None:
        """启动模型服务容器"""
        # 实际实现：调用K8s API或Docker启动容器
        # 示例命令：
        # vllm serve {model_path} --tensor-parallel-size {gpu_count}
        await asyncio.sleep(1)  # 模拟启动时间

    async def _register_model(self, deploy_id: str, service_name: str, endpoint: str) -> None:
        """注册模型到检测Agent可用列表"""
        # 实际实现：更新model_configs表或专门的模型注册表
        # 使检测Agent可以在推理时选择此模型
        pass

    async def undeploy(self, deploy_id: str) -> None:
        """下线模型服务"""
        # 实际实现：停止容器、从注册表移除
        pass
```

### 11.3 与检测Agent的集成

部署后的模型需要被检测Agent调用。集成方式：

1. **模型注册**：部署完成后，在 `model_configs` 表中新增一条记录（或更新现有记录）
2. **健康检查**：复用现有的 `ModelHealthChecker` 定期检查部署模型服务健康状态
3. **动态路由**：检测Agent根据 `model_key` 或 `model_type` 选择可用模型

```python
# 部署完成后注册模型示例

async def _register_deployment_model(self, deploy_id: str, service_name: str, endpoint: str):
    """将部署的模型注册到平台模型配置中"""
    model_config = {
        "org_id": self._org_id,
        "provider": "internal",
        "model_key": service_name,
        "display_name": f"Deployed Model {deploy_id}",
        "endpoint": endpoint,
        "model_type": "multimodal",
        "is_active": True,
        "priority": 100,
    }
    # 调用 model_config_service.create_config()
```

---

## 12. 前端页面设计

### 12.1 页面清单

| 页面 | 路由 | 核心功能 |
|------|------|----------|
| 测试集管理 | `/ops/data/eval-sets` | 创建/编辑/查看测试集 |
| 训练任务列表 | `/ops/training/jobs` | 查看所有训练任务 |
| 训练任务详情 | `/ops/training/jobs/:id` | 查看指标、日志、产出物 |
| 微调管理 | `/ops/training/fine-tune` | 创建/管理微调任务 |
| 离线评测 | `/ops/eval/offline` | 创建/查看评测结果 |
| 在线验证 | `/ops/eval/online` | 创建/查看验证结果 |
| 实验追踪 | `/ops/experiments` | 实验列表、对比分析 |
| 模型部署 | `/ops/deployments` | 创建/管理/下线部署 |

### 12.2 训练任务详情页设计

```vue
<!-- frontend/src/views/ops/TrainingJobDetailView.vue -->
<template>
  <div class="training-job-detail">
    <!-- 头部信息 -->
    <el-page-header @back="$router.back()" :title="job.name">
      <template #extra>
        <el-tag :type="statusType">{{ job.status }}</el-tag>
        <el-button
          v-if="job.status === 'draft' || job.status === 'failed'"
          type="primary"
          @click="launchJob"
        >启动</el-button>
        <el-button
          v-if="job.status === 'queued' || job.status === 'running'"
          type="danger"
          @click="cancelJob"
        >取消</el-button>
      </template>
    </el-page-header>

    <!-- 基本信息卡片 -->
    <el-card class="info-card">
      <el-descriptions :column="2">
        <el-descriptions-item label="数据集">{{ datasetName }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ modelConfigName }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(job.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="执行模式">{{ job.execution_mode }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 指标图表 -->
    <el-card v-if="hasMetrics" class="metrics-card">
      <template #header>训练指标</template>
      <div ref="metricsChart" style="height: 300px;"></div>
    </el-card>

    <!-- 产出物列表 -->
    <el-card v-if="artifacts.length > 0" class="artifacts-card">
      <template #header>模型产出物</template>
      <el-table :data="artifacts">
        <el-table-column prop="type" label="类型" width="120" />
        <el-table-column prop="epoch" label="轮次" width="100" />
        <el-table-column prop="path" label="路径" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button link @click="downloadArtifact(row)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 日志查看器 -->
    <el-card class="logs-card">
      <template #header>训练日志</template>
      <pre class="log-viewer">{{ logs }}</pre>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { useTrainingStore } from '@/stores/training.store'

const route = useRoute()
const store = useTrainingStore()
const job = computed(() => store.currentJob)
const metricsChart = ref<HTMLDivElement>()

const statusType = computed(() => {
  const map: Record<string, string> = {
    completed: 'success',
    running: 'primary',
    failed: 'danger',
    cancelled: 'info',
    queued: 'warning',
    draft: 'info'
  }
  return map[job.value?.status] || 'info'
})

const hasMetrics = computed(() => {
  const summary = job.value?.result_summary
  return summary?.metrics && Object.keys(summary.metrics).length > 0
})

const artifacts = computed(() => {
  return job.value?.result_summary?.artifacts || []
})

const logs = computed(() => {
  return (job.value?.result_summary?.logs || []).join('\n')
})

onMounted(async () => {
  await store.fetchJob(route.params.id as string)
  if (hasMetrics.value && metricsChart.value) {
    renderMetricsChart()
  }
})

function renderMetricsChart() {
  const chart = echarts.init(metricsChart.value!)
  const metrics = job.value!.result_summary!.metrics
  const option = {
    tooltip: { trigger: 'axis' },
    legend: { data: Object.keys(metrics) },
    xAxis: { type: 'category', data: metrics.train_loss.map((_: number, i: number) => `Epoch ${i + 1}`) },
    yAxis: { type: 'value' },
    series: Object.entries(metrics).map(([name, data]) => ({
      name,
      type: 'line',
      data,
      smooth: true
    }))
  }
  chart.setOption(option)
}

async function launchJob() {
  await store.launchJob(job.value!.id)
}

async function cancelJob() {
  await store.cancelJob(job.value!.id)
}
</script>
```

### 12.3 实验对比页设计

```vue
<!-- frontend/src/views/ops/ExperimentCompareView.vue -->
<template>
  <div class="experiment-compare">
    <h2>实验对比: {{ experiment.name }}</h2>

    <!-- 超参数对比表 -->
    <el-card>
      <template #header>超参数对比</template>
      <el-table :data="hyperparameterComparison">
        <el-table-column prop="runName" label="运行" />
        <el-table-column prop="learningRate" label="学习率" />
        <el-table-column prop="batchSize" label="批次大小" />
        <el-table-column prop="epochs" label="轮数" />
      </el-table>
    </el-card>

    <!-- 指标对比图 -->
    <el-card>
      <template #header>指标对比</template>
      <div ref="comparisonChart" style="height: 400px;"></div>
    </el-card>
  </div>
</template>
```

### 12.4 Pinia Store设计

```typescript
// frontend/src/stores/training.store.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchTrainingJobs,
  fetchTrainingJob,
  createTrainingJob,
  launchTrainingJob,
  cancelTrainingJob,
  updateTrainingJob,
  deleteTrainingJob
} from '@/api/algo_workspace.api'

export const useTrainingStore = defineStore('training', () => {
  // State
  const jobs = ref<TrainingJob[]>([])
  const currentJob = ref<TrainingJob | null>(null)
  const loading = ref(false)
  const total = ref(0)

  // Getters
  const runningJobs = computed(() => jobs.value.filter(j => j.status === 'running'))
  const completedJobs = computed(() => jobs.value.filter(j => j.status === 'completed'))

  // Actions
  async function fetchJobs(params: ListParams = {}) {
    loading.value = true
    try {
      const res = await fetchTrainingJobs(params)
      jobs.value = res.items
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  async function fetchJob(id: string) {
    currentJob.value = await fetchTrainingJob(id)
  }

  async function createJob(payload: TrainingJobCreateRequest) {
    const job = await createTrainingJob(payload)
    jobs.value.unshift(job)
    return job
  }

  async function launchJob(id: string) {
    await launchTrainingJob(id)
    await fetchJob(id)
  }

  async function cancelJob(id: string) {
    await cancelTrainingJob(id)
    await fetchJob(id)
  }

  async function updateJob(id: string, payload: TrainingJobUpdateRequest) {
    await updateTrainingJob(id, payload)
    await fetchJob(id)
  }

  async function removeJob(id: string) {
    await deleteTrainingJob(id)
    jobs.value = jobs.value.filter(j => j.id !== id)
  }

  return {
    jobs,
    currentJob,
    loading,
    total,
    runningJobs,
    completedJobs,
    fetchJobs,
    fetchJob,
    createJob,
    launchJob,
    cancelJob,
    updateJob,
    removeJob
  }
})
```

---

## 13. 开发计划

### 13.1 里程碑规划

| 阶段 | 时间 | 交付物 | 依赖 |
|------|------|--------|------|
| **Phase 1** | 第1-2周 | 测试集管理 + 训练任务CRUD + 启动/取消 | 数据接入完成 |
| **Phase 2** | 第3周 | 微调管理 + 训练执行器骨架 | Phase 1 |
| **Phase 3** | 第4周 | 离线评测（指标计算） | Phase 2 |
| **Phase 4** | 第5周 | 模型部署（注册到Agent） | Phase 3 |
| **Phase 5** | 第6周 | 实验追踪 + 在线验证骨架 | Phase 4 |
| **Phase 6** | 第7周 | 前端页面 + 联调测试 | 全部 |

### 13.2 Phase 1 详细任务

#### 后端任务

| 任务ID | 任务 | 优先级 | 预估工时 | 依赖 |
|--------|------|--------|----------|------|
| BE-001 | 确认ORM模型已创建（algo_resources.py） | P0 | 1h | - |
| BE-002 | 实现测试集CRUD Service方法 | P0 | 4h | BE-001 |
| BE-003 | 实现训练任务CRUD + launch/cancel Service | P0 | 6h | BE-001 |
| BE-004 | 实现algo_workspace API路由（已有骨架） | P0 | 3h | BE-002, BE-003 |
| BE-005 | 实现测试集样本快照机制 | P0 | 4h | BE-002 |
| BE-006 | 集成Celery异步任务执行 | P1 | 4h | BE-003 |
| BE-007 | 实现训练执行器骨架（TrainingRunner） | P1 | 4h | BE-006 |

#### 前端任务

| 任务ID | 任务 | 优先级 | 预估工时 | 依赖 |
|--------|------|--------|----------|------|
| FE-001 | 创建训练/评测类型定义 | P0 | 2h | - |
| FE-002 | 封装algo_workspace API调用 | P0 | 3h | FE-001 |
| FE-003 | 实现Training Store | P0 | 3h | FE-002 |
| FE-004 | 开发测试集管理页面 | P0 | 4h | FE-003 |
| FE-005 | 开发训练任务列表页 | P0 | 4h | FE-003 |
| FE-006 | 开发训练任务详情页 | P0 | 6h | FE-005 |
| FE-007 | 开发实验追踪页面 | P1 | 4h | FE-003 |

### 13.3 技术风险与应对

| 风险 | 影响 | 概率 | 应对措施 |
|------|------|------|----------|
| GPU集群调度失败 | 训练任务无法执行 | 高 | 支持local_background降级执行、完善重试机制 |
| 模型权重文件过大 | MinIO上传/下载超时 | 中 | 分片传输、断点续传、压缩传输 |
| 评测指标计算复杂 | 评测任务执行慢 | 中 | 异步执行、缓存评测结果、增量评测 |
| 部署服务启动失败 | 模型无法上线 | 中 | 健康检查、自动回滚、蓝绿部署 |
| 训练框架未确定 | 执行器无法落地 | 高 | 先实现骨架，支持配置化替换训练命令 |

### 13.4 验收标准

#### 功能验收

- [ ] 能够创建/编辑/删除测试集，样本快照正确
- [ ] 能够创建/启动/取消训练任务
- [ ] 训练任务状态流转正确（draft -> queued -> running -> completed/failed）
- [ ] 能够创建微调任务并关联训练任务
- [ ] 能够创建/启动离线评测，计算Accuracy/F1/mAP/IoU/AR
- [ ] 能够部署模型并注册到检测Agent
- [ ] 能够创建实验并关联多个资源
- [ ] 能够查看实验对比和指标趋势

#### 性能验收

| 指标 | 目标值 |
|------|--------|
| 训练任务创建响应 | < 500ms |
| 测试集样本快照（1000条） | < 3s |
| 评测任务执行（1000样本） | < 5分钟 |
| 模型部署启动 | < 2分钟 |
| 页面加载（P95） | < 1s |

---

## 附录

### A. 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| 训练任务 | Training Job | 使用数据集训练模型的任务 |
| 微调 | Fine-tuning | 在已有训练基础上进行精细调整 |
| 测试集 | Evaluation Dataset | 用于评估模型性能的独立数据集 |
| 离线评测 | Offline Evaluation | 在测试集上批量评估模型 |
| 在线验证 | Online Validation | 对部署模型进行线上流量验证 |
| 实验 | Experiment | 组织多次训练/评测的逻辑分组 |
| 部署 | Deployment | 将模型发布为推理服务 |
| 影子验证 | Shadow Validation | 复制生产流量到新模型进行验证 |
| Checkpoint | Checkpoint | 训练过程中的模型权重快照 |
| mAP | mean Average Precision | 目标检测平均精度均值 |
| IoU | Intersection over Union | 边界框交并比 |
| AR | Average Recall | 平均召回率 |

### B. 参考资源

- **vLLM**: https://github.com/vllm-project/vllm
- **Text Generation Inference**: https://github.com/huggingface/text-generation-inference
- **PyTorch Distributed**: https://pytorch.org/docs/stable/distributed.html
- **COCO Evaluation**: https://github.com/cocodataset/cocoapi
- **ECharts**: https://echarts.apache.org/

### C. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1.0 | 2026-05-20 | AI Assistant | 初始版本，完成整体设计 |

---

> **文档结束**