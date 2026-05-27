from __future__ import annotations

from typing import Any, Protocol


class ObjectStorage(Protocol):
    backend_name: str

    def put_bytes(
        self,
        *,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        ...

    def get_bytes(self, *, bucket: str, object_key: str) -> tuple[bytes, str | None] | None:
        ...

    def object_exists(self, *, bucket: str, object_key: str) -> bool:
        ...

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        ...

    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
        ...

    def ensure_bucket(self, bucket: str) -> None:
        ...
