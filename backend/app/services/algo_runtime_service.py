from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(slots=True)
class DeploymentRuntimeRecord:
    deployment_id: str
    source_type: str
    source_id: str
    model_key: str | None
    provider: str | None
    endpoint: str
    status: str
    inference_config: dict[str, Any]


class AlgoRuntimeRegistry:
    def register(
        self,
        *,
        deployment_id: str,
        source_type: str,
        source_id: str,
        model_key: str | None,
        provider: str | None,
        inference_config: dict[str, Any],
    ) -> DeploymentRuntimeRecord:
        endpoint = f"{settings.algo_runtime_base_url.rstrip('/')}/runtime/algo-deployments/{deployment_id}/infer"
        return DeploymentRuntimeRecord(
            deployment_id=deployment_id,
            source_type=source_type,
            source_id=source_id,
            model_key=model_key,
            provider=provider,
            endpoint=endpoint,
            status="available",
            inference_config=inference_config,
        )

    def unregister(self, *, deployment_id: str) -> None:
        return None
