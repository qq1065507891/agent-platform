from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel


class BaseSchema(BaseModel):
    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
    }


class Pagination(BaseSchema):
    list: list[Any]
    total: int
    page: int
    page_size: int


class APIResponse(BaseSchema):
    code: int = 0
    message: str = "ok"
    data: Any | None = None


class ErrorDetail(BaseSchema):
    field: str | None = None
    reason: str | None = None
    trace_id: str | None = None


class ErrorResponse(BaseSchema):
    code: int
    message: str
    detail: ErrorDetail | None = None


class Timestamped(BaseSchema):
    created_at: datetime | None = None
    updated_at: datetime | None = None
