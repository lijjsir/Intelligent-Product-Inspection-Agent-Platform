from __future__ import annotations

import mimetypes

from app.core.config import settings
from app.services.file_storage_service import FileStorageService


class LocalObjectStorage:
    backend_name = "local"

    def __init__(self, storage: FileStorageService | None = None):
        self._storage = storage or FileStorageService()

    def put_bytes(self, *, bucket: str, object_key: str, data: bytes, content_type: str | None = None) -> dict:
        stored = self._storage.save_bytes_at_relative_path(
            relative_path=object_key,
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

    def object_exists(self, *, bucket: str, object_key: str) -> bool:
        cleaned = object_key.strip().lstrip("/").replace("\\", "/")
        if not cleaned:
            return False
        target = (self._storage.root / cleaned).resolve()
        root = self._storage.root.resolve()
        return str(target).startswith(str(root)) and target.exists() and target.is_file()

    def get_bytes_from_legacy_prefix(self, *, object_key_prefix: str, suffix: str | None = None) -> tuple[bytes, str | None] | None:
        prefix = object_key_prefix.strip().strip("/")
        if not prefix:
            return None
        target_dir = (self._storage.root / prefix).resolve()
        root = self._storage.root.resolve()
        if not str(target_dir).startswith(str(root)) or not target_dir.exists() or not target_dir.is_dir():
            return None
        candidates = sorted(path for path in target_dir.iterdir() if path.is_file())
        if suffix:
            suffix_matches = [path for path in candidates if path.name.endswith(suffix)]
            if suffix_matches:
                candidates = suffix_matches
        for path in candidates:
            resolved_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return path.read_bytes(), resolved_type
        return None

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        self._storage.delete_by_url(f"{settings.local_upload_url_prefix.rstrip('/')}/{object_key.lstrip('/')}")

    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
        return f"{settings.local_upload_url_prefix.rstrip('/')}/{object_key.lstrip('/')}"

    def ensure_bucket(self, bucket: str) -> None:
        return None

    def bucket_exists(self, bucket: str) -> bool:
        return True
