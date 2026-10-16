from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.services.object_storage.factory import build_object_storage
from app.api.v1.deps import get_db, get_current_user, get_permission_identity
from app.core.config import settings
from app.services.export_job_service import ExportJobService
from sqlalchemy import select
from app.models.rag_space import RagDocument
from app.repositories.rag_space_repo import RagSpaceRepository
from app.core.exceptions import NotFoundError
from app.core.permissions import require_role

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{bucket}/{object_key:path}")
async def serve_file(bucket: str, object_key: str, authorization: str = Header(default=""), db=Depends(get_db)):
    if bucket == "quality-data":
        raise HTTPException(status_code=404, detail="请使用鉴权的质量资料附件接口")
    parts = object_key.split("/")
    rag_file=(await db.execute(select(RagDocument).where(RagDocument.bucket==bucket,RagDocument.object_key==object_key).limit(1))).scalar_one_or_none() if bucket==settings.rag_storage_bucket else None
    if rag_file:
        identity=await get_permission_identity(authorization=authorization,token="",db=db)
        current=get_current_user(authorization=authorization,identity=identity)
        space=await RagSpaceRepository(db).get(org_id=current.org_id,rag_space_id=rag_file.rag_space_id,
            owner_user_id=current.user_id,include_system=True)
        if not space or rag_file.org_id!=current.org_id or rag_file.deleted_at:
            raise NotFoundError("资料文件不在当前授权范围")
        if space.resource_domain=="formal_standard":require_role("inspection_standard_library_read",current.role)
    if bucket == settings.report_export_bucket:
        identity = await get_permission_identity(authorization=authorization, token="", db=db)
        current = get_current_user(authorization=authorization, identity=identity)
        if len(parts) != 3 or not parts[-1].startswith("report."):
            raise HTTPException(status_code=404, detail="report file not available")
        job = await ExportJobService(db, current.org_id, actor_user_id=current.user_id, actor_role=current.role).get_detail(parts[1])
        from app.core.datetime import utcnow
        if job.expires_at and job.expires_at<utcnow():raise HTTPException(status_code=404,detail='report expired')
        if job.file_url != f"/api/v1/files/{bucket}/{object_key}" or job.status != "success":
            raise HTTPException(status_code=404, detail="report file not available")
    result = build_object_storage().get_bytes(bucket=bucket, object_key=object_key)
    if result is None:
        raise HTTPException(status_code=404, detail="file not found")
    content, content_type = result
    return StreamingResponse(BytesIO(content), media_type=content_type or "application/octet-stream")
