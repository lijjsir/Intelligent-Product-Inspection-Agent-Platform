from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlparse

from app.services.object_storage.factory import build_object_storage


def read_attachment_bytes(attachment: dict[str, Any]) -> tuple[bytes, str | None] | None:
    bucket = str(attachment.get("bucket") or "")
    object_key = str(attachment.get("object_key") or "")
    if not bucket or not object_key:
        return None
    return build_object_storage().get_bytes(bucket=bucket, object_key=object_key)


def attachment_to_data_url(attachment: dict[str, Any]) -> str | None:
    bucket = str(attachment.get("bucket") or "")
    object_key = str(attachment.get("object_key") or "")
    if not bucket or not object_key:
        return None
    result = build_object_storage().get_bytes(bucket=bucket, object_key=object_key)
    if result is None:
        return None
    content, content_type = result
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{content_type or 'application/octet-stream'};base64,{encoded}"


def attachment_ref_from_url(url: str) -> dict[str, str] | None:
    """Extract the protected file route's storage identity from a task URL."""
    raw = str(url or "").strip()
    if not raw:
        return None
    path = urlparse(raw).path if "://" in raw else raw.split("?", 1)[0]
    for prefix in ("/api/v1/files/", "/api/v1/chat/files/"):
        if not path.startswith(prefix):
            continue
        suffix = path[len(prefix):].strip("/")
        parts = suffix.split("/", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return {"bucket": parts[0], "object_key": parts[1]}
    return None


def url_to_data_url(url: str) -> str | None:
    """Read a protected API file URL from object storage and return a model-safe data URL."""
    ref = attachment_ref_from_url(url)
    if not ref:
        return None
    return attachment_to_data_url(ref)
