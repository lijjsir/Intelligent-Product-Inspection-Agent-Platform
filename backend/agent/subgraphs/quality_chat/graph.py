from __future__ import annotations

import re
from typing import Any

from langgraph.graph import END, StateGraph

from agent.llm.client import LLMClient
from agent.llm.langfuse_tracer import LangfuseTracer
from agent.rag.retriever import Retriever
from agent.subgraphs.quality_chat.state import QualityChatState
from app.core.exceptions import ValidationError
from app.repositories.chat_repo import ChatMessageRepository
from app.services.task_service import TaskService
from infra.database.session import get_session


SMALLTALK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^\s*(你是谁|介绍一下自己|你是做什么的)\s*[？?]?\s*$",
        r"^\s*(你能做什么|你会什么|你可以做什么)\s*[？?]?\s*$",
        r"^\s*(hello|hi|hey|你好|嗨)\s*[!！。.]?\s*$",
    ]
]
TASK_CREATE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(创建|新建|发起|提交).{0,8}(任务|检测|质检)",
        r"(帮我|给我).{0,8}(创建|发起|提交).{0,8}(任务|检测|质检)",
        r"(帮我|给我).{0,8}(进行|做).{0,8}(质量检测|质检|检测)",
        r"(需要|想要).{0,8}(创建|发起).{0,8}(任务|检测)",
        r"^\s*(质量检测|质检|检测任务|开始检测|启动检测)\s*[!！。.]?\s*$",
    ]
]
CONFIRM_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^\s*(确认|确定|可以创建|开始创建|提交吧|创建吧|好的创建|ok|okay|yes)\s*[!！。.]?\s*$",
    ]
]
CANCEL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^\s*(取消|不用了|算了|先不要|停止创建|别创建了|no)\s*[!！。.]?\s*$",
    ]
]
QUALITY_QA_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(质量|质检|检测|检验|缺陷|瑕疵|判定|允收|不良|NG|OK|标准|规范|条款|公差|尺寸|外观|划痕|裂纹|毛刺|飞边|凹陷|污渍|色差|气泡|变形|烧焦|缩水|夹杂|焊点|工艺)",
        r"(QC|QA|IQC|IPQC|FQC|OQC|AQL|SOP|SIP|GB/?T|ISO\s*\d+)",
        r"(spec|defect|inspection|quality|standard|tolerance|scratch|burr|dent|stain|crack)",
    ]
]
QUALITY_CONTEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(这个|那这个|这种|那种|该怎么|为什么|是否|算不算|属于|依据是什么|怎么判|如何判定)",
    ]
]
URL_PATTERN = re.compile(r"https?://[^\s,，；;]+", re.IGNORECASE)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_smalltalk(query: str) -> bool:
    text = _clean_text(query)
    return any(pattern.search(text) for pattern in SMALLTALK_PATTERNS)


def _has_recent_quality_context(history: list[dict[str, Any]]) -> bool:
    for item in reversed(history[-4:]):
        payload = item.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("intent") == "quality_qa":
            return True
        if payload.get("message_type") == "quality_answer":
            return True
        if item.get("message_type") == "quality_answer":
            return True
    return False


def _is_quality_qa_candidate(query: str, history: list[dict[str, Any]] | None = None) -> bool:
    text = _clean_text(query)
    if not text:
        return False
    if any(pattern.search(text) for pattern in QUALITY_QA_PATTERNS):
        return True
    if _has_recent_quality_context(list(history or [])) and any(
        pattern.search(text) for pattern in QUALITY_CONTEXT_PATTERNS
    ):
        return True
    return False


def _is_task_create_candidate(query: str, ext: dict[str, Any] | None) -> bool:
    text = _clean_text(query)
    if any(pattern.search(text) for pattern in TASK_CREATE_PATTERNS):
        return True
    attachments = list((ext or {}).get("attachments") or [])
    return any(str(item.get("kind") or "") == "image" for item in attachments if isinstance(item, dict))


def _is_confirm(query: str) -> bool:
    return any(pattern.search(_clean_text(query)) for pattern in CONFIRM_PATTERNS)


def _is_cancel(query: str) -> bool:
    return any(pattern.search(_clean_text(query)) for pattern in CANCEL_PATTERNS)


def _extract_first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip().strip("，。；;:：")
    return None


def _extract_priority(query: str, base_priority: int = 5) -> int:
    patterns = [
        re.compile(r"优先级\s*[:：]?\s*(\d{1,2})"),
        re.compile(r"priority\s*[:：]?\s*(\d{1,2})", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(query)
        if match:
            return max(1, min(10, int(match.group(1))))
    return max(1, min(10, int(base_priority or 5)))


def _extract_image_urls(query: str, ext: dict[str, Any] | None, base: list[str] | None = None) -> list[str]:
    ext = ext or {}
    candidates: list[str] = []
    for key in ("image_urls", "images"):
        value = ext.get(key)
        if isinstance(value, list):
            candidates.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            candidates.extend(part.strip() for part in re.split(r"[\n,，；;]+", value) if part.strip())
    attachments = ext.get("attachments") or []
    if isinstance(attachments, list):
        for item in attachments:
            if isinstance(item, dict) and str(item.get("kind") or "") == "image":
                url = str(item.get("url") or "").strip()
                if url:
                    candidates.append(url)
    candidates.extend(match.group(0).strip() for match in URL_PATTERN.finditer(query))
    merged: list[str] = []
    for item in [*(base or []), *candidates]:
        if item and item not in merged:
            merged.append(item)
    return merged


def _extract_task_draft(
    query: str,
    metadata: dict[str, Any] | None = None,
    ext: dict[str, Any] | None = None,
    base_draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    ext = ext or {}
    base_draft = dict(base_draft or {})
    text = query.strip()
    product_patterns = [
        re.compile(r"产品(?:编号|id|ID|型号)?\s*[:：为是]?\s*([A-Za-z0-9._-]+)"),
        re.compile(r"product(?:_id)?\s*[:：]?\s*([A-Za-z0-9._-]+)", re.IGNORECASE),
    ]
    spec_patterns = [
        re.compile(r"标准(?:编号|编码|号|code)?\s*[:：为是]?\s*([A-Za-z0-9._-]+)"),
        re.compile(r"检测标准(?:编号|编码|号)?\s*[:：为是]?\s*([A-Za-z0-9._-]+)"),
        re.compile(r"spec(?:_code)?\s*[:：]?\s*([A-Za-z0-9._-]+)", re.IGNORECASE),
    ]
    return {
        "product_id": str(
            ext.get("product_id")
            or metadata.get("product_id")
            or _extract_first_match(product_patterns, text)
            or base_draft.get("product_id")
            or ""
        ).strip(),
        "spec_code": str(
            ext.get("spec_code")
            or metadata.get("spec_code")
            or _extract_first_match(spec_patterns, text)
            or base_draft.get("spec_code")
            or ""
        ).strip(),
        "image_urls": _extract_image_urls(text, ext, base=list(base_draft.get("image_urls") or [])),
        "priority": _extract_priority(
            text,
            base_priority=int(ext.get("priority") or metadata.get("priority") or base_draft.get("priority") or 5),
        ),
        "metadata": {
            **dict(base_draft.get("metadata") or {}),
            **{key: value for key, value in metadata.items() if value is not None},
        },
    }


def _missing_slots(draft: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(draft.get("product_id") or "").strip():
        missing.append("product_id")
    if not str(draft.get("spec_code") or "").strip():
        missing.append("spec_code")
    if not list(draft.get("image_urls") or []):
        missing.append("image_urls")
    return missing


def _slot_labels(missing_slots: list[str]) -> list[str]:
    mapping = {
        "product_id": "产品编号",
        "spec_code": "检测标准编号",
        "image_urls": "检测图片",
    }
    return [mapping.get(item, item) for item in missing_slots]


def _format_task_draft(draft: dict[str, Any]) -> str:
    image_urls = list(draft.get("image_urls") or [])
    lines = [
        f"产品编号：{draft.get('product_id') or '未提供'}",
        f"检测标准：{draft.get('spec_code') or '未提供'}",
        f"图片数量：{len(image_urls)}",
        f"优先级：{draft.get('priority') or 5}",
    ]
    if image_urls:
        lines.append("图片链接：")
        lines.extend(f"- {item}" for item in image_urls[:3])
        if len(image_urls) > 3:
            lines.append(f"- 其余 {len(image_urls) - 3} 张图片已省略显示")
    return "\n".join(lines)


def _latest_pending_task(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(history):
        payload = item.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("pending_action") == "create_task" or payload.get("awaiting_confirmation"):
            return {
                "task_draft": dict(payload.get("task_draft") or {}),
                "missing_slots": list(payload.get("missing_slots") or []),
                "awaiting_confirmation": bool(payload.get("awaiting_confirmation")),
                "pending_action": str(payload.get("pending_action") or "create_task"),
            }
        if payload.get("action_state") in {"task_created", "task_cancelled"}:
            return None
    return None


def _smalltalk_answer(query: str) -> str:
    if re.search(r"你是谁|介绍一下自己", query):
        return (
            "我是质量检测聊天助手，主要帮助你解读检测标准、解释缺陷判定、梳理质检流程，"
            "也可以在信息补齐后协助你创建检测任务。"
        )
    return (
        "我可以回答质量检测相关问题，例如标准条款解读、缺陷是否判定为 NG、流程说明、结果解释；"
        "如果你想发起检测任务，我也可以先帮你整理必要信息。"
    )


def _general_answer_fallback(query: str) -> dict[str, Any]:
    return {
        "answer": (
            f"我收到了你的问题“{query}”。如果你想继续普通交流，我可以直接回答；"
            "如果你想咨询质量检测相关内容，也可以补充标准编号、缺陷现象或产品上下文。"
        ),
        "summary": "普通问答",
        "citations": [],
    }


def _fallback_answer(query: str, docs: list[dict[str, Any]], citations: list[dict[str, Any]]) -> dict[str, Any]:
    if not docs:
        return {
            "answer": (
                "当前没有检索到足够的质量检测依据。"
                "我可以先给你一个保守回答，但这次结论只能作为参考。"
                "建议补充更具体的产品编号、缺陷类型、标准编号或上下文。"
            ),
            "summary": "证据不足，给出保守回答",
            "citations": citations,
        }
    top = docs[0]
    excerpt = str(top.get("text") or "").strip()
    if len(excerpt) > 220:
        excerpt = f"{excerpt[:220]}..."
    return {
        "answer": (
            f"基于当前检索到的质量检测资料，与你的问题“{query}”最相关的依据来自"
            f"“{top.get('title') or '标准文档'}”。参考内容：{excerpt}"
        ),
        "summary": "基于检索结果生成的保守答案",
        "citations": citations,
    }


def _selected_rag_space(ext: dict[str, Any] | None) -> dict[str, Any] | None:
    ext = ext or {}
    selected = ext.get("selected_rag_space")
    if isinstance(selected, dict) and selected.get("id"):
        return {
            "id": str(selected.get("id")),
            "name": str(selected.get("name") or ""),
            "description": str(selected.get("description") or "") or None,
        }
    rag_space_id = str(ext.get("selected_rag_space_id") or "").strip()
    if not rag_space_id:
        return None
    return {
        "id": rag_space_id,
        "name": str(ext.get("selected_rag_space_name") or ""),
        "description": str(ext.get("selected_rag_space_description") or "") or None,
    }


async def input_adapter(state: QualityChatState) -> QualityChatState:
    state["workflow_version"] = "quality_chat_v1"
    state["prompt_version"] = str(state.get("prompt_version") or "builtin-quality-chat-v1")
    state["metadata"] = dict(state.get("metadata") or {})
    state["ext"] = dict(state.get("ext") or {})
    state["history"] = list(state.get("history") or [])
    state["intent"] = str(state.get("intent") or "")
    state["intent_confidence"] = float(state.get("intent_confidence") or 0.0)
    state["pending_action"] = state.get("pending_action")
    state["action_state"] = str(state.get("action_state") or "answered")
    state["task_draft"] = dict(state.get("task_draft") or {})
    state["missing_slots"] = list(state.get("missing_slots") or [])
    state["awaiting_confirmation"] = bool(state.get("awaiting_confirmation") or False)
    state["created_task"] = dict(state.get("created_task") or {})
    return state


async def history_loader(state: QualityChatState) -> QualityChatState:
    async with get_session() as session:
        repo = ChatMessageRepository(session)
        rows = await repo.list_for_session(
            org_id=str(state["org_id"]),
            session_id=str(state["session_id"]),
            after_seq=0,
            limit=20,
        )
    state["history"] = [
        {
            "role": row.role,
            "content": row.content,
            "message_type": row.message_type,
            "payload": row.payload or {},
        }
        for row in rows[:-1]
        if row.content or row.payload
    ]
    return state


async def planner(state: QualityChatState) -> QualityChatState:
    query = str(state.get("query") or "")
    history = list(state.get("history") or [])
    pending = _latest_pending_task(history)
    if pending is not None:
        state["intent"] = "task_followup"
        state["intent_confidence"] = 0.96 if (_is_confirm(query) or _is_cancel(query)) else 0.83
        state["task_draft"] = dict(pending.get("task_draft") or {})
        state["missing_slots"] = list(pending.get("missing_slots") or [])
        state["awaiting_confirmation"] = bool(pending.get("awaiting_confirmation"))
        state["pending_action"] = str(pending.get("pending_action") or "create_task")
    elif _is_smalltalk(query):
        state["intent"] = "smalltalk"
        state["intent_confidence"] = 0.98
    elif _is_task_create_candidate(query, state.get("ext") or {}):
        state["intent"] = "task_create"
        state["intent_confidence"] = 0.92
        state["pending_action"] = "create_task"
    elif _is_quality_qa_candidate(query, history):
        state["intent"] = "quality_qa"
        state["intent_confidence"] = 0.86
    else:
        state["intent"] = "general_qa"
        state["intent_confidence"] = 0.8

    state["metadata"]["intent"] = state["intent"]
    state["metadata"]["intent_confidence"] = state["intent_confidence"]
    state["metadata"]["target"] = {
        "quality_qa": "quality_assistant",
        "general_qa": "general_assistant",
        "smalltalk": "general_assistant",
    }.get(str(state["intent"]), "task_assistant")
    return state


async def task_extractor(state: QualityChatState) -> QualityChatState:
    if state.get("intent") not in {"task_create", "task_followup"}:
        return state

    query = str(state.get("query") or "")
    if _is_cancel(query):
        state["action_state"] = "task_cancelled"
        state["awaiting_confirmation"] = False
        state["pending_action"] = None
        state["missing_slots"] = []
        return state

    draft = _extract_task_draft(
        query,
        metadata=state.get("metadata") or {},
        ext=state.get("ext") or {},
        base_draft=state.get("task_draft") or {},
    )
    missing_slots = _missing_slots(draft)
    state["task_draft"] = draft
    state["missing_slots"] = missing_slots
    state["pending_action"] = "create_task"

    if _is_confirm(query) and state.get("awaiting_confirmation") and not missing_slots:
        state["action_state"] = "task_create_requested"
        state["awaiting_confirmation"] = False
        return state

    if missing_slots:
        state["action_state"] = "awaiting_task_details"
        state["awaiting_confirmation"] = False
        return state

    state["action_state"] = "awaiting_task_confirmation"
    state["awaiting_confirmation"] = True
    return state


async def knowledge(state: QualityChatState) -> QualityChatState:
    if state.get("intent") != "quality_qa":
        state["retrieved_chunks"] = []
        state["citations"] = []
        state["retrieval_metrics"] = {
            "query": state.get("query"),
            "hit_count": 0,
            "empty_recall": True,
            "top_score": 0.0,
            "skipped": True,
        }
        return state

    trace_id = str((state.get("trace") or {}).get("trace_id") or "")
    selected_rag = _selected_rag_space(state.get("ext") or {})
    payload_filter: dict[str, Any] = {
        "org_id": str(state["org_id"]),
        "user_id": str(state["user_id"]),
    }
    if selected_rag:
        payload_filter["rag_space_id"] = selected_rag["id"]

    retriever = Retriever(trace_id=trace_id or None, task_id=str(state["session_id"]), org_id=str(state["org_id"]))
    docs = await retriever.retrieve(str(state["query"]), top_k=4, payload_filter=payload_filter)
    citations = [
        {
            "id": doc.get("id"),
            "title": doc.get("title"),
            "source": doc.get("source"),
            "score": float(doc.get("score") or 0.0),
            "quote": str(doc.get("text") or "")[:180],
        }
        for doc in docs
    ]
    state["retrieved_chunks"] = docs
    state["citations"] = citations
    state["retrieval_metrics"] = {
        "query": state["query"],
        "hit_count": len(docs),
        "empty_recall": len(docs) == 0,
        "top_score": float(docs[0]["score"]) if docs else 0.0,
        "skipped": False,
        "rag_space_id": selected_rag["id"] if selected_rag else None,
    }
    return state


async def reasoning(state: QualityChatState) -> QualityChatState:
    intent = state.get("intent")
    if intent == "smalltalk":
        state["reasoning"] = {
            "answer": _smalltalk_answer(str(state.get("query") or "")),
            "summary": "普通对话",
            "citations": [],
        }
        state["action_state"] = "answered"
        return state

    if intent == "general_qa":
        llm = LLMClient(
            trace_id=str((state.get("trace") or {}).get("trace_id") or "") or None,
            task_id=str(state["session_id"]),
            org_id=str(state["org_id"]),
        )
        history_lines = [
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in list(state.get("history") or [])[-6:]
            if item.get("content")
        ]
        history_text = "\n".join(history_lines) if history_lines else "无"
        prompt = (
            "你是平台内的通用聊天助手。对于不属于质量检测、也不是任务创建的普通问答，"
            "请直接自然回答；如果用户信息不足，就简洁追问。"
            '只返回 JSON，格式为 {"answer": string, "summary": string}。'
        )
        user_message = f"问题:\n{state['query']}\n\n历史对话:\n{history_text}"
        try:
            response = await llm.chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.4,
                observation_name="quality_chat.general_reasoning",
                observation_metadata={"workflow_version": "quality_chat_v1"},
            )
            answer = str(response.get("answer") or "").strip()
            summary = str(response.get("summary") or "").strip()
            if not answer:
                fallback = _general_answer_fallback(str(state["query"]))
                answer = fallback["answer"]
                summary = fallback["summary"]
            state["reasoning"] = {
                "answer": answer,
                "summary": summary or "普通问答",
                "citations": [],
                "llm_meta": dict(response.get("__meta__") or {}),
            }
        except Exception as exc:
            state["reasoning"] = {
                **_general_answer_fallback(str(state["query"])),
                "llm_error": str(exc),
                "llm_meta": {},
            }
        state["action_state"] = "answered"
        return state

    if intent in {"task_create", "task_followup"}:
        action_state = str(state.get("action_state") or "answered")
        draft = dict(state.get("task_draft") or {})
        missing_slots = list(state.get("missing_slots") or [])
        if action_state == "task_cancelled":
            state["reasoning"] = {
                "answer": "好的，这次不创建检测任务了。之后如果你想继续创建，可以直接把产品编号、标准编号和图片发给我。",
                "summary": "任务创建已取消",
                "citations": [],
            }
            return state
        if action_state == "awaiting_task_details":
            missing_labels = "、".join(_slot_labels(missing_slots))
            state["reasoning"] = {
                "answer": (
                    "我已经识别到你想发起检测任务，但还缺少必要信息。\n\n"
                    f"当前已识别信息：\n{_format_task_draft(draft)}\n\n"
                    f"还需要补充：{missing_labels}。\n"
                    "你可以继续发送消息补充，也可以点击“补充信息”按钮直接填写表单。"
                ),
                "summary": "等待补充任务信息",
                "citations": [],
            }
            return state
        if action_state == "awaiting_task_confirmation":
            state["reasoning"] = {
                "answer": (
                    "我已经整理出一份检测任务草稿，请你确认是否创建：\n\n"
                    f"{_format_task_draft(draft)}\n\n"
                    "如果没有问题，可以继续回复“确认”，也可以直接打开补充信息表单进行修改后提交。"
                ),
                "summary": "等待用户确认任务创建",
                "citations": [],
            }
            return state
        if action_state == "task_create_requested":
            state["reasoning"] = {
                "answer": "任务信息已确认，我正在为你创建检测任务。",
                "summary": "准备创建任务",
                "citations": [],
            }
            return state

    docs = list(state.get("retrieved_chunks") or [])
    citations = list(state.get("citations") or [])
    llm = LLMClient(
        trace_id=str((state.get("trace") or {}).get("trace_id") or "") or None,
        task_id=str(state["session_id"]),
        org_id=str(state["org_id"]),
    )
    doc_lines = [
        "\n".join(
            [
                f"[{index}] 标题: {doc.get('title')}",
                f"来源: {doc.get('source')}",
                f"内容: {str(doc.get('text') or '')[:600]}",
            ]
        )
        for index, doc in enumerate(docs, start=1)
    ]
    history_lines = [
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in list(state.get("history") or [])[-6:]
        if item.get("content")
    ]
    history_text = "\n".join(history_lines) if history_lines else "无"
    doc_text = "\n\n".join(doc_lines) if doc_lines else "无"
    prompt = (
        "你是质量检测聊天智能体。请基于提供的历史对话和检索证据回答用户问题。"
        "如果证据不足，必须明确说明不确定性，不要编造标准条款。"
        '只返回 JSON，格式为 {"answer": string, "summary": string}。'
    )
    user_message = (
        f"问题:\n{state['query']}\n\n"
        f"历史对话:\n{history_text}\n\n"
        f"检索证据:\n{doc_text}"
    )
    try:
        response = await llm.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            observation_name="quality_chat.reasoning",
            observation_metadata={"workflow_version": "quality_chat_v1"},
        )
        answer = str(response.get("answer") or "").strip()
        summary = str(response.get("summary") or "").strip()
        meta = dict(response.get("__meta__") or {})
        if not answer:
            fallback = _fallback_answer(str(state["query"]), docs, citations)
            answer = fallback["answer"]
            summary = fallback["summary"]
        state["reasoning"] = {
            "answer": answer,
            "summary": summary or "质量检测问答",
            "citations": citations,
            "llm_meta": meta,
        }
        state["action_state"] = "answered"
    except Exception as exc:
        fallback = _fallback_answer(str(state["query"]), docs, citations)
        state["reasoning"] = {
            **fallback,
            "llm_error": str(exc),
            "llm_meta": {},
        }
        state["action_state"] = "answered"
    return state


async def quality_gate(state: QualityChatState) -> QualityChatState:
    if state.get("intent") != "quality_qa":
        state["quality"] = {}
        return state

    citations = list(state.get("citations") or [])
    answer = str((state.get("reasoning") or {}).get("answer") or "")
    hit_count = int((state.get("retrieval_metrics") or {}).get("hit_count") or 0)
    evidence_coverage = 1.0 if citations else 0.0
    traceability = min(1.0, len(citations) / 2) if citations else 0.0
    faithfulness = 0.92 if citations else 0.45
    confidence = 0.9 if hit_count >= 2 and citations else 0.55 if citations else 0.3
    hallucination_flags: list[str] = []
    if not citations:
        hallucination_flags.append("low_evidence")
    if len(answer) < 20:
        hallucination_flags.append("thin_answer")
    passed = (
        confidence >= 0.85
        and evidence_coverage >= 1.0
        and traceability >= 0.9
        and faithfulness >= 0.85
        and "low_evidence" not in hallucination_flags
    )
    risk_level = "green" if passed else ("yellow" if citations else "red")
    risk_score = 0.08 if passed else (0.42 if citations else 0.78)
    state["quality"] = {
        "confidence": round(confidence, 4),
        "evidence_coverage": round(evidence_coverage, 4),
        "traceability": round(traceability, 4),
        "faithfulness": round(faithfulness, 4),
        "hallucination_flags": hallucination_flags,
        "risk_level": risk_level,
        "risk_score": round(risk_score, 4),
        "passed": passed,
    }
    if not passed:
        state["reasoning"]["answer"] = (
            "以下回答基于当前可检索到的质量检测依据生成，但证据完整性不足，建议将其视为保守参考。\n\n"
            f"{state['reasoning']['answer']}\n\n"
            "如果你愿意，我可以继续根据更具体的标准编号、产品型号、缺陷位置或工艺上下文补充说明。"
        )
    return state


async def task_executor(state: QualityChatState) -> QualityChatState:
    if state.get("action_state") != "task_create_requested":
        return state

    draft = dict(state.get("task_draft") or {})
    try:
        async with get_session() as session:
            service = TaskService(session, str(state["org_id"]))
            task = await service.create_task(
                created_by=str(state["user_id"]),
                product_id=str(draft.get("product_id") or ""),
                spec_code=str(draft.get("spec_code") or ""),
                image_urls=list(draft.get("image_urls") or []),
                priority=int(draft.get("priority") or 5),
                metadata=dict(draft.get("metadata") or {}),
            )
            await session.commit()
        state["created_task"] = {
            "id": str(task.id),
            "status": str(task.status),
            "product_id": str(task.product_id),
            "spec_code": str(task.spec_code),
            "priority": int(task.priority),
            "image_count": len(task.image_urls or []),
        }
        state["action_state"] = "task_created"
        state["pending_action"] = None
        state["awaiting_confirmation"] = False
        state["missing_slots"] = []
        state["reasoning"] = {
            "answer": (
                "检测任务已创建成功。\n\n"
                f"任务 ID：{state['created_task']['id']}\n"
                f"产品编号：{state['created_task']['product_id']}\n"
                f"检测标准：{state['created_task']['spec_code']}\n"
                f"当前状态：{state['created_task']['status']}\n"
                f"图片数量：{state['created_task']['image_count']}"
            ),
            "summary": "任务创建成功",
            "citations": [],
        }
        return state
    except ValidationError as exc:
        message = str(exc)
        if "标准" in message and "spec_code" not in state["missing_slots"]:
            state["missing_slots"] = ["spec_code", *[item for item in state["missing_slots"] if item != "spec_code"]]
        state["action_state"] = "awaiting_task_details"
        state["pending_action"] = "create_task"
        state["awaiting_confirmation"] = False
        state["reasoning"] = {
            "answer": (
                "任务还没有创建成功，因为任务信息校验未通过。\n\n"
                f"原因：{message}\n\n"
                f"当前草稿：\n{_format_task_draft(draft)}\n\n"
                "请直接补充或修正后再发给我，我会重新整理。"
            ),
            "summary": "任务信息校验未通过",
            "citations": [],
        }
        return state
    except Exception as exc:
        state["action_state"] = "task_create_failed"
        state["pending_action"] = "create_task"
        state["awaiting_confirmation"] = False
        state["reasoning"] = {
            "answer": (
                "任务创建时出现了系统异常，暂时还没有落库成功。"
                "你不用重新整理整份草稿，可以稍后回复“确认”再次尝试，或者直接修改任务信息。"
            ),
            "summary": "任务创建失败",
            "citations": [],
            "error": str(exc),
        }
        return state


def _message_type_for_state(state: QualityChatState) -> str:
    action_state = str(state.get("action_state") or "answered")
    if action_state == "task_created":
        return "task_result"
    if action_state in {"awaiting_task_confirmation", "awaiting_task_details", "task_cancelled", "task_create_failed"}:
        return "task_action"
    if state.get("intent") in {"smalltalk", "general_qa"}:
        return "assistant_text"
    return "quality_answer"


async def response_writer(state: QualityChatState) -> QualityChatState:
    answer = str((state.get("reasoning") or {}).get("answer") or "")
    emit = state["emit"]
    chunk_size = 48
    for start in range(0, len(answer), chunk_size):
        await emit(
            {
                "event": "message_delta",
                "session_id": state["session_id"],
                "message_id": state["assistant_message_id"],
                "workflow_run_id": state["workflow_run_id"],
                "delta": answer[start : start + chunk_size],
            }
        )

    selected_rag = _selected_rag_space(state.get("ext") or {})
    attachments = [
        item
        for item in list((state.get("ext") or {}).get("attachments") or [])
        if isinstance(item, dict) and item.get("url")
    ]
    task_draft = dict(state.get("task_draft") or {})
    action_state = str(state.get("action_state") or "")
    state["response_payload"] = {
        "answer": answer,
        "citations": list(state.get("citations") or []),
        "quality": dict(state.get("quality") or {}),
        "trace_id": (state.get("trace") or {}).get("trace_id"),
        "workflow_version": state.get("workflow_version") or "quality_chat_v1",
        "prompt_version": state.get("prompt_version") or "builtin-quality-chat-v1",
        "retrieval_metrics": state.get("retrieval_metrics") or {},
        "summary": (state.get("reasoning") or {}).get("summary"),
        "intent": state.get("intent"),
        "intent_confidence": state.get("intent_confidence"),
        "action_state": action_state,
        "task_draft": task_draft or None,
        "task_form_defaults": task_draft or None,
        "task_submit_mode": "direct_create" if action_state in {"awaiting_task_details", "awaiting_task_confirmation"} else None,
        "missing_slots": list(state.get("missing_slots") or []),
        "pending_action": state.get("pending_action"),
        "awaiting_confirmation": bool(state.get("awaiting_confirmation") or False),
        "created_task": dict(state.get("created_task") or {}) or None,
        "selected_rag_space": selected_rag,
        "attachment_echo": attachments,
        "message_type": _message_type_for_state(state),
    }
    if state.get("quality"):
        await emit(
            {
                "event": "quality_signal",
                "session_id": state["session_id"],
                "message_id": state["assistant_message_id"],
                "workflow_run_id": state["workflow_run_id"],
                "quality": state.get("quality") or {},
            }
        )
    return state


async def finalizer(state: QualityChatState) -> QualityChatState:
    response_payload = state.get("response_payload") or {}
    async with get_session() as session:
        repo = ChatMessageRepository(session)
        await repo.update_assistant_message(
            org_id=str(state["org_id"]),
            message_id=str(state["assistant_message_id"]),
            content=str(response_payload.get("answer") or ""),
            message_type=str(response_payload.get("message_type") or "quality_answer"),
            payload=response_payload,
        )
        await session.commit()
    await state["emit"](
        {
            "event": "message_final",
            "session_id": state["session_id"],
            "message_id": state["assistant_message_id"],
            "workflow_run_id": state["workflow_run_id"],
            "content": str(response_payload.get("answer") or ""),
            "payload": response_payload,
            "quality": state.get("quality") or {},
        }
    )
    return state


class QualityChatGraph:
    def __init__(self) -> None:
        graph = StateGraph(QualityChatState)
        graph.add_node("input_adapter", input_adapter)
        graph.add_node("history_loader", history_loader)
        graph.add_node("planner", planner)
        graph.add_node("task_extractor", task_extractor)
        graph.add_node("knowledge", knowledge)
        graph.add_node("reasoning", reasoning)
        graph.add_node("quality_gate", quality_gate)
        graph.add_node("task_executor", task_executor)
        graph.add_node("response_writer", response_writer)
        graph.add_node("finalizer", finalizer)
        graph.set_entry_point("input_adapter")
        graph.add_edge("input_adapter", "history_loader")
        graph.add_edge("history_loader", "planner")
        graph.add_edge("planner", "task_extractor")
        graph.add_edge("task_extractor", "knowledge")
        graph.add_edge("knowledge", "reasoning")
        graph.add_edge("reasoning", "quality_gate")
        graph.add_edge("quality_gate", "task_executor")
        graph.add_edge("task_executor", "response_writer")
        graph.add_edge("response_writer", "finalizer")
        graph.add_edge("finalizer", END)
        self._graph = graph.compile()

    async def run(self, state: QualityChatState) -> QualityChatState:
        tracer = LangfuseTracer()
        trace = tracer.start_trace(
            task_id=state["session_id"],
            org_id=state["org_id"],
            model_key="quality_chat_v1",
            name="quality_chat_v1",
            input={"query": state["query"], "session_id": state["session_id"]},
        )
        state["trace"] = trace
        return await self._graph.ainvoke(state)
