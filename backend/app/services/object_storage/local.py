from __future__ import annotations

from app.core.config import settings
from app.services.file_storage_service import FileStorageService


class LocalObjectStorage:
    backend_name = "local"

    def __init__(self, storage: FileStorageService | None = None):
        self._storage = storage or FileStorageService()

    def put_bytes(self, *, bucket: str, object_key: str, data: bytes, content_type: str | None = None) -> dict:
        stored = self._storage.save_bytes(
            category=object_key.rsplit("/", 1)[0] if "/" in object_key else bucket,
            file_name=object_key.rsplit("/", 1)[-1],
            data=data,
            content_type=content_type,
        )
        return {
            "bucket": bucket,
            "object_key": object_key,
            "url": stored["url"],
            "content_type": stored["content_type"],
            "size_bytes": stored["size_bytes"],
        }

    def get_bytes(self, *, bucket: str, object_key: str) -> tuple[bytes, str | None] | None:
        return self._storage.file_bytes_from_url(
            f"{settings.local_upload_url_prefix.rstrip('/')}/{object_key.lstrip('/')}"
        )

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        self._storage.delete_by_url(f"{settings.local_upload_url_prefix.rstrip('/')}/{object_key.lstrip('/')}")

    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
        return f"{settings.local_upload_url_prefix.rstrip('/')}/{object_key.lstrip('/')}"

    def ensure_bucket(self, bucket: str) -> None:
        return None

    def bucket_exists(self, bucket: str) -> bool:
        return True
