# 算法工程师 - 数据接入功能开发设计文档

> **版本**: v1.0  
> **日期**: 2026-05-20  
> **角色**: algorithm_engineer  
> **状态**: 设计阶段  

---

## 目录

1. [概述](#1-概述)
2. [业务场景与需求](#2-业务场景与需求)
3. [技术架构](#3-技术架构)
4. [数据库设计](#4-数据库设计)
5. [API接口设计](#5-api接口设计)
6. [知识图谱模块](#6-知识图谱模块)
7. [跨媒体对齐模块](#7-跨媒体对齐模块)
8. [数据增强模块](#8-数据增强模块)
9. [前端页面设计](#9-前端页面设计)
10. [开发计划](#10-开发计划)

---

## 1. 概述

### 1.1 功能定位

数据接入是算法工程师工作台的核心入口，提供**知识增强的多模态数据管理能力**，支持从原始数据到训练就绪数据的全流程处理。

### 1.2 核心能力矩阵

| 能力维度 | 功能点 | 优先级 |
|----------|--------|--------|
| **基础数据管理** | 数据集CRUD、上传下载、预览 | P0 |
| **知识图谱构建** | 实体抽取、关系抽取、图谱可视化 | P0 |
| **跨媒体对齐** | 图文自动对齐、质量评估 | P0 |
| **数据增强** | 基于图谱的数据增强 | P1 |
| **协作共享** | 团队共享、版本管理 | P2 |

### 1.3 目标用户

- **算法工程师**：负责模型微调、实验迭代
- **数据工程师**：负责数据清洗、标注
- **领域专家**：参与知识图谱审核、实体关系确认

---

## 2. 业务场景与需求

### 2.1 典型使用流程

```
┌─────────────────────────────────────────────────────────────┐
│                     算法工程师工作流                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1: 创建数据集                                          │
│    ├── 定义数据集名称、类型（图片/文本/多模态）               │
│    └── 选择存储位置（MinIO Bucket）                           │
│                                                             │
│  Step 2: 上传数据                                            │
│    ├── 上传产品检测图片                                      │
│    ├── 导入缺陷描述文本                                      │
│    └── 导入产品规格结构化数据                                │
│                                                             │
│  Step 3: 构建知识图谱                                        │
│    ├── 自动抽取实体（产品、缺陷、部件、标准）                 │
│    ├── 自动识别关系（has_defect, part_of, belongs_to）       │
│    └── 人工审核修正                                         │
│                                                             │
│  Step 4: 跨媒体对齐                                          │
│    ├── 图像-文本自动对齐                                     │
│    ├── 图像-实体关联                                         │
│    └── 对齐质量评估与调整                                    │
│                                                             │
│  Step 5: 数据优化（可选）                                    │
│    ├── 基于知识图谱的标注补全                                 │
│    ├── 实体替换生成新样本                                    │
│    └── 关系推理生成新样本                                    │
│                                                             │
│  Step 6: 导出训练数据                                        │
│    └── 支持COCO/YOLO/VLM-JSON等格式                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据类型定义

#### 2.2.1 图片数据

```yaml
字段说明:
  - source_type: 任务导入 / 用户上传 / OSS同步
  - format: JPEG/PNG/WebP/TIFF
  - annotation_format: COCO/YOLO/VLM-JSON
  - metadata:
      product_id: 产品ID
      capture_time: 拍摄时间
      camera_info: 相机参数
      defect_labels: 缺陷标签列表
```

#### 2.2.2 文本数据

```yaml
字段说明:
  - content_type: 描述/标准/指令/对话
  - language: zh/en/mixed
  - length: short(<100) / medium(100-1000) / long(>1000)
  - entities: 已标注的实体列表
```

#### 2.2.3 结构化数据

```yaml
字段说明:
  - schema: 产品属性表 / 缺陷分类表 / 标准规范表
  - fields: 字段定义
  - relationships: 外键关联
```

#### 2.2.4 知识图谱数据

```cypher
// Neo4j 节点类型
(:Product)        // 产品实体
(:Defect)         // 缺陷类型
(:Part)            // 部件组件
(:Standard)        // 检测标准
(:Material)        // 材质信息
(:Process)         // 工艺流程

// 关系类型
[:HAS_DEFECT]     // 产品包含缺陷
[:PART_OF]        // 部件属于产品
[:BELONGS_TO]     // 缺陷属于类别
[:REQUIRES]       // 检测需要标准
[:CAUSES]         // 工艺导致缺陷
```

---

## 3. 技术架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                             │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│   │ 数据集   │  │ 知识图谱 │  │ 跨媒体   │  │ 数据增强     │  │
│   │ 管理     │  │ 可视化   │  │ 对齐     │  │ 配置         │  │
│   └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI 后端服务                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Dataset API │  │ Knowledge   │  │ Alignment &             │ │
│  │ Service     │  │ Graph API   │  │ Augmentation API        │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    核心引擎层                               │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │  │
│  │  │ Entity       │  │ Cross-Media  │  │ Data           │  │  │
│  │  │ Extractor    │  │ Aligner      │  │ Augmentor      │  │  │
│  │  │ (LLM-based)  │  │ (CLIP/Embed) │  │ (KG-guided)    │  │  │
│  │  └──────────────┘  └──────────────┘  └────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │   MySQL     │     │    MinIO    │     │    Neo4j     │
   │  元数据/样本 │     │  图片/文件  │     │  知识图谱    │
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
| **UI组件库** | Element Plus | ^2.4 | 表格、表单、抽屉、图表 |
| **图表可视化** | ECharts + D3.js | ^5.4 | 力导向图（知识图谱）|
| **后端框架** | FastAPI | ^0.104 | 异步高性能API |
| **ORM** | SQLAlchemy | ^2.0 | 异步支持 |
| **关系数据库** | MySQL | 8.0+ | 存储元数据和样本索引 |
| **图数据库** | Neo4j | 5.x | 存储知识图谱 |
| **对象存储** | MinIO | latest | 存储图片和文件 |
| **任务队列** | Celery + Redis | 5.x | 异步任务处理 |
| **向量计算** | NumPy + PyTorch | latest | Embedding计算和对齐 |

### 3.3 目录结构规划

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── datasets.py              # 数据集API路由
│   │   ├── knowledge_graph.py       # 知识图谱API路由
│   │   ├── alignment.py             # 跨媒体对齐API路由
│   │   └── augmentation.py          # 数据增强API路由
│   │
│   ├── schemas/
│   │   ├── dataset.py               # 数据集Schema
│   │   ├── knowledge_graph.py       # 知识图谱Schema
│   │   ├── alignment.py             # 对齐Schema
│   │   └── augmentation.py          # 增强Schema
│   │
│   ├── services/
│   │   ├── dataset_service.py       # 数据集业务逻辑
│   │   ├── kg_service.py            # 知识图谱业务逻辑
│   │   ├── alignment_service.py     # 对齐业务逻辑
│   │   └── augmentation_service.py  # 增强业务逻辑
│   │
│   ├── repositories/
│   │   ├── dataset_repo.py          # 数据集Repository
│   │   └── sample_repo.py           # 样本Repository
│   │
│   ├── models/
│   │   ├── dataset.py               # 数据集模型
│   │   └── sample.py                # 样本模型
│   │
│   └── engines/
│       ├── entity_extractor.py      # 实体抽取引擎
│       ├── relation_extractor.py    # 关系抽取引擎
│       ├── cross_media_aligner.py   # 跨媒体对齐引擎
│       └── data_augmentor.py        # 数据增强引擎
│
├── agent/
│   └── llm/
│       └── health_checker.py        # 复用现有健康检查
│
frontend/src/
├── views/ops/
│   ├── DataImportView.vue           # 数据接入主页面
│   └── DatasetDetailView.vue        # 数据集详情页
│
├── components/business/data/
│   ├── DatasetList.vue              # 数据集列表组件
│   ├── SampleGallery.vue            # 样本画廊组件
│   ├── KnowledgeGraphViz.vue        # 知识图谱可视化
│   ├── AlignmentResult.vue          # 对齐结果展示
│   └── AugmentationPanel.vue        # 数据增强面板
│
├── stores/
│   └── dataset.store.ts             # 数据集Store
│
├── api/
│   ├── dataset.api.ts               # 数据集API封装
│   ├── knowledge_graph.api.ts       # 知识图谱API封装
│   ├── alignment.api.ts             # 对齐API封装
│   └── augmentation.api.ts          # 增强API封装
│
└── types/
    └── dataset.types.ts             # 类型定义
```

---

## 4. 数据库设计

### 4.1 MySQL 表设计

#### 4.1.1 datasets 表（数据集）

```sql
CREATE TABLE `datasets` (
    `id` VARCHAR(36) NOT NULL COMMENT 'UUIDv7主键',
    `org_id` VARCHAR(36) NOT NULL COMMENT '组织ID',
    `name` VARCHAR(255) NOT NULL COMMENT '数据集名称',
    `description` TEXT DEFAULT NULL COMMENT '数据集描述',
    
    -- 数据类型枚举
    `data_type` VARCHAR(50) NOT NULL 
        COMMENT 'image_only/text_only/multimodal/knowledge_graph',
    
    -- 存储信息
    `storage_bucket` VARCHAR(100) DEFAULT NULL COMMENT 'MinIO bucket名称',
    `storage_prefix` VARCHAR(500) DEFAULT NULL COMMENT 'MinIO路径前缀',
    
    -- 统计信息
    `sample_count` INT UNSIGNED DEFAULT 0 COMMENT '总样本数',
    `image_count` INT UNSIGNED DEFAULT 0 COMMENT '图片数量',
    `text_count` INT UNSIGNED DEFAULT 0 COMMENT '文本数量',
    `structured_count` INT UNSIGNED DEFAULT 0 COMMENT '结构化数据数量',
    
    -- 知识图谱关联
    `knowledge_graph_id` VARCHAR(36) DEFAULT NULL COMMENT '关联的知识图谱ID',
    `kg_status` VARCHAR(50) DEFAULT 'none' 
        COMMENT 'none/building/completed/failed',
    
    -- 对齐状态
    `alignment_status` VARCHAR(50) DEFAULT 'pending'
        COMMENT 'pending/processing/completed/failed',
    `alignment_progress` INT UNSIGNED DEFAULT 0 COMMENT '对齐进度 0-100',
    `alignment_stats` JSON DEFAULT NULL COMMENT '对齐统计信息',
    
    -- 增强状态
    `augmentation_enabled` BOOLEAN DEFAULT FALSE,
    `augmented_sample_count` INT UNSIGNED DEFAULT 0 COMMENT '已生成增强样本数',
    
    -- 状态与审计
    `status` VARCHAR(50) DEFAULT 'active' 
        COMMENT 'active/archived/deleted',
    `created_by` VARCHAR(36) NOT NULL COMMENT '创建者ID',
    `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    `deleted_at` DATETIME(3) DEFAULT NULL COMMENT '软删除时间',
    
    PRIMARY KEY (`id`),
    INDEX `idx_org_id` (`org_id`),
    INDEX `idx_data_type` (`data_type`),
    INDEX `idx_kg_id` (`knowledge_graph_id`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='数据集主表';
```

#### 4.1.2 dataset_samples 表（数据样本）

```sql
CREATE TABLE `dataset_samples` (
    `id` VARCHAR(36) NOT NULL COMMENT 'UUIDv7主键',
    `dataset_id` VARCHAR(36) NOT NULL COMMENT '所属数据集ID',
    
    -- 样本类型
    `sample_type` VARCHAR(50) NOT NULL 
        COMMENT 'image/text/pair/triple/structured',
    
    -- 存储路径（MinIO）
    `storage_path` VARCHAR(500) DEFAULT NULL COMMENT '文件在MinIO的完整路径',
    `file_size` BIGINT UNSIGNED DEFAULT 0 COMMENT '文件大小(bytes)',
    `mime_type` VARCHAR(100) DEFAULT NULL COMMENT 'MIME类型',
    `checksum` VARCHAR(64) DEFAULT NULL COMMENT 'SHA256校验和',
    
    -- 内容（小文本直接存，大文本存MinIO）
    `text_content` MEDIUMTEXT DEFAULT NULL COMMENT '文本内容（<16KB）',
    `text_storage_path` VARCHAR(500) DEFAULT NULL COMMENT '大文本的MinIO路径',
    
    -- 图片元数据
    `image_width` INT UNSIGNED DEFAULT NULL COMMENT '图片宽度(px)',
    `image_height` INT UNSIGNED DEFAULT NULL COMMENT '图片高度(px)',
    `image_channels` TINYINT UNSIGNED DEFAULT NULL COMMENT '通道数',
    
    -- 原始标注
    `annotation_data` JSON DEFAULT NULL COMMENT '原始标注数据(COCO/YOLO格式)',
    `metadata` JSON DEFAULT NULL COMMENT '扩展元数据',
    
    -- 对齐信息
    `embedding_vector_id` VARCHAR(36) DEFAULT NULL COMMENT '向量ID',
    `aligned_with` JSON DEFAULT NULL COMMENT '对齐的其他样本ID及相似度',
    `alignment_confidence` DECIMAL(5,4) DEFAULT NULL COMMENT '整体对齐置信度',
    
    -- 知识图谱关联
    `related_entities` JSON DEFAULT NULL COMMENT '关联的实体ID列表',
    `entity_mentions` JSON DEFAULT NULL COMMENT '实体提及位置(bounding box)',
    
    -- 数据增强标记
    `is_augmented` BOOLEAN DEFAULT FALSE COMMENT '是否为增强生成的样本',
    `augmentation_source_id` VARCHAR(36) DEFAULT NULL COMMENT '来源样本ID',
    `augmentation_method` VARCHAR(50) DEFAULT NULL COMMENT '增强方法',
    `augmentation_params` JSON DEFAULT NULL COMMENT '增强参数',
    
    -- 质量评分
    `quality_score` DECIMAL(3,2) DEFAULT NULL COMMENT '质量评分(0-1)',
    `quality_issues` JSON DEFAULT NULL COMMENT '质量问题列表',
    
    -- 审计
    `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    
    PRIMARY KEY (`id`),
    INDEX `idx_dataset_id` (`dataset_id`),
    INDEX `idx_sample_type` (`sample_type`),
    INDEX `idx_embedding` (`embedding_vector_id`),
    INDEX `idx_augmented` (`is_augmented`, `augmentation_source_id`),
    INDEX `idx_quality` (`quality_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='数据样本表';

-- 分区策略：按数据集分区，单表上限约1000万条
ALTER TABLE `dataset_samples` PARTITION BY HASH(`dataset_id`) PARTITIONS 16;
```

#### 4.1.3 knowledge_graphs 表（知识图谱元数据）

```sql
CREATE TABLE `knowledge_graphs` (
    `id` VARCHAR(36) NOT NULL COMMENT 'UUIDv7主键',
    `org_id` VARCHAR(36) NOT NULL COMMENT '组织ID',
    `name` VARCHAR(255) NOT NULL COMMENT '图谱名称',
    `description` TEXT DEFAULT NULL,
    
    -- Neo4j连接信息
    `neo4j_database` VARCHAR(100) DEFAULT 'neo4j' COMMENT 'Neo4j数据库名',
    `node_label_prefix` VARCHAR(50) DEFAULT '' COMMENT '节点Label前缀(用于隔离)',
    
    -- 统计信息
    `entity_count` INT UNSIGNED DEFAULT 0 COMMENT '实体总数',
    `relation_count` INT UNSIGNED DEFAULT 0 COMMENT '关系总数',
    `node_types` JSON DEFAULT NULL COMMENT '节点类型统计',
    `relation_types` JSON DEFAULT NULL COMMENT '关系类型统计',
    
    -- 构建配置
    `extraction_config` JSON DEFAULT NULL COMMENT '抽取配置(模型、阈值等)',
    `build_status` VARCHAR(50) DEFAULT 'idle' 
        COMMENT 'idle/running/completed/failed',
    `build_job_id` VARCHAR(36) DEFAULT NULL COMMENT '构建任务ID',
    `built_at` DATETIME(3) DEFAULT NULL COMMENT '完成时间',
    
    -- 审计
    `created_by` VARCHAR(36) NOT NULL,
    `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    
    PRIMARY KEY (`id`),
    INDEX `idx_org_id` (`org_id`),
    INDEX `idx_build_status` (`build_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='知识图谱元数据表';
```

#### 4.1.4 async_jobs 表（异步任务）

```sql
CREATE TABLE `async_jobs` (
    `id` VARCHAR(36) NOT NULL COMMENT 'UUIDv7主键',
    `job_type` VARCHAR(50) NOT NULL 
        COMMENT 'kg_build/alignment/augmentation/data_import',
    `resource_type` VARCHAR(50) NOT NULL COMMENT 'dataset/sample/kg',
    `resource_id` VARCHAR(36) NOT NULL COMMENT '资源ID',
    
    -- 状态
    `status` VARCHAR(50) DEFAULT 'pending' 
        COMMENT 'pending/running/completed/failed/cancelled',
    `progress` INT UNSIGNED DEFAULT 0 COMMENT '进度 0-100',
    
    -- 结果
    `result` JSON DEFAULT NULL COMMENT '执行结果',
    `error_message` TEXT DEFAULT NULL COMMENT '错误信息',
    `stack_trace` TEXT DEFAULT NULL COMMENT '异常堆栈',
    
    -- 配置
    `config` JSON DEFAULT NULL COMMENT '任务配置参数',
    `triggered_by` VARCHAR(36) NOT NULL COMMENT '触发者ID',
    
    -- 时间
    `started_at` DATETIME(3) DEFAULT NULL,
    `completed_at` DATETIME(3) DEFAULT NULL,
    `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    
    PRIMARY KEY (`id`),
    INDEX `idx_resource` (`resource_type`, `resource_id`),
    INDEX `idx_job_type` (`job_type`),
    INDEX `idx_status` (`status`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='异步任务表';
```

### 4.2 Neo4j Schema设计

#### 4.2.1 节点约束与索引

```cypher
-- 创建唯一约束
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.id IS UNIQUE;

-- 创建索引
CREATE INDEX entity_dataset_idx IF NOT EXISTS
FOR (e:Entity) ON (e.dataset_id);

CREATE INDEX entity_name_idx IF NOT EXISTS
FOR (e:Entity) ON (e.name);

CREATE INDEX entity_type_idx IF NOT EXISTS
FOR (e:Entity) ON (e.type);
```

#### 4.2.2 实体节点属性

```cypher
// 基础实体属性模板
{
    id: string,              // 全局唯一UUID
    dataset_id: string,      // 所属数据集ID
    name: string,            // 显示名称
    type: string,            // 实体类型(Product/Defect/Part/Standard/Material/Process)
    properties: map,         // 额外属性(根据type不同而不同)
    source: string,          // 来源(manual/extracted/inferred)
    confidence: float,       // 置信度(0-1)
    created_at: datetime,
    updated_at: datetime,
    
    // 统计信息
    mention_count: int,      // 在样本中的出现次数
    relation_count: int,     // 关联的关系数
}

// Product实体额外属性
{
    product_code: string,    // 产品编码
    category: string,        // 分类
    specifications: map,     // 规格参数
}

// Defect实体额外属性
{
    severity: string,        // 严重程度(critical/major/minor/trivial)
    common_causes: list,     // 常见原因
    detection_methods: list, // 检测方法
}
```

#### 4.2.3 关系边属性

```cypher
// 基础关系属性模板
{
    type: string,            // 关系类型(HAS_DEFECT/PART_OF/BELONGS_TO/REQUIRES/CAUSES)
    confidence: float,       // 置信度(0-1)
    source: string,          // 来源
    evidence: string,        // 证据(哪段文本/哪个图像区域)
    created_at: datetime,
    weight: float,           // 关系权重(用于图算法)
}

// 特殊关系示例
(:Product)-[:HAS_DEFECT {severity_weight: float}]->(:Defect)
(:Part)-[:PART_OF {quantity: int}]->(:Product)
(:Defect)-[:BELONGS_TO {category: string}]->(:DefectCategory)
(:Standard)-[:REQUIRES {mandatory: bool}]->(:InspectionMethod)
(:Process)-[:CAUSES {probability: float}]->(:Defect)
```

#### 4.2.4 实体-样本关联关系

```cypher
// 实体在样本中的出现记录
(:Entity)-[:APPEARS_IN {
    sample_id: string,       // 样本ID
    sample_type: string,     // image/text
    
    // 图片中出现的位置
    bbox: list,              // [x, y, width, height]
    confidence: float,       // 检测置信度
    
    // 文本中的出现位置
    start_offset: int,       // 文本起始偏移
    end_offset: int,         // 文本结束偏移
    mention_text: string,    // 提及的原文
    
    role: string,            // subject/object/attribute
}]->(:SampleRef)
```

---

## 5. API接口设计

### 5.1 接口规范

所有接口遵循统一的响应格式：

```json
{
    "code": 200,
    "message": "success",
    "data": {},
    "meta": {
        "request_id": "req_xxx",
        "timestamp": "2026-05-20T10:00:00Z"
    }
}
```

### 5.2 数据集管理API

#### 5.2.1 创建数据集

```http
POST /v1/datasets
Content-Type: application/json
Authorization: Bearer <token>

Request Body:
{
    "name": "电子产品缺陷检测数据集",
    "description": "包含手机、平板的外观缺陷图片及描述",
    "data_type": "multimodal",           // image_only | text_only | multimodal | knowledge_graph
    "storage_config": {
        "bucket": "piap-datasets",       // 可选，默认使用系统bucket
        "prefix": "org_001/dataset_001"
    },
    "tags": ["defect-detection", "electronics"]
}

Response 201:
{
    "code": 201,
    "message": "Dataset created successfully",
    "data": {
        "id": "01XXXXXXXXXXXXXXX",
        "name": "电子产品缺陷检测数据集",
        "data_type": "multimodal",
        "status": "active",
        "sample_count": 0,
        "storage_path": "minio://piap-datasets/org_001/dataset_001",
        "created_at": "2026-05-20T10:00:00Z"
    }
}
```

#### 5.2.2 获取数据集列表

```http
GET /v1/datasets?page=1&page_size=20&data_type=multimodal&status=active

Query Parameters:
- page: 页码(默认1)
- page_size: 每页数量(默认20, 最大100)
- data_type: 按数据类型筛选
- status: 按状态筛选(active/archived)
- search: 搜索关键词(匹配name/description)
- sort_by: 排序字段(created_at/name/sample_count)
- sort_order: asc/desc

Response 200:
{
    "code": 200,
    "data": [
        {
            "id": "01XXXXXXXXXXXXXXX",
            "name": "电子产品缺陷检测数据集",
            "description": "...",
            "data_type": "multimodal",
            "sample_count": 15000,
            "image_count": 12000,
            "text_count": 3000,
            "kg_status": "completed",
            "alignment_status": "completed",
            "status": "active",
            "created_at": "2026-05-20T10:00:00Z"
        }
    ],
    "meta": {
        "page": 1,
        "page_size": 20,
        "total": 15,
        "total_pages": 1
    }
}
```

#### 5.2.3 获取数据集详情

```http
GET /v1/datasets/{dataset_id}

Response 200:
{
    "code": 200,
    "data": {
        "id": "01XXXXXXXXXXXXXXX",
        "name": "电子产品缺陷检测数据集",
        "description": "...",
        
        // 基本信息
        "data_type": "multimodal",
        "status": "active",
        
        // 存储信息
        "storage_bucket": "piap-datasets",
        "storage_prefix": "org_001/dataset_001",
        
        // 统计信息
        "stats": {
            "total_samples": 15000,
            "images": 12000,
            "texts": 3000,
            "augmented_samples": 2000,
            "avg_image_size": "2.3MB",
            "total_storage": "35GB"
        },
        
        // 知识图谱状态
        "knowledge_graph": {
            "id": "kg_001",
            "status": "completed",
            "entity_count": 850,
            "relation_count": 2300,
            "last_built_at": "2026-05-19T15:30:00Z"
        },
        
        // 对齐状态
        "alignment": {
            "status": "completed",
            "progress": 100,
            "aligned_pairs": 9500,
            "avg_similarity": 0.82,
            "completed_at": "2026-05-19T16:00:00Z"
        },
        
        // 时间戳
        "created_by": "user_001",
        "created_at": "2026-05-18T09:00:00Z",
        "updated_at": "2026-05-19T16:00:00Z"
    }
}
```

#### 5.2.4 更新数据集

```http
PATCH /v1/datasets/{dataset_id}
Content-Type: application/json

Request Body:
{
    "name": "更新后的名称",
    "description": "更新后的描述",
    "tags": ["new-tag"]
}

Response 200:
{
    "code": 200,
    "message": "Dataset updated successfully",
    "data": { /* 更新后的完整数据集对象 */ }
}
```

#### 5.2.5 删除数据集

```http
DELETE /v1/datasets/{dataset_id}

Response 200:
{
    "code": 200,
    "message": "Dataset deleted successfully",
    "data": true
}
```

### 5.3 数据上传API

#### 5.3.1 初始化分片上传

```http
POST /v1/datasets/{dataset_id}/upload/init
Content-Type: application/json

Request Body:
{
    "filename": "batch_images.zip",
    "total_size": 1073741824,          // 1GB
    "chunk_size": 10485760,             // 10MB per chunk
    "content_type": "application/zip",
    "format": "auto"                    // auto | coco | yolo | vlm_json | csv
}

Response 200:
{
    "code": 200,
    "data": {
        "upload_id": "upload_xxx",
        "chunks_total": 103,            // ceil(total_size/chunk_size)
        "presigned_urls": [
            "https://minio.example.com/bucket?partNumber=1&signature=xxx",
            "https://minio.example.com/bucket?partNumber=2&signature=xxx",
            // ... 共 chunks_total 个URL
        ]
    }
}
```

#### 5.3.2 上传分片

```http
PUT {presigned_url_from_init}
Content-Type: application/octet-stream
Content-Length: 10485760

Body: <binary chunk data>

Response: 直接返回S3/MinIO的响应(204 No Content on success)
```

#### 5.3.3 完成上传

```http
POST /v1/datasets/{dataset_id}/upload/complete
Content-Type: application/json

Request Body:
{
    "upload_id": "upload_xxx",
    "parts": [
        {"part_number": 1, "etag": "\"etag1\""},
        {"part_number": 2, "etag": "\"etag2\""}
        // ... 所有分片的ETag
    ]
}

Response 200:
{
    "code": 200,
    "data": {
        "job_id": "job_xxx",            // 解压和处理任务的ID
        "estimated_files": 5000,         // 预估文件数
        "status": "processing"           // processing | completed
    }
}
```

#### 5.3.4 单条样本添加

```http
POST /v1/datasets/{dataset_id}/samples
Content-Type: application/json

Request Body:
{
    "sample_type": "pair",              // image | text | pair | triple | structured
    
    // 图片相关
    "image_base64": "/9j/4AAQ...",      // Base64编码的图片(或用image_url)
    "image_url": "https://example.com/image.jpg",  // 或外部URL
    
    // 文本相关
    "text_content": "屏幕右上角有划痕，长度约2cm",
    
    // 标注
    "annotations": {
        "defects": [
            {
                "label": "scratch",
                "bbox": [800, 50, 200, 80],  // x, y, w, h
                "attributes": {
                    "length": "2cm",
                    "severity": "minor"
                }
            }
        ]
    },
    
    // 元数据
    "metadata": {
        "product_id": "phone_model_a",
        "capture_date": "2026-05-15",
        "source": "manual_upload"
    }
}

Response 201:
{
    "code": 201,
    "data": {
        "id": "sample_xxx",
        "dataset_id": "dataset_xxx",
        "sample_type": "pair",
        "storage_path": "minio://bucket/path/sample_xxx.jpg",
        "created_at": "2026-05-20T10:05:00Z"
    }
}
```

### 5.4 知识图谱API

#### 5.4.1 构建知识图谱

```http
POST /v1/datasets/{dataset_id}/knowledge-graph/build
Content-Type: application/json

Request Body:
{
    // 实体抽取配置
    "entity_extraction": {
        "model": "default",              // 使用默认的LLM实体抽取模型
        "entity_types": ["Product", "Defect", "Part", "Standard", "Material"],
        "confidence_threshold": 0.7,     // 最低置信度
        "max_entities_per_sample": 20    // 每个样本最大实体数
    },
    
    // 关系抽取配置
    "relation_extraction": {
        "model": "default",
        "relation_types": [
            "HAS_DEFECT", "PART_OF", "BELONGS_TO", 
            "REQUIRES", "CAUSES", "SIMILAR_TO"
        ],
        "confidence_threshold": 0.65,
        "max_relations_per_entity": 10
    },
    
    // 高级选项
    "options": {
        "merge_similar_entities": true,  // 合并相似实体(模糊匹配)
        "similarity_threshold": 0.85,    // 合并阈值
        "infer_transitive": true,        // 推断传递关系(A->B, B=>A->C)
        "use_existing_kg": false          // 是否在已有图谱上增量构建
    }
}

Response 202:
{
    "code": 202,
    "data": {
        "job_id": "job_kg_build_xxx",
        "status": "running",
        "estimated_duration_seconds": 300,  // 预估耗时
        "message": "Knowledge graph construction started"
    }
}
```

#### 5.4.2 查询构建状态

```http
GET /v1/datasets/{dataset_id}/knowledge-graph/status

Response 200:
{
    "code": 200,
    "data": {
        "kg_id": "kg_001",
        "status": "running",              // idle | running | completed | failed
        "progress": 65,                   // 0-100
        
        // 当前阶段的详细信息
        "current_phase": "relation_extraction",
        "phases": [
            {
                "name": "text_parsing",
                "status": "completed",
                "duration_seconds": 45
            },
            {
                "name": "entity_extraction",
                "status": "completed",
                "duration_seconds": 120,
                "entities_found": 1250
            },
            {
                "name": "relation_extraction",
                "status": "running",
                "progress": 40,
                "relations_found": 890
            },
            {
                "name": "graph_optimization",
                "status": "pending"
            }
        ],
        
        // 已完成的统计
        "current_stats": {
            "entities": 1250,
            "relations": 890,
            "entity_types": {
                "Product": 350,
                "Defect": 420,
                "Part": 280,
                "Standard": 120,
                "Material": 80
            }
        },
        
        "started_at": "2026-05-20T10:00:00Z",
        "eta": "2026-05-20T10:05:30Z"
    }
}
```

#### 5.4.3 获取实体列表

```http
GET /v1/datasets/{dataset_id}/knowledge-graph/entities
    ?type=Defect
    &page=1
    &page_size=50
    &search=划痕
    &sort_by=mention_count
    &sort_order=desc

Query Parameters:
- type: 按实体类型筛选
- page, page_size: 分页
- search: 搜索实体名称
- sort_by: 排序字段(name/mention_count/relation_count/created_at)

Response 200:
{
    "code": 200,
    "data": {
        "items": [
            {
                "id": "entity_001",
                "name": "屏幕划痕",
                "type": "Defect",
                "properties": {
                    "severity": "minor",
                    "common_causes": ["摩擦碰撞", "尖锐物体接触"],
                    "detection_methods": ["目视检查", "机器视觉"]
                },
                "confidence": 0.92,
                "source": "extracted",
                
                // 统计信息
                "mention_count": 245,
                "relation_count": 12,
                "related_samples_count": 189,
                
                // 关联关系预览
                "relations_preview": [
                    {
                        "target": "手机屏幕",
                        "relation_type": "APPEARS_ON",
                        "confidence": 0.88
                    },
                    {
                        "target": "表面缺陷",
                        "relation_type": "BELONGS_TO",
                        "confidence": 0.95
                    }
                ],
                
                "created_at": "2026-05-20T10:02:00Z"
            }
        ],
        "total": 420,
        "page": 1,
        "page_size": 50
    }
}
```

#### 5.4.4 手动添加实体

```http
POST /v1/datasets/{dataset_id}/knowledge-graph/entities
Content-Type: application/json

Request Body:
{
    "name": "边框掉漆",
    "type": "Defect",
    "properties": {
        "severity": "major",
        "common_causes": ["磕碰", "涂层附着力不足"],
        "detection_methods": ["目视检查", "色差仪"]
    },
    "source": "manual"
}

Response 201:
{
    "code": 201,
    "data": {
        "id": "entity_manual_001",
        "name": "边框掉漆",
        "type": "Defect",
        "source": "manual",
        "created_at": "2026-05-20T11:00:00Z"
    }
}
```

#### 5.4.5 添加关系

```http
POST /v1/datasets/{dataset_id}/knowledge-graph/relations
Content-Type: application/json

Request Body:
{
    "source_entity_id": "entity_product_phone",
    "target_entity_id": "entity_defect_scratch",
    "relation_type": "HAS_DEFECT",
    "confidence": 1.0,
    "properties": {
        "frequency": "high",              // 出现频率
        "affected_batches": ["batch_001", "batch_003"]
    },
    "source": "manual",
    "evidence": "基于生产质检数据统计"
}

Response 201:
{
    "code": 201,
    "data": {
        "id": "rel_manual_001",
        "source": "entity_product_phone",
        "target": "entity_defect_scratch",
        "relation_type": "HAS_DEFECT",
        "created_at": "2026-05-20T11:05:00Z"
    }
}
```

#### 5.4.6 子图查询（用于前端可视化）

```http
POST /v1/datasets/{dataset_id}/knowledge-graph/subgraph
Content-Type: application/json

Request Body:
{
    "center_entity_id": "entity_defect_scratch",
    "depth": 2,                         // 跳数(1-3)
    "limit": 50,                        // 返回的最大节点数
    "include_node_properties": true,
    "include_relation_properties": true,
    "filters": {
        "entity_types": null,           // null表示不过滤
        "relation_types": null,
        "min_confidence": 0.5
    }
}

Response 200:
{
    "code": 200,
    "data": {
        "nodes": [
            {
                "id": "entity_defect_scratch",
                "label": "屏幕划痕",
                "type": "Defect",
                "properties": {...},
                "size": 45,              // 根据mention_count计算的显示大小
                "color": "#DC2626"       // 根据type分配的颜色
            },
            // ... 其他节点
        ],
        "edges": [
            {
                "source": "entity_defect_scratch",
                "target": "entity_product_phone",
                "label": "HAS_DEFECT",
                "type": "HAS_DEFECT",
                "weight": 0.88,
                "properties": {...}
            },
            // ... 其他边
        ],
        "statistics": {
            "total_nodes": 24,
            "total_edges": 56,
            "max_depth_reached": 2
        }
    }
}
```

### 5.5 跨媒体对齐API

#### 5.5.1 启动自动对齐

```http
POST /v1/datasets/{dataset_id}/alignment/start
Content-Type: application/json

Request Body:
{
    "alignment_type": "all",            // image_text | image_structured | all
    
    // 模型配置
    "model": {
        "vision_encoder": "clip-vit-base-patch32",  // 视觉编码器
        "text_encoder": "clip-text",                  // 文本编码器
        "embedding_dim": 512
    },
    
    // 对齐参数
    "parameters": {
        "similarity_threshold": 0.75,    // 匹配阈值
        "top_k": 5,                      // 每个样本最多返回k个对齐
        "batch_size": 64,                // 批处理大小
        "normalize_embeddings": true     // 归一化
    },
    
    // 对齐策略
    "strategy": "hybrid",               // nearest | cluster | graph_based | hybrid
    "use_knowledge_graph": true,        // 利用知识图谱辅助对齐
    "kg_weight": 0.3                    // 图谱权重(0-1)
}

Response 202:
{
    "code": 202,
    "data": {
        "job_id": "job_alignment_xxx",
        "status": "running",
        "estimated_duration_minutes": 15,
        "config_summary": {
            "total_images": 12000,
            "total_texts": 3000,
            "strategy": "hybrid",
            "model": "clip-vit-base-patch32"
        }
    }
}
```

#### 5.5.2 查询对齐状态

```http
GET /v1/datasets/{dataset_id}/alignment/status

Response 200:
{
    "code": 200,
    "data": {
        "job_id": "job_alignment_xxx",
        "status": "running",
        "progress": 68,
        
        // 各阶段进度
        "phases": [
            {
                "name": "image_encoding",
                "status": "completed",
                "processed": 12000,
                "total": 12000
            },
            {
                "name": "text_encoding",
                "status": "completed",
                "processed": 3000,
                "total": 3000
            },
            {
                "name": "similarity_computation",
                "status": "running",
                "progress": 55
            },
            {
                "name": "post_processing",
                "status": "pending"
            }
        ],
        
        // 中间统计
        "intermediate_stats": {
            "computed_pairs": 18000000,  // 12000 * 3000 * 0.5(近似)
            "above_threshold": 9500,
            "avg_similarity": 0.82
        },
        
        "started_at": "2026-05-20T10:00:00Z",
        "eta": "2026-05-20T10:08:00Z"
    }
}
```

#### 5.5.3 获取对齐结果

```http
GET /v1/datasets/{dataset_id}/alignment/results
    ?sample_id=img_001
    ?min_similarity=0.8
    ?page=1
    &page_size=20
    ?sort_by=similarity
    &sort_order=desc

Query Parameters:
- sample_id: 查询特定样本的对齐结果(可选)
- min_similarity: 最低相似度筛选
- aligned_type: 筛选对齐类型(image_text/image_entity)
- page, page_size: 分页

Response 200:
{
    "code": 200,
    "data": {
        "alignments": [
            {
                "source_sample": {
                    "id": "img_001",
                    "type": "image",
                    "preview_url": "/api/v1/datasets/xxx/samples/img_001/preview"
                },
                "targets": [
                    {
                        "sample_id": "txt_003",
                        "type": "text",
                        "content": "屏幕右上角有划痕...",
                        "similarity": 0.89,
                        "alignment_method": "embedding_nearest",
                        "shared_entities": ["entity_screen", "entity_scratch"],
                        "confidence": 0.92
                    },
                    {
                        "sample_id": "txt_007",
                        "type": "text",
                        "content": "显示屏表面损伤...",
                        "similarity": 0.84,
                        "alignment_method": "embedding_nearest",
                        "shared_entities": ["entity_display"],
                        "confidence": 0.87
                    }
                ]
            }
        ],
        
        // 统计摘要
        "summary": {
            "total_aligned_pairs": 9500,
            "avg_similarity": 0.82,
            "distribution": {
                "0.9-1.0": 2500,
                "0.8-0.9": 4000,
                "0.75-0.8": 3000
            },
            "unaligned_images": 1500,
            "unaligned_texts": 400
        },
        
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 9500
        }
    }
}
```

#### 5.5.4 手动添加/修改对齐

```http
POST /v1/datasets/{dataset_id}/alignment/manual
Content-Type: application/json

Request Body:
{
    "action": "add",                    // add | remove | update
    
    "alignment": {
        "source_sample_id": "img_001",
        "target_sample_id": "txt_003",
        "relation_type": "describes",    // describes | contains | references
        "similarity": 0.95,              // 人工确认的相似度
        "confidence": 1.0,               // 人工确认，置信度为1
        "notes": "经人工审核确认该图文对应"
    }
}

Response 200:
{
    "code": 200,
    "message": "Alignment updated successfully",
    "data": {
        "alignment_id": "align_manual_001",
        "status": "confirmed"
    }
}
```

### 5.6 数据增强API

#### 5.6.1 生成增强建议

```http
POST /v1/datasets/{dataset_id}/augmentation/generate-proposals
Content-Type: application/json

Request Body:
{
    // 增强策略选择
    "strategies": [
        {
            "name": "entity_substitution",     // 实体替换
            "enabled": true,
            "params": {
                "substitution_rate": 0.3,       // 替换比例
                "preserve_semantics": true,     // 保持语义一致性
                "diversity_constraint": 0.8     // 多样性约束
            }
        },
        {
            "name": "relation_inference",       // 关系推理
            "enabled": true,
            "params": {
                "max_inference_depth": 2,
                "confidence_threshold": 0.7
            }
        },
        {
            "name": "multi_view_generation",    // 多视角生成
            "enabled": false,
            "params": {}
        }
    ],
    
    // 生成控制
    "generation_control": {
        "target_proposals": 1000,              // 目标建议数
        "max_per_source_sample": 5,            // 每个源样本最多生成几个变体
        "validate_against_kg": true,           // 用知识图谱验证合理性
        "deduplicate": true                    // 去重
    },
    
    // 筛选条件(可选，只对部分数据生成)
    "filters": {
        "entity_types": ["Defect"],            // 只涉及特定实体的样本
        "min_quality_score": 0.7,              // 高质量样本才作为源
        "sample_ids": null                     // 指定样本ID列表
    }
}

Response 200:
{
    "code": 200,
    "data": {
        "proposal_batch_id": "batch_xxx",
        "total_proposals": 985,
        
        // 按策略分组统计
        "by_strategy": {
            "entity_substitution": 650,
            "relation_inference": 335
        },
        
        // 质量预估
        "quality_estimates": {
            "avg_predicted_quality": 0.82,
            "distribution": {
                "high_confidence(>0.9)": 320,
                "medium_confidence(0.7-0.9)": 480,
                "low_confidence(<0.7)": 185
            }
        },
        
        // 示例预览(前5条)
        "preview": [
            {
                "proposal_id": "prop_001",
                "source_sample_id": "src_img_001",
                "strategy": "entity_substitution",
                "changes": {
                    "original": "屏幕有划痕",
                    "generated": "边框有掉漆",
                    "substituted_entities": [
                        {"from": "屏幕", "to": "边框"},
                        {"from": "划痕", "to": "掉漆"}
                    ]
                },
                "predicted_quality": 0.88,
                "kg_validation_passed": true,
                "similar_existing_count": 2        // 与已有样本的相似度
            }
        ]
    }
}
```

#### 5.6.2 应用增强数据

```http
POST /v1/datasets/{dataset_id}/augmentation/apply
Content-Type: application/json

Request Body:
{
    "proposal_batch_id": "batch_xxx",
    
    // 选择要应用的提议
    "selected_proposal_ids": [
        "prop_001", "prop_002", "prop_005", ...
        // 可以全选或部分选择
    ],
    
    // 应用选项
    "options": {
        "add_to_dataset": true,           // 直接加入数据集
        "mark_as_augmented": true,        // 标记为增强数据
        "create_new_version": false,       // 是否创建数据集新版本
        "validation_level": "auto"        // none | auto | manual
    }
}

Response 202:
{
    "code": 202,
    "data": {
        "job_id": "job_apply_aug_xxx",
        "status": "processing",
        "selected_count": 750,
        "message": "Augmentation application started"
    }
}
```

#### 5.6.3 查询增强历史

```http
GET /v1/datasets/{dataset_id}/augmentation/history
    ?page=1
    &page_size=20

Response 200:
{
    "code": 200,
    "data": {
        "history": [
            {
                "batch_id": "batch_xxx",
                "applied_at": "2026-05-20T14:00:00Z",
                "applied_by": "user_algo_001",
                "proposals_selected": 750,
                "samples_created": 748,          // 可能有少量失败
                "strategies_used": ["entity_substitution", "relation_inference"],
                "quality_stats": {
                    "avg_quality": 0.83,
                    "min_quality": 0.71,
                    "max_quality": 0.96
                },
                "status": "completed"
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 5
        }
    }
}
```

### 5.7 数据导出API

#### 5.7.1 生成导出

```http
POST /v1/datasets/{dataset_id}/export
Content-Type: application/json

Request Body:
{
    "format": "vlm_json",                  // coco | yolo | vlm_json | raw | custom
    "include_augmented": true,             // 包含增强数据
    "include_knowledge_annotations": true, // 包含知识图谱标注
    "split_ratio": {                       // 数据划分比例
        "train": 0.7,
        "val": 0.15,
        "test": 0.15
    },
    "filters": {
        "sample_types": ["pair"],          // 只导出图文对
        "entity_types": ["Defect"],         // 只包含特定实体
        "min_quality_score": 0.7,
        "alignment_status": "completed"     // 只导出已完成对齐的
    },
    "options": {
        "compress": true,                  // 打包为zip
        "include_metadata": true,
        "custom_schema": null              // 自定义输出schema(JSON)
    }
}

Response 202:
{
    "code": 202,
    "data": {
        "export_id": "export_xxx",
        "download_url": null,               // 处理完成后会有值
        "status": "processing",
        "estimated_size_mb": 2500,          // 预估大小
        "expires_at": "2026-05-21T10:00:00Z" // 下载链接过期时间
    }
}
```

#### 5.7.2 查询导出状态

```http
GET /v1/datasets/{dataset_id}/export/{export_id}

Response 200:
{
    "code": 200,
    "data": {
        "export_id": "export_xxx",
        "status": "completed",
        "download_url": "https://minio.example.com/exports/export_xxx.zip?signature=xxx",
        "file_name": "dataset_001_vlm_json_20260520.zip",
        "file_size_bytes": 2580000000,
        "file_count": 15200,
        "format": "vlm_json",
        "statistics": {
            "train_samples": 10640,
            "val_samples": 2280,
            "test_samples": 2280,
            "includes_augmented": true,
            "augmented_count": 1480
        },
        "expires_at": "2026-05-21T10:00:00Z",
        "created_at": "2026-05-20T10:00:00Z"
    }
}
```

---

## 6. 知识图谱模块

### 6.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    知识图谱构建流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  输入层                                                      │
│  ├── 图片样本 → OCR → 文本                                  │
│  ├── 文本样本 → 直接使用                                    │
│  └── 结构化数据 → 转换为三元组                               │
│                                                             │
│  ↓                                                          │
│                                                             │
│  实体抽取层                                                  │
│  ├── LLM Prompt Engineering                                 │
│  │   └── "从以下文本中提取产品相关的实体..."                  │
│  ├── NER模型(可选)                                          │
│  │   └── BERT-NER / LLaMA-NER                              │
│  └── 规则匹配(补充)                                         │
│      └── 正则表达式 / 字典匹配                               │
│                                                             │
│  ↓                                                          │
│                                                             │
│  关系抽取层                                                  │
│  ├── LLM Relation Extraction                                │
│  │   └── "判断以下实体间是否存在关系..."                      │
│  ├── 模板匹配                                               │
│  │   └── "[EntityA] 具有 [EntityB] 缺陷" → HAS_DEFECT      │
│  └── 共现分析                                               │
│      └── 统计共现频率 → 候选关系                            │
│                                                             │
│  ↓                                                          │
│                                                             │
│  融合与优化层                                                │
│  ├── 实体消歧 & 合并                                        │
│  │   └── 字符串相似度 + 语义相似度 > 阈值 → 合并             │
│  ├── 关系去重                                                │
│  │   └── 同一实体对保留最高置信度                            │
│  └── 图谱补全                                                │
│      └── 传递闭包(A→B, B→C ⇒ A→C)                          │
│                                                             │
│  ↓                                                          │
│                                                             │
│  输出层                                                      │
│  └── 写入 Neo4j                                              │
│      ├── CREATE (:Entity {...})                              │
│      └── CREATE (a)-[r:{type}]->(b)                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 实体抽取引擎

#### 6.2.1 Prompt设计

```python
ENTITY_EXTRACTION_PROMPT = """你是一个专业的工业检测领域实体抽取专家。

## 任务
从给定的文本中抽取与产品检测相关的实体。

## 实体类型定义
{entity_type_definitions}

## 输入文本
{text}

## 输出格式（严格JSON）
{{
    "entities": [
        {{
            "name": "实体名称",
            "type": "实体类型",
            "confidence": 0.95,
            "span": [start_offset, end_offset],
            "context": "上下文片段"
        }}
    ]
}}

## 规则
1. 只抽取明确提到的实体，不要推测
2. 置信度反映抽取的确信程度
3. 实体名称使用原文中的表述
4. 如果没有找到实体，返回空数组
"""
```

#### 6.2.2 实体类型定义

```python
ENTITY_TYPE_DEFINITIONS = """
## Product（产品）
- 成品、半成品、零部件
- 例：iPhone 15 Pro、三星Galaxy S24、汽车发动机缸体

## Defect（缺陷）
- 外观缺陷、功能故障、性能不达标
- 例：划痕、裂纹、色差、漏液、异响

## Part（部件/部位）
- 产品的组成部分
- 例：屏幕、电池盖、摄像头模组、边框

## Standard（标准/规范）
- 检测标准、质量规范、行业标准
- 例：ISO 9001、GB/T 2828.1、企业内控标准Q/XXX-001

## Material（材料）
- 产品使用的材质
- 例：铝合金、钢化玻璃、聚碳酸酯(PC)、ABS塑料

## Process（工艺/工序）
- 生产工艺、检测工序
- 例：注塑成型、喷涂、CNC加工、AOI光学检测
"""
```

### 6.3 关系抽取引擎

#### 6.3.1 Prompt设计

```python
RELATION_EXTRACTION_PROMPT = """你是一个专业的工业领域知识图谱构建专家。

## 任务
判断给定的两个实体之间是否存在有意义的关系。

## 可用关系类型
{relation_type_definitions}

## 实体信息
- 实体A: {{entity_a_name}} (类型: {{entity_a_type}})
- 实体B: {{entity_b_name}} (类型: {{entity_b_type}})

## 上下文文本
{{context}}

## 输出格式（严格JSON）
{{
    "has_relation": true/false,
    "relation_type": "关系类型或null",
    "confidence": 0.0-1.0,
    "evidence": "支持该关系的原文证据",
    "reasoning": "简要推理过程"
}}

## 规则
1. 只有在上下文中有明确证据时才判断存在关系
2. 选择最具体的关系类型
3. 如果多个关系都适用，选择置信度最高的
4. 置信度应反映关系的确定性
"""
```

#### 6.3.2 关系类型定义

```python
RELATION_TYPE_DEFINITIONS = """
## HAS_DEFECT（具有缺陷）
- 产品/部件 → 缺陷
- 例：iPhone 15 Pro HAS_DEFECT 屏幕划痕

## PART_OF（组成部分）
- 部件 → 产品/更大部件
- 例：A17芯片 PART_OF iPhone 15 Pro

## BELONGS_TO（属于类别）
- 缺陷 → 缺陷类别
- 例：屏幕划痕 BELONGS_TO 外观缺陷

## REQUIRES（需要/遵循）
- 产品/工序 → 标准
- 例：外观检测 REQUIRES GB/T 2828.1

## CAUSES（导致/引起）
- 工艺/原因 → 缺陷
- 例：运输震动 CAUSES 屏幕裂纹

## SIMILAR_TO（相似于）
- 缺陷 ↔ 缺陷 / 产品 ↔ 产品
- 例：气泡 SIMILAR_TO 针孔

## LOCATED_AT（位于）
- 缺陷 → 部位
- 例：掉漆 LOCATED_AT 边框右下角

## DETECTED_BY（被...检测）
- 缺陷 → 检测方法
- 例：裂纹 DETECTED_BY 荧光渗透检测
"""
```

### 6.4 实体合并策略

```python
class EntityMerger:
    """实体消歧与合并"""
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.threshold = similarity_threshold
    
    def should_merge(self, entity_a: dict, entity_b: dict) -> tuple[bool, float]:
        """
        判断两个实体是否应该合并
        
        Returns:
            (should_merge, similarity_score)
        """
        # 1. 必须是相同类型
        if entity_a["type"] != entity_b["type"]:
            return False, 0.0
        
        # 2. 计算字符串相似度
        name_sim = self._string_similarity(
            entity_a["name"], 
            entity_b["name"]
        )
        
        # 3. 计算语义相似度（可选，调用Embedding模型）
        semantic_sim = self._semantic_similarity(
            entity_a["name"],
            entity_b["name"]
        )
        
        # 4. 加权综合得分
        final_sim = 0.6 * name_sim + 0.4 * semantic_sim
        
        return final_sim >= self.threshold, final_sim
    
    def merge(self, entities: list[dict]) -> list[dict]:
        """执行合并操作"""
        # 使用Union-Find算法进行聚类合并
        merged = []
        # ... 合并逻辑
        return merged
```

---

## 7. 跨媒体对齐模块

### 7.1 对齐算法流程

```
┌─────────────────────────────────────────────────────────────┐
│                   跨媒体自动对齐流程                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 1: 特征提取                                           │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │   图片特征提取   │    │   文本特征提取   │                │
│  │                 │    │                 │                │
│  │ CLIP ViT Encoder│    │ CLIP Text Enc   │                │
│  │ Output: 512-dim │    │ Output: 512-dim │                │
│  └────────┬────────┘    └────────┬────────┘                │
│           │                       │                         │
│           ▼                       ▼                         │
│     Image_Embeddings          Text_Embeddings               │
│     shape: (N, 512)           shape: (M, 512)              │
│                                                             │
│  Phase 2: 相似度计算                                         │
│  ┌─────────────────────────────────────────────┐           │
│  │         Similarity Matrix Computation        │           │
│  │                                             │           │
│  │  sim_matrix = cosine_similarity(             │           │
│  │      image_embeddings,                       │           │
│  │      text_embeddings                         │           │
│  │  )  # shape: (N, M)                         │           │
│  │                                             │           │
│  │  时间复杂度: O(N*M*D)                        │           │
│  │  优化: Faiss ANN 近似搜索                    │           │
│  └────────────────────┬────────────────────────┘           │
│                       │                                     │
│                       ▼                                     │
│              sim_matrix (N×M)                              │
│                                                             │
│  Phase 3: 匹配与后处理                                       │
│  ┌─────────────────────────────────────────────┐           │
│  │  1. 阈值过滤: sim > threshold (0.75)         │           │
│  │  2. Top-K选择: 每行保留K个最高分              │           │
│  │  3. 双向验证: mutual nearest neighbor        │           │
│  │  4. 知识图谱增强:                             │           │
│  │     - 共享实体加分                            │           │
│  │     - 关系约束过滤                            │           │
│  └────────────────────┬────────────────────────┘           │
│                       │                                     │
│                       ▼                                     │
│              Aligned Pairs List                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 核心实现

```python
import numpy as np
from typing import Optional
import faiss


class CrossMediaAligner:
    """跨媒体对齐器"""
    
    def __init__(
        self,
        vision_model: str = "openai/clip-vit-base-patch32",
        text_model: str = "openai/clip-vit-base-patch32",
        embedding_dim: int = 512,
        device: str = "cuda"
    ):
        self.embedding_dim = embedding_dim
        self.device = device
        
        # 初始化CLIP模型
        from transformers import CLIPModel, CLIPProcessor
        self.model = CLIPModel.from_pretrained(vision_model).to(device)
        self.processor = CLIPProcessor.from_pretrained(text_model)
        self.model.eval()
    
    def extract_image_features(
        self, 
        images: list[np.ndarray],  # PIL Images or numpy arrays
        batch_size: int = 64
    ) -> np.ndarray:
        """
        提取图片特征向量
        
        Args:
            images: 图片列表
            batch_size: 批处理大小
            
        Returns:
            embeddings: shape (N, embedding_dim), L2归一化
        """
        all_embeddings = []
        
        for i in range(0, len(images), batch_size):
            batch = images[i:i+batch_size]
            
            inputs = self.processor(
                images=batch, 
                return_tensors="pt", 
                padding=True
            ).to(self.device)
            
            with torch.no_grad():
                image_features = self.model.get_image_features(**inputs)
            
            # L2归一化
            features = torch.nn.functional.normalize(
                image_features, p=2, dim=-1
            )
            all_embeddings.append(features.cpu().numpy())
        
        return np.vstack(all_embeddings)
    
    def extract_text_features(
        self,
        texts: list[str],
        batch_size: int = 64
    ) -> np.ndarray:
        """
        提取文本特征向量
        
        Args:
            texts: 文本列表
            batch_size: 批处理大小
            
        Returns:
            embeddings: shape (M, embedding_dim), L2归一化
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            
            inputs = self.processor(
                text=batch, 
                return_tensors="pt", 
                padding=True, 
                truncation=True,
                max_length=77  # CLIP max length
            ).to(self.device)
            
            with torch.no_grad():
                text_features = self.model.get_text_features(**inputs)
            
            # L2归一化
            features = torch.nn.functional.normalize(
                text_features, p=2, dim=-1
            )
            all_embeddings.append(features.cpu().numpy())
        
        return np.vstack(all_embeddings)
    
    def compute_similarity_matrix(
        self,
        image_embeddings: np.ndarray,  # (N, D)
        text_embeddings: np.ndarray    # (M, D)
    ) -> np.ndarray:
        """
        计算图文相似度矩阵
        
        Returns:
            sim_matrix: shape (N, M), 值域 [-1, 1]
        """
        # 使用Faiss加速大规模计算
        index = faiss.IndexFlatIP(self.embedding_dim)  # 内积(归一化后=余弦)
        index.add(text_embeddings.astype('float32'))
        
        similarities, _ = index.search(
            image_embeddings.astype('float32'), 
            k=text_embeddings.shape[0]
        )
        
        return similarities
    
    def align(
        self,
        image_embeddings: np.ndarray,
        text_embeddings: np.ndarray,
        similarity_threshold: float = 0.75,
        top_k: int = 5,
        mutual_nn: bool = True
    ) -> list[dict]:
        """
        执行跨媒体对齐
        
        Args:
            similarity_threshold: 最低相似度阈值
            top_k: 每个图片最多匹配的文本数
            mutual_nn: 是否使用双向最近邻过滤
            
        Returns:
            alignments: 对齐结果列表
        """
        sim_matrix = self.compute_similarity_matrix(
            image_embeddings, 
            text_embeddings
        )
        
        alignments = []
        
        for img_idx in range(sim_matrix.shape[0]):
            scores = sim_matrix[img_idx]
            
            # 筛选高于阈值的匹配
            valid_mask = scores >= similarity_threshold
            if not valid_mask.any():
                continue
            
            # Top-K选择
            top_indices = np.argsort(scores[valid_mask])[-top_k:][::-1]
            
            for txt_idx in top_indices:
                txt_idx_global = np.where(valid_mask)[0][txt_idx]
                
                alignment = {
                    "image_index": img_idx,
                    "text_index": txt_idx_global,
                    "similarity": float(scores[txt_idx_global]),
                    "method": "embedding_nearest"
                }
                
                # 双向验证（可选）
                if mutual_nn:
                    reverse_scores = sim_matrix[:, txt_idx_global]
                    best_img_match = np.argmax(reverse_scores)
                    if best_img_match != img_idx:
                        continue
                
                alignments.append(alignment)
        
        return alignments


class KnowledgeGraphEnhancedAligner(CrossMediaAligner):
    """知识图谱增强的对齐器"""
    
    def __init__(self, kg_client, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kg_client = kg_client
    
    def enhance_with_kg(
        self,
        alignments: list[dict],
        image_entities: dict,   # {img_idx: [entity_ids]}
        text_entities: dict     # {txt_idx: [entity_ids]}
    ) -> list[dict]:
        """
        利用知识图谱增强对齐结果
        
        增强策略:
        1. 共享实体加分：如果图文共享实体，增加置信度
        2. 关系约束过滤：不符合关系的对齐降低分数
        3. 推理补充：基于关系推断新的对齐
        """
        enhanced = []
        
        for align in alignments:
            img_ents = set(image_entities.get(align["image_index"], []))
            txt_ents = set(text_entities.get(align["text_index"], []))
            
            # 计算共享实体比例
            shared = img_ents & txt_ents
            entity_boost = len(shared) / max(len(img_ents | txt_ents), 1)
            
            # 查询实体间的关系
            relation_score = self._query_entity_relations(shared)
            
            # 综合调整得分
            adjusted_sim = align["similarity"] * (1 + 0.1 * entity_boost + 0.05 * relation_score)
            adjusted_sim = min(adjusted_sim, 1.0)  # 上界为1
            
            align["similarity"] = round(adjusted_sim, 4)
            align["shared_entities"] = list(shared)
            align["kg_enhanced"] = True
            
            enhanced.append(align)
        
        return enhanced


# ──────────────────────────────────────────────
# 对齐质量评估
# ──────────────────────────────────────────────

def evaluate_alignment_quality(
    alignments: list[dict],
    ground_truth: Optional[list[tuple]] = None
) -> dict:
    """
    评估对齐质量
    
    Args:
        alignments: 预测的对齐结果
        ground_truth: 真实标注(可选)，格式 [(img_idx, txt_idx)]
    
    Returns:
        metrics: 评估指标字典
    """
    metrics = {
        "total_alignments": len(alignments),
        "avg_similarity": np.mean([a["similarity"] for a in alignments]),
        "similarity_distribution": {
            "high (>0.9)": sum(1 for a in alignments if a["similarity"] > 0.9),
            "medium (0.8-0.9)": sum(1 for a in alignments if 0.8 < a["similarity"] <= 0.9),
            "low (0.75-0.8)": sum(1 for a in alignments if 0.75 < a["similarity"] <= 0.8),
        }
    }
    
    if ground_truth is not None:
        predicted_set = {(a["image_index"], a["text_index"]) for a in alignments}
        gt_set = set(ground_truth)
        
        tp = len(predicted_set & gt_set)
        fp = len(predicted_set - gt_set)
        fn = len(gt_set - predicted_set)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        metrics.update({
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn
        })
    
    return metrics
```

---

## 8. 数据增强模块

### 8.1 增强策略架构

```
┌─────────────────────────────────────────────────────────────┐
│                   数据增强引擎架构                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Augmentation Orchestrator               │   │
│  │                                                     │   │
│  │  输入: 源样本 + 知识图谱 + 配置参数                  │   │
│  │  输出: 增强样本列表                                  │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│         ┌───────────────┼───────────────┐                   │
│         ▼               ▼               ▼                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Entity      │ │ Relation    │ │ Multi-View  │           │
│  │ Substitution│ │ Inference   │ │ Generation  │           │
│  │             │ │             │ │             │           │
│  │ 实体替换    │ │ 关系推理    │ │ 多视角生成  │           │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘           │
│         │               │               │                   │
│         ▼               ▼               ▼                   │
│  ┌─────────────────────────────────────────────────┐       │
│  │              Quality Validator                   │       │
│  │                                                 │       │
│  │  - 语义一致性检查                                 │       │
│  │  - 知识图谱验证                                   │       │
│  │  - 去重处理                                      │       │
│  │  - 质量评分                                       │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 实体替换策略

```python
class EntitySubstitutionAugmentor:
    """基于实体替换的数据增强"""
    
    def __init__(
        self,
        substitution_rate: float = 0.3,
        preserve_semantics: bool = True,
        diversity_constraint: float = 0.8
    ):
        self.substitution_rate = substitution_rate
        self.preserve_semantics = preserve_semantics
        self.diversity_constraint = diversity_constraint
    
    def generate_proposals(
        self,
        source_sample: dict,
        knowledge_graph: 'KnowledgeGraph',
        num_variants: int = 5
    ) -> list[dict]:
        """
        为单个源样本生成增强建议
        
        Args:
            source_sample: 包含 text_content 和 related_entities 的样本
            knowledge_graph: 知识图谱客户端
            num_variants: 生成的变体数量
            
        Returns:
            proposals: 增强建议列表
        """
        proposals = []
        entities = source_sample.get("related_entities", [])
        original_text = source_sample.get("text_content", "")
        
        if not entities or not original_text:
            return proposals
        
        # 获取每个实体的候选替换实体
        substitution_candidates = {}
        for entity_id in entities:
            entity = knowledge_graph.get_entity(entity_id)
            if not entity:
                continue
            
            # 查找同类型、同属性的相似实体
            candidates = knowledge_graph.find_similar_entities(
                entity_type=entity["type"],
                exclude_ids=[entity_id],
                limit=10
            )
            substitution_candidates[entity_id] = candidates
        
        # 生成多个变体
        import random
        for variant_idx in range(num_variants):
            substitutions = {}
            new_text = original_text
            
            # 随机选择要替换的实体
            entities_to_replace = random.sample(
                entities, 
                min(int(len(entities) * self.substitution_rate), len(entities))
            )
            
            for entity_id in entities_to_replace:
                entity = knowledge_graph.get_entity(entity_id)
                candidates = substitution_candidates.get(entity_id, [])
                
                if not candidates:
                    continue
                
                # 选择替换目标（考虑多样性）
                candidate = random.choice(candidates)
                
                # 执行替换
                old_name = entity["name"]
                new_name = candidate["name"]
                new_text = new_text.replace(old_name, new_name)
                
                substitutions[old_name] = new_name
            
            # 验证语义一致性
            if self.preserve_semantics:
                semantic_score = self._check_semantic_consistency(
                    original_text, new_text
                )
                if semantic_score < self.diversity_constraint:
                    continue
            
            proposal = {
                "source_sample_id": source_sample["id"],
                "strategy": "entity_substitution",
                "generated_text": new_text,
                "substitutions": substitutions,
                "predicted_quality": semantic_score,
                "substituted_entity_count": len(substitutions)
            }
            
            proposals.append(proposal)
        
        return proposals
    
    def _check_semantic_consistency(
        self, 
        original: str, 
        generated: str
    ) -> float:
        """
        检查生成文本与原文的语义一致性
        
        简化实现：使用编辑距离和关键词保留率
        """
        from difflib import SequenceMatcher
        
        # 编辑距离相似度
        edit_sim = SequenceMatcher(None, original, generated).ratio()
        
        # 关键词保留率（简化版）
        orig_words = set(original.split())
        gen_words = set(generated.split())
        keyword_overlap = len(orig_words & gen_words) / max(len(orig_words), 1)
        
        return 0.6 * edit_sim + 0.4 * keyword_overlap
```

### 8.3 关系推理策略

```python
class RelationInferenceAugmentor:
    """基于关系推理的数据增强"""
    
    def __init__(
        self,
        max_inference_depth: int = 2,
        confidence_threshold: float = 0.7
    ):
        self.max_depth = max_inference_depth
        self.confidence_threshold = confidence_threshold
    
    def infer_new_samples(
        self,
        existing_samples: list[dict],
        knowledge_graph: 'KnowledgeGraph'
    ) -> list[dict]:
        """
        基于已有样本和知识图谱推理新样本
        
        推理逻辑:
        - 如果 A HAS_DEFECT X，且 X SIMILAR_TO Y → A 可能 HAS_DEFECT Y
        - 如果 Part_A PART_OF Product，且 Product HAS_DEFECT D → Part_A 可能有D
        """
        new_samples = []
        
        for sample in existing_samples:
            entities = sample.get("related_entities", [])
            
            for entity_id in entities:
                entity = knowledge_graph.get_entity(entity_id)
                if not entity or entity.get("type") != "Defect":
                    continue
                
                # 查找相似的缺陷实体
                similar_defects = knowledge_graph.find_related_entities(
                    entity_id=entity_id,
                    relation_types=["SIMILAR_TO"],
                    depth=1
                )
                
                for similar_defect in similar_defects:
                    if similar_defect["confidence"] < self.confidence_threshold:
                        continue
                    
                    # 生成新描述
                    new_description = self._generate_variant_description(
                        original_desc=sample.get("text_content", ""),
                        original_defect=entity["name"],
                        new_defect=similar_defect["name"]
                    )
                    
                    new_sample = {
                        "source_sample_id": sample["id"],
                        "strategy": "relation_inference",
                        "generated_text": new_description,
                        "inference_path": [
                            entity["name"],
                            "SIMILAR_TO",
                            similar_defect["name"]
                        ],
                        "confidence": similar_defect["confidence"],
                        "reasoning": f"Based on similarity between {entity['name']} and {similar_defect['name']}"
                    }
                    
                    new_samples.append(new_sample)
        
        return new_samples
    
    def _generate_variant_description(
        self,
        original_desc: str,
        original_defect: str,
        new_defect: str
    ) -> str:
        """生成变体描述"""
        return original_desc.replace(original_defect, new_defect)
```

### 8.4 质量验证器

```python
class DataAugmentationValidator:
    """数据增强质量验证"""
    
    def __init__(self):
        pass
    
    def validate_batch(
        self,
        proposals: list[dict],
        knowledge_graph: 'KnowledgeGraph',
        existing_samples: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """
        验证一批增强提议
        
        Returns:
            (accepted, rejected): 通过/未通过的提议
        """
        accepted = []
        rejected = []
        
        # 构建现有样本的指纹用于去重
        existing_fingerprints = {
            self._fingerprint(s["text_content"]) 
            for s in existing_samples if s.get("text_content")
        }
        
        for proposal in proposals:
            issues = []
            quality_score = 1.0
            
            # 1. 去重检查
            fp = self._fingerprint(proposal.get("generated_text", ""))
            if fp in existing_fingerprints:
                issues.append("duplicate_of_existing")
                quality_score -= 0.3
            
            # 2. 知识图谱验证
            kg_valid = self._validate_with_kg(proposal, knowledge_graph)
            if not kg_valid:
                issues.append("kg_validation_failed")
                quality_score -= 0.2
            
            # 3. 内容质量检查
            content_issues = self._check_content_quality(proposal)
            issues.extend(content_issues)
            quality_score -= len(content_issues) * 0.1
            
            # 4. 最终判定
            proposal["quality_score"] = max(0, quality_score)
            proposal["validation_issues"] = issues
            
            if quality_score >= 0.5 and not any(
                i in ["duplicate_of_existing", "kg_validation_failed"] 
                for i in issues
            ):
                accepted.append(proposal)
            else:
                rejected.append(proposal)
        
        return accepted, rejected
    
    def _fingerprint(self, text: str) -> str:
        """生成文本指纹（简化版：使用hash）"""
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()[:16]
    
    def _validate_with_kg(self, proposal: dict, kg) -> bool:
        """用知识图谱验证增强结果的合理性"""
        # 检查生成的实体是否存在于图谱中
        # 检查推断的关系是否符合图谱约束
        # 实现略...
        return True
    
    def _check_content_quality(self, proposal: dict) -> list[str]:
        """检查内容质量问题"""
        issues = []
        text = proposal.get("generated_text", "")
        
        if len(text) < 10:
            issues.append("too_short")
        
        if len(text) > 10000:
            issues.append("too_long")
        
        # 检查是否有乱码或特殊字符
        # ...
        
        return issues
```

---

## 9. 前端页面设计

### 9.1 页面结构总览

```
数据接入主页面 (/ops/data/import)
│
├── 左侧导航（Tab切换）
│   ├── 📊 数据集概览
│   ├── 📁 样本管理
│   ├── 🔗 知识图谱
│   ├── 🔀 跨媒体对齐
│   └── ✨ 数据增强
│
└── 右侧主内容区
    └── 根据Tab显示不同内容
```

### 9.2 数据集概览 Tab

```vue
<!-- DatasetOverview.vue -->
<template>
  <div class="dataset-overview">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="mb-4">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>总样本数</template>
          <div class="stat-value">{{ stats.total_samples.toLocaleString() }}</div>
          <div class="stat-trend">+12% 较上周</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>图片数</template>
          <div class="stat-value">{{ stats.image_count.toLocaleString() }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>知识图谱</template>
          <div class="stat-value">{{ stats.entity_count }} 实体</div>
          <div class="stat-sub">{{ stats.relation_count }} 关系</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>对齐状态</template>
          <el-progress 
            :percentage="stats.alignment_progress" 
            :status="alignmentStatus"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作按钮组 -->
    <div class="action-bar mb-4">
      <el-button type="primary" @click="showUploadDialog = true">
        <el-icon><Upload /></el-icon> 上传数据
      </el-button>
      <el-button @click="handleBuildKG" :loading="kgBuilding">
        <el-icon><Connection /></el-icon> 构建知识图谱
      </el-button>
      <el-button @click="handleStartAlignment" :loading="aligning">
        <el-icon><Refresh /></el-icon> 启动对齐
      </el-button>
      <el-button type="success" @click="handleExport">
        <el-icon><Download /></el-icon> 导出数据集
      </el-button>
    </div>

    <!-- 处理进度面板 -->
    <el-card v-if="hasActiveJobs" class="mb-4">
      <template #header>处理任务</template>
      <div v-for="job in activeJobs" :key="job.id" class="job-item">
        <span>{{ job.type_label }}</span>
        <el-progress :percentage="job.progress" :status="job.status" />
      </div>
    </el-card>
  </div>
</template>
```

### 9.3 知识图谱可视化组件

```vue
<!-- KnowledgeGraphViz.vue -->
<template>
  <div class="knowledge-graph-viz">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="selectedEntityType" placeholder="筛选实体类型" clearable>
        <el-option label="全部" value="" />
        <el-option v-for="t in entityTypes" :key="t" :label="t" :value="t" />
      </el-select>
      
      <el-input 
        v-model="searchKeyword" 
        placeholder="搜索实体"
        clearable
        style="width: 200px"
      />
      
      <el-button-group>
        <el-button @click="zoomIn"><ZoomIn /></el-button>
        <el-button @click="zoomOut"><ZoomOut /></el-button>
        <el-button @click="fitView"><FullScreen /></el-button>
      </el-button-group>
    </div>

    <!-- 图谱画布 (使用D3.js力导向图) -->
    <div ref="graphContainer" class="graph-container">
      <svg ref="svgRef" width="100%" height="100%"></svg>
    </div>

    <!-- 实体详情侧边抽屉 -->
    <el-drawer v-model="entityDrawerVisible" title="实体详情" size="400px">
      <template v-if="selectedEntity">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="名称">
            {{ selectedEntity.name }}
          </el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag>{{ selectedEntity.type }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="置信度">
            {{ (selectedEntity.confidence * 100).toFixed(1) }}%
          </el-descriptions-item>
          <el-descriptions-item label="出现次数">
            {{ selectedEntity.mention_count }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 关系列表 -->
        <h4 class="mt-4">关联关系</h4>
        <el-table :data="selectedEntity.relations" size="small">
          <el-table-column prop="target_name" label="目标实体" />
          <el-table-column prop="relation_type" label="关系类型">
            <template #default="{ row }">
              <el-tag size="small">{{ row.relation_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="confidence" label="置信度" width="80">
            <template #default="{ row }">
              {{ (row.confidence * 100).toFixed(0) }}%
            </template>
          </el-table-column>
        </el-table>

        <!-- 出现的样本 -->
        <h4 class="mt-4">相关样本</h4>
        <div class="sample-list">
          <div 
            v-for="sample in selectedEntity.samples" 
            :key="sample.id"
            class="sample-item"
            @click="previewSample(sample)"
          >
            <img v-if="sample.type === 'image'" :src="sample.thumbnail" />
            <span v-else class="text-preview">{{ sample.content }}</span>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { useKnowledgeGraphApi } from '@/api/knowledge_graph.api'

const props = defineProps<{
  datasetId: string
}>()

// 状态
const graphContainer = ref<HTMLElement>()
const svgRef = ref<SVGSVGElement>()
const selectedEntity = ref<Entity | null>(null)
const entityDrawerVisible = ref(false)
const selectedEntityType = ref('')
const searchKeyword = ref('')

// 图谱数据
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const entityTypes = ref<string[]>([])

// D3力模拟
let simulation: d3.Simulation<any, undefined> | null = null

// 加载子图数据
async function loadSubgraph(centerEntityId?: string) {
  const res = await useKnowledgeGraphApi().getSubgraph(props.datasetId, {
    center_entity_id: centerEntityId,
    depth: 2,
    limit: 100
  })
  
  nodes.value = res.data.nodes
  edges.value = res.data.edges
  
  // 提取实体类型
  entityTypes.value = [...new Set(nodes.value.map(n => n.type))]
  
  renderGraph()
}

// 渲染力导向图
function renderGraph() {
  if (!svgRef.value || !graphContainer.value) return
  
  const container = graphContainer.value
  const width = container.clientWidth
  const height = container.clientHeight
  
  // 清空旧图形
  d3.select(svgRef.value).selectAll('*').remove()
  
  const svg = d3.select(svgRef.value)
    .attr('width', width)
    .attr('height', height)
  
  // 创建力模拟
  simulation = d3.forceSimulation(nodes.value as any)
    .force('link', d3.forceLink(edges.value as any)
      .id((d: any) => d.id)
      .distance(100))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(30))
  
  // 绘制连线
  const link = svg.append('g')
    .selectAll('line')
    .data(edges.value)
    .enter()
    .append('line')
    .attr('stroke', '#999')
    .attr('stroke-opacity', 0.6)
    .attr('stroke-width', (d: any) => Math.sqrt(d.weight * 5))
  
  // 绘制节点
  const node = svg.append('g')
    .selectAll('g')
    .data(nodes.value)
    .enter()
    .append('g')
    .call(d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended) as any)
  
  // 节点圆圈
  node.append('circle')
    .attr('r', (d: any) => Math.sqrt(d.size || 10) * 3)
    .attr('fill', (d: any) => d.color || '#2563A8')
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)
    .style('cursor', 'pointer')
    .on('click', (_event: Event, d: any) => {
      selectedEntity.value = d
      entityDrawerVisible.value = true
    })
  
  // 节点标签
  node.append('text')
    .text((d: any) => d.label?.slice(0, 8) || '')
    .attr('font-size', '10px')
    .attr('dx', 15)
    .attr('dy', 4)
  
  // 更新位置
  simulation.on('tick', () => {
    link
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y)
    
    node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
  })
}

function dragstarted(event: any, d: any) {
  if (!event.active) simulation!.alphaTarget(0.3).restart()
  d.fx = d.x
  d.fy = d.y
}

function dragged(event: any, d: any) {
  d.fx = event.x
  d.fy = event.y
}

function dragended(event: any, d: any) {
  if (!event.active) simulation!.alphaTarget(0)
  d.fx = null
  d.fy = null
}

// 缩放控制
function zoomIn() { /* ... */ }
function zoomOut() { /* ... */ }
function fitView() { /* ... */ }

// 预览样本
function previewSample(sample: any) { /* ... */ }

onMounted(() => loadSubgraph())
watch(selectedEntityType, () => loadSubgraph())
</script>

<style scoped>
.graph-container {
  width: 100%;
  height: calc(100vh - 250px);
  background: #fafafa;
  border-radius: 8px;
  overflow: hidden;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}
.sample-list {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.sample-item {
  cursor: pointer;
  border-radius: 4px;
  overflow: hidden;
}
.sample-item img {
  width: 100%;
  height: 60px;
  object-fit: cover;
}
.text-preview {
  font-size: 12px;
  padding: 8px;
  background: #f5f5f5;
}
</style>
```

### 9.4 对齐结果展示组件

```vue
<!-- AlignmentResult.vue -->
<template>
  <div class="alignment-result">
    <!-- 筛选工具栏 -->
    <el-row :gutter="16" class="filter-bar">
      <el-col :span="6">
        <el-slider 
          v-model="minSimilarity" 
          :min="0.5" 
          :max="1" 
          :step="0.05"
          show-input
        />
      </el-col>
      <el-col :span="6">
        <el-select v-model="sortBy" placeholder="排序方式">
          <el-option label="相似度降序" value="similarity_desc" />
          <el-option label="相似度升序" value="similarity_asc" />
        </el-select>
      </el-col>
    </el-row>

    <!-- 对齐结果网格 -->
    <div class="alignment-grid">
      <div 
        v-for="pair in filteredAlignments" 
        :key="`${pair.image_id}-${pair.text_id}`"
        class="alignment-pair"
        :class="{ highlighted: pair.similarity > 0.9 }"
      >
        <!-- 图片预览 -->
        <div class="image-side">
          <img :src="pair.image_preview" alt="" />
          <div class="similarity-badge" :style="{ backgroundColor: getSimColor(pair.similarity) }">
            {{ (pair.similarity * 100).toFixed(0) }}%
          </div>
        </div>
        
        <!-- 文本内容 -->
        <div class="text-side">
          <p class="text-content">{{ pair.text_content }}</p>
          
          <!-- 共享实体标签 -->
          <div class="entity-tags">
            <el-tag 
              v-for="ent in pair.shared_entities" 
              :key="ent.id"
              size="small"
              type="info"
            >
              {{ ent.name }}
            </el-tag>
          </div>
          
          <!-- 操作按钮 -->
          <div class="actions">
            <el-button 
              link 
              type="primary" 
              size="small"
              @click="confirmAlignment(pair)"
            >
              确认
            </el-button>
            <el-button 
              link 
              type="danger" 
              size="small"
              @click="rejectAlignment(pair)"
            >
              拒绝
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="page"
      :page-size="pageSize"
      :total="totalAlignments"
      layout="prev, pager, next"
      class="mt-4"
    />
  </div>
</template>
```

### 9.5 Store设计

```typescript
// stores/dataset.store.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { datasetApi } from '@/api/dataset.api'
import { knowledgeGraphApi } from '@/api/knowledge_graph.api'
import { alignmentApi } from '@/api/alignment.api'
import { augmentationApi } from '@/api/augmentation.api'
import type { Dataset, Sample, AlignmentPair, KGEntity } from '@/types/dataset.types'

export const useDatasetStore = defineStore('dataset', () => {
  // State
  const currentDataset = ref<Dataset | null>(null)
  const samples = ref<Sample[]>([])
  const loading = ref(false)
  
  // Knowledge Graph State
  const kgEntities = ref<KGEntity[]>([])
  const kgStatus = ref<'idle' | 'building' | 'completed' | 'failed'>('idle')
  const kgProgress = ref(0)
  
  // Alignment State
  const alignments = ref<AlignmentPair[]>([])
  const alignmentStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
  const alignmentProgress = ref(0)
  
  // Augmentation State
  const augmentationProposals = ref<any[]>([])
  
  // Getters
  const stats = computed(() => ({
    total_samples: samples.value.length,
    images: samples.value.filter(s => s.sample_type === 'image' || s.sample_type === 'pair').length,
    texts: samples.value.filter(s => s.sample_type === 'text' || s.sample_type === 'pair').length,
    entity_count: kgEntities.value.length,
    alignment_progress: alignmentProgress.value
  }))
  
  // Actions
  async function fetchDataset(id: string) {
    loading.value = true
    try {
      const { data } = await datasetApi.getDetail(id)
      currentDataset.value = data.data
    } finally {
      loading.value = false
    }
  }
  
  async function buildKnowledgeGraph(config: any) {
    kgStatus.value = 'building'
    const { data } = await knowledgeGraphApi.build(currentDataset.value!.id, config)
    
    // 轮询状态
    const pollInterval = setInterval(async () => {
      const statusRes = await knowledgeGraphApi.getStatus(currentDataset.value!.id)
      kgProgress.value = statusRes.data.data.progress
      
      if (statusRes.data.data.status !== 'running') {
        kgStatus.value = statusRes.data.data.status
        clearInterval(pollInterval)
        
        if (kgStatus.value === 'completed') {
          await fetchEntities()
        }
      }
    }, 3000)
  }
  
  async function startAlignment(config: any) {
    alignmentStatus.value = 'running'
    const { data } = await alignmentApi.start(currentDataset.value!.id, config)
    
    const pollInterval = setInterval(async () => {
      const statusRes = await alignmentApi.getStatus(currentDataset.value!.id)
      alignmentProgress.value = statusRes.data.data.progress
        
      if (statusRes.data.data.status !== 'running') {
        alignmentStatus.value = statusRes.data.data.status
        clearInterval(pollInterval)
        
        if (alignmentStatus.value === 'completed') {
          await fetchAlignments()
        }
      }
    }, 2000)
  }
  
  async function fetchEntities(params?: any) {
    const { data } = await knowledgeGraphApi.getEntities(currentDataset.value!.id, params)
    kgEntities.value = data.data.items
  }
  
  async function fetchAlignments(params?: any) {
    const { data } = await alignmentApi.getResults(currentDataset.value!.id, params)
    alignments.value = data.data.alignments
  }
  
  async function generateAugmentationProposals(config: any) {
    const { data } = await augmentationApi.generateProposals(currentDataset.value!.id, config)
    augmentationProposals.value = data.data.preview
  }
  
  return {
    currentDataset,
    samples,
    loading,
    kgEntities,
    kgStatus,
    kgProgress,
    alignments,
    alignmentStatus,
    alignmentProgress,
    augmentationProposals,
    stats,
    fetchDataset,
    buildKnowledgeGraph,
    startAlignment,
    fetchEntities,
    fetchAlignments,
    generateAugmentationProposals
  }
})
```

---

## 10. 开发计划

### 10.1 里程碑规划

| 阶段 | 时间 | 交付物 |
|------|------|--------|
| **Phase 1** | 第1-2周 | 数据集基础CRUD + MinIO上传下载 |
| **Phase 2** | 第3-4周 | 知识图谱构建（实体/关系抽取）|
| **Phase 3** | 第5周 | 跨媒体对齐（CLIP Embedding）|
| **Phase 4** | 第6周 | 数据增强（实体替换）|
| **Phase 5** | 第7周 | 前端页面完善 + 联调测试 |

### 10.2 Phase 1 详细任务

#### 后端任务

| 任务ID | 任务 | 优先级 | 预估工时 | 依赖 |
|--------|------|--------|----------|------|
| BE-001 | 创建数据库表(datasets/samples/async_jobs) | P0 | 4h | - |
| BE-002 | 实现Dataset Repository层 | P0 | 3h | BE-001 |
| BE-003 | 实现Dataset Service层 | P0 | 4h | BE-002 |
| BE-004 | 实现数据集CRUD API | P0 | 3h | BE-003 |
| BE-005 | 集成MinIO SDK | P0 | 2h | - |
| BE-006 | 实现分片上传接口 | P0 | 6h | BE-005 |
| BE-007 | 实现单条样本上传 | P1 | 3h | BE-004 |
| BE-008 | 实现数据预览接口 | P1 | 2h | BE-004 |

#### 前端任务

| 任务ID | 任务 | 优先级 | 预估工时 | 依赖 |
|--------|------|--------|----------|------|
| FE-001 | 创建数据集类型定义 | P0 | 1h | - |
| FE-002 | 封装数据集API调用 | P0 | 2h | FE-001 |
| FE-003 | 实现Dataset Store | P0 | 2h | FE-002 |
| FE-004 | 开发数据集列表页面 | P0 | 4h | FE-003 |
| FE-005 | 开发数据集详情页骨架 | P0 | 3h | FE-004 |
| FE-006 | 开发上传对话框组件 | P0 | 4h | FE-005 |
| FE-007 | 开发样本画廊组件 | P1 | 4h | FE-005 |

### 10.3 技术风险与应对

| 风险 | 影响 | 概率 | 应对措施 |
|------|------|------|----------|
| Neo4j性能瓶颈 | 大规模图谱查询慢 | 中 | 分片存储、索引优化、缓存热点查询 |
| CLIP模型显存占用 | GPU资源不足 | 高 | 使用CPU推理、批处理优化、模型量化 |
| LLM抽取成本高 | API费用超预算 | 中 | 本地部署小模型、缓存已抽取结果 |
| 大文件上传超时 | 网络不稳定导致失败 | 高 | 断点续传、重试机制、压缩传输 |

### 10.4 验收标准

#### 功能验收

- [ ] 能够创建/删除/查看数据集
- [ ] 支持分片上传大文件（>1GB）
- [ ] 能够构建知识图谱并可视化展示
- [ ] 能够执行图文自动对齐并查看结果
- [ ] 能够生成并应用数据增强

#### 性能验收

| 指标 | 目标值 |
|------|--------|
| 单个数据集最大样本数 | 100万条 |
| 图片上传速度 | >50MB/s |
| 知识图谱构建速度 | >100样本/秒 |
| 对齐计算速度 | >1000对/秒 |
| 页面响应时间 | <500ms(P95) |

---

## 附录

### A. 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| 数据集 | Dataset | 一组相关数据的集合，包含图片、文本等 |
| 样本 | Sample | 数据集中的单条记录（一张图/一段文本）|
| 知识图谱 | Knowledge Graph | 用图结构表示实体及其关系的知识库 |
| 实体 | Entity | 图中的节点，代表现实世界中的对象 |
| 关系 | Relation | 图中的边，连接两个实体 |
| 跨媒体对齐 | Cross-media Alignment | 建立不同模态数据间的对应关系 |
| 数据增强 | Data Augmentation | 通过变换生成新的训练样本 |
| 微调 | Fine-tuning | 在预训练模型基础上进行针对性训练 |

### B. 参考资源

- **LLaVA-Factory**: https://github.com/LLaMA-Factory/LLaVA-Factory
- **CLIP**: https://openai.com/research/clip
- **Neo4j Python Driver**: https://neo4j.com/docs/python-manual/current/
- **MinIO Python SDK**: https://docs.min.io/docs/python-client-api-reference.html
- **D3.js Force Layout**: https://github.com/d3/d3-force

### C. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1.0 | 2026-05-20 | AI Assistant | 初始版本，完成整体设计 |

---

> **文档结束**