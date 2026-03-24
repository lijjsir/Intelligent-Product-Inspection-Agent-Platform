from __future__ import annotations

from datetime import datetime

from app.core.ids import uuid7


class LangfuseTracer:
    def start_trace(self, **kwargs):
        return {
            "trace_id": str(kwargs.get("trace_id") or uuid7()),
            "task_id": kwargs.get("task_id"),
            "org_id": kwargs.get("org_id"),
            "model_key": kwargs.get("model_key"),
            "name": kwargs.get("name") or "inspection_pipeline",
            "started_at": kwargs.get("started_at") or datetime.utcnow().isoformat(),
        }

    def score(self, **kwargs):
        return {
            "ok": True,
            "trace_id": kwargs.get("trace_id"),
            "name": kwargs.get("name") or "user_feedback",
            "value": float(kwargs.get("value") or 0.0),
            "comment": kwargs.get("comment"),
            "metadata": kwargs.get("metadata") or {},
            "scored_at": kwargs.get("scored_at") or datetime.utcnow().isoformat(),
        }
