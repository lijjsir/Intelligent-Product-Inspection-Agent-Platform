from __future__ import annotations

from agent.llm.model_selector import ModelSelector
from infra.cache.rate_limiter import RateLimiter


class LLMGateway:
    def __init__(self) -> None:
        self._selector = ModelSelector()

    async def select_runtime(
        self,
        models: list[dict] | None = None,
        *,
        excluded_runtime_ids: set[str] | None = None,
        model_types: set[str] | None = None,
        reserve: bool = True,
    ) -> dict[str, str | int | float | None] | None:
        excluded_runtime_ids = excluded_runtime_ids or set()
        candidates = self._selector.ordered_candidates(
            models or [],
            excluded_runtime_ids=excluded_runtime_ids,
            model_types=model_types,
        )
        for failover_depth, item in enumerate(candidates):
            if await self._within_rate_limit(item, reserve=reserve):
                return self._build_runtime_payload(item, failover_depth=failover_depth)
        return None

    async def has_available_runtime(
        self,
        models: list[dict] | None = None,
        *,
        excluded_runtime_ids: set[str] | None = None,
        model_types: set[str] | None = None,
    ) -> bool:
        runtime = await self.select_runtime(
            models=models,
            excluded_runtime_ids=excluded_runtime_ids,
            model_types=model_types,
            reserve=False,
        )
        return runtime is not None

    async def _within_rate_limit(self, model: dict, *, reserve: bool) -> bool:
        rpm_limit = model.get("rpm_limit")
        limiter = RateLimiter(int(rpm_limit) if rpm_limit is not None else None)
        key = f"llm:{self._runtime_key(model)}"
        if reserve:
            return await limiter.reserve(key)
        return await limiter.allow(key)

    def _build_runtime_payload(
        self,
        selected: dict,
        *,
        failover_depth: int,
    ) -> dict[str, str | int | float | None]:
        return {
            "runtime_key": self._runtime_key(selected),
            "model_config_id": str(selected.get("id") or "") or None,
            "model_id": str(selected.get("model_key") or ""),
            "base_url": str(selected.get("endpoint") or ""),
            "api_key": selected.get("api_key"),
            "provider": str(selected.get("provider") or "custom"),
            "input_price_per_million": selected.get("input_price_per_million"),
            "output_price_per_million": selected.get("output_price_per_million"),
            "rpm_limit": selected.get("rpm_limit"),
            "failover_depth": failover_depth,
        }

    def _runtime_key(self, selected: dict) -> str:
        if selected.get("runtime_key"):
            return str(selected["runtime_key"])
        return ModelSelector.runtime_id(selected)
