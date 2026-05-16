from __future__ import annotations

from typing import Any, Iterable

import httpx

from agent.llm.client import LLMClient
from app.core.config import settings


class ModelHealthChecker:
    async def check(self, models: Iterable[dict]) -> list[dict]:
        checked: list[dict[str, Any]] = []
        for item in models:
            payload = dict(item)
            status, message = await self._check_one(payload)
            payload["health_status"] = status
            payload["health_message"] = message
            checked.append(payload)
        return checked

    async def _check_one(self, item: dict[str, Any]) -> tuple[str, str | None]:
        endpoint = str(item.get("endpoint") or "").rstrip("/")
        if not endpoint:
            return "unhealthy", "missing endpoint"

        if self._is_embedding_model(item) and self._uses_sdk_embedding(item):
            return await self._probe_embedding_runtime(item)

        headers = {}
        if item.get("api_key"):
            headers["Authorization"] = f"Bearer {item['api_key']}"

        timeout = float(settings.model_health_timeout_sec)
        async with httpx.AsyncClient(base_url=endpoint, timeout=timeout) as client:
            try:
                response = await client.get("/models", headers=headers)
            except httpx.TimeoutException:
                return "degraded", "health probe timeout"
            except httpx.HTTPError as exc:
                return "degraded", self._trim_message(f"http probe failed: {exc}")

            if response.status_code < 400:
                if self._is_embedding_model(item):
                    return await self._probe_embedding(client, headers=headers, model_key=str(item.get("model_key") or ""))
                return "healthy", "GET /models ok"

            if response.status_code in {401, 403, 404, 405}:
                if self._is_embedding_model(item):
                    return await self._probe_embedding(client, headers=headers, model_key=str(item.get("model_key") or ""))
                return await self._probe_chat_completion(client, headers=headers, model_key=str(item.get("model_key") or ""))

            return self._status_from_response(response, path="/models")

    async def _probe_chat_completion(
        self,
        client: httpx.AsyncClient,
        *,
        headers: dict[str, str],
        model_key: str,
    ) -> tuple[str, str | None]:
        try:
            response = await client.post(
                "/chat/completions",
                json={
                    "model": model_key,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                headers=headers,
            )
        except httpx.TimeoutException:
            return "degraded", "chat probe timeout"
        except httpx.HTTPError as exc:
            return "degraded", self._trim_message(f"chat probe failed: {exc}")

        if response.status_code < 400:
            return "healthy", "POST /chat/completions ok"
        return self._status_from_response(response, path="/chat/completions")

    async def _probe_embedding(
        self,
        client: httpx.AsyncClient,
        *,
        headers: dict[str, str],
        model_key: str,
    ) -> tuple[str, str | None]:
        try:
            response = await client.post(
                "/embeddings",
                json={
                    "model": model_key,
                    "input": ["ping"],
                },
                headers=headers,
            )
        except httpx.TimeoutException:
            return "degraded", "embedding probe timeout"
        except httpx.HTTPError as exc:
            return "degraded", self._trim_message(f"embedding probe failed: {exc}")

        if response.status_code < 400:
            return "healthy", "POST /embeddings ok"
        return self._status_from_response(response, path="/embeddings")

    async def _probe_embedding_runtime(self, item: dict[str, Any]) -> tuple[str, str | None]:
        client = LLMClient(
            api_key=str(item.get("api_key") or "") or None,
            base_url=str(item.get("endpoint") or ""),
            model_id=str(item.get("model_key") or ""),
            embed_model=str(item.get("model_key") or ""),
            provider=str(item.get("provider") or ""),
        )
        try:
            vector = await client.embed(
                "ping",
                observation_name="llm.health_embedding_probe",
                observation_metadata={"component": "health_checker"},
            )
        except httpx.TimeoutException:
            return "degraded", "embedding probe timeout"
        except Exception as exc:
            return "degraded", self._trim_message(f"embedding probe failed: {exc}")

        if vector:
            return "healthy", "embedding runtime ok"
        return "unhealthy", "embedding probe returned empty vector"

    def _status_from_response(self, response: httpx.Response, *, path: str) -> tuple[str, str | None]:
        status_code = response.status_code
        detail = self._trim_message(response.text)
        if status_code in {401, 403}:
            return "unhealthy", f"{path} auth failed: {status_code}"
        if status_code == 429:
            return "degraded", f"{path} rate limited: {status_code}"
        if status_code >= 500:
            return "degraded", f"{path} upstream error: {status_code}"
        return "unhealthy", self._trim_message(f"{path} returned {status_code}: {detail}")

    @staticmethod
    def _trim_message(message: str | None) -> str | None:
        if not message:
            return None
        return message.strip()[:256]

    @staticmethod
    def _is_embedding_model(item: dict[str, Any]) -> bool:
        model_type = str(item.get("model_type") or "").strip().lower()
        return model_type in {"embedding", "embed", "text_embedding"}

    @staticmethod
    def _uses_sdk_embedding(item: dict[str, Any]) -> bool:
        provider = str(item.get("provider") or "").strip().lower()
        model_key = str(item.get("model_key") or "").strip().lower()
        return provider == "volcengine" and ("embedding-vision" in model_key or model_key.startswith("ep-"))
