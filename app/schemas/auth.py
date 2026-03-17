from __future__ import annotations

from pydantic import BaseModel

from app.schemas.user import UserOut


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
    user: UserOut


class RefreshTokenResponse(BaseModel):
    access_token: str
    expires_in: int
