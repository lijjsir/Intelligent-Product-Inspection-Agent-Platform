"""Load template-side evidence used by the paper review model.

Reads the writing guide file from object storage. If files are not found,
returns an error dict that propagates to the frontend.
"""

from __future__ import annotations

from typing import Any

from agent.tools.file_parsers import parse_file_content
from agent.tools.paper_format_templates import get_paper_template


def load_writing_guide_evidence(
    template_id: str | None,
    *,
    max_chars: int = 12000,
) -> dict[str, Any] | None:
    template = get_paper_template(template_id)
    if template is None:
        return None

    storage = dict(template.get("storage") or {})
    bucket = str(storage.get("bucket") or "").strip()
    guide = _template_file_by_role(template, "writing_guide")
    # No storage configured at all → return None (not an error; template doesn't need guide files)
    if not storage or not bucket:
        return None
    # Storage configured but writing_guide role not found in files list
    if not guide:
        return _error_result(template, template_id, "模板存储配置中缺少 writing_guide 文件定义")

    object_key = str(guide.get("object_key") or "").strip()
    file_name = str(guide.get("file_name") or "writing-guide.docx")
    if not object_key:
        return _error_result(template, template_id, "模板缺少 object_key")

    try:
        from app.services.object_storage.factory import build_object_storage

        payload = build_object_storage().get_bytes(bucket=bucket, object_key=object_key)
    except Exception as exc:
        return _error_result(template, template_id, f"对象存储读取失败：{exc}")

    if payload is None:
        return _error_result(
            template,
            template_id,
            f"MinIO 中未找到文件：{file_name}（bucket={bucket}, key={object_key}）。请先将模板文件导入对象存储。",
        )

    content, content_type = payload
    try:
        parsed = parse_file_content(file_name, content)
    except Exception as exc:
        return _error_result(template, template_id, f"模板文件解析失败：{exc}")

    text = str(parsed.get("text") or "").strip()
    if not text:
        return _error_result(template, template_id, f"模板文件 {file_name} 解析后无文本内容")

    return {
        "template_id": str(template.get("template_id") or template_id or ""),
        "template_name": str(template.get("name") or ""),
        "source": "object_storage",
        "role": "writing_guide",
        "file_name": file_name,
        "bucket": bucket,
        "object_key": object_key,
        "content_type": content_type or guide.get("content_type"),
        "document_type": str(parsed.get("kind") or ""),
        "text": text[:max_chars],
        "summary": _summarize(text),
    }


def _error_result(template: dict[str, Any], template_id: str | None, message: str) -> dict[str, Any]:
    return {
        "template_id": str(template.get("template_id") or template_id or ""),
        "template_name": str(template.get("name") or ""),
        "source": "error",
        "role": "writing_guide",
        "error": True,
        "error_message": message,
    }


def _template_file_by_role(template: dict[str, Any], role: str) -> dict[str, Any] | None:
    for item in list((template.get("storage") or {}).get("files") or []):
        if str(item.get("role") or "") == role:
            return dict(item)
    return None


def _summarize(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    return cleaned[:500] + ("..." if len(cleaned) > 500 else "")
