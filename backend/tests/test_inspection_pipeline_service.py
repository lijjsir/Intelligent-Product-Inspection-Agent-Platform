from app.services.inspection_pipeline_service import _normalize_image_urls_for_runtime


def test_normalize_image_urls_for_runtime_keeps_remote_and_data_urls(monkeypatch):
    calls: list[str] = []

    class FakeStorageService:
        def to_data_url(self, url: str) -> str | None:
            calls.append(url)
            return None

    monkeypatch.setattr(
        "app.services.inspection_pipeline_service.FileStorageService",
        lambda: FakeStorageService(),
    )

    normalized = _normalize_image_urls_for_runtime(
        [
            "https://example.com/demo.png",
            "http://example.com/demo.png",
            "data:image/png;base64,abc123",
        ]
    )

    assert normalized == [
        "https://example.com/demo.png",
        "http://example.com/demo.png",
        "data:image/png;base64,abc123",
    ]
    assert calls == []


def test_normalize_image_urls_for_runtime_converts_local_upload_urls(monkeypatch):
    calls: list[str] = []

    class FakeStorageService:
        def to_data_url(self, url: str) -> str | None:
            calls.append(url)
            if url == "/uploads/chat_attachments/demo.png":
                return "data:image/png;base64,ZmFrZQ=="
            return None

    monkeypatch.setattr(
        "app.services.inspection_pipeline_service.FileStorageService",
        lambda: FakeStorageService(),
    )

    normalized = _normalize_image_urls_for_runtime(
        [
            "/uploads/chat_attachments/demo.png",
            "/uploads/chat_attachments/missing.png",
        ]
    )

    assert normalized == [
        "data:image/png;base64,ZmFrZQ==",
        "/uploads/chat_attachments/missing.png",
    ]
    assert calls == [
        "/uploads/chat_attachments/demo.png",
        "/uploads/chat_attachments/missing.png",
    ]
