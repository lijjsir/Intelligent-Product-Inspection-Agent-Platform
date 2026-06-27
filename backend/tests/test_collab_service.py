from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.schemas.collab import CollabAttachmentPayload, CollabMessageActionRequest, CollabMessageCreateRequest, CollabThreadCreateRequest
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


class FakeMeetingRepo:
    def __init__(self):
        self.rooms = {"room-1": SimpleNamespace(id="room-1", title="质量复盘室")}
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
                content_json={"title": "边缘识别复盘", "content": "弱光下边缘识别不稳定。"},
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
        self.transfer_logs.append(kwargs)
        return SimpleNamespace(id=f"transfer-{len(self.transfer_logs)}", **kwargs)

    async def update_memory_item(self, *, org_id: str, memory_id: str, status=None, content_json=None, **kwargs):
        item = self.memory_items[memory_id]
        if status is not None:
            item.status = status
        if content_json is not None:
            item.content_json = content_json
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
    repeated_receipt = await recipient.update_action(message.id, CollabMessageActionRequest(action_status="done"))

    assert done_receipt.action_status == "done"
    assert repeated_receipt.action_status == "done"
    assert owner._meetings.memory_items["mem-1"].status == "confirmed"
    assert owner._meetings.scope_bindings == [
        {
            "org_id": "org-1",
            "memory_id": "mem-1",
            "scope_type": "user",
            "scope_id": "user-2",
            "permission": "read",
            "created_by": "user-2",
        }
    ]
    assert owner._meetings.transfer_logs == [
        {
            "org_id": "org-1",
            "memory_id": "mem-1",
            "from_scope_type": "meeting_room",
            "from_scope_id": "room-1",
            "to_scope_type": "user",
            "to_scope_id": "user-2",
            "transfer_reason": "协作消息接收方确认记忆卡片",
            "status": "executed",
            "operator_id": "user-2",
        }
    ]


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
    repeated_receipt = await host.update_action(message.id, CollabMessageActionRequest(action_status="done"))

    assert host_receipt.action_status == "done"
    assert repeated_receipt.action_status == "done"
    with pytest.raises(ValidationError, match="already been handled"):
        await host.update_action(message.id, CollabMessageActionRequest(action_status="rejected"))
    assert len(sender._meetings.scope_bindings) == 1
    assert sender._meetings.scope_bindings[0]["scope_type"] == "meeting_room"
    assert sender._meetings.scope_bindings[0]["scope_id"] == "room-1"
