from __future__ import annotations

import mimetypes
import os
import base64
from urllib.parse import urlparse
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


class FileStorageService:
    def __init__(self) -> None:
        root = Path(settings.local_upload_dir)
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[2] / root
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def save_bytes(self, *, category: str, file_name: str, data: bytes, content_type: str | None = None) -> dict:
        safe_name = Path(file_name).name or "file.bin"
        suffix = Path(safe_name).suffix
        stored_name = f"{uuid4().hex}{suffix}"
        category_dir = self._root / category
        category_dir.mkdir(parents=True, exist_ok=True)
        target = category_dir / stored_name
        target.write_bytes(data)
        resolved_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        rel_path = target.relative_to(self._root).as_posix()
        return {
            "id": uuid4().hex,
            "name": safe_name,
            "stored_name": stored_name,
            "path": str(target),
            "relative_path": rel_path,
            "url": f"{settings.local_upload_url_prefix.rstrip('/')}/{rel_path}",
            "content_type": resolved_type,
            "size_bytes": os.path.getsize(target),
        }

    def save_bytes_at_relative_path(self, *, relative_path: str, data: bytes, content_type: str | None = None) -> dict:
        cleaned = relative_path.strip().lstrip("/").replace("\\", "/")
        if not cleaned:
            cleaned = uuid4().hex
        target = (self._root / cleaned).resolve()
        root = self._root.resolve()
        if not str(target).startswith(str(root)):
            raise ValueError("invalid relative path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        resolved_type = content_type or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        rel_path = target.relative_to(self._root).as_posix()
        return {
            "id": uuid4().hex,
            "name": target.name,
            "stored_name": target.name,
            "path": str(target),
            "relative_path": rel_path,
            "url": f"{settings.local_upload_url_prefix.rstrip('/')}/{rel_path}",
            "content_type": resolved_type,
            "size_bytes": os.path.getsize(target),
        }

    def delete_relative_path(self, relative_path: str) -> None:
        if not relative_path:
            return
        target = (self._root / relative_path).resolve()
        root = self._root.resolve()
        if not str(target).startswith(str(root)):
            return
        if target.exists() and target.is_file():
            target.unlink()

    def delete_by_url(self, url: str) -> None:
        prefix = settings.local_upload_url_prefix.rstrip("/")
        path = url
        if "://" in url:
            path = urlparse(url).path or ""
        if not path.startswith(prefix):
            return
        relative_path = path[len(prefix) :].lstrip("/").replace("/", os.sep)
        self.delete_relative_path(relative_path)

    def file_bytes_from_url(self, url: str) -> tuple[bytes, str] | None:
        prefix = settings.local_upload_url_prefix.rstrip("/")
        path = url
        if "://" in url:
            path = urlparse(url).path or ""
        api_prefix = "/api/v1/files/"
        if path.startswith(api_prefix):
            suffix = path[len(api_prefix) :].strip("/")
            parts = suffix.split("/", 1)
            if len(parts) == 2:
                _bucket, object_key = parts
                local_url = f"{prefix}/{object_key.lstrip('/')}"
                return self.file_bytes_from_url(local_url)
        if not path.startswith(prefix):
            return None
        relative_path = path[len(prefix) :].lstrip("/").replace("/", os.sep)
        target = (self._root / relative_path).resolve()
        root = self._root.resolve()
        if not str(target).startswith(str(root)) or not target.exists() or not target.is_file():
            return None
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return target.read_bytes(), content_type

    def to_data_url(self, url: str) -> str | None:
        payload = self.file_bytes_from_url(url)
        if payload is None:
            return None
        content, content_type = payload
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"
