from __future__ import annotations

from app.core.config import settings
from app.services.object_storage.local import LocalObjectStorage
from app.services.object_storage.minio import MinioObjectStorage


def build_object_storage():
    backend = str(settings.object_storage_backend or "").strip().lower()
    if backend == "minio":
        return MinioObjectStorage(
            endpoint=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        )
    return LocalObjectStorage()
