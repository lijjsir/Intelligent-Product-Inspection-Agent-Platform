from __future__ import annotations

from typing import Any, TypedDict


class QualityAnalysisState(TypedDict, total=False):
    org_id: str
    user_id: str | None
    session_id: str | None
    workflow_run_id: str
    surface: str
    query: str
    capability: str
    request: dict[str, Any]
    manager_state: dict[str, Any]
    db_session: Any

    artifacts: list[dict[str, Any]]
    evidence_packet: dict[str, Any] | None
    visual_inspection_result: dict[str, Any] | None
    lab_detection_result: dict[str, Any] | None
    file_results: list[dict[str, Any]]
    consumed_artifact_ids: list[str]

    needs_user_input: bool
    response_mode: str
    llm_prompt: str
    llm_answer: str
    reasoning_chain: dict[str, Any]
    standard_evaluation: dict[str, Any]
    report: str

    final_assessment: dict[str, Any]
    persistable_output: dict[str, Any] | None
    answer: str
    message_type: str
    citations: list[dict[str, Any]]
    status: str
    summary: str
    confidence: float
    candidate_extractable: bool
    metadata: dict[str, Any]
