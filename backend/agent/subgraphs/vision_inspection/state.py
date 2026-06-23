from __future__ import annotations

from typing import Any, TypedDict


class VisionInspectionState(TypedDict, total=False):
    request_id: str
    workflow_run_id: str
    query: str
    attachments: list[dict[str, Any]]
    request: dict[str, Any]
    manager_state: dict[str, Any]
    step: dict[str, Any]
    image_attachments: list[dict[str, Any]]
    legacy_result: dict[str, Any]
    visual_inspection_result: dict[str, Any]
    status: str
    error: dict[str, Any]
