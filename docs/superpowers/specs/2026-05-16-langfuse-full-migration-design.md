# Langfuse 完全迁移设计

日期: 2026-05-16 | 状态: 待实现

## 目标

将质量追踪（Quality Tracing）的数据源从 piap-mysql 的五张表完全迁移到 Langfuse API，实现：
- 读取：`list_traces` 通过 Langfuse REST API 获取数据
- 删除：通过 Langfuse API 删除 trace，同步清理本地
- 链接：修复 Langfuse URL 跳转
- 评测模型：使用数据库配置的模型

## 数据映射

### Langfuse Trace → QualityTraceItem

| QualityTraceItem 字段 | Langfuse 来源 |
|---|---|
| trace_id | trace.id |
| trace_url | 构造: `{public_host}/project/{project_id}/traces/{id}` |
| source_type | trace.tags → `source_type:inspection` 或 `source_type:chat` |
| verdict | trace.metadata.verdict |
| model_key | trace.metadata.model_key |
| created_at | trace.timestamp |
| task_id | trace.sessionId (inspection) 或 trace.metadata.task_id |
| session_id | trace.sessionId (chat) |
| trust_score | scores[?name=trust_score].value |
| hallucination_risk | scores[?name=hallucination_risk].value |
| overconfidence | scores[?name=overconfidence].value |
| total_tokens | observations[].usage.total |
| feedback_count | scores 中 name=user_feedback 的数量 |
| has_citation | scores[?name=has_citation].value |
| review_model | scores metadata 或 trace.metadata.review_model |

### API 调用

- **列表**：`GET /api/public/traces?tags=source_type:inspection&tags=org_id:xxx&limit=50&page=1`
- **详情**：`GET /api/public/traces/{traceId}` (按需，获取 observations 详情)
- **删除**：`DELETE /api/public/traces/{traceId}`

## 实现步骤

1. 补全 trace 创建时的 metadata 和 tags（source_type, verdict）
2. 改写 `QualityReportService.list_traces()` 使用 Langfuse API
3. 保留 `delete_trace` 已实现功能
4. 创建迁移脚本删除 piap-mysql 旧表
5. 清理废弃的 repository 查询代码
6. 测试验证

## 表清理

验证通过后删除：chat_message_scores, result_feedbacks, token_usage_ledger, stability_reports, inspection_results
