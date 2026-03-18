from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.user import UserLogin


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def login(self, payload: UserLogin) -> tuple[str, int, User]:
        user = self.db.query(User).filter(
            (User.username == payload.username) | (User.email == payload.username)
        ).first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise ValueError("用户名或密码错误")
        if user.status != "active":
            raise ValueError("用户已禁用")
        expires_in = 60 * 60
        token = create_access_token({"sub": user.id}, expires_minutes=expires_in // 60)
        return token, expires_in, user
