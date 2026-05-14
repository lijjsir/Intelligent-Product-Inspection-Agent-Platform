from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
try:
    from volcenginesdkarkruntime import Ark
except Exception:  # pragma: no cover - optional dependency at runtime
    Ark = None

from agent.llm.langfuse_tracer import LangfuseTracer
from app.core.config import settings


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_id: str | None = None,
        embed_model: str | None = None,
        trace_id: str | None = None,
        task_id: str | None = None,
        org_id: str | None = None,
        provider: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.volcengine_api_key
        self._base_url = (base_url or settings.volcengine_base_url).rstrip("/")
        self._model_id = model_id or settings.volcengine_model_id
        self._embed_model = embed_model or settings.volcengine_embed_model
        self._provider = provider or "volcengine"
        self._task_id = None if task_id is None else str(task_id)
        self._org_id = None if org_id is None else str(org_id)
        self._request_attempts = 3
        self._tracer = LangfuseTracer()
        self._trace_id = trace_id or (self._tracer.create_trace_id() if self._tracer.enabled else None)
        self._ark_client = Ark(api_key=self._api_key) if Ark and self._api_key else None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def trace_id(self) -> str | None:
        return self._trace_id

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        observation_name: str = "llm.chat",
        observation_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self._model_id,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        return await self._post_json(
            "/chat/completions",
            payload,
            observation_name=observation_name,
            observation_type="generation",
            observation_metadata=observation_metadata,
        )

    async def vision_chat(self, prompt: str, image_urls: list[str]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        return await self.chat(
            [{"role": "user", "content": content}],
            temperature=0.1,
            observation_name="llm.vision_chat",
            observation_metadata={"image_count": len(image_urls), "modality": "vision"},
        )

    async def embed(
        self,
        text: str,
        *,
        observation_name: str = "llm.embedding",
        observation_metadata: dict[str, Any] | None = None,
    ) -> list[float]:
        metadata = dict(observation_metadata or {})
        metadata.setdefault("modality", "text")
        if self._should_use_multimodal_embedding():
            vector = await self._embed_with_multimodal_sdk(
                text,
                observation_name=observation_name,
                observation_metadata=metadata,
            )
            if vector:
                return vector

        payload = {"model": self._embed_model, "input": [text]}
        try:
            data = await self._post_json(
                "/embeddings",
                payload,
                observation_name=observation_name,
                observation_type="embedding",
                observation_metadata={**metadata, "input_shape": "list"},
            )
        except httpx.HTTPStatusError:
            fallback_payload = {"model": self._embed_model, "input": text}
            data = await self._post_json(
                "/embeddings",
                fallback_payload,
                observation_name=observation_name,
                observation_type="embedding",
                observation_metadata={**metadata, "input_shape": "string", "fallback": True},
            )
        vector = self._extract_embedding_vector(data)
        if not vector:
            raise RuntimeError("embedding response did not include a vector")
        return vector

    def _should_use_multimodal_embedding(self) -> bool:
        model = (self._embed_model or "").lower()
        return "embedding-vision" in model or model.startswith("ep-")

    async def _embed_with_multimodal_sdk(
        self,
        text: str,
        *,
        observation_name: str,
        observation_metadata: dict[str, Any] | None = None,
    ) -> list[float]:
        if not self._ark_client:
            return []

        def _request() -> Any:
            return self._ark_client.multimodal_embeddings.create(
                model=self._embed_model,
                input=[{"type": "text", "text": text}],
            )

        observation_input = {"model": self._embed_model, "input": [{"type": "text", "text": text}]}
        with self._tracer.observe(
            trace_id=self._trace_id,
            name=observation_name,
            as_type="embedding",
            input=observation_input,
            model=self._embed_model,
            model_parameters={"transport": "ark_sdk"},
            metadata=self._build_observation_metadata(path="ark.multimodal_embeddings", extra=observation_metadata),
        ) as observation:
            try:
                resp = await asyncio.to_thread(_request)
            except Exception as exc:
                self._safe_update_observation(
                    observation,
                    level="ERROR",
                    status_message=str(exc),
                    output={"error": str(exc)},
                )
                raise

            if isinstance(resp, dict):
                data = resp
            else:
                data = self._normalize_multimodal_embedding_response(resp)
                if not data:
                    self._safe_update_observation(
                        observation,
                        output={"vector_size": 0, "transport": "ark_sdk", "unsupported_response": True},
                    )
                    return []

            vector = self._extract_embedding_vector(data)
            usage_metadata = self._normalize_usage(data.get("usage") if isinstance(data, dict) else None)
            self._safe_update_observation(
                observation,
                output={"vector_size": len(vector), "transport": "ark_sdk", "response": data},
                metadata={
                    "vector_size": len(vector),
                    "transport": "ark_sdk",
                    **({"usage": usage_metadata} if usage_metadata else {}),
                },
            )
            return vector

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

    @classmethod
    def _normalize_multimodal_embedding_response(cls, response: Any) -> dict[str, Any] | None:
        raw_data = cls._read_field(response, "data")
        normalized_data = cls._normalize_embedding_payload(raw_data)
        if normalized_data is None:
            return None

        payload: dict[str, Any] = {
            "data": normalized_data,
            "model": cls._read_field(response, "model"),
        }
        usage = cls._usage_to_dict(cls._read_field(response, "usage"))
        if usage:
            payload["usage"] = usage
        return payload

    @classmethod
    def _normalize_embedding_payload(cls, value: Any) -> list[dict[str, Any]] | dict[str, Any] | None:
        if isinstance(value, list):
            items = [item for item in (cls._normalize_embedding_item(entry) for entry in value) if item]
            return items
        if isinstance(value, dict):
            return value
        item = cls._normalize_embedding_item(value)
        return item

    @staticmethod
    def _normalize_embedding_item(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            embedding = value.get("embedding")
            if isinstance(embedding, list):
                normalized = {"embedding": embedding}
                if "index" in value:
                    normalized["index"] = value.get("index")
                if "object" in value:
                    normalized["object"] = value.get("object")
                return normalized
            return None

        embedding = getattr(value, "embedding", None)
        if not isinstance(embedding, list):
            return None

        normalized = {"embedding": embedding}
        index = getattr(value, "index", None)
        object_name = getattr(value, "object", None)
        if index is not None:
            normalized["index"] = index
        if object_name is not None:
            normalized["object"] = object_name
        return normalized

    @staticmethod
    def _read_field(value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    async def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        observation_name: str,
        observation_type: str,
        observation_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError("VOLCENGINE_API_KEY is not configured")

        headers = {"Authorization": f"Bearer {self._api_key}"}
        model_name = str(payload.get("model") or self._model_id)
        model_parameters = {
            key: value
            for key, value in payload.items()
            if key not in {"messages", "input", "model"}
        }
        with self._tracer.observe(
            trace_id=self._trace_id,
            name=observation_name,
            as_type=observation_type,
            input=payload,
            model=model_name,
            model_parameters=model_parameters or None,
            metadata=self._build_observation_metadata(path=path, extra=observation_metadata),
        ) as observation:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=45.0) as client:
                last_error: Exception | None = None
                request_payload = dict(payload)
                response_format_fallback = False
                observation_id: str | None = None
                data: dict[str, Any] = {}
                for attempt in range(1, self._request_attempts + 1):
                    try:
                        resp = await client.post(path, json=request_payload, headers=headers)
                    except httpx.TransportError as exc:
                        last_error = exc
                        if attempt >= self._request_attempts:
                            self._safe_update_observation(
                                observation,
                                level="ERROR",
                                status_message=f"{type(exc).__name__}: {exc}",
                                output={"error": str(exc)},
                                metadata={"attempt": attempt, "response_format_fallback": response_format_fallback},
                            )
                            raise
                        await asyncio.sleep(self._retry_delay(attempt))
                        continue

                    if resp.is_error:
                        detail = resp.text
                        status_error = httpx.HTTPStatusError(
                            f"{resp.status_code} for {path}: {detail}",
                            request=resp.request,
                            response=resp,
                        )
                        if self._should_retry_without_response_format(path, request_payload, resp):
                            request_payload = dict(request_payload)
                            request_payload.pop("response_format", None)
                            response_format_fallback = True
                            continue
                        if resp.status_code in {408, 409, 425, 429, 500, 502, 503, 504} and attempt < self._request_attempts:
                            last_error = status_error
                            await asyncio.sleep(self._retry_delay(attempt))
                            continue
                        self._safe_update_observation(
                            observation,
                            level="ERROR",
                            status_message=f"{resp.status_code} for {path}",
                            output={"status_code": resp.status_code, "detail": detail},
                            metadata={
                                "status_code": resp.status_code,
                                "attempt": attempt,
                                "response_format_fallback": response_format_fallback,
                            },
                        )
                        raise status_error

                    data = resp.json()
                    usage_metadata = self._normalize_usage(data.get("usage") if isinstance(data, dict) else None)
                    observation_id = self._tracer.current_observation_id()
                    self._safe_update_observation(
                        observation,
                        output=data,
                        usage_details=usage_metadata,
                        metadata={
                            "status_code": resp.status_code,
                            "response_id": data.get("id") if isinstance(data, dict) else None,
                            "attempt": attempt,
                            "response_format_fallback": response_format_fallback,
                            **({"usage": usage_metadata} if usage_metadata else {}),
                        },
                    )
                    break
                else:
                    if last_error is not None:
                        raise last_error
                    raise RuntimeError(f"request failed without response for {path}")

        meta = {
            "id": data.get("id"),
            "model": data.get("model"),
            "usage": data.get("usage"),
        }
        langfuse_meta = self._build_langfuse_meta(observation_id=observation_id)
        if langfuse_meta:
            meta["langfuse"] = langfuse_meta

        choices = data.get("choices") or []
        if choices:
            content = ((choices[0] or {}).get("message") or {}).get("content")
            if isinstance(content, str):
                parsed = self._extract_json_object(content)
                if isinstance(parsed, dict):
                    parsed["__meta__"] = meta
                    return parsed
                return {"text": content, "__meta__": meta}
        if isinstance(data, dict):
            data["__meta__"] = meta
        return data

    def _build_observation_metadata(self, *, path: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "provider": self._provider,
            "base_url": self._base_url,
            "path": path,
        }
        if self._task_id:
            metadata["task_id"] = self._task_id
        if self._org_id:
            metadata["org_id"] = self._org_id
        if extra:
            metadata.update({key: value for key, value in extra.items() if value is not None})
        return metadata

    def _build_langfuse_meta(self, *, observation_id: str | None = None) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        if self._trace_id:
            meta["trace_id"] = self._trace_id
            trace_url = self._tracer.get_trace_url(self._trace_id)
            if trace_url:
                meta["trace_url"] = trace_url
        if observation_id:
            meta["observation_id"] = observation_id
        return meta

    @staticmethod
    def _normalize_usage(raw_usage: Any) -> dict[str, int] | None:
        usage_dict = LLMClient._usage_to_dict(raw_usage)
        if usage_dict is None:
            return None

        normalized: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage_dict.get(key)
            if isinstance(value, (int, float)):
                normalized[key] = int(value)
        return normalized or None

    @staticmethod
    def _usage_to_dict(raw_usage: Any) -> dict[str, Any] | None:
        if isinstance(raw_usage, dict):
            return raw_usage
        if raw_usage is None:
            return None

        payload: dict[str, Any] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(raw_usage, key, None)
            if value is not None:
                payload[key] = value
        return payload or None

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return min(0.5 * (2 ** max(attempt - 1, 0)), 2.0)

    @staticmethod
    def _should_retry_without_response_format(path: str, payload: dict[str, Any], response: httpx.Response) -> bool:
        if path != "/chat/completions":
            return False
        response_format = payload.get("response_format")
        if not isinstance(response_format, dict) or response_format.get("type") != "json_object":
            return False
        detail = response.text.lower()
        return "response_format.type" in detail and "json_object" in detail and "not supported by this model" in detail

    @staticmethod
    def _safe_update_observation(observation: Any, **kwargs) -> None:
        updater = getattr(observation, "update", None)
        if not callable(updater):
            return
        payload = {key: value for key, value in kwargs.items() if value is not None}
        if not payload:
            return
        try:
            updater(**payload)
        except Exception:
            return

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        candidates = [text.strip()]
        if "```" in text:
            for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S):
                candidates.append(block.strip())

        for candidate in candidates:
            if not candidate:
                continue
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                start = candidate.find("{")
                end = candidate.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    continue
                try:
                    parsed = json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    continue
            if isinstance(parsed, dict):
                return parsed
        return None
