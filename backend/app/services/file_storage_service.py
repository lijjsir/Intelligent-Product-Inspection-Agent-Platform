from __future__ import annotations

import mimetypes
import os
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
