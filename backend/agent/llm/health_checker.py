from __future__ import annotations

from typing import Iterable


class ModelHealthChecker:
    async def check(self, models: Iterable[dict]) -> list[dict]:
        return [
            {
                **item,
                "health_status": item.get("health_status") or "healthy",
                "health_message": item.get("health_message"),
            }
            for item in models
        ]

