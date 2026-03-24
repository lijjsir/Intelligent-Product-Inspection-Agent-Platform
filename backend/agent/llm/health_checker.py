from __future__ import annotations

from typing import Any, Iterable

import httpx

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
                return "healthy", "GET /models ok"

            if response.status_code in {404, 405}:
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
