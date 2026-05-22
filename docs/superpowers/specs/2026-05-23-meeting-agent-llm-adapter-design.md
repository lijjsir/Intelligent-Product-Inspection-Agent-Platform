# Meeting Room Agent — LLM Adapter 设计文档

> 日期: 2026-05-23 | 状态: draft

## 目标

在会议室聊天中引入 AI Agent 参与讨论。现阶段用 LLM 直调作为 agent 的占位实现，后续无缝切换到真实 agent pipeline。

支持两种触发方式：
- **@提及触发**：用户 `@Agent名称` 时唤醒对应 agent
- **自主参与**：Agent 根据策略（消息数/话题/计时器）主动发言

## 架构

```
MeetingService.send_message()
        │
        ├── @mention? ──→ MeetingAgentService.invoke_agent()
        └── 每条消息 ──→ MeetingAgentService.check_autonomous()
                                │
                                ▼
                       AgentAdapterFactory
                                │
              ┌─────────────────┼─────────────────┐
              ▼                                   ▼
     LLMAgentAdapter                      PipelineAgentAdapter
     (当前实现)                            (预留，后续接入)
              │
     MeetingAiService (改造)
              │
     DeepSeek / 其他 LLM API
```

## 数据模型

### 新表: `meeting_agent_definitions`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| org_id | UUID | 租户隔离 |
| name | String(64) | 显示名称 |
| system_prompt | Text | 人设 prompt |
| model | String(64) | 模型名，默认 deepseek-chat |
| adapter_type | String(32) | `llm` 或 `pipeline` |
| participation_strategy | JSON | 自主参与策略配置 |
| is_active | Boolean | 启用状态 |
| created_by | UUID | 创建者 |
| created_at/updated_at | DateTime | 时间戳 |

### participation_strategy JSON 结构

```json
{
  "auto_reply": true,
  "cooldown_seconds": 30,
  "strategies": {
    "message_count": { "enabled": true, "every_n_messages": 5 },
    "topic_match": { "enabled": false, "keywords": [] },
    "silence_timer": { "enabled": true, "after_seconds": 300 }
  }
}
```

### 现有表不变

- `meeting_room_agents.agent_id` → 引用 `meeting_agent_definitions.id`
- `meeting_messages` 的 `agent_id` 字段沿用

### 预置数据

迁移自动创建默认 agent：
- name: "AI 助手"
- adapter_type: `llm`
- system_prompt: 通用会议协作助手
- participation_strategy: message_count(每5条) + silence_timer(300s)

## Adapter 层

### 接口 (BaseAgentAdapter)

```python
class BaseAgentAdapter(ABC):
    async def invoke(room_id, agent_def, query, context) -> str
    async def should_participate(agent_def, messages_since_last, time_since_last, recent_content) -> bool
    async def generate_autonomous_reply(room_id, agent_def, recent_messages) -> str | None
```

### LLMAgentAdapter

- 构建消息列表：[system_prompt] + 房间最近N条消息 + 当前query
- 调用 LLM API（复用现有 DeepSeek 配置）
- 支持流式输出，通过 emit callback 推送 SSE
- should_participate 根据 participation_strategy 判断

### PipelineAgentAdapter（预留）

- 实现三个接口方法为空壳，raise NotImplementedError
- 后续接入真实 agent 时只需填充此类

## 触发流程

### @提及

1. 用户发送含 `@AgentName` 的消息
2. `MeetingService._parse_mentions()` 解析出 agent 名
3. 查找 `meeting_agent_definitions` + `meeting_room_agents` 验证 agent 在房间内
4. 通过 factory 获取 adapter，调用 `adapter.invoke()`
5. SSE 推流：agent_run_started → message_delta* → message_final
6. 保存回复到 meeting_messages (message_type="agent")

### 自主参与

1. 用户发送消息（无 @mention）后，触发后台 asyncio task
2. 遍历房间内所有 is_active 的 agent
3. 调用 `adapter.should_participate(messages_since_last, time_since_last, content)`
4. 返回 True 时调用 `adapter.generate_autonomous_reply()`
5. SSE 推流 → 保存消息
6. 冷却期内同一 agent 不会再次触发

## API 变更

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /v1/meetings/available-agent-defs | 列出可用 agent 定义 |
| POST | /v1/meetings/agent-defs | 创建自定义 agent（后续） |
| DELETE | /v1/meetings/agent-defs/{id} | 删除自定义 agent（后续） |

现有 meeting room agents CRUD 接口不变。

## 前端

- 房间 header 增加 "Agent 管理" 按钮，弹出 agent 列表 + 添加/移除操作
- 每个 agent 可切换自主参与开关
- Agent 消息 UI 保留现有蓝左边框样式，自主发言带 `[自主]` 标记
- Store 新增 `roomAgents`、`availableAgentDefs` 状态和相关 actions
- 流式接收 agent 回复，SSE 事件处理已有基础

## 降级

- LLM API 失败：agent 不发言，记录日志，不影响人类聊天
- Pipeline adapter 不可用：fallback 到 LLM adapter

## 迁移

- Migration `0053_add_meeting_agent_definitions`：建表 + 预置默认 agent

## 文件清单

### 新建
- `backend/agent/adapters/__init__.py`
- `backend/agent/adapters/base.py` — BaseAgentAdapter
- `backend/agent/adapters/llm_adapter.py` — LLMAgentAdapter
- `backend/agent/adapters/pipeline_adapter.py` — PipelineAgentAdapter
- `backend/agent/adapters/factory.py` — AgentAdapterFactory
- `backend/migrations/versions/0053_add_meeting_agent_definitions.py`

### 改造
- `backend/app/services/meeting_agent_service.py` — 使用 adapter 替代直接调 orchestrator
- `backend/app/services/meeting_ai_service.py` — 被 LLMAgentAdapter 调用，增强流式支持
- `backend/app/services/meeting_service.py` — send_message 后触发自主参与检查
- `backend/app/api/v1/meetings.py` — 新增 agent-defs 端点
- `backend/app/models/meeting.py` — 新增 MeetingAgentDefinition 模型
- `backend/app/schemas/meeting.py` — 新增 agent definition schema
- `frontend/src/stores/meeting.store.ts` — 新增 agent 管理状态
- `frontend/src/api/meeting.api.ts` — 新增 agent-defs API 调用
- `frontend/src/views/MeetingRoomView.vue` — 新增 agent 管理入口
