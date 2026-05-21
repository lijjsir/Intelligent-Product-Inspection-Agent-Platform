from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MeetingRoomCreateRequest(BaseModel):
    title: str = Field(default="会议室", min_length=1, max_length=120)
    password: str | None = Field(default=None, max_length=64)


class MeetingRoomJoinRequest(BaseModel):
    access_code: str = Field(..., min_length=4, max_length=16)
    password: str | None = Field(default=None, max_length=64)


class MeetingMessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class MeetingRoomResponse(BaseModel):
    id: str
    org_id: str
    title: str
    access_code: str
    created_by: str
    status: str
    member_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeetingMessageResponse(BaseModel):
    id: str
    room_id: str
    user_id: str
    username: str
    seq_no: int
    content: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
