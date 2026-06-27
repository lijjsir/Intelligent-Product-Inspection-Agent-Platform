from __future__ import annotations

from typing import Any


REGISTERED_SUBGRAPHS: list[dict[str, Any]] = [
    {
        "name": "Orchestrator",
        "description": "统一入口、计划、调度和任务级黑板管理。",
        "workflow_binding": "orchestrator_v1",
        "subgraph_key": "orchestrator",
        "entry_graph": "OrchestratorLoop",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group_key": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "type": "orchestrator",
        "customer_visible_description": "统一编排入口，负责计划、能力调用和业务 Agent 调度。",
    },
    {
        "name": "Evidence Capability",
        "description": "RAG、共享记忆和质量知识图谱证据检索与冲突裁决。",
        "workflow_binding": "evidence_capability_v1",
        "subgraph_key": "evidence_arbitration",
        "entry_graph": "EvidenceArbitrationService",
        "supports_start_stop": False,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group_key": "capability",
        "route_enabled": False,
        "supports_route_toggle": False,
        "type": "capability",
        "customer_visible_description": "由编排器调用的证据检索与裁决能力。",
    },
    {
        "name": "Vision Inspection Agent",
        "description": "多模态视觉检验、缺陷定位和结构化视觉输出。",
        "workflow_binding": "vision_inspection_v1",
        "subgraph_key": "vision_inspection",
        "entry_graph": "VisionInspectionGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group_key": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "type": "agent",
        "customer_visible_description": "负责图片理解、缺陷线索识别和视觉风险说明。",
    },
    {
        "name": "Lab Detection Agent",
        "description": "实验室、设备和环境数据的多步骤风险研判。",
        "workflow_binding": "lab_detection_v1",
        "subgraph_key": "lab_detection",
        "entry_graph": "LabDetectionGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group_key": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "type": "agent",
        "customer_visible_description": "负责实验室和设备环境数据的早期风险研判。",
    },
    {
        "name": "Quality Analysis Agent",
        "description": "证据聚合、质量问答和正式质检终判。",
        "workflow_binding": "quality_analysis_v1",
        "subgraph_key": "quality_analysis",
        "entry_graph": "QualityAnalysisGraph",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group_key": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "type": "agent",
        "customer_visible_description": "负责整合证据并生成最终回答或正式质检结果。",
    },
    {
        "name": "File Agent",
        "description": "文件总结、问答、RAG 入库请求和论文格式检查。",
        "workflow_binding": "file_agent_v1",
        "subgraph_key": "file",
        "entry_graph": "FileExecutor",
        "supports_start_stop": True,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group_key": "core",
        "route_enabled": True,
        "supports_route_toggle": True,
        "type": "agent",
        "customer_visible_description": "负责文件解析、总结、问答和论文格式检查。",
    },
    {
        "name": "Memory Capability",
        "description": "候选记忆、污染传播分析、回滚与恢复评估。",
        "workflow_binding": "memory_capability_v1",
        "subgraph_key": "memory_governance",
        "entry_graph": "MemoryCapabilityService",
        "supports_start_stop": False,
        "graph_version": "v1",
        "is_active": True,
        "lifecycle_status": "active",
        "group_key": "capability",
        "route_enabled": False,
        "supports_route_toggle": False,
        "type": "capability",
        "customer_visible_description": "由后台管理流程调用的共享记忆治理能力。",
    },
]


ROOT_NODES: list[dict[str, Any]] = [
    {"id": "request_intake", "label": "Request Intake", "kind": "orchestrator"},
    {"id": "global_plan", "label": "Global Plan", "kind": "orchestrator"},
    {"id": "task_blackboard", "label": "Task Blackboard", "kind": "orchestrator"},
    {"id": "capability_dispatch", "label": "Capability Dispatch", "kind": "orchestrator"},
    {"id": "agent_dispatch", "label": "Business Agent Dispatch", "kind": "orchestrator"},
    {"id": "result_synthesizer", "label": "Result Synthesizer", "kind": "orchestrator"},
]
ROOT_EDGES: list[dict[str, Any]] = [
    {"source": "request_intake", "target": "global_plan"},
    {"source": "global_plan", "target": "task_blackboard"},
    {"source": "task_blackboard", "target": "capability_dispatch"},
    {"source": "task_blackboard", "target": "agent_dispatch"},
    {"source": "capability_dispatch", "target": "result_synthesizer"},
    {"source": "agent_dispatch", "target": "result_synthesizer"},
]


def _component_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item["subgraph_key"]),
        "label": str(item["name"]),
        "kind": str(item.get("type") or "component"),
    }


def get_topology(
    subgraph_key: str = "all",
    *,
    include_root: bool = True,
) -> dict[str, Any]:
    nodes = [dict(item) for item in ROOT_NODES] if include_root else []
    edges = [dict(item) for item in ROOT_EDGES] if include_root else []
    selected = REGISTERED_SUBGRAPHS
    if subgraph_key not in {"all", "*"}:
        selected = [
            item
            for item in REGISTERED_SUBGRAPHS
            if item["subgraph_key"] == subgraph_key
        ]
    for item in selected:
        node = _component_node(item)
        nodes.append(node)
        if include_root and node["id"] != "orchestrator":
            source = (
                "capability_dispatch"
                if node["kind"] == "capability"
                else "agent_dispatch"
            )
            edges.append({"source": source, "target": node["id"]})
    deduped_nodes = {node["id"]: node for node in nodes}
    deduped_edges = {
        (edge["source"], edge["target"]): edge
        for edge in edges
    }
    return {
        "nodes": list(deduped_nodes.values()),
        "edges": list(deduped_edges.values()),
    }


def get_route_topology(
    *,
    intent_name: str,
    agent_name: str | None,
    subgraph_key: str,
) -> dict[str, Any]:
    return {
        **get_topology(subgraph_key, include_root=True),
        "intent_name": intent_name,
        "agent_name": agent_name,
        "selected_subgraph": subgraph_key,
    }


def get_registered_subgraphs() -> list[dict[str, Any]]:
    return [dict(item) for item in REGISTERED_SUBGRAPHS]


def get_agent_overview_root() -> dict[str, Any]:
    return {
        "nodes": [dict(item) for item in ROOT_NODES],
        "edges": [dict(item) for item in ROOT_EDGES],
    }
