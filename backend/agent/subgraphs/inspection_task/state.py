from __future__ import annotations

from typing import Any, TypedDict


class InspectionState(TypedDict, total=False):
    """在计划、视觉、RAG、推理和持久化阶段之间共享的可变状态。"""
    task_id: str
    org_id: str
    product_id: str
    spec_code: str
    product_family: str | None
    image_urls: list[str]
    image_items: list[dict[str, Any]]
    selected_rag_space_id: str | None
    selected_rag_space_name: str | None
    selected_rag_space: dict[str, Any] | None
    selected_rag_scope_node_ids: list[str]
    structured_record: dict[str, Any]
    model_id: str
    model_config_id: str | None
    model_base_url: str | None
    model_api_key: str | None
    model_provider: str | None
    model_input_price_per_million: float | None
    model_output_price_per_million: float | None
    trace_id: str

    plan: dict[str, Any]
    defects: list[dict[str, Any]]
    knowledge_docs: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    rag_summary: dict[str, Any]
    reasoning_chain: dict[str, Any]
    conclusion: dict[str, Any]
    standard_evaluation: dict[str, Any]
    dimensions: dict[str, float]
    stability: dict[str, Any]
    alert_needed: bool

    timeline: list[dict[str, Any]]
    usage_events: list[dict[str, Any]]
    runtime_errors: list[dict[str, Any]]
