# PIAP 平台最终版：高效 Manager Agent 路由循环与聊天/质检边界设计

> 目标：设计一个最终版本架构，不再以“聊天 Agent / 质量检测 Agent”二选一硬编码为核心，而是以 **Manager Agent 有限循环 + Capability Registry + Route Plan + Artifacts + ChatAgent 统一展示** 为核心。  
> 适用场景：聊天页面、质量检测任务页面、RAG 空间选择、图片/文件上传、后续新增多个能力 Agent。  
> 设计原则：聊天相关任务交给聊天 Agent；正式质量检测交给质量任务检测 Agent；其他能力 Agent 可以向聊天页面提供报告/数据/分析结果，但不能在聊天页面直接执行正式业务动作。

---

## 1. 最终目标

系统最终应形成以下结构：

```text
用户输入
  ↓
入口 API 根据页面来源设置 surface
  ↓
Manager Agent 有限循环
  ├─ 理解用户目标
  ├─ 制定 route_plan
  ├─ 路由到能力 Agent 执行
  ├─ 收集 artifacts / reports / observations
  ├─ 判断结果是否满足任务目标
  └─ 不满足则继续下一轮，满足则退出
  ↓
ChatAgent 负责最终自然语言回复和前端展示结构
  ↓
聊天页面 / 质量检测任务页面展示
```

核心变化是：

```text
旧模式：
一次路由 → 一个 Agent → 一次输出

最终模式：
Manager Agent 循环规划 → 可调用多个能力 Agent → 汇总结果 → ChatAgent 统一表达
```

---

## 2. 页面边界

### 2.1 聊天页面 surface=chat

聊天页面是统一交互入口，只允许执行：

```text
answer：生成自然语言回复
report：获取已有报告、检索结果、文件摘要、图片初步分析等
```

聊天页面不允许执行：

```text
action：创建正式任务、执行正式检测、写正式检测结果、触发正式业务动作
```

聊天页面可以处理：

```text
普通聊天
平台功能问答
RAG 问答
图片理解和初步判断
文件总结、文件问答
查询已有任务状态
查询已有检测报告
调用后续新增 Agent 获取报告信息
```

聊天页面不应处理：

```text
正式创建质量检测任务
正式执行质量检测任务
正式落库检测结果
正式生成稳定性结果、告警、质检结论记录
```

### 2.2 质量检测任务页面 surface=quality_task

质量检测任务页面是正式质量检测入口，允许执行：

```text
action：创建正式任务、执行正式检测、更新任务状态、落库正式结果
report：查询任务状态、读取已有检测结果
```

质量检测任务页面处理：

```text
产品编号
检测标准
检测图片
检测文件
优先级
RAG 空间作为检测依据
正式提交检测任务
正式执行检测任务
```

---

## 3. Agent 类型

最终系统不再写死“聊天 Agent / 质量检测 Agent / 数据分析 Agent”。应抽象成三类 Agent。

### 3.1 Manager Agent

职责：

```text
理解用户意图
识别页面来源 surface
识别允许的动作模式 allowed_modes
制定 route_plan
选择一个或多个能力 Agent
调用子 Agent
评估子 Agent 结果是否满足目标
必要时继续循环规划
最终交给 ChatAgent 组织回复
```

Manager Agent 不直接负责最终用户表达，而是负责调度和决策。

### 3.2 ChatAgent

职责：

```text
普通聊天
根据 artifacts 组织最终回复
展示报告摘要
解释能力 Agent 返回结果
生成前端 UI payload
告诉用户是否需要去正式任务页面创建任务
```

ChatAgent 不直接创建正式质检任务。

### 3.3 Capability Agent

能力 Agent 可以有很多种，不应在协议中写死，例如：

```text
file.summary
file.qa
image.understanding
rag.retrieve
rag.ingest
quality.report.query
quality.task.status
quality.inspection.execute
standard.explain
future.xxx.report
future.xxx.analysis
```

这些 Agent 可以向聊天页面提供 report，也可以在特定页面执行 action。

---

## 4. surface、mode 与权限约束

### 4.1 surface

```text
chat：聊天页面
quality_task：质量检测任务页面
admin：后台管理页面
batch：后台批处理任务
```

### 4.2 mode

```text
answer：生成最终回复
report：获取信息、报告、证据、摘要，不产生正式业务副作用
action：产生正式业务副作用，例如创建任务、执行检测、落库正式结果
```

### 4.3 默认权限

```json
{
  "chat": {
    "allowed_modes": ["answer", "report"],
    "forbidden_modes": ["action"]
  },
  "quality_task": {
    "allowed_modes": ["action", "report", "answer"],
    "forbidden_modes": []
  }
}
```

Manager Agent 必须先检查 mode 权限，再执行 route_plan。

---

## 5. Capability Registry

新增文件：

```text
backend/agent/router/capability_registry.py
```

定义所有能力。

### 5.1 Capability 定义

```py
from pydantic import BaseModel, Field
from typing import Any, Literal

class Capability(BaseModel):
    key: str
    agent: str
    operation: str
    mode: Literal["answer", "report", "action"]
    surfaces: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    cost_level: Literal["low", "medium", "high"] = "medium"
    allow_parallel: bool = True
    description: str = ""
```

### 5.2 初始能力注册

```py
CAPABILITIES = {
    "chat.general": Capability(
        key="chat.general",
        agent="chat",
        operation="answer",
        mode="answer",
        surfaces=["chat"],
        cost_level="low",
        description="普通聊天和平台功能问答",
    ),

    "chat.response.compose": Capability(
        key="chat.response.compose",
        agent="chat",
        operation="compose",
        mode="answer",
        surfaces=["chat", "quality_task"],
        cost_level="low",
        description="根据 artifacts 组织最终用户可读回复",
    ),

    "rag.retrieve": Capability(
        key="rag.retrieve",
        agent="rag",
        operation="retrieve",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="从用户选择的 RAG 空间检索证据",
    ),

    "file.summary": Capability(
        key="file.summary",
        agent="file",
        operation="summarize",
        mode="report",
        surfaces=["chat"],
        cost_level="medium",
        description="聊天页面文件总结",
    ),

    "file.qa": Capability(
        key="file.qa",
        agent="file",
        operation="qa",
        mode="report",
        surfaces=["chat"],
        cost_level="medium",
        description="基于聊天上传文件回答问题",
    ),

    "image.understanding": Capability(
        key="image.understanding",
        agent="vision",
        operation="understand",
        mode="report",
        surfaces=["chat"],
        cost_level="high",
        description="聊天页面图片理解和初步判断",
    ),

    "quality.report.query": Capability(
        key="quality.report.query",
        agent="quality_report",
        operation="query",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="查询已有质量检测报告",
    ),

    "quality.task.status": Capability(
        key="quality.task.status",
        agent="quality_report",
        operation="status",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="low",
        description="查询质量检测任务状态",
    ),

    "quality.inspection.execute": Capability(
        key="quality.inspection.execute",
        agent="inspection_task",
        operation="execute",
        mode="action",
        surfaces=["quality_task"],
        cost_level="high",
        description="正式质量检测执行，只允许质量检测任务页面调用",
    ),
}
```

### 5.3 Registry 权限校验

```py
def capability_allowed(capability: Capability, surface: str, allowed_modes: list[str]) -> bool:
    if surface not in capability.surfaces:
        return False
    if capability.mode not in allowed_modes:
        return False
    return True
```

---

## 6. Manager Agent 状态模型

新增文件：

```text
backend/agent/router/manager_state.py
```

### 6.1 状态结构

```py
class ManagerState(BaseModel):
    request_id: str
    workflow_run_id: str
    surface: str = "chat"

    original_query: str
    normalized_query: str = ""

    org_id: str
    user_id: str | None = None
    session_id: str | None = None

    attachments: list[dict[str, Any]] = Field(default_factory=list)
    selected_rag_space: dict[str, Any] | None = None
    rag_scope: dict[str, Any] | None = None

    allowed_modes: list[str] = Field(default_factory=lambda: ["answer", "report"])
    forbidden_modes: list[str] = Field(default_factory=list)

    goal: str = ""
    constraints: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)

    route_plan: "AgentRoutePlan | None" = None

    observations: list["AgentObservation"] = Field(default_factory=list)
    artifacts: list["AgentArtifact"] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)

    iteration: int = 0
    max_iterations: int = 3
    max_tool_calls: int = 5
    max_llm_calls: int = 3
    timeout_ms: int = 45000

    used_tool_calls: int = 0
    used_llm_calls: int = 0

    satisfied: bool = False
    satisfaction_score: float = 0.0
    final_action: str = "continue"  # continue | finish | ask_user | fail
```

---

## 7. Route Plan 结构

替代旧的单一 `selected_agent + sub_route`。

新增到：

```text
backend/agent/router/contracts.py
```

### 7.1 AgentPlanStep

```py
class AgentPlanStep(BaseModel):
    step_id: str
    capability_key: str
    agent: str
    operation: str
    mode: Literal["answer", "report", "action"]
    input: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: str | None = None
    required: bool = True
```

### 7.2 AgentRoutePlan

```py
class AgentRoutePlan(BaseModel):
    plan_id: str
    surface: str
    goal: str
    steps: list[AgentPlanStep]
    success_criteria: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    max_iterations: int = 3
```

### 7.3 Observation 与 Artifact

```py
class AgentObservation(BaseModel):
    step_id: str
    capability_key: str
    agent: str
    status: Literal["success", "failed", "blocked", "skipped"]
    summary: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)

class AgentArtifact(BaseModel):
    artifact_id: str
    type: str
    source_agent: str
    content: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    created_at: str | None = None
```

---

## 8. Manager Agent 有限循环

新增文件：

```text
backend/agent/router/manager_loop.py
```

### 8.1 总体流程

```text
initialize_state
  ↓
while not stop:
  understand
  plan
  validate_plan
  dispatch
  observe
  evaluate
  if satisfied:
      break
  if no_progress:
      break
  if budget_exhausted:
      break
compose_final
```

### 8.2 伪代码

```py
class ManagerLoop:
    async def run(self, request: NormalizedRequest, db_session=None) -> AgentRouterOutput:
        state = self._init_state(request)

        while self._can_continue(state):
            state.iteration += 1

            understanding = await self._understand(state)
            plan = await self._plan(state, understanding)
            state.route_plan = plan

            validation = self._validate_plan(state, plan)
            if not validation.allowed:
                state.errors.append(validation.to_error())
                state.final_action = "ask_user" if validation.need_user_input else "fail"
                break

            observations, artifacts = await self._dispatch(plan, state, db_session=db_session)
            state.observations.extend(observations)
            state.artifacts.extend(artifacts)

            evaluation = await self._evaluate(state, plan, observations, artifacts)
            state.satisfied = evaluation.satisfied
            state.satisfaction_score = evaluation.score
            state.final_action = evaluation.next_action

            if evaluation.satisfied:
                break

            if self._no_progress(state, evaluation):
                break

            if evaluation.next_action == "ask_user":
                break

            state = self._refine_for_next_round(state, evaluation)

        return await self._compose_final(state)
```

---

## 9. understand 阶段

### 9.1 输入

```text
用户原始问题
页面 surface
附件类型
是否选择 RAG 空间
历史摘要
当前允许的 mode
```

### 9.2 输出

```json
{
  "goal": "用户想查询某个检测报告并解释原因",
  "intent": "quality_report_query",
  "entities": {
    "task_id": null,
    "product_id": null,
    "time_range": "latest"
  },
  "needs": [
    "quality.report.query",
    "chat.response.compose"
  ],
  "missing_inputs": [],
  "risk": "low"
}
```

### 9.3 高效实现策略

普通请求可规则理解：

```text
你好 / 你是谁 / 能聊天吗 → chat.general
有附件且问总结 → file.summary
问报告 / 上次检测 / 失败原因 → quality.report.query
```

不确定时才调用模型理解。

---

## 10. plan 阶段

Manager Agent 根据理解结果和 Capability Registry 生成 route_plan。

### 10.1 示例：普通聊天

```json
{
  "surface": "chat",
  "goal": "回答普通聊天问题",
  "steps": [
    {
      "step_id": "s1",
      "capability_key": "chat.general",
      "agent": "chat",
      "operation": "answer",
      "mode": "answer",
      "input": {}
    }
  ],
  "success_criteria": ["生成非空回答"]
}
```

### 10.2 示例：聊天页查询检测报告

```json
{
  "surface": "chat",
  "goal": "查询已有检测报告并解释失败原因",
  "steps": [
    {
      "step_id": "s1",
      "capability_key": "quality.report.query",
      "agent": "quality_report",
      "operation": "query",
      "mode": "report",
      "input": {
        "scope": "latest"
      }
    },
    {
      "step_id": "s2",
      "capability_key": "chat.response.compose",
      "agent": "chat",
      "operation": "compose",
      "mode": "answer",
      "depends_on": ["s1"]
    }
  ],
  "success_criteria": [
    "找到相关报告",
    "能解释报告结论",
    "回答有来源"
  ]
}
```

### 10.3 示例：聊天页上传图片

```json
{
  "surface": "chat",
  "goal": "对图片进行非正式理解和初步判断",
  "steps": [
    {
      "step_id": "s1",
      "capability_key": "image.understanding",
      "agent": "vision",
      "operation": "understand",
      "mode": "report",
      "input": {
        "attachment_ids": ["..."]
      }
    },
    {
      "step_id": "s2",
      "capability_key": "chat.response.compose",
      "agent": "chat",
      "operation": "compose",
      "mode": "answer",
      "depends_on": ["s1"]
    }
  ],
  "success_criteria": [
    "图片分析成功",
    "明确说明非正式判断",
    "必要时建议进入质量检测任务页面"
  ]
}
```

### 10.4 示例：质量检测任务页正式执行

```json
{
  "surface": "quality_task",
  "goal": "正式执行质量检测任务",
  "steps": [
    {
      "step_id": "s1",
      "capability_key": "quality.inspection.execute",
      "agent": "inspection_task",
      "operation": "execute",
      "mode": "action",
      "input": {
        "task_id": "...",
        "product_id": "...",
        "spec_code": "...",
        "image_urls": [],
        "file_ids": [],
        "rag_space_id": "..."
      }
    }
  ],
  "success_criteria": [
    "正式任务创建或执行成功",
    "检测结果已落库",
    "任务状态更新"
  ]
}
```

---

## 11. validate_plan 阶段

Manager 必须检查：

```text
1. step 的 capability_key 是否存在
2. capability 是否允许当前 surface 调用
3. capability.mode 是否在 allowed_modes 内
4. 聊天页面是否包含 action，如果包含则阻止
5. 是否缺少必要输入
6. 是否超出 max_tool_calls / max_llm_calls
```

### 11.1 聊天页面阻止正式动作

```py
if state.surface == "chat" and any(step.mode == "action" for step in plan.steps):
    return blocked("聊天页面不允许执行正式业务动作")
```

阻止后应交给 ChatAgent 回复：

```text
这个操作需要在质量检测任务页面中执行。你可以前往任务页面创建正式检测任务。
```

---

## 12. dispatch 阶段

### 12.1 能力调用接口

所有能力 Agent 统一实现：

```py
class CapabilityExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        ...
```

### 12.2 并行执行

若多个 step 没有依赖关系且 `allow_parallel=True`，可并行：

```py
ready_steps = find_ready_steps(plan, completed_step_ids)
results = await asyncio.gather(
    *[executor.execute(step, state, db_session=db_session) for step in ready_steps]
)
```

### 12.3 去重执行

每个 step 生成 hash：

```text
step_hash = capability_key + operation + normalized_input
```

如果当前 ManagerLoop 中已经执行过相同 hash，则跳过，避免重复查询、重复检索、重复解析。

---

## 13. observe 阶段

子 Agent 不直接返回最终自然语言，而是返回结构化 observation 和 artifact。

### 13.1 报告查询 artifact

```json
{
  "artifact_id": "art_quality_report_001",
  "type": "quality_report",
  "source_agent": "quality_report",
  "content": {
    "task_id": "T123",
    "status": "done",
    "verdict": "FAIL",
    "summary": "划痕超过阈值",
    "reasons": ["scratch_over_limit"],
    "created_at": "..."
  },
  "citations": [],
  "confidence": 0.92
}
```

### 13.2 RAG artifact

```json
{
  "artifact_id": "art_rag_001",
  "type": "rag_hits",
  "source_agent": "rag",
  "content": {
    "hit_count": 3,
    "top_score": 0.82,
    "rag_space_id": "...",
    "hits": []
  },
  "citations": [],
  "confidence": 0.82
}
```

### 13.3 图片理解 artifact

```json
{
  "artifact_id": "art_image_001",
  "type": "image_understanding",
  "source_agent": "vision",
  "content": {
    "objects": [],
    "possible_defects": ["surface_scratch"],
    "risk": "medium",
    "informal": true
  },
  "confidence": 0.7
}
```

---

## 14. evaluate 阶段

评价阶段用于判断：

```text
当前 artifacts 是否足够回答用户
是否缺少关键信息
是否需要调用更多能力
是否应询问用户补充信息
是否应退出循环
```

### 14.1 规则优先

不建议每次都调用大模型评价。优先用规则：

```text
report.query：
- artifact.type == quality_report
- found == true
- verdict 非空
→ satisfied

rag.retrieve：
- hit_count > 0
- top_score 达到阈值
→ evidence_sufficient

file.summary：
- parsed_text 非空
- summary 非空
→ satisfied

image.understanding：
- vision_result 非空
→ satisfied

inspection.execute：
- task_id 非空
- status in queued/running/done
→ satisfied
```

### 14.2 模型评价只用于复杂情况

以下情况可调用模型评价：

```text
多个 Agent 结果冲突
报告存在但是否回答了用户问题不明确
用户问题复杂，需要判断是否还要调用 RAG
图片分析和 RAG 证据不一致
```

### 14.3 Evaluation 输出

```json
{
  "satisfied": true,
  "score": 0.86,
  "next_action": "finish",
  "reason": "已经找到报告并能解释失败原因",
  "missing_inputs": [],
  "recommended_next_capabilities": []
}
```

不满意时：

```json
{
  "satisfied": false,
  "score": 0.42,
  "next_action": "continue",
  "reason": "只找到了任务状态，但没有找到检测报告详情",
  "recommended_next_capabilities": ["quality.report.query"]
}
```

需要用户补充：

```json
{
  "satisfied": false,
  "score": 0.3,
  "next_action": "ask_user",
  "reason": "缺少任务编号，无法定位报告",
  "missing_inputs": ["task_id"]
}
```

---

## 15. 循环停止条件

必须避免无限循环。最终版本使用有限循环。

### 15.1 停止条件

```text
1. satisfied == true
2. iteration >= max_iterations
3. used_tool_calls >= max_tool_calls
4. used_llm_calls >= max_llm_calls
5. timeout exceeded
6. next_action == ask_user
7. 连续两轮没有新增 artifact
8. 连续两轮 route_plan hash 相同
9. 所有可用能力都已执行但仍不满足
10. 出现不可恢复错误
```

### 15.2 默认预算

```json
{
  "chat": {
    "max_iterations": 2,
    "max_tool_calls": 3,
    "max_llm_calls": 2,
    "timeout_ms": 30000
  },
  "quality_task": {
    "max_iterations": 5,
    "max_tool_calls": 8,
    "max_llm_calls": 5,
    "timeout_ms": 60000
  }
}
```

---

## 16. RAG 设计

RAG 是共享能力，不是固定路由目标。

### 16.1 用户选择 RAG 空间的含义

```text
选择 RAG 空间 = 给 Manager Agent 一个可用知识源
是否调用 RAG = Manager Agent 根据当前任务决定
```

不能写成：

```text
只要选择 RAG 空间 → 必定走 RAG 问答
```

### 16.2 聊天页面 RAG

用于：

```text
基于知识库回答
解释标准
总结资料
辅助报告解释
辅助图片初步判断
```

输出 mode 为 `report` 或由 ChatAgent 组合成 `answer`。

### 16.3 质量检测任务页面 RAG

用于：

```text
正式检测依据
标准条款检索
证据片段引用
检测结果解释
```

可以作为 `quality.inspection.execute` 的输入。

---

## 17. 图片上传处理

### 17.1 聊天页面图片

```text
surface=chat
mode=report
capability=image.understanding
```

结果是非正式判断：

```text
这是基于聊天图片理解的初步判断，不等同于正式质检结果。
如需正式检测，请到质量检测任务页面创建任务。
```

不允许创建正式任务。

### 17.2 质量检测任务页面图片

```text
surface=quality_task
mode=action
capability=quality.inspection.execute
```

图片作为正式检测证据，可以落库任务和结果。

---

## 18. 文件上传处理

### 18.1 聊天页面文件

聊天文件默认是 `chat_context`，不是正式检测证据。

处理方式：

```text
用户问总结 → file.summary
用户问文件内容 → file.qa
用户问把文件加入知识库 → rag.ingest，需要确认
用户问结合文件和报告解释 → file.qa + quality.report.query + chat.response.compose
```

文件解析结果作为 artifact 给 ChatAgent 使用。

### 18.2 质量检测任务页面文件

任务页面文件作为正式检测输入：

```text
surface=quality_task
capability=quality.inspection.execute
mode=action
```

文件可作为：

```text
结构化检测记录
检测证据
标准补充材料
```

---

## 19. ChatAgent 最终回复

Manager Agent 最终不直接把 observation 返回给用户。它应调用：

```text
chat.response.compose
```

ChatAgent 根据：

```text
original_query
route_plan
observations
artifacts
surface
citations
warnings
missing_inputs
```

生成最终回复。

### 19.1 最终回复 payload

```json
{
  "answer": "...",
  "summary": "...",
  "message_type": "assistant_text | report_answer | image_analysis | file_answer | task_status",
  "artifacts": [],
  "citations": [],
  "route_trace": {
    "iterations": 2,
    "capabilities_used": ["quality.report.query", "chat.response.compose"],
    "satisfied": true
  },
  "ui_schema": "chat_answer_v2"
}
```

---

## 20. 安全与权限控制

### 20.1 聊天页禁止 action

任何 action 能力在 `surface=chat` 下必须被阻止。

### 20.2 正式任务必须显式提交

正式质量检测任务必须来自质量检测任务页面，并带明确字段：

```json
{
  "surface": "quality_task",
  "action_intent": "quality_inspection_execute"
}
```

### 20.3 用户确认

以下操作需要确认：

```text
RAG 入库
正式创建任务
正式执行检测
删除数据
更新标准
发送通知
```

---

## 21. 高效实现关键点

### 21.1 轻路由优先

简单任务不进入复杂多轮：

```text
普通聊天 → chat.general，一轮结束
文件总结 → file.summary + compose，一轮结束
报告查询 → quality.report.query + compose，一轮结束
复杂任务 → 多轮
```

### 21.2 结构化状态而非长文本思维链

不要把完整思维链作为运行依赖。保存：

```text
goal
route_plan
observations
evaluation_summary
artifacts
decision_reason
```

这样可调试、可审计、高效。

### 21.3 并行执行

无依赖 report 能力并行执行。

### 21.4 去重执行

相同 capability + input 不重复执行。

### 21.5 预算控制

每轮限制：

```text
max_iterations
max_tool_calls
max_llm_calls
timeout_ms
```

### 21.6 缓存

推荐缓存：

```text
模型配置短缓存
Prompt 短缓存
RAG embedding 缓存
RAG 检索结果缓存
文件解析结果缓存
Agent runtime guard 短缓存
```

---

## 22. 后端目录设计

```text
backend/agent/router/
  contracts.py
  capability_registry.py
  manager_state.py
  manager_loop.py
  manager_policy.py
  manager_evaluator.py
  manager_dispatcher.py
  executors/
    chat_executor.py
    rag_executor.py
    file_executor.py
    vision_executor.py
    quality_report_executor.py
    inspection_task_executor.py
```

### 22.1 manager_loop.py

负责主循环。

### 22.2 manager_policy.py

负责理解和计划。

### 22.3 manager_dispatcher.py

负责执行 route_plan 中的 steps。

### 22.4 manager_evaluator.py

负责判断结果是否满意。

### 22.5 executors

把 capability_key 映射到具体 Agent / service。

---

## 23. 前端协议

### 23.1 聊天页面请求

```json
{
  "schema_version": "2.0.0",
  "workspace": "app",
  "message": "帮我看看上次检测报告为什么失败",
  "ext": {
    "surface": "chat",
    "allowed_modes": ["answer", "report"],
    "forbidden_modes": ["action"],
    "attachments": [],
    "selected_rag_space": {
      "id": "...",
      "name": "..."
    },
    "rag_scope": {
      "enabled": true,
      "rag_space_id": "...",
      "scope_mode": "space",
      "mode": "auto"
    }
  }
}
```

### 23.2 质量检测任务页面请求

```json
{
  "schema_version": "2.0.0",
  "workspace": "quality_task",
  "message": "执行质量检测",
  "metadata": {
    "product_id": "P001",
    "spec_code": "GB-XXX",
    "priority": 5
  },
  "ext": {
    "surface": "quality_task",
    "allowed_modes": ["action", "report", "answer"],
    "action_intent": "quality_inspection_execute",
    "selected_rag_space_id": "...",
    "rag_scope": {
      "enabled": true,
      "rag_space_id": "...",
      "scope_mode": "space",
      "mode": "auto"
    }
  }
}
```

---

## 24. AgentManager.run 最终形态

旧逻辑：

```text
decide → if inspection_task else chat
```

最终逻辑：

```py
class AgentManager:
    def __init__(self) -> None:
        self._loop = ManagerLoop()

    async def run(self, request: NormalizedRequest, db_session=None) -> AgentRouterOutput:
        return await self._loop.run(request, db_session=db_session)
```

---

## 25. 典型流程示例

### 25.1 聊天问普通问题

```text
用户：你能做什么？
surface=chat
Manager:
  plan = chat.general
ChatAgent:
  直接回答平台能力
```

### 25.2 聊天上传图片

```text
用户：这个图片有没有问题？
surface=chat
Manager:
  plan = image.understanding → chat.response.compose
VisionAgent:
  返回初步视觉判断 artifact
ChatAgent:
  说明可能问题，并提示非正式判断
```

### 25.3 聊天查询检测报告

```text
用户：帮我看看上次检测报告为什么失败
surface=chat
Manager:
  plan = quality.report.query → chat.response.compose
QualityReportAgent:
  返回最近报告 artifact
ChatAgent:
  解释失败原因
```

### 25.4 聊天选中 RAG 问标准

```text
用户：根据这个知识库，AQL 是什么意思？
surface=chat
Manager:
  plan = rag.retrieve → chat.response.compose
RAG:
  返回相关片段
ChatAgent:
  组织回答和引用
```

### 25.5 质量检测任务页正式检测

```text
用户提交任务表单
surface=quality_task
Manager:
  plan = quality.inspection.execute
InspectionTaskAgent:
  创建任务、执行检测、落库结果
Task Page:
  展示正式检测结果
```

---

## 26. 最终结论

最终版本应实现为：

```text
Manager Agent 有限循环
+ Capability Registry
+ Route Plan
+ Artifacts
+ 规则优先的结果评价
+ 必要时模型评价
+ ChatAgent 统一回复
+ surface/mode 权限控制
```

最重要的边界是：

```text
聊天页面：
只能 answer/report，不能 action。

质量检测任务页面：
可以 action，负责正式质量检测。

RAG：
是共享能力，不是固定路由目标。

图片/文件：
聊天页作为上下文资产和非正式分析；
任务页作为正式检测证据。

新增 Agent：
不改聊天页面，只在 Capability Registry 注册能力，由 Manager Agent 动态规划调用。
```

一句话总结：

> 最终系统不是“聊天 Agent 和检测 Agent 二选一”，而是“Manager Agent 根据页面边界和任务目标动态规划能力调用，所有结果最终由 ChatAgent 组织展示，正式检测只允许在质量检测任务页面触发”。
