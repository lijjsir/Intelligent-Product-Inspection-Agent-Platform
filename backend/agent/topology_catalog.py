from __future__ import annotations

from typing import Any

REGISTERED_SUBGRAPHS = [
    {
        "name": "Legacy Quality",
        "description": "Legacy quality chat and task creation workflow.",
        "workflow_binding": "quality_chat_v1",
        "subgraph_key": "legacy_quality",
        "entry_graph": "QualityAgentRootGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
    },
    {
        "name": "LLM-native Quality",
        "description": "LLM-native file and text driven quality workflow.",
        "workflow_binding": "llm_native_quality_v1",
        "subgraph_key": "llm_native_quality",
        "entry_graph": "QualityAgentRootGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
    },
]


DSPY_OPTIMIZATION_TARGETS = [
    {
        "target_key": "legacy_quality.planner",
        "subgraph_key": "legacy_quality",
        "node_id": "planner",
        "node_ref": "legacy_quality.planner",
        "node_label": "Planner",
        "module_name": "LegacyQualityPlanner",
        "optimization_goal": "Improve task planning clarity and reduce ambiguous branching in legacy quality conversations.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "legacy_quality.task_extractor",
        "subgraph_key": "legacy_quality",
        "node_id": "task_extractor",
        "node_ref": "legacy_quality.task_extractor",
        "node_label": "Task Extractor",
        "module_name": "LegacyTaskExtractor",
        "optimization_goal": "Improve structured task extraction accuracy from mixed user messages and uploaded context.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "legacy_quality.knowledge",
        "subgraph_key": "legacy_quality",
        "node_id": "knowledge",
        "node_ref": "legacy_quality.knowledge",
        "node_label": "Knowledge",
        "module_name": "LegacyKnowledgeRouter",
        "optimization_goal": "Improve retrieval and grounding decisions before the legacy reasoning phase.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination"],
        "supports_compile": True,
    },
    {
        "target_key": "legacy_quality.reasoning",
        "subgraph_key": "legacy_quality",
        "node_id": "reasoning",
        "node_ref": "legacy_quality.reasoning",
        "node_label": "Reasoning",
        "module_name": "LegacyReasoningCore",
        "optimization_goal": "Reduce hallucination in legacy reasoning while preserving answer completeness and consistency.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "legacy_quality.response_writer",
        "subgraph_key": "legacy_quality",
        "node_id": "response_writer",
        "node_ref": "legacy_quality.response_writer",
        "node_label": "Response Writer",
        "module_name": "LegacyResponseWriter",
        "optimization_goal": "Improve response formatting, task form defaults, and admin-facing data completeness in legacy output.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "llm_native_quality.contract_inferencer_dspy",
        "subgraph_key": "llm_native_quality",
        "node_id": "contract_inferencer_dspy",
        "node_ref": "llm_native_quality.contract_inferencer_dspy",
        "node_label": "Contract Inferencer",
        "module_name": "QualityContractInferencer",
        "optimization_goal": "Improve contract inference for text and file-driven inspection requests before downstream planning.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "llm_native_quality.planner",
        "subgraph_key": "llm_native_quality",
        "node_id": "planner",
        "node_ref": "llm_native_quality.planner",
        "node_label": "Planner",
        "module_name": "NativeQualityPlanner",
        "optimization_goal": "Optimize inspection task planning and tool orchestration for LLM-native quality flows.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "llm_native_quality.knowledge_router",
        "subgraph_key": "llm_native_quality",
        "node_id": "knowledge_router",
        "node_ref": "llm_native_quality.knowledge_router",
        "node_label": "Knowledge Router",
        "module_name": "NativeKnowledgeRouter",
        "optimization_goal": "Improve decisions about when to use RAG, specs, and API contract evidence in native flows.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination"],
        "supports_compile": True,
    },
    {
        "target_key": "llm_native_quality.evidence_synthesizer",
        "subgraph_key": "llm_native_quality",
        "node_id": "evidence_synthesizer",
        "node_ref": "llm_native_quality.evidence_synthesizer",
        "node_label": "Evidence Synthesizer",
        "module_name": "EvidenceSynthesizer",
        "optimization_goal": "Improve evidence assembly quality, citation coverage, and defect reasoning traceability.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "llm_native_quality.review_gate",
        "subgraph_key": "llm_native_quality",
        "node_id": "review_gate",
        "node_ref": "llm_native_quality.review_gate",
        "node_label": "Review Gate",
        "module_name": "NativeReviewGate",
        "optimization_goal": "Improve PASS/FAIL/UNCERTAIN gating decisions and reduce unsafe auto-pass behavior.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination", "pass_rate"],
        "supports_compile": True,
    },
]


ROOT_NODES = [
    {"id": "request_intake", "label": "Request Intake", "kind": "root"},
    {"id": "route_signal_builder", "label": "Route Signals", "kind": "root"},
    {"id": "route_policy", "label": "Route Policy", "kind": "root"},
    {"id": "subgraph_runner", "label": "Subgraph Runner", "kind": "root"},
    {"id": "contract_finalize", "label": "Contract Finalize", "kind": "root"},
]
ROOT_EDGES = [
    {"source": "request_intake", "target": "route_signal_builder"},
    {"source": "route_signal_builder", "target": "route_policy"},
    {"source": "route_policy", "target": "subgraph_runner"},
    {"source": "subgraph_runner", "target": "contract_finalize"},
]

LEGACY_NODES = [
    {"id": "legacy_quality", "label": "Legacy Quality Subgraph", "kind": "subgraph"},
    {"id": "legacy_quality.input_adapter", "label": "Input Adapter", "kind": "legacy"},
    {"id": "legacy_quality.history_loader", "label": "History Loader", "kind": "legacy"},
    {"id": "legacy_quality.planner", "label": "Planner", "kind": "legacy"},
    {"id": "legacy_quality.task_extractor", "label": "Task Extractor", "kind": "legacy"},
    {"id": "legacy_quality.knowledge", "label": "Knowledge", "kind": "legacy"},
    {"id": "legacy_quality.reasoning", "label": "Reasoning", "kind": "legacy"},
    {"id": "legacy_quality.quality_gate", "label": "Quality Gate", "kind": "legacy"},
    {"id": "legacy_quality.task_executor", "label": "Task Executor", "kind": "legacy"},
    {"id": "legacy_quality.response_writer", "label": "Response Writer", "kind": "legacy"},
    {"id": "legacy_quality.finalizer", "label": "Finalizer", "kind": "legacy"},
]
LEGACY_EDGES = [
    {"source": "legacy_quality", "target": "legacy_quality.input_adapter"},
    {"source": "legacy_quality.input_adapter", "target": "legacy_quality.history_loader"},
    {"source": "legacy_quality.history_loader", "target": "legacy_quality.planner"},
    {"source": "legacy_quality.planner", "target": "legacy_quality.task_extractor"},
    {"source": "legacy_quality.task_extractor", "target": "legacy_quality.knowledge"},
    {"source": "legacy_quality.knowledge", "target": "legacy_quality.reasoning"},
    {"source": "legacy_quality.reasoning", "target": "legacy_quality.quality_gate"},
    {"source": "legacy_quality.quality_gate", "target": "legacy_quality.task_executor"},
    {"source": "legacy_quality.task_executor", "target": "legacy_quality.response_writer"},
    {"source": "legacy_quality.response_writer", "target": "legacy_quality.finalizer"},
]

LLM_NATIVE_NODES = [
    {"id": "llm_native_quality", "label": "LLM-native Quality Subgraph", "kind": "subgraph"},
    {"id": "llm_native_quality.intake_normalizer", "label": "Intake Normalizer", "kind": "native"},
    {"id": "llm_native_quality.file_loader", "label": "File Loader", "kind": "native"},
    {"id": "llm_native_quality.contract_inferencer_dspy", "label": "Contract Inferencer", "kind": "native"},
    {"id": "llm_native_quality.planner", "label": "Planner", "kind": "native"},
    {"id": "llm_native_quality.knowledge_router", "label": "Knowledge Router", "kind": "native"},
    {"id": "llm_native_quality.tool_loop", "label": "Tool Loop", "kind": "native"},
    {"id": "llm_native_quality.evidence_synthesizer", "label": "Evidence Synthesizer", "kind": "native"},
    {"id": "llm_native_quality.contract_mapper", "label": "Contract Mapper", "kind": "native"},
    {"id": "llm_native_quality.review_gate", "label": "Review Gate", "kind": "native"},
    {"id": "llm_native_quality.persist_emit", "label": "Persist Emit", "kind": "native"},
]
LLM_NATIVE_EDGES = [
    {"source": "llm_native_quality", "target": "llm_native_quality.intake_normalizer"},
    {"source": "llm_native_quality.intake_normalizer", "target": "llm_native_quality.file_loader"},
    {"source": "llm_native_quality.file_loader", "target": "llm_native_quality.contract_inferencer_dspy"},
    {"source": "llm_native_quality.contract_inferencer_dspy", "target": "llm_native_quality.planner"},
    {"source": "llm_native_quality.planner", "target": "llm_native_quality.knowledge_router"},
    {"source": "llm_native_quality.knowledge_router", "target": "llm_native_quality.tool_loop"},
    {"source": "llm_native_quality.tool_loop", "target": "llm_native_quality.evidence_synthesizer"},
    {"source": "llm_native_quality.evidence_synthesizer", "target": "llm_native_quality.contract_mapper"},
    {"source": "llm_native_quality.contract_mapper", "target": "llm_native_quality.review_gate"},
    {"source": "llm_native_quality.review_gate", "target": "llm_native_quality.persist_emit"},
]


def get_topology(subgraph_key: str = "legacy_quality", *, include_root: bool = True) -> dict[str, Any]:
    nodes = []
    edges = []
    if include_root:
        nodes.extend(ROOT_NODES)
        edges.extend(ROOT_EDGES)
    selected_keys = [subgraph_key]
    if subgraph_key in {"all", "*"}:
        selected_keys = [item["subgraph_key"] for item in REGISTERED_SUBGRAPHS]
    for key in selected_keys:
        if key == "llm_native_quality":
            nodes.extend(LLM_NATIVE_NODES)
            edges.extend(LLM_NATIVE_EDGES)
        else:
            nodes.extend(LEGACY_NODES)
            edges.extend(LEGACY_EDGES)
        if include_root:
            edges.append({"source": "subgraph_runner", "target": key})
    if include_root and subgraph_key in {"all", "*"}:
        deduped_nodes = {node["id"]: node for node in nodes}
        deduped_edges = {(edge["source"], edge["target"]): edge for edge in edges}
        return {"nodes": list(deduped_nodes.values()), "edges": list(deduped_edges.values())}
    return {"nodes": nodes, "edges": edges}


def get_route_topology(*, intent_name: str, agent_name: str | None, subgraph_key: str) -> dict[str, Any]:
    topology = get_topology(subgraph_key, include_root=True)
    return {
        **topology,
        "intent_name": intent_name,
        "agent_name": agent_name,
        "selected_subgraph": subgraph_key,
    }


def get_registered_subgraphs() -> list[dict[str, Any]]:
    return [dict(item) for item in REGISTERED_SUBGRAPHS]


def get_dspy_optimization_targets() -> list[dict[str, Any]]:
    return [dict(item) for item in DSPY_OPTIMIZATION_TARGETS]


def get_dspy_optimization_target(target_key: str) -> dict[str, Any] | None:
    return next((dict(item) for item in DSPY_OPTIMIZATION_TARGETS if item["target_key"] == target_key), None)


def get_dspy_graph_context(target_key: str) -> dict[str, Any] | None:
    target = get_dspy_optimization_target(target_key)
    if not target:
        return None
    topology = get_topology(target["subgraph_key"], include_root=True)
    focus_node = target["node_ref"]
    upstream = [
        edge["source"]
        for edge in topology["edges"]
        if edge["target"] == focus_node
    ]
    downstream = [
        edge["target"]
        for edge in topology["edges"]
        if edge["source"] == focus_node
    ]
    return {
        "focus_node_id": focus_node,
        "focus_node_label": target["node_label"],
        "upstream_nodes": upstream,
        "downstream_nodes": downstream,
        "nodes": topology["nodes"],
        "edges": topology["edges"],
    }
