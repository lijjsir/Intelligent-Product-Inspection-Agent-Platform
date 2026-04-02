from __future__ import annotations

from datetime import datetime

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.services.rag_space_service import RagSpaceService


class FakeSpace:
    def __init__(self, *, rag_space_id: str, org_id: str, created_by: str | None):
        self.id = rag_space_id
        self.org_id = org_id
        self.created_by = created_by
        self.name = "My Space"
        self.description = "private docs"
        self.status = "ready"
        self.file_count = 1
        self.selected_count = 0
        self.created_at = datetime(2026, 4, 2, 10, 0, 0)
        self.updated_at = datetime(2026, 4, 2, 10, 5, 0)
        self.files = []


class FakeFile:
    def __init__(self, *, rag_space_id: str, org_id: str):
        self.id = "file-1"
        self.rag_space_id = rag_space_id
        self.org_id = org_id
        self.file_name = "spec.txt"
        self.content_type = "text/plain"
        self.file_url = "https://example.com/spec.txt"
        self.size_bytes = 128
        self.status = "ready"
        self.created_at = datetime(2026, 4, 2, 10, 10, 0)


class FakeSpaceRepo:
    def __init__(self):
        self.list_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.increment_calls: list[dict[str, object]] = []
        self.deleted_space_ids: list[str] = []
        self.file_counts: dict[str, int] = {"space-1": 1}

    async def create(self, **kwargs):
        return FakeSpace(
            rag_space_id="space-1",
            org_id=str(kwargs["org_id"]),
            created_by=str(kwargs.get("created_by") or ""),
        )

    async def list_for_org(self, *, org_id: str, owner_user_id: str | None = None, limit: int = 200):
        self.list_calls.append(
            {
                "org_id": org_id,
                "owner_user_id": owner_user_id,
                "limit": limit,
            }
        )
        return [FakeSpace(rag_space_id="space-1", org_id=org_id, created_by=owner_user_id)]

    async def get(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.get_calls.append(
            {
                "org_id": org_id,
                "rag_space_id": rag_space_id,
                "owner_user_id": owner_user_id,
            }
        )
        if rag_space_id == "foreign-space":
            return None
        space = FakeSpace(rag_space_id=rag_space_id, org_id=org_id, created_by=owner_user_id)
        space.file_count = self.file_counts.get(rag_space_id, space.file_count)
        return space

    async def increment_selected_count(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.increment_calls.append(
            {
                "org_id": org_id,
                "rag_space_id": rag_space_id,
                "owner_user_id": owner_user_id,
            }
        )

    async def recalculate_file_count(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.file_counts[rag_space_id] = 0
        return None

    async def soft_delete(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.deleted_space_ids.append(rag_space_id)
        return FakeSpace(rag_space_id=rag_space_id, org_id=org_id, created_by=owner_user_id)


class FakeFileRepo:
    def __init__(self):
        self.list_calls: list[dict[str, object]] = []
        self.deleted_file_ids: list[str] = []
        self.rows: list[FakeFile] = [FakeFile(rag_space_id="space-1", org_id="org-1")]

    async def list_for_space(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        owner_user_id: str | None = None,
        limit: int = 200,
    ):
        self.list_calls.append(
            {
                "org_id": org_id,
                "rag_space_id": rag_space_id,
                "owner_user_id": owner_user_id,
                "limit": limit,
            }
        )
        return list(self.rows[:limit])

    async def soft_delete(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        file_id: str,
        owner_user_id: str | None = None,
    ):
        if file_id == "missing":
            return None
        self.deleted_file_ids.append(file_id)
        self.rows = []
        return FakeFile(rag_space_id=rag_space_id, org_id=org_id)


class FakeStorageService:
    def save_bytes(self, **kwargs):
        return {
            "id": "file-storage-1",
            "name": str(kwargs.get("file_name") or "document.bin"),
            "url": "https://example.com/document.bin",
            "content_type": kwargs.get("content_type"),
            "size_bytes": len(kwargs.get("data") or b""),
        }

    def delete_by_url(self, url: str):
        return None


class FakeIndexer:
    async def index(self, docs):
        return {"accepted": len(docs)}

    async def delete_by_filter(self, payload_filter):
        return None


class FakeSession:
    async def commit(self):
        return None


def build_service(monkeypatch):
    space_repo = FakeSpaceRepo()
    file_repo = FakeFileRepo()
    monkeypatch.setattr("app.services.rag_space_service.RagSpaceRepository", lambda session: space_repo)
    monkeypatch.setattr("app.services.rag_space_service.RagSpaceFileRepository", lambda session: file_repo)
    monkeypatch.setattr("app.services.rag_space_service.FileStorageService", lambda: FakeStorageService())
    monkeypatch.setattr("app.services.rag_space_service.KnowledgeIndexer", lambda: FakeIndexer())
    service = RagSpaceService(FakeSession(), org_id="org-1", user_id="user-1")
    return service, space_repo, file_repo


@pytest.mark.asyncio
async def test_list_spaces_uses_current_user_scope(monkeypatch):
    service, space_repo, _ = build_service(monkeypatch)

    rows = await service.list_spaces(limit=20)

    assert space_repo.list_calls == [{"org_id": "org-1", "owner_user_id": "user-1", "limit": 20}]
    assert rows[0].created_by == "user-1"


@pytest.mark.asyncio
async def test_list_documents_uses_current_user_scope(monkeypatch):
    service, _, file_repo = build_service(monkeypatch)

    rows = await service.list_documents(rag_space_id="space-1", limit=30)

    assert file_repo.list_calls == [
        {
            "org_id": "org-1",
            "rag_space_id": "space-1",
            "owner_user_id": "user-1",
            "limit": 30,
        }
    ]
    assert rows[0].rag_space_id == "space-1"


@pytest.mark.asyncio
async def test_note_selected_rejects_foreign_rag_space(monkeypatch):
    service, space_repo, _ = build_service(monkeypatch)

    with pytest.raises(NotFoundError, match="rag space not found"):
        await service.note_selected("foreign-space")

    assert space_repo.increment_calls == []


@pytest.mark.asyncio
async def test_delete_document_uses_current_user_scope(monkeypatch):
    service, space_repo, file_repo = build_service(monkeypatch)

    await service.delete_document(rag_space_id="space-1", file_id="file-1")

    assert file_repo.deleted_file_ids == ["file-1"]
    assert space_repo.deleted_space_ids == ["space-1"]


@pytest.mark.asyncio
async def test_upload_documents_rejects_multiple_files(monkeypatch):
    service, _, _ = build_service(monkeypatch)

    class FakeUpload:
        def __init__(self, filename: str):
            self.filename = filename
            self.content_type = "text/plain"

        async def read(self):
            return b"hello"

    with pytest.raises(ValidationError, match="只允许上传一个文档"):
        await service.upload_documents(
            rag_space_id="space-1",
            files=[FakeUpload("a.txt"), FakeUpload("b.txt")],
        )


def test_build_docs_from_file_includes_user_scope_in_payload(monkeypatch):
    service, _, _ = build_service(monkeypatch)

    docs = service._build_docs_from_file(
        file_name="spec.txt",
        file_url="https://example.com/spec.txt",
        suffix=".txt",
        content="hello world".encode("utf-8"),
        rag_space_id="space-1",
    )

    assert docs[0]["payload"]["org_id"] == "org-1"
    assert docs[0]["payload"]["user_id"] == "user-1"
    assert docs[0]["payload"]["rag_space_id"] == "space-1"
