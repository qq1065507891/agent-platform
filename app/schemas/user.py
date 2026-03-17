from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    email: EmailStr
    role: str = Field(..., pattern=r"^(admin|user|manager)$")
    status: str = Field("active", pattern=r"^(active|disabled)$")


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=32)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
            raise ValueError("password must contain letters and digits")
        return value


class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    email: EmailStr | None = None
    role: str | None = Field(None, pattern=r"^(admin|user|manager)$")
    status: str | None = Field(None, pattern=r"^(active|disabled)$")


class UserOut(UserBase):
    id: str
    created_at: datetime | None = None


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=32)
    login_type: str | None = Field("password", pattern=r"^(password|sso)$")
