from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import require_role
from app.core.security import safe_decode_token
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.meeting import (
    MeetingAddAgentRequest,
    MeetingActionItemCreateRequest,
    MeetingActionItemResponse,
    MeetingActionItemUpdateRequest,
    MeetingAgentRunRequest,
    MeetingAgentRunResponse,
    MeetingMemoryExtractRequest,
    MeetingMemoryResponse,
    MeetingMemoryTransferRequest,
    MeetingMemoryUpdateRequest,
    MeetingMessageCreateRequest,
    MeetingMessageResponse,
    MeetingRoomAgentResponse,
    MeetingRoomCreateRequest,
    MeetingRoomDetailResponse,
    MeetingRoomJoinRequest,
    MeetingRoomMemberResponse,
    MeetingRoomResponse,
    MeetingRoomUpdateRequest,
)
from app.schemas.user import CurrentUser
from app.services.meeting_service import MeetingService
from app.services.stream_service import meeting_stream_broker


router = APIRouter(prefix="/meetings", tags=["meetings"])


def _build_service(db, current: CurrentUser) -> MeetingService:
    require_role("meeting", current.role)
    return MeetingService(db, current.org_id, current.user_id)


def _get_user_for_stream(token: str = Query(default="")) -> CurrentUser:
    if not token:
        raise ForbiddenError("missing stream token")
    payload = safe_decode_token(token)
    if payload.get("typ") != "stream":
        raise ForbiddenError("invalid stream token type")
    return CurrentUser(
        user_id=str(payload.get("user_id") or payload.get("sub") or ""),
        org_id=str(payload.get("org_id") or ""),
        role=str(payload.get("role") or ""),
        roles=[str(item) for item in (payload.get("roles") or [])],
        plan_tier=str(payload.get("plan_tier") or "basic"),
        capabilities=[str(item) for item in (payload.get("capabilities") or [])],
        workspaces=[str(item) for item in (payload.get("workspaces") or [])],
        default_workspace=str(payload.get("default_workspace") or "app"),
        stream_resource=str(payload.get("resource") or ""),
        stream_resource_id=str(payload.get("resource_id") or ""),
    )


# ── Rooms ─────────────────────────────────────────────────────────

@router.get("/rooms", response_model=ResponseEnvelope[list[MeetingRoomResponse]])
async def list_rooms(
    limit: int = Query(default=100, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_rooms(limit=limit))


@router.post("/rooms", response_model=ResponseEnvelope[MeetingRoomResponse])
async def create_room(
    body: MeetingRoomCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.create_room(body.title, body.password))


@router.post("/rooms/join", response_model=ResponseEnvelope[MeetingRoomResponse])
async def join_room(
    body: MeetingRoomJoinRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.join_room(body.access_code, body.password))


@router.get("/rooms/{room_id}", response_model=ResponseEnvelope[MeetingRoomDetailResponse])
async def get_room_detail(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.get_room_detail(room_id))


@router.put("/rooms/{room_id}", response_model=ResponseEnvelope[MeetingRoomResponse])
async def update_room(
    room_id: str,
    body: MeetingRoomUpdateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    if body.title is None:
        return ResponseEnvelope(data=(await service.get_room_detail(room_id)))
    return ResponseEnvelope(data=await service.update_room_title(room_id, body.title))


@router.post("/rooms/{room_id}/close", response_model=ResponseEnvelope[MeetingRoomResponse])
async def close_room(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.close_room(room_id))


@router.post("/rooms/{room_id}/archive", response_model=ResponseEnvelope[MeetingRoomResponse])
async def archive_room(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.archive_room(room_id))


# ── Messages ──────────────────────────────────────────────────────

@router.delete("/rooms/{room_id}", response_model=ResponseEnvelope[dict])
async def delete_room(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    await service.delete_room(room_id)
    return ResponseEnvelope(data={"ok": True})


@router.get("/rooms/{room_id}/messages", response_model=ResponseEnvelope[list[MeetingMessageResponse]])
async def list_messages(
    room_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_messages(room_id, after_seq=after_seq, limit=limit))


@router.post("/rooms/{room_id}/messages", response_model=ResponseEnvelope[MeetingMessageResponse])
async def send_message(
    room_id: str,
    body: MeetingMessageCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.send_message(room_id, body.content, body.quote_message_id))


@router.post("/rooms/{room_id}/messages/{message_id}/quote", response_model=ResponseEnvelope[MeetingMessageResponse])
async def quote_message(
    room_id: str,
    message_id: str,
    body: MeetingMessageCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.quote_message(room_id, message_id, body.content))


# ── General Agent ─────────────────────────────────────────────────────

@router.post("/rooms/{room_id}/agent/run", response_model=ResponseEnvelope[MeetingAgentRunResponse])
async def run_general_agent(
    room_id: str,
    body: MeetingAgentRunRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.run_general_agent(room_id, body))


# ── Meeting memories ──────────────────────────────────────────────────

@router.get("/rooms/{room_id}/memories", response_model=ResponseEnvelope[list[MeetingMemoryResponse]])
async def list_room_memories(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_room_memories(room_id))


@router.post("/rooms/{room_id}/memories/extract", response_model=ResponseEnvelope[list[MeetingMemoryResponse]])
async def extract_room_memories(
    room_id: str,
    body: MeetingMemoryExtractRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    candidates = await service.extract_memories(room_id, body)
    memories = [
        MeetingMemoryResponse(
            memory_id=item.memory_id,
            title=item.title,
            content=item.content,
            summary=item.summary,
            memory_type=item.memory_type,
            status=item.status,
            scope="meeting",
            confidence=item.confidence,
            source_message_id=item.source_message_id,
            created_at=item.created_at,
        )
        for item in candidates
    ]
    return ResponseEnvelope(data=memories)


@router.post("/memories/{memory_id}/confirm", response_model=ResponseEnvelope[MeetingMemoryResponse])
async def confirm_memory(
    memory_id: str,
    body: MeetingMemoryUpdateRequest | None = None,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.confirm_memory(memory_id, body))


@router.post("/memories/{memory_id}/reject", response_model=ResponseEnvelope[MeetingMemoryResponse])
async def reject_memory(
    memory_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.reject_memory(memory_id))


@router.post("/memories/{memory_id}/transfer", response_model=ResponseEnvelope[MeetingMemoryResponse])
async def transfer_memory(
    memory_id: str,
    body: MeetingMemoryTransferRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.transfer_memory(memory_id, body))


# ── Action items ──────────────────────────────────────────────────────

@router.get("/rooms/{room_id}/action-items", response_model=ResponseEnvelope[list[MeetingActionItemResponse]])
async def list_action_items(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_action_items(room_id))


@router.post("/rooms/{room_id}/action-items", response_model=ResponseEnvelope[MeetingActionItemResponse])
async def create_action_item(
    room_id: str,
    body: MeetingActionItemCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.create_action_item(room_id, body))


@router.put("/action-items/{action_item_id}", response_model=ResponseEnvelope[MeetingActionItemResponse])
async def update_action_item(
    action_item_id: str,
    body: MeetingActionItemUpdateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.update_action_item(action_item_id, body))


@router.post("/action-items/{action_item_id}/complete", response_model=ResponseEnvelope[MeetingActionItemResponse])
async def complete_action_item(
    action_item_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.complete_action_item(action_item_id))


# ── AI Assistant ──────────────────────────────────────────────────

@router.post("/rooms/{room_id}/ai-chat", response_model=ResponseEnvelope[MeetingMessageResponse])
async def ai_chat(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("meeting", current.role)
    from app.services.meeting_ai_service import MeetingAiService
    service = MeetingAiService(db, current.org_id, current.user_id)
    return ResponseEnvelope(data=await service.ai_respond(room_id))


@router.post("/rooms/{room_id}/summary", response_model=ResponseEnvelope[MeetingMessageResponse])
async def summarize_room(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("meeting", current.role)
    from app.services.meeting_ai_service import MeetingAiService

    service = MeetingAiService(db, current.org_id, current.user_id)
    return ResponseEnvelope(data=await service.summarize(room_id))


# ── Available Agents ──────────────────────────────────────────────

@router.get("/available-agents", response_model=ResponseEnvelope[list[dict]])
async def list_available_agents(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("meeting", current.role)
    from agent.topology_catalog import get_registered_subgraphs

    # Return agents directly from catalog — no DB dependency
    agents = []
    for item in get_registered_subgraphs():
        if not item.get("is_active", True):
            continue
        status = item.get("lifecycle_status", "active")
        if status in ("planned", "deprecated"):
            continue
        agents.append({
            "id": item["subgraph_key"],
            "name": item["name"],
            "description": item.get("customer_visible_description") or item.get("description") or "",
            "group_key": item.get("group_key") or item.get("group") or "",
        })
    return ResponseEnvelope(data=agents)


# ── Agent Definitions ─────────────────────────────────────────────

@router.get("/agent-defs", response_model=ResponseEnvelope[list[dict]])
async def list_agent_definitions(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """List active agent definitions available for this org."""
    require_role("meeting", current.role)
    from app.repositories.meeting_repo import MeetingRepository
    repo = MeetingRepository(db)
    defs = await repo.list_active_agent_definitions(current.org_id)
    return ResponseEnvelope(data=[
        {
            "id": str(ad.id),
            "name": ad.name,
            "system_prompt": ad.system_prompt,
            "model": ad.model,
            "adapter_type": ad.adapter_type,
            "participation_strategy": ad.participation_strategy,
            "is_active": ad.is_active,
        }
        for ad in defs
    ])


# ── Agents ────────────────────────────────────────────────────────

@router.get("/rooms/{room_id}/agents", response_model=ResponseEnvelope[list[MeetingRoomAgentResponse]])
async def list_room_agents(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_room_agents(room_id))


@router.get("/rooms/{room_id}/members", response_model=ResponseEnvelope[list[MeetingRoomMemberResponse]])
async def list_room_members(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_room_members(room_id))


@router.post("/rooms/{room_id}/agents", response_model=ResponseEnvelope[MeetingRoomAgentResponse])
async def add_agent_to_room(
    room_id: str,
    body: MeetingAddAgentRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.add_agent_to_room(room_id, body.agent_id, body.role))


@router.delete("/rooms/{room_id}/agents/{agent_id}", response_model=ResponseEnvelope[dict])
async def remove_agent_from_room(
    room_id: str,
    agent_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    await service.remove_agent_from_room(room_id, agent_id)
    return ResponseEnvelope(data={"ok": True})


# ── SSE Stream ────────────────────────────────────────────────────

@router.get("/rooms/{room_id}/stream")
async def stream_meeting_events(
    room_id: str,
    token: str = Query(default=""),
    db=Depends(get_db),
):
    current = _get_user_for_stream(token)
    repo = MeetingRepository(db)
    member = await repo.get_member(current.org_id, room_id, current.user_id)
    if not member:
        raise ForbiddenError("you are not a member of this meeting room")

    async def event_generator():
        async for event in meeting_stream_broker.subscribe(room_id):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
