from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from agent.rag.embedder import EmbeddingModelNotConfigured
from app.core.exceptions import NotFoundError, ValidationError
from app.services.rag_space_service import RagSpaceService


@dataclass
class FakeSpace:
    id: str
    org_id: str
    created_by: str | None
    name: str = "My Space"
    description: str | None = "private docs"
    status: str = "ready"
    file_count: int = 0
    folder_count: int = 0
    chunk_count: int = 0
    index_status: str = "ready"
    selected_count: int = 0
    created_at: datetime = datetime(2026, 4, 2, 10, 0, 0)
    updated_at: datetime = datetime(2026, 4, 2, 10, 5, 0)
    deleted_at: datetime | None = None


@dataclass
class FakeNode:
    id: str
    org_id: str
    rag_space_id: str
    parent_id: str | None
    created_by: str | None
    node_type: str
    name: str
    full_path: str
    depth: int
    sort_order: int = 0
    status: str = "ready"
    children_count: int = 0
    created_at: datetime = datetime(2026, 4, 2, 10, 10, 0)
    updated_at: datetime = datetime(2026, 4, 2, 10, 10, 0)
    deleted_at: datetime | None = None


@dataclass
class FakeDocument:
    id: str
    org_id: str
    rag_space_id: str
    node_id: str
    file_name: str
    file_url: str
    uploaded_by: str | None = "user-1"
    content_type: str | None = "text/plain"
    size_bytes: int = 128
    checksum_sha256: str = "abc"
    storage_backend: str = "local"
    object_key: str = "rag/spec.txt"
    parse_status: str = "parsed"
    index_status: str = "ready"
    chunk_count: int = 1
    error_message: str | None = None
    created_at: datetime = datetime(2026, 4, 2, 10, 12, 0)
    updated_at: datetime = datetime(2026, 4, 2, 10, 12, 0)
    deleted_at: datetime | None = None


class FakeSpaceRepo:
    def __init__(self):
        self.list_calls: list[dict[str, object]] = []
        self.increment_calls: list[dict[str, object]] = []
        self.recalculate_calls: list[dict[str, object]] = []
        self.soft_delete_calls: list[dict[str, object]] = []
        self.spaces: dict[str, FakeSpace] = {"space-1": FakeSpace(id="space-1", org_id="org-1", created_by="user-1")}

    async def create(self, **kwargs):
        created = FakeSpace(
            id="space-2",
            org_id=str(kwargs["org_id"]),
            created_by=kwargs.get("created_by"),
            name=str(kwargs["name"]),
            description=kwargs.get("description"),
        )
        self.spaces[created.id] = created
        return created

    async def list_for_org(self, *, org_id: str, owner_user_id: str | None = None, limit: int = 200):
        self.list_calls.append({"org_id": org_id, "owner_user_id": owner_user_id, "limit": limit})
        return list(self.spaces.values())[:limit]

    async def get(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        if rag_space_id == "foreign-space":
            return None
        return self.spaces.get(rag_space_id)

    async def increment_selected_count(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.increment_calls.append({"org_id": org_id, "rag_space_id": rag_space_id, "owner_user_id": owner_user_id})

    async def recalculate_counters(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.recalculate_calls.append({"org_id": org_id, "rag_space_id": rag_space_id, "owner_user_id": owner_user_id})
        return self.spaces.get(rag_space_id)

    async def soft_delete(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.soft_delete_calls.append({"org_id": org_id, "rag_space_id": rag_space_id, "owner_user_id": owner_user_id})
        obj = self.spaces.get(rag_space_id)
        if obj is not None:
            obj.deleted_at = datetime.utcnow()
        return obj


class FakeNodeRepo:
    def __init__(self):
        self.nodes: list[FakeNode] = [
            FakeNode(
                id="folder-1",
                org_id="org-1",
                rag_space_id="space-1",
                parent_id=None,
                created_by="user-1",
                node_type="folder",
                name="机械",
                full_path="机械",
                depth=0,
                children_count=1,
            ),
            FakeNode(
                id="file-node-1",
                org_id="org-1",
                rag_space_id="space-1",
                parent_id="folder-1",
                created_by="user-1",
                node_type="file",
                name="spec.txt",
                full_path="机械/spec.txt",
                depth=1,
            ),
        ]
        self.created_nodes: list[FakeNode] = []
        self.deleted_node_ids: list[str] = []
        self.children_recalculated = 0

    async def create(self, **kwargs):
        node = FakeNode(id=f"node-{len(self.nodes) + 1}", **kwargs)
        self.nodes.append(node)
        self.created_nodes.append(node)
        return node

    async def get(self, *, org_id: str, rag_space_id: str, node_id: str, owner_user_id: str | None = None):
        return next(
            (
                node
                for node in self.nodes
                if node.id == node_id and node.org_id == org_id and node.rag_space_id == rag_space_id and node.deleted_at is None
            ),
            None,
        )

    async def list_for_space(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        return [node for node in self.nodes if node.org_id == org_id and node.rag_space_id == rag_space_id and node.deleted_at is None]

    async def list_children(self, *, org_id: str, rag_space_id: str, parent_id: str | None, owner_user_id: str | None = None):
        return [
            node
            for node in self.nodes
            if node.org_id == org_id and node.rag_space_id == rag_space_id and node.parent_id == parent_id and node.deleted_at is None
        ]

    async def find_sibling(self, *, org_id: str, rag_space_id: str, parent_id: str | None, name: str, owner_user_id: str | None = None):
        normalized = name.lower()
        return next(
            (
                node
                for node in self.nodes
                if node.org_id == org_id
                and node.rag_space_id == rag_space_id
                and node.parent_id == parent_id
                and node.deleted_at is None
                and node.name.lower() == normalized
            ),
            None,
        )

    async def recalculate_children_counts(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        self.children_recalculated += 1
        active = [node for node in self.nodes if node.org_id == org_id and node.rag_space_id == rag_space_id and node.deleted_at is None]
        for node in active:
            node.children_count = sum(1 for child in active if child.parent_id == node.id)

    async def soft_delete_many(self, *, node_ids: list[str]):
        self.deleted_node_ids.extend(node_ids)
        for node in self.nodes:
            if node.id in node_ids:
                node.deleted_at = datetime.utcnow()


class FakeDocumentRepo:
    def __init__(self):
        self.documents: list[FakeDocument] = [
            FakeDocument(id="doc-1", org_id="org-1", rag_space_id="space-1", node_id="file-node-1", file_name="spec.txt", file_url="https://example.com/spec.txt")
        ]
        self.created_documents: list[FakeDocument] = []
        self.deleted_document_ids: list[str] = []

    async def create(self, **kwargs):
        document = FakeDocument(id=f"doc-{len(self.documents) + 1}", **kwargs)
        self.documents.append(document)
        self.created_documents.append(document)
        return document

    async def list_for_space(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None, limit: int = 1000):
        return [doc for doc in self.documents if doc.org_id == org_id and doc.rag_space_id == rag_space_id and doc.deleted_at is None][:limit]

    async def get(self, *, org_id: str, rag_space_id: str, document_id: str, owner_user_id: str | None = None):
        return next(
            (
                doc
                for doc in self.documents
                if doc.id == document_id and doc.org_id == org_id and doc.rag_space_id == rag_space_id and doc.deleted_at is None
            ),
            None,
        )

    async def get_by_node_id(self, *, org_id: str, rag_space_id: str, node_id: str, owner_user_id: str | None = None):
        return next(
            (
                doc
                for doc in self.documents
                if doc.node_id == node_id and doc.org_id == org_id and doc.rag_space_id == rag_space_id and doc.deleted_at is None
            ),
            None,
        )

    async def list_for_node_ids(self, *, org_id: str, rag_space_id: str, node_ids: list[str], owner_user_id: str | None = None):
        return [
            doc
            for doc in self.documents
            if doc.org_id == org_id and doc.rag_space_id == rag_space_id and doc.node_id in node_ids and doc.deleted_at is None
        ]

    async def soft_delete_many(self, *, document_ids: list[str]):
        self.deleted_document_ids.extend(document_ids)
        for doc in self.documents:
            if doc.id in document_ids:
                doc.deleted_at = datetime.utcnow()


class FakeStorageService:
    def __init__(self):
        self.deleted_urls: list[str] = []

    def save_bytes(self, **kwargs):
        name = str(kwargs.get("file_name") or "document.bin")
        return {
            "id": "file-storage-1",
            "name": name,
            "url": f"https://example.com/{name}",
            "relative_path": f"rag/{name}",
            "content_type": kwargs.get("content_type"),
            "size_bytes": len(kwargs.get("data") or b""),
        }

    def delete_by_url(self, url: str):
        self.deleted_urls.append(url)


class FakeIndexer:
    def __init__(self):
        self.last_docs = []
        self.deleted_filters = []

    async def index(self, docs):
        self.last_docs = docs
        return {"accepted": len(docs)}

    async def delete_by_filter(self, payload_filter):
        self.deleted_filters.append(payload_filter)


class FakeSession:
    def __init__(self):
        self.commit_count = 0

    async def commit(self):
        self.commit_count += 1


def build_service(monkeypatch):
    session = FakeSession()
    space_repo = FakeSpaceRepo()
    node_repo = FakeNodeRepo()
    document_repo = FakeDocumentRepo()
    storage = FakeStorageService()
    indexer = FakeIndexer()

    monkeypatch.setattr("app.services.rag_space_service.RagSpaceRepository", lambda session: space_repo)
    monkeypatch.setattr("app.services.rag_space_service.RagNodeRepository", lambda session: node_repo)
    monkeypatch.setattr("app.services.rag_space_service.RagDocumentRepository", lambda session: document_repo)
    monkeypatch.setattr("app.services.rag_space_service.FileStorageService", lambda: storage)
    monkeypatch.setattr("app.services.rag_space_service.KnowledgeIndexer", lambda org_id=None: indexer)
    monkeypatch.setattr("app.services.rag_space_service.parse_file_content", lambda *_args, **_kwargs: {"text": "hello world"})
    service = RagSpaceService(session, org_id="org-1", user_id="user-1")
    return service, session, space_repo, node_repo, document_repo, storage, indexer


@pytest.mark.asyncio
async def test_list_spaces_uses_current_user_scope(monkeypatch):
    service, _session, space_repo, *_ = build_service(monkeypatch)

    rows = await service.list_spaces(limit=20)

    assert space_repo.list_calls == [{"org_id": "org-1", "owner_user_id": "user-1", "limit": 20}]
    assert rows[0].created_by == "user-1"


@pytest.mark.asyncio
async def test_get_tree_returns_nested_nodes_and_document(monkeypatch):
    service, *_rest = build_service(monkeypatch)

    tree = await service.get_tree(rag_space_id="space-1")

    assert len(tree) == 1
    assert tree[0].name == "机械"
    assert tree[0].children[0].name == "spec.txt"
    assert tree[0].children[0].document is not None
    assert tree[0].children[0].document.file_name == "spec.txt"


@pytest.mark.asyncio
async def test_create_node_creates_root_folder(monkeypatch):
    service, session, space_repo, node_repo, *_rest = build_service(monkeypatch)

    created = await service.create_node(rag_space_id="space-1", parent_id=None, node_type="folder", name="食品")

    assert created.node_type == "folder"
    assert created.full_path == "食品"
    assert node_repo.created_nodes[-1].name == "食品"
    assert node_repo.children_recalculated == 1
    assert space_repo.recalculate_calls[-1]["rag_space_id"] == "space-1"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_upload_documents_creates_file_node_and_document(monkeypatch):
    service, session, space_repo, node_repo, document_repo, _storage, indexer = build_service(monkeypatch)

    class FakeUpload:
        def __init__(self, filename: str):
            self.filename = filename
            self.content_type = "text/plain"

        async def read(self):
            return b"hello world"

    rows = await service.upload_documents(
        rag_space_id="space-1",
        parent_node_id="folder-1",
        files=[FakeUpload("manual.txt")],
    )

    assert rows[0].node_type == "file"
    assert rows[0].full_path == "机械/manual.txt"
    assert document_repo.created_documents[-1].file_name == "manual.txt"
    assert indexer.last_docs[0]["payload"]["node_id"] == rows[0].id
    assert node_repo.children_recalculated == 1
    assert space_repo.recalculate_calls[-1]["rag_space_id"] == "space-1"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_upload_documents_returns_validation_error_when_embedding_model_missing(monkeypatch):
    service, _session, _space_repo, _node_repo, document_repo, _storage, indexer = build_service(monkeypatch)

    class FakeUpload:
        def __init__(self, filename: str):
            self.filename = filename
            self.content_type = "text/plain"

        async def read(self):
            return b"hello world"

    async def raise_missing_model(_docs):
        raise EmbeddingModelNotConfigured("no active embedding model configured in model config page")

    indexer.index = raise_missing_model

    with pytest.raises(ValidationError, match="embedding"):
        await service.upload_documents(
            rag_space_id="space-1",
            parent_node_id="folder-1",
            files=[FakeUpload("manual.txt")],
        )

    assert document_repo.created_documents[-1].index_status == "indexing"


@pytest.mark.asyncio
async def test_delete_node_cascades_documents_and_index(monkeypatch):
    service, session, space_repo, node_repo, document_repo, storage, indexer = build_service(monkeypatch)

    await service.delete_node(rag_space_id="space-1", node_id="folder-1")

    assert set(node_repo.deleted_node_ids) == {"folder-1", "file-node-1"}
    assert document_repo.deleted_document_ids == ["doc-1"]
    assert storage.deleted_urls == ["https://example.com/spec.txt"]
    assert indexer.deleted_filters == [
        {
            "org_id": "org-1",
            "user_id": "user-1",
            "rag_space_id": "space-1",
            "document_id": "doc-1",
            "node_id": "file-node-1",
        }
    ]
    assert space_repo.recalculate_calls[-1]["rag_space_id"] == "space-1"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_delete_document_resolves_document_id_to_node(monkeypatch):
    service, _session, _space_repo, node_repo, document_repo, _storage, _indexer = build_service(monkeypatch)

    await service.delete_document(rag_space_id="space-1", file_id="doc-1")

    assert "file-node-1" in node_repo.deleted_node_ids
    assert "doc-1" in document_repo.deleted_document_ids


@pytest.mark.asyncio
async def test_update_space_renames_space_and_description(monkeypatch):
    service, session, space_repo, *_rest = build_service(monkeypatch)

    updated = await service.update_space(
        rag_space_id="space-1",
        name="Updated Space",
        description="fresh description",
    )

    assert updated.name == "Updated Space"
    assert updated.description == "fresh description"
    assert space_repo.spaces["space-1"].name == "Updated Space"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_delete_space_cascades_nodes_documents_and_soft_deletes_space(monkeypatch):
    service, session, space_repo, node_repo, document_repo, storage, indexer = build_service(monkeypatch)

    await service.delete_space(rag_space_id="space-1")

    assert space_repo.soft_delete_calls == [{"org_id": "org-1", "rag_space_id": "space-1", "owner_user_id": "user-1"}]
    assert space_repo.spaces["space-1"].deleted_at is not None
    assert set(node_repo.deleted_node_ids) == {"folder-1", "file-node-1"}
    assert document_repo.deleted_document_ids == ["doc-1"]
    assert storage.deleted_urls == ["https://example.com/spec.txt"]
    assert indexer.deleted_filters == [
        {
            "org_id": "org-1",
            "user_id": "user-1",
            "rag_space_id": "space-1",
            "document_id": "doc-1",
            "node_id": "file-node-1",
        }
    ]
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_note_selected_rejects_foreign_rag_space(monkeypatch):
    service, _session, space_repo, *_rest = build_service(monkeypatch)

    with pytest.raises(NotFoundError, match="rag space not found"):
        await service.note_selected("foreign-space")

    assert space_repo.increment_calls == []


@pytest.mark.asyncio
async def test_create_node_rejects_duplicate_sibling_name(monkeypatch):
    service, *_rest = build_service(monkeypatch)

    with pytest.raises(ValidationError, match="same name"):
        await service.create_node(rag_space_id="space-1", parent_id=None, node_type="folder", name="机械")


@pytest.mark.asyncio
async def test_update_node_renames_folder_and_descendant_paths(monkeypatch):
    service, session, space_repo, node_repo, *_rest = build_service(monkeypatch)
    node_repo.nodes.insert(
        1,
        FakeNode(
            id="folder-2",
            org_id="org-1",
            rag_space_id="space-1",
            parent_id="folder-1",
            created_by="user-1",
            node_type="folder",
            name="模具标准",
            full_path="机械/模具标准",
            depth=1,
            children_count=1,
        ),
    )
    node_repo.nodes[2].parent_id = "folder-2"
    node_repo.nodes[2].full_path = "机械/模具标准/spec.txt"
    node_repo.nodes[2].depth = 2

    updated = await service.update_node(
        rag_space_id="space-1",
        node_id="folder-2",
        name="新模具标准",
        parent_id="folder-1",
    )

    renamed_folder = next(node for node in node_repo.nodes if node.id == "folder-2")
    renamed_file = next(node for node in node_repo.nodes if node.id == "file-node-1")
    assert updated.full_path == "机械/新模具标准"
    assert renamed_folder.full_path == "机械/新模具标准"
    assert renamed_file.full_path == "机械/新模具标准/spec.txt"
    assert renamed_file.depth == 2
    assert space_repo.recalculate_calls[-1]["rag_space_id"] == "space-1"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_update_node_moves_file_to_new_folder(monkeypatch):
    service, session, _space_repo, node_repo, document_repo, *_rest = build_service(monkeypatch)
    node_repo.nodes.append(
        FakeNode(
            id="folder-3",
            org_id="org-1",
            rag_space_id="space-1",
            parent_id=None,
            created_by="user-1",
            node_type="folder",
            name="电子产品",
            full_path="电子产品",
            depth=0,
        )
    )

    updated = await service.update_node(
        rag_space_id="space-1",
        node_id="file-node-1",
        name="spec-v2.txt",
        parent_id="folder-3",
    )

    moved = next(node for node in node_repo.nodes if node.id == "file-node-1")
    assert updated.full_path == "电子产品/spec-v2.txt"
    assert moved.parent_id == "folder-3"
    assert moved.full_path == "电子产品/spec-v2.txt"
    assert moved.depth == 1
    assert document_repo.documents[0].file_name == "spec-v2.txt"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_update_node_rejects_move_into_own_descendant(monkeypatch):
    service, _session, _space_repo, node_repo, *_rest = build_service(monkeypatch)
    node_repo.nodes.insert(
        1,
        FakeNode(
            id="folder-2",
            org_id="org-1",
            rag_space_id="space-1",
            parent_id="folder-1",
            created_by="user-1",
            node_type="folder",
            name="模具标准",
            full_path="机械/模具标准",
            depth=1,
        ),
    )

    with pytest.raises(ValidationError, match="descendant"):
        await service.update_node(
            rag_space_id="space-1",
            node_id="folder-1",
            name="机械",
            parent_id="folder-2",
        )
