from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.rag_space import RagDocument, RagDocumentChunk, RagIndexJob, RagNode, RagSpace


class RagSpaceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, *, org_id: str, created_by: str | None, name: str, description: str | None) -> RagSpace:
        obj = RagSpace(
            org_id=org_id,
            created_by=created_by,
            name=name,
            description=description,
            status="ready",
            index_status="ready",
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None) -> RagSpace | None:
        stmt = select(RagSpace).where(
            RagSpace.org_id == org_id,
            RagSpace.id == rag_space_id,
            RagSpace.deleted_at.is_(None),
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, *, org_id: str, owner_user_id: str | None = None, limit: int = 200) -> list[RagSpace]:
        stmt = select(RagSpace).where(
            RagSpace.org_id == org_id,
            RagSpace.deleted_at.is_(None),
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        stmt = stmt.order_by(RagSpace.updated_at.desc(), RagSpace.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def increment_selected_count(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None) -> None:
        obj = await self.get(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=owner_user_id)
        if obj is None:
            return
        obj.selected_count = int(obj.selected_count or 0) + 1
        await self._session.flush()

    async def recalculate_counters(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None) -> RagSpace | None:
        obj = await self.get(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=owner_user_id)
        if obj is None:
            return None

        file_count = await self._session.scalar(
            select(func.count(RagNode.id)).where(
                RagNode.org_id == org_id,
                RagNode.rag_space_id == rag_space_id,
                RagNode.node_type == "file",
                RagNode.deleted_at.is_(None),
            )
        )
        folder_count = await self._session.scalar(
            select(func.count(RagNode.id)).where(
                RagNode.org_id == org_id,
                RagNode.rag_space_id == rag_space_id,
                RagNode.node_type == "folder",
                RagNode.deleted_at.is_(None),
            )
        )
        chunk_count = await self._session.scalar(
            select(func.coalesce(func.sum(RagDocument.chunk_count), 0)).where(
                RagDocument.org_id == org_id,
                RagDocument.rag_space_id == rag_space_id,
                RagDocument.deleted_at.is_(None),
            )
        )
        status_row = await self._session.execute(
            select(
                func.sum(case((RagDocument.index_status == "failed", 1), else_=0)).label("failed_count"),
                func.sum(
                    case(
                        (
                            RagDocument.index_status.in_(("pending", "indexing"))
                            | RagDocument.parse_status.in_(("pending", "parsing")),
                            1,
                        ),
                        else_=0,
                    )
                ).label("active_count"),
            ).where(
                RagDocument.org_id == org_id,
                RagDocument.rag_space_id == rag_space_id,
                RagDocument.deleted_at.is_(None),
            )
        )
        failed_count, active_count = status_row.one()
        index_status = "ready"
        if int(failed_count or 0) > 0:
            index_status = "failed"
        elif int(active_count or 0) > 0:
            index_status = "indexing"

        obj.file_count = int(file_count or 0)
        obj.folder_count = int(folder_count or 0)
        obj.chunk_count = int(chunk_count or 0)
        obj.index_status = index_status
        await self._session.flush()
        return obj

    async def soft_delete(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None) -> RagSpace | None:
        obj = await self.get(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=owner_user_id)
        if obj is None:
            return None
        obj.deleted_at = utcnow()
        await self._session.flush()
        return obj


class RagNodeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        created_by: str | None,
        parent_id: str | None,
        node_type: str,
        name: str,
        full_path: str,
        depth: int,
        sort_order: int = 0,
        status: str = "ready",
    ) -> RagNode:
        obj = RagNode(
            org_id=org_id,
            rag_space_id=rag_space_id,
            created_by=created_by,
            parent_id=parent_id,
            node_type=node_type,
            name=name,
            full_path=full_path,
            depth=depth,
            sort_order=sort_order,
            status=status,
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        node_id: str,
        owner_user_id: str | None = None,
    ) -> RagNode | None:
        stmt = (
            select(RagNode)
            .join(RagSpace, RagSpace.id == RagNode.rag_space_id)
            .where(
                RagNode.org_id == org_id,
                RagNode.rag_space_id == rag_space_id,
                RagNode.id == node_id,
                RagNode.deleted_at.is_(None),
                RagSpace.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_space(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        owner_user_id: str | None = None,
    ) -> list[RagNode]:
        stmt = (
            select(RagNode)
            .join(RagSpace, RagSpace.id == RagNode.rag_space_id)
            .where(
                RagNode.org_id == org_id,
                RagNode.rag_space_id == rag_space_id,
                RagNode.deleted_at.is_(None),
                RagSpace.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        stmt = stmt.order_by(RagNode.depth.asc(), RagNode.sort_order.asc(), RagNode.created_at.asc(), RagNode.name.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_children(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        parent_id: str | None,
        owner_user_id: str | None = None,
    ) -> list[RagNode]:
        rows = await self.list_for_space(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=owner_user_id)
        return [row for row in rows if row.parent_id == parent_id]

    async def find_sibling(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        parent_id: str | None,
        name: str,
        owner_user_id: str | None = None,
    ) -> RagNode | None:
        stmt = (
            select(RagNode)
            .join(RagSpace, RagSpace.id == RagNode.rag_space_id)
            .where(
                RagNode.org_id == org_id,
                RagNode.rag_space_id == rag_space_id,
                RagNode.deleted_at.is_(None),
                RagNode.parent_id.is_(parent_id) if parent_id is None else RagNode.parent_id == parent_id,
                func.lower(RagNode.name) == name.lower(),
                RagSpace.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def recalculate_children_counts(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        owner_user_id: str | None = None,
    ) -> None:
        rows = await self.list_for_space(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=owner_user_id)
        children_by_parent: dict[str | None, int] = {}
        for row in rows:
            children_by_parent[row.parent_id] = children_by_parent.get(row.parent_id, 0) + 1
        for row in rows:
            row.children_count = int(children_by_parent.get(row.id, 0))
        await self._session.flush()

    async def soft_delete_many(self, *, node_ids: list[str]) -> None:
        if not node_ids:
            return
        now = utcnow()
        result = await self._session.execute(select(RagNode).where(RagNode.id.in_(node_ids), RagNode.deleted_at.is_(None)))
        for row in result.scalars().all():
            row.deleted_at = now
        await self._session.flush()


class RagDocumentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        node_id: str,
        uploaded_by: str | None,
        file_name: str,
        content_type: str | None,
        file_url: str,
        size_bytes: int,
        checksum_sha256: str,
        storage_backend: str,
        bucket: str,
        object_key: str,
        parse_status: str = "parsed",
        index_status: str = "ready",
        chunk_count: int = 0,
        error_message: str | None = None,
    ) -> RagDocument:
        obj = RagDocument(
            org_id=org_id,
            rag_space_id=rag_space_id,
            node_id=node_id,
            uploaded_by=uploaded_by,
            file_name=file_name,
            content_type=content_type,
            file_url=file_url,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            storage_backend=storage_backend,
            bucket=bucket,
            object_key=object_key,
            parse_status=parse_status,
            index_status=index_status,
            chunk_count=chunk_count,
            error_message=error_message,
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def list_for_space(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        owner_user_id: str | None = None,
        limit: int = 1000,
    ) -> list[RagDocument]:
        stmt = (
            select(RagDocument)
            .join(RagSpace, RagSpace.id == RagDocument.rag_space_id)
            .where(
                RagDocument.org_id == org_id,
                RagDocument.rag_space_id == rag_space_id,
                RagDocument.deleted_at.is_(None),
                RagSpace.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        stmt = stmt.order_by(RagDocument.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        document_id: str,
        owner_user_id: str | None = None,
    ) -> RagDocument | None:
        stmt = (
            select(RagDocument)
            .join(RagSpace, RagSpace.id == RagDocument.rag_space_id)
            .where(
                RagDocument.org_id == org_id,
                RagDocument.rag_space_id == rag_space_id,
                RagDocument.id == document_id,
                RagDocument.deleted_at.is_(None),
                RagSpace.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_node_id(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        node_id: str,
        owner_user_id: str | None = None,
    ) -> RagDocument | None:
        stmt = (
            select(RagDocument)
            .join(RagSpace, RagSpace.id == RagDocument.rag_space_id)
            .where(
                RagDocument.org_id == org_id,
                RagDocument.rag_space_id == rag_space_id,
                RagDocument.node_id == node_id,
                RagDocument.deleted_at.is_(None),
                RagSpace.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_node_ids(
        self,
        *,
        org_id: str,
        rag_space_id: str,
        node_ids: list[str],
        owner_user_id: str | None = None,
    ) -> list[RagDocument]:
        if not node_ids:
            return []
        stmt = (
            select(RagDocument)
            .join(RagSpace, RagSpace.id == RagDocument.rag_space_id)
            .where(
                RagDocument.org_id == org_id,
                RagDocument.rag_space_id == rag_space_id,
                RagDocument.node_id.in_(node_ids),
                RagDocument.deleted_at.is_(None),
                RagSpace.deleted_at.is_(None),
            )
        )
        if owner_user_id is not None:
            stmt = stmt.where(RagSpace.created_by == owner_user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete_many(self, *, document_ids: list[str]) -> None:
        if not document_ids:
            return
        now = utcnow()
        result = await self._session.execute(
            select(RagDocument).where(RagDocument.id.in_(document_ids), RagDocument.deleted_at.is_(None))
        )
        for row in result.scalars().all():
            row.deleted_at = now
        await self._session.flush()


class RagDocumentChunkRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_many(self, rows: list[dict[str, object]]) -> None:
        for row in rows:
            self._session.add(RagDocumentChunk(**row))
        await self._session.flush()

    async def soft_delete_by_document_ids(self, *, document_ids: list[str]) -> None:
        if not document_ids:
            return
        now = utcnow()
        result = await self._session.execute(
            select(RagDocumentChunk).where(RagDocumentChunk.document_id.in_(document_ids), RagDocumentChunk.deleted_at.is_(None))
        )
        for row in result.scalars().all():
            row.deleted_at = now
        await self._session.flush()


class RagIndexJobRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, *, org_id: str, rag_space_id: str, document_id: str, status: str = "pending") -> RagIndexJob:
        obj = RagIndexJob(
            org_id=org_id,
            rag_space_id=rag_space_id,
            document_id=document_id,
            status=status,
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def soft_delete_by_document_ids(self, *, document_ids: list[str]) -> None:
        if not document_ids:
            return
        now = utcnow()
        result = await self._session.execute(
            select(RagIndexJob).where(RagIndexJob.document_id.in_(document_ids), RagIndexJob.deleted_at.is_(None))
        )
        for row in result.scalars().all():
            row.deleted_at = now
        await self._session.flush()
