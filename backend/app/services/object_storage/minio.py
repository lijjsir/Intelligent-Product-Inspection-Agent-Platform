from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio


class MinioObjectStorage:
    backend_name = "minio"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool | None = None,
        client: Minio | None = None,
    ):
        parsed = urlparse(endpoint)
        resolved_secure = parsed.scheme == "https" if secure is None else bool(secure)
        host = parsed.netloc or parsed.path
        self._endpoint = endpoint.rstrip("/")
        self._client = client or Minio(
            host,
            access_key=access_key,
            secret_key=secret_key,
            secure=resolved_secure,
        )

    def put_bytes(self, *, bucket: str, object_key: str, data: bytes, content_type: str | None = None) -> dict:
        self.ensure_bucket(bucket)
        payload = BytesIO(data)
        self._client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=payload,
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )
        return {
            "bucket": bucket,
            "object_key": object_key,
            "url": f"{self._endpoint}/{bucket}/{object_key}",
            "content_type": content_type or "application/octet-stream",
            "size_bytes": len(data),
        }

    def get_bytes(self, *, bucket: str, object_key: str) -> tuple[bytes, str | None] | None:
        response = self._client.get_object(bucket, object_key)
        try:
            content = response.read()
            content_type = None
            headers = getattr(response, "headers", None)
            if headers is not None:
                content_type = headers.get("Content-Type")
            return content, content_type
        finally:
            try:
                response.close()
            finally:
                response.release_conn()

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        self._client.remove_object(bucket, object_key)

    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
        return self._client.presigned_get_object(
            bucket,
            object_key,
            expires=timedelta(seconds=expires_seconds),
        )

    def ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def bucket_exists(self, bucket: str) -> bool:
        return self._client.bucket_exists(bucket)
