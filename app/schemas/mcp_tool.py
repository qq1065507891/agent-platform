from __future__ import annotations

from pydantic import BaseModel, Field


class McpToolCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    transport: str = Field(..., pattern=r"^(stdio|http|sse)$")
    endpoint_url: str | None = Field(None, max_length=500)
    command: str | None = Field(None, max_length=255)
    args: list[str] = Field(default_factory=list)
    env: dict = Field(default_factory=dict)
    auth_config: dict = Field(default_factory=dict)
    enabled: bool = True


class McpToolUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    endpoint_url: str | None = Field(None, max_length=500)
    command: str | None = Field(None, max_length=255)
    args: list[str] | None = None
    env: dict | None = None
    auth_config: dict | None = None
    enabled: bool | None = None


class McpToolTestResponse(BaseModel):
    ok: bool
    message: str
    discovered_tools: int = 0
    latency_ms: int = 0
