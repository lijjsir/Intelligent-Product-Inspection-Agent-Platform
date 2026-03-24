from __future__ import annotations

from app.core.config import settings
from agent.llm.model_selector import ModelSelector


class LLMGateway:
    def __init__(self) -> None:
        self._selector = ModelSelector()

    def select_runtime(self, models: list[dict] | None = None) -> dict[str, str | None]:
        selected = self._selector.select(models or [])
        if not selected:
            return {
                "model_config_id": None,
                "model_id": settings.volcengine_model_id,
                "base_url": settings.volcengine_base_url,
                "api_key": settings.volcengine_api_key,
                "provider": "volcengine",
                "input_price_per_million": None,
                "output_price_per_million": None,
            }
        return {
            "model_config_id": str(selected.get("id") or ""),
            "model_id": str(selected.get("model_key") or settings.volcengine_model_id),
            "base_url": str(selected.get("endpoint") or settings.volcengine_base_url),
            "api_key": selected.get("api_key"),
            "provider": str(selected.get("provider") or "custom"),
            "input_price_per_million": selected.get("input_price_per_million"),
            "output_price_per_million": selected.get("output_price_per_million"),
        }
