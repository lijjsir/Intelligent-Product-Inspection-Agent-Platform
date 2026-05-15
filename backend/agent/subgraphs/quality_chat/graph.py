from __future__ import annotations

import asyncio
import logging
import re
from time import perf_counter
from typing import Any

from langgraph.graph import END, StateGraph

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.llm.langfuse_tracer import LangfuseTracer
from agent.llm.pricing import ModelPricing
from agent.rag.retriever import Retriever
from agent.subgraphs.quality_chat.state import QualityChatState
from app.core.exceptions import ValidationError
from app.core.ids import uuid7
from app.core.config import settings
from app.repositories.chat_repo import ChatMessageRepository
from app.repositories.agent_ops_repo import RagAnalysisRepository
from app.repositories.chat_score_repo import ChatMessageScoreRepository
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.user_token_usage_repo import UserTokenUsageSummaryRepository
from app.services.chat_trust_scoring_service import (
    build_pending_trust_score,
    trust_payload_from_score,
)
from app.services.dspy_runtime_service import build_runtime_prompt_section, resolve_dspy_runtime_profile
from app.services.model_config_service import ModelConfigService
from app.services.task_execution_service import launch_task_execution
from app.services.task_service import TaskService
from infra.database.session import get_session

logger = logging.getLogger(__name__)

SMALLTALK_PATTERNS = [re.compile(p, re.I) for p in [
    r"^\s*(你是谁|介绍一下自己|你是做什么的)\s*[？?]?\s*$",
    r"^\s*(你能做什么|你会什么|你可以做什么)\s*[？?]?\s*$",
    r"^\s*(hello|hi|hey|你好|嗨)\s*[!！。.]?\s*$",
    r"^\s*(我的名字是|我叫)\s*.+$",
    r"^\s*(who are you|what can you do)\s*[?？]?\s*$",
]]
NAME_INTRO_PATTERNS = [
    re.compile(r"^\s*(?:我的名字是|我叫)\s*([A-Za-z0-9_\-\u4e00-\u9fa5]{1,32})\s*$", re.I),
]
NAME_RECALL_PATTERNS = [
    re.compile(r"^\s*(?:我叫什么名字|你知道我叫什么吗|你还记得我叫什么吗|还记得我叫什么吗)\s*[？?]?\s*$", re.I),
]
TASK_CREATE_PATTERNS = [re.compile(p, re.I) for p in [
    r"(创建|新建|发起|提交).{0,8}(任务|检测|质检)",
    r"(帮我|给我).{0,8}(创建|发起|提交).{0,8}(任务|检测|质检)",
    r"(帮我|给我).{0,8}(进行|做).{0,8}(质量检测|质检|检测任务)",
    r"(需要|想要).{0,8}(创建|发起).{0,8}(任务|检测)",
    r"^\s*(质量检测|质检|检测任务|开始检测|启动检测|quality inspection|inspection task|start inspection)\s*[!！?.]?\s*$",
]]
CONFIRM_PATTERNS = [re.compile(r"^\s*(确认|确定|可以创建|开始创建|提交吧|创建吧|ok|okay|yes|confirm)\s*[!！。.]?\s*$", re.I)]
CANCEL_PATTERNS = [re.compile(r"^\s*(取消|不用了|算了|先不要|停止创建|别创建了|no)\s*[!！。.]?\s*$", re.I)]
QUALITY_QA_PATTERNS = [re.compile(p, re.I) for p in [
    r"(质量|质检|检测|检验|缺陷|瑕疵|判定|允收|不良|标准|规范|条款|公差|尺寸|外观|划痕|裂纹|毛刺|飞边|凹陷|污渍|色差|气泡|变形|烧焦|缩水|夹杂|焊点|工艺)",
    r"(QC|QA|IQC|IPQC|FQC|OQC|AQL|SOP|SIP|GB/?T|ISO\s*\d+)",
    r"(spec|defect|inspection|quality|standard|tolerance|scratch|burr|dent|stain|crack)",
]]
QUALITY_CONTEXT_PATTERNS = [re.compile(p, re.I) for p in [r"(这个|那个|这种|那种|该怎么|为什么|是否|算不算|属于|依据是什么|怎么判|如何判定)"]]
URL_PATTERN = re.compile(r"https?://[^\s,，；;]+", re.I)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_smalltalk(query: str) -> bool:
    text = _clean_text(query)
    return any(p.search(text) for p in SMALLTALK_PATTERNS)


def _extract_self_named_user(text: str) -> str | None:
    normalized = _clean_text(text)
    for pattern in NAME_INTRO_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return match.group(1).strip()
    return None


def _is_name_recall_query(query: str) -> bool:
    text = _clean_text(query)
    return any(p.search(text) for p in NAME_RECALL_PATTERNS)


def _extract_named_user_from_history(history: list[dict[str, Any]]) -> str | None:
    for item in reversed(history):
        if str(item.get("role") or "") != "user":
            continue
        name = _extract_self_named_user(str(item.get("content") or ""))
        if name:
            return name
    return None


def _has_recent_quality_context(history: list[dict[str, Any]]) -> bool:
    for item in reversed(history[-4:]):
        payload = item.get("payload") or {}
        if isinstance(payload, dict) and (
            payload.get("intent") == "quality_qa"
            or payload.get("message_type") == "quality_answer"
            or item.get("message_type") == "quality_answer"
        ):
            return True
    return False


def _is_quality_qa_candidate(query: str, history: list[dict[str, Any]] | None = None) -> bool:
    text = _clean_text(query)
    if not text:
        return False
    if any(p.search(text) for p in QUALITY_QA_PATTERNS):
        return True
    return _has_recent_quality_context(list(history or [])) and any(p.search(text) for p in QUALITY_CONTEXT_PATTERNS)


def _is_task_create_candidate(query: str, ext: dict[str, Any] | None) -> bool:
    text = _clean_text(query)
    if any(p.search(text) for p in TASK_CREATE_PATTERNS):
        return True
    attachments = list((ext or {}).get("attachments") or [])
    return any(str(item.get("kind") or "") == "image" for item in attachments if isinstance(item, dict))


def _is_confirm(query: str) -> bool:
    text = _clean_text(query)
    return any(p.search(text) for p in CONFIRM_PATTERNS)


def _is_cancel(query: str) -> bool:
    text = _clean_text(query)
    return any(p.search(text) for p in CANCEL_PATTERNS)


def _extract_first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip().strip("，。；;:：?")
    return None


def _extract_priority(query: str, base_priority: int = 5) -> int:
    patterns = [re.compile(r"优先级\s*[:：]?\s*(\d{1,2})"), re.compile(r"priority\s*[:：]?\s*(\d{1,2})", re.I)]
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
    for item in ext.get("attachments") or []:
        if isinstance(item, dict) and str(item.get("kind") or "") == "image" and str(item.get("url") or "").strip():
            candidates.append(str(item.get("url")).strip())
    candidates.extend(match.group(0).strip() for match in URL_PATTERN.finditer(query))
    merged: list[str] = []
    for item in [*(base or []), *candidates]:
        if item and item not in merged:
            merged.append(item)
    return merged


def _extract_task_draft(query: str, metadata: dict[str, Any] | None = None, ext: dict[str, Any] | None = None, base_draft: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    ext = ext or {}
    base_draft = dict(base_draft or {})
    text = query.strip()
    product_patterns = [
        re.compile(r"产品(?:编号|id|ID|型号)?\s*[:：为是]?\s*([A-Za-z0-9._-]+)"),
        re.compile(r"product(?:_id)?\s*[:：]?\s*([A-Za-z0-9._-]+)", re.I),
    ]
    spec_patterns = [
        re.compile(r"标准(?:编号|编码|号|code)?\s*[:：为是]?\s*([A-Za-z0-9._-]+)"),
        re.compile(r"检测标准(?:编号|编码|号)?\s*[:：为是]?\s*([A-Za-z0-9._-]+)"),
        re.compile(r"spec(?:_code)?\s*[:：]?\s*([A-Za-z0-9._-]+)", re.I),
    ]
    return {
        "product_id": str(ext.get("product_id") or metadata.get("product_id") or _extract_first_match(product_patterns, text) or base_draft.get("product_id") or "").strip(),
        "spec_code": str(ext.get("spec_code") or metadata.get("spec_code") or _extract_first_match(spec_patterns, text) or base_draft.get("spec_code") or "").strip(),
        "image_urls": _extract_image_urls(text, ext, base=list(base_draft.get("image_urls") or [])),
        "priority": _extract_priority(text, int(ext.get("priority") or metadata.get("priority") or base_draft.get("priority") or 5)),
        "metadata": {**dict(base_draft.get("metadata") or {}), **{k: v for k, v in metadata.items() if v is not None}},
    }


def _missing_slots(draft: dict[str, Any]) -> list[str]:
    missing = []
    if not str(draft.get("product_id") or "").strip():
        missing.append("product_id")
    if not str(draft.get("spec_code") or "").strip():
        missing.append("spec_code")
    if not list(draft.get("image_urls") or []):
        missing.append("image_urls")
    return missing


def _slot_labels(missing_slots: list[str]) -> list[str]:
    mapping = {"product_id": "产品编号", "spec_code": "检测标准编号", "image_urls": "检测图片"}
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
        if payload.get("action_state") in {"task_created", "task_cancelled", "task_started"}:
            return None
    return None


def _smalltalk_answer(query: str, history: list[dict[str, Any]] | None = None) -> str:
    if _is_name_recall_query(query):
        remembered_name = _extract_named_user_from_history(list(history or []))
        if remembered_name:
            return f"你之前告诉过我，你叫{remembered_name}。"
        return "你还没有告诉我你的名字。你可以直接说“我叫xxx”，我就能按当前会话记住。"
    introduced_name = _extract_self_named_user(query)
    if introduced_name:
        return f"好的，我记住了，你叫{introduced_name}。"
    if re.search(r"(你是谁|介绍一下自己)", query):
        return "我是质量检测聊天助手，可以帮你整理任务信息、解释质量标准、分析缺陷判定依据，也可以在信息补齐后直接发起检测任务。"
    return "我可以帮你解答质量检测问题，也可以把聊天里整理好的任务信息直接提交给智能体执行。"


def _general_answer_fallback(query: str) -> dict[str, Any]:
    return {
        "answer": f"我收到了你的问题“{query}”。如果你准备发起质量检测任务，也可以继续补充产品编号、检测标准和图片。",
        "summary": "普通问答",
        "citations": [],
    }


def _fallback_answer(query: str, docs: list[dict[str, Any]], citations: list[dict[str, Any]]) -> dict[str, Any]:
    if not docs:
        return {"answer": "当前没有检索到足够的质量检测依据，这次回答只能作为保守参考。", "summary": "证据不足，给出保守回答", "citations": citations}
    top = docs[0]
    excerpt = str(top.get("text") or "").strip()
    if len(excerpt) > 220:
        excerpt = f"{excerpt[:220]}..."
    return {
        "answer": f"基于当前检索到的资料，与你的问题“{query}”最相关的依据来自“{top.get('title') or '标准文档'}”。参考内容：{excerpt}",
        "summary": "基于检索结果生成的保守答案",
        "citations": citations,
    }


def _selected_rag_space(ext: dict[str, Any] | None) -> dict[str, Any] | None:
    ext = ext or {}
    selected = ext.get("selected_rag_space")
    if isinstance(selected, dict) and selected.get("id"):
        return {"id": str(selected.get("id")), "name": str(selected.get("name") or ""), "description": str(selected.get("description") or "") or None}
    rag_space_id = str(ext.get("selected_rag_space_id") or "").strip()
    if not rag_space_id:
        return None
    return {"id": rag_space_id, "name": str(ext.get("selected_rag_space_name") or ""), "description": str(ext.get("selected_rag_space_description") or "") or None}


def _dspy_runtime_meta(state: QualityChatState) -> dict[str, Any]:
    return dict((state.get("metadata") or {}).get("dspy_runtime") or {})


def _dspy_target_payload(state: QualityChatState, target_key: str) -> dict[str, Any]:
    return dict(_dspy_runtime_meta(state).get("targets", {}).get(target_key, {}).get("config_payload") or {})


def _dspy_prompt_section(state: QualityChatState, target_keys: list[str]) -> str:
    runtime_meta = _dspy_runtime_meta(state)
    targets = {}
    for key in target_keys:
        target = dict(runtime_meta.get("targets", {}).get(key) or {})
        if target:
            targets[key] = target
    if not targets:
        return ""
    profile_like = type(
        "ProfileLike",
        (),
        {
            "get": lambda self, item: type(
                "TargetLike",
                (),
                {
                    "is_enabled": True,
                    "target_key": item,
                    "artifact_version": str(targets[item].get("artifact_version") or ""),
                    "optimization_goal": str(targets[item].get("optimization_goal") or targets[item].get("module_name") or item),
                    "metric_names": list(targets[item].get("metric_names") or []),
                    "prompt_content": str(targets[item].get("prompt_content") or ""),
                    "config_payload": dict(targets[item].get("config_payload") or {}),
                },
            ) if item in targets else None,
        },
    )()
    return build_runtime_prompt_section(profile_like, [key for key in target_keys if key in targets])


async def input_adapter(state: QualityChatState) -> QualityChatState:
    runtime_profile = await resolve_dspy_runtime_profile(str(state["org_id"]), "quality_judgement")
    state["workflow_version"] = "quality_chat_v1"
    state["prompt_version"] = runtime_profile.active_prompt_version
    state["metadata"] = dict(state.get("metadata") or {})
    state["metadata"]["dspy_runtime"] = runtime_profile.as_metadata()
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
        rows = await repo.list_for_session(org_id=str(state["org_id"]), session_id=str(state["session_id"]), after_seq=0, limit=20)
    state["history"] = [{"role": row.role, "content": row.content, "message_type": row.message_type, "payload": row.payload or {}} for row in rows[:-1] if row.content or row.payload]
    return state


async def planner(state: QualityChatState) -> QualityChatState:
    query = str(state.get("query") or "")
    lowered_query = query.lower()
    history = list(state.get("history") or [])
    pending = _latest_pending_task(history)
    planner_payload = _dspy_target_payload(state, "quality_judgement.planner")
    extra_task_keywords = [str(item).strip().lower() for item in list(planner_payload.get("task_keywords") or []) if str(item).strip()]
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
    elif _is_task_create_candidate(query, state.get("ext") or {}) or any(keyword in lowered_query for keyword in extra_task_keywords):
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
    draft = _extract_task_draft(query, metadata=state.get("metadata") or {}, ext=state.get("ext") or {}, base_draft=state.get("task_draft") or {})
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
        state["retrieval_metrics"] = {"query": state.get("query"), "hit_count": 0, "empty_recall": True, "top_score": 0.0, "skipped": True}
        return state
    trace_id = str((state.get("trace") or {}).get("trace_id") or "")
    selected_rag = _selected_rag_space(state.get("ext") or {})
    payload_filter: dict[str, Any] = {"org_id": str(state["org_id"]), "user_id": str(state["user_id"])}
    if selected_rag:
        payload_filter["rag_space_id"] = selected_rag["id"]
    retriever = Retriever(trace_id=trace_id or None, task_id=str(state["session_id"]), org_id=str(state["org_id"]))
    knowledge_payload = _dspy_target_payload(state, "quality_judgement.knowledge")
    top_k = max(1, min(8, int(knowledge_payload.get("retrieval_top_k") or knowledge_payload.get("top_k") or 4)))
    started_at = perf_counter()
    docs = await retriever.retrieve(str(state["query"]), top_k=top_k, payload_filter=payload_filter)
    latency_ms = round((perf_counter() - started_at) * 1000)
    citations = [{"id": doc.get("id"), "title": doc.get("title"), "source": doc.get("source"), "score": float(doc.get("score") or 0.0), "quote": str(doc.get("text") or "")[:180]} for doc in docs]
    state["retrieved_chunks"] = docs
    state["citations"] = citations
    state["retrieval_metrics"] = {
        "query": state["query"],
        "hit_count": len(docs),
        "empty_recall": len(docs) == 0,
        "top_score": float(docs[0]["score"]) if docs else 0.0,
        "skipped": False,
        "latency_ms": latency_ms,
        "rag_space_id": selected_rag["id"] if selected_rag else None,
        "top_k": top_k,
    }
    return state


async def reasoning(state: QualityChatState) -> QualityChatState:
    _t_reasoning = perf_counter()
    intent = state.get("intent")
    query = str(state.get("query") or "")
    history = list(state.get("history") or [])
    docs = list(state.get("retrieved_chunks") or [])
    citations = list(state.get("citations") or [])
    action_state = str(state.get("action_state") or "answered")
    draft = dict(state.get("task_draft") or {})
    missing_slots = list(state.get("missing_slots") or [])

    history_lines = [f"{item.get('role', 'user')}: {item.get('content', '')}" for item in history[-6:] if item.get("content")]
    history_text = "\n".join(history_lines) if history_lines else "无"

    # ── Build system prompt per intent ──
    if intent == "smalltalk":
        prompt = (
            "你是平台内的智能助手。请友好、自然地回复用户的闲聊消息，可以适当展现个性。"
            "只返回 JSON：{\"answer\": string, \"summary\": string}。"
        )
        user_message = f"用户消息:\n{query}\n\n历史对话:\n{history_text}"
        temperature = 0.7

    elif intent in {"task_create", "task_followup"}:
        task_context = (
            f"当前任务草稿：\n{_format_task_draft(draft)}\n"
            f"缺失字段：{'、'.join(_slot_labels(missing_slots)) if missing_slots else '无'}\n"
            f"当前状态：{action_state}"
        )
        if action_state == "task_cancelled":
            prompt = (
                "你是平台内的质量检测助手。用户已取消任务创建。请友好地告知用户取消成功，并说明以后可继续发起。"
                "只返回 JSON：{\"answer\": string, \"summary\": string}。"
            )
        elif action_state == "awaiting_task_details":
            label_hints = "、".join(_slot_labels(missing_slots)) if missing_slots else "无"
            prompt = (
                f"你是平台内的质量检测助手。用户想创建检测任务但信息不完整，还需要补充：{label_hints}。\n"
                f"{task_context}\n"
                "请自然地告知用户当前进展，列出还需补充的信息，引导用户继续提供，并提示可以点击“填写检测信息”按钮直接填表。"
                "只返回 JSON：{\"answer\": string, \"summary\": string}。"
            )
        elif action_state == "awaiting_task_confirmation":
            prompt = (
                f"你是平台内的质量检测助手。任务信息已完整，等待用户确认。\n{task_context}\n"
                "请清晰展示任务草稿，引导用户回复“确认”或点击“确认并提交任务”按钮来提交。"
                "只返回 JSON：{\"answer\": string, \"summary\": string}。"
            )
        elif action_state == "task_create_requested":
            prompt = (
                "你是平台内的质量检测助手。任务正在创建中，请告知用户任务已接收，正在启动执行。"
                "只返回 JSON：{\"answer\": string, \"summary\": string}。"
            )
        else:
            prompt = (
                f"你是平台内的质量检测助手。用户提到了检测任务相关的内容。\n{task_context}\n"
                "请自然地回应用户，判断用户意图并引导用户明确任务需求。"
                "只返回 JSON：{\"answer\": string, \"summary\": string}。"
            )
        user_message = f"用户消息:\n{query}\n\n历史对话:\n{history_text}"
        temperature = 0.3

    elif intent == "quality_qa":
        doc_lines = ["\n".join([f"[{index}] 标题: {doc.get('title')}", f"来源: {doc.get('source')}", f"内容: {str(doc.get('text') or '')[:600]}"]) for index, doc in enumerate(docs, start=1)]
        doc_text = "\n\n".join(doc_lines) if doc_lines else "无"
        prompt = "你是质量检测聊天智能体。请严格基于检索证据回答，不足时明确说明不确定性。只返回 JSON：{\"answer\": string, \"summary\": string}。"
        user_message = f"问题:\n{query}\n\n历史对话:\n{history_text}\n\n检索证据:\n{doc_text}"
        temperature = 0.2

    else:  # general_qa
        prompt = "你是平台内的通用聊天助手。对普通问答直接自然回答；若信息不足就简洁追问。只返回 JSON：{\"answer\": string, \"summary\": string}。"
        user_message = f"问题:\n{query}\n\n历史对话:\n{history_text}"
        temperature = 0.4

    # ── Attach DSPy runtime prompt section if available ──
    prompt_section = _dspy_prompt_section(
        state,
        [
            "quality_judgement.planner",
            "quality_judgement.reasoning",
            "quality_judgement.response_writer",
        ],
    )
    if prompt_section:
        prompt = f"{prompt}\n\n{prompt_section}"

    # ── Unified LLM call ──
    _t_pre_llm = perf_counter()
    runtime_models: list[dict[str, Any]] = []
    runtime = None
    try:
        async with get_session() as session:
            runtime_models = await ModelConfigService(session, str(state["org_id"])).list_runtime_models()
        runtime = await LLMGateway().select_runtime(runtime_models)
    except Exception:
        runtime = None
    _t_runtime = perf_counter()
    llm = LLMClient(
        api_key=None if not runtime else runtime.get("api_key"),
        base_url=None if not runtime else runtime.get("base_url"),
        model_id=None if not runtime else runtime.get("model_id"),
        trace_id=str((state.get("trace") or {}).get("trace_id") or "") or None,
        task_id=str(state["session_id"]),
        org_id=str(state["org_id"]),
        provider=None if not runtime else str(runtime.get("provider") or ""),
        input_price_per_million=None if not runtime else runtime.get("input_price_per_million"),
        output_price_per_million=None if not runtime else runtime.get("output_price_per_million"),
    )
    obs_name = f"quality_chat.{intent}" if intent else "quality_chat.reasoning"
    try:
        response = await llm.chat(
            [{"role": "system", "content": prompt}, {"role": "user", "content": user_message}],
            temperature=temperature,
            observation_name=obs_name,
            observation_metadata={"workflow_version": "quality_chat_v1", "intent": intent},
        )
        answer = str(response.get("answer") or "").strip()
        summary = str(response.get("summary") or "").strip()
        if not answer:
            if intent == "quality_qa":
                fallback = _fallback_answer(query, docs, citations)
            else:
                fallback = _general_answer_fallback(query)
            answer, summary = fallback["answer"], fallback["summary"]
        state["reasoning"] = {
            "answer": answer,
            "summary": summary or "对话回复",
            "citations": citations,
            "llm_meta": dict(response.get("__meta__") or {}),
        }
    except Exception as exc:
        if intent == "quality_qa":
            fallback = _fallback_answer(query, docs, citations)
        else:
            fallback = _general_answer_fallback(query)
        state["reasoning"] = {**fallback, "llm_error": str(exc), "llm_meta": {}}
    state["action_state"] = "answered"
    _t_end = perf_counter()
    logger.info(
        "reasoning intent=%s answer_len=%d runtime_ms=%d llm_ms=%d total_ms=%d",
        intent, len(answer), round((_t_runtime - _t_pre_llm) * 1000), round((_t_end - _t_runtime) * 1000), round((_t_end - _t_reasoning) * 1000),
    )
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
    hallucination_flags = []
    if not citations:
        hallucination_flags.append("low_evidence")
    if len(answer) < 20:
        hallucination_flags.append("thin_answer")
    passed = confidence >= 0.85 and evidence_coverage >= 1.0 and traceability >= 0.9 and faithfulness >= 0.85 and "low_evidence" not in hallucination_flags
    risk_level = "low" if passed else ("medium" if citations else "critical")
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
        state["reasoning"]["answer"] = "以下回答基于当前可检索到的质量检测依据生成，但证据完整性不足，建议将其视为保守参考。\n\n" + state["reasoning"]["answer"] + "\n\n如果你愿意，我可以继续根据更具体的标准编号、产品型号、缺陷位置或工艺上下文补充说明。"
    return state


async def task_executor(state: QualityChatState) -> QualityChatState:
    if state.get("action_state") != "task_create_requested":
        return state
    draft = dict(state.get("task_draft") or {})
    metadata = {**dict(draft.get("metadata") or {}), "source": "chat", "chat_session_id": str(state["session_id"]), "chat_request_id": str(state.get("request_id") or "")}
    try:
        async with get_session() as session:
            service = TaskService(session, str(state["org_id"]))
            task = await service.create_task(
                created_by=str(state["user_id"]),
                product_id=str(draft.get("product_id") or ""),
                spec_code=str(draft.get("spec_code") or ""),
                image_urls=list(draft.get("image_urls") or []),
                priority=int(draft.get("priority") or 5),
                metadata=metadata,
            )
            await session.commit()
        launch = await launch_task_execution(task_id=str(task.id), org_id=str(state["org_id"]))
        state["created_task"] = {
            "id": str(task.id),
            "status": "running",
            "product_id": str(task.product_id),
            "spec_code": str(task.spec_code),
            "priority": int(task.priority),
            "image_count": len(task.image_urls or []),
            "execution": launch,
        }
        state["action_state"] = "task_started"
        state["pending_action"] = None
        state["awaiting_confirmation"] = False
        state["missing_slots"] = []
        state["reasoning"] = {
            "answer": "检测任务已创建并启动执行。\n\n"
            f"任务 ID：{state['created_task']['id']}\n"
            f"产品编号：{state['created_task']['product_id']}\n"
            f"检测标准：{state['created_task']['spec_code']}\n"
            f"执行方式：{launch['mode']}\n"
            f"图片数量：{state['created_task']['image_count']}",
            "summary": "任务已创建并启动",
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
            "answer": "任务还没有创建成功，因为任务信息校验未通过。\n\n"
            f"原因：{message}\n\n当前草稿：\n{_format_task_draft(draft)}\n\n请直接补充或修正后再发送给我，我会重新整理。",
            "summary": "任务信息校验未通过",
            "citations": [],
        }
        return state
    except Exception as exc:
        state["action_state"] = "task_create_failed"
        state["pending_action"] = "create_task"
        state["awaiting_confirmation"] = False
        state["reasoning"] = {
            "answer": "任务创建或启动时出现了系统异常，暂时还没有成功提交。你稍后可以再次回复“确认”，或者直接修改任务信息后重新提交。",
            "summary": "任务创建失败",
            "citations": [],
            "error": str(exc),
        }
        return state


def _message_type_for_state(state: QualityChatState) -> str:
    action_state = str(state.get("action_state") or "answered")
    if action_state in {"task_started", "task_finished"}:
        return "task_result"
    if action_state in {"awaiting_task_confirmation", "awaiting_task_details", "task_cancelled", "task_create_failed"}:
        return "task_action"
    if state.get("intent") in {"smalltalk", "general_qa"}:
        return "assistant_text"
    return "quality_answer"


def _chat_usage_from_state(state: QualityChatState) -> dict[str, Any] | None:
    llm_meta = dict((state.get("reasoning") or {}).get("llm_meta") or {})
    usage = LLMClient._normalize_usage(llm_meta.get("usage"))
    if not usage:
        return None
    model_key = str(llm_meta.get("model") or "").strip() or "unknown"
    pricing = dict(llm_meta.get("pricing") or {})
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    if total_tokens <= 0:
        return None
    return {
        "model_key": model_key,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "trace_id": str(
            llm_meta.get("langfuse", {}).get("trace_id")
            or (state.get("trace") or {}).get("trace_id")
            or ""
        ).strip()
        or None,
        "cost_amount": ModelPricing.estimate_cost(
            model_key,
            prompt_tokens,
            completion_tokens,
            input_price_per_million=pricing.get("input_price_per_million"),
            output_price_per_million=pricing.get("output_price_per_million"),
        ),
    }


async def _persist_chat_token_usage(session, state: QualityChatState) -> None:
    usage = _chat_usage_from_state(state)
    if not usage:
        return
    token_repo = TokenLedgerRepository(session)
    user_summary_repo = UserTokenUsageSummaryRepository(session)
    await token_repo.create(
        {
            "id": str(uuid7()),
            "org_id": str(state["org_id"]),
            "user_id": str(state["user_id"]),
            "task_id": None,
            "result_id": None,
            "model_config_id": None,
            "model_key": usage["model_key"],
            "product_line": str(state.get("workspace") or "chat"),
            "trace_id": usage["trace_id"],
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "cost_amount": usage["cost_amount"],
        }
    )
    await user_summary_repo.increment(
        org_id=str(state["org_id"]),
        user_id=str(state["user_id"]),
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        cost_amount=float(usage["cost_amount"]),
    )


async def _persist_rag_query_log(session, state: QualityChatState) -> None:
    metrics = dict(state.get("retrieval_metrics") or {})
    if bool(metrics.get("skipped")):
        return
    rag_repo = RagAnalysisRepository(session, str(state["org_id"]))
    citation_count = len(list(state.get("citations") or []))
    hit_count = int(metrics.get("hit_count") or 0)
    hit_rate = min(1.0, hit_count / 4) if hit_count else 0.0
    coverage = 0.0
    if hit_count > 0:
        coverage = min(1.0, citation_count / hit_count)
    await rag_repo.create_log(
        {
            "session_id": str(state["session_id"]),
            "user_id": str(state["user_id"]),
            "query": str(metrics.get("query") or state.get("query") or ""),
            "rag_space_id": metrics.get("rag_space_id"),
            "hit_count": hit_count,
            "hit_rate": round(hit_rate, 4),
            "citation_coverage": round(coverage, 4),
            "latency_ms": int(metrics.get("latency_ms") or 0),
            "source_graph": "quality_judgement",
            "metadata_json": {
                "intent": state.get("intent"),
                "empty_recall": bool(metrics.get("empty_recall")),
                "top_score": float(metrics.get("top_score") or 0.0),
            },
        }
    )


async def response_writer(state: QualityChatState) -> QualityChatState:
    _t0 = perf_counter()
    answer = str((state.get("reasoning") or {}).get("answer") or "")
    emit = state["emit"]
    for start in range(0, len(answer), 3):
        await emit({"event": "message_delta", "session_id": state["session_id"], "message_id": state["assistant_message_id"], "workflow_run_id": state["workflow_run_id"], "delta": answer[start : start + 3]})
        await asyncio.sleep(0.025)
    selected_rag = _selected_rag_space(state.get("ext") or {})
    attachments = [item for item in list((state.get("ext") or {}).get("attachments") or []) if isinstance(item, dict) and item.get("url")]
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
        "dspy_runtime": _dspy_runtime_meta(state),
        "message_type": _message_type_for_state(state),
    }
    state["trust_scoring_payload"] = _build_trust_scoring_request(state, state["response_payload"])
    if state.get("quality"):
        await emit({"event": "quality_signal", "session_id": state["session_id"], "message_id": state["assistant_message_id"], "workflow_run_id": state["workflow_run_id"], "quality": state.get("quality") or {}})
    logger.info(
        "response_writer intent=%s answer_len=%d stream_ms=%d",
        state.get("intent"), len(answer), round((perf_counter() - _t0) * 1000),
    )
    return state


def _build_trust_scoring_request(state: QualityChatState, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.trust_scoring_enabled or not str(payload.get("answer") or "").strip():
        return None
    llm_meta = dict((state.get("reasoning") or {}).get("llm_meta") or {})
    langfuse_meta = dict(llm_meta.get("langfuse") or {})
    return {
        "org_id": str(state["org_id"]),
        "session_id": str(state["session_id"]),
        "user_id": str(state["user_id"]),
        "assistant_message_id": str(state["assistant_message_id"]),
        "input_text": str(state.get("query") or ""),
        "output_text": str(payload.get("answer") or ""),
        "citations": list(payload.get("citations") or []),
        "trace_id": str(langfuse_meta.get("trace_id") or (state.get("trace") or {}).get("trace_id") or "") or None,
        "observation_id": str(langfuse_meta.get("observation_id") or "") or None,
        "model_key": str(llm_meta.get("model") or "") or None,
    }


def _enqueue_trust_scoring(payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    try:
        from worker.tasks.chat_trust_scoring_task import score_chat_message

        score_chat_message.delay(payload)
    except Exception as exc:
        logger.warning(
            "trust scoring enqueue failed assistant_message_id=%s trace_id=%s: %s",
            payload.get("assistant_message_id"),
            payload.get("trace_id"),
            exc,
            exc_info=True,
        )
        return


async def finalizer(state: QualityChatState) -> QualityChatState:
    _t0 = perf_counter()
    payload = state.get("response_payload") or {}
    trust_score: dict[str, Any] | None = None
    trust_request = state.get("trust_scoring_payload")
    if trust_request:
        trust_score = build_pending_trust_score(**trust_request)
        payload = {**payload, "trust_scoring": trust_payload_from_score(trust_score)}
        _enqueue_trust_scoring(trust_request)
    state["response_payload"] = payload
    async with get_session() as session:
        repo = ChatMessageRepository(session)
        await repo.update_assistant_message(org_id=str(state["org_id"]), message_id=str(state["assistant_message_id"]), content=str(payload.get("answer") or ""), message_type=str(payload.get("message_type") or "quality_answer"), payload=payload)
        if trust_score:
            await ChatMessageScoreRepository(session).upsert_by_message_version(trust_score)
        await _persist_chat_token_usage(session, state)
        await _persist_rag_query_log(session, state)
        await session.commit()
    await state["emit"]({"event": "message_final", "session_id": state["session_id"], "message_id": state["assistant_message_id"], "workflow_run_id": state["workflow_run_id"], "content": str(payload.get("answer") or ""), "payload": payload, "quality": state.get("quality") or {}})
    logger.info(
        "finalizer intent=%s trust_status=%s db_ms=%d total_ms=%d",
        state.get("intent"), (trust_score or {}).get("status", "none"), 0, round((perf_counter() - _t0) * 1000),
    )
    return state


class QualityChatGraph:
    def __init__(self) -> None:
        graph = StateGraph(QualityChatState)
        for name, node in [
            ("input_adapter", input_adapter),
            ("history_loader", history_loader),
            ("planner", planner),
            ("task_extractor", task_extractor),
            ("knowledge", knowledge),
            ("reasoning", reasoning),
            ("quality_gate", quality_gate),
            ("task_executor", task_executor),
            ("response_writer", response_writer),
            ("finalizer", finalizer),
        ]:
            graph.add_node(name, node)
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
        _t_graph = perf_counter()
        tracer = LangfuseTracer()
        state["trace"] = tracer.start_trace(task_id=state["session_id"], org_id=state["org_id"], model_key="quality_chat_v1", name="quality_chat_v1", input={"query": state["query"], "session_id": state["session_id"]})
        result = await self._graph.ainvoke(state)
        logger.info(
            "graph_total intent=%s query_len=%d total_ms=%d",
            result.get("intent"), len(str(result.get("query") or "")), round((perf_counter() - _t_graph) * 1000),
        )
        return result
