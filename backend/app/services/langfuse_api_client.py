from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

API_V1_PREFIX = "/api/public"


class LangfuseApiError(Exception):
    pass


class LangfuseApiClient:
    def __init__(self) -> None:
        self._host = str(settings.langfuse_host or "").rstrip("/")
        self._public_host = str(getattr(settings, "langfuse_public_host", "") or "").rstrip("/")
        self._project_id = getattr(settings, "langfuse_project_id", "") or ""
        self._enabled = bool(
            settings.langfuse_enabled
            and settings.langfuse_public_key
            and settings.langfuse_secret_key
            and self._host
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _auth_header(self) -> dict[str, str]:
        raw = f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}"
        encoded = base64.b64encode(raw.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def _api_url(self, path: str) -> str:
        return f"{self._host}{API_V1_PREFIX}{path}"

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self._enabled:
            raise LangfuseApiError("Langfuse is not enabled or configured")
        url = self._api_url(path)
        headers = {**self._auth_header(), "Content-Type": "application/json"}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(method, url, headers=headers, **kwargs)
            if resp.status_code >= 400:
                detail = (resp.text or "")[:500]
                logger.warning("Langfuse API %s %s returned %s: %s", method, url, resp.status_code, detail)
                raise LangfuseApiError(f"Langfuse API error {resp.status_code}: {detail}")
            try:
                return resp.json() if resp.text else {}
            except Exception:
                return {}
        except httpx.RequestError as exc:
            logger.warning("Langfuse API request failed: %s %s: %s", method, url, exc)
            raise LangfuseApiError(f"Langfuse API request failed: {exc}") from exc

    async def list_traces(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        user_id: str | None = None,
        name: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if user_id:
            params["userId"] = user_id
        if name:
            params["name"] = name
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        if tags:
            params["tags"] = tags
        return await self._request("GET", "/traces", params=params)

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/traces/{trace_id}")

    async def delete_trace(self, trace_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/traces/{trace_id}")

    async def list_observations(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        trace_id: str | None = None,
        user_id: str | None = None,
        type: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if trace_id:
            params["traceId"] = trace_id
        if user_id:
            params["userId"] = user_id
        if type:
            params["type"] = type
        if name:
            params["name"] = name
        return await self._request("GET", "/observations", params=params)

    async def get_observation(self, observation_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/observations/{observation_id}")

    async def list_scores(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        trace_id: str | None = None,
        user_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if trace_id:
            params["traceId"] = trace_id
        if user_id:
            params["userId"] = user_id
        if name:
            params["name"] = name
        return await self._request("GET", "/scores", params=params)

    async def delete_score(self, score_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/scores/{score_id}")

    def build_trace_url(self, trace_id: str) -> str | None:
        if not self._public_host or not self._project_id:
            return None
        return f"{self._public_host}/project/{self._project_id}/traces/{trace_id}"

    async def trace_exists(self, trace_id: str) -> bool:
        try:
            await self.get_trace(trace_id)
            return True
        except LangfuseApiError as exc:
            if "404" in str(exc):
                return False
            raise
