# tgg 分支：降级处理与写死数据排查清单

> 筛选原则：只记录会掩盖问题、让功能看似正常但实际退化，或本应动态获取却写死/模拟的数据。
> 未记录：有明确异常、明确状态事件、或业务上合理且可见的 failover。

## 一、需要优先处理的静默降级

| 优先级 | 位置 | 类型 | 当前行为 | 风险 | 建议 |
|---|---|---|---|---|---|
| P0 | `backend/agent/rag/retriever.py` | RAG 静默降级 | embedding 模型未配置时直接 `return []`；Qdrant HTTP 异常也 `return []` | RAG 坏了但表现为“没搜到资料”，开发时很难发现 | 改为抛出业务异常，或返回 `degraded=true + error_code` 并前端显式提示 |
| P0 | `backend/app/services/memory_vector_service.py` | 伪向量/静默失败 | 未接真实 embedding，使用 `_pseudo_embed()`；Qdrant 搜索 HTTP 异常返回空列表；删除异常直接 `pass` | 共享记忆检索结果不可信，且 Qdrant 故障不明显 | 接入统一 `Embedder`；Qdrant 异常写事件/告警；禁止生产使用 pseudo vector |
| P0 | `backend/app/services/rag_retrieval_service.py` | 非向量 RAG 兜底 | 结构化质检里的 RAG 检索不是查 Qdrant，而是读取 RAG 空间文件后做关键词 overlap；空间不存在也返回空 hits | 与主 RAG 实现不一致，容易误以为向量检索已生效 | 改名为 `LocalFileKeywordRetrievalService` 或接入统一 Retriever；空间不存在应报错 |
| P0 | `backend/app/services/task_execution_service.py` | Celery 静默降级 | 检测不到 Celery worker 时自动 `asyncio.create_task` 本地后台执行，返回 `local_background` | 部署时 worker 没启动也不会失败，任务执行方式被悄悄改变 | 开发环境可允许；生产环境应直接报错或需要显式开关 |
| P1 | `backend/app/services/dspy_runtime_service.py` | DSPy 配置降级 | org_id 非 UUID 或读取配置异常时返回空 targets，随后使用 builtin prompt | DSPy 配置表/迁移坏了会被隐藏，优化结果不生效但系统继续跑 | 配置读取异常应抛出或至少返回 `runtime_profile_degraded` |
| P1 | `backend/app/services/chat_trust_scoring_service.py` | 信任评分降级 | reviewer LLM 失败后切到 rule-only，并把规则分数伪装进 LLM 分数字段 | 质检可信度评分可能被高估/低估，且用户以为 LLM 评审已完成 | `rule_only` 必须前端显著展示；不要填充为 LLM 分数 |
| P1 | `backend/agent/llm/langfuse_tracer.py` | Trace/Score 静默降级 | Langfuse 不可用时返回 Noop observation；`get_trace_url()` 可能仍拼出 URL；score 同步失败只 warning 后返回未同步 payload | trace 链接可能看起来存在但实际无 trace；评测分数可能没同步 | 区分 `trace_url_generated` 与 `trace_synced`；同步失败进入告警 |
| P1 | `backend/app/services/file_storage_service.py` | 存储实现写死 | 实际只存本地 `runtime_uploads`，没有使用 S3/MinIO 配置 | 部署时误以为文件进了对象存储，容器重建/多实例时风险大 | 增加 storage backend 抽象；本地模式只允许 dev |

## 二、写死/模拟数据：本应动态获取

| 优先级 | 位置 | 写死内容 | 风险 | 建议 |
|---|---|---|---|---|
| P0 | `backend/agent/graphs/memory_manager/nodes.py` | 多个专业 Agent 节点直接返回 `status=completed`、空 findings、空 candidate_memories | 多 Agent 看起来跑通，但没有真实业务输出 | 未实现节点返回 `not_implemented`，不要返回 completed |
| P0 | `backend/agent/graphs/memory_manager/nodes.py` | `memory_context_loader` 不调用 MemoryService，只返回空 memory context | 共享记忆实际未进入主图上下文 | 接入 `MemoryService.search()`，失败显式报错 |
| P0 | `backend/agent/graphs/memory_manager/nodes.py` | `write_gate_node` 只按 source/scope 判断 active/isolated，trust_score 直接等于 confidence | 写入门控过于简单，和真实 MemoryService 策略不一致 | 删除图内伪门控，只委托 MemoryService |
| P0 | `backend/agent/graphs/memory_manager/nodes.py` | 污染检测阈值 `trust_score < 0.4`、回滚策略 direct=isolate/indirect=degrade、评测指标固定 | 治理闭环像是生效，实则是规则演示 | 改成策略表配置；未配置则报错或标记 mock |
| P1 | `backend/app/services/agent_ops_service.py` | DSPy compile 只是 sleep 后生成 system prompt；metrics 用 target_key 字符求 seed 伪造 | Prompt 优化结果不是实际编译/评测结果 | compile 前端标注 mock；接入真实数据集和评测任务 |
| P1 | `backend/agent/topology_catalog.py` | 子图注册、节点、边、DSPy targets 全部写死在代码里 | 前端拓扑和真实 LangGraph 可能不一致 | 从实际 graph 构建/数据库配置生成拓扑 |
| P1 | `backend/agent/subgraphs/quality_judgement/product_adapters.py` | 默认标准号 `FOOD-RAG-BASE-V1`、`SCREW-A-2026-V1`、`ELEC-RAG-BASE-V1`；大量食品/电子/螺丝规则、阈值、置信度写死 | 检测标准绕过数据库，产品类型扩展困难 | 迁移到 `inspection_specs` 或规则配置表 |
| P1 | `backend/agent/subgraphs/quality_judgement/product_adapters.py` | `score_from_record()` 无缺陷直接 0.96，有缺陷按固定公式扣分 | 评分不是模型/标准/历史统计得出 | 从标准门禁、缺陷严重度、模型置信度综合计算 |
| P1 | `backend/agent/subgraphs/quality_judgement/graph.py` | 缺失字段默认 `product_id/spec_code`，图片要求默认 true；review gate 默认阈值 0.85/0.9 | 未配置 DSPy 时仍按固定策略跑 | 配置缺失应显式提示；阈值进入配置表 |
| P1 | `backend/agent/subgraphs/quality_judgement/graph.py` | 质量指标写死：pass faithfulness=0.94，否则 0.71；physical_hallucination=0.08/0.29；token_usage=0 | 质量报告、成本统计、稳定性分析失真 | 由真实评测/LLM usage/trace 计算 |
| P1 | `backend/agent/graph/nodes/planner.py` | 旧检测图计划固定为 `vision → knowledge → reasoning → finalize` | Agent 看起来可规划，但实际上没有动态规划 | 从任务类型、标准、图片/文件条件生成计划 |
| P2 | `backend/app/services/inspection_pipeline_service.py` | `prompt_version="phase3-v1"`、`tokens_used=0`、`latency_ms=None`、缺失结论时默认 `overall_score=0.5` | 报表和追踪数据不真实 | 使用 LLM meta、trace、实际耗时填充 |
| P2 | `frontend/src/router/routes/*.ts` | 大量页面挂 `PlaceholderPage.vue`，例如记忆治理、角色菜单、审计日志、DSPy 优化等 | 菜单可见但功能未实现 | 未实现页面隐藏，或标注 beta/mock 并禁用入口 |

## 三、建议的统一改法

1. 增加统一降级结构：`degraded: true`、`degrade_reason`、`error_code`、`fallback_source`、`visible_to_user`。
2. 生产环境禁止静默 fallback：通过 `PIAP_ALLOW_DEV_FALLBACKS=false` 控制。
3. 对 RAG、Memory、Langfuse、Celery、DSPy 增加启动健康检查，失败直接阻止相关功能入口。
4. mock/placeholder 必须显式命名：`MockDSPyCompiler`、`PseudoMemoryVectorService`、`PlaceholderAgentNode`。
5. 关键指标禁止默认值污染报表：tokens、latency、trust score、faithfulness、hallucination score 缺失时应显示 `null/unavailable`，不要填 0 或固定值。
6. 前端对 `rule_only`、`qdrant_degraded`、`rag_empty_due_to_error`、`local_background` 等状态做醒目标识。这个直接在对应前端页面小弹窗显示
