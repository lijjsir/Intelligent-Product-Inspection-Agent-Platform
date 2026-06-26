from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.collab import CollabMessage, CollabMessageReceipt, CollabThread, CollabThreadParticipant, FileAsset
from app.repositories.collab_repo import CollabRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.user_repo import UserRepository
from app.schemas.collab import (
    CollabAttachmentPayload,
    CollabMessageActionRequest,
    CollabMessageCreateRequest,
    CollabMessageReceiptResponse,
    CollabMessageResponse,
    CollabTargetResponse,
    CollabThreadCreateRequest,
    CollabThreadParticipantResponse,
    CollabThreadResponse,
    FileAssetResponse,
)
from app.services.object_storage.factory import build_object_storage
from app.services.stream_service import collab_stream_broker


_VALID_SCOPE_PARTICIPANTS = {"user", "meeting_room", "agent"}


class CollabService:
    def __init__(self, session: AsyncSession, org_id: str, user_id: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._repo = CollabRepository(session)
        self._users = UserRepository(session)
        self._meetings = MeetingRepository(session)
        self._storage = build_object_storage()

    async def list_threads(self, limit: int = 100) -> list[CollabThreadResponse]:
        rows = await self._repo.list_threads_for_participant(
            org_id=self._org_id,
            participant_type="user",
            participant_id=self._user_id,
            limit=limit,
        )
        return await self._serialize_threads(rows)

    async def list_targets(self, limit: int = 100) -> list[CollabTargetResponse]:
        users = await self._users.list_by_org_id(self._org_id)
        rooms = await self._meetings.list_joined_rooms(self._org_id, self._user_id, limit=limit)
        agents = await self._meetings.list_active_agent_definitions(self._org_id)

        targets: list[CollabTargetResponse] = []
        for user in users[:limit]:
            user_id = str(user.id)
            if user_id == self._user_id:
                continue
            targets.append(
                CollabTargetResponse(
                    target_type="user",
                    target_id=user_id,
                    label=str(user.username or user.email or user_id),
                    description=str(user.email or user.role or "成员"),
                    group="成员",
                )
            )
        for room in rooms[:limit]:
            targets.append(
                CollabTargetResponse(
                    target_type="meeting_room",
                    target_id=str(room.id),
                    label=str(room.title or "会议室"),
                    description=f"会议室 · {getattr(room, 'status', '') or 'active'}",
                    group="会议室",
                )
            )
        for agent in agents[:limit]:
            targets.append(
                CollabTargetResponse(
                    target_type="agent",
                    target_id=str(agent.id),
                    label=str(agent.name or agent.id),
                    description=str(getattr(agent, "adapter_type", "") or "Agent"),
                    group="Agent",
                )
            )
        return targets

    async def create_thread(self, request: CollabThreadCreateRequest) -> CollabThreadResponse:
        source_type = request.source_type or "user"
        source_id = (request.source_id or self._user_id).strip()
        target_type = request.target_type
        target_id = request.target_id.strip()
        self._validate_participant_type(source_type)
        self._validate_participant_type(target_type)
        if target_type == "agent":
            raise ValidationError("Agent is not a collaboration message recipient; share memory to agent scope or create an agent task")
        if source_type == "user" and source_id != self._user_id:
            raise ForbiddenError("cannot create a collaboration thread for another user")
        await self._ensure_target_visible(target_type, target_id)

        thread_type = f"{source_type}_to_{target_type}"
        existing = await self._repo.find_existing_thread(
            org_id=self._org_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
        )
        if existing is None:
            title = (request.title or "").strip() or await self._default_thread_title(target_type, target_id)
            existing = await self._repo.create_thread(
                org_id=self._org_id,
                thread_type=thread_type,
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                target_id=target_id,
                title=title[:200],
                created_by=self._user_id,
                metadata_json=request.metadata_json,
            )
            await self._ensure_thread_participants(existing)
            await self._session.commit()
        else:
            if str(existing.status or "") == "archived":
                existing = await self._repo.update_thread_status(
                    org_id=self._org_id,
                    thread_id=str(existing.id),
                    status="active",
                ) or existing
                await self._session.commit()
            await self._ensure_user_participates(str(existing.id))
        return (await self._serialize_threads([existing]))[0]

    async def list_messages(self, thread_id: str, limit: int = 200) -> list[CollabMessageResponse]:
        await self._ensure_user_participates(thread_id)
        rows = await self._repo.list_messages(org_id=self._org_id, thread_id=thread_id, limit=limit)
        return await self._serialize_messages(rows)

    async def send_message(
        self,
        thread_id: str,
        request: CollabMessageCreateRequest,
    ) -> CollabMessageResponse:
        thread = await self._ensure_user_participates(thread_id)
        content = request.content.strip()
        attachments = await self._resolve_attachment_assets(request.attachments)
        metadata = dict(request.metadata_json or {})
        if request.attachments:
            metadata["attachment_ids"] = [item.id for item in request.attachments]
        if not content and not attachments and request.message_type not in {"memory_card", "action_request"}:
            raise ValidationError("message content or attachments required")
        message = await self._repo.create_message(
            org_id=self._org_id,
            thread_id=str(thread.id),
            sender_type="user",
            sender_id=self._user_id,
            message_type=request.message_type,
            content=content,
            reply_to_message_id=request.reply_to_message_id,
            metadata_json=metadata or None,
        )
        for index, asset in enumerate(attachments):
            await self._repo.attach_file(
                org_id=self._org_id,
                message_id=str(message.id),
                file_id=str(asset.id),
                sort_order=index,
            )
        await self._create_message_receipts(thread, message)
        await self._session.commit()
        response = (await self._serialize_messages([message]))[0]
        await self._publish_message_created(thread, response)
        return response

    async def mark_read(self, message_id: str) -> CollabMessageReceiptResponse:
        message = await self._repo.get_message(self._org_id, message_id)
        if message is None:
            raise NotFoundError("collaboration message not found")
        thread = await self._ensure_user_participates(str(message.thread_id))
        receipt = await self._repo.get_receipt_for_recipient(
            org_id=self._org_id,
            message_id=message_id,
            recipient_type="user",
            recipient_id=self._user_id,
        )
        if receipt is None:
            receipt = await self._repo.create_receipt(
                org_id=self._org_id,
                message_id=message_id,
                thread_id=str(message.thread_id),
                recipient_type="user",
                recipient_id=self._user_id,
                delivered_at=utcnow(),
                read_at=utcnow(),
            )
        else:
            receipt = await self._repo.mark_receipt_read(receipt)
        await self._session.commit()
        response = self._serialize_receipt(receipt)
        await self._publish_receipt_updated("collab_message_read", response)
        return response

    async def update_action(
        self,
        message_id: str,
        request: CollabMessageActionRequest,
    ) -> CollabMessageReceiptResponse:
        message = await self._repo.get_message(self._org_id, message_id)
        if message is None:
            raise NotFoundError("collaboration message not found")
        thread = await self._ensure_user_participates(str(message.thread_id))
        receipt = await self._repo.get_receipt_for_recipient(
            org_id=self._org_id,
            message_id=message_id,
            recipient_type="user",
            recipient_id=self._user_id,
        )
        if receipt is None:
            receipt = await self._repo.create_receipt(
                org_id=self._org_id,
                message_id=message_id,
                thread_id=str(message.thread_id),
                recipient_type="user",
                recipient_id=self._user_id,
                delivered_at=utcnow(),
            )
        updated = await self._repo.update_receipt_action(receipt, request.action_status)
        if message.message_type == "memory_card" and request.action_status == "done":
            await self._confirm_memory_card(thread, message)
        await self._session.commit()
        response = self._serialize_receipt(updated)
        await self._publish_receipt_updated("collab_message_action_updated", response)
        return response

    async def archive_thread(self, thread_id: str) -> CollabThreadResponse:
        thread = await self._ensure_user_participates(thread_id)
        updated = await self._repo.update_thread_status(
            org_id=self._org_id,
            thread_id=str(thread.id),
            status="archived",
        )
        await self._session.commit()
        return (await self._serialize_threads([updated or thread]))[0]

    async def delete_thread(self, thread_id: str) -> dict[str, str | bool]:
        thread = await self._ensure_user_participates(thread_id)
        if str(thread.created_by) != self._user_id:
            raise ForbiddenError("only the thread owner can delete this collaboration record")
        await self._repo.soft_delete_thread(org_id=self._org_id, thread_id=str(thread.id))
        await self._session.commit()
        await self._publish_thread_deleted(str(thread.id))
        return {"deleted": True, "thread_id": str(thread.id)}

    async def delete_message(self, message_id: str) -> dict[str, str | bool]:
        message = await self._repo.get_message(self._org_id, message_id)
        if message is None:
            raise NotFoundError("collaboration message not found")
        thread = await self._ensure_user_participates(str(message.thread_id))
        is_sender = message.sender_type == "user" and message.sender_id == self._user_id
        is_owner = str(thread.created_by) == self._user_id
        if not (is_sender or is_owner):
            raise ForbiddenError("only the sender or thread owner can delete this message")
        await self._repo.soft_delete_message(org_id=self._org_id, message_id=message_id)
        await self._session.commit()
        await self._publish_message_deleted(str(thread.id), message_id)
        return {"deleted": True, "message_id": message_id}

    async def upload_attachments(self, files: list[UploadFile]) -> list[CollabAttachmentPayload]:
        if not files:
            raise ValidationError("files required")
        bucket = "collab-assets"
        items: list[CollabAttachmentPayload] = []
        for file in files:
            data = await file.read()
            if not data:
                raise ValidationError("empty file is not allowed")
            safe_name = Path(file.filename or "file.bin").name
            suffix = Path(safe_name).suffix
            object_key = f"collab/{self._org_id}/{uuid4().hex}{suffix}"
            checksum = hashlib.sha256(data).hexdigest()
            stored = self._storage.put_bytes(
                bucket=bucket,
                object_key=object_key,
                data=data,
                content_type=file.content_type,
            )
            asset = await self._repo.create_file_asset(
                org_id=self._org_id,
                bucket=str(stored.get("bucket") or bucket),
                object_key=str(stored.get("object_key") or object_key),
                url=str(stored.get("url") or ""),
                file_name=safe_name,
                mime_type=str(stored.get("content_type") or file.content_type or "application/octet-stream"),
                size_bytes=int(stored.get("size_bytes") or len(data)),
                checksum=checksum,
                uploaded_by=self._user_id,
            )
            items.append(self._asset_to_attachment_payload(asset))
        await self._session.commit()
        return items

    async def _ensure_target_visible(self, target_type: str, target_id: str) -> None:
        if target_type == "user":
            user = await self._users.get_by_id(self._org_id, target_id)
            if user is None:
                raise NotFoundError("target user not found")
            if target_id == self._user_id:
                raise ValidationError("cannot create a collaboration thread to self")
            return
        if target_type == "meeting_room":
            member = await self._meetings.get_member(self._org_id, target_id, self._user_id)
            if member is None:
                raise ForbiddenError("not a member of target meeting room")
            return
        if target_type == "agent":
            if not target_id:
                raise ValidationError("target agent required")
            return
        raise ValidationError(f"unsupported collaboration target: {target_type}")

    async def _confirm_memory_card(self, thread: CollabThread, message: CollabMessage) -> None:
        payload = self._memory_payload_from_message(message)
        memory_id = str(payload.get("memory_id") or payload.get("id") or "").strip()
        if not memory_id:
            raise ValidationError("memory card missing memory_id")
        item = await self._meetings.get_memory_item(self._org_id, memory_id)
        if item is None:
            raise NotFoundError("meeting memory not found")
        target_scope_type, target_scope_id = self._memory_card_target_scope(thread)
        source_scope_type, source_scope_id = self._memory_card_source_scope(thread, message, payload)
        existing = await self._meetings.get_memory_scope_binding(
            org_id=self._org_id,
            memory_id=memory_id,
            scope_type=target_scope_type,
            scope_id=target_scope_id,
        )
        if existing is None:
            await self._meetings.create_memory_scope_binding(
                org_id=self._org_id,
                memory_id=memory_id,
                scope_type=target_scope_type,
                scope_id=target_scope_id,
                permission="read",
                created_by=self._user_id,
            )
            await self._meetings.create_memory_transfer_log(
                org_id=self._org_id,
                memory_id=memory_id,
                from_scope_type=source_scope_type,
                from_scope_id=source_scope_id,
                to_scope_type=target_scope_type,
                to_scope_id=target_scope_id,
                transfer_reason="协作消息接收方确认记忆卡片",
                status="executed",
                operator_id=self._user_id,
            )
        content_json = dict(getattr(item, "content_json", None) or {})
        confirmations = list(content_json.get("collab_confirmations") or [])
        confirmation = {
            "thread_id": str(thread.id),
            "message_id": str(message.id),
            "target_scope_type": target_scope_type,
            "target_scope_id": target_scope_id,
        }
        already_confirmed = any(
            isinstance(row, dict)
            and str(row.get("thread_id")) == confirmation["thread_id"]
            and str(row.get("message_id")) == confirmation["message_id"]
            and str(row.get("target_scope_type")) == confirmation["target_scope_type"]
            and str(row.get("target_scope_id")) == confirmation["target_scope_id"]
            for row in confirmations
        )
        if not already_confirmed:
            confirmations.append({
                **confirmation,
                "confirmed_by": self._user_id,
                "confirmed_at": utcnow().isoformat(),
            })
        content_json["collab_confirmations"] = confirmations[-20:]
        content_json["last_collab_confirmed_by"] = self._user_id
        content_json["last_collab_target_scope_type"] = target_scope_type
        content_json["last_collab_target_scope_id"] = target_scope_id
        next_status = None if str(getattr(item, "status", "") or "") in {"confirmed", "active"} else "confirmed"
        await self._meetings.update_memory_item(
            org_id=self._org_id,
            memory_id=memory_id,
            status=next_status,
            content_json=content_json,
        )

    @staticmethod
    def _memory_payload_from_message(message: CollabMessage) -> dict:
        metadata = message.metadata_json or {}
        for key in ("memory", "memory_card", "memory_item"):
            value = metadata.get(key)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _source_context_from_message(message: CollabMessage) -> dict:
        metadata = message.metadata_json or {}
        for key in ("source_context", "source", "origin"):
            value = metadata.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _memory_card_target_scope(self, thread: CollabThread) -> tuple[str, str]:
        if thread.target_type == "meeting_room":
            return "meeting_room", str(thread.target_id)
        if thread.target_type == "user":
            return "user", self._user_id
        raise ValidationError("memory cards can only be confirmed to member or meeting room scopes")

    def _memory_card_source_scope(
        self,
        thread: CollabThread,
        message: CollabMessage,
        payload: dict,
    ) -> tuple[str, str]:
        context = self._source_context_from_message(message)
        source_room_id = str(
            payload.get("source_room_id")
            or payload.get("meeting_room_id")
            or payload.get("room_id")
            or context.get("source_room_id")
            or context.get("room_id")
            or ""
        ).strip()
        if source_room_id:
            return "meeting_room", source_room_id
        return "collab_thread", str(thread.id)

    async def _ensure_user_participates(self, thread_id: str) -> CollabThread:
        thread = await self._repo.get_thread(self._org_id, thread_id)
        if thread is None:
            raise NotFoundError("collaboration thread not found")
        participant = await self._repo.get_participant(
            org_id=self._org_id,
            thread_id=thread_id,
            participant_type="user",
            participant_id=self._user_id,
        )
        if participant is None:
            raise ForbiddenError("not a participant of this collaboration thread")
        return thread

    async def _ensure_thread_participants(self, thread: CollabThread) -> None:
        await self._repo.add_participant(
            org_id=self._org_id,
            thread_id=str(thread.id),
            participant_type=thread.source_type,
            participant_id=str(thread.source_id),
            role="owner",
        )
        await self._repo.add_participant(
            org_id=self._org_id,
            thread_id=str(thread.id),
            participant_type=thread.target_type,
            participant_id=str(thread.target_id),
            role="participant",
        )
        if thread.target_type == "meeting_room":
            members = await self._meetings.list_members(self._org_id, str(thread.target_id))
            for member in members:
                await self._repo.add_participant(
                    org_id=self._org_id,
                    thread_id=str(thread.id),
                    participant_type="user",
                    participant_id=str(member.user_id),
                    role="participant",
                )
        if thread.source_type == "meeting_room":
            members = await self._meetings.list_members(self._org_id, str(thread.source_id))
            for member in members:
                await self._repo.add_participant(
                    org_id=self._org_id,
                    thread_id=str(thread.id),
                    participant_type="user",
                    participant_id=str(member.user_id),
                    role="participant",
                )
        if thread.source_type != "user" and thread.target_type != "user":
            await self._repo.add_participant(
                org_id=self._org_id,
                thread_id=str(thread.id),
                participant_type="user",
                participant_id=self._user_id,
                role="owner",
            )

    async def _create_message_receipts(self, thread: CollabThread, message: CollabMessage) -> None:
        participants = (await self._repo.list_participants(self._org_id, [str(thread.id)])).get(str(thread.id), [])
        now = utcnow()
        for participant in participants:
            is_sender = participant.participant_type == message.sender_type and participant.participant_id == message.sender_id
            await self._repo.create_receipt(
                org_id=self._org_id,
                message_id=str(message.id),
                thread_id=str(thread.id),
                recipient_type=participant.participant_type,
                recipient_id=participant.participant_id,
                delivered_at=now,
                read_at=now if is_sender else None,
            )
        await self._repo.mark_participant_read(
            org_id=self._org_id,
            thread_id=str(thread.id),
            participant_type="user",
            participant_id=self._user_id,
            message_id=str(message.id),
        )

    async def _publish_message_created(self, thread: CollabThread, message: CollabMessageResponse) -> None:
        participants = (await self._repo.list_participants(self._org_id, [str(thread.id)])).get(str(thread.id), [])
        payload = message.model_dump(mode="json")
        for participant in participants:
            if participant.participant_type != "user":
                continue
            await collab_stream_broker.publish(
                str(participant.participant_id),
                {
                    "event": "collab_message_created",
                    "thread_id": str(thread.id),
                    "message": payload,
                    "unread": str(participant.participant_id) != self._user_id,
                },
            )

    async def _publish_receipt_updated(self, event_name: str, receipt: CollabMessageReceiptResponse) -> None:
        participants = (await self._repo.list_participants(self._org_id, [receipt.thread_id])).get(receipt.thread_id, [])
        payload = {
            "event": event_name,
            "thread_id": receipt.thread_id,
            "message_id": receipt.message_id,
            "receipt": receipt.model_dump(mode="json"),
        }
        for participant in participants:
            if participant.participant_type == "user":
                await collab_stream_broker.publish(str(participant.participant_id), payload)

    async def _publish_message_deleted(self, thread_id: str, message_id: str) -> None:
        participants = (await self._repo.list_participants(self._org_id, [thread_id])).get(thread_id, [])
        payload = {
            "event": "collab_message_deleted",
            "thread_id": thread_id,
            "message_id": message_id,
        }
        for participant in participants:
            if participant.participant_type == "user":
                await collab_stream_broker.publish(str(participant.participant_id), payload)

    async def _publish_thread_deleted(self, thread_id: str) -> None:
        participants = (await self._repo.list_participants(self._org_id, [thread_id])).get(thread_id, [])
        payload = {
            "event": "collab_thread_deleted",
            "thread_id": thread_id,
        }
        for participant in participants:
            if participant.participant_type == "user":
                await collab_stream_broker.publish(str(participant.participant_id), payload)

    async def _resolve_attachment_assets(
        self,
        attachments: list[CollabAttachmentPayload],
    ) -> list[FileAsset]:
        ids = [item.id for item in attachments if item.id]
        assets = await self._repo.get_file_assets(self._org_id, ids)
        found_ids = {str(item.id) for item in assets}
        missing = [file_id for file_id in ids if file_id not in found_ids]
        if missing:
            raise NotFoundError(f"attachment not found: {missing[0]}")
        return assets

    async def _serialize_threads(self, rows: list[CollabThread]) -> list[CollabThreadResponse]:
        thread_ids = [str(row.id) for row in rows]
        participants = await self._repo.list_participants(self._org_id, thread_ids)
        unread_counts = await self._repo.unread_counts_for_participant(
            org_id=self._org_id,
            participant_type="user",
            participant_id=self._user_id,
            thread_ids=thread_ids,
        )
        return [
            CollabThreadResponse(
                id=str(row.id),
                org_id=str(row.org_id),
                thread_type=row.thread_type,
                source_type=row.source_type,
                source_id=row.source_id,
                target_type=row.target_type,
                target_id=row.target_id,
                title=row.title,
                status=row.status,
                created_by=str(row.created_by),
                last_message_at=row.last_message_at,
                unread_count=unread_counts.get(str(row.id), 0),
                metadata_json=row.metadata_json,
                participants=[
                    self._serialize_participant(participant)
                    for participant in participants.get(str(row.id), [])
                ],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def _serialize_messages(self, rows: list[CollabMessage]) -> list[CollabMessageResponse]:
        message_ids = [str(row.id) for row in rows]
        attachments = await self._repo.list_message_attachments(self._org_id, message_ids)
        receipts = await self._repo.list_receipts(self._org_id, message_ids)
        return [
            CollabMessageResponse(
                id=str(row.id),
                org_id=str(row.org_id),
                thread_id=str(row.thread_id),
                sender_type=row.sender_type,
                sender_id=row.sender_id,
                message_type=row.message_type,
                content=row.content,
                reply_to_message_id=str(row.reply_to_message_id) if row.reply_to_message_id else None,
                metadata_json=row.metadata_json,
                attachments=[
                    self._serialize_file_asset(asset)
                    for asset in attachments.get(str(row.id), [])
                ],
                receipts=[
                    self._serialize_receipt(receipt)
                    for receipt in receipts.get(str(row.id), [])
                ],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    @staticmethod
    def _serialize_participant(row: CollabThreadParticipant) -> CollabThreadParticipantResponse:
        return CollabThreadParticipantResponse(
            id=str(row.id),
            thread_id=str(row.thread_id),
            participant_type=row.participant_type,
            participant_id=row.participant_id,
            role=row.role,
            last_read_message_id=str(row.last_read_message_id) if row.last_read_message_id else None,
            joined_at=row.created_at,
        )

    @staticmethod
    def _serialize_receipt(row: CollabMessageReceipt) -> CollabMessageReceiptResponse:
        return CollabMessageReceiptResponse(
            id=str(row.id),
            message_id=str(row.message_id),
            thread_id=str(row.thread_id),
            recipient_type=row.recipient_type,
            recipient_id=row.recipient_id,
            delivered_at=row.delivered_at,
            read_at=row.read_at,
            acted_at=row.acted_at,
            action_status=row.action_status,
        )

    @staticmethod
    def _serialize_file_asset(row: FileAsset) -> FileAssetResponse:
        return FileAssetResponse(
            id=str(row.id),
            bucket=row.bucket,
            object_key=row.object_key,
            url=row.url,
            file_name=row.file_name,
            mime_type=row.mime_type,
            size_bytes=int(row.size_bytes or 0),
            checksum=row.checksum,
        )

    @staticmethod
    def _asset_to_attachment_payload(row: FileAsset) -> CollabAttachmentPayload:
        mime_type = row.mime_type or "application/octet-stream"
        kind = "image" if mime_type.startswith("image/") else "file"
        return CollabAttachmentPayload(
            id=str(row.id),
            name=row.file_name,
            url=row.url,
            content_type=row.mime_type,
            size_bytes=int(row.size_bytes or 0),
            kind=kind,
            bucket=row.bucket,
            object_key=row.object_key,
        )

    async def _default_thread_title(self, target_type: str, target_id: str) -> str:
        if target_type == "user":
            user = await self._users.get_by_id(self._org_id, target_id)
            return f"发给 {user.username if user else target_id}"
        if target_type == "meeting_room":
            room = await self._meetings.get_room(self._org_id, target_id)
            return f"发给会议室 {room.title if room else target_id}"
        return "Agent 处理记录"

    @staticmethod
    def _validate_participant_type(value: str) -> None:
        if value not in _VALID_SCOPE_PARTICIPANTS:
            raise ValidationError(f"unsupported collaboration participant type: {value}")
