from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.core.permissions import ROLE_ADMIN, ROLE_USER
from app.models.collab import CollabMessage, CollabMessageReceipt, CollabThread, CollabThreadParticipant, FileAsset
from app.models.memory import MemoryEvidence
from app.repositories.collab_repo import CollabRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.user_repo import UserRepository
from app.schemas.collab import (
    CollabAttachmentPayload,
    CollabActionRequestCreateRequest,
    CollabMessageActionRequest,
    CollabMessageCreateRequest,
    CollabMessageReceiptResponse,
    CollabMessageResponse,
    CollabTargetResponse,
    CollabThreadCreateRequest,
    CollabThreadParticipantResponse,
    CollabThreadResponse,
    CollabWorkItemResponse,
    CollabWorkItemSummaryResponse,
    FileAssetResponse,
)
from app.services.object_storage.factory import build_object_storage
from app.services.stream_service import collab_stream_broker
from app.services.meeting_service import MeetingService
from app.schemas.meeting import MeetingMemoryShareDecisionRequest, MeetingMemoryShareRejectRequest


_VALID_SCOPE_PARTICIPANTS = {"user", "meeting_room", "agent"}


class CollabService:
    def __init__(self, session: AsyncSession, org_id: str, user_id: str, role: str = ROLE_USER):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._role = role or ROLE_USER
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

    async def list_work_items(
        self,
        *,
        view: str = "pending",
        item_type: str | None = None,
        scope_type: str | None = None,
        room_id: str | None = None,
        limit: int = 200,
    ) -> list[CollabWorkItemResponse]:
        if view not in {"pending", "initiated", "processed"}:
            raise ValidationError("unsupported collaboration work item view")
        items: list[CollabWorkItemResponse] = []
        if item_type in {None, "memory_share"}:
            transfer_rows = await self._meetings.list_memory_transfer_logs(
                org_id=self._org_id,
                limit=limit,
            )
            for row in transfer_rows:
                if (
                    str(getattr(row, "from_scope_type", "") or "")
                    == str(getattr(row, "to_scope_type", "") or "")
                    and str(getattr(row, "from_scope_id", "") or "")
                    == str(getattr(row, "to_scope_id", "") or "")
                ):
                    continue
                normalized_status = self._normalize_transfer_status(str(getattr(row, "status", "") or ""))
                requested_by = str(
                    getattr(row, "requested_by", None)
                    or getattr(row, "operator_id", None)
                    or ""
                )
                can_handle = await self._can_handle_memory_share(row)
                relevant = (
                    requested_by == self._user_id
                    or can_handle
                    or str(getattr(row, "decided_by", None) or "") == self._user_id
                )
                if view == "pending" and not (normalized_status == "pending_approval" and can_handle):
                    continue
                if view == "initiated" and requested_by != self._user_id:
                    continue
                if view == "processed" and not (normalized_status != "pending_approval" and relevant):
                    continue
                if scope_type and scope_type not in {
                    str(getattr(row, "from_scope_type", "") or ""),
                    str(getattr(row, "to_scope_type", "") or ""),
                }:
                    continue
                if room_id and room_id not in {
                    str(getattr(row, "from_scope_id", "") or ""),
                    str(getattr(row, "to_scope_id", "") or ""),
                }:
                    continue
                items.append(await self._serialize_memory_share_work_item(row, can_handle=can_handle))

        if item_type in {None, "action_request"}:
            action_rows = await self._repo.list_action_requests_for_user(
                org_id=self._org_id,
                user_id=self._user_id,
                limit=limit,
            )
            message_ids = [str(message.id) for message, _, _ in action_rows]
            receipts = await self._repo.list_receipts(self._org_id, message_ids)
            for message, receipt, thread in action_rows:
                message_receipts = receipts.get(str(message.id), [])
                status = self._action_request_status(message, message_receipts)
                initiated = str(message.sender_id) == self._user_id
                can_handle = await self._can_handle_action_request(thread, message, receipt)
                relevant = initiated or receipt is not None
                if view == "pending" and not (status == "pending" and can_handle):
                    continue
                if view == "initiated" and not initiated:
                    continue
                if view == "processed" and not (status != "pending" and relevant):
                    continue
                if scope_type and scope_type not in {str(thread.source_type), str(thread.target_type)}:
                    continue
                if room_id and not (
                    (str(thread.source_type) == "meeting_room" and str(thread.source_id) == room_id)
                    or (str(thread.target_type) == "meeting_room" and str(thread.target_id) == room_id)
                ):
                    continue
                items.append(
                    await self._serialize_action_request_work_item(
                        message,
                        receipt,
                        thread,
                        message_receipts,
                    )
                )
        items.sort(
            key=lambda item: item.updated_at or item.created_at or utcnow(),
            reverse=True,
        )
        return items[:limit]

    async def get_work_item_summary(self) -> CollabWorkItemSummaryResponse:
        pending, initiated, processed = await self._list_work_item_counts()
        return CollabWorkItemSummaryResponse(
            pending_count=pending,
            initiated_count=initiated,
            processed_count=processed,
        )

    async def _list_work_item_counts(self) -> tuple[int, int, int]:
        pending = await self.list_work_items(view="pending", limit=500)
        initiated = await self.list_work_items(view="initiated", limit=500)
        processed = await self.list_work_items(view="processed", limit=500)
        return len(pending), len(initiated), len(processed)

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
        *,
        _structured_request: bool = False,
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

    async def send_work_item_comment(
        self,
        thread_id: str,
        request: CollabMessageCreateRequest,
    ) -> CollabMessageResponse:
        if request.message_type != "text" or not request.reply_to_message_id:
            raise ValidationError("collaboration center only accepts comments attached to a work item")
        parent = await self._repo.get_message(self._org_id, request.reply_to_message_id)
        if (
            parent is None
            or str(parent.thread_id) != thread_id
            or str(parent.message_type) not in {"action_request", "memory_card"}
        ):
            raise ValidationError("comment must reply to an action request or memory work item")
        return await self.send_message(thread_id, request)

    async def create_action_request(
        self,
        request: CollabActionRequestCreateRequest,
    ) -> CollabWorkItemResponse:
        thread = await self.create_thread(
            CollabThreadCreateRequest(
                target_type=request.target_type,
                target_id=request.target_id,
                title=request.title,
                source_type="user",
                source_id=self._user_id,
                metadata_json={"workflow_type": "structured_action_request"},
            )
        )
        metadata = {
            "action_request": {
                "title": request.title,
                "description": request.description,
                "source_link": request.source_link,
                "source_context": request.source_context or {},
                "idempotency_key": request.idempotency_key,
            },
            "source_context": request.source_context or {},
            "source_link": request.source_link,
            "idempotency_key": request.idempotency_key,
        }
        message = await self.send_message(
            thread.id,
            CollabMessageCreateRequest(
                content=request.description,
                message_type="action_request",
                attachments=request.attachments,
                metadata_json=metadata,
            ),
            _structured_request=True,
        )
        rows = await self._repo.list_action_requests_for_user(
            org_id=self._org_id,
            user_id=self._user_id,
            limit=200,
        )
        receipts_by_message = await self._repo.list_receipts(self._org_id, [message.id])
        for row_message, receipt, row_thread in rows:
            if str(row_message.id) == message.id:
                work_item = await self._serialize_action_request_work_item(
                    row_message,
                    receipt,
                    row_thread,
                    receipts_by_message.get(message.id, []),
                )
                await self._publish_work_item_event(row_thread, work_item, "work_item_created")
                return work_item
        raise NotFoundError("created collaboration work item not found")

    async def mark_read(self, message_id: str) -> CollabMessageReceiptResponse:
        message = await self._repo.get_message(self._org_id, message_id)
        if message is None:
            raise NotFoundError("collaboration message not found")
        await self._ensure_user_participates(str(message.thread_id))
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
        await self._ensure_meeting_room_action_available(thread, message, receipt, request.action_status)
        if message.message_type == "memory_card":
            if request.action_status == "rejected" and not str(request.decision_note or "").strip():
                raise ValidationError("rejecting a memory share requires a reason")
            await self._handle_memory_card_decision(
                thread,
                message,
                action_status=request.action_status,
                decision_note=request.decision_note,
            )
        previous_action_status = str(getattr(receipt, "action_status", "") or "pending")
        updated = await self._repo.update_receipt_action(receipt, request.action_status)
        status_message = None
        if previous_action_status != request.action_status:
            status_message = await self._create_action_status_message(thread, message, updated)
        await self._session.commit()
        response = self._serialize_receipt(updated)
        if status_message is not None:
            status_response = (await self._serialize_messages([status_message]))[0]
            await self._publish_message_created(thread, status_response)
        await self._publish_receipt_updated("collab_message_action_updated", response)
        if message.message_type == "action_request":
            receipts = (await self._repo.list_receipts(self._org_id, [str(message.id)])).get(str(message.id), [])
            work_item = await self._serialize_action_request_work_item(message, updated, thread, receipts)
            await self._publish_work_item_event(thread, work_item, "work_item_completed")
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

    async def _serialize_memory_share_work_item(
        self,
        row: Any,
        *,
        can_handle: bool,
    ) -> CollabWorkItemResponse:
        item = await self._meetings.get_memory_item(self._org_id, str(row.memory_id))
        content_json = dict(getattr(item, "content_json", None) or {}) if item is not None else {}
        requested_by = str(
            getattr(row, "requested_by", None)
            or getattr(row, "operator_id", None)
            or ""
        ) or None
        status = self._normalize_transfer_status(str(getattr(row, "status", "") or ""))
        allowed_actions: list[str] = []
        if status == "pending_approval" and can_handle:
            allowed_actions.extend(["approve", "reject"])
        if status == "pending_approval" and requested_by == self._user_id:
            allowed_actions.append("cancel")
        source = await self._scope_descriptor(
            str(getattr(row, "from_scope_type", "") or ""),
            str(getattr(row, "from_scope_id", "") or ""),
        )
        target = await self._scope_descriptor(
            str(getattr(row, "to_scope_type", "") or ""),
            str(getattr(row, "to_scope_id", "") or ""),
        )
        requester_label = await self._user_display_name(requested_by) if requested_by else None
        history = [
            {
                "action": "requested",
                "actor_id": requested_by,
                "actor_label": requester_label,
                "at": getattr(row, "created_at", None),
                "note": getattr(row, "transfer_reason", None),
            }
        ]
        if status != "pending_approval":
            history.append(
                {
                    "action": status,
                    "actor_id": str(getattr(row, "decided_by", None) or "") or None,
                    "at": getattr(row, "decided_at", None) or getattr(row, "updated_at", None),
                    "note": getattr(row, "decision_note", None),
                }
            )
        return CollabWorkItemResponse(
            id=f"memory_share:{row.id}",
            resource_id=str(row.id),
            item_type="memory_share",
            title=str(content_json.get("title") or getattr(item, "content_summary", "") or row.memory_id),
            description=str(content_json.get("content") or getattr(item, "content_summary", "") or ""),
            source=source,
            target=target,
            requested_by=requested_by,
            requester_label=requester_label,
            status=status,
            evidence=[
                dict(entry)
                for entry in list(content_json.get("source_refs") or content_json.get("evidence_refs") or [])
                if isinstance(entry, dict)
            ],
            source_link=(
                f"/app/meetings?room_id={source.get('id')}&memory_id={row.memory_id}"
                if source.get("type") == "meeting_room"
                else None
            ),
            allowed_actions=allowed_actions,
            decision_note=getattr(row, "decision_note", None),
            decided_by=str(getattr(row, "decided_by", None) or "") or None,
            decided_at=getattr(row, "decided_at", None),
            history=history,
            payload={
                "memory_id": str(row.memory_id),
                "share_reason": getattr(row, "transfer_reason", None),
                "memory_status": str(getattr(item, "status", "") or ""),
                "source_refs": list(content_json.get("source_refs") or []),
                "affected_objects": content_json.get("affected_objects") or {},
                "shared_scopes": list(content_json.get("shared_scopes") or []),
            },
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )

    async def _serialize_action_request_work_item(
        self,
        message: CollabMessage,
        receipt: CollabMessageReceipt | None,
        thread: CollabThread,
        receipts: list[CollabMessageReceipt],
    ) -> CollabWorkItemResponse:
        metadata = dict(message.metadata_json or {})
        request_payload = dict(metadata.get("action_request") or {})
        status = self._action_request_status(message, receipts)
        can_handle = await self._can_handle_action_request(thread, message, receipt)
        allowed_actions = ["accepted", "rejected", "done"] if status == "pending" and can_handle else []
        attachments = await self._repo.list_message_attachments(self._org_id, [str(message.id)])
        source = await self._scope_descriptor(str(thread.source_type), str(thread.source_id))
        target = await self._scope_descriptor(str(thread.target_type), str(thread.target_id))
        requested_by = str(message.sender_id) if message.sender_type == "user" else None
        requester_label = await self._user_display_name(requested_by) if requested_by else None
        acted_receipt = next(
            (
                row
                for row in receipts
                if str(row.recipient_id) != str(message.sender_id)
                and str(row.action_status or "pending") != "pending"
            ),
            None,
        )
        history = [
            {
                "action": "requested",
                "actor_id": requested_by,
                "actor_label": requester_label,
                "at": message.created_at,
            }
        ]
        if acted_receipt is not None:
            history.append(
                {
                    "action": str(acted_receipt.action_status),
                    "actor_id": str(acted_receipt.recipient_id),
                    "at": acted_receipt.acted_at or acted_receipt.updated_at,
                }
            )
        evidence = [
            {
                "type": "attachment",
                "id": str(asset.id),
                "name": asset.file_name,
                "url": asset.url,
            }
            for asset in attachments.get(str(message.id), [])
        ]
        source_context = request_payload.get("source_context") or metadata.get("source_context")
        if isinstance(source_context, dict) and source_context:
            evidence.append({"type": "source_context", **source_context})
        return CollabWorkItemResponse(
            id=f"action_request:{message.id}",
            resource_id=str(message.id),
            item_type="action_request",
            title=str(request_payload.get("title") or thread.title or "处理请求"),
            description=str(request_payload.get("description") or message.content or ""),
            source=source,
            target=target,
            requested_by=requested_by,
            requester_label=requester_label,
            status=status,
            evidence=evidence,
            source_link=str(request_payload.get("source_link") or metadata.get("source_link") or "") or None,
            allowed_actions=allowed_actions,
            decided_by=(str(acted_receipt.recipient_id) if acted_receipt is not None else None),
            decided_at=(acted_receipt.acted_at if acted_receipt is not None else None),
            history=history,
            payload={
                "thread_id": str(thread.id),
                "message_id": str(message.id),
                "source_context": source_context or {},
            },
            created_at=message.created_at,
            updated_at=message.updated_at,
        )

    async def _can_handle_memory_share(self, row: Any) -> bool:
        if self._normalize_transfer_status(str(getattr(row, "status", "") or "")) != "pending_approval":
            return False
        scope_type = str(getattr(row, "to_scope_type", "") or "")
        scope_id = str(getattr(row, "to_scope_id", "") or "")
        if scope_type == "user":
            return scope_id == self._user_id
        if scope_type == "org_space":
            return self._role == ROLE_ADMIN
        if scope_type == "meeting_room":
            return await self._is_meeting_host(scope_id)
        return False

    async def _can_handle_action_request(
        self,
        thread: CollabThread,
        message: CollabMessage,
        receipt: CollabMessageReceipt | None,
    ) -> bool:
        if str(message.sender_id) == self._user_id or receipt is None:
            return False
        if str(receipt.action_status or "pending") != "pending":
            return False
        if str(thread.target_type) == "user":
            return str(thread.target_id) == self._user_id
        if str(thread.target_type) == "meeting_room":
            return await self._is_meeting_host(str(thread.target_id))
        return False

    async def _is_meeting_host(self, room_id: str) -> bool:
        member = await self._meetings.get_member(self._org_id, room_id, self._user_id)
        if member is not None and str(getattr(member, "role", "") or "") == "host":
            return True
        room = await self._meetings.get_room(self._org_id, room_id)
        return room is not None and str(getattr(room, "created_by", "") or "") == self._user_id

    async def _scope_descriptor(self, scope_type: str, scope_id: str) -> dict[str, str]:
        if scope_type == "meeting_room":
            room = await self._meetings.get_room(self._org_id, scope_id)
            return {
                "type": scope_type,
                "id": scope_id,
                "label": str(getattr(room, "title", "") or "会议室"),
            }
        if scope_type == "user":
            user = await self._users.get_by_id(self._org_id, scope_id)
            return {
                "type": scope_type,
                "id": scope_id,
                "label": str(getattr(user, "username", "") or getattr(user, "email", "") or "成员"),
            }
        if scope_type == "org_space":
            return {"type": scope_type, "id": scope_id, "label": "组织共享空间"}
        if scope_type == "agent":
            return {"type": scope_type, "id": scope_id, "label": "Agent"}
        if scope_type == "collab_thread":
            return {"type": scope_type, "id": scope_id, "label": "协作工作项"}
        return {"type": scope_type, "id": scope_id, "label": scope_type or "未知范围"}

    @staticmethod
    def _normalize_transfer_status(status: str) -> str:
        return "executed" if status == "confirmed" else status

    @staticmethod
    def _action_request_status(
        message: CollabMessage,
        receipts: list[CollabMessageReceipt],
    ) -> str:
        actionable = [
            row
            for row in receipts
            if not (
                row.recipient_type == message.sender_type
                and str(row.recipient_id) == str(message.sender_id)
            )
        ]
        handled = next(
            (str(row.action_status) for row in actionable if str(row.action_status or "pending") != "pending"),
            None,
        )
        return handled or "pending"

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

    async def _handle_memory_card_decision(
        self,
        thread: CollabThread,
        message: CollabMessage,
        *,
        action_status: str,
        decision_note: str | None,
    ) -> None:
        payload = self._memory_payload_from_message(message)
        memory_id = str(payload.get("memory_id") or payload.get("id") or "").strip()
        if not memory_id:
            raise ValidationError("memory card missing memory_id")
        item = await self._meetings.get_memory_item(self._org_id, memory_id)
        if item is None:
            raise NotFoundError("meeting memory not found")
        target_scope_type, target_scope_id = self._memory_card_target_scope(thread)
        source_scope_type, source_scope_id = self._memory_card_source_scope(thread, message, payload)
        same_scope = (
            source_scope_type == target_scope_type
            and source_scope_id == target_scope_id
        )
        if same_scope:
            existing_confirmations = list(
                (getattr(item, "content_json", None) or {}).get("collab_confirmations") or []
            )
            if any(
                isinstance(row, dict)
                and str(row.get("message_id") or "") == str(message.id)
                and not str(row.get("transfer_id") or "")
                for row in existing_confirmations
            ):
                raise ConflictError("memory card has already been handled")
            if action_status == "rejected":
                rejected_content = dict(getattr(item, "content_json", None) or {})
                rejected_content.update(
                    {
                        "governance_status": "rejected",
                        "rejected_by": self._user_id,
                        "rejected_at": utcnow().isoformat(),
                        "rejection_note": str(decision_note or "").strip(),
                    }
                )
                item = await self._meetings.update_memory_item(
                    org_id=self._org_id,
                    memory_id=memory_id,
                    status="rejected",
                    review_status="rejected",
                    readiness_status="blocked",
                    readiness_blockers=["review_status_rejected"],
                    content_json=rejected_content,
                )
            elif str(getattr(item, "status", "") or "") == "candidate":
                if source_scope_type != "meeting_room" or source_scope_id in {"", "legacy"}:
                    raise ValidationError("legacy candidate memory must be confirmed in its source meeting room first")
                source_binding = await self._meetings.get_memory_scope_binding(
                    org_id=self._org_id,
                    memory_id=memory_id,
                    scope_type="meeting_room",
                    scope_id=source_scope_id,
                )
                if source_binding is None:
                    await self._meetings.create_memory_scope_binding(
                        org_id=self._org_id,
                        memory_id=memory_id,
                        scope_type="meeting_room",
                        scope_id=source_scope_id,
                        permission="read",
                        created_by=str(message.sender_id),
                    )
                source_content = dict(getattr(item, "content_json", None) or {})
                source_content.update(
                    {
                        "confirmed_by": str(message.sender_id),
                        "confirmed_at": utcnow().isoformat(),
                        "governance_status": "confirmed",
                        "published_scope": "meeting_room",
                        "source_room_id": source_scope_id,
                    }
                )
                item = await self._meetings.update_memory_item(
                    org_id=self._org_id,
                    memory_id=memory_id,
                    status="confirmed",
                    review_status="approved",
                    readiness_status="ready",
                    readiness_blockers=[],
                    content_json=source_content,
                    scope_json={
                        "scope_type": "meeting_room",
                        "scope_id": source_scope_id,
                        "meeting_room_id": source_scope_id,
                        "room_id": source_scope_id,
                        "source_room_id": source_scope_id,
                    },
                )
            await self._record_memory_card_confirmation(
                item,
                thread,
                message,
                memory_id=memory_id,
                target_scope_type=target_scope_type,
                target_scope_id=target_scope_id,
                transfer_id=None,
                decision="rejected" if action_status == "rejected" else "confirmed",
            )
            return

        if str(getattr(item, "status", "") or "") == "candidate":
            if source_scope_type != "meeting_room" or source_scope_id in {"", "legacy"}:
                raise ValidationError("legacy candidate memory must be confirmed in its source meeting room first")
            source_binding = await self._meetings.get_memory_scope_binding(
                org_id=self._org_id,
                memory_id=memory_id,
                scope_type="meeting_room",
                scope_id=source_scope_id,
            )
            if source_binding is None:
                await self._meetings.create_memory_scope_binding(
                    org_id=self._org_id,
                    memory_id=memory_id,
                    scope_type="meeting_room",
                    scope_id=source_scope_id,
                    permission="read",
                    created_by=str(message.sender_id),
                )
            source_content = dict(getattr(item, "content_json", None) or {})
            source_content.update(
                {
                    "confirmed_by": str(message.sender_id),
                    "confirmed_at": utcnow().isoformat(),
                    "governance_status": "confirmed",
                    "published_scope": "meeting_room",
                    "source_room_id": source_scope_id,
                }
            )
            item = await self._meetings.update_memory_item(
                org_id=self._org_id,
                memory_id=memory_id,
                status="confirmed",
                content_json=source_content,
                scope_json={
                    "scope_type": "meeting_room",
                    "scope_id": source_scope_id,
                    "meeting_room_id": source_scope_id,
                    "room_id": source_scope_id,
                    "source_room_id": source_scope_id,
                },
            )
        metadata = dict(message.metadata_json or {})
        transfer_id = str(
            payload.get("transfer_id")
            or payload.get("pending_transfer_id")
            or metadata.get("transfer_id")
            or ""
        )
        if not transfer_id:
            idempotency_key = f"legacy-collab-card:{message.id}"
            lookup = getattr(self._meetings, "get_memory_transfer_log_by_idempotency_key", None)
            transfer = await lookup(
                org_id=self._org_id,
                idempotency_key=idempotency_key,
            ) if lookup else None
            if transfer is None:
                transfer = await self._meetings.create_memory_transfer_log(
                    org_id=self._org_id,
                    memory_id=memory_id,
                    from_scope_type=source_scope_type,
                    from_scope_id=source_scope_id,
                    to_scope_type=target_scope_type,
                    to_scope_id=target_scope_id,
                    transfer_reason="旧协作记忆卡片转换为共享审批",
                    status="pending_approval",
                    operator_id=str(message.sender_id),
                    requested_by=str(message.sender_id),
                    idempotency_key=idempotency_key,
                )
            transfer_id = str(transfer.id)
        meeting_service = MeetingService(
            self._session,
            self._org_id,
            self._user_id,
            role=self._role,
        )
        meeting_service._repo = self._meetings
        if action_status == "rejected":
            await meeting_service.reject_memory_share(
                transfer_id,
                MeetingMemoryShareRejectRequest(decision_note=str(decision_note or "").strip()),
            )
        else:
            await meeting_service.approve_memory_share(
                transfer_id,
                MeetingMemoryShareDecisionRequest(decision_note=decision_note),
            )
        refreshed_item = await self._meetings.get_memory_item(self._org_id, memory_id)
        if refreshed_item is not None:
            item = refreshed_item
        await self._record_memory_card_confirmation(
            item,
            thread,
            message,
            memory_id=memory_id,
            target_scope_type=target_scope_type,
            target_scope_id=target_scope_id,
            transfer_id=transfer_id,
            decision="rejected" if action_status == "rejected" else "executed",
        )

    async def _record_memory_card_confirmation(
        self,
        item,
        thread: CollabThread,
        message: CollabMessage,
        *,
        memory_id: str,
        target_scope_type: str,
        target_scope_id: str,
        transfer_id: str | None,
        decision: str,
    ) -> None:
        confirmations = list((getattr(item, "content_json", None) or {}).get("collab_confirmations") or [])
        confirmation = {
            "thread_id": str(thread.id),
            "message_id": str(message.id),
            "target_scope_type": target_scope_type,
            "target_scope_id": target_scope_id,
            "transfer_id": transfer_id,
            "decision": decision,
            "decided_by": self._user_id,
            "decided_at": utcnow().isoformat(),
        }
        if any(
            isinstance(row, dict)
            and str(row.get("message_id") or "") == str(message.id)
            and str(row.get("transfer_id") or "") == str(transfer_id or "")
            for row in confirmations
        ):
            return
        confirmations.append(confirmation)
        content_json = dict(getattr(item, "content_json", None) or {})
        content_json["collab_confirmations"] = confirmations[-20:]
        await self._meetings.update_memory_item(
            org_id=self._org_id,
            memory_id=memory_id,
            content_json=content_json,
        )
        if decision != "rejected":
            create_evidence = getattr(self._meetings, "create_memory_evidence", None)
            if create_evidence is not None:
                now = utcnow()
                await create_evidence(
                    MemoryEvidence(
                        id=str(uuid7()),
                        org_id=self._org_id,
                        memory_id=memory_id,
                        evidence_role="human_confirmation",
                        source_kind="human_review",
                        source_type="user",
                        source_id=self._user_id,
                        independence_key=hashlib.sha256(
                            f"human_confirmation\x1f{self._user_id}".encode("utf-8")
                        ).hexdigest(),
                        trace_id=str(getattr(item, "trace_id", "") or "") or None,
                        evidence_pointer={
                            "scope_type": target_scope_type,
                            "scope_id": target_scope_id,
                            "thread_id": str(thread.id),
                            "message_id": str(message.id),
                        },
                        confidence=1.0,
                        weight=1.0,
                        occurred_at=now,
                    )
                )
            if hasattr(item, "human_confirmation_count"):
                item.human_confirmation_count = int(
                    getattr(item, "human_confirmation_count", 0) or 0
                ) + 1
                item.human_approved = True
                item.support_count = max(
                    int(getattr(item, "support_count", 0) or 0),
                    int(getattr(item, "origin_evidence_count", 0) or 0)
                    + int(item.human_confirmation_count),
                )
                item.last_evidence_at = utcnow()
                item.last_supported_at = item.last_evidence_at
                flush = getattr(self._session, "flush", None)
                if flush is not None:
                    await flush()

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

    async def _ensure_meeting_room_action_available(
        self,
        thread: CollabThread,
        message: CollabMessage,
        receipt: CollabMessageReceipt,
        requested_action_status: str,
    ) -> None:
        if thread.target_type != "meeting_room":
            return
        if message.message_type not in {"memory_card", "action_request"}:
            return
        await self._ensure_meeting_room_action_host(str(thread.target_id))
        if receipt.action_status and receipt.action_status != "pending":
            if receipt.action_status == requested_action_status:
                return
            raise ValidationError("this meeting room request has already been handled")
        receipts = (await self._repo.list_receipts(self._org_id, [str(message.id)])).get(str(message.id), [])
        for row in receipts:
            if row.recipient_type != "user":
                continue
            if str(row.recipient_id) == self._user_id:
                continue
            if message.sender_type == "user" and str(row.recipient_id) == str(message.sender_id):
                continue
            if row.action_status and row.action_status != "pending":
                raise ValidationError("this meeting room request has already been handled by another member")

    async def _ensure_meeting_room_action_host(self, room_id: str) -> None:
        member = await self._meetings.get_member(self._org_id, room_id, self._user_id)
        if member is None:
            raise ForbiddenError("not a member of target meeting room")
        if str(getattr(member, "role", "") or "member") == "host":
            return
        room = await self._meetings.get_room(self._org_id, room_id)
        if room is not None and str(getattr(room, "created_by", "") or "") == self._user_id:
            return
        raise ForbiddenError("only the meeting host can handle meeting room requests")

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
                    role="host" if str(getattr(member, "role", "") or "") == "host" else "participant",
                )
        if thread.source_type == "meeting_room":
            members = await self._meetings.list_members(self._org_id, str(thread.source_id))
            for member in members:
                await self._repo.add_participant(
                    org_id=self._org_id,
                    thread_id=str(thread.id),
                    participant_type="user",
                    participant_id=str(member.user_id),
                    role="host" if str(getattr(member, "role", "") or "") == "host" else "participant",
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

    async def _create_action_status_message(
        self,
        thread: CollabThread,
        source_message: CollabMessage,
        receipt: CollabMessageReceipt,
    ) -> CollabMessage:
        action_status = str(receipt.action_status or "pending")
        action_label = self._action_status_label(action_status)
        message_type_label = "记忆卡片" if source_message.message_type == "memory_card" else "处理请求"
        actor_label = await self._user_display_name(self._user_id)
        status_message = await self._repo.create_message(
            org_id=self._org_id,
            thread_id=str(thread.id),
            sender_type="system",
            sender_id=self._user_id,
            message_type="system",
            content=f"{actor_label}已{action_label}这条{message_type_label}。",
            reply_to_message_id=str(source_message.id),
            metadata_json={
                "event": "collab_action_status",
                "source_message_id": str(source_message.id),
                "actor_user_id": self._user_id,
                "actor_label": actor_label,
                "action_status": action_status,
                "message_type": str(source_message.message_type or ""),
            },
        )
        await self._create_action_status_message_receipts(thread, status_message)
        return status_message

    async def _create_action_status_message_receipts(self, thread: CollabThread, message: CollabMessage) -> None:
        participants = (await self._repo.list_participants(self._org_id, [str(thread.id)])).get(str(thread.id), [])
        now = utcnow()
        for participant in participants:
            is_actor = participant.participant_type == "user" and str(participant.participant_id) == self._user_id
            await self._repo.create_receipt(
                org_id=self._org_id,
                message_id=str(message.id),
                thread_id=str(thread.id),
                recipient_type=participant.participant_type,
                recipient_id=participant.participant_id,
                delivered_at=now,
                read_at=now if is_actor else None,
            )
        await self._repo.mark_participant_read(
            org_id=self._org_id,
            thread_id=str(thread.id),
            participant_type="user",
            participant_id=self._user_id,
            message_id=str(message.id),
        )

    async def _user_display_name(self, user_id: str) -> str:
        user = await self._users.get_by_id(self._org_id, user_id)
        return str(getattr(user, "username", None) or getattr(user, "email", None) or user_id)

    @staticmethod
    def _action_status_label(action_status: str) -> str:
        if action_status == "accepted":
            return "接受"
        if action_status == "rejected":
            return "拒绝"
        if action_status == "done":
            return "确认/完成"
        return "处理"

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

    async def _publish_work_item_event(
        self,
        thread: CollabThread,
        work_item: CollabWorkItemResponse,
        event_name: str,
    ) -> None:
        participants = (await self._repo.list_participants(self._org_id, [str(thread.id)])).get(str(thread.id), [])
        payload = {
            "event": event_name,
            "work_item_id": work_item.id,
            "resource_id": work_item.resource_id,
            "item_type": work_item.item_type,
            "status": work_item.status,
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
