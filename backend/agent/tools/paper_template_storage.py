from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.tools.paper_format_templates import get_paper_template

logger = logging.getLogger(__name__)

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
    """Upload built-in template files to MinIO. Idempotent — skips existing files."""
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


async def ensure_paper_templates_ready(
    *,
    org_id: str | None = None,
    force_index: bool = False,
) -> dict[str, Any]:
    """Ensure template files are in MinIO and indexed in MySQL + Qdrant.

    This is the single entry point for bootstrap. It is fully idempotent:
    - MinIO: skips if file already exists
    - MySQL: skips if template already has clauses
    - Qdrant: upsert by point id

    Called on app startup. Safe to call repeatedly.
    """
    from app.services.object_storage.factory import build_object_storage
    from app.services.paper_template_index_service import PaperTemplateIndexService
    from infra.database.session import get_session

    # 1. Ensure MinIO has the files (idempotent)
    storage = build_object_storage()
    seed_result = seed_builtin_paper_templates(storage=storage)
    logger.info(
        "MinIO seed: template_id=%s files=%s",
        seed_result["template_id"],
        [(f["role"], f["status"]) for f in seed_result["files"]],
    )

    # 2. Ensure MySQL + Qdrant have the clause index (idempotent)
    template = get_paper_template("cqupt_graduate_thesis_2022")
    template_id = str(template["template_id"])

    writing_guide_role = _template_file_by_role(template, "writing_guide")
    if writing_guide_role is None:
        logger.warning("No writing_guide file defined for template %s", template_id)
        return {**seed_result, "index_status": "skipped", "reason": "no writing_guide role"}

    guide_path = DEFAULT_WRITING_GUIDE_PATH
    if not guide_path.exists():
        logger.warning("Writing guide file not found: %s", guide_path)
        return {**seed_result, "index_status": "skipped", "reason": "file not found"}

    async with get_session() as session:
        try:
            index_service = PaperTemplateIndexService(session, org_id=org_id)

            if not force_index and await index_service.is_indexed(template_id=template_id):
                logger.info("Template %s already indexed in MySQL, skipping", template_id)
                return {**seed_result, "index_status": "already_indexed"}

            index_result = await index_service.index_template(
                template_id=template_id,
                template_name=str(template.get("name") or "CQUPT Graduate Thesis 2022"),
                guide_file_bytes=guide_path.read_bytes(),
                guide_file_name=guide_path.name,
                school_name="重庆邮电大学",
                degree_type="硕士",
                version=str(template.get("version") or "V2.0"),
                description=str(template.get("description") or ""),
                force=force_index,
            )
            await session.commit()
            logger.info("Template index result: %s", index_result)
            return {**seed_result, "index_status": index_result["status"], "clause_count": index_result.get("clause_count", 0)}
        except Exception as exc:
            await session.rollback()
            logger.exception("Failed to index template %s: %s", template_id, exc)
            return {**seed_result, "index_status": "failed", "error": str(exc)}


def _template_file_by_role(template: dict[str, Any], role: str) -> dict[str, Any] | None:
    for item in list((template.get("storage") or {}).get("files") or []):
        if str(item.get("role") or "") == role:
            return dict(item)
    return None


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
