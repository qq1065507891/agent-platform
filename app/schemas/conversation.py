from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ConversationBase(BaseModel):
    agent_id: str
    user_id: str | None = None
    messages: list[dict] | None = None


class ConversationCreate(BaseModel):
    agent_id: str


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    attachments: list[dict] | None = None


class ConversationOut(ConversationBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime | None = None
    agent_name: str | None = None
    agent_description: str | None = None
