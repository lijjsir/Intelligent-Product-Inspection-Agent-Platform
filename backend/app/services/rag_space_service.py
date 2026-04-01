from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.rag.knowledge_indexer import KnowledgeIndexer
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.repositories.rag_space_repo import RagSpaceFileRepository, RagSpaceRepository
from app.schemas.rag_space import RagSpaceFileResponse, RagSpaceResponse
from app.services.file_storage_service import FileStorageService


ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md", ".jsonl"}
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
}
RAG_METADATA_MISSING_MESSAGE = "RAG 空间尚未初始化，请先完成数据库迁移。"


def _is_rag_metadata_missing(exc: Exception) -> bool:
    if not isinstance(exc, (ProgrammingError, OperationalError)):
        return False
    message = str(exc).lower()
    if "doesn't exist" not in message and "does not exist" not in message:
        return False
    return "rag_spaces" in message or "rag_space_files" in message


class RagSpaceService:
    def __init__(self, session: AsyncSession, *, org_id: str, user_id: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._spaces = RagSpaceRepository(session)
        self._files = RagSpaceFileRepository(session)
        self._storage = FileStorageService()
        self._indexer = KnowledgeIndexer()

    async def create_space(self, *, name: str, description: str | None) -> RagSpaceResponse:
        try:
            obj = await self._spaces.create(
                org_id=self._org_id,
                created_by=self._user_id,
                name=name.strip(),
                description=(description or "").strip() or None,
            )
            await self._session.commit()
            return RagSpaceResponse.model_validate(obj)
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def list_spaces(self, limit: int = 200) -> list[RagSpaceResponse]:
        try:
            rows = await self._spaces.list_for_org(org_id=self._org_id, limit=limit)
            payload: list[RagSpaceResponse] = []
            for row in rows:
                files = await self._files.list_for_space(org_id=self._org_id, rag_space_id=str(row.id), limit=50)
                payload.append(
                    RagSpaceResponse.model_validate(
                        {
                            **row.__dict__,
                            "files": [RagSpaceFileResponse.model_validate(item) for item in files],
                        }
                    )
                )
            return payload
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def upload_documents(self, *, rag_space_id: str, files: list[UploadFile]) -> list[RagSpaceFileResponse]:
        try:
            space = await self._spaces.get(org_id=self._org_id, rag_space_id=rag_space_id)
            if space is None:
                raise NotFoundError("rag space not found")
            if not files:
                raise ValidationError("no files uploaded")

            saved_rows: list[RagSpaceFileResponse] = []
            for upload in files:
                suffix = Path(upload.filename or "").suffix.lower()
                if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
                    raise ValidationError(f"unsupported document type: {suffix or 'unknown'}")

                content = await upload.read()
                if not content:
                    raise ValidationError(f"empty document: {upload.filename or 'unnamed'}")

                stored = self._storage.save_bytes(
                    category=f"rag_spaces/{rag_space_id}",
                    file_name=upload.filename or "document.bin",
                    data=content,
                    content_type=upload.content_type,
                )
                docs = self._build_docs_from_file(
                    file_name=upload.filename or "document.bin",
                    file_url=stored["url"],
                    suffix=suffix,
                    content=content,
                    rag_space_id=rag_space_id,
                )
                result = await self._indexer.index(docs)
                if int(result.get("accepted") or 0) <= 0:
                    raise ValidationError(f"failed to index document: {upload.filename or 'unnamed'}")
                row = await self._files.create(
                    rag_space_id=rag_space_id,
                    org_id=self._org_id,
                    uploaded_by=self._user_id,
                    file_name=upload.filename or "document.bin",
                    content_type=upload.content_type,
                    file_url=stored["url"],
                    size_bytes=int(stored["size_bytes"] or 0),
                    status="ready",
                )
                saved_rows.append(RagSpaceFileResponse.model_validate(row))

            await self._spaces.recalculate_file_count(org_id=self._org_id, rag_space_id=rag_space_id)
            await self._session.commit()
            return saved_rows
        except Exception as exc:
            self._raise_if_rag_metadata_missing(exc)
            raise

    async def note_selected(self, rag_space_id: str | None) -> None:
        if not rag_space_id:
            return
        try:
            await self._spaces.increment_selected_count(org_id=self._org_id, rag_space_id=rag_space_id)
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
            stored = self._storage.save_bytes(
                category="chat_attachments",
                file_name=upload.filename or "attachment.bin",
                data=content,
                content_type=upload.content_type,
            )
            kind = "image" if (stored["content_type"] or "").startswith("image/") else "file"
            items.append(
                {
                    "id": stored["id"],
                    "name": stored["name"],
                    "url": stored["url"],
                    "content_type": stored["content_type"],
                    "size_bytes": stored["size_bytes"],
                    "kind": kind,
                }
            )
        return items

    def _build_docs_from_file(
        self,
        *,
        file_name: str,
        file_url: str,
        suffix: str,
        content: bytes,
        rag_space_id: str,
    ) -> list[dict[str, Any]]:
        payload = {
            "rag_space_id": rag_space_id,
            "org_id": self._org_id,
            "file_name": file_name,
            "file_url": file_url,
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
                        "id": f"{rag_space_id}:{file_name}:{index}",
                        "title": str(item.get("title") or file_name),
                        "text": body,
                        "source": str(item.get("source") or file_name),
                        "payload": payload,
                    }
                )
            if docs:
                return docs
            raise ValidationError(f"jsonl document has no indexable text: {file_name}")

        text = self._extract_text(file_name=file_name, suffix=suffix, content=content)
        if not text.strip():
            raise ValidationError(f"document has no indexable text: {file_name}")
        return [
            {
                "id": f"{rag_space_id}:{file_name}",
                "title": file_name,
                "text": text.strip(),
                "source": file_name,
                "payload": payload,
            }
        ]

    def _extract_text(self, *, file_name: str, suffix: str, content: bytes) -> str:
        if suffix in {".txt", ".md"}:
            return content.decode("utf-8", errors="ignore")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except Exception as exc:  # pragma: no cover - runtime dependency
                raise ValidationError(f"pdf parsing dependency unavailable: {exc}") from exc
            from io import BytesIO

            reader = PdfReader(BytesIO(content))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        raise ValidationError(f"unsupported document type: {file_name}")

    def _raise_if_rag_metadata_missing(self, exc: Exception) -> None:
        if _is_rag_metadata_missing(exc):
            raise ServiceUnavailableError(RAG_METADATA_MISSING_MESSAGE) from exc
