from __future__ import annotations

from typing import Any, TypedDict


class LabDetectionState(TypedDict, total=False):
    schema_version: str
    workflow_version: str

    request_id: str
    workflow_run_id: str
    session_id: str
    org_id: str
    user_id: str

    input_context: dict[str, Any]
    normalized_context: dict[str, Any]

    validation_errors: list[str]
    blocked_reason: str

    standard_limits: list[dict[str, Any]]
    normal_profile: dict[str, Any]

    anomaly_features: list[dict[str, Any]]
    deterministic_summary: dict[str, Any]

    llm_prompt: dict[str, Any]
    llm_result: dict[str, Any]
    llm_error: str

    next_test_priority: list[dict[str, Any]]
    assessment: dict[str, Any]

    metadata: dict[str, Any]
