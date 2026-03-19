from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
try:
    from volcenginesdkarkruntime import Ark
except Exception:  # pragma: no cover - optional dependency at runtime
    Ark = None

from app.core.config import settings


class LLMClient:
    def __init__(self) -> None:
        self._api_key = settings.volcengine_api_key
        self._base_url = settings.volcengine_base_url.rstrip("/")
        self._model_id = settings.volcengine_model_id
        self._embed_model = settings.volcengine_embed_model
        self._ark_client = Ark(api_key=self._api_key) if Ark and self._api_key else None

    @property
    def model_id(self) -> str:
        return self._model_id

    async def chat(self, messages: list[dict[str, Any]], *, temperature: float = 0.2) -> dict[str, Any]:
        payload = {
            "model": self._model_id,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        return await self._post_json("/chat/completions", payload)

    async def vision_chat(self, prompt: str, image_urls: list[str]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        return await self.chat([{"role": "user", "content": content}], temperature=0.1)

    async def embed(self, text: str) -> list[float]:
        if self._should_use_multimodal_embedding():
            vector = await self._embed_with_multimodal_sdk(text)
            if vector:
                return vector

        payload = {"model": self._embed_model, "input": [text]}
        try:
            data = await self._post_json("/embeddings", payload)
        except httpx.HTTPStatusError:
            # Some providers accept string, some require list; fallback once.
            fallback_payload = {"model": self._embed_model, "input": text}
            try:
                data = await self._post_json("/embeddings", fallback_payload)
            except httpx.HTTPStatusError:
                # Embedding failure should not break the whole inspection flow.
                return []
        return self._extract_embedding_vector(data)

    def _should_use_multimodal_embedding(self) -> bool:
        model = (self._embed_model or "").lower()
        return "embedding-vision" in model or model.startswith("ep-")

    async def _embed_with_multimodal_sdk(self, text: str) -> list[float]:
        if not self._ark_client:
            return []

        def _request() -> Any:
            return self._ark_client.multimodal_embeddings.create(
                model=self._embed_model,
                input=[{"type": "text", "text": text}],
            )

        try:
            resp = await asyncio.to_thread(_request)
        except Exception:
            return []

        if hasattr(resp, "model_dump"):
            data = resp.model_dump()
        elif isinstance(resp, dict):
            data = resp
        else:
            return []

        return self._extract_embedding_vector(data)

    def _extract_embedding_vector(self, data: dict[str, Any]) -> list[float]:
        container = data.get("data")
        if isinstance(container, list):
            if not container:
                return []
            embedding = container[0].get("embedding")
            return embedding if isinstance(embedding, list) else []
        if isinstance(container, dict):
            embedding = container.get("embedding")
            return embedding if isinstance(embedding, list) else []
        return []

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError("VOLCENGINE_API_KEY is not configured")
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=45.0) as client:
            resp = await client.post(path, json=payload, headers=headers)
            if resp.is_error:
                detail = resp.text
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} for {path}: {detail}",
                    request=resp.request,
                    response=resp,
                )
            data = resp.json()

        # OpenAI-compatible response: pick message content and decode JSON object content.
        choices = data.get("choices") or []
        if choices:
            content = ((choices[0] or {}).get("message") or {}).get("content")
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    return {"text": content}
        return data
