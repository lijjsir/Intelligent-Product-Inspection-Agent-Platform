from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument, StandardDocumentChunk


class InspectionStandardLibraryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self, org_id: str) -> list[InspectionStandardLibrary]:
        result = await self._session.execute(
            select(InspectionStandardLibrary)
            .where(
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
            .order_by(
                InspectionStandardLibrary.product_family.asc(),
                InspectionStandardLibrary.created_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def list_all_paginated(self, org_id: str, *, page: int = 1, size: int = 50) -> tuple[list[InspectionStandardLibrary], int]:
        base = select(InspectionStandardLibrary).where(
            InspectionStandardLibrary.deleted_at.is_(None),
            InspectionStandardLibrary.org_id == org_id,
        )
        count = await self._session.scalar(
            select(func.count(InspectionStandardLibrary.id)).where(
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
        )
        result = await self._session.execute(
            base.order_by(InspectionStandardLibrary.product_family.asc(), InspectionStandardLibrary.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), int(count or 0)

    async def get(self, org_id: str, library_id: str) -> InspectionStandardLibrary | None:
        result = await self._session.execute(
            select(InspectionStandardLibrary).where(
                InspectionStandardLibrary.id == library_id,
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active(self, org_id: str, library_id: str) -> InspectionStandardLibrary | None:
        result = await self._session.execute(
            select(InspectionStandardLibrary).where(
                InspectionStandardLibrary.id == library_id,
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
                InspectionStandardLibrary.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_spec_code(self, org_id: str, spec_code: str) -> InspectionStandardLibrary | None:
        result = await self._session.execute(
            select(InspectionStandardLibrary)
            .where(
                InspectionStandardLibrary.spec_code == spec_code,
                InspectionStandardLibrary.is_active.is_(True),
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
            .order_by(InspectionStandardLibrary.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_product_family(self, org_id: str, product_family: str) -> InspectionStandardLibrary | None:
        result = await self._session.execute(
            select(InspectionStandardLibrary)
            .where(
                InspectionStandardLibrary.product_family == product_family,
                InspectionStandardLibrary.is_active.is_(True),
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
            .order_by(
                InspectionStandardLibrary.updated_at.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, library: InspectionStandardLibrary) -> InspectionStandardLibrary:
        self._session.add(library)
        await self._session.flush()
        await self._session.refresh(library, attribute_names=["created_at", "updated_at"])
        return library

    async def update(self, library: InspectionStandardLibrary, payload: dict) -> InspectionStandardLibrary:
        for key, value in payload.items():
            setattr(library, key, value)
        await self._session.flush()
        await self._session.refresh(library)
        return library

    async def soft_delete(self, library: InspectionStandardLibrary) -> None:
        library.deleted_at = utcnow()
        await self._session.flush()


class StandardDocumentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_by_library(self, org_id: str, library_id: str) -> list[StandardDocument]:
        result = await self._session.execute(
            select(StandardDocument)
            .where(
                StandardDocument.org_id == org_id,
                StandardDocument.library_id == library_id,
                StandardDocument.deleted_at.is_(None),
            )
            .order_by(StandardDocument.domain.asc(), StandardDocument.standard_no.asc(), StandardDocument.file_name.asc())
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, document_id: str) -> StandardDocument | None:
        result = await self._session.execute(
            select(StandardDocument).where(
                StandardDocument.org_id == org_id,
                StandardDocument.id == document_id,
                StandardDocument.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_file_hash(self, org_id: str, library_id: str, standard_no: str, file_hash: str) -> StandardDocument | None:
        result = await self._session.execute(
            select(StandardDocument).where(
                StandardDocument.org_id == org_id,
                StandardDocument.library_id == library_id,
                StandardDocument.standard_no == standard_no,
                StandardDocument.file_hash == file_hash,
                StandardDocument.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_file_path(self, org_id: str, library_id: str, file_path: str) -> StandardDocument | None:
        result = await self._session.execute(
            select(StandardDocument).where(
                StandardDocument.org_id == org_id,
                StandardDocument.library_id == library_id,
                StandardDocument.file_path == file_path,
                StandardDocument.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_scanned(self, *, org_id: str, library_id: str, payload: dict) -> tuple[StandardDocument, bool]:
        existing = await self.get_by_file_path(org_id, library_id, str(payload["file_path"]))
        if existing is None and payload.get("file_hash"):
            existing = await self.get_by_file_hash(
                org_id,
                library_id,
                str(payload.get("standard_no") or ""),
                str(payload["file_hash"]),
            )
        created = existing is None
        if existing is None:
            existing = StandardDocument(org_id=org_id, library_id=library_id, **payload)
            self._session.add(existing)
        else:
            for key, value in payload.items():
                if key == "import_status" and existing.import_status == "completed":
                    continue
                setattr(existing, key, value)
        await self._session.flush()
        await self._session.refresh(existing, attribute_names=["created_at", "updated_at"])
        return existing, created

    async def update(self, document: StandardDocument, payload: dict) -> StandardDocument:
        for key, value in payload.items():
            setattr(document, key, value)
        await self._session.flush()
        await self._session.refresh(document, attribute_names=["updated_at"])
        return document

    async def count_by_library(self, org_id: str, library_id: str) -> int:
        count = await self._session.scalar(
            select(func.count(StandardDocument.id)).where(
                StandardDocument.org_id == org_id,
                StandardDocument.library_id == library_id,
                StandardDocument.deleted_at.is_(None),
            )
        )
        return int(count or 0)

    async def list_by_library_paginated(self, org_id: str, library_id: str, *, page: int = 1, size: int = 50) -> tuple[
        list[StandardDocument], int
    ]:
        base = select(StandardDocument).where(
            StandardDocument.org_id == org_id,
            StandardDocument.library_id == library_id,
            StandardDocument.deleted_at.is_(None),
        )
        count = await self._session.scalar(
            select(func.count(StandardDocument.id)).where(
                StandardDocument.org_id == org_id,
                StandardDocument.library_id == library_id,
                StandardDocument.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(
            base.order_by(StandardDocument.domain.asc(), StandardDocument.standard_no.asc(), StandardDocument.file_name.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), int(count or 0)

    async def soft_delete(self, document: StandardDocument) -> None:
        document.deleted_at = utcnow()
        await self._session.flush()

    async def soft_delete_by_library(self, org_id: str, library_id: str) -> int:
        result = await self._session.execute(
            update(StandardDocument)
            .where(
                StandardDocument.org_id == org_id,
                StandardDocument.library_id == library_id,
                StandardDocument.deleted_at.is_(None),
            )
            .values(deleted_at=utcnow())
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def count_completed_by_library(self, org_id: str, library_id: str) -> int:
        count = await self._session.scalar(
            select(func.count(StandardDocument.id)).where(
                StandardDocument.org_id == org_id,
                StandardDocument.library_id == library_id,
                StandardDocument.import_status == "completed",
                StandardDocument.deleted_at.is_(None),
            )
        )
        return int(count or 0)


class StandardDocumentChunkRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_by_document(self, document_id: str) -> list[StandardDocumentChunk]:
        result = await self._session.execute(
            select(StandardDocumentChunk)
            .where(
                StandardDocumentChunk.document_id == document_id,
                StandardDocumentChunk.deleted_at.is_(None),
            )
            .order_by(StandardDocumentChunk.page_from.asc(), StandardDocumentChunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def replace_for_document(self, *, document_id: str, library_id: str, rows: list[dict]) -> None:
        now = utcnow()
        result = await self._session.execute(
            select(StandardDocumentChunk).where(
                StandardDocumentChunk.document_id == document_id,
                StandardDocumentChunk.deleted_at.is_(None),
            )
        )
        for chunk in result.scalars().all():
            chunk.deleted_at = now
        for row in rows:
            self._session.add(StandardDocumentChunk(document_id=document_id, library_id=library_id, **row))
        await self._session.flush()

    async def soft_delete_by_document(self, document_id: str) -> int:
        result = await self._session.execute(
            update(StandardDocumentChunk)
            .where(
                StandardDocumentChunk.document_id == document_id,
                StandardDocumentChunk.deleted_at.is_(None),
            )
            .values(deleted_at=utcnow())
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def soft_delete_by_library(self, library_id: str) -> int:
        result = await self._session.execute(
            update(StandardDocumentChunk)
            .where(
                StandardDocumentChunk.library_id == library_id,
                StandardDocumentChunk.deleted_at.is_(None),
            )
            .values(deleted_at=utcnow())
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def count_by_library(self, library_id: str) -> int:
        count = await self._session.scalar(
            select(func.count(StandardDocumentChunk.id)).where(
                StandardDocumentChunk.library_id == library_id,
                StandardDocumentChunk.deleted_at.is_(None),
            )
        )
        return int(count or 0)
