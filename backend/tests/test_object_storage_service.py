from __future__ import annotations


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
