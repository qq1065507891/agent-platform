from __future__ import annotations

from typing import Any

from app.schemas.common import APIResponse


def success_response(data: Any | None = None) -> APIResponse:
    return APIResponse(code=0, message="ok", data=data or {})
