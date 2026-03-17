from __future__ import annotations

from pydantic import BaseModel, Field


class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    permissions: list[str]


class RoleCreate(RoleBase):
    pass


class RoleUpdate(RoleBase):
    pass


class RoleOut(RoleBase):
    id: str
