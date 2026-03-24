from __future__ import annotations


class ModelSelector:
    def select(self, models: list[dict]) -> dict | None:
        active = [item for item in models if item.get("is_active") and self._supports_inference(item)]
        healthy = [item for item in active if item.get("health_status") in {"healthy", "unknown"}]
        pool = healthy or active
        if not pool:
            return None
        return sorted(pool, key=lambda item: int(item.get("priority") or 9999))[0]

    @staticmethod
    def _supports_inference(item: dict) -> bool:
        model_type = str(item.get("model_type") or "chat").lower()
        return model_type in {"chat", "vision", "multimodal", "vlm", "llm"}
