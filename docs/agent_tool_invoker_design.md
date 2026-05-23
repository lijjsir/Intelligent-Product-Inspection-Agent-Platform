# Agent 工具化改造方案：ToolRegistry / ToolInvoker / ToolExecution

> 适用仓库：`lijjsir/Intelligent-Product-Inspection-Agent-Platform`  
> 适用分支：`develop`  
> 目标：将需要与外部数据交互的功能封装为工具，并通过统一工具入口提供给所有 Agent 使用。

---

## 1. 核心结论

功能 Agent 中的模型本身不会“自动知道”仓库里有哪些函数或工具。  
模型只能知道系统在当前轮调用前显式提供给它的内容。

因此，实现重点不是让模型扫描代码，而是：

1. 将外部交互能力注册为结构化工具 `ToolSpec`。
2. 每轮 Agent 推理前，根据 `agent / surface / 权限 / 当前任务状态` 过滤可用工具。
3. 将可用工具的名称、说明、参数 schema 注入给模型。
4. 模型输出 `tool_calls`。
5. 执行 Agent 通过统一入口 `ToolInvoker` 调用工具。
6. 所有工具执行写入 `ToolExecution` 记录，方便审计、回放和工具库展示。

一句话概括：

> 凡是访问外部数据、外部服务、数据库、对象存储、向量库、第三方模型或正式业务动作的功能，都封装为工具；纯计算、规则判断、字符串处理、格式化逻辑保留为内部函数。

---

## 2. develop 分支当前现状

当前 develop 分支中已经有“工具化”的雏形，主要体现在：

```text
backend/agent/router/capability_registry.py
backend/agent/router/manager_dispatcher.py
backend/agent/router/executors/
```

现有 `CAPABILITIES` 已经定义了类似工具能力：

```text
chat.general
chat.response.compose
rag.retrieve
rag.ingest
file.summary
file.qa
image.understanding
quality.report.query
quality.task.status
quality.inspection.execute
data.analysis
```

同时 `ManagerDispatcher` 已经根据 step 的 agent 分发到不同 executor：

```python
self._executors = {
    "chat": ChatExecutor(),
    "rag": RagExecutor(),
    "file": FileExecutor(),
    "vision": VisionExecutor(),
    "quality_report": QualityReportExecutor(),
    "inspection_task": InspectionTaskExecutor(),
    "data_analysis": DataAnalysisExecutor(),
}
```

这说明项目已经具备：

```text
capability 定义
  ↓
route plan
  ↓
dispatcher
  ↓
executor
```

但目前主要问题是：

1. 工具不是统一的 `ToolSpec`。
2. 工具调用不是统一的 `ToolInvoker`。
3. 工具执行记录不够独立，缺少标准 `ToolExecution`。
4. 工具选择主要依赖 `ManagerPolicy` 的规则/正则，而不是模型基于工具 schema 自主选择。
5. 部分外部交互逻辑仍然散落在 graph 节点或业务函数中。

---

## 3. 哪些功能应该封装为工具

判断规则：

```text
需要访问外部资源、外部状态、外部服务、数据库、对象存储、向量库、模型 API、正式业务动作的功能，都应该封装为工具。
```

### 3.1 应封装为工具的功能

| 功能类型 | 当前可能涉及代码 | 建议工具名 |
|---|---|---|
| RAG 检索 | `Retriever` / `RagRetrievalService` / Qdrant | `rag.retrieve` |
| RAG 入库 | 文件切分、embedding、Qdrant upsert | `rag.ingest` |
| 附件读取 | MinIO / object storage | `file.read_attachment` |
| 文件解析 | PDF / DOCX / XLSX / TXT 解析 | `file.parse` |
| 文件总结 | 文件解析 + LLM 总结 | `file.summary` |
| 文件问答 | 文件解析 + LLM QA | `file.qa` |
| 图片理解 | vision model | `image.understand` |
| 检测任务状态查询 | 数据库任务表 | `quality.task.status` |
| 历史报告查询 | 数据库结果表 / 报告表 | `quality.report.query` |
| 标准规则评估 | `InspectionStandardService.evaluate()` | `quality.standard.evaluate` |
| 正式质检执行 | 创建/执行/落库正式任务 | `quality.inspection.execute` |
| 数据分析 | 查询统计数据、报表数据 | `data.analysis` |
| 模型调用 | 外部 LLM API | 内部可作为 LLM gateway，不一定暴露给普通 Agent |

---

## 4. 哪些功能不需要封装为工具

纯内部逻辑不需要封装为工具，例如：

| 功能 | 原因 |
|---|---|
| `_clean_text()` | 纯文本清洗 |
| `_extract_task_draft()` | 规则抽取，可作为 agent 内部 helper |
| `_missing_slots()` | 纯判断 |
| `_format_task_draft()` | 格式化 |
| `detect_product_family()` | 纯业务规则判断 |
| `build_defects()` | 结构化转换 |
| `score_from_record()` | 本地计算 |
| `PromptBuilder.build()` | prompt 构造 |
| `capability_allowed()` | 权限判断 |

这些逻辑可以被工具 handler 或 agent 节点内部调用，但不应该暴露给模型作为工具。

---

## 5. 推荐目录结构

建议新增或重构：

```text
backend/agent/tools/
  __init__.py
  contracts.py
  registry.py
  invoker.py
  execution.py
  schema.py
  builtin/
    __init__.py
    rag_tools.py
    file_tools.py
    vision_tools.py
    quality_tools.py
    data_tools.py
```

各文件职责：

```text
contracts.py
  定义 ToolSpec / ToolCall / ToolResult / ToolContext / ToolExecution

registry.py
  负责工具注册、查询、按 agent/surface 过滤工具

invoker.py
  统一工具调用入口，负责权限校验、参数校验、超时、错误处理、执行记录

execution.py
  负责工具执行日志落库或构建审计对象

schema.py
  JSON Schema 校验工具

builtin/
  内置工具实现
```

---

## 6. ToolSpec 设计

建议使用 Pydantic 定义：

```python
from typing import Any, Literal
from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    title: str
    description: str

    agent_scope: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)

    mode: Literal["read", "write", "action"] = "read"
    risk_level: Literal["low", "medium", "high"] = "medium"

    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)

    requires_confirmation: bool = False
    enabled: bool = True
    timeout_ms: int = 30000
    version: str = "1.0.0"
```

示例：

```python
RAG_RETRIEVE = ToolSpec(
    name="rag.retrieve",
    title="知识库检索",
    description="从用户选择的 RAG 空间中检索与问题相关的证据片段。",
    agent_scope=["chat", "inspection_task"],
    surfaces=["chat", "quality_task"],
    mode="read",
    risk_level="medium",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索问题"
            },
            "rag_space_id": {
                "type": "string",
                "description": "知识库空间 ID"
            },
            "top_k": {
                "type": "integer",
                "default": 5
            }
        },
        "required": ["query"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "hits": {"type": "array"},
            "hit_count": {"type": "integer"},
            "top_score": {"type": "number"}
        }
    }
)
```

---

## 7. ToolContext / ToolCall / ToolResult

```python
class ToolContext(BaseModel):
    org_id: str
    user_id: str | None = None
    request_id: str
    workflow_run_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None

    agent: str
    surface: str
    allowed_modes: list[str] = Field(default_factory=list)

    confirmed_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


class ToolResult(BaseModel):
    tool_name: str
    status: Literal["success", "failed", "blocked", "skipped"]
    data: dict[str, Any] | None = None
    error: str | None = None
    execution_id: str | None = None
    latency_ms: int | None = None
```

---

## 8. ToolExecution 记录

每次工具调用都应该生成标准记录：

```python
class ToolExecution(BaseModel):
    id: str
    tool_name: str
    agent_name: str
    surface: str

    request_id: str
    workflow_run_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None

    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] | None = None

    status: Literal["success", "failed", "blocked", "skipped"]
    error_message: str | None = None
    latency_ms: int = 0

    created_at: str
```

作用：

1. 工具库中展示“最近执行记录”。
2. Langfuse / AgentOps 中追踪工具调用。
3. 调试 Agent 任务时可以回放。
4. 发生污染、错误传播、工具异常时可以定位源头。
5. 为后续工具权限、成本统计、可用性统计提供数据。

---

## 9. ToolRegistry 设计

```python
class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {}

    def register(
        self,
        spec: ToolSpec,
        handler: Callable[..., Awaitable[dict[str, Any]]],
    ) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def get_handler(self, name: str):
        return self._handlers[name]

    def list_for(
        self,
        *,
        agent: str,
        surface: str,
        allowed_modes: list[str],
    ) -> list[ToolSpec]:
        result = []
        for spec in self._specs.values():
            if not spec.enabled:
                continue
            if spec.agent_scope and agent not in spec.agent_scope:
                continue
            if spec.surfaces and surface not in spec.surfaces:
                continue
            if spec.mode == "action" and "action" not in allowed_modes:
                continue
            result.append(spec)
        return result
```

当前 `CAPABILITIES` 可以先兼容迁移为 `ToolSpec`，避免一次性重构过大。

---

## 10. ToolInvoker 设计

```python
class ToolInvoker:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        spec = self.registry.get(tool_name)

        self._validate_enabled(spec)
        self._validate_agent_scope(spec, context)
        self._validate_surface(spec, context)
        self._validate_mode(spec, context)
        self._validate_input_schema(spec, arguments)
        self._validate_confirmation(spec, context)

        started = perf_counter()

        try:
            handler = self.registry.get_handler(tool_name)
            data = await asyncio.wait_for(
                handler(arguments, context),
                timeout=spec.timeout_ms / 1000,
            )
            status = "success"
            error = None
        except ToolBlockedError as exc:
            data = None
            status = "blocked"
            error = str(exc)
        except Exception as exc:
            data = None
            status = "failed"
            error = str(exc)

        latency_ms = round((perf_counter() - started) * 1000)

        execution = await self._record_execution(
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            status=status,
            data=data,
            error=error,
            latency_ms=latency_ms,
        )

        return ToolResult(
            tool_name=tool_name,
            status=status,
            data=data,
            error=error,
            execution_id=execution.id,
            latency_ms=latency_ms,
        )
```

ToolInvoker 必须负责：

```text
工具是否存在
工具是否启用
当前 agent 是否允许调用
当前页面 surface 是否允许调用
当前 mode 是否允许
参数是否符合 input_schema
高风险 action 是否已经确认
调用是否超时
错误是否捕获
执行是否记录
```

---

## 11. 模型如何知道该调用哪些工具

模型知道工具，依赖三层机制：

### 11.1 第一层：工具 schema 注入

在每轮调用模型前，系统过滤出当前可用工具：

```python
tools = tool_registry.list_for(
    agent=state.agent,
    surface=state.surface,
    allowed_modes=state.allowed_modes,
)
```

然后把工具转换成模型可理解的格式。

如果模型支持 OpenAI function calling：

```python
openai_tools = [
    {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.input_schema,
        },
    }
    for spec in tools
]
```

如果暂时不支持原生 tool calling，则注入到 prompt 中：

```text
你可以调用以下工具：

1. rag.retrieve
说明：从知识库检索证据。
参数：
{
  "query": "string",
  "rag_space_id": "string",
  "top_k": "integer"
}

2. quality.task.status
说明：查询质量检测任务状态。
参数：
{
  "task_id": "string"
}

当你需要外部数据时，必须输出 tool_calls，不要凭空回答。
```

### 11.2 第二层：系统提示词说明调用条件

例如：

```text
你是质量检测 Agent。

当用户问题需要访问知识库、检测报告、任务状态、文件内容、图片内容或正式检测执行时，必须调用工具。

调用规则：
- 涉及标准、规范、知识库、RAG 证据：调用 rag.retrieve
- 涉及检测任务状态：调用 quality.task.status
- 涉及历史报告或检测结果：调用 quality.report.query
- 涉及上传文件总结：调用 file.summary
- 涉及上传图片理解：调用 image.understand
- 只有 quality_task 页面允许调用 quality.inspection.execute
- 聊天页禁止执行 action 类工具
- 工具结果不足时，应说明证据不足，而不是编造答案
```

### 11.3 第三层：系统强约束

即使模型输出了违规工具调用，也必须由 `ToolInvoker` 拦截。

例如聊天页中模型尝试调用：

```json
{
  "name": "quality.inspection.execute",
  "arguments": {}
}
```

ToolInvoker 应返回：

```json
{
  "status": "blocked",
  "error": "聊天页面不允许执行正式质量检测动作"
}
```

也就是说：

```text
模型负责提出工具调用意图；
ToolInvoker 负责决定能不能真的执行。
```

---

## 12. Agent 工具调用循环

功能 Agent 不应该只调用一次模型，而应该使用有限轮工具循环：

```text
1. 构造 messages
2. 注入可用工具
3. 调用模型
4. 如果模型返回 final_answer，结束
5. 如果模型返回 tool_calls，执行工具
6. 将 tool results 作为 observation 回填给模型
7. 进入下一轮
8. 达到上限则降级返回
```

伪代码：

```python
async def run_agent_with_tools(state):
    tools = tool_registry.list_for(
        agent=state.agent,
        surface=state.surface,
        allowed_modes=state.allowed_modes,
    )

    observations = []

    for _ in range(state.max_tool_rounds):
        response = await llm.chat_with_tools(
            messages=build_messages(state, observations),
            tools=tools,
        )

        if response.final_answer:
            return response.final_answer

        if not response.tool_calls:
            return response.answer or "我无法确定是否需要调用工具，请补充更多信息。"

        for call in response.tool_calls:
            result = await tool_invoker.invoke(
                tool_name=call.name,
                arguments=call.arguments,
                context=ToolContext.from_state(state),
            )
            observations.append(result)

    return "工具调用轮次已达到上限，请补充更明确的信息。"
```

---

## 13. LLMClient 需要的改造

当前 `LLMClient.chat()` 主要支持普通 JSON 输出。建议增加：

```python
async def chat_with_tools(
    self,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    tool_choice: str | dict[str, Any] = "auto",
    temperature: float = 0.2,
    observation_name: str = "llm.chat_with_tools",
    observation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "model": self._model_id,
        "messages": messages,
        "temperature": temperature,
        "tools": tools,
        "tool_choice": tool_choice,
    }
    return await self._post_json(...)
```

如果底层模型不支持 tools，则提供降级路径：

```python
async def chat_tool_json_mode(...):
    # 把 tools 作为文本注入 prompt
    # 要求模型返回：
    # {
    #   "tool_calls": [...],
    #   "final_answer": null
    # }
```

这样可以兼容不同模型供应商。

---

## 14. 与当前 ManagerLoop 的兼容策略

不建议一次性推翻现有 `ManagerLoop`。推荐两阶段迁移。

### 阶段一：兼容现有 capability

保留：

```text
Capability
AgentRoutePlan
ManagerLoop
ManagerDispatcher
Executor
```

新增：

```text
ToolSpec
ToolRegistry
ToolInvoker
ToolExecution
```

然后将 `ManagerDispatcher` 改为调用 `ToolInvoker`：

```python
result = await tool_invoker.invoke(
    tool_name=step.capability_key,
    arguments=step.input,
    context=ToolContext.from_manager_state(state, request),
)
```

这样原来的规则路由还能继续工作。

### 阶段二：模型生成 tool_calls

将 `ManagerPolicy.understand()` 的规则判断降级为兜底，把主路径改为：

```text
获取可用工具
  ↓
模型根据 query + tools 生成 tool plan
  ↓
ToolInvoker 执行
  ↓
Evaluator 判断是否完成
```

规则仍保留用于：

```text
安全边界
页面限制
硬性动作拦截
工具调用预算
fallback
```

---

## 15. 数据库表设计

### 15.1 agent_tools

记录工具定义：

```sql
CREATE TABLE agent_tools (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    title VARCHAR NOT NULL,
    description TEXT NOT NULL,
    agent_scope JSONB NOT NULL DEFAULT '[]',
    surfaces JSONB NOT NULL DEFAULT '[]',
    mode VARCHAR NOT NULL,
    input_schema JSONB NOT NULL DEFAULT '{}',
    output_schema JSONB NOT NULL DEFAULT '{}',
    risk_level VARCHAR NOT NULL DEFAULT 'medium',
    requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    version VARCHAR NOT NULL DEFAULT '1.0.0',
    source VARCHAR NOT NULL DEFAULT 'builtin',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

### 15.2 agent_tool_executions

记录每次工具调用：

```sql
CREATE TABLE agent_tool_executions (
    id VARCHAR PRIMARY KEY,
    tool_name VARCHAR NOT NULL,
    agent_name VARCHAR NOT NULL,
    surface VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    workflow_run_id VARCHAR,
    session_id VARCHAR,
    trace_id VARCHAR,
    input_json JSONB NOT NULL DEFAULT '{}',
    output_json JSONB,
    status VARCHAR NOT NULL,
    error_message TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL
);
```

---

## 16. 工具库前端应该展示什么

工具库页面可以展示：

```text
工具名称
工具标题
工具描述
所属 agent
允许页面 surface
工具模式 read/write/action
风险等级
是否需要确认
是否启用
输入 schema
输出 schema
最近调用次数
最近成功率
平均耗时
最近错误
```

Agent 详情页可以展示：

```text
该 Agent 可用工具
该 Agent 最近调用过的工具
调用失败的工具
工具调用链路
工具返回的 artifacts
```

---

## 17. 推荐改造文件顺序

优先改这些文件：

```text
1. backend/agent/tools/contracts.py
2. backend/agent/tools/registry.py
3. backend/agent/tools/invoker.py
4. backend/agent/tools/execution.py
5. backend/agent/tools/builtin/rag_tools.py
6. backend/agent/tools/builtin/file_tools.py
7. backend/agent/tools/builtin/vision_tools.py
8. backend/agent/tools/builtin/quality_tools.py
9. backend/agent/tools/builtin/data_tools.py
10. backend/agent/llm/client.py
11. backend/agent/router/manager_dispatcher.py
12. backend/agent/router/manager_policy.py
13. backend/agent/subgraphs/quality_chat/graph.py
14. backend/agent/subgraphs/inspection_task/graph.py
```

---

## 18. 具体迁移建议

### 18.1 RAG 检索迁移

当前 `quality_chat/graph.py` 中 `knowledge()` 节点直接执行 RAG 检索。  
建议迁移为：

```python
result = await tool_invoker.invoke(
    tool_name="rag.retrieve",
    arguments={
        "query": state["query"],
        "rag_space_id": policy_decision.rag_space_id,
        "top_k": top_k,
        "payload_filter": payload_filter,
    },
    context=ToolContext.from_state(state),
)
```

### 18.2 文件读取迁移

当前 `inspection_task/graph.py` 中 `_parse_attachments()` 会读取对象存储并解析文件。  
建议拆成：

```text
file.read_attachment
file.parse
file.summary
file.qa
```

### 18.3 正式质检迁移

正式质检执行建议拆为：

```text
quality.inspection.execute
quality.standard.evaluate
quality.result.persist
```

其中：

```text
quality.inspection.execute
  负责整体编排

quality.standard.evaluate
  负责规则评估

quality.result.persist
  负责落库
```

正式写入动作必须：

```text
surface = quality_task
mode = action
requires_confirmation = true
action_intent = quality_inspection_execute
```

### 18.4 报告查询迁移

查询已有检测报告属于只读工具：

```text
quality.report.query
quality.task.status
```

可以允许在 chat 和 quality_task 页面调用。

---

## 19. 安全边界

工具系统必须保留这些硬边界：

| 场景 | 规则 |
|---|---|
| 聊天页请求正式检测 | 阻止，提示去任务页面 |
| 聊天页请求 RAG 入库 | 阻止，提示去知识库页面确认 |
| action 工具缺少确认 | 阻止 |
| action 工具缺少 action_intent | 阻止 |
| 工具参数不满足 schema | 阻止并返回缺失字段 |
| 工具超时 | 返回 failed，不让模型继续编造 |
| RAG 无命中 | 明确证据不足 |
| 模型输出未知工具 | 阻止 |
| agent 调用了不属于自己的工具 | 阻止 |

---

## 20. 最终架构图

```text
用户请求
  ↓
AgentManager / ManagerLoop
  ↓
识别 surface、agent、权限、预算
  ↓
ToolRegistry 过滤当前可用工具
  ↓
功能 Agent 模型接收：
    - 用户目标
    - 历史上下文
    - 当前 observations
    - 可用工具 schema
    - 工具调用规则
  ↓
模型输出 tool_calls
  ↓
执行 Agent 调用 ToolInvoker
  ↓
ToolInvoker：
    - 工具存在性校验
    - agent scope 校验
    - surface 校验
    - mode 校验
    - JSON schema 校验
    - 确认状态校验
    - 超时控制
    - 错误捕获
    - ToolExecution 记录
  ↓
工具结果 observation 回填给模型
  ↓
模型生成最终回答
  ↓
ResponseWriter 输出给用户
```

---

## 21. 最小可落地版本

如果先做一个最小版本，可以只实现：

```text
ToolSpec
ToolRegistry
ToolInvoker
ToolExecution
rag.retrieve
quality.task.status
quality.report.query
file.summary
image.understand
```

然后先把 `ManagerDispatcher` 改成通过 `ToolInvoker` 执行。  
这样不需要马上实现模型自主 tool calling，也能先完成“外部能力统一工具化”。

下一步再把 `ManagerPolicy` 从规则规划升级为模型基于工具 schema 规划。

---

## 22. 关键回答：功能 Agent 的模型如何知道自己需要调用哪些工具？

答案是：

> 在每次模型推理前，由系统从工具库中筛选该 Agent 当前可用工具，并把工具说明和参数 schema 注入给模型；模型根据用户目标和工具说明输出 tool_calls；执行 Agent 再通过 ToolInvoker 统一调用工具。模型不是自己发现工具，而是由 ToolRegistry 显式提供工具清单。

这也是最稳定、最可控、最适合多 Agent 系统的实现方式。
