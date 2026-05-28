from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.object_storage.factory import build_object_storage


router = APIRouter()


@router.get("/{bucket}/{object_key:path}")
async def serve_file(bucket: str, object_key: str):
    result = build_object_storage().get_bytes(bucket=bucket, object_key=object_key)
    if result is None:
        raise HTTPException(status_code=404, detail="file not found")
    content, content_type = result
    return StreamingResponse(BytesIO(content), media_type=content_type or "application/octet-stream")
