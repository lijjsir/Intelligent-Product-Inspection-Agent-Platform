from datetime import datetime
from types import SimpleNamespace

from app.api.v1.agent import _task_event_payload


def test_task_event_payload_exposes_persisted_event_identity_and_status():
    event = SimpleNamespace(
        id="019e-event",
        event_type="status",
        stage="reasoning",
        status="running",
        message="reasoning started",
        payload_json={"type": "status", "extra": "kept"},
        created_at=datetime(2026, 5, 24, 6, 41, 35, 126000),
    )

    payload = _task_event_payload(event)

    assert payload == {
        "id": "019e-event",
        "type": "status",
        "extra": "kept",
        "stage": "reasoning",
        "status": "running",
        "message": "reasoning started",
        "ts": "2026-05-24T06:41:35.126000",
    }
