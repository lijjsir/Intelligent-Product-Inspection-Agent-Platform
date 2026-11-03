"""Small standalone OpenAI-compatible client; no platform or GPU dependencies."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "qwen3.5:9b-q8_0"


def runtime_defaults():
    """Environment overrides machine-local config; neither is committed."""
    config_path = Path(__file__).with_name("config.local.json")
    config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("QDL config.local.json must be a JSON object")
    base_url = os.getenv("QDL_BASE_URL") or config.get("base_url") or DEFAULT_URL
    model = os.getenv("QDL_MODEL") or config.get("model") or DEFAULT_MODEL
    if not isinstance(base_url, str) or not isinstance(model, str):
        raise ValueError("QDL base_url and model must be strings")
    return base_url, model


class OpenAIClient:
    def __init__(self, base_url=DEFAULT_URL, model_name=DEFAULT_MODEL, timeout=180.0):
        url = base_url.rstrip("/")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("Expected an HTTP(S) model API base URL")
        if url.endswith("/chat/completions"):
            self.endpoint = url
        else:
            self.endpoint = url + ("" if parts.path.rstrip("/") else "/v1") + "/chat/completions"
        self.model_name = model_name
        self.timeout = timeout
        # The default endpoint is on the LAN; avoid sending it through a global proxy.
        # Proxy use is an explicit opt-in for other endpoints.
        self.opener = urllib.request.build_opener(
            *([] if os.getenv("QDL_USE_PROXY") == "1" else [urllib.request.ProxyHandler({})])
        )

    def chat(self, prompt, max_tokens=1024, image_path=None, *, json_mode=False, response_schema=None):
        content = [{"type": "text", "text": prompt}]
        if image_path is not None:
            path = Path(image_path)
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if not mime.startswith("image/"):
                raise ValueError(f"Unsupported image extension: {path.suffix}")
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
        headers = {"Content-Type": "application/json"}
        if key := os.getenv("QDL_API_KEY"):
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "reasoning_effort": "none",
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if response_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "qdl_review", "strict": True, "schema": response_schema,
            }}
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Model API HTTP {exc.code}: {exc.read(1000).decode(errors='replace')}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Cannot reach model API {self.endpoint}: {exc}") from exc
        choices = result.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Model API returned no text content")
        if choices[0].get("finish_reason") == "length":
            raise RuntimeError("Model output was truncated; increase --max-new-tokens")
        return text.strip()

    def generate(self, image_path, prompt, max_new_tokens):
        return self.chat(prompt, max_new_tokens, image_path)
