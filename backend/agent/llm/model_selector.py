from __future__ import annotations


class ModelSelector:
    def ordered_candidates(
        self,
        models: list[dict],
        *,
        excluded_runtime_ids: set[str] | None = None,
    ) -> list[dict]:
        excluded_runtime_ids = excluded_runtime_ids or set()
        active = [
            item
            for item in models
            if item.get("is_active")
            and self._supports_inference(item)
            and self.runtime_id(item) not in excluded_runtime_ids
        ]
        return sorted(active, key=self._sort_key)

    def select(
        self,
        models: list[dict],
        *,
        excluded_runtime_ids: set[str] | None = None,
    ) -> dict | None:
        ordered = self.ordered_candidates(models, excluded_runtime_ids=excluded_runtime_ids)
        if not ordered:
            return None
        return ordered[0]

    @classmethod
    def runtime_id(cls, item: dict) -> str:
        if item.get("id"):
            return str(item["id"])
        if item.get("model_key"):
            return f"model::{item['model_key']}"
        return "unknown"

    @classmethod
    def _sort_key(cls, item: dict) -> tuple[int, int, str]:
        return (
            cls._health_rank(item.get("health_status")),
            int(item.get("priority") or 9999),
            str(item.get("display_name") or item.get("model_key") or ""),
        )

    @staticmethod
    def _supports_inference(item: dict) -> bool:
        model_type = str(item.get("model_type") or "chat").lower()
        return model_type in {"chat", "vision", "multimodal", "vlm", "llm"}

    @staticmethod
    def _health_rank(health_status: str | None) -> int:
        mapping = {
            "healthy": 0,
            "unknown": 1,
            "degraded": 2,
            "unhealthy": 3,
        }
        return mapping.get(str(health_status or "unknown").lower(), 3)
