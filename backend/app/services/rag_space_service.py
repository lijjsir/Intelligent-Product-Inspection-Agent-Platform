from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.rag.embedder import EmbeddingModelNotConfigured
from fastapi import UploadFile
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.rag.knowledge_indexer import KnowledgeIndexer
from agent.tools.file_parsers import parse_file_content
from app.core.config import settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.models.rag_space import RagDocument, RagNode, RagSpace
from app.repositories.rag_space_repo import (
    RagDocumentChunkRepository,
    RagDocumentRepository,
    RagIndexJobRepository,
    RagNodeRepository,
    RagSpaceRepository,
)
from app.schemas.rag_space import (
    RagDocumentResponse,
    RagNodeResponse,
    RagSpaceDocumentListItem,
    RagSpaceResponse,
)
from app.services.file_storage_service import FileStorageService
from app.services.object_storage.factory import build_object_storage


ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md", ".jsonl", ".json", ".docx", ".csv", ".xlsx"}
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".pdf",
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".docx",
    ".csv",
    ".xlsx",
}
RAG_METADATA_MISSING_MESSAGE = "RAG 空间尚未初始化，请先完成数据库迁移。"


def _is_rag_metadata_missing(exc: Exception) -> bool:
    if not isinstance(exc, (ProgrammingError, OperationalError)):
        return False
    message = str(exc).lower()
    if "doesn't exist" not in message and "does not exist" not in message:
        return False
    return any(name in message for name in ("rag_spaces", "rag_nodes", "rag_documents"))


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _chunk_text(text: str, chunk_size: int = 380) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]
    if not paragraphs:
        paragraphs = [raw]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        for start in range(0, len(paragraph), chunk_size):
            chunks.append(paragraph[start : start + chunk_size].strip())
        current = ""
    if current:
        chunks.append(current)
    return chunks[:24]


def _token_count(text: str) -> int:
    return len(TOKEN_PATTERN.findall(str(text or "")))


class RagSpaceService:
    def __init__(self, session: AsyncSession, *, org_id: str, user_id: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._spaces = RagSpaceRepository(session)
        self._nodes = RagNodeRepository(session)
        self._documents = RagDocumentRepository(session)
        self._chunks = RagDocumentChunkRepository(session)
        self._jobs = RagIndexJobRepository(session)
        self._storage = build_object_storage()
        self._rag_storage_bucket = settings.rag_storage_bucket
        self._indexer = KnowledgeIndexer(org_id=self._org_id)

    async def create_space(self, *, name: str, description: str | None) -> RagSpaceResponse:
        try:
            obj = await self._spaces.create(
                org_id=self._org_id,
                created_by=self._user_id,
                name=self._normalize_node_name(name, label="space"),
                description=(description or "").strip() or None,
            )
            await self._session.commit()
            return RagSpaceResponse.model_validate(obj)
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def list_spaces(self, limit: int = 200) -> list[RagSpaceResponse]:
        try:
            rows = await self._spaces.list_for_org(org_id=self._org_id, owner_user_id=None, limit=limit)
            return [RagSpaceResponse.model_validate(row) for row in rows]
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def update_space(self, *, rag_space_id: str, name: str, description: str | None) -> RagSpaceResponse:
        try:
            space = await self._get_owned_space(rag_space_id)
            space.name = self._normalize_node_name(name, label="space")
            space.description = (description or "").strip() or None
            await self._session.commit()
            return RagSpaceResponse.model_validate(space)
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def delete_space(self, *, rag_space_id: str) -> None:
        try:
            await self._get_owned_space(rag_space_id)
            nodes = await self._nodes.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            node_ids = [str(node.id) for node in nodes]
            documents = await self._documents.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
                limit=5000,
            )
            await self._remove_documents(rag_space_id=rag_space_id, documents=documents)
            await self._documents.soft_delete_many(document_ids=[str(item.id) for item in documents])
            await self._nodes.soft_delete_many(node_ids=node_ids)
            await self._spaces.soft_delete(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._session.commit()
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def get_tree(self, *, rag_space_id: str) -> list[RagNodeResponse]:
        try:
            await self._get_owned_space(rag_space_id)
            nodes = await self._nodes.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            documents = await self._documents.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
                limit=5000,
            )
            return self._build_tree(nodes=nodes, documents=documents)
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def create_node(self, *, rag_space_id: str, parent_id: str | None, node_type: str, name: str) -> RagNodeResponse:
        try:
            await self._get_owned_space(rag_space_id)
            if node_type != "folder":
                raise ValidationError("only folder nodes can be created explicitly")
            parent = await self._get_valid_parent(rag_space_id=rag_space_id, parent_id=parent_id)
            normalized_name = self._normalize_node_name(name)
            await self._ensure_unique_name(rag_space_id=rag_space_id, parent_id=parent_id, name=normalized_name)

            created = await self._nodes.create(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                created_by=self._user_id,
                parent_id=parent_id,
                node_type="folder",
                name=normalized_name,
                full_path=self._build_full_path(parent=parent, name=normalized_name),
                depth=(parent.depth + 1) if parent else 0,
                sort_order=0,
                status="ready",
            )
            await self._nodes.recalculate_children_counts(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._spaces.recalculate_counters(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._session.commit()
            return self._serialize_node(created, None)
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def update_node(self, *, rag_space_id: str, node_id: str, parent_id: str | None, name: str) -> RagNodeResponse:
        try:
            await self._get_owned_space(rag_space_id)
            nodes = await self._nodes.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            target = next((node for node in nodes if str(node.id) == node_id), None)
            if target is None:
                raise NotFoundError("rag node not found")

            normalized_name = self._normalize_node_name(name)
            new_parent = await self._get_valid_parent(rag_space_id=rag_space_id, parent_id=parent_id)
            self._ensure_not_moving_into_descendant(target=target, new_parent=new_parent, nodes=nodes)
            await self._ensure_unique_name(
                rag_space_id=rag_space_id,
                parent_id=parent_id,
                name=normalized_name,
                exclude_node_id=str(target.id),
            )

            target.parent_id = parent_id
            target.name = normalized_name
            target.full_path = self._build_full_path(parent=new_parent, name=normalized_name)
            target.depth = (new_parent.depth + 1) if new_parent else 0
            self._refresh_subtree_paths(nodes=nodes, root_id=str(target.id))

            if target.node_type == "file":
                document = await self._documents.get_by_node_id(
                    org_id=self._org_id,
                    rag_space_id=rag_space_id,
                    node_id=str(target.id),
                    owner_user_id=self._user_id,
                )
                if document is not None:
                    document.file_name = normalized_name
            else:
                document = await self._documents.get_by_node_id(
                    org_id=self._org_id,
                    rag_space_id=rag_space_id,
                    node_id=str(target.id),
                    owner_user_id=self._user_id,
                )

            await self._nodes.recalculate_children_counts(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._spaces.recalculate_counters(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._session.commit()
            return self._serialize_node(target, document)
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def list_documents(self, *, rag_space_id: str, limit: int = 1000) -> list[RagSpaceDocumentListItem]:
        try:
            await self._get_owned_space(rag_space_id)
            nodes = await self._nodes.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            node_map = {node.id: node for node in nodes}
            rows = await self._documents.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
                limit=limit,
            )
            rows.sort(key=lambda item: (node_map.get(item.node_id).full_path if node_map.get(item.node_id) else item.file_name))
            return [
                RagSpaceDocumentListItem(
                    id=str(item.id),
                    rag_space_id=str(item.rag_space_id),
                    org_id=str(item.org_id),
                    node_id=str(item.node_id),
                    file_name=str(item.file_name),
                    content_type=item.content_type,
                    file_url=str(item.file_url),
                    size_bytes=int(item.size_bytes or 0),
                    status=str(item.index_status or item.parse_status or "ready"),
                    created_at=item.created_at,
                )
                for item in rows
            ]
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def upload_documents(
        self,
        *,
        rag_space_id: str,
        files: list[UploadFile],
        parent_node_id: str | None = None,
    ) -> list[RagNodeResponse]:
        try:
            await self._get_owned_space(rag_space_id)
            if not files:
                raise ValidationError("no files uploaded")
            parent = await self._get_valid_parent(rag_space_id=rag_space_id, parent_id=parent_node_id)
            space_nodes = await self._nodes.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            ancestor_node_ids = self._resolve_ancestor_node_ids(nodes=space_nodes, parent_id=parent_node_id)

            saved_rows: list[RagNodeResponse] = []
            for upload in files:
                raw_name = upload.filename or "document.bin"
                normalized_name = self._normalize_node_name(raw_name)
                suffix = Path(normalized_name).suffix.lower()
                if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
                    raise ValidationError(f"unsupported document type: {suffix or 'unknown'}")
                await self._ensure_unique_name(rag_space_id=rag_space_id, parent_id=parent_node_id, name=normalized_name)

                content = await upload.read()
                if not content:
                    raise ValidationError(f"empty document: {normalized_name}")
                checksum = hashlib.sha256(content).hexdigest()
                rag_storage = build_object_storage()
                object_key = f"rag/{self._org_id}/{rag_space_id}/{checksum[:12]}-{normalized_name}"
                stored = rag_storage.put_bytes(
                    bucket=self._rag_storage_bucket,
                    object_key=object_key,
                    data=content,
                    content_type=upload.content_type,
                )
                full_path = self._build_full_path(parent=parent, name=normalized_name)
                node = await self._nodes.create(
                    org_id=self._org_id,
                    rag_space_id=rag_space_id,
                    created_by=self._user_id,
                    parent_id=parent_node_id,
                    node_type="file",
                    name=normalized_name,
                    full_path=full_path,
                    depth=(parent.depth + 1) if parent else 0,
                    sort_order=0,
                    status="ready",
                )
                document = await self._documents.create(
                    org_id=self._org_id,
                    rag_space_id=rag_space_id,
                    node_id=str(node.id),
                    uploaded_by=self._user_id,
                    file_name=normalized_name,
                    content_type=upload.content_type,
                    file_url=stored["url"],
                    size_bytes=int(stored["size_bytes"] or 0),
                    checksum_sha256=checksum,
                    storage_backend=str(stored.get("backend") or getattr(rag_storage, "backend_name", "local")),
                    bucket=str(stored.get("bucket") or self._rag_storage_bucket),
                    object_key=str(stored.get("object_key") or object_key),
                    parse_status="pending",
                    index_status="indexing",
                    chunk_count=0,
                )
                job = await self._jobs.create(
                    org_id=self._org_id,
                    rag_space_id=rag_space_id,
                    document_id=str(document.id),
                    status="indexing",
                )
                docs = self._build_docs_from_file(
                    document_id=str(document.id),
                    node_id=str(node.id),
                    file_name=normalized_name,
                    file_url=stored["url"],
                    full_path=full_path,
                    suffix=suffix,
                    content=content,
                    rag_space_id=rag_space_id,
                    ancestor_node_ids=ancestor_node_ids,
                )
                try:
                    result = await self._indexer.index(docs)
                except EmbeddingModelNotConfigured as exc:
                    document.parse_status = "failed"
                    document.index_status = "failed"
                    document.error_message = str(exc)
                    job.status = "failed"
                    job.error_message = str(exc)
                    raise ValidationError("未配置 embedding 模型，请先在模型配置页启用 embedding 模型后再上传文件。") from exc
                if int(result.get("accepted") or 0) <= 0:
                    document.parse_status = "failed"
                    document.index_status = "failed"
                    document.error_message = f"failed to index document: {normalized_name}"
                    job.status = "failed"
                    job.error_message = document.error_message
                    raise ValidationError(f"failed to index document: {normalized_name}")
                await self._persist_chunk_rows(
                    rag_space_id=rag_space_id,
                    node_id=str(node.id),
                    document_id=str(document.id),
                    docs=docs,
                )
                document.parse_status = "parsed"
                document.index_status = "ready"
                document.chunk_count = int(result.get("accepted") or 0)
                document.error_message = None
                job.status = "ready"
                job.error_message = None
                saved_rows.append(self._serialize_node(node, document))

            await self._nodes.recalculate_children_counts(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._spaces.recalculate_counters(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._session.commit()
            return saved_rows
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def create_generated_document(
        self,
        *,
        rag_space_id: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
        parent_node_id: str | None = None,
    ) -> RagNodeResponse:
        try:
            await self._get_owned_space(rag_space_id)
            parent = await self._get_valid_parent(rag_space_id=rag_space_id, parent_id=parent_node_id)
            space_nodes = await self._nodes.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            ancestor_node_ids = self._resolve_ancestor_node_ids(nodes=space_nodes, parent_id=parent_node_id)
            normalized_name = self._normalize_node_name(file_name)
            suffix = Path(normalized_name).suffix.lower()
            if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
                raise ValidationError(f"unsupported document type: {suffix or 'unknown'}")
            await self._ensure_unique_name(rag_space_id=rag_space_id, parent_id=parent_node_id, name=normalized_name)
            if not content:
                raise ValidationError(f"empty document: {normalized_name}")

            checksum = hashlib.sha256(content).hexdigest()
            rag_storage = build_object_storage()
            object_key = f"rag/{self._org_id}/{rag_space_id}/{checksum[:12]}-{normalized_name}"
            stored = rag_storage.put_bytes(
                bucket=self._rag_storage_bucket,
                object_key=object_key,
                data=content,
                content_type=content_type,
            )
            full_path = self._build_full_path(parent=parent, name=normalized_name)
            node = await self._nodes.create(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                created_by=self._user_id,
                parent_id=parent_node_id,
                node_type="file",
                name=normalized_name,
                full_path=full_path,
                depth=(parent.depth + 1) if parent else 0,
                sort_order=0,
                status="ready",
            )
            document = await self._documents.create(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                node_id=str(node.id),
                uploaded_by=self._user_id,
                file_name=normalized_name,
                content_type=content_type,
                file_url=stored["url"],
                size_bytes=int(stored["size_bytes"] or 0),
                checksum_sha256=checksum,
                storage_backend=str(stored.get("backend") or getattr(rag_storage, "backend_name", "local")),
                bucket=str(stored.get("bucket") or self._rag_storage_bucket),
                object_key=str(stored.get("object_key") or object_key),
                parse_status="pending",
                index_status="indexing",
                chunk_count=0,
            )
            job = await self._jobs.create(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                document_id=str(document.id),
                status="indexing",
            )
            docs = self._build_docs_from_file(
                document_id=str(document.id),
                node_id=str(node.id),
                file_name=normalized_name,
                file_url=stored["url"],
                full_path=full_path,
                suffix=suffix,
                content=content,
                rag_space_id=rag_space_id,
                ancestor_node_ids=ancestor_node_ids,
            )
            try:
                result = await self._indexer.index(docs)
            except EmbeddingModelNotConfigured as exc:
                document.parse_status = "failed"
                document.index_status = "failed"
                document.error_message = str(exc)
                job.status = "failed"
                job.error_message = str(exc)
                raise ValidationError("未配置 embedding 模型，请先在模型配置页启用 embedding 模型后再上传文件。") from exc
            if int(result.get("accepted") or 0) <= 0:
                document.parse_status = "failed"
                document.index_status = "failed"
                document.error_message = f"failed to index document: {normalized_name}"
                job.status = "failed"
                job.error_message = document.error_message
                raise ValidationError(f"failed to index document: {normalized_name}")

            await self._persist_chunk_rows(
                rag_space_id=rag_space_id,
                node_id=str(node.id),
                document_id=str(document.id),
                docs=docs,
            )
            document.parse_status = "parsed"
            document.index_status = "ready"
            document.chunk_count = int(result.get("accepted") or 0)
            document.error_message = None
            job.status = "ready"
            job.error_message = None
            await self._nodes.recalculate_children_counts(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._spaces.recalculate_counters(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._session.flush()
            return self._serialize_node(node, document)
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def delete_node(self, *, rag_space_id: str, node_id: str) -> None:
        try:
            await self._get_owned_space(rag_space_id)
            nodes = await self._nodes.list_for_space(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            target = next((node for node in nodes if node.id == node_id), None)
            if target is None:
                raise NotFoundError("rag node not found")

            subtree = self._collect_subtree(nodes=nodes, root_id=node_id)
            subtree_ids = [str(node.id) for node in subtree]
            documents = await self._documents.list_for_node_ids(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                node_ids=subtree_ids,
                owner_user_id=self._user_id,
            )
            await self._remove_documents(rag_space_id=rag_space_id, documents=documents)
            await self._documents.soft_delete_many(document_ids=[str(item.id) for item in documents])
            await self._nodes.soft_delete_many(node_ids=subtree_ids)
            await self._nodes.recalculate_children_counts(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._spaces.recalculate_counters(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            await self._session.commit()
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def delete_document(self, *, rag_space_id: str, file_id: str) -> None:
        try:
            await self._get_owned_space(rag_space_id)
            document = await self._documents.get(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                document_id=file_id,
                owner_user_id=self._user_id,
            )
            if document is None:
                raise NotFoundError("rag document not found")
            await self.delete_node(rag_space_id=rag_space_id, node_id=str(document.node_id))
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def note_selected(self, rag_space_id: str | None) -> None:
        if not rag_space_id:
            return
        try:
            await self._get_owned_space(rag_space_id)
            await self._spaces.increment_selected_count(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def upload_attachments(self, *, files: list[UploadFile]) -> list[dict[str, Any]]:
        if not files:
            raise ValidationError("no files uploaded")
        items: list[dict[str, Any]] = []
        for upload in files:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in ALLOWED_ATTACHMENT_EXTENSIONS:
                raise ValidationError(f"unsupported attachment type: {suffix or 'unknown'}")
            content = await upload.read()
            if not content:
                raise ValidationError(f"empty attachment: {upload.filename or 'unnamed'}")
            safe_name = Path(upload.filename or "attachment.bin").name
            object_key = f"chat_attachments/{uuid4().hex}{suffix}"
            stored = self._storage.put_bytes(
                bucket="chat-attachments",
                object_key=object_key,
                data=content,
                content_type=upload.content_type,
            )
            kind = "image" if (stored["content_type"] or "").startswith("image/") else "file"
            items.append(
                {
                    "id": uuid4().hex,
                    "name": safe_name,
                    "url": f"/api/v1/files/{stored['bucket']}/{stored['object_key']}",
                    "content_type": stored["content_type"],
                    "size_bytes": stored["size_bytes"],
                    "kind": kind,
                    "bucket": stored["bucket"],
                    "object_key": stored["object_key"],
                }
            )
        return items

    def _build_docs_from_file(
        self,
        *,
        document_id: str,
        node_id: str,
        file_name: str,
        file_url: str,
        full_path: str,
        suffix: str,
        content: bytes,
        rag_space_id: str,
        ancestor_node_ids: list[str],
    ) -> list[dict[str, Any]]:
        payload = {
            "rag_space_id": rag_space_id,
            "org_id": self._org_id,
            "user_id": self._user_id,
            "node_id": node_id,
            "document_id": document_id,
            "file_name": file_name,
            "file_url": file_url,
            "full_path": full_path,
            "ancestor_node_ids": list(ancestor_node_ids),
        }
        if suffix == ".jsonl":
            docs: list[dict[str, Any]] = []
            text = content.decode("utf-8", errors="ignore")
            for index, raw_line in enumerate(text.splitlines(), start=1):
                line = raw_line.strip()
                if not line:
                    continue
                item = json.loads(line)
                body = str(item.get("text") or "").strip()
                if not body:
                    continue
                docs.append(
                    {
                        "id": f"{document_id}:{index}",
                        "title": str(item.get("title") or file_name),
                        "text": body,
                        "source": str(item.get("source") or full_path),
                        "payload": {**payload, "chunk_index": index, "page_number": None},
                    }
                )
            if docs:
                return docs
            raise ValidationError(f"jsonl document has no indexable text: {file_name}")

        text = self._extract_text(file_name=file_name, suffix=suffix, content=content)
        if not text.strip():
            raise ValidationError(f"document has no indexable text: {file_name}")
        chunks = _chunk_text(text.strip())
        return [
            {
                "id": f"{document_id}:{index}",
                "title": file_name,
                "text": chunk,
                "source": full_path,
                "payload": {**payload, "chunk_index": index, "page_number": None},
            }
            for index, chunk in enumerate(chunks, start=1)
        ]

    def _extract_text(self, *, file_name: str, suffix: str, content: bytes) -> str:
        try:
            parsed = parse_file_content(file_name, content)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if suffix not in {".txt", ".md", ".pdf", ".json", ".docx", ".csv", ".xlsx"}:
            raise ValidationError(f"unsupported document type: {file_name}")
        return str(parsed.get("text") or "")

    async def _get_valid_parent(self, *, rag_space_id: str, parent_id: str | None) -> RagNode | None:
        if not parent_id:
            return None
        parent = await self._nodes.get(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            node_id=parent_id,
            owner_user_id=self._user_id,
        )
        if parent is None:
            raise NotFoundError("parent node not found")
        if parent.node_type != "folder":
            raise ValidationError("files cannot contain child nodes")
        return parent

    async def _ensure_unique_name(
        self,
        *,
        rag_space_id: str,
        parent_id: str | None,
        name: str,
        exclude_node_id: str | None = None,
    ) -> None:
        sibling = await self._nodes.find_sibling(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            parent_id=parent_id,
            name=name,
            owner_user_id=self._user_id,
        )
        if sibling is not None and str(sibling.id) != exclude_node_id:
            raise ValidationError("a node with the same name already exists in this folder")

    def _normalize_node_name(self, value: str, *, label: str = "node") -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValidationError(f"{label} name is required")
        if "/" in normalized or "\\" in normalized:
            raise ValidationError(f"{label} name cannot contain path separators")
        return normalized

    def _build_full_path(self, *, parent: RagNode | None, name: str) -> str:
        return f"{parent.full_path}/{name}" if parent else name

    def _refresh_subtree_paths(self, *, nodes: list[RagNode], root_id: str) -> None:
        node_map = {str(node.id): node for node in nodes}
        children_by_parent: dict[str, list[RagNode]] = {}
        for node in nodes:
            if node.parent_id:
                children_by_parent.setdefault(str(node.parent_id), []).append(node)

        root = node_map[root_id]
        stack = [root]
        while stack:
            current = stack.pop()
            for child in children_by_parent.get(str(current.id), []):
                child.full_path = f"{current.full_path}/{child.name}"
                child.depth = int(current.depth or 0) + 1
                stack.append(child)

    def _ensure_not_moving_into_descendant(self, *, target: RagNode, new_parent: RagNode | None, nodes: list[RagNode]) -> None:
        if new_parent is None or target.node_type != "folder":
            return
        subtree_ids = {str(node.id) for node in self._collect_subtree(nodes=nodes, root_id=str(target.id))}
        if str(new_parent.id) in subtree_ids:
            raise ValidationError("cannot move a folder into its own descendant")

    def _build_tree(self, *, nodes: list[RagNode], documents: list[RagDocument]) -> list[RagNodeResponse]:
        document_map = {str(item.node_id): item for item in documents}
        serialized: dict[str, RagNodeResponse] = {
            str(node.id): self._serialize_node(node, document_map.get(str(node.id))) for node in nodes
        }
        roots: list[RagNodeResponse] = []
        for node in nodes:
            current = serialized[str(node.id)]
            if node.parent_id and str(node.parent_id) in serialized:
                serialized[str(node.parent_id)].children.append(current)
            else:
                roots.append(current)
        return roots

    def _serialize_node(self, node: RagNode, document: RagDocument | None) -> RagNodeResponse:
        return RagNodeResponse(
            id=str(node.id),
            org_id=str(node.org_id),
            rag_space_id=str(node.rag_space_id),
            parent_id=str(node.parent_id) if node.parent_id else None,
            created_by=str(node.created_by) if node.created_by else None,
            node_type=str(node.node_type),
            name=str(node.name),
            full_path=str(node.full_path),
            depth=int(node.depth or 0),
            sort_order=int(node.sort_order or 0),
            status=str(node.status or "ready"),
            children_count=int(node.children_count or 0),
            created_at=node.created_at,
            updated_at=node.updated_at,
            document=RagDocumentResponse.model_validate(document) if document is not None else None,
            children=[],
        )

    def _collect_subtree(self, *, nodes: list[RagNode], root_id: str) -> list[RagNode]:
        children_by_parent: dict[str | None, list[RagNode]] = {}
        for node in nodes:
            children_by_parent.setdefault(str(node.parent_id) if node.parent_id else None, []).append(node)

        result: list[RagNode] = []
        stack = [root_id]
        node_map = {str(node.id): node for node in nodes}
        while stack:
            current_id = stack.pop()
            current = node_map.get(current_id)
            if current is None:
                continue
            result.append(current)
            for child in children_by_parent.get(current_id, []):
                stack.append(str(child.id))
        return result

    async def _remove_documents(self, *, rag_space_id: str, documents: list[RagDocument]) -> None:
        document_ids = [str(document.id) for document in documents]
        for document in documents:
            bucket = str(getattr(document, "bucket", "") or self._rag_storage_bucket)
            build_object_storage().delete_object(
                bucket=bucket,
                object_key=str(document.object_key),
            )
            await self._indexer.delete_by_filter(
                {
                    "org_id": self._org_id,
                    "user_id": self._user_id,
                    "rag_space_id": rag_space_id,
                    "document_id": str(document.id),
                    "node_id": str(document.node_id),
                }
            )
        await self._chunks.soft_delete_by_document_ids(document_ids=document_ids)
        await self._jobs.soft_delete_by_document_ids(document_ids=document_ids)

    def _resolve_ancestor_node_ids(self, *, nodes: list[RagNode], parent_id: str | None) -> list[str]:
        if not parent_id:
            return []
        node_map = {str(node.id): node for node in nodes}
        ordered: list[str] = []
        current_id = parent_id
        while current_id:
            ordered.insert(0, current_id)
            current = node_map.get(current_id)
            if current is None or not current.parent_id:
                break
            current_id = str(current.parent_id)
        return ordered

    async def _persist_chunk_rows(
        self,
        *,
        rag_space_id: str,
        node_id: str,
        document_id: str,
        docs: list[dict[str, Any]],
    ) -> None:
        rows = []
        for item in docs:
            text = str(item.get("text") or "").strip()
            payload = dict(item.get("payload") or {})
            rows.append(
                {
                    "org_id": self._org_id,
                    "rag_space_id": rag_space_id,
                    "document_id": document_id,
                    "node_id": node_id,
                    "chunk_index": int(payload.get("chunk_index") or 1),
                    "content_text": text,
                    "content_preview": text[:220],
                    "page_number": payload.get("page_number"),
                    "token_count": _token_count(text),
                    "qdrant_point_id": str(item.get("id") or ""),
                }
            )
        await self._chunks.create_many(rows)

    def _raise_if_rag_metadata_missing(self, exc: Exception) -> None:
        if _is_rag_metadata_missing(exc):
            raise ServiceUnavailableError(RAG_METADATA_MISSING_MESSAGE) from exc

    async def _get_owned_space(self, rag_space_id: str) -> RagSpace:
        space = await self._spaces.get(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            owner_user_id=self._user_id,
        )
        if space is None:
            raise NotFoundError("rag space not found")
        return space
