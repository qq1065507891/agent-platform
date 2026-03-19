from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RoleBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=64)
    permissions: list[str]


class RoleCreate(RoleBase):
    pass


class RoleUpdate(RoleBase):
    pass


class RoleOut(RoleBase):
    id: str
