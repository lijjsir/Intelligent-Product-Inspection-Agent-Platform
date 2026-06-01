from __future__ import annotations

import json
from typing import Any, Iterable

import httpx

from agent.llm.base_url_resolver import resolve_runtime_base_url
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
        endpoint = resolve_runtime_base_url(item.get("provider"), item.get("endpoint"))
        if not endpoint:
            return "unhealthy", "missing endpoint"

        model_key = str(item.get("model_key") or "").strip()
        if not model_key:
            return "unhealthy", "missing model_key"

        headers = {}
        if item.get("api_key"):
            headers["Authorization"] = f"Bearer {item['api_key']}"

        timeout = float(settings.model_health_timeout_sec)
        async with httpx.AsyncClient(base_url=endpoint, timeout=timeout, trust_env=False) as client:
            try:
                response = await client.get("/models", headers=headers)
            except httpx.TimeoutException:
                return "degraded", "health probe timeout"
            except httpx.HTTPError as exc:
                return "degraded", self._trim_message(f"http probe failed: {exc}")

            if response.status_code >= 400:
                return self._status_from_response(response, path="/models")

            try:
                model_ids = self._extract_model_ids(response)
            except ValueError as exc:
                return "unhealthy", self._trim_message(f"GET /models returned invalid payload: {exc}")

            if model_key in model_ids:
                return "healthy", "GET /models contains model_key"
            fallback_status, fallback_message = await self._probe_runtime_model(
                client=client,
                item=item,
                headers=headers,
                model_ids=model_ids,
            )
            if fallback_status is not None:
                return fallback_status, fallback_message
            return "unhealthy", self._missing_model_key_message(model_key, set())

    async def _probe_runtime_model(
        self,
        *,
        client: httpx.AsyncClient,
        item: dict[str, Any],
        headers: dict[str, str],
        model_ids: set[str],
    ) -> tuple[str | None, str | None]:
        model_key = str(item.get("model_key") or "").strip()
        provider = str(item.get("provider") or "").strip().lower()
        model_type = str(item.get("model_type") or "chat").strip().lower()

        # Ark endpoint-style models such as ep-... may be callable even when /models
        # only returns upstream foundation model names instead of the endpoint id.
        if provider == "volcengine" and model_key.startswith("ep-"):
            if model_type == "embedding":
                return await self._probe_embedding_runtime(client=client, headers=headers, model_key=model_key, model_ids=model_ids)
            return await self._probe_chat_runtime(client=client, headers=headers, model_key=model_key, model_ids=model_ids)
        return None, None

    async def _probe_chat_runtime(
        self,
        *,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        model_key: str,
        model_ids: set[str],
    ) -> tuple[str, str]:
        payload = {
            "model": model_key,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        try:
            response = await client.post("/chat/completions", json=payload, headers=headers)
        except httpx.TimeoutException:
            return "degraded", "chat probe timeout"
        except httpx.HTTPError as exc:
            return "degraded", self._trim_message(f"chat probe failed: {exc}")

        if response.status_code >= 400:
            return self._status_from_response(response, path="/chat/completions")
        return "healthy", self._direct_probe_success_message(model_key, model_ids, probe_path="/chat/completions")

    async def _probe_embedding_runtime(
        self,
        *,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        model_key: str,
        model_ids: set[str],
    ) -> tuple[str, str]:
        payload = {
            "model": model_key,
            "input": "ping",
        }
        try:
            response = await client.post("/embeddings", json=payload, headers=headers)
        except httpx.TimeoutException:
            return "degraded", "embedding probe timeout"
        except httpx.HTTPError as exc:
            return "degraded", self._trim_message(f"embedding probe failed: {exc}")

        if response.status_code >= 400:
            return self._status_from_response(response, path="/embeddings")
        return "healthy", self._direct_probe_success_message(model_key, model_ids, probe_path="/embeddings")

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

    @classmethod
    def _missing_model_key_message(cls, model_key: str, model_ids: set[str]) -> str:
        available = sorted(value for value in model_ids if value)[:5]
        suffix = f"; available: [{', '.join(available)}]" if available else ""
        return cls._trim_message(f"GET /models missing model_key: {model_key}{suffix}") or (
            f"GET /models missing model_key: {model_key}"
        )

    @classmethod
    def _direct_probe_success_message(cls, model_key: str, model_ids: set[str], *, probe_path: str) -> str:
        available = sorted(value for value in model_ids if value)[:5]
        suffix = f"; available: [{', '.join(available)}]" if available else ""
        return cls._trim_message(
            f"{probe_path} accepted model_key: {model_key}; /models did not list endpoint id{suffix}"
        ) or f"{probe_path} accepted model_key: {model_key}"

    @staticmethod
    def _extract_model_ids(response: httpx.Response) -> set[str]:
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("response is not valid JSON") from exc

        items: list[Any]
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            for key in ("data", "models", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    items = value
                    break
            else:
                raise ValueError("missing model list")
        else:
            raise ValueError("unsupported response type")

        model_ids: set[str] = set()
        for entry in items:
            if isinstance(entry, str):
                value = entry.strip()
                if value:
                    model_ids.add(value)
                continue
            if isinstance(entry, dict):
                for key in ("id", "model", "model_key", "name"):
                    value = str(entry.get(key) or "").strip()
                    if value:
                        model_ids.add(value)
                continue
        if not model_ids:
            raise ValueError("empty model list")
        return model_ids
