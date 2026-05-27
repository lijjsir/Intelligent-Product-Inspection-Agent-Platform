from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.tools.paper_format_templates import get_paper_template


DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ASSET_DIR = (
    Path(__file__).resolve().parent
    / "assets"
    / "paper_templates"
    / "cqupt"
    / "graduate-thesis"
    / "2022"
)
DEFAULT_COMMENTED_TEMPLATE_PATH = _ASSET_DIR / "word-commented-template.docx"
DEFAULT_WRITING_GUIDE_PATH = _ASSET_DIR / "writing-guide.docx"


def get_cqupt_graduate_template_asset_paths() -> dict[str, Path]:
    return {
        "word_commented_template": DEFAULT_COMMENTED_TEMPLATE_PATH,
        "writing_guide": DEFAULT_WRITING_GUIDE_PATH,
    }


def seed_builtin_paper_templates(*, storage: Any | None = None) -> dict[str, Any]:
    if storage is None:
        from app.services.object_storage.factory import build_object_storage

        storage = build_object_storage()
    return seed_cqupt_graduate_templates(
        storage=storage,
        commented_template_path=DEFAULT_COMMENTED_TEMPLATE_PATH,
        writing_guide_path=DEFAULT_WRITING_GUIDE_PATH,
    )


def seed_cqupt_graduate_templates(
    *,
    storage: Any,
    commented_template_path: str | Path,
    writing_guide_path: str | Path,
) -> dict[str, Any]:
    template = get_paper_template("cqupt_graduate_thesis_2022")
    bucket = str((template.get("storage") or {}).get("bucket") or "paper-templates")
    files = list((template.get("storage") or {}).get("files") or [])
    paths_by_role = {
        "word_commented_template": Path(commented_template_path),
        "writing_guide": Path(writing_guide_path),
    }
    uploaded: list[dict[str, Any]] = []

    for item in files:
        role = str(item.get("role") or "")
        source_path = paths_by_role.get(role)
        if source_path is None:
            continue
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"template file not found: {source_path}")
        object_key = str(item["object_key"])
        content_type = str(item.get("content_type") or DOCX_CONTENT_TYPE)
        if _object_exists(storage, bucket=bucket, object_key=object_key):
            uploaded.append({
                "role": role,
                "file_name": item.get("file_name") or source_path.name,
                "bucket": bucket,
                "object_key": object_key,
                "content_type": content_type,
                "size_bytes": None,
                "url": None,
                "status": "exists",
            })
            continue
        stored = storage.put_bytes(
            bucket=bucket,
            object_key=object_key,
            data=source_path.read_bytes(),
            content_type=content_type,
        )
        uploaded.append({
            "role": role,
            "file_name": item.get("file_name") or source_path.name,
            "bucket": bucket,
            "object_key": object_key,
            "content_type": content_type,
            "size_bytes": stored.get("size_bytes"),
            "url": stored.get("url"),
            "status": "uploaded",
        })

    return {
        "template_id": template["template_id"],
        "template_name": template["name"],
        "bucket": bucket,
        "files": uploaded,
    }


def _object_exists(storage: Any, *, bucket: str, object_key: str) -> bool:
    exists = getattr(storage, "object_exists", None)
    if callable(exists):
        try:
            return bool(exists(bucket=bucket, object_key=object_key))
        except Exception:
            return False
    get_bytes = getattr(storage, "get_bytes", None)
    if callable(get_bytes):
        try:
            return get_bytes(bucket=bucket, object_key=object_key) is not None
        except Exception:
            return False
    return False
