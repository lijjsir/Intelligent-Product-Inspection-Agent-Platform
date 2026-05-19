# Chat Agent Routing Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor chat routing from ambiguous `quality_chat`/`inspection_task` to clean `chat`/`inspection_task` with 5 sub-routes, isolated prompts per flow, per-route RAG policies, unified response protocol, and Langfuse trace standardization.

**Architecture:** Two-tier routing — AgentManager does coarse `chat` vs `inspection_task` dispatch; each agent internally routes to specific sub-routes (`general_chat`, `rag_qa`, `quality_qa`, `task_create`, `inspection_execute`). PromptBuilder isolates prompts per sub-route. RagPolicy decides retrieval per sub-route. ResponseBuilder returns unified payload. Model classifier handles ambiguous inputs.

**Tech Stack:** Python/FastAPI backend, Vue3/TypeScript frontend, LangGraph subgraphs, Langfuse observability

---

### Task 1: Update Route Contracts — AgentRouteDecision with sub_route

**Files:**
- Modify: `backend/agent/router/contracts.py:8-16`

- [ ] **Step 1: Update AgentRouteDecision model**

```python
class AgentRouteDecision(BaseModel):
    """AgentManager 路由决策结果"""
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

- [ ] **Step 2: Verify no import errors**

Run: `cd backend && python -c "from agent.router.contracts import AgentRouteDecision; d = AgentRouteDecision(); print(d.selected_agent, d.sub_route)"`
Expected: `chat general_chat`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/router/contracts.py
git commit -m "feat: update AgentRouteDecision with sub_route and chat/inspection_task agents

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Add Quality/Inspection Signal Detection to Route Policy

**Files:**
- Modify: `backend/agent/router/route_policy.py`

- [ ] **Step 1: Add quality QA and general RAG signal patterns**

Add after `TASK_INTENT_PATTERNS` (line 31):

```python
QUALITY_QA_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"质量|质检|缺陷|不合格|合格|判定|标准|规范|划痕|瑕疵",
        r"(这个|那个).{0,4}(算不算|是不是|能不能).{0,4}(缺陷|不合格|有问题)",
        r"(怎么|如何).{0,6}(判定|判断|检测|评估)",
        r"GB/T|ISO|标准.{0,4}要求|规范.{0,4}规定",
        r"(什么|哪些).{0,4}(情况|时候).{0,4}(缺陷|不合格|处理)",
        r"检测标准|质量要求|判定依据|判定规则",
    ]
]

GENERAL_RAG_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"总结|概括|归纳.{0,4}(文档|知识库|资料|这份)",
        r"(文档|知识库|资料).{0,4}(说什么|讲什么|内容|主要)",
        r"根据.{0,4}(文档|知识库|资料|选中)",
        r"(查|找|搜索).{0,4}(文档|知识库)",
        r"知识库|参考资料|参考文档",
    ]
]
```

- [ ] **Step 2: Add signal detection helper methods to AgentRoutePolicy**

Add methods to `AgentRoutePolicy` class:

```python
def _has_quality_signal(self, query: str) -> bool:
    return any(p.search(query) for p in QUALITY_QA_PATTERNS)

def _has_general_rag_signal(self, query: str) -> bool:
    return any(p.search(query) for p in GENERAL_RAG_PATTERNS)

def _has_selected_rag_space(self, ext: dict) -> bool:
    rag = ext.get("selected_rag_space") or {}
    return bool(rag.get("id"))

def _is_ambiguous(self, query: str) -> bool:
    """检测模糊输入：短句、代词多、无明确信号"""
    if not query or len(query) < 4:
        return True
    ambiguous_patterns = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"^(这个|那个|它|他|她)$",
            r"^(看看|帮我看看|看一下|处理一下|怎么办|有问题吗|能不能过)$",
            r"^(这个|那个).{0,3}(呢|吗|吧|啊)?$",
        ]
    ]
    return any(p.search(query.strip()) for p in ambiguous_patterns)
```

- [ ] **Step 3: Rewrite decide() method with new routing logic**

Replace the `decide()` method:

```python
def decide(self, input_data: AgentRouterInput) -> AgentRouteDecision:
    query = str(input_data.query or "").strip()
    attachments = list(input_data.attachments or [])
    image_urls = list(input_data.image_urls or [])
    ext = dict(input_data.ext or {})
    route_hints = {
        **dict(input_data.route_hints or {}),
        **dict(ext.get("route_hints") or {}),
    }

    # ── Manual override: force_agent ──
    if route_hints.get("force_agent") == "inspection_task":
        forced_sub = route_hints.get("force_sub_route") or "task_create"
        return AgentRouteDecision(
            selected_agent="inspection_task",
            sub_route=forced_sub,
            intent=forced_sub,
            reason="前端强制指定检测 Agent",
            route_source="manual",
        )
    if route_hints.get("force_agent") == "chat":
        forced_sub = route_hints.get("force_sub_route") or "general_chat"
        return AgentRouteDecision(
            selected_agent="chat",
            sub_route=forced_sub,
            intent=forced_sub,
            reason="前端强制指定聊天 Agent",
            route_source="manual",
        )
    # Compat: old force_agent values
    if route_hints.get("force_agent") == "quality_chat":
        return AgentRouteDecision(
            selected_agent="chat",
            sub_route="general_chat",
            intent="general_chat",
            reason="旧版 quality_chat 映射为 chat.general_chat",
            route_source="manual",
        )

    # ── Attachment type detection ──
    has_structured_file = False
    has_image_attachment = False
    for item in attachments:
        name = str(item.get("name") or "").lower()
        suffix = name.rsplit(".", 1)[-1] if "." in name else ""
        if suffix in STRUCTURED_FILE_EXTENSIONS:
            has_structured_file = True
        if suffix in IMAGE_EXTENSIONS or item.get("kind") == "image":
            has_image_attachment = True

    has_task_signal = any(p.search(query) for p in TASK_INTENT_PATTERNS)
    has_quality_signal = self._has_quality_signal(query)
    has_rag_space = self._has_selected_rag_space(ext)
    has_rag_signal = self._has_general_rag_signal(query)
    is_ambiguous = self._is_ambiguous(query)

    # 1. 结构化文件 + 检测意图 → inspection_execute
    if has_structured_file and (has_task_signal or has_quality_signal):
        return AgentRouteDecision(
            selected_agent="inspection_task",
            sub_route="inspection_execute",
            intent="inspection_execute",
            reason="结构化文件 + 检测意图",
            route_source="rule",
        )

    # 2. 图片 + 检测意图 → inspection_execute
    if (has_image_attachment or image_urls) and (has_task_signal or has_quality_signal):
        return AgentRouteDecision(
            selected_agent="inspection_task",
            sub_route="inspection_execute",
            intent="inspection_execute",
            reason="图片 + 检测意图",
            route_source="rule",
        )

    # 3. 明确任务创建意图 → task_create
    if has_task_signal and not has_quality_signal:
        return AgentRouteDecision(
            selected_agent="inspection_task",
            sub_route="task_create",
            intent="task_create",
            reason="检测到任务创建意图关键词",
            route_source="rule",
        )

    # 4. 质检问答语义 → quality_qa
    if has_quality_signal:
        return AgentRouteDecision(
            selected_agent="inspection_task",
            sub_route="quality_qa",
            intent="quality_qa",
            reason="检测到质检问答语义",
            route_source="rule",
        )

    # 5. 选中RAG空间 或 明确知识库意图 → chat.rag_qa
    if has_rag_space or has_rag_signal:
        return AgentRouteDecision(
            selected_agent="chat",
            sub_route="rag_qa",
            intent="rag_qa",
            reason="选中知识库或知识库问答意图",
            route_source="rule",
        )

    # 6. 模糊输入 → 标记需要模型分类
    if is_ambiguous:
        return AgentRouteDecision(
            selected_agent="chat",
            sub_route="general_chat",
            intent="general_chat",
            confidence=0.5,
            reason="模糊输入，建议模型兜底分类",
            route_source="rule",
            requires_confirmation=False,
            fallback_agent="model_classifier",
        )

    # 7. 默认 → chat.general_chat
    return AgentRouteDecision(
        selected_agent="chat",
        sub_route="general_chat",
        intent="general_chat",
        confidence=0.85,
        reason="默认普通聊天",
        route_source="rule",
    )
```

- [ ] **Step 4: Verify routing logic**

Run: `cd backend && python -c "
from agent.router.route_policy import AgentRoutePolicy
from agent.router.contracts import AgentRouterInput
p = AgentRoutePolicy()
# Test general chat
d1 = p.decide(AgentRouterInput(query='你好'))
assert d1.selected_agent == 'chat' and d1.sub_route == 'general_chat', f'FAIL: {d1}'
# Test quality QA
d2 = p.decide(AgentRouterInput(query='这个缺陷算不算不合格'))
assert d2.selected_agent == 'inspection_task' and d2.sub_route == 'quality_qa', f'FAIL: {d2}'
# Test task create
d3 = p.decide(AgentRouterInput(query='帮我创建检测任务'))
assert d3.selected_agent == 'inspection_task' and d3.sub_route == 'task_create', f'FAIL: {d3}'
# Test RAG
d4 = p.decide(AgentRouterInput(query='总结这个知识库'))
assert d4.selected_agent == 'chat' and d4.sub_route == 'rag_qa', f'FAIL: {d4}'
# Test ambiguous
d5 = p.decide(AgentRouterInput(query='这个呢'))
assert d5.fallback_agent == 'model_classifier', f'FAIL: {d5}'
print('All routing tests passed')
"`

- [ ] **Step 5: Commit**

```bash
git add backend/agent/router/route_policy.py
git commit -m "feat: add quality/rag signal detection and 7-level routing rules

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Update AgentManager to Pass sub_route to Agents

**Files:**
- Modify: `backend/agent/router/agent_manager.py`

- [ ] **Step 1: Pass sub_route in agent dispatch**

Replace the `run()` method:

```python
async def run(self, request: NormalizedRequest) -> AgentRouterOutput:
    router_input = AgentRouterInput(
        query=request.query,
        request_kind=request.request_kind,
        attachments=[item.model_dump() for item in request.attachments],
        image_urls=request.image_urls,
        route_hints=request.route_hints,
        ext=request.ext,
    )

    decision = self._route_policy.decide(router_input)

    try:
        if decision.selected_agent == "inspection_task":
            agent_output = await self.task_agent.run(request, decision)
        else:
            agent_output = await self.chat_agent.run(request, decision)
    except Exception as exc:
        logger.exception("Agent execution failed: agent=%s sub_route=%s", decision.selected_agent, decision.sub_route)
        return AgentRouterOutput(
            route_decision=decision,
            agent_output={
                "message_type": "agent_route_failed",
                "answer": f"Agent 执行失败：{str(exc)}",
                "route_decision": decision.model_dump(),
            },
            status="failed",
            degrade_reason=str(exc),
        )

    return AgentRouterOutput(
        route_decision=decision,
        agent_output=agent_output if isinstance(agent_output, dict) else agent_output.model_dump(),
        status="completed",
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/router/agent_manager.py
git commit -m "feat: pass sub_route through AgentManager dispatch

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Create Model Classifier for Ambiguous Inputs

**Files:**
- Create: `backend/agent/router/model_classifier.py`

- [ ] **Step 1: Write the module**

```python
from __future__ import annotations

import json
import logging
from typing import Any

from agent.router.contracts import AgentRouteDecision

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """你是 PIAP 平台的消息路由分类器。
只根据用户输入判断它属于哪种意图，不生成回答。

输出严格 JSON：
{
  "selected_agent": "chat" | "inspection_task",
  "sub_route": "general_chat" | "rag_qa" | "quality_qa" | "task_create" | "inspection_execute",
  "confidence": 0.0 ~ 1.0,
  "reason": "简短理由"
}

分类标准：
- general_chat: 普通闲聊、问候、平台功能询问，无质检/任务/知识库意图
- rag_qa: 想查询知识库、总结文档、根据资料回答问题，无质检信号
- quality_qa: 询问质量判定、缺陷标准、是否合格、检测规范
- task_create: 想创建检测任务、发起质检流程
- inspection_execute: 上传了文件/图片并明确要进行检测
"""


class ModelClassifier:
    """小模型兜底分类器，仅用于规则无法确定的模糊输入。"""

    async def classify(
        self,
        query: str,
        llm_client: Any,  # LLMClient instance
        ext: dict[str, Any] | None = None,
    ) -> AgentRouteDecision:
        ext = ext or {}
        has_rag_space = bool((ext.get("selected_rag_space") or {}).get("id"))
        has_attachments = bool(ext.get("attachments"))

        user_context = f"用户输入: {query}"
        if has_rag_space:
            user_context += "\n[用户已选择RAG知识库]"
        if has_attachments:
            user_context += "\n[用户上传了附件]"

        try:
            result = await llm_client.chat(
                system_prompt=CLASSIFIER_SYSTEM_PROMPT,
                user_message=user_context,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            data = json.loads(result.get("content", "{}"))
            return AgentRouteDecision(
                selected_agent=data.get("selected_agent", "chat"),
                sub_route=data.get("sub_route", "general_chat"),
                intent=data.get("sub_route", "general_chat"),
                confidence=float(data.get("confidence", 0.5)),
                reason=str(data.get("reason", "模型分类")),
                route_source="model",
            )
        except Exception as exc:
            logger.warning("Model classifier failed, fallback to general_chat: %s", exc)
            return AgentRouteDecision(
                selected_agent="chat",
                sub_route="general_chat",
                intent="general_chat",
                confidence=0.3,
                reason=f"模型分类失败回退: {exc}",
                route_source="fallback",
            )
```

- [ ] **Step 2: Integrate classifier into AgentRoutePolicy.decide()**

In `route_policy.py`, modify the `decide` method signature and add model fallback at the ambiguous case:

Add at top of file:
```python
from agent.router.model_classifier import ModelClassifier
```

Change the ambiguous case in `decide()` (step 6) to accept an optional model classifier parameter. Add a new method:

```python
async def decide_with_model(
    self,
    input_data: AgentRouterInput,
    llm_client=None,
) -> AgentRouteDecision:
    decision = self.decide(input_data)
    if decision.fallback_agent == "model_classifier" and llm_client is not None:
        classifier = ModelClassifier()
        return await classifier.classify(
            query=input_data.query,
            llm_client=llm_client,
            ext=input_data.ext,
        )
    return decision
```

- [ ] **Step 3: Verify classifier import**

Run: `cd backend && python -c "from agent.router.model_classifier import ModelClassifier; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add backend/agent/router/model_classifier.py backend/agent/router/route_policy.py
git commit -m "feat: add model classifier for ambiguous routing fallback

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Create PromptBuilder — Chat Prompts

**Files:**
- Create: `backend/agent/prompts/__init__.py`
- Create: `backend/agent/prompts/chat.py`

- [ ] **Step 1: Create __init__.py**

```python
from agent.prompts.prompt_builder import PromptBuilder

__all__ = ["PromptBuilder"]
```

- [ ] **Step 2: Create chat.py with general_chat and rag_qa prompts**

```python
from __future__ import annotations

CHAT_GENERAL_V1 = """你是 PIAP 平台的通用聊天助手。
你可以解释平台功能、普通问题、知识库使用方式和检测任务入口。
如果用户没有提出质检、任务创建、知识库引用需求，不要主动输出质检判定、检测标准、风险等级、缺陷结论等内容。
回答应自然、简洁、面向用户操作。
只返回 JSON：{"answer": string, "summary": string}。"""

CHAT_RAG_QA_V1 = """你是知识库问答助手。
请基于检索到的知识库内容回答用户的问题。
不要套用质量检测、任务检测、标准编号、产品型号、缺陷位置、风险等级等质检话术。
如果证据不足，请说明知识库中没有足够相关内容，并给出可以继续补充的方向。
只返回 JSON：{"answer": string, "summary": string}。"""

CHAT_PROMPTS = {
    "general_chat": {
        "version": "chat_general_v1",
        "system": CHAT_GENERAL_V1,
        "temperature": 0.7,
    },
    "rag_qa": {
        "version": "chat_rag_qa_v1",
        "system": CHAT_RAG_QA_V1,
        "temperature": 0.2,
    },
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/agent/prompts/__init__.py backend/agent/prompts/chat.py
git commit -m "feat: add ChatAgent prompts - general_chat and rag_qa

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Create PromptBuilder — Inspection Prompts

**Files:**
- Create: `backend/agent/prompts/inspection.py`

- [ ] **Step 1: Create inspection.py with quality_qa, task_create, inspection_execute prompts**

```python
from __future__ import annotations

INSPECTION_QUALITY_QA_V1 = """你是质量检测问答助手。
请基于检索到的标准、规范、规则和历史检测依据回答用户的质检问题。
回答必须包含：判定依据、不确定性说明、必要时的引用来源。
证据不足时，请明确说明不能做最终判定，不要编造标准条款或检测结论。
只返回 JSON：{"answer": string, "summary": string}。"""

INSPECTION_TASK_CREATE_V1 = """你是检测任务创建助手。
你的职责是从用户输入中提取产品编号、检测标准、检测图片、优先级，并生成任务草稿。
如果信息不足，只追问缺失字段，不要进行质量判定。
如果信息完整，请展示任务草稿，并要求用户确认后再提交。
只返回 JSON：{"answer": string, "summary": string}。"""

INSPECTION_EXECUTE_V1 = """你是正式质量检测执行智能体。
请基于图片、结构化文件、产品信息、检测标准和 RAG 证据完成检测。
输出必须包含检测结论、依据、引用、风险等级、结果摘要。
证据不足时，应进入人工复核或补充信息状态，不要强行 PASS/FAIL。
只返回 JSON：{"answer": string, "summary": string}。"""

INSPECTION_PROMPTS = {
    "quality_qa": {
        "version": "inspection_quality_qa_v1",
        "system": INSPECTION_QUALITY_QA_V1,
        "temperature": 0.2,
    },
    "task_create": {
        "version": "inspection_task_create_v1",
        "system": INSPECTION_TASK_CREATE_V1,
        "temperature": 0.3,
    },
    "inspection_execute": {
        "version": "inspection_execute_v1",
        "system": INSPECTION_EXECUTE_V1,
        "temperature": 0.2,
    },
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/prompts/inspection.py
git commit -m "feat: add InspectionTaskAgent prompts - quality_qa, task_create, inspection_execute

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Create PromptBuilder Main Module

**Files:**
- Create: `backend/agent/prompts/prompt_builder.py`

- [ ] **Step 1: Create prompt_builder.py**

```python
from __future__ import annotations

from typing import Any

from agent.prompts.chat import CHAT_PROMPTS
from agent.prompts.inspection import INSPECTION_PROMPTS

ALL_PROMPTS = {**CHAT_PROMPTS, **INSPECTION_PROMPTS}


class PromptBuilder:
    """按 agent + sub_route 生成系统提示词、用户消息和元数据。"""

    @staticmethod
    def build(
        *,
        agent: str,
        sub_route: str,
        query: str,
        history: list[dict[str, Any]] | None = None,
        retrieved_docs: list[dict[str, Any]] | None = None,
        task_draft: dict[str, Any] | None = None,
        action_state: str = "",
        runtime_prompt_section: str = "",
    ) -> tuple[str, str, float, dict[str, Any]]:
        """返回 (system_prompt, user_message, temperature, metadata)"""
        prompt_config = ALL_PROMPTS.get(sub_route, CHAT_PROMPTS["general_chat"])
        system_prompt = prompt_config["system"]
        temperature = prompt_config["temperature"]

        if runtime_prompt_section:
            system_prompt = f"{system_prompt}\n\n{runtime_prompt_section}"

        history_lines = [
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in (history or [])[-6:]
            if item.get("content")
        ]
        history_text = "\n".join(history_lines) if history_lines else "无"

        user_message = f"用户消息:\n{query}\n\n历史对话:\n{history_text}"

        if retrieved_docs:
            doc_lines = [
                "\n".join([
                    f"[{i}] 标题: {doc.get('title', '')}",
                    f"来源: {doc.get('source', '')}",
                    f"内容: {str(doc.get('text', '') or '')[:600]}",
                ])
                for i, doc in enumerate(retrieved_docs, start=1)
            ]
            doc_text = "\n\n".join(doc_lines) if doc_lines else "无"
            user_message = f"问题:\n{query}\n\n历史对话:\n{history_text}\n\n检索证据:\n{doc_text}"

        if task_draft:
            from agent.subgraphs.quality_chat.graph import _format_task_draft, _slot_labels
            draft_text = _format_task_draft(task_draft)
            missing = list(task_draft.get("_missing_slots") or [])
            label_hints = "、".join(_slot_labels(missing)) if missing else "无"
            task_context = (
                f"\n\n当前任务草稿：\n{draft_text}\n"
                f"缺失字段：{label_hints}\n"
                f"当前状态：{action_state}"
            )
            user_message += task_context

        metadata = {
            "prompt_version": prompt_config["version"],
            "agent": agent,
            "sub_route": sub_route,
            "temperature": temperature,
        }

        return system_prompt, user_message, temperature, metadata
```

- [ ] **Step 2: Import _format_task_draft and _slot_labels from quality_chat graph**

These functions are currently in `backend/agent/subgraphs/quality_chat/graph.py`. Move them to a shared location or import directly. For minimal change, add a fallback:

In `prompt_builder.py`, define local fallbacks:

```python
def _format_task_draft(draft: dict[str, Any]) -> str:
    if not draft:
        return "无"
    lines = []
    for key, value in draft.items():
        if not key.startswith("_") and value:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines) if lines else "无"


def _slot_labels(slots: list[str]) -> list[str]:
    labels = {
        "product_id": "产品编号",
        "spec_code": "检测标准",
        "image_urls": "检测图片",
        "priority": "优先级",
    }
    return [labels.get(s, s) for s in slots]
```

Remove the import from quality_chat and use local helpers instead.

- [ ] **Step 3: Verify module loads**

Run: `cd backend && python -c "from agent.prompts.prompt_builder import PromptBuilder; s, u, t, m = PromptBuilder.build(agent='chat', sub_route='general_chat', query='你好'); print(m['prompt_version'])"`
Expected: `chat_general_v1`

- [ ] **Step 4: Commit**

```bash
git add backend/agent/prompts/prompt_builder.py
git commit -m "feat: add PromptBuilder - unified prompt generation per agent+sub_route

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Integrate PromptBuilder into QualityChatGraph reasoning()

**Files:**
- Modify: `backend/agent/subgraphs/quality_chat/graph.py:497-593`

- [ ] **Step 1: Replace hardcoded prompt logic in reasoning() function**

Replace the prompt building section (lines 511-593) with PromptBuilder call:

```python
async def reasoning(state: QualityChatState) -> QualityChatState:
    _t_reasoning = perf_counter()
    intent = state.get("intent")
    sub_route = state.get("sub_route", intent or "general_chat")
    query = str(state.get("query") or "")
    history = list(state.get("history") or [])
    docs = list(state.get("retrieved_chunks") or [])
    citations = list(state.get("citations") or [])
    action_state = str(state.get("action_state") or "answered")
    draft = dict(state.get("task_draft") or {})
    missing_slots = list(state.get("missing_slots") or [])

    # Use PromptBuilder
    from agent.prompts.prompt_builder import PromptBuilder

    agent_name = state.get("agent", "chat")
    system_prompt, user_message, temperature, prompt_meta = PromptBuilder.build(
        agent=agent_name,
        sub_route=sub_route,
        query=query,
        history=history,
        retrieved_docs=docs if sub_route in {"rag_qa", "quality_qa", "inspection_execute"} else None,
        task_draft=draft if sub_route in {"task_create"} else None,
        action_state=action_state,
        runtime_prompt_section=_dspy_prompt_section(
            state,
            ["quality_judgement.planner", "quality_judgement.reasoning", "quality_judgement.response_writer"],
        ),
    )

    state["prompt_version"] = prompt_meta["prompt_version"]

    # ── Unified LLM call ──
    _t_pre_llm = perf_counter()
    # ... rest of the LLM call remains unchanged
```

- [ ] **Step 2: Verify the graph still works**

Run: `cd backend && python -c "from agent.subgraphs.quality_chat import QualityChatGraph; g = QualityChatGraph(); print('graph loaded OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/subgraphs/quality_chat/graph.py
git commit -m "feat: integrate PromptBuilder into QualityChatGraph reasoning

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: Create RagPolicy Module

**Files:**
- Create: `backend/agent/rag/rag_policy.py`

- [ ] **Step 1: Create rag_policy.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagPolicyDecision:
    should_retrieve: bool = False
    rag_space_id: str | None = None
    top_k: int = 4
    filter_conditions: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


RAG_POLICY_MAP = {
    "general_chat": {"retrieve": False, "source": None, "top_k": 0},
    "rag_qa": {"retrieve": True, "source": "selected_space", "top_k": 4},
    "quality_qa": {"retrieve": True, "source": "standard_library + selected_space", "top_k": 6},
    "task_create": {"retrieve": False, "source": None, "top_k": 0},
    "inspection_execute": {"retrieve": True, "source": "spec_code_standard + selected_space", "top_k": 8},
}


class RagPolicy:
    """按 sub_route 决定是否检索、检索哪个空间、top_k、过滤条件。"""

    def decide(
        self,
        *,
        sub_route: str,
        selected_rag_space: dict[str, Any] | None = None,
        spec_code: str | None = None,
    ) -> RagPolicyDecision:
        policy = RAG_POLICY_MAP.get(sub_route, RAG_POLICY_MAP["general_chat"])

        if not policy["retrieve"]:
            return RagPolicyDecision(should_retrieve=False, reason=f"{sub_route} 不需要 RAG 检索")

        rag_space_id = None
        filter_conditions: dict[str, Any] = {}

        if selected_rag_space and selected_rag_space.get("id"):
            rag_space_id = selected_rag_space["id"]
            filter_conditions["rag_space_id"] = rag_space_id

        if sub_route == "inspection_execute" and spec_code:
            filter_conditions["spec_code"] = spec_code

        return RagPolicyDecision(
            should_retrieve=True,
            rag_space_id=rag_space_id,
            top_k=policy["top_k"],
            filter_conditions=filter_conditions,
            reason=f"{sub_route} 需要 RAG 检索，来源: {policy['source']}",
        )
```

- [ ] **Step 2: Verify module loads**

Run: `cd backend && python -c "from agent.rag.rag_policy import RagPolicy; p = RagPolicy(); d = p.decide(sub_route='rag_qa', selected_rag_space={'id': 'space-1'}); print(d.should_retrieve, d.rag_space_id)"`
Expected: `True space-1`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/rag/rag_policy.py
git commit -m "feat: add RagPolicy - per-sub-route RAG retrieval decisions

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 10: Integrate RagPolicy into QualityChatGraph knowledge node

**Files:**
- Modify: `backend/agent/subgraphs/quality_chat/graph.py` (knowledge function)

- [ ] **Step 1: Read the knowledge function to understand current logic**

The `knowledge` function is at approximately line 461. It currently decides RAG based on intent.

- [ ] **Step 2: Update knowledge() to use RagPolicy**

Replace the RAG decision logic in `knowledge()`:

```python
async def knowledge(state: QualityChatState) -> QualityChatState:
    _t_knowledge = perf_counter()
    sub_route = state.get("sub_route", state.get("intent", "general_chat"))
    selected_rag = state.get("selected_rag_space") or {}

    from agent.rag.rag_policy import RagPolicy
    rag_policy = RagPolicy()
    policy_decision = rag_policy.decide(
        sub_route=sub_route,
        selected_rag_space=selected_rag if selected_rag.get("id") else None,
        spec_code=state.get("spec_code"),
    )

    if not policy_decision.should_retrieve:
        state["retrieved_chunks"] = []
        state["citations"] = []
        state["retrieval_metrics"] = {"skipped": True, "reason": policy_decision.reason}
        return state

    # ... existing retrieval logic using policy_decision.rag_space_id, policy_decision.top_k
```

- [ ] **Step 3: Commit**

```bash
git add backend/agent/subgraphs/quality_chat/graph.py
git commit -m "feat: integrate RagPolicy into QualityChatGraph knowledge node

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 11: Create Unified ResponseBuilder

**Files:**
- Create: `backend/agent/response/__init__.py`
- Create: `backend/agent/response/response_builder.py`

- [ ] **Step 1: Create __init__.py**

```python
from agent.response.response_builder import ResponseBuilder

__all__ = ["ResponseBuilder"]
```

- [ ] **Step 2: Create response_builder.py**

```python
from __future__ import annotations

from typing import Any

UI_SCHEMA_MAP = {
    ("chat", "general_chat"): "chat_text_v1",
    ("chat", "rag_qa"): "rag_answer_v1",
    ("inspection_task", "quality_qa"): "quality_answer_v1",
    ("inspection_task", "task_create"): "task_action_v1",
    ("inspection_task", "inspection_execute"): "task_result_v1",
}


class ResponseBuilder:
    """统一构建 ChatAssistantPayload，保证所有流程返回结构一致。"""

    @staticmethod
    def build(
        *,
        agent: str,
        sub_route: str,
        answer: str,
        summary: str = "",
        message_type: str = "assistant_text",
        citations: list[dict[str, Any]] | None = None,
        quality: dict[str, Any] | None = None,
        rag_summary: dict[str, Any] | None = None,
        retrieval_metrics: dict[str, Any] | None = None,
        task_draft: dict[str, Any] | None = None,
        missing_slots: list[str] | None = None,
        awaiting_confirmation: bool = False,
        action_state: str = "answered",
        created_task: dict[str, Any] | None = None,
        result_card: dict[str, Any] | None = None,
        route_decision: dict[str, Any] | None = None,
        trace_id: str | None = None,
        trace_url: str | None = None,
        prompt_version: str = "",
        workflow_version: str = "chat_router_v2",
        selected_rag_space: dict[str, Any] | None = None,
        agent_name_compat: str = "",
        source_graph_compat: str = "",
    ) -> dict[str, Any]:
        ui_schema = UI_SCHEMA_MAP.get((agent, sub_route), "chat_text_v1")

        return {
            "answer": answer,
            "summary": summary,
            "agent": agent,
            "sub_route": sub_route,
            "intent": sub_route,
            "message_type": message_type,
            "ui_schema": ui_schema,
            "citations": list(citations or []),
            "rag_summary": rag_summary,
            "retrieval_metrics": retrieval_metrics,
            "quality": dict(quality or {}),
            "task_draft": task_draft,
            "task_form_defaults": task_draft,
            "missing_slots": list(missing_slots or []),
            "pending_action": None,
            "awaiting_confirmation": awaiting_confirmation,
            "action_state": action_state,
            "created_task": created_task,
            "result_card": result_card,
            "expectation_check": None,
            "route_decision": route_decision,
            "trace_id": trace_id,
            "trace_url": trace_url,
            "workflow_version": workflow_version,
            "prompt_version": prompt_version,
            "selected_rag_space": selected_rag_space,
            "agent_name": agent_name_compat or agent,
            "source_graph": source_graph_compat or agent,
            "status": "completed",
            "error": None,
        }
```

- [ ] **Step 3: Commit**

```bash
git add backend/agent/response/
git commit -m "feat: add ResponseBuilder - unified output protocol with ui_schema

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 12: Update Orchestrator to Use ResponseBuilder and New Fields

**Files:**
- Modify: `backend/app/services/quality_agent_orchestrator_service.py:302-373`

- [ ] **Step 1: Update _build_response_payload to include new fields**

Replace the `_build_response_payload` method:

```python
def _build_response_payload(
    self,
    *,
    request: NormalizedRequest,
    output: AgentOutput,
    task_form_defaults: dict[str, Any],
    materialized_task: dict[str, Any] | None,
    materialization_error: str | None,
) -> dict[str, Any]:
    base_payload = {}
    if isinstance(output.raw_state, dict):
        base_payload = dict(output.raw_state.get("response_payload") or {})

    # Extract agent/sub_route from route_decision or base_payload
    agent = (
        base_payload.get("agent")
        or (output.route_decision.selected_subgraph if output.route_decision else None)
        or "chat"
    )
    sub_route = (
        base_payload.get("sub_route")
        or base_payload.get("intent")
        or "general_chat"
    )
    trace_id = base_payload.get("trace_id") or (
        output.persistable_output.quality_trace.trace_id
        if output.persistable_output and output.persistable_output.quality_trace
        else None
    )

    from agent.response.response_builder import ResponseBuilder

    return ResponseBuilder.build(
        agent=agent,
        sub_route=sub_route,
        answer=output.answer,
        summary=output.summary,
        message_type=output.message_type,
        citations=list(output.citations or []),
        quality=dict(output.quality or {}),
        rag_summary=dict(output.rag_summary) if output.rag_summary else None,
        task_draft=task_form_defaults or None,
        missing_slots=list((output.clarification.missing_fields if output.clarification else []) or []),
        awaiting_confirmation=bool(base_payload.get("awaiting_confirmation") or False),
        action_state=output.action_state,
        created_task=base_payload.get("created_task") or materialized_task,
        result_card=dict(output.result_card) if output.result_card else None,
        route_decision=output.route_decision.model_dump() if output.route_decision else None,
        trace_id=trace_id,
        trace_url=base_payload.get("trace_url"),
        prompt_version=base_payload.get("prompt_version", ""),
        selected_rag_space=request.ext.get("selected_rag_space") or base_payload.get("selected_rag_space"),
        agent_name_compat=(
            output.route_decision.selected_subgraph
            if output.route_decision
            else base_payload.get("agent_name") or "quality_judgement"
        ),
        source_graph_compat=(
            output.route_decision.selected_subgraph
            if output.route_decision
            else base_payload.get("source_graph") or "quality_judgement"
        ),
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/quality_agent_orchestrator_service.py
git commit -m "feat: integrate ResponseBuilder into orchestrator with agent/sub_route/ui_schema

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 13: Langfuse — Trace Naming Standardization

**Files:**
- Modify: `backend/agent/llm/langfuse_tracer.py`

- [ ] **Step 1: Update start_trace to use agent.sub_route naming convention**

Modify `start_trace` method signature and default name logic:

```python
def start_trace(self, **kwargs):
    trace_id = str(kwargs.get("trace_id") or self.create_trace_id())
    source_type = kwargs.get("source_type") or "inspection"

    # Build trace name: agent.sub_route or fallback
    agent = kwargs.get("agent", "")
    sub_route = kwargs.get("sub_route", "")
    if agent and sub_route:
        trace_name = f"{agent}.{sub_route}"
    elif agent:
        trace_name = agent
    else:
        trace_name = kwargs.get("name") or "chat.general_chat"

    payload = {
        "trace_id": trace_id,
        "task_id": kwargs.get("task_id"),
        "org_id": kwargs.get("org_id"),
        "model_key": kwargs.get("model_key"),
        "name": trace_name,
        "started_at": kwargs.get("started_at") or datetime.utcnow().isoformat(),
        "trace_url": self.get_trace_url(trace_id),
        "source_type": source_type,
        "agent": agent,
        "sub_route": sub_route,
    }

    if self._client is not None:
        trace_factory = getattr(self._client, "trace", None)
        metadata = {
            key: value
            for key, value in {
                "task_id": payload["task_id"],
                "org_id": payload["org_id"],
                "model_key": payload["model_key"],
                "source_type": source_type,
                "agent": agent,
                "sub_route": sub_route,
                "intent": kwargs.get("intent", ""),
                "prompt_version": kwargs.get("prompt_version", ""),
                "workflow_version": kwargs.get("workflow_version", ""),
                "session_id": kwargs.get("session_id", ""),
                "route_source": kwargs.get("route_source", ""),
                "route_confidence": kwargs.get("route_confidence", 0.0),
                "verdict": kwargs.get("verdict"),
            }.items()
            if value is not None and value != ""
        }
        tags = [
            t for t in [
                f"source_type:{source_type}",
                f"agent:{agent}" if agent else None,
                f"sub_route:{sub_route}" if sub_route else None,
                f"org_id:{payload['org_id']}" if payload.get("org_id") else None,
            ] if t is not None
        ]
        # ... rest of trace creation unchanged
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/llm/langfuse_tracer.py
git commit -m "feat: standardize Langfuse trace naming as agent.sub_route with full metadata

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 14: Langfuse — Environment Variables and .env.example

**Files:**
- Create: `backend/.env.langfuse.local.example`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Create .env.langfuse.local.example**

```env
# Langfuse 本地开发配置
PIAP_LANGFUSE_ENABLED=true
PIAP_LANGFUSE_HOST=http://langfuse-web:3000
PIAP_LANGFUSE_PUBLIC_HOST=http://127.0.0.1:3000
PIAP_LANGFUSE_PUBLIC_KEY=pk-lf-piap-local
PIAP_LANGFUSE_SECRET_KEY=sk-lf-piap-local
PIAP_LANGFUSE_ENVIRONMENT=local
PIAP_LANGFUSE_RELEASE=tgg-local

# Langfuse 本地初始化账号（仅本地开发使用）
LANGFUSE_INIT_ORG_ID=piap-local-org
LANGFUSE_INIT_ORG_NAME=PIAP Local
LANGFUSE_INIT_PROJECT_ID=piap-local-project
LANGFUSE_INIT_PROJECT_NAME=PIAP Local Project
LANGFUSE_INIT_USER_EMAIL=admin@piap.local
LANGFUSE_INIT_USER_NAME=PIAP Admin
LANGFUSE_INIT_USER_PASSWORD=piap_admin_123456
```

- [ ] **Step 2: Add Langfuse init config to Settings**

In `backend/app/core/config.py`, add after existing langfuse fields:

```python
langfuse_init_org_id: str | None = None
langfuse_init_org_name: str | None = None
langfuse_init_project_id: str | None = None
langfuse_init_project_name: str | None = None
langfuse_init_user_email: str | None = None
langfuse_init_user_name: str | None = None
langfuse_init_user_password: str | None = None
```

- [ ] **Step 3: Commit**

```bash
git add backend/.env.langfuse.local.example backend/app/core/config.py
git commit -m "feat: add Langfuse local env config with fixed credentials

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 15: Pass sub_route Through QualityChatGraph State and Run

**Files:**
- Modify: `backend/agent/subgraphs/quality_chat/graph.py` (state definition, run method)

- [ ] **Step 1: Add sub_route and agent to QualityChatState TypedDict**

Read current state definition at lines 6-40. Add two fields:

```python
class QualityChatState(TypedDict, total=False):
    # ... existing fields ...
    agent: str  # "chat" | "inspection_task"
    sub_route: str  # "general_chat" | "rag_qa" | "quality_qa" | "task_create" | "inspection_execute"
```

- [ ] **Step 2: Set agent and sub_route from AgentRouteDecision in run() method**

In the `run()` method, extract from `route_decision`:

```python
agent = getattr(route_decision, "selected_agent", "chat")
sub_route = getattr(route_decision, "sub_route", "general_chat")

initial_state: QualityChatState = {
    # ... existing fields ...
    "agent": agent,
    "sub_route": sub_route,
}
```

- [ ] **Step 3: Pass agent/sub_route to Langfuse tracer in _run_state()**

In the `_run_state()` method (around line 1048), update the trace start:

```python
trace_payload = tracer.start_trace(
    trace_id=trace_id,
    name=f"{agent}.{sub_route}",
    agent=agent,
    sub_route=sub_route,
    intent=state.get("intent"),
    prompt_version=state.get("prompt_version"),
    workflow_version="chat_router_v2",
    route_source=getattr(route_decision, "route_source", ""),
    route_confidence=getattr(route_decision, "confidence", 0.0),
    session_id=state.get("session_id"),
    source_type="chat",
    org_id=state.get("org_id"),
    model_key=state.get("model_key"),
)
```

- [ ] **Step 4: Commit**

```bash
git add backend/agent/subgraphs/quality_chat/graph.py
git commit -m "feat: thread agent/sub_route through QualityChatGraph to Langfuse traces

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 16: Update Frontend Types — agent, sub_route, ui_schema, chatMode

**Files:**
- Modify: `frontend/src/types/chat.types.ts`

- [ ] **Step 1: Add new type definitions**

Add after `ChatAttachment` (after line 23):

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

- [ ] **Step 2: Add new fields to ChatMessagePayload**

Add inside `ChatMessagePayload` (after existing fields):

```ts
  agent?: ChatAgentName | string | null;
  sub_route?: ChatSubRoute | string | null;
  ui_schema?: ChatUiSchema | string | null;
  trace_url?: string | null;
```

- [ ] **Step 3: Add ChatMode type**

```ts
export type ChatMode = "auto" | "chat" | "inspection";
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/chat.types.ts
git commit -m "feat: add ChatAgentName, ChatSubRoute, ChatUiSchema, ChatMode types

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 17: Update Frontend ChatView — chatMode and route_hints

**Files:**
- Modify: `frontend/src/views/ChatView.vue`

- [ ] **Step 1: Change chatMode type from `"auto" | "qa" | "inspection"` to `"auto" | "chat" | "inspection"`**

Line 25: Change:
```ts
const chatMode = ref<"auto" | "qa" | "inspection">("auto");
```
To:
```ts
const chatMode = ref<ChatMode>("auto");
```

- [ ] **Step 2: Update route_hints logic**

Lines 246-249: Change:
```ts
const routeHints = chatMode.value === "inspection"
  ? { force_agent: "inspection_task" }
  : chatMode.value === "qa"
    ? { force_agent: "quality_chat" }
    : undefined;
```
To:
```ts
const routeHints = chatMode.value === "inspection"
  ? { force_agent: "inspection_task" }
  : chatMode.value === "chat"
    ? { force_agent: "chat" }
    : undefined;
```

- [ ] **Step 3: Update the mode selector labels in the template**

Around line 359, update the select options:
```html
<option value="auto">自动识别</option>
<option value="chat">聊天/知识库</option>
<option value="inspection">质检/任务</option>
```

- [ ] **Step 4: Add ui_schema-based rendering helper**

Add a computed or function:
```ts
function resolveUiSchema(message: ChatMessage): ChatUiSchema {
  if (message.payload?.ui_schema) return message.payload.ui_schema as ChatUiSchema;
  if (message.message_type === "task_result") return "task_result_v1";
  if (message.message_type === "task_action") return "task_action_v1";
  if (message.message_type === "quality_answer") return "quality_answer_v1";
  if (message.payload?.citations?.length) return "rag_answer_v1";
  return "chat_text_v1";
}

function resolveAgent(payload: ChatMessagePayload | null | undefined): string {
  return payload?.agent || payload?.agent_name || payload?.source_graph || "";
}

function resolveSubRoute(payload: ChatMessagePayload | null | undefined): string {
  return payload?.sub_route || payload?.intent || "";
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ChatView.vue
git commit -m "feat: update ChatView chatMode to chat/inspection, add ui_schema resolver

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 18: Update Frontend Chat Store — ext payload with new fields

**Files:**
- Modify: `frontend/src/stores/chat.store.ts`

- [ ] **Step 1: Update ext payload in sendMessage() to include new field structure**

In the `sendMessage()` function, update the ext object:

```ts
const ext: Record<string, unknown> = {
  ui_mode: chatMode.value,
  route_hints: routeHints || undefined,
  attachments: attachments.value.map(a => ({
    id: a.id, name: a.name, url: a.url,
    content_type: a.content_type, size_bytes: a.size_bytes, kind: a.kind,
  })),
  selected_rag_space_id: selectedRagSpace.value?.id || undefined,
  selected_rag_space_name: selectedRagSpace.value?.name || undefined,
  selected_rag_space_description: selectedRagSpace.value?.description || undefined,
  selected_rag_space: selectedRagSpace.value ? {
    id: selectedRagSpace.value.id,
    name: selectedRagSpace.value.name,
    description: selectedRagSpace.value.description,
  } : undefined,
  rag_scope: ragScope.value || undefined,
};
```

- [ ] **Step 2: Update applyStreamEvent to extract new fields**

In `applyStreamEvent()`, when handling `message_final`:

```ts
if (event.payload) {
  message.payload = {
    ...message.payload,
    ...event.payload,
    agent: event.payload.agent || event.payload.agent_name || event.payload.source_graph,
    sub_route: event.payload.sub_route || event.payload.intent,
    ui_schema: event.payload.ui_schema,
    trace_url: event.payload.trace_url || event.payload.trust_scoring?.trace_url,
  };
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/chat.store.ts
git commit -m "feat: update chat store ext payload and stream event handling

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 19: End-to-End Verification

**Files:**
- None (verification only)

- [ ] **Step 1: Verify backend imports all work together**

Run: `cd backend && python -c "
from agent.router.contracts import AgentRouteDecision
from agent.router.route_policy import AgentRoutePolicy
from agent.router.agent_manager import AgentManager
from agent.router.model_classifier import ModelClassifier
from agent.prompts.prompt_builder import PromptBuilder
from agent.prompts.chat import CHAT_PROMPTS
from agent.prompts.inspection import INSPECTION_PROMPTS
from agent.rag.rag_policy import RagPolicy
from agent.response.response_builder import ResponseBuilder
print('All imports OK')
"`

- [ ] **Step 2: Run routing decision matrix**

Run:
```bash
cd backend && python -c "
from agent.router.route_policy import AgentRoutePolicy
from agent.router.contracts import AgentRouterInput

p = AgentRoutePolicy()
tests = [
    ('你好', ('chat', 'general_chat')),
    ('你是谁', ('chat', 'general_chat')),
    ('总结这个知识库', ('chat', 'rag_qa')),
    ('这个缺陷算不算不合格', ('inspection_task', 'quality_qa')),
    ('帮我创建检测任务', ('inspection_task', 'task_create')),
    ('检测这张图片', ('inspection_task', 'inspection_execute')),
    ('划痕怎么判定', ('inspection_task', 'quality_qa')),
    ('文档里有没有提到标准', ('chat', 'rag_qa')),
    ('这个呢', ('chat', 'general_chat')),
]
for query, (exp_agent, exp_sub) in tests:
    d = p.decide(AgentRouterInput(query=query))
    ok = d.selected_agent == exp_agent and d.sub_route == exp_sub
    status = 'OK' if ok else f'FAIL (got {d.selected_agent}.{d.sub_route})'
    print(f'[{status}] \"{query}\" -> {d.selected_agent}.{d.sub_route}')
"
```

- [ ] **Step 3: Verify ResponseBuilder output for each sub_route**

Run:
```bash
cd backend && python -c "
from agent.response.response_builder import ResponseBuilder

for agent, sub in [('chat','general_chat'), ('chat','rag_qa'), ('inspection_task','quality_qa'), ('inspection_task','task_create'), ('inspection_task','inspection_execute')]:
    r = ResponseBuilder.build(agent=agent, sub_route=sub, answer='test', prompt_version=f'{agent}_{sub}_v1')
    print(f'{agent}.{sub} -> ui_schema={r[\"ui_schema\"]}, agent={r[\"agent\"]}, sub_route={r[\"sub_route\"]}')
"
```

- [ ] **Step 4: Commit verification results**

```bash
git add -A
git commit -m "chore: end-to-end verification of routing, prompts, and response

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Summary

19 tasks covering:
1. **Route Protocol** (Tasks 1-3): `quality_chat` → `chat`, add `sub_route`, 7-level rule-based routing
2. **Model Classifier** (Task 4): LLM fallback for ambiguous inputs
3. **PromptBuilder** (Tasks 5-8): Isolated prompts per sub-route, integrated into QualityChatGraph
4. **RagPolicy** (Tasks 9-10): Per-sub-route RAG decisions, prevents quality prompts in chat
5. **ResponseBuilder** (Tasks 11-12): Unified output with `ui_schema`, integrated into orchestrator
6. **Langfuse** (Tasks 13-15): Trace naming `agent.sub_route`, full metadata, env config
7. **Frontend** (Tasks 16-18): Types, chatMode, route_hints, ui_schema rendering
8. **Verification** (Task 19): Import check, routing matrix, response validation
