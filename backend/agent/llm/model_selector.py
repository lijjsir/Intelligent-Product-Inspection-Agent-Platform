from __future__ import annotations


INFERENCE_MODEL_TYPES = {"chat", "vision", "multimodal", "vlm", "llm"}


class ModelSelector:
    def ordered_candidates(
        self,
        models: list[dict],
        *,
        excluded_runtime_ids: set[str] | None = None,
        model_types: set[str] | None = None,
    ) -> list[dict]:
        excluded_runtime_ids = excluded_runtime_ids or set()
        supported_model_types = self._normalize_model_types(model_types) if model_types else INFERENCE_MODEL_TYPES
        active = [
            item
            for item in models
            if item.get("is_active")
            and self._supports_model_type(item, supported_model_types)
            and self._is_configured_runtime(item)
            and self.runtime_id(item) not in excluded_runtime_ids
        ]
        return sorted(active, key=self._sort_key)

    def select(
        self,
        models: list[dict],
        *,
        excluded_runtime_ids: set[str] | None = None,
        model_types: set[str] | None = None,
    ) -> dict | None:
        ordered = self.ordered_candidates(
            models,
            excluded_runtime_ids=excluded_runtime_ids,
            model_types=model_types,
        )
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
    def _supports_model_type(item: dict, model_types: set[str]) -> bool:
        model_type = str(item.get("model_type") or "chat").lower()
        return model_type in model_types

    @staticmethod
    def _normalize_model_types(model_types: set[str]) -> set[str]:
        return {str(item or "").strip().lower() for item in model_types if str(item or "").strip()}

    @staticmethod
    def _health_rank(health_status: str | None) -> int:
        mapping = {
            "healthy": 0,
            "unknown": 1,
            "degraded": 2,
            "unhealthy": 3,
        }
        return mapping.get(str(health_status or "unknown").lower(), 3)

    @staticmethod
    def _is_configured_runtime(item: dict) -> bool:
        endpoint = str(item.get("endpoint") or "").strip()
        if not endpoint:
            return False
        provider = str(item.get("provider") or "").strip().lower()
        if provider == "local_openai":
            return True
        return bool(str(item.get("api_key") or "").strip())

