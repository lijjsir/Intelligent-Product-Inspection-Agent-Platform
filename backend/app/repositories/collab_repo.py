from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.collab import (
    CollabMessage,
    CollabMessageReceipt,
    CollabThread,
    CollabThreadParticipant,
    FileAsset,
    MessageAttachment,
)


class CollabRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_thread(self, org_id: str, thread_id: str) -> CollabThread | None:
        result = await self._session.execute(
            select(CollabThread).where(
                CollabThread.org_id == org_id,
                CollabThread.id == thread_id,
                CollabThread.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def find_existing_thread(
        self,
        *,
        org_id: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
    ) -> CollabThread | None:
        direct = and_(
            CollabThread.source_type == source_type,
            CollabThread.source_id == source_id,
            CollabThread.target_type == target_type,
            CollabThread.target_id == target_id,
        )
        reverse = and_(
            CollabThread.source_type == target_type,
            CollabThread.source_id == target_id,
            CollabThread.target_type == source_type,
            CollabThread.target_id == source_id,
        )
        result = await self._session.execute(
            select(CollabThread)
            .where(
                CollabThread.org_id == org_id,
                CollabThread.deleted_at.is_(None),
                or_(direct, reverse),
            )
            .order_by(CollabThread.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_thread(
        self,
        *,
        org_id: str,
        thread_type: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        title: str,
        created_by: str,
        metadata_json: dict | None = None,
    ) -> CollabThread:
        row = CollabThread(
            org_id=org_id,
            thread_type=thread_type,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            title=title,
            status="active",
            created_by=created_by,
            metadata_json=metadata_json,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def add_participant(
        self,
        *,
        org_id: str,
        thread_id: str,
        participant_type: str,
        participant_id: str,
        role: str = "participant",
    ) -> CollabThreadParticipant:
        existing = await self.get_participant(
            org_id=org_id,
            thread_id=thread_id,
            participant_type=participant_type,
            participant_id=participant_id,
        )
        if existing:
            return existing
        row = CollabThreadParticipant(
            org_id=org_id,
            thread_id=thread_id,
            participant_type=participant_type,
            participant_id=participant_id,
            role=role,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def get_participant(
        self,
        *,
        org_id: str,
        thread_id: str,
        participant_type: str,
        participant_id: str,
    ) -> CollabThreadParticipant | None:
        result = await self._session.execute(
            select(CollabThreadParticipant).where(
                CollabThreadParticipant.org_id == org_id,
                CollabThreadParticipant.thread_id == thread_id,
                CollabThreadParticipant.participant_type == participant_type,
                CollabThreadParticipant.participant_id == participant_id,
                CollabThreadParticipant.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_threads_for_participant(
        self,
        *,
        org_id: str,
        participant_type: str,
        participant_id: str,
        limit: int = 100,
    ) -> list[CollabThread]:
        result = await self._session.execute(
            select(CollabThread)
            .join(CollabThreadParticipant, CollabThreadParticipant.thread_id == CollabThread.id)
            .where(
                CollabThread.org_id == org_id,
                CollabThread.deleted_at.is_(None),
                CollabThreadParticipant.org_id == org_id,
                CollabThreadParticipant.participant_type == participant_type,
                CollabThreadParticipant.participant_id == participant_id,
                CollabThreadParticipant.deleted_at.is_(None),
            )
            .order_by(CollabThread.last_message_at.desc(), CollabThread.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_participants(
        self,
        org_id: str,
        thread_ids: Sequence[str],
    ) -> dict[str, list[CollabThreadParticipant]]:
        if not thread_ids:
            return {}
        result = await self._session.execute(
            select(CollabThreadParticipant).where(
                CollabThreadParticipant.org_id == org_id,
                CollabThreadParticipant.thread_id.in_(list(thread_ids)),
                CollabThreadParticipant.deleted_at.is_(None),
            )
        )
        grouped: dict[str, list[CollabThreadParticipant]] = defaultdict(list)
        for row in result.scalars().all():
            grouped[str(row.thread_id)].append(row)
        return grouped

    async def unread_counts_for_participant(
        self,
        *,
        org_id: str,
        participant_type: str,
        participant_id: str,
        thread_ids: Sequence[str],
    ) -> dict[str, int]:
        if not thread_ids:
            return {}
        result = await self._session.execute(
            select(CollabMessageReceipt.thread_id, func.count(CollabMessageReceipt.id))
            .where(
                CollabMessageReceipt.org_id == org_id,
                CollabMessageReceipt.thread_id.in_(list(thread_ids)),
                CollabMessageReceipt.recipient_type == participant_type,
                CollabMessageReceipt.recipient_id == participant_id,
                CollabMessageReceipt.read_at.is_(None),
                CollabMessageReceipt.deleted_at.is_(None),
            )
            .group_by(CollabMessageReceipt.thread_id)
        )
        return {str(thread_id): int(count) for thread_id, count in result.all()}

    async def create_message(
        self,
        *,
        org_id: str,
        thread_id: str,
        sender_type: str,
        sender_id: str,
        message_type: str,
        content: str,
        reply_to_message_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> CollabMessage:
        row = CollabMessage(
            org_id=org_id,
            thread_id=thread_id,
            sender_type=sender_type,
            sender_id=sender_id,
            message_type=message_type,
            content=content,
            reply_to_message_id=reply_to_message_id,
            metadata_json=metadata_json,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        await self.touch_thread(org_id=org_id, thread_id=thread_id, last_message_at=row.created_at)
        return row

    async def list_messages(
        self,
        *,
        org_id: str,
        thread_id: str,
        limit: int = 200,
    ) -> list[CollabMessage]:
        result = await self._session.execute(
            select(CollabMessage)
            .where(
                CollabMessage.org_id == org_id,
                CollabMessage.thread_id == thread_id,
                CollabMessage.deleted_at.is_(None),
            )
            .order_by(CollabMessage.created_at.asc(), CollabMessage.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_message(self, org_id: str, message_id: str) -> CollabMessage | None:
        result = await self._session.execute(
            select(CollabMessage).where(
                CollabMessage.org_id == org_id,
                CollabMessage.id == message_id,
                CollabMessage.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_receipt(
        self,
        *,
        org_id: str,
        message_id: str,
        thread_id: str,
        recipient_type: str,
        recipient_id: str,
        delivered_at: datetime | None = None,
        read_at: datetime | None = None,
    ) -> CollabMessageReceipt:
        row = CollabMessageReceipt(
            org_id=org_id,
            message_id=message_id,
            thread_id=thread_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            delivered_at=delivered_at,
            read_at=read_at,
            action_status="done" if read_at else "pending",
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def get_receipt_for_recipient(
        self,
        *,
        org_id: str,
        message_id: str,
        recipient_type: str,
        recipient_id: str,
    ) -> CollabMessageReceipt | None:
        result = await self._session.execute(
            select(CollabMessageReceipt).where(
                CollabMessageReceipt.org_id == org_id,
                CollabMessageReceipt.message_id == message_id,
                CollabMessageReceipt.recipient_type == recipient_type,
                CollabMessageReceipt.recipient_id == recipient_id,
                CollabMessageReceipt.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_receipts(
        self,
        org_id: str,
        message_ids: Sequence[str],
    ) -> dict[str, list[CollabMessageReceipt]]:
        if not message_ids:
            return {}
        result = await self._session.execute(
            select(CollabMessageReceipt).where(
                CollabMessageReceipt.org_id == org_id,
                CollabMessageReceipt.message_id.in_(list(message_ids)),
                CollabMessageReceipt.deleted_at.is_(None),
            )
        )
        grouped: dict[str, list[CollabMessageReceipt]] = defaultdict(list)
        for row in result.scalars().all():
            grouped[str(row.message_id)].append(row)
        return grouped

    async def mark_receipt_read(self, receipt: CollabMessageReceipt) -> CollabMessageReceipt:
        now = utcnow()
        receipt.read_at = receipt.read_at or now
        await self._session.flush()
        await self._session.refresh(receipt, attribute_names=["created_at", "updated_at"])
        return receipt

    async def mark_participant_read(
        self,
        *,
        org_id: str,
        thread_id: str,
        participant_type: str,
        participant_id: str,
        message_id: str,
    ) -> None:
        participant = await self.get_participant(
            org_id=org_id,
            thread_id=thread_id,
            participant_type=participant_type,
            participant_id=participant_id,
        )
        if participant is None:
            return
        participant.last_read_message_id = message_id
        await self._session.flush()

    async def update_receipt_action(
        self,
        receipt: CollabMessageReceipt,
        action_status: str,
    ) -> CollabMessageReceipt:
        now = utcnow()
        receipt.read_at = receipt.read_at or now
        receipt.acted_at = now
        receipt.action_status = action_status
        await self._session.flush()
        await self._session.refresh(receipt, attribute_names=["created_at", "updated_at"])
        return receipt

    async def create_file_asset(
        self,
        *,
        org_id: str,
        bucket: str,
        object_key: str,
        url: str,
        file_name: str,
        mime_type: str | None,
        size_bytes: int,
        checksum: str,
        uploaded_by: str,
    ) -> FileAsset:
        row = FileAsset(
            org_id=org_id,
            bucket=bucket,
            object_key=object_key,
            url=url,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
            uploaded_by=uploaded_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def get_file_assets(self, org_id: str, file_ids: Sequence[str]) -> list[FileAsset]:
        if not file_ids:
            return []
        result = await self._session.execute(
            select(FileAsset).where(
                FileAsset.org_id == org_id,
                FileAsset.id.in_(list(file_ids)),
                FileAsset.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def attach_file(
        self,
        *,
        org_id: str,
        message_id: str,
        file_id: str,
        sort_order: int,
    ) -> MessageAttachment:
        row = MessageAttachment(
            org_id=org_id,
            message_id=message_id,
            file_id=file_id,
            sort_order=sort_order,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def list_message_attachments(
        self,
        org_id: str,
        message_ids: Sequence[str],
    ) -> dict[str, list[FileAsset]]:
        if not message_ids:
            return {}
        result = await self._session.execute(
            select(MessageAttachment.message_id, FileAsset)
            .join(FileAsset, FileAsset.id == MessageAttachment.file_id)
            .where(
                MessageAttachment.org_id == org_id,
                MessageAttachment.message_id.in_(list(message_ids)),
                MessageAttachment.deleted_at.is_(None),
                FileAsset.deleted_at.is_(None),
            )
            .order_by(MessageAttachment.sort_order.asc(), MessageAttachment.created_at.asc())
        )
        grouped: dict[str, list[FileAsset]] = defaultdict(list)
        for message_id, asset in result.all():
            grouped[str(message_id)].append(asset)
        return grouped

    async def touch_thread(
        self,
        *,
        org_id: str,
        thread_id: str,
        last_message_at: datetime | None = None,
    ) -> None:
        thread = await self.get_thread(org_id, thread_id)
        if thread is None:
            return
        thread.last_message_at = last_message_at or utcnow()
        await self._session.flush()

    async def update_thread_status(
        self,
        *,
        org_id: str,
        thread_id: str,
        status: str,
    ) -> CollabThread | None:
        thread = await self.get_thread(org_id, thread_id)
        if thread is None:
            return None
        thread.status = status
        await self._session.flush()
        await self._session.refresh(thread, attribute_names=["created_at", "updated_at"])
        return thread

    async def soft_delete_thread(self, *, org_id: str, thread_id: str) -> CollabThread | None:
        thread = await self.get_thread(org_id, thread_id)
        if thread is None:
            return None
        thread.deleted_at = utcnow()
        thread.status = "deleted"
        metadata = dict(thread.metadata_json or {})
        metadata["deleted_at"] = thread.deleted_at.isoformat()
        thread.metadata_json = metadata
        await self._session.flush()
        await self._session.refresh(thread, attribute_names=["created_at", "updated_at"])
        return thread

    async def soft_delete_message(self, *, org_id: str, message_id: str) -> CollabMessage | None:
        message = await self.get_message(org_id, message_id)
        if message is None:
            return None
        message.deleted_at = utcnow()
        metadata = dict(message.metadata_json or {})
        metadata["deleted_at"] = message.deleted_at.isoformat()
        message.metadata_json = metadata
        await self._session.flush()
        await self._session.refresh(message, attribute_names=["created_at", "updated_at"])
        return message
