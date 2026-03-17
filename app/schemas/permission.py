from __future__ import annotations

from pydantic import BaseModel, Field


class PermissionGrant(BaseModel):
    subject_type: str = Field(..., pattern=r"^(user|role|team)$")
    subject_id: str
    object_type: str = Field(..., pattern=r"^(agent|skill|data)$")
    object_id: str
    actions: list[str] = Field(..., min_length=1)
