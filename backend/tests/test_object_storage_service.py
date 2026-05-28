from __future__ import annotations

from datetime import timedelta
from pathlib import Path


def test_object_storage_factory_uses_minio_backend(monkeypatch):
    monkeypatch.setenv("PIAP_OBJECT_STORAGE_BACKEND", "minio")

    from app.core.config import settings
    from app.services.object_storage.factory import build_object_storage

    monkeypatch.setattr(settings, "object_storage_backend", "minio")
    service = build_object_storage()

    assert service.backend_name == "minio"


def test_minio_storage_returns_bucket_and_object_key():
    from app.services.object_storage.minio import MinioObjectStorage

    class FakeClient:
        def bucket_exists(self, _bucket: str) -> bool:
            return True

        def make_bucket(self, _bucket: str) -> None:
            raise AssertionError("bucket should already exist")

        def put_object(self, bucket_name: str, object_name: str, data, length: int, content_type: str | None = None):
            return {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "length": length,
                "content_type": content_type,
                "peek": data.read(),
            }

    service = MinioObjectStorage(
        endpoint="http://minio:9000",
        access_key="minio",
        secret_key="miniopass",
        secure=False,
        client=FakeClient(),
    )

    payload = service.put_bytes(
        bucket="rag-docs",
        object_key="rag/org-1/space-1/spec.txt",
        data=b"hello",
        content_type="text/plain",
    )

    assert payload["bucket"] == "rag-docs"
    assert payload["object_key"] == "rag/org-1/space-1/spec.txt"
    assert payload["size_bytes"] == 5


def test_minio_presign_converts_expiry_seconds_to_timedelta():
    from app.services.object_storage.minio import MinioObjectStorage

    class FakeClient:
        def presigned_get_object(self, bucket: str, object_key: str, *, expires):
            assert bucket == "dataset-samples"
            assert object_key == "datasets/org-1/ds-1/sample.png"
            assert isinstance(expires, timedelta)
            assert expires.total_seconds() == 900
            return "http://minio/download/sample.png"

    service = MinioObjectStorage(
        endpoint="http://minio:9000",
        access_key="minio",
        secret_key="miniopass",
        secure=False,
        client=FakeClient(),
    )

    assert (
        service.presign_download_url(
            bucket="dataset-samples",
            object_key="datasets/org-1/ds-1/sample.png",
            expires_seconds=900,
        )
        == "http://minio/download/sample.png"
    )


def test_local_storage_put_and_get_bytes_by_object_key(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services.file_storage_service import FileStorageService
    from app.services.object_storage.local import LocalObjectStorage

    monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "local_upload_url_prefix", "/uploads")

    storage = LocalObjectStorage(FileStorageService())
    storage.put_bytes(
        bucket="dataset-exports",
        object_key="dataset-exports/org-1/ds-1/export-1/annotations.coco.json",
        data=b'{"format":"coco"}',
        content_type="application/json",
    )

    payload = storage.get_bytes(
        bucket="dataset-exports",
        object_key="dataset-exports/org-1/ds-1/export-1/annotations.coco.json",
    )

    assert payload == (b'{"format":"coco"}', "application/json")
    assert (Path(tmp_path) / "dataset-exports/org-1/ds-1/export-1/annotations.coco.json").exists()
