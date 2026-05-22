# 聊天 Agent 系统的轻量化高效率优化方案

> 适用分支：`develop`  
> 适用目标：用户每次聊天都必须进入大模型驱动的 Agent 系统。  
> 核心原则：**不减少大模型调用，而是减少重复初始化、重复上下文、重复落库、重复推送和无效轮询。**

---

## 1. 优化边界

本方案不建议把“你好”“你是谁”“确认”“取消”等简单输入改成本地规则直接回复，因为当前目标是构建聊天 Agent 系统。  
因此，每次用户发起聊天时，都应保留如下基本路径：

```text
用户消息
→ ChatService 创建本轮消息
→ 管理 Agent / 路由 Agent 判断执行路径
→ Chat Agent / RAG Agent / Inspection Agent 执行
→ 至少一次 LLM 调用生成最终自然语言回复
→ 统一 finalizer 落库并推送前端
```

轻量化优化只处理链路中的低效部分，不改变“每轮聊天必须调用大模型”的原则。

---

## 2. 推荐的轻量化总体结构

```text
ChatService
  - 每个请求可新建，保持轻量
  - 不持有重型 Graph 状态

QualityAgentOrchestratorService
  - 可做进程级轻量复用
  - 只负责调度和统一结果处理

AgentManager
  - 进程级复用
  - 内部懒加载 ChatGraph / InspectionTaskGraph

QualityChatGraph / InspectionTaskGraph
  - 编译结构复用
  - 每轮请求状态通过 state/request 传入

LLMClient / DB session / trace / emit
  - 每轮请求新建
  - 不做全局复用
```

重点是：**复用结构，不复用请求状态。**

---

## 3. 第一优先级：低风险、高收益修复

### 3.1 修复 SSE 消息重复消费

前端 `chat.api.ts` 中如果同时存在：

```ts
source.onmessage = consume;
source.addEventListener("message", consume as EventListener);
```

应只保留一种。推荐：

```ts
source.onmessage = consume;
```

否则同一个 SSE message 可能被处理两次，导致流式回答重复拼接、最终消息重复刷新。

---

### 3.2 统一 finalizer，避免双重落库和双重 message_final

当前链路中，Graph finalizer 和 Orchestrator 持久化逻辑都可能更新 assistant message、写日志并发送 `message_final`。

建议选择一种职责边界：

```text
推荐边界：
Graph：负责执行 Agent 逻辑、调用 LLM、生成 response_payload。
Orchestrator：负责统一落库、写日志、推送 message_final。
```

这样后续接入更多 Agent 时，所有结果都能走同一套生命周期管理。

---

### 3.3 history_loader 排除本轮用户消息

正确上下文应是：

```text
history = 本轮用户消息之前的历史
query = 本轮用户刚发的消息
```

不要让本轮 query 同时出现在 history 和 current query 中。

推荐在创建消息后，把本轮 user message 的 `seq_no` 写入 workflow state：

```py
"current_user_seq_no": user_message.seq_no,
"assistant_message_seq_no": assistant_message.seq_no,
```

然后 `history_loader` 使用：

```py
history_rows = [
    row for row in rows
    if row.seq_no < current_user_seq_no
]
```

这样历史仍然起作用，但不会重复当前问题。

---

## 4. 轻量化 Agent / Graph 复用

### 4.1 只复用 AgentManager

当前 `AgentManager` 内部已经有懒加载设计：

```py
self._chat_agent = None
self._task_agent = None
```

因此不需要复杂框架，只需要让 `AgentManager` 本身在进程内复用。

新增一个轻量 provider：

```py
# backend/agent/router/manager_provider.py

from functools import lru_cache
from agent.router import AgentManager

@lru_cache(maxsize=1)
def get_agent_manager() -> AgentManager:
    return AgentManager()
```

然后修改 `AgentManagerService`：

```py
from agent.router.manager_provider import get_agent_manager

class AgentManagerService:
    def __init__(self) -> None:
        self._manager = get_agent_manager()
```

### 4.2 可以复用的对象

```text
AgentManager
AgentRoutePolicy
QualityChatGraph 编译结构
InspectionTaskGraph 编译结构
PromptBuilder 静态规则
```

### 4.3 不应复用的对象

```text
CurrentUser
NormalizedRequest
db_session
LLMClient
trace_id / workflow_run_id
RAG Retriever 中带 trace 的实例
本轮 emit 回调
本轮 attachments / metadata / ext
```

这样能轻量减少重复构造，同时避免用户状态串线。

---

## 5. 模型配置轻缓存

每轮 LLM 调用前都会读取模型配置、解密 API Key、再由 LLMGateway 选择模型。  
这部分可以加短 TTL 缓存，但不缓存实时限流结果。

推荐：

```text
缓存对象：active runtime model list
cache key：org_id + model_type
TTL：10 ~ 30 秒
主动失效：模型配置新增、修改、删除、健康状态变化
```

注意：

```text
可以缓存：
- 模型配置列表
- 解密后的 runtime payload

不要缓存：
- 本轮 LLMClient
- rate limit reserve 结果
- trace_id
```

---

## 6. Prompt 轻缓存

PromptBuilder 每次根据 `org_id + prompt_key` 解析运行时 prompt。  
可以做轻缓存：

```text
cache key：org_id + prompt_key
cache value：prompt_content + prompt_version
TTL：30 ~ 120 秒
主动失效：prompt 管理后台保存时清缓存
```

这样仍然支持 prompt 管理和版本更新，但避免每条消息都查 prompt 配置。

---

## 7. RuntimeGuard 短缓存

管理 Agent 执行前需要判断某个 Agent 是否被暂停、停止、维护。该机制应保留。  
但检查结果可以短缓存：

```text
cache key：org_id + selected_agent + sub_route
TTL：3 ~ 10 秒
主动失效：管理员暂停/恢复 Agent 时清缓存
```

这能减少高并发聊天时对 Agent 管理表的重复查询。

---

## 8. RAG 链路轻量优化

RAG 不应每次都无脑执行，但当路由决定需要 RAG 时，可以减少重复开销。

### 8.1 RAG Space 元数据缓存

```text
cache key：org_id + user_id + rag_space_id
cache value：space id/name/owner/updated_at
TTL：30 ~ 120 秒
```

### 8.2 Query Embedding 缓存

```text
cache key：embedding_model + normalized_query
cache value：embedding vector
TTL：5 ~ 30 分钟
```

适合连续追问、重复问法、刷新重试场景。

### 8.3 检索结果缓存

```text
cache key：
rag_space_id + scope_node_ids + normalized_query + top_k + index_version

cache value：
hits
```

RAG 文档更新后必须更新 `index_version`，避免命中过期证据。

---

## 9. 执行 Agent 的轻并行化

不要一开始重构整个 LangGraph。可以先做小范围并行：

```text
可并行：
- 文件解析
- 标准元数据加载
- RAG 检索准备
- 规则配置读取
```

推荐先在执行 Agent 内部局部使用：

```py
parsed_files, standard_meta = await asyncio.gather(
    parse_attachments(...),
    load_standard_meta(...),
)
```

不要把所有节点都并行化，避免破坏当前执行顺序和错误处理。

---

## 10. 任务启动 Celery worker 状态缓存

任务启动时如果每次都 ping Celery worker，会产生固定等待开销。

推荐：

```text
worker_available 缓存 TTL：5 ~ 10 秒
后台健康检查周期性刷新
launch_task_execution 只读缓存结果
```

这样聊天中创建检测任务时，不必每次阻塞检查 worker。

---

## 11. 前端轮询改成增量

fallback polling 不要每次拉取全部消息：

```ts
chatApi.listMessages(sessionId, 0, 500)
```

应改成：

```ts
chatApi.listMessages(sessionId, lastSeq.value, 100)
```

这样历史越长也不会越来越慢。

---

## 12. 统一聊天消息生命周期

建议抽象一个轻量生命周期服务：

```text
begin_turn()
complete_turn()
fail_turn()
interrupt_turn()
```

状态流转：

```text
created
→ routing
→ running
→ finalizing
→ completed

异常：
running → failed
running → interrupted
```

这样能集中处理：

```text
assistant message 更新
session touch
route log
token ledger
rag log
trust score pending
message_final 推送
```

避免多个模块分散写同一条消息。

---

## 13. 幂等键防重复执行

推荐给每轮聊天生成稳定幂等键：

```text
idempotency_key =
org_id + session_id + assistant_message_id + workflow_run_id
```

用于保护：

```text
assistant message final update
task 创建
result 创建
stability 创建
alert 创建
rag log
token ledger
trust score
```

即使重试、断线重连、finalizer 重入，也不会重复创建任务或重复计费。

---

## 14. 推荐落地顺序

### 阶段一：最小修复

```text
1. 修复 SSE 重复消费
2. 统一 finalizer，避免双重 message_final
3. history_loader 排除本轮用户消息
4. fallback polling 改 after_seq 增量
```

### 阶段二：轻量性能优化

```text
5. AgentManager 进程级复用
6. 模型配置短 TTL 缓存
7. Prompt 短 TTL 缓存
8. RuntimeGuard 短 TTL 缓存
```

### 阶段三：Agent 链路优化

```text
9. RAG embedding / 检索结果缓存
10. 执行 Agent 局部并行化
11. Celery worker 状态缓存
12. 统一 ChatMessageLifecycleService
13. 增加幂等键
```

---

## 15. 最终目标

优化后的系统应满足：

```text
每次用户聊天都进入 Agent 系统
每次用户聊天都至少调用一次大模型生成最终回复
管理 Agent 负责轻量路由和运行时控制
执行 Agent 负责具体任务、RAG、检测和工具调用
Graph 编译结构复用，请求状态不复用
上下文不重复，事件不重复，落库不重复
```

一句话总结：

> **不是少调模型，而是让每轮聊天只走一次清晰、轻量、可追踪、可幂等的 Agent 链路。**
