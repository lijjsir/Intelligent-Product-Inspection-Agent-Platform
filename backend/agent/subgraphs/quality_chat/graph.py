from __future__ import annotations

import asyncio
import json
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
from agent.subgraphs.quality_chat.state import ChatState
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
from app.services.chat_trust_scoring_dispatcher import enqueue_chat_trust_scoring
from app.services.runtime_profile_service import build_runtime_prompt_section, resolve_runtime_profile
from app.services.model_config_service import ModelConfigService
from app.services.system_rag_service import resolve_and_search_system_rag
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
    r"^\s*(质量检测|质检|任务检测|检测任务|开始检测|启动检测|quality inspection|inspection task|start inspection)\s*[!！?.]?\s*$",
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
        return "我是 PIAP 平台的智能助手，可以陪你聊天、回答问题，也可以帮你使用平台的质量检测、知识库检索等功能。有什么我可以帮你的吗？"
    return "你好！我是 PIAP 智能助手，可以陪你聊天、解答问题。如果你需要使用质量检测或任务管理功能，也可以随时告诉我。"


def _general_answer_fallback(query: str) -> dict[str, Any]:
    return {
        "answer": f"抱歉，我暂时无法处理你的问题「{query}」。请换个方式描述一下，或者告诉我你需要什么帮助？",
        "summary": "普通问答（兜底）",
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


def _rag_answer_fallback(query: str, docs: list[dict[str, Any]], citations: list[dict[str, Any]]) -> dict[str, Any]:
    if not docs:
        return {
            "answer": (
                "当前知识库没有检索到可引用依据；同时模型本次未生成有效回复，"
                f"因此暂时无法可靠回答“{query}”。请稍后重试或补充知识库资料。"
            ),
            "summary": "RAG 未命中且模型回复兜底失败",
            "citations": citations,
        }
    top = docs[0]
    excerpt = str(top.get("text") or "").strip()
    if len(excerpt) > 220:
        excerpt = f"{excerpt[:220]}..."
    return {
        "answer": excerpt,
        "summary": "基于知识库回答",
        "citations": citations,
    }


def _selected_rag_space(ext: dict[str, Any] | None) -> dict[str, Any] | None:
    ext = ext or {}
    selected = ext.get("selected_rag_space")
    if isinstance(selected, dict) and selected.get("id"):
        return {"id": str(selected.get("id")), "name": str(selected.get("name") or ""), "description": str(selected.get("description") or "") or None}
    rag_scope = ext.get("rag_scope")
    if isinstance(rag_scope, dict) and rag_scope.get("enabled", True):
        scoped_rag_space_id = str(rag_scope.get("rag_space_id") or "").strip()
        if scoped_rag_space_id:
            return {
                "id": scoped_rag_space_id,
                "name": str(rag_scope.get("rag_space_name") or ext.get("selected_rag_space_name") or ""),
                "description": str(rag_scope.get("rag_space_description") or ext.get("selected_rag_space_description") or "") or None,
            }
    rag_space_id = str(ext.get("selected_rag_space_id") or "").strip()
    if not rag_space_id:
        return None
    return {"id": rag_space_id, "name": str(ext.get("selected_rag_space_name") or ""), "description": str(ext.get("selected_rag_space_description") or "") or None}


def _selected_rag_scope_node_ids(ext: dict[str, Any] | None) -> list[str]:
    ext = ext or {}
    rag_scope = ext.get("rag_scope")
    if isinstance(rag_scope, dict) and rag_scope.get("enabled", True):
        raw = rag_scope.get("scope_node_ids") or []
    else:
        raw = ext.get("selected_rag_scope_node_ids") or []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _runtime_profile_meta(state: ChatState) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    return dict(metadata.get("runtime_profile") or {})


def _runtime_target_payload(state: ChatState, target_key: str) -> dict[str, Any]:
    return dict(_runtime_profile_meta(state).get("targets", {}).get(target_key, {}).get("config_payload") or {})


def _runtime_prompt_section(state: ChatState, target_keys: list[str]) -> str:
    runtime_meta = _runtime_profile_meta(state)
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


async def input_adapter(state: ChatState) -> ChatState:
    runtime_profile = await resolve_runtime_profile(str(state["org_id"]), "quality_judgement")
    state["workflow_version"] = "quality_chat_v2"
    state["prompt_version"] = runtime_profile.active_prompt_version
    state["metadata"] = dict(state.get("metadata") or {})
    state["metadata"]["runtime_profile"] = runtime_profile.as_metadata()
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


async def history_loader(state: ChatState) -> ChatState:
    async with get_session() as session:
        repo = ChatMessageRepository(session)
        rows = await repo.list_for_session(org_id=str(state["org_id"]), session_id=str(state["session_id"]), after_seq=0, limit=20)
    current_user_seq_no = int((state.get("ext") or {}).get("current_user_seq_no") or 0)
    if current_user_seq_no > 0:
        rows = [row for row in rows if int(row.seq_no or 0) < current_user_seq_no]
    else:
        rows = rows[:-1]
    state["history"] = [{"role": row.role, "content": row.content, "message_type": row.message_type, "payload": row.payload or {}} for row in rows if row.content or row.payload]
    return state


async def planner(state: ChatState) -> ChatState:
    query = str(state.get("query") or "")
    lowered_query = query.lower()
    history = list(state.get("history") or [])
    pending = _latest_pending_task(history)
    selected_rag = _selected_rag_space(state.get("ext") or {})
    planner_payload = _runtime_target_payload(state, "quality_judgement.planner")
    extra_task_keywords = [str(item).strip().lower() for item in list(planner_payload.get("task_keywords") or []) if str(item).strip()]
    if pending is not None:
        state["intent"] = "task_followup"
        state["intent_confidence"] = 0.96 if (_is_confirm(query) or _is_cancel(query)) else 0.83
        state["task_draft"] = dict(pending.get("task_draft") or {})
        state["missing_slots"] = list(pending.get("missing_slots") or [])
        state["awaiting_confirmation"] = bool(pending.get("awaiting_confirmation"))
        state["pending_action"] = str(pending.get("pending_action") or "create_task")
    elif _is_task_create_candidate(query, state.get("ext") or {}) or any(keyword in lowered_query for keyword in extra_task_keywords):
        state["intent"] = "task_create"
        state["intent_confidence"] = 0.92
        state["pending_action"] = "create_task"
    elif selected_rag is not None:
        state["intent"] = "rag_qa"
        state["intent_confidence"] = 0.9
        state["metadata"]["rag_forced_by_selection"] = True
    elif _is_smalltalk(query):
        state["intent"] = "smalltalk"
        state["intent_confidence"] = 0.98
    elif _is_quality_qa_candidate(query, history):
        state["intent"] = "quality_qa"
        state["intent_confidence"] = 0.86
    else:
        state["intent"] = "general_qa"
        state["intent_confidence"] = 0.8
    state["metadata"]["intent"] = state["intent"]
    state["metadata"]["intent_confidence"] = state["intent_confidence"]
    return state


async def task_extractor(state: ChatState) -> ChatState:
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


async def knowledge(state: ChatState) -> ChatState:
    if state.get("retrieved_chunks"):
        return state
    from agent.rag.rag_policy import RagPolicy
    rag_policy = RagPolicy()
    sub_route = state.get("sub_route", state.get("intent", "general_chat"))
    selected_rag = _selected_rag_space(state.get("ext") or {}) or {}

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

    scope_node_ids = _selected_rag_scope_node_ids(state.get("ext") or {})
    knowledge_payload = _runtime_target_payload(state, "quality_judgement.knowledge")
    top_k = max(1, min(8, int(knowledge_payload.get("retrieval_top_k") or knowledge_payload.get("top_k") or policy_decision.top_k)))
    async with get_session() as session:
        rag_result = await resolve_and_search_system_rag(
            session=session,
            org_id=str(state["org_id"]),
            user_id=str(state["user_id"]),
            query=str(state["query"]),
            product_family=str(state.get("metadata", {}).get("product_family") or "").strip() or None,
            product_id=str(state.get("metadata", {}).get("product_id") or "").strip() or None,
            spec_code=str(state.get("metadata", {}).get("spec_code") or "").strip() or None,
            user_rag_space_id=policy_decision.rag_space_id,
            scope_node_ids=scope_node_ids,
            top_k=top_k,
        )
    docs = list(rag_result.get("hits") or [])
    latency_ms = round(float(rag_result.get("latency_ms") or 0.0))
    citations = [{"id": doc.get("id"), "title": doc.get("title"), "source": doc.get("source"), "score": float(doc.get("score") or 0.0), "quote": str(doc.get("quote") or doc.get("text") or "")[:180]} for doc in docs]
    state["retrieved_chunks"] = docs
    state["citations"] = citations
    state["retrieval_metrics"] = {
        "query": state["query"],
        "hit_count": len(docs),
        "empty_recall": len(docs) == 0,
        "top_score": float(docs[0]["score"]) if docs else 0.0,
        "skipped": False,
        "latency_ms": latency_ms,
        "rag_space_id": rag_result.get("rag_space_id"),
        "rag_space_ids": list(rag_result.get("rag_space_ids") or []),
        "rag_space_names": list(rag_result.get("rag_space_names") or []),
        "system_rag_space_ids": list(rag_result.get("system_rag_space_ids") or []),
        "system_rag_space_names": list(rag_result.get("system_rag_space_names") or []),
        "standard_binding_name": rag_result.get("standard_binding_name"),
        "candidate_count": int(rag_result.get("candidate_count") or len(docs)),
        "rejected_count": int(rag_result.get("rejected_count") or 0),
        "score_threshold": rag_result.get("score_threshold"),
        "top_k": top_k,
    }
    return state


async def reasoning(state: ChatState) -> ChatState:
    _t_reasoning = perf_counter()
    intent = state.get("intent")
    query = str(state.get("query") or "")
    history = list(state.get("history") or [])
    docs = list(state.get("retrieved_chunks") or [])
    citations = list(state.get("citations") or [])
    action_state = str(state.get("action_state") or "answered")
    draft = dict(state.get("task_draft") or {})
    missing_slots = list(state.get("missing_slots") or [])

    # ── Build system prompt via PromptBuilder ──
    from agent.prompts.prompt_builder import PromptBuilder

    agent_name = state.get("agent", "chat")
    sub_route = state.get("sub_route", intent or "general_chat")

    # Map old intents to new sub_routes for backward compat
    if not state.get("sub_route"):
        if intent == "smalltalk":
            sub_route = "general_chat"
        elif intent in {"task_create", "task_followup"}:
            sub_route = "task_create"
        elif intent == "rag_qa":
            sub_route = "rag_qa"
        elif intent == "quality_qa":
            sub_route = "quality_qa"
        else:
            sub_route = "general_chat"

    prompt, user_message, temperature, prompt_meta = await PromptBuilder.build_runtime(
        agent=agent_name,
        sub_route=sub_route,
        query=query,
        org_id=str(state["org_id"]),
        history=history,
        retrieved_docs=docs if sub_route in {"rag_qa", "quality_qa", "inspection_execute"} else None,
        task_draft=draft if sub_route in {"task_create"} else None,
        action_state=action_state,
        runtime_prompt_section=_runtime_prompt_section(
            state,
            [
                "quality_judgement.planner",
                "quality_judgement.reasoning",
                "quality_judgement.response_writer",
            ],
        ),
    )

    state["prompt_version"] = prompt_meta["prompt_version"]
    state["sub_route"] = sub_route
    state["agent"] = agent_name

    # ── Unified LLM call ──
    _t_pre_llm = perf_counter()
    async with get_session() as session:
        runtime_models = await ModelConfigService(session, str(state["org_id"])).list_runtime_models()
    runtime = await LLMGateway().select_runtime(runtime_models)
    _t_runtime = perf_counter()
    if not runtime:
        raise RuntimeError("no runtime model available — please configure and enable a model in the model config page")
    llm = LLMClient(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        model_id=runtime.get("model_id"),
        trace_id=str((state.get("trace") or {}).get("trace_id") or "") or None,
        task_id=str(state["session_id"]),
        org_id=str(state["org_id"]),
        provider=str(runtime.get("provider") or ""),
        input_price_per_million=runtime.get("input_price_per_million"),
        output_price_per_million=runtime.get("output_price_per_million"),
    )
    obs_name = f"chat.{sub_route}" if sub_route else "chat.reasoning"
    answer = ""
    summary = ""
    try:
        response = await llm.chat(
            [{"role": "system", "content": prompt}, {"role": "user", "content": user_message}],
            temperature=temperature,
            observation_name=obs_name,
            observation_metadata={
                "workflow_version": "quality_chat_v2",
                "agent": agent_name,
                "sub_route": sub_route,
                "intent": intent,
                "prompt_version": state.get("prompt_version"),
            },
        )
        answer = str(response.get("answer") or "").strip()
        summary = str(response.get("summary") or "").strip()
        # If the LLM returned raw text instead of structured JSON, try to parse or use it directly
        if not answer and "text" in response:
            raw_text = str(response["text"]).strip()
            try:
                parsed = json.loads(raw_text)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                answer = str(parsed.get("answer") or "").strip()
                summary = str(parsed.get("summary") or "").strip()
            if not answer:
                answer = raw_text
                summary = summary or "普通问答"
        if not answer:
            if intent == "quality_qa":
                fallback = _fallback_answer(query, docs, citations)
            elif intent == "rag_qa":
                fallback = _rag_answer_fallback(query, docs, citations)
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
        elif intent == "rag_qa":
            fallback = _rag_answer_fallback(query, docs, citations)
        else:
            fallback = _general_answer_fallback(query)
        answer = str(fallback.get("answer") or "")
        summary = str(fallback.get("summary") or "")
        state["reasoning"] = {**fallback, "llm_error": str(exc), "llm_meta": {}}
    state["action_state"] = "answered"
    _t_end = perf_counter()
    logger.info(
        "reasoning intent=%s answer_len=%d runtime_ms=%d llm_ms=%d total_ms=%d",
        intent, len(answer), round((_t_runtime - _t_pre_llm) * 1000), round((_t_end - _t_runtime) * 1000), round((_t_end - _t_reasoning) * 1000),
    )
    return state



async def quality_gate(state: ChatState) -> ChatState:
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


async def task_executor(state: ChatState) -> ChatState:
    if state.get("action_state") != "task_create_requested":
        return state
    draft = dict(state.get("task_draft") or {})
    state["created_task"] = None
    state["action_state"] = "blocked"
    state["pending_action"] = "create_task"
    state["awaiting_confirmation"] = False
    state["reasoning"] = {
        "answer": "聊天页面不能创建或执行正式质量检测任务。\n\n"
        f"当前草稿：\n{_format_task_draft(draft)}\n\n"
        "请前往质量检测任务页面确认并提交，正式任务只会在那里创建、执行和落库。",
        "summary": "聊天页已阻止正式任务创建",
        "citations": [],
    }
    return state


def _message_type_for_state(state: ChatState) -> str:
    action_state = str(state.get("action_state") or "answered")
    if action_state in {"task_started", "task_finished"}:
        return "task_result"
    if action_state in {"awaiting_task_confirmation", "awaiting_task_details", "task_cancelled", "task_create_failed"}:
        return "task_action"
    if state.get("intent") in {"smalltalk", "general_qa", "rag_qa"}:
        return "assistant_text"
    return "quality_answer"


def _chat_usage_from_state(state: ChatState) -> dict[str, Any] | None:
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


async def _persist_chat_token_usage(session, state: ChatState) -> None:
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


async def _persist_rag_query_log(session, state: ChatState) -> None:
    metrics = dict(state.get("retrieval_metrics") or {})
    if bool(metrics.get("skipped")):
        return
    rag_repo = RagAnalysisRepository(session, str(state["org_id"]))
    citations = [dict(item) for item in list(state.get("citations") or []) if isinstance(item, dict)]
    retrieved_chunks = [dict(item) for item in list(state.get("retrieved_chunks") or []) if isinstance(item, dict)]
    response_payload = dict(state.get("response_payload") or {})
    citation_count = len(citations)
    hit_count = int(metrics.get("hit_count") or 0)
    top_k = max(int(metrics.get("top_k") or 0), 0)
    hit_rate = min(1.0, hit_count / top_k) if hit_count and top_k else 0.0
    coverage = 0.0
    if hit_count > 0:
        coverage = min(1.0, citation_count / hit_count)
    top_sources: list[str] = []
    for item in [*retrieved_chunks, *citations]:
        source = str(item.get("source") or "").strip()
        if source and source not in top_sources:
            top_sources.append(source)
    expectation_check = response_payload.get("expectation_check")
    expectation_matched = None
    if isinstance(expectation_check, dict):
        expectation_matched = expectation_check.get("matched")
    verdict = response_payload.get("verdict")
    if verdict is None:
        result_card = response_payload.get("result_card")
        if isinstance(result_card, dict):
            verdict = result_card.get("verdict")
    normalized_verdict = str(verdict).strip() if verdict is not None else ""
    evidence_found = bool(hit_count > 0 or retrieved_chunks or top_sources)
    evidence_used = bool(citations)
    verdict_impacted = bool(normalized_verdict and response_payload.get("rule_hits"))
    await rag_repo.create_log(
        {
            "session_id": str(state["session_id"]),
            "user_id": str(state["user_id"]),
            "query": str(metrics.get("query") or state.get("query") or ""),
            "rag_space_id": metrics.get("rag_space_id"),
            "top_k": top_k,
            "hit_count": hit_count,
            "hit_rate": round(hit_rate, 4),
            "citation_coverage": round(coverage, 4),
            "latency_ms": int(metrics.get("latency_ms") or 0),
            "source_graph": "chat",
            "agent_name": "chat",
            "sub_route": str(state.get("sub_route") or state.get("intent") or "general_chat"),
            "trace_id": str((state.get("trace") or {}).get("trace_id") or state.get("workflow_run_id") or ""),
            "top_score": float(metrics.get("top_score") or 0.0),
            "metadata_json": {
                "intent": state.get("intent"),
                "empty_recall": bool(metrics.get("empty_recall")),
                "top_score": float(metrics.get("top_score") or 0.0),
                "top_sources": top_sources[:5],
                "rule_hits": [str(item) for item in list(response_payload.get("rule_hits") or []) if str(item).strip()],
                "verdict": normalized_verdict or None,
                "product_family": str((state.get("metadata") or {}).get("product_family") or "").strip() or None,
                "expectation_matched": expectation_matched,
                "evidence_found": evidence_found,
                "evidence_used": evidence_used,
                "verdict_impacted": verdict_impacted,
                "candidate_count": int(metrics.get("candidate_count") or hit_count),
                "rejected_count": int(metrics.get("rejected_count") or 0),
                "score_threshold": metrics.get("score_threshold"),
                "retrieval_config": {
                    "rag_space_id": metrics.get("rag_space_id"),
                    "rag_space_name": str((((state.get("ext") or {}).get("selected_rag_space") or {}).get("name") or "")).strip() or None,
                    "top_k": top_k,
                    "score_threshold": metrics.get("score_threshold"),
                    "scope_node_ids": _selected_rag_scope_node_ids(state.get("ext") or {}),
                },
                "retrieved_chunks": retrieved_chunks,
                "used_citations": citations,
                "answer": str(response_payload.get("answer") or "").strip() or None,
                "result": response_payload.get("result") or response_payload.get("result_card"),
            },
        }
    )


async def response_writer(state: ChatState) -> ChatState:
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
        "workflow_version": state.get("workflow_version") or "quality_chat_v2",
        "prompt_version": state.get("prompt_version") or "chat_general_v1",
        "retrieval_metrics": state.get("retrieval_metrics") or {},
        "summary": (state.get("reasoning") or {}).get("summary"),
        "intent": state.get("intent"),
        "intent_confidence": state.get("intent_confidence"),
        "action_state": action_state,
        "task_draft": task_draft or None,
        "task_form_defaults": task_draft or None,
        "task_submit_mode": "direct_create" if action_state in {"awaiting_clarification", "awaiting_task_details", "awaiting_task_confirmation"} else None,
        "missing_slots": list(state.get("missing_slots") or []),
        "pending_action": state.get("pending_action"),
        "awaiting_confirmation": bool(state.get("awaiting_confirmation") or False),
        "created_task": dict(state.get("created_task") or {}) or None,
        "selected_rag_space": selected_rag,
        "attachment_echo": attachments,
        "runtime_profile": _runtime_profile_meta(state),
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


def _build_trust_scoring_request(state: ChatState, payload: dict[str, Any]) -> dict[str, Any] | None:
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


async def _enqueue_trust_scoring(payload: dict[str, Any] | None) -> str | None:
    return await enqueue_chat_trust_scoring(payload, logger=logger)


async def finalizer(state: ChatState) -> ChatState:
    _t0 = perf_counter()
    payload = state.get("response_payload") or {}
    trust_score: dict[str, Any] | None = None
    trust_request = state.get("trust_scoring_payload")
    if trust_request:
        trust_score = build_pending_trust_score(**trust_request)
        payload = {**payload, "trust_scoring": trust_payload_from_score(trust_score)}
        await _enqueue_trust_scoring(trust_request)
    state["response_payload"] = payload
    logger.info(
        "finalizer intent=%s trust_status=%s db_ms=%d total_ms=%d",
        state.get("intent"), (trust_score or {}).get("status", "none"), 0, round((perf_counter() - _t0) * 1000),
    )
    return state


class ChatGraph:
    def __init__(self) -> None:
        graph = StateGraph(ChatState)
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

    async def run(self, state, route_decision=None):
        if isinstance(state, dict):
            return await self._run_state(state)
        from agent.contracts.quality_contracts import NormalizedRequest, AgentOutput
        if isinstance(state, NormalizedRequest):
            agent = getattr(route_decision, "selected_agent", "chat") if route_decision else "chat"
            sub_route = getattr(route_decision, "sub_route", "general_chat") if route_decision else "general_chat"
            state_dict = {
                "schema_version": "1.0.0",
                "request_id": state.request_id,
                "workflow_run_id": state.workflow_run_id or state.request_id,
                "session_id": state.session_id or state.request_id,
                "assistant_message_id": state.assistant_message_id or "",
                "org_id": state.org_id,
                "user_id": state.user_id or "",
                "plan_tier": state.plan_tier,
                "capabilities": list(state.capabilities),
                "workspace": state.workspace,
                "query": state.query,
                "metadata": dict(state.metadata),
                "ext": dict(state.ext),
                "emit": state.ext.get("emit"),
                "agent": agent,
                "sub_route": sub_route,
            }
            graph_result = await self._run_state(state_dict)
            payload = dict(graph_result.get("response_payload") or {})
            return AgentOutput(
                message_type=str(payload.get("message_type") or "assistant_text"),
                answer=str(payload.get("answer") or ""),
                summary=str(payload.get("summary") or ""),
                citations=list(payload.get("citations") or []),
                quality=dict(payload.get("quality") or {}),
                action_state=str(payload.get("action_state") or "") or None,
                task_draft=dict(payload.get("task_draft") or {}) or None,
                created_task=dict(payload.get("created_task") or {}) or None,
                raw_state=graph_result,
            )
        raise TypeError(f"ChatGraph.run() expects dict or NormalizedRequest, got {type(state)}")

    async def _run_state(self, state: ChatState) -> ChatState:
        _t_graph = perf_counter()
        tracer = LangfuseTracer()
        state["trace"] = tracer.start_trace(
            trace_id=state.get("trace", {}).get("trace_id"),
            task_id=state["session_id"],
            agent=state.get("agent", "chat"),
            sub_route=state.get("sub_route", "general_chat"),
            intent=state.get("intent"),
            prompt_version=state.get("prompt_version"),
            workflow_version="quality_chat_v2",
            workflow_run_id=state.get("workflow_run_id"),
            request_id=state.get("request_id"),
            assistant_message_id=state.get("assistant_message_id"),
            route_source=state.get("route_source", ""),
            route_confidence=state.get("route_confidence", 0.0),
            session_id=state.get("session_id"),
            source_type="chat",
            org_id=state.get("org_id"),
            model_key=state.get("model_key"),
            name="quality_chat_v2",
            input={"query": state.get("query", ""), "session_id": state.get("session_id", "")},
        )
        result = await self._graph.ainvoke(state)
        logger.info(
            "graph_total intent=%s query_len=%d total_ms=%d",
            result.get("intent"), len(str(result.get("query") or "")), round((perf_counter() - _t_graph) * 1000),
        )
        return result
