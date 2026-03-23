from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=200)
    prompt_template: str = Field(..., min_length=1, max_length=4000)
    skills: list[dict] | None = Field(default=None, max_length=50)
    is_public: bool = False
    status: str = Field("draft", pattern=r"^(draft|published|archived)$")

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[dict] | None) -> list[dict] | None:
        if value is None:
            return value
        for item in value:
            if not isinstance(item, dict) or "skill_id" not in item:
                raise ValueError("skills item must contain skill_id")
        return value


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, max_length=200)
    prompt_template: str | None = Field(None, min_length=1, max_length=4000)
    skills: list[dict] | None = None
    is_public: bool | None = None
    status: str | None = Field(None, pattern=r"^(draft|published|archived)$")


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    prompt_template: str
    skills: list[dict] | None = None
    is_public: bool = False
    status: str
    owner_id: str | None = None
    owner_username: str | None = None
    owner_email: str | None = None
    created_at: str | None = None
