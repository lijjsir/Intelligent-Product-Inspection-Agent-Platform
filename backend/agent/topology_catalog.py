from __future__ import annotations

from typing import Any

REGISTERED_SUBGRAPHS: list[dict[str, Any]] = [
    {
        "name": "Quality Judgement",
        "description": "统一质量判定（合并 Legacy + LLM-native），支持 chat / file / task 多策略。",
        "workflow_binding": "quality_judgement_v2",
        "subgraph_key": "quality_judgement",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": True,
        "graph_version": "v2",
        "is_active": True,
    },
    {
        "name": "Quality Chat",
        "description": "轻量级智能问答入口，支持附件上传和 RAG 空间选择。",
        "workflow_binding": "quality_chat_v2",
        "subgraph_key": "chat",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": True,
        "graph_version": "v2",
        "is_active": True,
    },
    {
        "name": "Inspection Task Agent",
        "description": "负责正式质检任务创建、文件/图片检测、结果落库。",
        "workflow_binding": "inspection_task_v1",
        "subgraph_key": "inspection_task",
        "entry_graph": "InspectionTaskGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
    },
    {
        "name": "Agent Manager",
        "description": "统一入口路由，负责将请求分发给聊天或检测 Agent。",
        "workflow_binding": "agent_manager_v1",
        "subgraph_key": "agent_manager",
        "entry_graph": "AgentManagerService",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
    },
    {
        "name": "Market Monitor",
        "description": "市场价格、销量、渠道异常检测（规划中）。",
        "workflow_binding": "market_monitor_v0",
        "subgraph_key": "market_monitor",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Public Opinion",
        "description": "新闻、社交媒体、投诉举报等舆情分析（规划中）。",
        "workflow_binding": "public_opinion_v0",
        "subgraph_key": "public_opinion",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Trend Evolution",
        "description": "风险融合、趋势推演和情景预测（规划中）。",
        "workflow_binding": "trend_evolution_v0",
        "subgraph_key": "trend_evolution",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Supervision Sampling",
        "description": "抽检计划生成、样品管理和现场检查记录（规划中）。",
        "workflow_binding": "supervision_sampling_v0",
        "subgraph_key": "supervision_sampling",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
    {
        "name": "Lab Detection",
        "description": "样品检测、指标解析和标准比对（规划中）。",
        "workflow_binding": "lab_detection_v0",
        "subgraph_key": "lab_detection",
        "entry_graph": "MemoryManagerGraph",
        "supports_start_stop": False,
        "graph_version": "v0",
        "is_active": False,
    },
]


DSPY_OPTIMIZATION_TARGETS: list[dict[str, Any]] = [
    {
        "target_key": "quality_judgement.contract_inferencer",
        "subgraph_key": "quality_judgement",
        "node_id": "contract_inferencer",
        "node_ref": "quality_judgement.contract_inferencer",
        "node_label": "Contract Inferencer",
        "module_name": "QualityContractInferencer",
        "optimization_goal": "Improve contract inference for text and file-driven inspection requests.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.planner",
        "subgraph_key": "quality_judgement",
        "node_id": "planner",
        "node_ref": "quality_judgement.planner",
        "node_label": "Planner",
        "module_name": "QualityJudgementPlanner",
        "optimization_goal": "Optimize inspection task planning for unified quality flows.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.knowledge_router",
        "subgraph_key": "quality_judgement",
        "node_id": "knowledge_router",
        "node_ref": "quality_judgement.knowledge_router",
        "node_label": "Knowledge Router",
        "module_name": "QualityJudgementKnowledgeRouter",
        "optimization_goal": "Improve RAG and spec retrieval decisions.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.evidence_synthesizer",
        "subgraph_key": "quality_judgement",
        "node_id": "evidence_synthesizer",
        "node_ref": "quality_judgement.evidence_synthesizer",
        "node_label": "Evidence Synthesizer",
        "module_name": "EvidenceSynthesizer",
        "optimization_goal": "Improve evidence assembly quality and citation coverage.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination", "pass_rate"],
        "supports_compile": True,
    },
    {
        "target_key": "quality_judgement.review_gate",
        "subgraph_key": "quality_judgement",
        "node_id": "review_gate",
        "node_ref": "quality_judgement.review_gate",
        "node_label": "Review Gate",
        "module_name": "QualityJudgementReviewGate",
        "optimization_goal": "Improve PASS/FAIL/UNCERTAIN gating decisions.",
        "optimizer_strategy": "bootstrap-fewshot",
        "metric_names": ["faithfulness", "traceability", "physical_hallucination", "pass_rate"],
        "supports_compile": True,
    },
]


ROOT_NODES: list[dict[str, Any]] = [
    {"id": "request_intake", "label": "Request Intake", "kind": "root"},
    {"id": "memory_context_loader", "label": "Memory Context Loader", "kind": "root"},
    {"id": "manager_route_policy", "label": "Manager Route Policy", "kind": "root"},
    {"id": "subgraph_runner", "label": "Subgraph Runner", "kind": "root"},
    {"id": "result_synthesizer", "label": "Result Synthesizer", "kind": "root"},
]
ROOT_EDGES: list[dict[str, Any]] = [
    {"source": "request_intake", "target": "memory_context_loader"},
    {"source": "memory_context_loader", "target": "manager_route_policy"},
    {"source": "manager_route_policy", "target": "subgraph_runner"},
    {"source": "subgraph_runner", "target": "result_synthesizer"},
]

QUALITY_JUDGEMENT_NODES: list[dict[str, Any]] = [
    {"id": "quality_judgement", "label": "Quality Judgement Subgraph", "kind": "subgraph"},
    {"id": "quality_judgement.intake_normalizer", "label": "Intake Normalizer", "kind": "quality"},
    {"id": "quality_judgement.file_loader", "label": "File Loader", "kind": "quality"},
    {"id": "quality_judgement.contract_inferencer", "label": "Contract Inferencer", "kind": "quality"},
    {"id": "quality_judgement.planner", "label": "Planner", "kind": "quality"},
    {"id": "quality_judgement.task_extractor", "label": "Task Extractor", "kind": "quality"},
    {"id": "quality_judgement.knowledge_router", "label": "Knowledge Router", "kind": "quality"},
    {"id": "quality_judgement.tool_loop", "label": "Tool Loop", "kind": "quality"},
    {"id": "quality_judgement.reasoning", "label": "Reasoning", "kind": "quality"},
    {"id": "quality_judgement.evidence_synthesizer", "label": "Evidence Synthesizer", "kind": "quality"},
    {"id": "quality_judgement.review_gate", "label": "Review Gate", "kind": "quality"},
    {"id": "quality_judgement.task_executor", "label": "Task Executor", "kind": "quality"},
    {"id": "quality_judgement.persist_emit", "label": "Persist Emit", "kind": "quality"},
]
QUALITY_JUDGEMENT_EDGES: list[dict[str, Any]] = [
    {"source": "quality_judgement", "target": "quality_judgement.intake_normalizer"},
    {"source": "quality_judgement.intake_normalizer", "target": "quality_judgement.file_loader"},
    {"source": "quality_judgement.file_loader", "target": "quality_judgement.contract_inferencer"},
    {"source": "quality_judgement.contract_inferencer", "target": "quality_judgement.planner"},
    {"source": "quality_judgement.planner", "target": "quality_judgement.task_extractor"},
    {"source": "quality_judgement.planner", "target": "quality_judgement.knowledge_router"},
    {"source": "quality_judgement.task_extractor", "target": "quality_judgement.reasoning"},
    {"source": "quality_judgement.knowledge_router", "target": "quality_judgement.tool_loop"},
    {"source": "quality_judgement.knowledge_router", "target": "quality_judgement.reasoning"},
    {"source": "quality_judgement.tool_loop", "target": "quality_judgement.evidence_synthesizer"},
    {"source": "quality_judgement.reasoning", "target": "quality_judgement.review_gate"},
    {"source": "quality_judgement.evidence_synthesizer", "target": "quality_judgement.review_gate"},
    {"source": "quality_judgement.review_gate", "target": "quality_judgement.task_executor"},
    {"source": "quality_judgement.task_executor", "target": "quality_judgement.persist_emit"},
]

MEMORY_MANAGER_NODES: list[dict[str, Any]] = [
    {"id": "memory_manager", "label": "Memory Manager Graph", "kind": "subgraph"},
    {"id": "memory_manager.request_intake", "label": "Request Intake", "kind": "memory"},
    {"id": "memory_manager.memory_context_loader", "label": "Memory Context Loader", "kind": "memory"},
    {"id": "memory_manager.manager_route_policy", "label": "Manager Route Policy", "kind": "memory"},
    {"id": "memory_manager.market_monitor_agent", "label": "Market Monitor Agent", "kind": "memory"},
    {"id": "memory_manager.public_opinion_agent", "label": "Public Opinion Agent", "kind": "memory"},
    {"id": "memory_manager.trend_evolution_agent", "label": "Trend Evolution Agent", "kind": "memory"},
    {"id": "memory_manager.supervision_sampling_agent", "label": "Supervision Sampling Agent", "kind": "memory"},
    {"id": "memory_manager.lab_detection_agent", "label": "Lab Detection Agent", "kind": "memory"},
    {"id": "memory_manager.quality_judgement_agent", "label": "Quality Judgement Agent", "kind": "memory"},
    {"id": "memory_manager.candidate_memory_builder", "label": "Candidate Memory Builder", "kind": "memory"},
    {"id": "memory_manager.write_gate_node", "label": "Write Gate", "kind": "memory"},
    {"id": "memory_manager.contamination_monitor_node", "label": "Contamination Monitor", "kind": "memory"},
    {"id": "memory_manager.provenance_node", "label": "Provenance", "kind": "memory"},
    {"id": "memory_manager.propagation_graph_node", "label": "Propagation Graph", "kind": "memory"},
    {"id": "memory_manager.rollback_planner_node", "label": "Rollback Planner", "kind": "memory"},
    {"id": "memory_manager.governance_recovery_agent", "label": "Governance Recovery Agent", "kind": "memory"},
    {"id": "memory_manager.replay_evaluation_node", "label": "Replay Evaluation", "kind": "memory"},
    {"id": "memory_manager.result_synthesizer", "label": "Result Synthesizer", "kind": "memory"},
]
MEMORY_MANAGER_EDGES: list[dict[str, Any]] = [
    {"source": "memory_manager", "target": "memory_manager.request_intake"},
    {"source": "memory_manager.request_intake", "target": "memory_manager.memory_context_loader"},
    {"source": "memory_manager.memory_context_loader", "target": "memory_manager.manager_route_policy"},
    {"source": "memory_manager.manager_route_policy", "target": "memory_manager.market_monitor_agent"},
    {"source": "memory_manager.manager_route_policy", "target": "memory_manager.public_opinion_agent"},
    {"source": "memory_manager.manager_route_policy", "target": "memory_manager.trend_evolution_agent"},
    {"source": "memory_manager.manager_route_policy", "target": "memory_manager.quality_judgement_agent"},
    {"source": "memory_manager.market_monitor_agent", "target": "memory_manager.candidate_memory_builder"},
    {"source": "memory_manager.public_opinion_agent", "target": "memory_manager.candidate_memory_builder"},
    {"source": "memory_manager.trend_evolution_agent", "target": "memory_manager.candidate_memory_builder"},
    {"source": "memory_manager.quality_judgement_agent", "target": "memory_manager.candidate_memory_builder"},
    {"source": "memory_manager.candidate_memory_builder", "target": "memory_manager.write_gate_node"},
    {"source": "memory_manager.write_gate_node", "target": "memory_manager.contamination_monitor_node"},
    {"source": "memory_manager.contamination_monitor_node", "target": "memory_manager.result_synthesizer"},
    {"source": "memory_manager.contamination_monitor_node", "target": "memory_manager.provenance_node"},
    {"source": "memory_manager.provenance_node", "target": "memory_manager.propagation_graph_node"},
    {"source": "memory_manager.propagation_graph_node", "target": "memory_manager.rollback_planner_node"},
    {"source": "memory_manager.rollback_planner_node", "target": "memory_manager.governance_recovery_agent"},
    {"source": "memory_manager.governance_recovery_agent", "target": "memory_manager.replay_evaluation_node"},
    {"source": "memory_manager.replay_evaluation_node", "target": "memory_manager.result_synthesizer"},
]


def get_topology(subgraph_key: str = "quality_judgement", *, include_root: bool = True) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    if include_root:
        nodes.extend(ROOT_NODES)
        edges.extend(ROOT_EDGES)
    selected_keys = [subgraph_key]
    if subgraph_key in {"all", "*"}:
        selected_keys = [item["subgraph_key"] for item in REGISTERED_SUBGRAPHS]
    for key in selected_keys:
        if key == "quality_judgement":
            nodes.extend(QUALITY_JUDGEMENT_NODES)
            edges.extend(QUALITY_JUDGEMENT_EDGES)
        elif key == "memory_manager":
            nodes.extend(MEMORY_MANAGER_NODES)
            edges.extend(MEMORY_MANAGER_EDGES)
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
