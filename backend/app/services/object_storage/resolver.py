from __future__ import annotations

import base64
from typing import Any

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
