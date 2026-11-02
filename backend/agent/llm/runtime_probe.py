from __future__ import annotations

import base64
import json
import math
import struct
import time
import zlib
from typing import Any

import httpx

from agent.llm.base_url_resolver import resolve_runtime_base_url
from agent.llm.runtime_auth import runtime_headers
from agent.llm.runtime_options import apply_runtime_options
from app.core.config import settings
from app.core.model_types import normalize_model_type


def _probe_image() -> str:
    """A valid 64x64 white PNG, generated without files or external URLs."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff" * 64 * 3) * 64))
    png += chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


class ModelRuntimeProbe:
    """Small synthetic requests that verify protocol support, not model accuracy."""

    async def verify(self, item: dict[str, Any], capabilities: list[str]) -> list[dict[str, Any]]:
        endpoint = resolve_runtime_base_url(item.get("provider"), item.get("endpoint"))
        headers = runtime_headers(item.get("provider"), item.get("api_key"))
        async with httpx.AsyncClient(
            base_url=endpoint, timeout=float(settings.local_model_timeout_sec), trust_env=False,
        ) as client:
            return [
                await self.check_capability(client, item, capability, headers=headers)
                for capability in dict.fromkeys(capabilities)
            ]

    @staticmethod
    def basic_capability(item: dict[str, Any]) -> str:
        model_type = normalize_model_type(item.get("model_type") or "chat")
        return {"embedding": "embedding", "multimodal": "vision"}.get(model_type, "text")

    async def check_capability(
        self, client: httpx.AsyncClient, item: dict[str, Any], capability: str, *, headers: dict[str, str],
    ) -> dict[str, Any]:
        started = time.monotonic()
        result: dict[str, Any] = {"capability": capability, "status": "unhealthy", "message": ""}
        try:
            path, payload = self._request(str(item.get("model_key") or ""), capability)
            payload = apply_runtime_options(payload, item.get("provider"))
            response = await client.post(path, json=payload, headers=headers)
            if response.status_code >= 400:
                if response.status_code in {400, 404, 405, 422, 501}:
                    result["status"] = "unsupported"
                elif response.status_code in {408, 429} or response.status_code >= 500:
                    result["status"] = "degraded"
                result["message"] = f"{path} HTTP {response.status_code}; check model and capability support"
            else:
                data = response.json()
                detail = self._validate(data, capability)
                result.update(status="healthy", message=detail)
                if capability == "embedding":
                    result["vector_dimension"] = len(data["data"][0]["embedding"])
        except httpx.TimeoutException:
            result.update(status="degraded", message="模型调用超时；首次加载可能较慢，请检查推理服务日志后重试")
        except httpx.HTTPError:
            result.update(status="degraded", message="无法连接模型接口，请检查地址、端口和容器到宿主机的网络")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            result["message"] = f"invalid {capability} response: {type(exc).__name__}"
        result["latency_ms"] = round((time.monotonic() - started) * 1000)
        return result

    @staticmethod
    def _request(model: str, capability: str) -> tuple[str, dict[str, Any]]:
        if capability == "embedding":
            return "/embeddings", {"model": model, "input": ["PIAP model connection test"]}
        payload: dict[str, Any] = {
            "model": model, "stream": False, "max_tokens": 128, "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with the word OK."}],
        }
        if capability == "json":
            payload["response_format"] = {"type": "json_object"}
            payload["messages"][0]["content"] = 'Return only this JSON object: {"ok":true}'
        elif capability == "vision":
            payload["messages"][0]["content"] = [
                {"type": "text", "text": "What is the background color of this image? Reply briefly."},
                {"type": "image_url", "image_url": {"url": _probe_image()}},
            ]
        elif capability == "tools":
            payload["messages"][0]["content"] = 'Call piap_probe with value="piap". Do not answer in prose.'
            payload["tools"] = [{"type": "function", "function": {
                "name": "piap_probe", "description": "A connection test; no action is executed.",
                "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
            }}]
            # Exercise the same auto selection used by the application's Agent.
            payload["tool_choice"] = "auto"
        elif capability != "text":
            raise ValueError("unsupported capability")
        return "/chat/completions", payload

    @staticmethod
    def _validate(data: Any, capability: str) -> str:
        if not isinstance(data, dict):
            raise ValueError("expected JSON object")
        if capability == "embedding":
            vector = data["data"][0]["embedding"]
            if not isinstance(vector, list) or not vector or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vector
            ):
                raise ValueError("missing finite embedding vector")
            return f"向量接口通过，维度 {len(vector)}；切换向量模型前仍需迁移已有索引"
        message = data["choices"][0]["message"]
        if not isinstance(message, dict):
            raise ValueError("expected message object")
        if capability == "tools":
            calls = message.get("tool_calls") or []
            if not isinstance(calls, list):
                raise ValueError("expected tool call array")
            for call in calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or {}
                if not isinstance(function, dict):
                    continue
                args = function.get("arguments")
                args = json.loads(args) if isinstance(args, str) else args
                if function.get("name") == "piap_probe" and args == {"value": "piap"}:
                    return "工具调用格式及参数通过；未执行任何业务工具"
            raise ValueError("expected tool call was not returned")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("missing generated text")
        if capability == "json":
            if json.loads(content) != {"ok": True}:
                raise ValueError("expected JSON object was not returned")
            return "JSON 输出格式通过"
        if capability == "vision":
            return "图片输入及文字响应通过；不代表业务识别准确率已验收"
        return "文字生成通过"
