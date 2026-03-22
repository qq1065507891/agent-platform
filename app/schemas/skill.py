from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class SkillOut(BaseModel):
    """输出模型保持兼容，避免历史数据因严格正则导致列表接口 500。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    skill_id: str
    name: str
    description: str | None = None
    version: str
    category: str
    source_type: str
    status: str
    yaml_definition: dict | None = None
    source_url: str | None = None
    source_version: str | None = None
    current_revision_id: str | None = None


class SkillLoadRequest(BaseModel):
    source_type: str = Field(..., pattern=r"^(github|npm|http|local|private_registry)$")
    source_url: str | None = None
    source_version: str | None = None
    package_path: str | None = None
    expected_hash: str | None = Field(None, min_length=32, max_length=128)
    skill_id: str | None = None
    name: str | None = None


class SkillLoadResponse(BaseModel):
    task_id: str
    skill_id: str
    status: str = "pending"


class SkillTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class SkillDisableRequest(BaseModel):
    reason: str | None = Field(None, max_length=255)
