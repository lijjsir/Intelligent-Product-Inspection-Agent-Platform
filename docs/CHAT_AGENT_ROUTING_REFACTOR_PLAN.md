# 聊天入口 Agent 路由、Prompt、RAG 与 Langfuse 监控重构方案

## 1. 背景与目标

当前同一个聊天页面承载了多种输入意图：普通聊天、知识库问答、质检问答、任务创建、正式检测。现有链路已经具备 `AgentManager -> Chat/Inspection` 的雏形，但仍存在以下问题：

1. 外层路由语义不清，普通聊天容易被质检语义污染。
2. 普通聊天、RAG 问答、质检问答、任务创建逻辑混在一起，后续维护成本高。
3. Prompt 与流程没有强绑定，导致普通知识库问答引用 RAG 后可能出现质检话术。
4. RAG 只是证据来源，但当前容易被当成流程身份，造成“用了 RAG 就像质检问答”。
5. 输出字段虽然接近统一，但不同流程的字段语义不够稳定，前端难以可靠渲染。
6. Langfuse 已接入 LLM 调用层，但缺少按流程、Agent、子路径的统一 trace/span 规范。
7. Langfuse 本地账号、项目密钥、环境变量和部署连接方式需要标准化。

本方案目标是以最高效率完成重构：

- 外层只保留两个一级 Agent：`ChatAgent` 和 `InspectionTaskAgent`。
- Agent 内部再用规则优先、模型兜底的方式分子路径。
- Prompt 按 `agent + sub_route` 单独管理。
- RAG 按流程策略调用，不能决定 Prompt 身份。
- 输出协议外层统一，字段按子路径差异化。
- Langfuse 按 `flow / agent / sub_route / intent / trace_id` 统一监控。

---

## 2. 目标总体架构

```text
同一个聊天页面输入
        ↓
ChatService：只负责会话、消息、SSE、异步工作流触发
        ↓
AgentManager：一级路由，只判断 ChatAgent / InspectionTaskAgent
        ↓
ChatAgent
  ├── general_chat：普通聊天、平台说明
  └── rag_qa：普通知识库问答

InspectionTaskAgent
  ├── quality_qa：质检问答、标准解释、缺陷判定依据
  ├── task_create：任务创建、任务草稿、槽位补全、确认提交
  └── inspection_execute：正式检测、结构化文件/图片检测、结果落库
        ↓
PromptBuilder：按 agent + sub_route 生成系统提示词
        ↓
RagPolicy：按 sub_route 决定是否检索、检索哪个空间、top_k、过滤条件
        ↓
LLMClient：统一模型调用 + Langfuse observation
        ↓
ResponseBuilder：统一 ChatAssistantPayload
        ↓
消息写回 + SSE 推送 + Langfuse trace
```

核心原则：

```text
RAG 是上下文来源，不是流程身份。
Prompt 由 Agent + 子路径决定，不由是否使用 RAG 决定。
AgentManager 只做粗粒度分流，细粒度功能在 Agent 内部完成。
```

---

## 3. 一级路由设计：AgentManager 只分两个 Agent

### 3.1 一级 Agent 枚举

将当前路由结果从：

```python
selected_agent: Literal["quality_chat", "inspection_task"]
```

调整为：

```python
selected_agent: Literal["chat", "inspection_task"]
```

新增子路径字段：

```python
sub_route: Literal[
    "general_chat",
    "rag_qa",
    "quality_qa",
    "task_create",
    "inspection_execute",
]
```

建议修改文件：

```text
backend/agent/router/contracts.py
backend/agent/router/route_policy.py
backend/agent/router/agent_manager.py
backend/agent/contracts/quality_contracts.py
```

### 3.2 一级路由规则

一级路由只判断是否进入质检业务域。

| 输入信号 | selected_agent | sub_route 建议 | 说明 |
|---|---|---|---|
| `route_hints.force_agent == chat` | `chat` | 由 ChatAgent 内部判断 | 前端强制聊天 |
| `route_hints.force_agent == inspection_task` | `inspection_task` | 由 InspectionTaskAgent 内部判断 | 前端强制检测 |
| 上传结构化文件 xlsx/csv/json/jsonl/txt/docx/md 且和检测有关 | `inspection_task` | `inspection_execute` | 直接进入正式检测或结构化检测 |
| 上传图片并要求检测/质检 | `inspection_task` | `inspection_execute` | 图片检测 |
| 出现创建任务/新建任务/发起检测/提交任务 | `inspection_task` | `task_create` | 任务创建 |
| 出现质量/质检/缺陷/合格/不合格/判定/标准/规范等质量语义 | `inspection_task` | `quality_qa` | 质检问答 |
| 选择了 RAG 知识库但无质检语义 | `chat` | `rag_qa` | 普通知识库问答 |
| 普通闲聊/平台功能/无明显业务信号 | `chat` | `general_chat` | 普通聊天 |
| 规则冲突或置信度低 | 先规则，必要时模型兜底 | 由 RouterClassifier 输出 | 模糊场景 |

### 3.3 规则优先、模型兜底

不建议每条消息都调用模型做路由，成本高且不稳定。推荐：

```text
manual route_hints
  > 强业务规则
  > 文件/图片信号
  > RAG 选择信号
  > 模糊场景模型分类
  > 默认 ChatAgent.general_chat
```

需要模型兜底的模糊输入示例：

```text
这个能不能过？
帮我看看这个。
这个有问题吗？
根据这个处理一下。
```

模型只输出分类，不生成最终回答：

```json
{
  "selected_agent": "inspection_task",
  "sub_route": "quality_qa",
  "intent": "quality_qa",
  "confidence": 0.72,
  "requires_confirmation": true,
  "reason": "用户可能在询问质量判定，但缺少产品和标准信息"
}
```

---

## 4. ChatAgent 内部设计

ChatAgent 负责非正式质检执行类的聊天能力。

```text
ChatAgent
├── general_chat
└── rag_qa
```

### 4.1 general_chat

适用输入：

```text
你好
你是谁
你能做什么
我叫 xxx
这个平台怎么用
知识库怎么上传
检测任务在哪里看
```

行为要求：

- 不检索 RAG，除非用户明确说“根据知识库/文档”。
- 不输出质检判定。
- 不输出风险等级。
- 不主动要求产品编号、标准编号、检测图片。
- 可以引导用户如何创建质检任务。

系统提示词：

```text
你是 PIAP 平台的通用聊天助手。
你可以解释平台功能、普通问题、知识库使用方式和检测任务入口。
如果用户没有提出质检、任务创建、知识库引用需求，不要主动输出质检判定、检测标准、风险等级、缺陷结论等内容。
回答应自然、简洁、面向用户操作。
```

输出：

```json
{
  "agent": "chat",
  "sub_route": "general_chat",
  "message_type": "assistant_text",
  "intent": "general_chat",
  "answer": "...",
  "citations": [],
  "quality": {},
  "task_draft": null,
  "created_task": null,
  "result_card": null
}
```

### 4.2 rag_qa

适用输入：

```text
总结这份文档
根据我选中的知识库回答
这个知识库主要讲什么
文档里有没有提到 xxx
```

进入条件：

- `selected_rag_space_id` 存在，并且无质检语义；或
- 用户明确说“根据知识库/根据文档/总结文档/引用资料”。

行为要求：

- 只作为普通知识库问答。
- 可以引用 RAG 证据。
- 不能套用质检话术。
- 不能要求用户补充产品编号、标准编号、检测图片。

系统提示词：

```text
你是知识库问答助手。
请基于检索到的知识库内容回答用户的问题。
不要套用质量检测、任务检测、标准编号、产品型号、缺陷位置、风险等级等质检话术。
如果证据不足，请说明知识库中没有足够相关内容，并给出可以继续补充的方向。
```

输出：

```json
{
  "agent": "chat",
  "sub_route": "rag_qa",
  "message_type": "assistant_text",
  "intent": "rag_qa",
  "answer": "...",
  "citations": [],
  "rag_summary": {
    "rag_space_id": "...",
    "hit_count": 4,
    "top_sources": []
  },
  "quality": {}
}
```

---

## 5. InspectionTaskAgent 内部设计

InspectionTaskAgent 负责质检业务域内的全部能力。

```text
InspectionTaskAgent
├── quality_qa
├── task_create
└── inspection_execute
```

### 5.1 quality_qa：质检问答

适用输入：

```text
这个缺陷算不算不合格？
划痕怎么判定？
GB/T 标准里外观缺陷怎么要求？
这种情况应该怎么处理？
```

行为要求：

- 检索质检标准库或用户选中的知识库。
- 以标准、规则、证据为依据回答。
- 证据不足时不能强行下结论。
- 可以输出置信度、证据覆盖、风险提示。
- 不直接创建任务，除非用户明确要求。

系统提示词：

```text
你是质量检测问答助手。
请基于检索到的标准、规范、规则和历史检测依据回答用户的质检问题。
回答必须包含：判定依据、不确定性说明、必要时的引用来源。
证据不足时，请明确说明不能做最终判定，不要编造标准条款或检测结论。
```

输出：

```json
{
  "agent": "inspection_task",
  "sub_route": "quality_qa",
  "message_type": "quality_answer",
  "intent": "quality_qa",
  "answer": "...",
  "citations": [],
  "quality": {
    "confidence": 0.86,
    "evidence_coverage": 1.0,
    "traceability": 0.9,
    "risk_level": "low",
    "passed": true
  }
}
```

### 5.2 task_create：任务创建 / 任务草稿

适用输入：

```text
帮我创建检测任务。
产品是 FOOD-001，标准是 FOOD-RAG-BASE-V1。
这些图片帮我检测一下。
确认创建。
取消任务。
```

行为要求：

- 提取槽位：`product_id`、`spec_code`、`image_urls`、`priority`。
- 信息不足时追问缺失字段。
- 信息完整时等待用户确认。
- 用户确认后进入 `inspection_execute` 或调用任务创建接口。

任务槽位：

```json
{
  "product_id": "",
  "spec_code": "",
  "image_urls": [],
  "priority": 5,
  "metadata": {}
}
```

系统提示词：

```text
你是检测任务创建助手。
你的职责是从用户输入中提取产品编号、检测标准、检测图片、优先级，并生成任务草稿。
如果信息不足，只追问缺失字段，不要进行质量判定。
如果信息完整，请展示任务草稿，并要求用户确认后再提交。
```

输出示例：

```json
{
  "agent": "inspection_task",
  "sub_route": "task_create",
  "message_type": "task_action",
  "intent": "task_create",
  "answer": "还需要补充检测标准和检测图片。",
  "action_state": "awaiting_task_details",
  "task_draft": {
    "product_id": "FOOD-001",
    "spec_code": "",
    "image_urls": [],
    "priority": 5
  },
  "missing_slots": ["spec_code", "image_urls"],
  "awaiting_confirmation": false
}
```

### 5.3 inspection_execute：正式检测

适用输入：

```text
确认创建。
开始检测。
检测这张图。
根据这个结构化文件完成质检。
```

行为要求：

- 解析文件或图片。
- 根据产品、标准、结构化记录和 RAG 证据完成检测。
- 写入任务、结果、稳定性分析、告警、token 使用记录。
- 输出检测结果卡片。

系统提示词：

```text
你是正式质量检测执行智能体。
请基于图片、结构化文件、产品信息、检测标准和 RAG 证据完成检测。
输出必须包含检测结论、依据、引用、风险等级、结果摘要。
证据不足时，应进入人工复核或补充信息状态，不要强行 PASS/FAIL。
```

输出：

```json
{
  "agent": "inspection_task",
  "sub_route": "inspection_execute",
  "message_type": "task_result",
  "intent": "inspection_execute",
  "answer": "...",
  "action_state": "done",
  "created_task": {
    "id": "...",
    "status": "done",
    "product_id": "FOOD-001",
    "spec_code": "FOOD-RAG-BASE-V1",
    "priority": 5,
    "image_count": 3
  },
  "result_card": {
    "verdict": "pass",
    "overall_score": 0.91,
    "risk_level": "low"
  },
  "citations": [],
  "quality": {},
  "rag_summary": {}
}
```

---

## 6. RAG 策略设计

RAG 策略必须按子路径决定。

| 子路径 | 默认是否 RAG | RAG 来源 | 说明 |
|---|---:|---|---|
| `general_chat` | 否 | 无 | 普通聊天不检索 |
| `rag_qa` | 是 | 用户选择的 RAG Space | 普通知识库问答 |
| `quality_qa` | 是 | 质检标准库 + 用户选择知识库 | 标准解释、缺陷判定 |
| `task_create` | 可选 | 一般不检索 | 主要做槽位提取 |
| `inspection_execute` | 是 | spec_code 对应标准 + 选中知识库 + 结构化记录 | 正式检测依据 |

RAG 返回内容应该统一为：

```json
{
  "retrieved_chunks": [],
  "citations": [],
  "rag_summary": {
    "rag_space_id": "...",
    "rag_space_name": "...",
    "hit_count": 0,
    "top_score": 0.0,
    "citation_coverage": 0.0,
    "top_sources": []
  },
  "retrieval_metrics": {
    "query": "...",
    "top_k": 4,
    "latency_ms": 0,
    "empty_recall": false,
    "skipped": false
  }
}
```

---

## 7. PromptBuilder 设计

新增目录：

```text
backend/agent/prompts/
  __init__.py
  prompt_builder.py
  chat.py
  inspection.py
  router.py
```

建议接口：

```python
class PromptBuilder:
    @staticmethod
    def build(
        *,
        agent: str,
        sub_route: str,
        query: str,
        history: list[dict],
        retrieved_docs: list[dict] | None = None,
        task_draft: dict | None = None,
        runtime_prompt_section: str = "",
    ) -> tuple[str, str, dict]:
        """返回 system_prompt, user_message, metadata"""
```

每个子路径独立 Prompt：

```text
ChatAgent.general_chat          -> chat_general_v1
ChatAgent.rag_qa                -> chat_rag_qa_v1
InspectionTaskAgent.quality_qa  -> inspection_quality_qa_v1
InspectionTaskAgent.task_create -> inspection_task_create_v1
InspectionTaskAgent.execute     -> inspection_execute_v1
```

Prompt 版本必须写入输出 payload 与 Langfuse metadata：

```json
{
  "prompt_version": "chat_rag_qa_v1",
  "workflow_version": "chat_router_v2"
}
```

---

## 8. 统一输出协议

保留现有 `ChatAssistantPayload` 思路，但增加以下字段：

```json
{
  "agent": "chat | inspection_task",
  "sub_route": "general_chat | rag_qa | quality_qa | task_create | inspection_execute",
  "ui_schema": "chat_text_v1 | rag_answer_v1 | quality_answer_v1 | task_action_v1 | task_result_v1",
  "route_decision": {},
  "trace_url": ""
}
```

完整推荐格式：

```json
{
  "answer": "",
  "summary": "",
  "agent": "chat",
  "sub_route": "general_chat",
  "intent": "general_chat",
  "message_type": "assistant_text",
  "ui_schema": "chat_text_v1",
  "citations": [],
  "rag_summary": null,
  "quality": {},
  "task_draft": null,
  "task_form_defaults": null,
  "missing_slots": [],
  "pending_action": null,
  "awaiting_confirmation": false,
  "created_task": null,
  "result_card": null,
  "expectation_check": null,
  "action_state": "answered",
  "route_decision": {},
  "trace_id": "",
  "trace_url": "",
  "workflow_version": "chat_router_v2",
  "prompt_version": "chat_general_v1"
}
```

前端渲染建议：

| ui_schema | 渲染方式 |
|---|---|
| `chat_text_v1` | 普通文本 |
| `rag_answer_v1` | 文本 + 引用来源 |
| `quality_answer_v1` | 文本 + 引用 + 质量风险指标 |
| `task_action_v1` | 任务草稿卡片 + 缺失字段 + 确认按钮 |
| `task_result_v1` | 检测结果卡片 + 风险 + 任务链接 |

---

## 9. Langfuse 监控方案

### 9.1 Trace 命名

每次聊天输入创建一个顶层 trace。

| 子路径 | trace name |
|---|---|
| 普通聊天 | `chat.general_chat` |
| 知识库问答 | `chat.rag_qa` |
| 质检问答 | `inspection.quality_qa` |
| 任务创建 | `inspection.task_create` |
| 正式检测 | `inspection.execute` |

### 9.2 Metadata 标准

所有 trace 必须包含：

```json
{
  "source_type": "chat",
  "agent": "chat",
  "sub_route": "rag_qa",
  "intent": "rag_qa",
  "route_source": "rule",
  "route_confidence": 0.9,
  "requires_confirmation": false,
  "session_id": "...",
  "assistant_message_id": "...",
  "workflow_run_id": "...",
  "org_id": "...",
  "user_id": "...",
  "rag_space_id": "...",
  "prompt_version": "chat_rag_qa_v1",
  "workflow_version": "chat_router_v2"
}
```

### 9.3 Span / Observation 结构

ChatAgent.rag_qa：

```text
trace: chat.rag_qa
  span: router.decide
  span: chat.history.load
  span: rag.retrieve
  generation: llm.chat.answer
  span: response.build
  span: db.persist
  score: trust_score / user_feedback
```

InspectionTaskAgent.quality_qa：

```text
trace: inspection.quality_qa
  span: router.decide
  span: inspection.intent.route
  span: rag.retrieve_standard
  generation: llm.quality_answer
  span: quality_gate
  span: response.build
  span: db.persist
```

InspectionTaskAgent.inspection_execute：

```text
trace: inspection.execute
  span: task.load_or_create
  span: model.select
  span: file.parse
  span: vision.detect
  span: rag.retrieve_standard
  generation: llm.reasoning
  span: standard_gate
  span: stability.analyze
  span: result.persist
```

### 9.4 Langfuse 环境变量

本地开发可提供固定默认账号密码，但不要把生产真实密码提交到仓库。

`.env.langfuse.local.example`：

```env
PIAP_LANGFUSE_ENABLED=true
PIAP_LANGFUSE_HOST=http://langfuse-web:3000
PIAP_LANGFUSE_PUBLIC_HOST=http://127.0.0.1:3000
PIAP_LANGFUSE_PUBLIC_KEY=pk-lf-piap-local
PIAP_LANGFUSE_SECRET_KEY=sk-lf-piap-local
PIAP_LANGFUSE_ENVIRONMENT=local
PIAP_LANGFUSE_RELEASE=tgg-local

LANGFUSE_INIT_ORG_ID=piap-local-org
LANGFUSE_INIT_ORG_NAME=PIAP Local
LANGFUSE_INIT_PROJECT_ID=piap-local-project
LANGFUSE_INIT_PROJECT_NAME=PIAP Local Project
LANGFUSE_INIT_USER_EMAIL=admin@piap.local
LANGFUSE_INIT_USER_NAME=PIAP Admin
LANGFUSE_INIT_USER_PASSWORD=piap_admin_123456
```

生产环境 `.env.production.example`：

```env
PIAP_LANGFUSE_ENABLED=true
PIAP_LANGFUSE_HOST=http://langfuse-web:3000
PIAP_LANGFUSE_PUBLIC_HOST=https://langfuse.example.com
PIAP_LANGFUSE_PUBLIC_KEY=replace-me
PIAP_LANGFUSE_SECRET_KEY=replace-me
PIAP_LANGFUSE_ENVIRONMENT=prod
PIAP_LANGFUSE_RELEASE=replace-me

LANGFUSE_INIT_USER_EMAIL=replace-me
LANGFUSE_INIT_USER_PASSWORD=replace-me
LANGFUSE_NEXTAUTH_SECRET=replace-me
LANGFUSE_SALT=replace-me
LANGFUSE_ENCRYPTION_KEY=replace-me
```

---

## 10. 高效率实现步骤

### 阶段 1：改路由协议，不大拆 Graph

目标：先让外层只区分 `chat` 与 `inspection_task`。

修改：

```text
backend/agent/router/contracts.py
backend/agent/router/route_policy.py
backend/agent/router/agent_manager.py
backend/agent/contracts/quality_contracts.py
```

完成标准：

- `AgentRouteDecision.selected_agent` 支持 `chat | inspection_task`。
- 新增 `sub_route`。
- 普通聊天默认进入 `chat.general_chat`。
- 选中普通知识库进入 `chat.rag_qa`。
- 质检语义进入 `inspection_task.quality_qa`。
- 创建任务进入 `inspection_task.task_create`。
- 图片/结构化文件检测进入 `inspection_task.inspection_execute`。

### 阶段 2：抽 PromptBuilder

目标：先解决 Prompt 污染问题。

新增：

```text
backend/agent/prompts/prompt_builder.py
backend/agent/prompts/chat.py
backend/agent/prompts/inspection.py
```

把原来 Graph 中硬编码的 prompt 移出来。

完成标准：

- `general_chat` 不出现质检话术。
- `rag_qa` 不出现产品编号、标准编号、缺陷判定等提示。
- `quality_qa` 才允许出现质检依据、证据覆盖、风险。
- `task_create` 只提槽位和确认，不做判定。
- `inspection_execute` 才做正式检测。

### 阶段 3：整理 ChatAgent / InspectionTaskAgent 内部子路由

短期可以复用现有 Graph，但要按新子路径运行。

建议：

```text
backend/agent/subgraphs/chat/
  __init__.py
  graph.py
  state.py

backend/agent/subgraphs/inspection_task/
  graph.py
  router.py
  nodes/
```

若时间紧，先不物理拆目录，只在现有文件中把 `sub_route` 传下去。

完成标准：

- ChatAgent 只处理 `general_chat / rag_qa`。
- InspectionTaskAgent 只处理 `quality_qa / task_create / inspection_execute`。
- `quality_qa / task_create` 不再放在 ChatAgent 语义下。

### 阶段 4：统一 ResponseBuilder

新增：

```text
backend/agent/response/response_builder.py
```

完成标准：

- 所有流程都返回统一 payload。
- 前端可根据 `ui_schema` 渲染。
- `agent / sub_route / message_type / action_state` 一致。

### 阶段 5：Langfuse Trace 标准化

修改：

```text
backend/agent/llm/langfuse_tracer.py
backend/agent/llm/client.py
各 Agent Graph run 入口
```

完成标准：

- 每次输入都有 trace。
- trace name 能区分 `chat.general_chat / chat.rag_qa / inspection.quality_qa / inspection.task_create / inspection.execute`。
- LLM observation 包含 `agent / sub_route / intent / prompt_version`。
- RAG 检索有 span 或 metadata。
- 最终 payload 返回 `trace_id / trace_url`。

---

## 11. 推荐代码草图

### 11.1 AgentRouteDecision

```python
class AgentRouteDecision(BaseModel):
    selected_agent: Literal["chat", "inspection_task"] = "chat"
    sub_route: Literal[
        "general_chat",
        "rag_qa",
        "quality_qa",
        "task_create",
        "inspection_execute",
    ] = "general_chat"
    intent: str = "general_chat"
    confidence: float = 1.0
    reason: str = ""
    requires_confirmation: bool = False
    route_source: Literal["manual", "rule", "model", "fallback"] = "rule"
    fallback_agent: str | None = None
```

### 11.2 AgentManager

```python
class AgentManager:
    async def run(self, request: NormalizedRequest) -> AgentRouterOutput:
        decision = self._route_policy.decide(AgentRouterInput.from_request(request))

        if decision.selected_agent == "inspection_task":
            agent_output = await self.inspection_task_agent.run(request, decision)
        else:
            agent_output = await self.chat_agent.run(request, decision)

        return AgentRouterOutput(
            route_decision=decision,
            agent_output=agent_output.model_dump() if hasattr(agent_output, "model_dump") else agent_output,
            status="completed",
        )
```

### 11.3 一级路由伪代码

```python
def decide(input_data: AgentRouterInput) -> AgentRouteDecision:
    query = normalize(input_data.query)
    route_hints = merge_route_hints(input_data)

    if route_hints.force_agent == "chat":
        return chat_decision(sub_route=route_hints.get("sub_route") or "general_chat", source="manual")

    if route_hints.force_agent == "inspection_task":
        return inspection_decision(sub_route=route_hints.get("sub_route") or "task_create", source="manual")

    if has_structured_file(input_data) and has_inspection_signal(query):
        return inspection_decision("inspection_execute", reason="结构化文件 + 检测意图")

    if has_image(input_data) and has_inspection_signal(query):
        return inspection_decision("inspection_execute", reason="图片 + 检测意图")

    if has_task_create_signal(query):
        return inspection_decision("task_create", reason="任务创建意图")

    if has_quality_qa_signal(query):
        return inspection_decision("quality_qa", reason="质检问答意图")

    if has_selected_rag_space(input_data) or has_general_rag_signal(query):
        return chat_decision("rag_qa", reason="普通知识库问答")

    if is_ambiguous(query):
        return classify_with_small_model_or_fallback(query)

    return chat_decision("general_chat", reason="默认普通聊天")
```

---

## 12. 测试用例

### 12.1 一级路由测试

| 输入 | 期望 Agent | 期望 sub_route |
|---|---|---|
| 你好 | chat | general_chat |
| 你是谁 | chat | general_chat |
| 总结这个知识库 | chat | rag_qa |
| 根据文档回答 xxx | chat | rag_qa |
| 这个缺陷算不算不合格 | inspection_task | quality_qa |
| 划痕怎么判定 | inspection_task | quality_qa |
| 帮我创建检测任务 | inspection_task | task_create |
| 产品 FOOD-001，标准 xxx，开始检测 | inspection_task | task_create 或 inspection_execute |
| 上传图片并说“检测这个” | inspection_task | inspection_execute |
| 上传 xlsx 并说“完成质检” | inspection_task | inspection_execute |

### 12.2 Prompt 污染测试

| 场景 | 不允许出现 |
|---|---|
| general_chat | 检测标准、缺陷判定、风险等级 |
| rag_qa | 产品编号、质检任务、PASS/FAIL |
| quality_qa | 闲聊式无依据结论 |
| task_create | 直接质量判定 |
| inspection_execute | 无结构化结果 |

### 12.3 Langfuse 测试

| 场景 | 期望 trace name |
|---|---|
| 普通聊天 | chat.general_chat |
| 知识库问答 | chat.rag_qa |
| 质检问答 | inspection.quality_qa |
| 任务创建 | inspection.task_create |
| 正式检测 | inspection.execute |

---

## 13. 验收标准

完成后应满足：

1. 普通聊天不会再进入 `quality_chat` 语义。
2. 普通知识库问答不会出现质检提示词。
3. 质检问答、任务创建、正式检测都归属于 `InspectionTaskAgent`。
4. AgentManager 只负责 `ChatAgent / InspectionTaskAgent` 粗粒度分流。
5. Agent 内部通过规则优先、模型兜底划分不同子路径。
6. 每条消息都有稳定的 `agent / sub_route / message_type / ui_schema`。
7. 前端能按 `ui_schema` 稳定渲染文本、引用、任务草稿、检测结果。
8. Langfuse 能按 `agent / sub_route / intent / prompt_version` 查询。
9. 本地 Langfuse 可通过环境变量自动初始化账号和项目。
10. 生产环境不提交真实密钥，只提交 example 模板。

---

## 14. 推荐最小改动版本

如果时间有限，先做最小闭环：

1. `quality_chat` 重命名或映射为 `chat`。
2. 路由结果新增 `sub_route`。
3. `general_chat / rag_qa / quality_qa / task_create / inspection_execute` 五个子路径明确。
4. Prompt 抽成 `PromptBuilder`，先解决质检 Prompt 污染。
5. 输出 payload 增加 `agent / sub_route / ui_schema`。
6. Langfuse trace metadata 增加 `agent / sub_route / intent / prompt_version`。

这 6 步即可解决当前最明显的问题，并为后续物理拆分 Graph 留出空间。


---

## 15. 前端页面设计与改造方案

### 15.1 当前前端基础

当前前端已经具备比较完整的聊天页面能力，不需要推翻重做。现有 `ChatView.vue` 已经包含：

- 聊天模式切换：`auto / qa / inspection`
- RAG 空间选择
- 附件上传
- SSE 流式消息展示
- fallback polling
- 任务草稿表单
- 任务创建按钮
- 任务执行状态订阅
- 结果卡片展示
- trace 链接入口
- trust scoring 展示

当前路由中 `/app/chat` 对应 `ChatView.vue`，标题为“AI 检测对话”。因此前端改造重点不是新增页面，而是**让页面组件根据后端返回的 `agent / sub_route / ui_schema` 稳定渲染**。

### 15.2 前端页面分层

建议把 `ChatView.vue` 逐步拆成以下组件，先抽展示组件，不影响业务流程：

```text
frontend/src/views/ChatView.vue
frontend/src/components/chat/
  ChatToolbar.vue
  ChatMessageList.vue
  ChatMessageBubble.vue
  ChatInputBox.vue
  ChatAttachmentList.vue
  RagSpaceSelector.vue
  TaskDraftCard.vue
  TaskResultCard.vue
  QualitySignalCard.vue
  TraceLink.vue
```

职责划分：

| 组件 | 职责 |
|---|---|
| `ChatToolbar.vue` | 聊天模式、RAG 选择、Token 展示 |
| `ChatInputBox.vue` | 输入框、附件上传、发送 |
| `ChatMessageList.vue` | 消息列表、滚动到底部 |
| `ChatMessageBubble.vue` | 单条消息基础渲染 |
| `TaskDraftCard.vue` | `ui_schema=task_action_v1` |
| `TaskResultCard.vue` | `ui_schema=task_result_v1` |
| `QualitySignalCard.vue` | `ui_schema=quality_answer_v1` 中的质量指标 |
| `TraceLink.vue` | Langfuse trace 链接展示 |

### 15.3 聊天模式调整

当前前端模式是：

```ts
const chatMode = ref<"auto" | "qa" | "inspection">("auto");
```

建议调整为：

```ts
type ChatMode = "auto" | "chat" | "inspection";
```

展示文案：

```text
自动识别
聊天/知识库
质检/任务
```

原因：

- `qa` 容易让前端强制到旧的 `quality_chat`。
- 新架构中“普通问答 + 知识库问答”都属于 `ChatAgent`。
- “质检问答 + 任务创建 + 正式检测”都属于 `InspectionTaskAgent`。

发送消息时的 `route_hints` 建议改为：

```ts
const routeHints =
  chatMode.value === "inspection"
    ? { force_agent: "inspection_task" }
    : chatMode.value === "chat"
      ? { force_agent: "chat" }
      : undefined;
```

如果用户在“聊天/知识库”模式下选择了 RAG 空间，则后端内部进入：

```text
ChatAgent.rag_qa
```

如果用户在“质检/任务”模式下选择了 RAG 空间，则后端内部进入：

```text
InspectionTaskAgent.quality_qa
或
InspectionTaskAgent.inspection_execute
```

### 15.4 前端发送 payload 规范

前端发送消息时，`ext` 应保持为统一入口：

```json
{
  "ui_mode": "auto | chat | inspection",
  "route_hints": {
    "force_agent": "chat | inspection_task",
    "force_sub_route": "general_chat | rag_qa | quality_qa | task_create | inspection_execute"
  },
  "attachments": [],
  "selected_rag_space_id": "...",
  "selected_rag_space_name": "...",
  "selected_rag_space_description": "...",
  "selected_rag_space": {
    "id": "...",
    "name": "...",
    "description": "..."
  },
  "rag_scope": {
    "enabled": true,
    "rag_space_id": "...",
    "scope_node_ids": [],
    "scope_mode": "space"
  }
}
```

其中：

- `force_agent` 只控制一级 Agent。
- `force_sub_route` 可选，通常只用于调试或明确按钮。
- 不建议前端直接判断复杂业务意图。
- 前端只提供 UI 模式、附件、RAG 选择等事实信息。

### 15.5 前端消息类型扩展

当前 `ChatMessagePayload` 已经有 `agent_name / source_graph / route_decision / intent / quality / result_card / task_draft / created_task` 等字段。建议新增：

```ts
export type ChatAgentName = "chat" | "inspection_task";

export type ChatSubRoute =
  | "general_chat"
  | "rag_qa"
  | "quality_qa"
  | "task_create"
  | "inspection_execute";

export type ChatUiSchema =
  | "chat_text_v1"
  | "rag_answer_v1"
  | "quality_answer_v1"
  | "task_action_v1"
  | "task_result_v1"
  | "error_v1";
```

在 `ChatMessagePayload` 中新增：

```ts
agent?: ChatAgentName;
sub_route?: ChatSubRoute;
ui_schema?: ChatUiSchema;
trace_url?: string | null;
route_decision?: {
  selected_agent?: ChatAgentName;
  sub_route?: ChatSubRoute;
  intent?: string;
  confidence?: number;
  route_source?: string;
  reason?: string;
  requires_confirmation?: boolean;
};
```

兼容旧字段：

```ts
agent_name?: string | null;
source_graph?: string | null;
```

短期兼容策略：

```ts
function resolveAgent(payload: ChatMessagePayload) {
  return payload.agent || payload.agent_name || payload.source_graph || "";
}

function resolveSubRoute(payload: ChatMessagePayload) {
  return payload.sub_route || payload.intent || "";
}

function resolveUiSchema(message: ChatMessage) {
  if (message.payload?.ui_schema) return message.payload.ui_schema;
  if (message.message_type === "task_result") return "task_result_v1";
  if (message.message_type === "task_action") return "task_action_v1";
  if (message.message_type === "quality_answer") return "quality_answer_v1";
  if (message.payload?.citations?.length) return "rag_answer_v1";
  return "chat_text_v1";
}
```

### 15.6 前端渲染逻辑

不要再主要依赖 `message_type` 猜测展示方式，而是：

```text
优先 ui_schema
其次 message_type
最后 payload 字段兜底
```

推荐渲染分支：

```vue
<TaskDraftCard
  v-if="uiSchema === 'task_action_v1'"
  :message="message"
/>

<TaskResultCard
  v-else-if="uiSchema === 'task_result_v1'"
  :message="message"
/>

<QualitySignalCard
  v-else-if="uiSchema === 'quality_answer_v1'"
  :message="message"
/>

<RagAnswerCard
  v-else-if="uiSchema === 'rag_answer_v1'"
  :message="message"
/>

<ChatTextMessage
  v-else
  :message="message"
/>
```

这样不同功能的渲染边界清晰：

| ui_schema | 前端展示 |
|---|---|
| `chat_text_v1` | 普通文本 |
| `rag_answer_v1` | 文本 + 引用来源 |
| `quality_answer_v1` | 文本 + 质量指标 + 引用 |
| `task_action_v1` | 任务草稿 + 缺失字段 + 填表/确认按钮 |
| `task_result_v1` | 检测结果卡片 + 风险等级 + 查看任务 |
| `error_v1` | 错误提示 + trace |

### 15.7 前端与任务页面的关系

聊天页面不应该承载完整任务管理，只负责：

1. 从对话中生成任务草稿。
2. 确认后创建任务。
3. 显示任务启动结果。
4. 订阅任务流式状态。
5. 检测完成后展示摘要卡片。
6. 点击跳转到 `/app/tasks/:id` 查看完整任务详情。

任务详情页负责：

- 完整检测过程
- 时间线
- 图像/文件证据
- 检测结果
- 稳定性报告
- 人工复核
- 告警处理

### 15.8 前端最小改动清单

优先修改：

```text
frontend/src/types/chat.types.ts
frontend/src/views/ChatView.vue
frontend/src/stores/chat.store.ts
frontend/src/views/chat-task-actions.ts
```

最小改动：

1. `chatMode` 从 `auto | qa | inspection` 改成 `auto | chat | inspection`。
2. `qa` 模式不再发送 `force_agent: quality_chat`，改为 `force_agent: chat`。
3. `ChatMessagePayload` 新增 `agent / sub_route / ui_schema / trace_url`。
4. `agentLabel()` 兼容新旧字段。
5. 前端展示优先根据 `ui_schema` 渲染。
6. `hasTaskAction()` 判断逻辑增加 `ui_schema === task_action_v1`。
7. 结果卡片判断增加 `ui_schema === task_result_v1`。
8. trace 按 `payload.trace_url || payload.trust_scoring?.trace_url` 展示。

---

## 16. 后端服务设计与改造方案

### 16.1 当前后端基础

当前后端链路可以继续复用：

```text
chat.py API
  ↓
ChatService
  ↓
QualityAgentOrchestratorService
  ↓
AgentManagerService
  ↓
AgentManager
  ↓
QualityChatGraph / InspectionTaskGraph
  ↓
ChatMessageRepository.update_assistant_message
```

高效率改造不建议一开始大改所有服务，而是先做“语义重命名 + 路由字段下传 + Prompt 隔离”。

### 16.2 后端目标服务分层

推荐后端服务关系：

```text
API 层
  app/api/v1/chat.py
    - 会话接口
    - 消息发送
    - SSE stream
    - 附件上传
    - chat submit task

服务编排层
  app/services/chat_service.py
    - 保存 user message
    - 创建 assistant streaming message
    - 启动后台 workflow
    - 发布 SSE 事件

  app/services/agent_orchestrator_service.py
    - 统一调用 AgentManager
    - 持久化 AgentOutput
    - 写 route log / rag log / token usage
    - 构建最终 payload

Agent 管理层
  backend/agent/router/agent_manager.py
    - 一级路由
    - 分发 ChatAgent / InspectionTaskAgent

  backend/agent/router/route_policy.py
    - 规则优先
    - 模型兜底可插拔

Agent 执行层
  backend/agent/subgraphs/chat/
    - general_chat
    - rag_qa

  backend/agent/subgraphs/inspection_task/
    - quality_qa
    - task_create
    - inspection_execute

基础能力层
  PromptBuilder
  RagPolicy
  LLMClient
  LangfuseTracer
  ResponseBuilder
```

### 16.3 ChatService 的职责边界

`ChatService` 不应该知道具体业务意图，只处理聊天基础设施：

```text
ChatService 负责：
- 会话存在性校验
- user message 落库
- assistant streaming 占位消息落库
- ext 中 RAG 选择合法性校验
- 附件标准化
- SSE run_started / run_failed
- 调用 Orchestrator
```

`ChatService` 不应该负责：

```text
- 判断是普通聊天还是质检
- 拼 Prompt
- 执行 RAG
- 判断任务是否创建
- 生成检测结果
```

### 16.4 Orchestrator 改造

建议将 `QualityAgentOrchestratorService` 语义改为：

```text
AgentOrchestratorService
```

短期可以不改类名，只新增字段和逻辑。

职责：

1. 接收 `NormalizedRequest`。
2. 调用 `AgentManager.run()`。
3. 获取 `route_decision` 和 `agent_output`。
4. 调用 `ResponseBuilder` 构建统一 payload。
5. 写回 `chat_messages`。
6. 写入 `agent_route_logs`。
7. 写入 `rag_query_logs`。
8. 写入 token usage。
9. 发布 SSE `message_final`。

### 16.5 AgentManager 改造

当前 `AgentManager` 可以保留结构，只改目标 Agent：

```python
if decision.selected_agent == "inspection_task":
    agent_output = await self.inspection_task_agent.run(request, decision)
else:
    agent_output = await self.chat_agent.run(request, decision)
```

其中：

```text
chat_agent -> ChatAgent / ChatGraph
inspection_task_agent -> InspectionTaskAgent / InspectionTaskGraph
```

### 16.6 ChatAgent 后端设计

ChatAgent 内部子路径：

```text
general_chat
rag_qa
```

建议文件结构：

```text
backend/agent/subgraphs/chat/
  __init__.py
  graph.py
  state.py
  router.py
  nodes/
    history.py
    knowledge.py
    reasoning.py
    response_writer.py
```

最小实现可以复用旧 `QualityChatGraph` 的部分节点：

| 旧逻辑 | 新归属 |
|---|---|
| `smalltalk` | `ChatAgent.general_chat` |
| `general_qa` | `ChatAgent.general_chat` |
| `rag_qa` | `ChatAgent.rag_qa` |
| `history_loader` | 可复用 |
| `knowledge` 中普通 RAG | 可复用但 Prompt 改掉 |
| `response_writer` | 可复用 |

### 16.7 InspectionTaskAgent 后端设计

InspectionTaskAgent 内部子路径：

```text
quality_qa
task_create
inspection_execute
```

建议文件结构：

```text
backend/agent/subgraphs/inspection_task/
  __init__.py
  graph.py
  router.py
  state.py
  nodes/
    quality_qa.py
    task_create.py
    inspection_execute.py
    file_parse.py
    vision.py
    knowledge.py
    standard_gate.py
    finalizer.py
```

迁移关系：

| 旧逻辑 | 新归属 |
|---|---|
| `quality_qa` | `InspectionTaskAgent.quality_qa` |
| `quality_gate` | `InspectionTaskAgent.quality_qa` |
| `task_extractor` | `InspectionTaskAgent.task_create` |
| `task_executor` | `InspectionTaskAgent.task_create` 或 `inspection_execute` |
| `InspectionTaskGraph._run_structured_inspection` | `InspectionTaskAgent.inspection_execute` |
| `InspectionGraph planner → vision → knowledge → reasoning → finalizer` | `InspectionTaskAgent.inspection_execute` |

### 16.8 后端输出构建 ResponseBuilder

新增：

```text
backend/agent/response/response_builder.py
```

职责：

```python
class ResponseBuilder:
    def build_chat_payload(
        *,
        request: NormalizedRequest,
        route_decision: AgentRouteDecision,
        output: AgentOutput,
        trace: dict | None = None,
    ) -> dict:
        ...
```

统一补齐：

```json
{
  "agent": "chat",
  "sub_route": "rag_qa",
  "intent": "rag_qa",
  "message_type": "assistant_text",
  "ui_schema": "rag_answer_v1",
  "answer": "...",
  "summary": "...",
  "citations": [],
  "rag_summary": null,
  "quality": {},
  "task_draft": null,
  "created_task": null,
  "route_decision": {},
  "trace_id": "...",
  "trace_url": "...",
  "workflow_version": "chat_router_v2",
  "prompt_version": "chat_rag_qa_v1"
}
```

建议统一映射：

```python
UI_SCHEMA_MAP = {
    ("chat", "general_chat"): "chat_text_v1",
    ("chat", "rag_qa"): "rag_answer_v1",
    ("inspection_task", "quality_qa"): "quality_answer_v1",
    ("inspection_task", "task_create"): "task_action_v1",
    ("inspection_task", "inspection_execute"): "task_result_v1",
}
```

### 16.9 后端 API 是否需要变化

大部分 API 可以不变：

```text
POST /chat/sessions/{session_id}/messages
GET  /chat/sessions/{session_id}/stream
POST /chat/sessions/{session_id}/tasks/submit
POST /chat/uploads
```

需要变的是请求/响应 payload 字段，不一定要改 URL。

建议新增可选调试接口：

```text
POST /agent/route/preview
```

输入：

```json
{
  "message": "...",
  "ext": {}
}
```

输出：

```json
{
  "selected_agent": "inspection_task",
  "sub_route": "quality_qa",
  "confidence": 0.86,
  "route_source": "rule",
  "reason": "命中质检问答关键词"
}
```

这个接口用于前端调试、测试和运营排查，不进入正式业务链路。

---

## 17. 数据库表结构设计与改造方案

### 17.1 当前数据库基础

当前表结构已经有较好的 JSON 扩展空间：

```text
chat_sessions
chat_messages
chat_message_scores
agent_definitions
intent_routes
agent_route_logs
rag_query_logs
inspection_tasks
inspection_results
stability_reports
```

关键点：

- `chat_messages.payload` 是 JSON，适合先承载新增字段。
- `inspection_tasks.metadata` 是 JSON，适合保存来源聊天信息。
- `inspection_results.reasoning_chain` 是 JSON，适合保存检测推理链和 trace。
- `agent_route_logs` 已经存在，适合扩展路由审计。
- `rag_query_logs` 已经存在，适合扩展 RAG 监控。
- `chat_message_scores` 已经存在，适合保存信任评估和 Langfuse 同步状态。

因此不建议第一阶段大量建新表。应采用：

```text
先 JSON payload 扩展
再为高频查询字段升列
最后补充索引和统计表
```

### 17.2 chat_messages.payload 推荐结构

`chat_messages` 当前已有：

```text
id
session_id
org_id
user_id
seq_no
role
message_type
content
payload JSON
```

推荐 assistant message 的 `payload` 统一为：

```json
{
  "schema_version": "chat_payload_v2",
  "answer": "",
  "summary": "",
  "agent": "chat",
  "sub_route": "general_chat",
  "intent": "general_chat",
  "intent_confidence": 0.9,
  "message_type": "assistant_text",
  "ui_schema": "chat_text_v1",

  "route_decision": {
    "selected_agent": "chat",
    "sub_route": "general_chat",
    "intent": "general_chat",
    "confidence": 0.9,
    "requires_confirmation": false,
    "route_source": "rule",
    "reason": "默认普通聊天"
  },

  "citations": [],
  "rag_summary": null,
  "retrieval_metrics": null,

  "quality": {},
  "trust_scoring": null,

  "task_draft": null,
  "task_form_defaults": null,
  "missing_slots": [],
  "pending_action": null,
  "awaiting_confirmation": false,
  "created_task": null,
  "materialized_task": null,

  "result_card": null,
  "expectation_check": null,

  "trace_id": null,
  "trace_url": null,
  "observation_id": null,
  "workflow_run_id": "",
  "workflow_version": "chat_router_v2",
  "prompt_version": "chat_general_v1",

  "selected_rag_space": null,
  "attachment_echo": [],

  "status": "completed",
  "error": null
}
```

### 17.3 是否需要给 chat_messages 增加列

第一阶段不建议增加列，因为 `payload` 足够承载，风险最低。

第二阶段如果要做后台统计、筛选、监控，可以增加冗余列：

```sql
ALTER TABLE chat_messages
  ADD COLUMN agent_name VARCHAR(64) NULL,
  ADD COLUMN sub_route VARCHAR(64) NULL,
  ADD COLUMN ui_schema VARCHAR(64) NULL,
  ADD COLUMN trace_id VARCHAR(128) NULL,
  ADD COLUMN workflow_run_id VARCHAR(64) NULL,
  ADD INDEX idx_chat_messages_agent_route (org_id, agent_name, sub_route, created_at),
  ADD INDEX idx_chat_messages_trace (org_id, trace_id),
  ADD INDEX idx_chat_messages_workflow (org_id, workflow_run_id);
```

注意：

- 这些字段可以从 `payload` 同步写入。
- 不要删除 JSON payload 中的同名字段。
- 前端仍以 payload 为准。

### 17.4 agent_route_logs 扩展

当前 `agent_route_logs` 已有：

```text
org_id
user_id
session_id
request_id
selected_agent
intent_name
confidence
route_source
reason
```

建议扩展：

```sql
ALTER TABLE agent_route_logs
  ADD COLUMN sub_route VARCHAR(64) NULL,
  ADD COLUMN fallback_agent VARCHAR(64) NULL,
  ADD COLUMN requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN signals_json JSON NULL,
  ADD COLUMN model_output_json JSON NULL,
  ADD COLUMN latency_ms INT NOT NULL DEFAULT 0,
  ADD INDEX idx_route_logs_sub_route (org_id, selected_agent, sub_route, created_at),
  ADD INDEX idx_route_logs_intent_source (org_id, intent_name, route_source, created_at);
```

用途：

- 排查为什么某条消息走了某个 Agent。
- 统计路由准确率。
- 统计模型兜底比例。
- 查找低置信度路由样本。
- 后续做路由策略优化。

推荐 `signals_json`：

```json
{
  "has_rag_space": true,
  "has_image": false,
  "has_structured_file": false,
  "has_task_keyword": false,
  "has_quality_keyword": true,
  "attachment_types": [],
  "selected_rag_space_id": "...",
  "ui_mode": "auto"
}
```

### 17.5 rag_query_logs 扩展

当前 `rag_query_logs` 已有：

```text
org_id
task_id
session_id
user_id
query
rag_space_id
hit_count
hit_rate
citation_coverage
latency_ms
source_graph
metadata_json
```

建议扩展或规范 `metadata_json`：

```json
{
  "agent": "chat",
  "sub_route": "rag_qa",
  "intent": "rag_qa",
  "retrieval_policy": "selected_space_required",
  "top_k": 4,
  "top_score": 0.82,
  "empty_recall": false,
  "scope_node_ids": [],
  "prompt_version": "chat_rag_qa_v1",
  "trace_id": "...",
  "observation_id": "..."
}
```

可选升列：

```sql
ALTER TABLE rag_query_logs
  ADD COLUMN agent_name VARCHAR(64) NULL,
  ADD COLUMN sub_route VARCHAR(64) NULL,
  ADD COLUMN trace_id VARCHAR(128) NULL,
  ADD COLUMN top_score DECIMAL(8, 6) NULL,
  ADD INDEX idx_rag_logs_agent_route (org_id, agent_name, sub_route, created_at),
  ADD INDEX idx_rag_logs_trace (org_id, trace_id);
```

### 17.6 inspection_tasks.metadata 规范

当前 `inspection_tasks` 有 `metadata` JSON。建议统一保存任务来源：

```json
{
  "source": "chat",
  "source_agent": "inspection_task",
  "source_sub_route": "task_create",
  "chat_session_id": "...",
  "chat_source_message_id": "...",
  "assistant_message_id": "...",
  "request_id": "...",
  "workflow_run_id": "...",
  "route_decision": {},
  "selected_rag_space": {},
  "attachments": [],
  "execution": {
    "mode": "celery",
    "job_id": "...",
    "queued_at": "...",
    "started_at": "...",
    "finished_at": "..."
  }
}
```

这样任务页能反向跳回聊天上下文。

### 17.7 inspection_results.reasoning_chain 规范

正式检测结果应保存：

```json
{
  "agent": "inspection_task",
  "sub_route": "inspection_execute",
  "workflow_version": "inspection_execute_v1",
  "prompt_version": "inspection_execute_v1",
  "trace": {
    "trace_id": "...",
    "trace_url": "...",
    "model_key": "...",
    "task_id": "...",
    "org_id": "..."
  },
  "input_summary": {
    "product_id": "...",
    "spec_code": "...",
    "image_count": 3,
    "structured_file_count": 1
  },
  "rag_summary": {},
  "standard_evaluation": {},
  "quality": {},
  "result_card": {},
  "expectation_check": {}
}
```

### 17.8 新增可选表：chat_workflow_runs

如果后续要更强的链路追踪，可以新增 `chat_workflow_runs`。第一阶段非必须。

```sql
CREATE TABLE chat_workflow_runs (
  id BINARY(16) PRIMARY KEY,
  org_id BINARY(16) NOT NULL,
  user_id BINARY(16) NULL,
  session_id BINARY(16) NOT NULL,
  user_message_id BINARY(16) NULL,
  assistant_message_id BINARY(16) NULL,

  selected_agent VARCHAR(64) NOT NULL,
  sub_route VARCHAR(64) NOT NULL,
  intent_name VARCHAR(64) NOT NULL,
  route_source VARCHAR(32) NOT NULL,
  route_confidence DECIMAL(5,4) NOT NULL DEFAULT 0,

  status VARCHAR(32) NOT NULL DEFAULT 'running',
  trace_id VARCHAR(128) NULL,
  trace_url VARCHAR(512) NULL,
  prompt_version VARCHAR(64) NULL,
  workflow_version VARCHAR(64) NULL,

  input_json JSON NULL,
  output_json JSON NULL,
  error_message TEXT NULL,

  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  INDEX idx_chat_workflow_session (org_id, session_id, created_at),
  INDEX idx_chat_workflow_agent_route (org_id, selected_agent, sub_route, created_at),
  INDEX idx_chat_workflow_trace (org_id, trace_id)
);
```

使用场景：

- 工作流级别的状态追踪。
- 比 `chat_messages.payload` 更方便做监控统计。
- 支持失败重试。
- 支持后台运营分析。

但最小实现不需要这张表。

### 17.9 数据库改造优先级

| 优先级 | 改动 | 是否必须 |
|---|---|---|
| P0 | `chat_messages.payload` 写入 `agent/sub_route/ui_schema/route_decision` | 必须 |
| P0 | `agent_route_logs.metadata/signals` 规范化，或在现有字段基础上写 `selected_agent/intent/confidence` | 必须 |
| P0 | `rag_query_logs.metadata_json` 写入 `agent/sub_route/trace_id` | 必须 |
| P0 | `inspection_tasks.metadata` 写入聊天来源 | 必须 |
| P1 | `agent_route_logs` 增加 `sub_route/signals_json/model_output_json` | 推荐 |
| P1 | `chat_messages` 增加冗余列 `agent_name/sub_route/ui_schema/trace_id` | 推荐 |
| P2 | 新增 `chat_workflow_runs` | 可选 |
| P2 | 新增运营统计聚合表 | 可选 |

---

## 18. 前端、后端、数据库三者关系

### 18.1 一次普通聊天

```text
前端 ChatView
  发送 message + ui_mode=chat
        ↓
后端 ChatService
  写 user message
  写 assistant streaming placeholder
        ↓
AgentManager
  selected_agent=chat
  sub_route=general_chat
        ↓
ChatAgent.general_chat
  不检索 RAG
  使用 chat_general_v1 prompt
        ↓
ResponseBuilder
  ui_schema=chat_text_v1
        ↓
数据库 chat_messages.payload
  保存 answer/agent/sub_route/ui_schema/trace_id
        ↓
前端 SSE message_final
  按 chat_text_v1 渲染普通消息
```

### 18.2 一次知识库问答

```text
前端选择 RAG 空间
  selected_rag_space_id 写入 ext
        ↓
后端 ChatService
  校验 RAG 空间是否存在
        ↓
AgentManager
  selected_agent=chat
  sub_route=rag_qa
        ↓
ChatAgent.rag_qa
  RagPolicy=selected_space_required
  Retriever 检索用户选中的 RAG Space
  Prompt=chat_rag_qa_v1
        ↓
ResponseBuilder
  ui_schema=rag_answer_v1
  citations/rag_summary/retrieval_metrics
        ↓
数据库
  chat_messages.payload 保存答案和引用
  rag_query_logs 保存检索指标
        ↓
前端
  RagAnswerCard 展示引用来源
```

### 18.3 一次质检问答

```text
前端输入“这个缺陷怎么判定”
        ↓
AgentManager
  selected_agent=inspection_task
  sub_route=quality_qa
        ↓
InspectionTaskAgent.quality_qa
  RagPolicy=quality_standard_first
  检索标准库/选中知识库
  Prompt=inspection_quality_qa_v1
  quality_gate 评估证据覆盖和风险
        ↓
ResponseBuilder
  ui_schema=quality_answer_v1
  quality/citations/rag_summary
        ↓
数据库
  chat_messages.payload 保存质检问答结果
  agent_route_logs 保存路由
  rag_query_logs 保存检索
  chat_message_scores 异步保存可信评估
        ↓
前端
  QualitySignalCard 展示质量指标
```

### 18.4 一次任务创建

```text
前端输入“帮我创建检测任务”
        ↓
AgentManager
  selected_agent=inspection_task
  sub_route=task_create
        ↓
InspectionTaskAgent.task_create
  提取 product_id/spec_code/image_urls/priority
        ↓
如果缺字段：
  ResponseBuilder ui_schema=task_action_v1
  chat_messages.payload.task_draft/missing_slots
  前端 TaskDraftCard 展示填表按钮

如果字段完整：
  awaiting_confirmation=true
  前端展示确认并提交按钮
```

### 18.5 一次正式检测

```text
用户点击确认并提交
        ↓
前端调用 /chat/sessions/{id}/tasks/submit
        ↓
后端 TaskService.create_task
  写 inspection_tasks
  metadata 保存聊天来源
        ↓
launch_task_execution
  celery 或 local_background
        ↓
InspectionGraph / InspectionTaskAgent.inspection_execute
  文件解析 / 视觉检测 / RAG / 标准判定 / 稳定性分析
        ↓
数据库
  inspection_tasks.status
  inspection_results
  stability_reports
  alert
  token_ledger
        ↓
聊天页面追加 task_result
  chat_messages.payload.created_task/result_card
        ↓
前端 TaskResultCard 展示摘要
  可跳转 /app/tasks/:id
```

---

## 19. 迁移步骤与兼容策略

### 19.1 兼容旧字段

短期保留旧字段：

```json
{
  "agent_name": "quality_chat",
  "source_graph": "quality_judgement",
  "intent": "quality_qa"
}
```

同时新增新字段：

```json
{
  "agent": "inspection_task",
  "sub_route": "quality_qa",
  "ui_schema": "quality_answer_v1"
}
```

前端兼容顺序：

```text
payload.agent > payload.agent_name > payload.source_graph
payload.sub_route > payload.intent
payload.ui_schema > message_type 推断
```

### 19.2 数据迁移

历史消息不需要立即迁移，前端通过兜底逻辑可以继续渲染。

如果需要批量补齐，可写一次性脚本：

```python
for message in assistant_messages:
    payload = message.payload or {}
    if "agent" not in payload:
        payload["agent"] = infer_agent(payload)
    if "sub_route" not in payload:
        payload["sub_route"] = infer_sub_route(payload)
    if "ui_schema" not in payload:
        payload["ui_schema"] = infer_ui_schema(message.message_type, payload)
    message.payload = payload
```

推断规则：

```text
message_type=task_result -> inspection_task / inspection_execute / task_result_v1
message_type=task_action -> inspection_task / task_create / task_action_v1
message_type=quality_answer -> inspection_task / quality_qa / quality_answer_v1
intent=rag_qa -> chat / rag_qa / rag_answer_v1
否则 -> chat / general_chat / chat_text_v1
```

### 19.3 发布顺序

推荐发布顺序：

```text
1. 后端兼容新增 payload 字段
2. 前端兼容读取新旧字段
3. 后端路由改成 chat / inspection_task
4. PromptBuilder 接入
5. RagPolicy 接入
6. Langfuse metadata 接入
7. 可选数据库升列
8. 清理旧 quality_chat 命名
```

这样可以避免前后端同时强依赖导致页面不可用。

---

## 20. 文件级修改清单

### 20.1 前端

必须改：

```text
frontend/src/types/chat.types.ts
frontend/src/views/ChatView.vue
frontend/src/stores/chat.store.ts
frontend/src/views/chat-task-actions.ts
```

推荐新增：

```text
frontend/src/components/chat/TaskDraftCard.vue
frontend/src/components/chat/TaskResultCard.vue
frontend/src/components/chat/QualitySignalCard.vue
frontend/src/components/chat/RagAnswerCard.vue
frontend/src/components/chat/TraceLink.vue
frontend/src/utils/chat-rendering.ts
```

### 20.2 后端

必须改：

```text
backend/agent/router/contracts.py
backend/agent/router/route_policy.py
backend/agent/router/agent_manager.py
backend/app/services/quality_agent_orchestrator_service.py
backend/app/schemas/chat.py
backend/agent/contracts/quality_contracts.py
backend/agent/subgraphs/quality_chat/graph.py
backend/agent/subgraphs/inspection_task/graph.py
```

推荐新增：

```text
backend/agent/prompts/prompt_builder.py
backend/agent/prompts/chat.py
backend/agent/prompts/inspection.py
backend/agent/rag/rag_policy.py
backend/agent/response/response_builder.py
backend/agent/router/model_classifier.py
```

中期重构：

```text
backend/agent/subgraphs/chat/
backend/agent/subgraphs/inspection_task/router.py
```

### 20.3 数据库 / migration

P0 可以不建新表，只写 JSON。

P1 推荐新增 migration：

```text
backend/migrations/versions/xxxx_add_chat_route_observability_fields.py
```

内容：

```sql
ALTER TABLE agent_route_logs
  ADD COLUMN sub_route VARCHAR(64) NULL,
  ADD COLUMN fallback_agent VARCHAR(64) NULL,
  ADD COLUMN requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN signals_json JSON NULL,
  ADD COLUMN model_output_json JSON NULL,
  ADD COLUMN latency_ms INT NOT NULL DEFAULT 0;

ALTER TABLE rag_query_logs
  ADD COLUMN agent_name VARCHAR(64) NULL,
  ADD COLUMN sub_route VARCHAR(64) NULL,
  ADD COLUMN trace_id VARCHAR(128) NULL,
  ADD COLUMN top_score DECIMAL(8, 6) NULL;

ALTER TABLE chat_messages
  ADD COLUMN agent_name VARCHAR(64) NULL,
  ADD COLUMN sub_route VARCHAR(64) NULL,
  ADD COLUMN ui_schema VARCHAR(64) NULL,
  ADD COLUMN trace_id VARCHAR(128) NULL,
  ADD COLUMN workflow_run_id VARCHAR(64) NULL;
```

如果担心生产风险，则 `chat_messages` 升列可以放到 P2，仅依赖 payload。

---

## 21. 新增验收用例：前后端数据库联动

### 21.1 普通聊天

输入：

```text
你好，你能做什么？
```

期望：

```json
{
  "agent": "chat",
  "sub_route": "general_chat",
  "ui_schema": "chat_text_v1",
  "quality": {},
  "citations": []
}
```

数据库：

```text
chat_messages.message_type = assistant_text
chat_messages.payload.agent = chat
chat_messages.payload.sub_route = general_chat
agent_route_logs.selected_agent = chat
agent_route_logs.sub_route = general_chat
```

前端：

```text
渲染 ChatTextMessage
不显示质量指标
不显示任务草稿
```

### 21.2 普通知识库问答

输入：

```text
总结这个知识库
```

期望：

```json
{
  "agent": "chat",
  "sub_route": "rag_qa",
  "ui_schema": "rag_answer_v1",
  "citations": [...],
  "rag_summary": {...},
  "quality": {}
}
```

数据库：

```text
chat_messages.payload.selected_rag_space 存在
rag_query_logs.agent_name = chat
rag_query_logs.sub_route = rag_qa
```

前端：

```text
渲染 RagAnswerCard
显示引用
不显示质检风险
```

### 21.3 质检问答

输入：

```text
这个划痕算不算不合格？
```

期望：

```json
{
  "agent": "inspection_task",
  "sub_route": "quality_qa",
  "ui_schema": "quality_answer_v1",
  "quality": {...},
  "citations": [...]
}
```

数据库：

```text
agent_route_logs.selected_agent = inspection_task
agent_route_logs.sub_route = quality_qa
rag_query_logs.sub_route = quality_qa
chat_message_scores 可异步生成
```

前端：

```text
渲染 QualitySignalCard
显示质量指标和引用
不显示任务提交按钮，除非后端 pending_action=create_task
```

### 21.4 任务创建

输入：

```text
帮我创建检测任务，产品 FOOD-001
```

期望：

```json
{
  "agent": "inspection_task",
  "sub_route": "task_create",
  "ui_schema": "task_action_v1",
  "task_draft": {
    "product_id": "FOOD-001"
  },
  "missing_slots": ["spec_code", "image_urls"]
}
```

数据库：

```text
chat_messages.payload.task_draft 存在
chat_messages.payload.missing_slots 存在
暂不创建 inspection_tasks
```

前端：

```text
渲染 TaskDraftCard
显示填写并提交检测任务按钮
```

### 21.5 正式检测

操作：

```text
用户点击确认并提交任务
```

期望：

```text
inspection_tasks 新增记录
inspection_tasks.metadata.chat_session_id 存在
inspection_results 生成
stability_reports 生成
chat_messages 追加 task_result
```

前端：

```text
TaskResultCard 显示任务摘要
可跳转 /app/tasks/:id
```

---

## 22. 最终关系总结

```text
前端页面负责：
  - 收集输入、附件、RAG 选择、UI 模式
  - 展示不同 ui_schema
  - 提供任务确认和跳转入口

后端服务负责：
  - 保存会话消息
  - 一级 Agent 路由
  - Agent 内部子路径执行
  - Prompt / RAG / LLM / Langfuse / ResponseBuilder
  - 任务创建和检测执行

数据库负责：
  - chat_messages.payload 保存对话结果全量结构
  - agent_route_logs 保存路由审计
  - rag_query_logs 保存检索指标
  - inspection_tasks 保存正式任务
  - inspection_results 保存检测结果
  - stability_reports 保存稳定性风险
  - chat_message_scores 保存可信评估
```

最高效率落地策略：

```text
第一步：不动大表，先扩 payload。
第二步：前端按 ui_schema 渲染。
第三步：后端改成 chat / inspection_task 两级 Agent。
第四步：PromptBuilder 隔离提示词。
第五步：Langfuse metadata 标准化。
第六步：高频字段再升列建索引。
```
