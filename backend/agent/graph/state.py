from __future__ import annotations

from typing import Any, TypedDict


class InspectionState(TypedDict, total=False):
    task_id: str
    org_id: str
    product_id: str
    spec_id: str
    image_urls: list[str]
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
    reasoning_chain: dict[str, Any]
    conclusion: dict[str, Any]
    dimensions: dict[str, float]
    stability: dict[str, Any]
    alert_needed: bool

    timeline: list[dict[str, Any]]
    usage_events: list[dict[str, Any]]
    runtime_errors: list[dict[str, Any]]
