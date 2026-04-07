from __future__ import annotations

import re
from typing import cast

from langgraph.graph import END, StateGraph

from agent.contracts import AgentOutput, NormalizedAttachment, NormalizedRequest, PersistableOutput, RouteSignals
from agent.graphs.quality_root.policy import select_subgraph
from agent.graphs.quality_root.state import QualityRootState
from agent.subgraphs.legacy_quality import LegacyQualitySubgraph
from agent.subgraphs.llm_native_quality import LLMNativeQualitySubgraph

TASK_KEYWORD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"创建任务",
        r"新建任务",
        r"发起检测",
        r"提交任务",
        r"检测任务",
        r"任务",
        r"task",
    ]
]


async def request_intake(state: QualityRootState) -> QualityRootState:
    request = NormalizedRequest.model_validate(state["request"])
    attachments = []
    for item in list((request.ext or {}).get("attachments") or []):
        if isinstance(item, dict):
            attachments.append(NormalizedAttachment.model_validate(item))
    request.attachments = attachments
    if not request.image_urls:
        request.image_urls = [
            str(item.url)
            for item in request.attachments
            if item.kind == "image" and item.url
        ]
    state["request"] = cast(NormalizedRequest, request)
    return state


async def route_signal_builder(state: QualityRootState) -> QualityRootState:
    request = NormalizedRequest.model_validate(state["request"])
    attachment_types = []
    has_non_pdf_documents = False
    has_images = False
    has_file_attachments = False
    for item in request.attachments:
        name = str(item.name or "").lower()
        if item.kind == "image":
            has_images = True
            attachment_types.append("image")
            continue
        has_file_attachments = True
        suffix = ""
        if "." in name:
            suffix = name.rsplit(".", 1)[-1]
        if suffix:
            attachment_types.append(suffix)
        if suffix and suffix not in {"pdf", "png", "jpg", "jpeg", "webp", "gif"}:
            has_non_pdf_documents = True
    query_text = str(request.query or "")
    has_task_keyword = any(pattern.search(query_text) for pattern in TASK_KEYWORD_PATTERNS)
    state["route_signals"] = RouteSignals(
        attachment_types=attachment_types,
        has_non_pdf_documents=has_non_pdf_documents,
        has_images=has_images,
        has_task_keyword=has_task_keyword,
        has_file_attachments=has_file_attachments,
        needs_external_knowledge=bool(request.ext.get("selected_rag_space_id") or request.ext.get("selected_rag_space")),
        request_kind=request.request_kind,
        selected_rag_space_id=str(request.ext.get("selected_rag_space_id") or "") or None,
    )
    return state


async def route_policy(state: QualityRootState) -> QualityRootState:
    state["route_decision"] = select_subgraph(RouteSignals.model_validate(state["route_signals"]))
    return state


async def subgraph_runner(state: QualityRootState) -> QualityRootState:
    request = NormalizedRequest.model_validate(state["request"])
    decision = state["route_decision"]
    if decision.selected_subgraph == "llm_native_quality":
        output = await LLMNativeQualitySubgraph().run(request)
    else:
        output = await LegacyQualitySubgraph().run(request)
    output.route_decision = decision
    state["agent_output"] = output
    state["raw_subgraph_state"] = dict(output.raw_state or {})
    return state


async def contract_finalize(state: QualityRootState) -> QualityRootState:
    output = AgentOutput.model_validate(state["agent_output"])
    state["persistable_output"] = PersistableOutput.model_validate(output.persistable_output)
    return state


class QualityAgentRootGraph:
    def __init__(self) -> None:
        graph = StateGraph(QualityRootState)
        for name, node in [
            ("request_intake", request_intake),
            ("route_signal_builder", route_signal_builder),
            ("route_policy", route_policy),
            ("subgraph_runner", subgraph_runner),
            ("contract_finalize", contract_finalize),
        ]:
            graph.add_node(name, node)
        graph.set_entry_point("request_intake")
        graph.add_edge("request_intake", "route_signal_builder")
        graph.add_edge("route_signal_builder", "route_policy")
        graph.add_edge("route_policy", "subgraph_runner")
        graph.add_edge("subgraph_runner", "contract_finalize")
        graph.add_edge("contract_finalize", END)
        self._graph = graph.compile()

    async def run(self, request: NormalizedRequest) -> QualityRootState:
        return await self._graph.ainvoke({"request": request})
