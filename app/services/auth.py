from __future__ import annotations

from sqlalchemy.orm import Session

from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserLogin, UserRegister


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: UserRegister) -> User:
        user = User(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role="user",
            status="active",
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("用户名或邮箱已存在") from exc
        self.db.refresh(user)
        return user

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
