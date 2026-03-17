from __future__ import annotations

from pydantic import BaseModel, Field


class SkillBase(BaseModel):
    skill_id: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]{2,50}$")
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    category: str = Field(
        ...,
        pattern=r"^(built_in|api|system|custom|ai_powered)$",
    )
    source_type: str = Field(
        ...,
        pattern=r"^(builtin|github|npm|http|local|private_registry)$",
    )
    status: str = Field("active", pattern=r"^(active|disabled)$")
    yaml_definition: dict | None = None


class SkillCreate(SkillBase):
    pass


class SkillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    version: str | None = Field(None, pattern=r"^\d+\.\d+\.\d+$")
    category: str | None = Field(
        None,
        pattern=r"^(built_in|api|system|custom|ai_powered)$",
    )
    source_type: str | None = Field(
        None,
        pattern=r"^(builtin|github|npm|http|local|private_registry)$",
    )
    status: str | None = Field(None, pattern=r"^(active|disabled)$")
    yaml_definition: dict | None = None


class SkillOut(SkillBase):
    id: str
    source_url: str | None = None
    source_version: str | None = None
