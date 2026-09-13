from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.schemas.collab import (
    CollabActionRequestCreateRequest,
    CollabAttachmentPayload,
    CollabMessageActionRequest,
    CollabMessageCreateRequest,
    CollabThreadCreateRequest,
)
from app.services import collab_service as collab_service_mod


def _now() -> datetime:
    return datetime(2026, 6, 22, 10, 0, 0)


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeUsersRepo:
    def __init__(self):
        self.users = {
            ("org-1", "user-1"): SimpleNamespace(id="user-1", username="alice"),
            ("org-1", "user-2"): SimpleNamespace(id="user-2", username="bob"),
            ("org-1", "user-3"): SimpleNamespace(id="user-3", username="cora"),
        }

    async def get_by_id(self, org_id: str, user_id: str):
        return self.users.get((org_id, user_id))

    async def list_by_org_id(self, org_id: str):
        return [user for (row_org_id, _), user in self.users.items() if row_org_id == org_id]


class FakeMeetingRepo:
    def __init__(self):
        self.rooms = {"room-1": SimpleNamespace(id="room-1", title="质量复盘室", created_by="user-1")}
        self.members = {
            "room-1": [
                SimpleNamespace(user_id="user-1", role="host"),
                SimpleNamespace(user_id="user-2", role="member"),
                SimpleNamespace(user_id="user-3", role="member"),
            ]
        }
        self.memory_items = {
            "mem-1": SimpleNamespace(
                memory_id="mem-1",
                status="candidate",
                content_summary="弱光下边缘识别不稳定。",
                memory_type="task_episode",
                content_json={"title": "边缘识别复盘", "content": "弱光下边缘识别不稳定。"},
                scope_json={"scope_type": "meeting_room", "scope_id": "room-1", "source_room_id": "room-1"},
                confidence=0.8,
                created_by="user-1",
                created_at=_now(),
                updated_at=_now(),
            )
        }
        self.scope_bindings: list[dict] = []
        self.transfer_logs: list[dict] = []

    async def get_room(self, org_id: str, room_id: str):
        return self.rooms.get(room_id)

    async def get_member(self, org_id: str, room_id: str, user_id: str):
        return next((member for member in self.members.get(room_id, []) if member.user_id == user_id), None)

    async def list_members(self, org_id: str, room_id: str):
        return list(self.members.get(room_id, []))

    async def list_joined_rooms(self, org_id: str, user_id: str, limit: int = 100):
        return list(self.rooms.values())[:limit]

    async def list_active_agent_definitions(self, org_id: str):
        return []

    async def list_memory_transfer_logs(self, **kwargs):
        return [SimpleNamespace(**row) for row in self.transfer_logs]

    async def get_memory_item(self, org_id: str, memory_id: str):
        return self.memory_items.get(memory_id)

    async def get_memory_scope_binding(self, *, org_id: str, memory_id: str, scope_type: str, scope_id: str):
        return next(
            (
                SimpleNamespace(**row)
                for row in self.scope_bindings
                if row["org_id"] == org_id
                and row["memory_id"] == memory_id
                and row["scope_type"] == scope_type
                and row["scope_id"] == scope_id
            ),
            None,
        )

    async def create_memory_scope_binding(self, **kwargs):
        self.scope_bindings.append(kwargs)
        return SimpleNamespace(id=f"binding-{len(self.scope_bindings)}", **kwargs)

    async def create_memory_transfer_log(self, **kwargs):
        row = {
            "id": f"transfer-{len(self.transfer_logs) + 1}",
            "created_at": _now(),
            "updated_at": _now(),
            "decided_by": None,
            "decided_at": None,
            "decision_note": None,
            **kwargs,
        }
        self.transfer_logs.append(row)
        return SimpleNamespace(**row)

    async def get_memory_transfer_log_by_idempotency_key(self, *, org_id: str, idempotency_key: str):
        row = next((item for item in self.transfer_logs if item["org_id"] == org_id and item.get("idempotency_key") == idempotency_key), None)
        return SimpleNamespace(**row) if row else None

    async def get_memory_transfer_log(self, org_id: str, transfer_id: str):
        row = next((item for item in self.transfer_logs if item["org_id"] == org_id and item["id"] == transfer_id), None)
        return SimpleNamespace(**row) if row else None

    async def update_memory_transfer_log_status(
        self,
        *,
        org_id: str,
        transfer_id: str,
        status: str,
        operator_id: str,
        decision_note=None,
        expected_status=None,
    ):
        row = next((item for item in self.transfer_logs if item["org_id"] == org_id and item["id"] == transfer_id), None)
        if row is None or (expected_status and row["status"] != expected_status):
            return None
        row.update(
            status=status,
            operator_id=operator_id,
            decided_by=operator_id,
            decided_at=_now(),
            decision_note=decision_note,
            updated_at=_now(),
        )
        return SimpleNamespace(**row)

    async def replace_memory_tags(self, **kwargs):
        return []

    async def create_message(self, **kwargs):
        return SimpleNamespace(
            id="meeting-system-1",
            seq_no=1,
            agent_id=None,
            mentions=None,
            quote_message_id=None,
            metadata_json=None,
            private_recipient_user_id=None,
            created_at=_now(),
            updated_at=_now(),
            **kwargs,
        )

    async def update_memory_item(self, *, org_id: str, memory_id: str, status=None, content_json=None, scope_json=None, **kwargs):
        item = self.memory_items[memory_id]
        if status is not None:
            item.status = status
        if content_json is not None:
            item.content_json = content_json
        if scope_json is not None:
            item.scope_json = scope_json
        item.updated_at = _now()
        return item


class FakeCollabRepo:
    def __init__(self):
        self.threads: dict[str, SimpleNamespace] = {}
        self.participants: list[SimpleNamespace] = []
        self.messages: dict[str, SimpleNamespace] = {}
        self.receipts: list[SimpleNamespace] = []
        self.file_assets: dict[str, SimpleNamespace] = {}
        self.attachments: list[SimpleNamespace] = []

    async def get_thread(self, org_id: str, thread_id: str):
        row = self.threads.get(thread_id)
        return row if row and row.org_id == org_id and row.deleted_at is None else None

    async def find_existing_thread(self, *, org_id: str, source_type: str, source_id: str, target_type: str, target_id: str):
        for row in self.threads.values():
            direct = row.source_type == source_type and row.source_id == source_id and row.target_type == target_type and row.target_id == target_id
            reverse = row.source_type == target_type and row.source_id == target_id and row.target_type == source_type and row.target_id == source_id
            if row.org_id == org_id and row.deleted_at is None and (direct or reverse):
                return row
        return None

    async def create_thread(self, **kwargs):
        thread_id = f"thread-{len(self.threads) + 1}"
        thread_data = dict(kwargs)
        thread_data.setdefault("metadata_json", None)
        row = SimpleNamespace(
            id=thread_id,
            status="active",
            last_message_at=None,
            deleted_at=None,
            created_at=_now(),
            updated_at=_now(),
            **thread_data,
        )
        self.threads[thread_id] = row
        return row

    async def add_participant(self, *, org_id: str, thread_id: str, participant_type: str, participant_id: str, role: str = "participant"):
        existing = await self.get_participant(
            org_id=org_id,
            thread_id=thread_id,
            participant_type=participant_type,
            participant_id=participant_id,
        )
        if existing:
            return existing
        row = SimpleNamespace(
            id=f"participant-{len(self.participants) + 1}",
            org_id=org_id,
            thread_id=thread_id,
            participant_type=participant_type,
            participant_id=participant_id,
            role=role,
            last_read_message_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        self.participants.append(row)
        return row

    async def get_participant(self, *, org_id: str, thread_id: str, participant_type: str, participant_id: str):
        return next(
            (
                row
                for row in self.participants
                if row.org_id == org_id
                and row.thread_id == thread_id
                and row.participant_type == participant_type
                and row.participant_id == participant_id
            ),
            None,
        )

    async def list_threads_for_participant(self, *, org_id: str, participant_type: str, participant_id: str, limit: int = 100):
        thread_ids = [
            row.thread_id
            for row in self.participants
            if row.org_id == org_id and row.participant_type == participant_type and row.participant_id == participant_id
        ]
        return [
            self.threads[thread_id]
            for thread_id in thread_ids[:limit]
            if self.threads[thread_id].deleted_at is None
        ]

    async def list_participants(self, org_id: str, thread_ids):
        grouped: dict[str, list[SimpleNamespace]] = {thread_id: [] for thread_id in thread_ids}
        for row in self.participants:
            if row.org_id == org_id and row.thread_id in grouped:
                grouped[row.thread_id].append(row)
        return grouped

    async def unread_counts_for_participant(self, *, org_id: str, participant_type: str, participant_id: str, thread_ids):
        counts: dict[str, int] = {}
        for row in self.receipts:
            if (
                row.org_id == org_id
                and row.thread_id in thread_ids
                and row.recipient_type == participant_type
                and row.recipient_id == participant_id
                and row.read_at is None
            ):
                counts[row.thread_id] = counts.get(row.thread_id, 0) + 1
        return counts

    async def create_message(self, **kwargs):
        message_id = f"message-{len(self.messages) + 1}"
        row = SimpleNamespace(id=message_id, deleted_at=None, created_at=_now(), updated_at=_now(), **kwargs)
        self.messages[message_id] = row
        self.threads[row.thread_id].last_message_at = row.created_at
        return row

    async def list_messages(self, *, org_id: str, thread_id: str, limit: int = 200):
        rows = [row for row in self.messages.values() if row.org_id == org_id and row.thread_id == thread_id and row.deleted_at is None]
        return rows[:limit]

    async def get_message(self, org_id: str, message_id: str):
        row = self.messages.get(message_id)
        return row if row and row.org_id == org_id and row.deleted_at is None else None

    async def list_action_requests_for_user(self, *, org_id: str, user_id: str, limit: int = 200):
        rows = []
        for message in self.messages.values():
            if message.org_id != org_id or message.message_type != "action_request" or message.deleted_at is not None:
                continue
            receipt = await self.get_receipt_for_recipient(
                org_id=org_id,
                message_id=message.id,
                recipient_type="user",
                recipient_id=user_id,
            )
            if str(message.sender_id) == user_id or receipt is not None:
                rows.append((message, receipt, self.threads[message.thread_id]))
        return rows[:limit]

    async def create_receipt(self, *, org_id: str, message_id: str, thread_id: str, recipient_type: str, recipient_id: str, delivered_at=None, read_at=None):
        existing = await self.get_receipt_for_recipient(
            org_id=org_id,
            message_id=message_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
        )
        if existing:
            return existing
        row = SimpleNamespace(
            id=f"receipt-{len(self.receipts) + 1}",
            org_id=org_id,
            message_id=message_id,
            thread_id=thread_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            delivered_at=delivered_at,
            read_at=read_at,
            acted_at=None,
            action_status="done" if read_at else "pending",
            created_at=_now(),
            updated_at=_now(),
        )
        self.receipts.append(row)
        return row

    async def get_receipt_for_recipient(self, *, org_id: str, message_id: str, recipient_type: str, recipient_id: str):
        return next(
            (
                row
                for row in self.receipts
                if row.org_id == org_id
                and row.message_id == message_id
                and row.recipient_type == recipient_type
                and row.recipient_id == recipient_id
            ),
            None,
        )

    async def list_receipts(self, org_id: str, message_ids):
        grouped: dict[str, list[SimpleNamespace]] = {message_id: [] for message_id in message_ids}
        for row in self.receipts:
            if row.org_id == org_id and row.message_id in grouped:
                grouped[row.message_id].append(row)
        return grouped

    async def mark_receipt_read(self, receipt):
        receipt.read_at = receipt.read_at or _now()
        return receipt

    async def mark_participant_read(self, *, org_id: str, thread_id: str, participant_type: str, participant_id: str, message_id: str):
        participant = await self.get_participant(
            org_id=org_id,
            thread_id=thread_id,
            participant_type=participant_type,
            participant_id=participant_id,
        )
        if participant:
            participant.last_read_message_id = message_id

    async def update_receipt_action(self, receipt, action_status: str):
        receipt.read_at = receipt.read_at or _now()
        receipt.acted_at = _now()
        receipt.action_status = action_status
        return receipt

    async def update_thread_status(self, *, org_id: str, thread_id: str, status: str):
        row = await self.get_thread(org_id, thread_id)
        if row:
            row.status = status
            row.updated_at = _now()
        return row

    async def soft_delete_thread(self, *, org_id: str, thread_id: str):
        row = self.threads.get(thread_id)
        if row and row.org_id != org_id:
            row = None
        if row:
            row.status = "deleted"
            row.deleted_at = _now()
            metadata = dict(row.metadata_json or {})
            metadata["deleted_at"] = row.deleted_at.isoformat()
            row.metadata_json = metadata
            row.updated_at = _now()
        return row

    async def soft_delete_message(self, *, org_id: str, message_id: str):
        row = await self.get_message(org_id, message_id)
        if row:
            row.deleted_at = _now()
            metadata = dict(getattr(row, "metadata_json", None) or {})
            metadata["deleted_at"] = row.deleted_at.isoformat()
            row.metadata_json = metadata
            row.updated_at = _now()
        return row

    async def get_file_assets(self, org_id: str, file_ids):
        return [row for file_id, row in self.file_assets.items() if file_id in file_ids and row.org_id == org_id]

    async def attach_file(self, *, org_id: str, message_id: str, file_id: str, sort_order: int):
        row = SimpleNamespace(
            id=f"attachment-{len(self.attachments) + 1}",
            org_id=org_id,
            message_id=message_id,
            file_id=file_id,
            sort_order=sort_order,
            created_at=_now(),
            updated_at=_now(),
        )
        self.attachments.append(row)
        return row

    async def list_message_attachments(self, org_id: str, message_ids):
        grouped: dict[str, list[SimpleNamespace]] = {message_id: [] for message_id in message_ids}
        for link in self.attachments:
            if link.org_id == org_id and link.message_id in grouped:
                grouped[link.message_id].append(self.file_assets[link.file_id])
        return grouped


def _service(repo: FakeCollabRepo, *, user_id: str = "user-1", session: FakeSession | None = None) -> collab_service_mod.CollabService:
    service = collab_service_mod.CollabService(session or FakeSession(), "org-1", user_id)
    service._repo = repo
    service._users = FakeUsersRepo()
    service._meetings = FakeMeetingRepo()
    return service


@pytest.mark.asyncio
async def test_create_thread_reuses_user_thread_and_blocks_self_target():
    repo = FakeCollabRepo()
    service = _service(repo)

    created = await service.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))
    reused = await service.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))

    assert created.id == reused.id
    assert len(repo.threads) == 1
    assert {(row.participant_type, row.participant_id) for row in repo.participants} == {
        ("user", "user-1"),
        ("user", "user-2"),
    }
    with pytest.raises(ValidationError, match="self"):
        await service.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-1"))


@pytest.mark.asyncio
async def test_create_thread_rejects_agent_as_message_recipient():
    service = _service(FakeCollabRepo())

    with pytest.raises(ValidationError, match="Agent is not a collaboration message recipient"):
        await service.create_thread(CollabThreadCreateRequest(target_type="agent", target_id="agent-1"))


@pytest.mark.asyncio
async def test_meeting_room_thread_expands_to_room_members_and_creates_receipts():
    repo = FakeCollabRepo()
    service = _service(repo)

    thread = await service.create_thread(CollabThreadCreateRequest(target_type="meeting_room", target_id="room-1"))
    message = await service.send_message(thread.id, CollabMessageCreateRequest(content="请大家确认这条候选记忆"))

    participants = {(row.participant_type, row.participant_id) for row in repo.participants}
    assert ("meeting_room", "room-1") in participants
    assert ("user", "user-2") in participants
    assert ("user", "user-3") in participants
    assert {(receipt.recipient_type, receipt.recipient_id) for receipt in repo.receipts} == participants
    assert next(receipt for receipt in repo.receipts if receipt.recipient_id == "user-1").read_at is not None
    assert message.receipts


@pytest.mark.asyncio
async def test_send_message_links_attachments_and_counts_unread():
    repo = FakeCollabRepo()
    repo.file_assets["file-1"] = SimpleNamespace(
        id="file-1",
        org_id="org-1",
        bucket="collab-assets",
        object_key="collab/org-1/file.png",
        url="/files/file.png",
        file_name="evidence.png",
        mime_type="image/png",
        size_bytes=128,
        checksum="abc",
    )
    service = _service(repo)
    thread = await service.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))

    message = await service.send_message(
        thread.id,
        CollabMessageCreateRequest(
            content="看一下这张图",
            message_type="image",
            attachments=[
                CollabAttachmentPayload(
                    id="file-1",
                    name="evidence.png",
                    url="/files/file.png",
                    content_type="image/png",
                    kind="image",
                )
            ],
        ),
    )
    recipient_threads = await _service(repo, user_id="user-2").list_threads()

    assert message.attachments[0].file_name == "evidence.png"
    assert repo.attachments[0].message_id == message.id
    assert recipient_threads[0].unread_count == 1


@pytest.mark.asyncio
async def test_non_participant_cannot_access_thread_messages():
    repo = FakeCollabRepo()
    owner = _service(repo)
    thread = await owner.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))

    outsider = _service(repo, user_id="user-3")

    with pytest.raises(ForbiddenError, match="not a participant"):
        await outsider.list_messages(thread.id)
    with pytest.raises(ForbiddenError, match="not a participant"):
        await outsider.send_message(thread.id, CollabMessageCreateRequest(content="越权消息"))


@pytest.mark.asyncio
async def test_thread_owner_can_delete_collaboration_record():
    repo = FakeCollabRepo()
    owner = _service(repo)
    thread = await owner.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))

    result = await owner.delete_thread(thread.id)
    owner_threads = await owner.list_threads()

    assert result == {"deleted": True, "thread_id": thread.id}
    assert repo.threads[thread.id].status == "deleted"
    assert repo.threads[thread.id].deleted_at is not None
    assert owner_threads == []


@pytest.mark.asyncio
async def test_non_owner_cannot_delete_collaboration_record():
    repo = FakeCollabRepo()
    owner = _service(repo)
    thread = await owner.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))
    recipient = _service(repo, user_id="user-2")

    with pytest.raises(ForbiddenError, match="only the thread owner"):
        await recipient.delete_thread(thread.id)

    assert repo.threads[thread.id].status == "active"
    assert repo.threads[thread.id].deleted_at is None


@pytest.mark.asyncio
async def test_recipient_can_mark_read_and_complete_action_request():
    repo = FakeCollabRepo()
    owner = _service(repo)
    thread = await owner.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))
    message = await owner.send_message(
        thread.id,
        CollabMessageCreateRequest(content="", message_type="action_request", metadata_json={"request_type": "data_management"}),
    )
    recipient = _service(repo, user_id="user-2")

    read_receipt = await recipient.mark_read(message.id)
    done_receipt = await recipient.update_action(message.id, CollabMessageActionRequest(action_status="done"))

    assert read_receipt.read_at is not None
    assert done_receipt.action_status == "done"
    assert done_receipt.acted_at is not None
    status_messages = [
        item for item in repo.messages.values()
        if item.message_type == "system"
        and (item.metadata_json or {}).get("event") == "collab_action_status"
    ]
    assert len(status_messages) == 1
    assert status_messages[0].reply_to_message_id == message.id
    assert (status_messages[0].metadata_json or {}).get("action_status") == "done"
    owner_threads = await owner.list_threads()
    assert owner_threads[0].unread_count == 1


@pytest.mark.asyncio
async def test_structured_action_request_is_exposed_as_unified_work_item():
    repo = FakeCollabRepo()
    owner = _service(repo)

    created = await owner.create_action_request(
        CollabActionRequestCreateRequest(
            target_type="user",
            target_id="user-2",
            title="复核弱光样本",
            description="请核对附件对应的批次记录。",
            source_link="/app/results/result-1",
            source_context={"result_id": "result-1"},
            idempotency_key="action-request-0001",
        )
    )
    recipient = _service(repo, user_id="user-2")
    recipient._meetings = owner._meetings
    pending = await recipient.list_work_items(view="pending")

    assert created.item_type == "action_request"
    assert created.status == "pending"
    assert created.payload["thread_id"]
    assert [item.id for item in pending] == [created.id]
    assert pending[0].allowed_actions == ["accepted", "rejected", "done"]
    assert pending[0].source_link == "/app/results/result-1"


@pytest.mark.asyncio
async def test_recipient_confirms_memory_card_into_personal_scope_once():
    repo = FakeCollabRepo()
    session = FakeSession()
    owner = _service(repo, session=session)
    thread = await owner.create_thread(CollabThreadCreateRequest(target_type="user", target_id="user-2"))
    message = await owner.send_message(
        thread.id,
        CollabMessageCreateRequest(
            content="请确认这条会议记忆",
            message_type="memory_card",
            metadata_json={
                "memory": {
                    "memory_id": "mem-1",
                    "title": "边缘识别复盘",
                    "source_room_id": "room-1",
                },
                "source_context": {
                    "source_type": "memory",
                    "source_room_id": "room-1",
                },
            },
        ),
    )
    recipient = _service(repo, user_id="user-2", session=session)
    recipient._meetings = owner._meetings

    done_receipt = await recipient.update_action(message.id, CollabMessageActionRequest(action_status="done"))
    with pytest.raises(ConflictError, match="already been handled"):
        await recipient.update_action(message.id, CollabMessageActionRequest(action_status="done"))

    assert done_receipt.action_status == "done"
    assert owner._meetings.memory_items["mem-1"].status == "confirmed"
    assert len(owner._meetings.scope_bindings) == 2
    assert owner._meetings.scope_bindings[0] == {
        "org_id": "org-1",
        "memory_id": "mem-1",
        "scope_type": "meeting_room",
        "scope_id": "room-1",
        "permission": "read",
        "created_by": "user-1",
    }
    personal_binding = owner._meetings.scope_bindings[1]
    assert {
        key: personal_binding[key]
        for key in ("org_id", "memory_id", "scope_type", "scope_id", "permission", "created_by")
    } == {
        "org_id": "org-1",
        "memory_id": "mem-1",
        "scope_type": "user",
        "scope_id": "user-2",
        "permission": "read",
        "created_by": "user-2",
    }
    assert personal_binding["binding_kind"] == "shared"
    assert personal_binding["binding_status"] == "active"
    assert personal_binding["approved_by"] == "user-2"
    assert personal_binding["source_transfer_id"] == "transfer-1"
    transfer = owner._meetings.transfer_logs[0]
    assert transfer["from_scope_type"] == "meeting_room"
    assert transfer["from_scope_id"] == "room-1"
    assert transfer["to_scope_type"] == "user"
    assert transfer["to_scope_id"] == "user-2"
    assert transfer["requested_by"] == "user-1"
    assert transfer["decided_by"] == "user-2"
    assert transfer["status"] == "approved"
    assert owner._meetings.memory_items["mem-1"].scope_json["scope_id"] == "room-1"


@pytest.mark.asyncio
async def test_meeting_room_memory_card_can_only_be_handled_by_host_once():
    repo = FakeCollabRepo()
    session = FakeSession()
    sender = _service(repo, user_id="user-2", session=session)
    thread = await sender.create_thread(CollabThreadCreateRequest(target_type="meeting_room", target_id="room-1"))
    message = await sender.send_message(
        thread.id,
        CollabMessageCreateRequest(
            content="请会议室确认这条会议记忆",
            message_type="memory_card",
            metadata_json={
                "memory": {
                    "memory_id": "mem-1",
                    "title": "边缘识别复盘",
                    "source_room_id": "room-1",
                },
            },
        ),
    )
    non_host = _service(repo, user_id="user-3", session=session)
    host = _service(repo, user_id="user-1", session=session)
    non_host._meetings = sender._meetings
    host._meetings = sender._meetings

    with pytest.raises(ForbiddenError, match="only the meeting host"):
        await non_host.update_action(message.id, CollabMessageActionRequest(action_status="done"))

    host_receipt = await host.update_action(message.id, CollabMessageActionRequest(action_status="done"))
    with pytest.raises(ConflictError, match="already been handled"):
        await host.update_action(message.id, CollabMessageActionRequest(action_status="done"))

    assert host_receipt.action_status == "done"
    with pytest.raises(ValidationError, match="already been handled"):
        await host.update_action(message.id, CollabMessageActionRequest(action_status="rejected"))
    assert len(sender._meetings.scope_bindings) == 1
    assert sender._meetings.scope_bindings[0]["scope_type"] == "meeting_room"
    assert sender._meetings.scope_bindings[0]["scope_id"] == "room-1"
