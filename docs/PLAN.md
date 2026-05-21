# 数据接入文档覆盖差距与 MVP 落地方案

## 摘要
- 当前已完成的部分：数据集 CRUD、图片直传、文本录入、样本浏览、评测集/训练任务/微调管理骨架。
- 当前未完成的核心部分：一体化数据接入工作台、大文件分片上传、真实知识图谱构建、真实跨媒体对齐、真实数据增强、真实导出产物生成。
- 当前最大偏差：`数据处理`相关前后端虽然有路由和页面，但后端执行仍是占位骨架，`AlgoWorkspaceService` 只会生成示例实体/对齐/增强结果，未实现文档描述的算法流程。
- 本期范围已锁定：做`务实 MVP`，前端改成`数据接入一体化页`，图谱先`不引 Neo4j`，算法先做`规则 + 人工校正`，导出先做`VLM-JSON`，导出后由训练任务`人工选择产物`，结构化数据`不做`，上传要补`分片上传`。

## 未完成功能清单
- 数据接入主页面未收敛为文档中的一体化工作台，当前仍拆成`数据集列表/详情`和独立`数据处理`页。
- 文档要求的`分片上传 init/upload/complete`未实现，当前只有小批量图片直传和文本录入。
- 知识图谱缺少真实构建链路：实体抽取、关系抽取、状态分阶段进度、子图查询、统计摘要、图可视化数据接口都未完成。
- 跨媒体对齐缺少真实计算链路：样本特征构建、相似度计算、阈值/Top-K 策略、结果筛选、人工确认/拒绝流未完成。
- 数据增强缺少真实链路：建议生成、应用到数据集、历史记录、样本增强标记未完成。
- 数据导出缺少真实产物：当前没有可下载的训练数据包，也没有 VLM-JSON 组装、切分、对象存储落盘。
- 文档中的状态/统计能力未闭环：概览卡片、进度面板、处理结果摘要、导出结果和训练衔接都未达到设计目标。

## 实施方案
- 保留`/ops/data/import`作为数据集列表页；把`/ops/data/import/:id`改造成统一工作台，包含`概览 / 样本管理 / 知识图谱 / 跨媒体对齐 / 数据增强 / 导出`六个 Tab。
- 保留现有`/ops/data/processing`路由仅做兼容跳转，菜单中移除，避免“双入口”。
- 后端继续复用现有`/v1/datasets`与`/v1/algo-workspace`路由体系，不额外拆新的 `knowledge_graph.py/alignment.py/augmentation.py` 文件；但要把当前占位逻辑从 `AlgoWorkspaceService` 中拆到独立处理服务，`AlgoWorkspaceService` 只负责编排、权限和状态。
- 新增`dataset_upload_sessions`持久化分片上传会话；实现`/v1/datasets/{id}/upload/init`、`/upload/complete`，对象存储走现有 MinIO/本地存储抽象；小文件直传接口继续保留。
- 分片上传完成后触发`data_import`异步任务，负责解包、识别图片文件、生成样本记录、更新数据集统计；本期不做结构化数据导入。
- 知识图谱 MVP 不用 Neo4j；继续使用现有 MySQL 处理资源表和实体/关系表。抽取输入来自`sample_name + text_content + annotation_data + related_entities + source_metadata + 文件名`。
- 知识图谱抽取策略固定为规则优先：关键词词典、标签映射、模板关系、共现规则；人工新增/删除实体关系保留并前置到页面主操作流。
- 知识图谱状态接口改为真实返回`phase/progress/current_stats`；结果接口返回实体、关系、统计；补`subgraph`查询接口供前端 D3/ECharts 渲染。
- 跨媒体对齐 MVP 不做真实图像 embedding；统一把图片样本转成“描述文本”后与文本样本做文本 embedding 相似度。描述文本来源为文件名、标注标签、缺陷标签、样本名、元数据。
- 对齐计算优先使用一个激活的`embedding`模型配置；若无 embedding 模型，则退化到词项重叠/规则相似度并在结果摘要里标记`degraded_mode`。
- 对齐输出采用`threshold + top_k + mutual_check`固定策略；支持人工确认、删除、补录对齐对。
- 数据增强 MVP 只覆盖文本样本；实现`实体替换`和`关系推理`两种策略，先生成 proposals，再由用户选择应用。
- 应用增强时直接新增文本样本，并在样本元数据中写入`is_augmented / augmentation_source_id / augmentation_method / augmentation_params`；同时保留增强历史。
- 数据导出先只支持`VLM-JSON`；默认切分比例`0.7 / 0.15 / 0.15`，可配置；导出产物写入对象存储，生成下载 URL 和统计摘要。
- 导出完成后不自动发起训练，也不自动改写训练任务；只在 UI 上展示可复制/可选择的导出产物信息，交由训练任务手工引用。

## 公共接口与类型变更
- `Dataset`相关新增上传会话响应类型、上传完成后的导入任务状态类型。
- `processing status`统一返回`resource + latest_job + summary + phases + progress + warnings`，替换当前只有骨架 summary 的结果。
- 知识图谱接口补齐：`build/start`配置、`status`、`results`、`entities list/filter`、`relations create/delete`、`subgraph`。
- 对齐接口补齐：`start`配置、`status`、`results`筛选、`manual add/remove/confirm`。
- 增强接口补齐：`generate proposals`、`apply`、`history`。
- 导出接口补齐：`create export`、`status/results`中的下载地址、文件大小、样本统计。
- 样本模型补充增强标记字段；不在本期引入结构化样本类型，不引入 Neo4j 专属 schema。

## 测试与验收
- 后端测试覆盖：分片上传初始化/完成、导入后样本入库、规则抽取实体关系、对齐结果生成与手工修正、增强建议生成与应用、VLM-JSON 导出产物生成。
- 前端测试覆盖：一体化工作台 Tab 切换、处理任务轮询、图谱可视化加载、对齐筛选与确认、增强应用、导出下载展示、旧`/ops/data/processing`跳转兼容。
- 回归测试覆盖：现有数据集 CRUD、图片直传、文本录入、评测集创建、训练任务和微调管理不被本次改动破坏。
- 验收标准：用户能从一个数据集详情页完成上传、构建图谱、查看图谱、生成对齐、人工修正、生成增强、应用增强、导出 VLM-JSON，并把导出产物手动用于训练任务。

## 假设与默认
- 本期不做 Neo4j、OCR、专用视觉检测器集成，也不做真实图像 embedding。
- 本期不做结构化数据导入，不做 COCO/YOLO 导出，不做自动启动训练。
- 自动对齐和自动图谱构建都允许“降级模式”运行，但必须在状态摘要中明确标出降级原因。
- 现有对象存储、Celery、模型配置基础设施视为可复用能力，不另起新底座。
