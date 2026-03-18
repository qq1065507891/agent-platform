from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_users(self, page: int, page_size: int, keyword: Optional[str]) -> tuple[list[User], int]:
        query = self.db.query(User)
        if keyword:
            like_keyword = f"%{keyword}%"
            query = query.filter((User.username.ilike(like_keyword)) | (User.email.ilike(like_keyword)))
        total = query.count()
        items = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def create_user(self, payload: UserCreate) -> User:
        user = User(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role,
            status=payload.status,
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("用户名或邮箱已存在") from exc
        self.db.refresh(user)
        return user

    def update_user(self, user_id: str, payload: UserUpdate) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        update_data = payload.model_dump(exclude_unset=True)
        if "password" in update_data:
            update_data["password_hash"] = hash_password(update_data.pop("password"))
        for key, value in update_data.items():
            setattr(user, key, value)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("用户名或邮箱已存在") from exc
        self.db.refresh(user)
        return user

    def import_users(self, users: list[UserCreate]) -> tuple[int, int]:
        success = 0
        failed = 0
        for payload in users:
            try:
                user = User(
                    username=payload.username,
                    email=payload.email,
                    password_hash=hash_password(payload.password),
                    role=payload.role,
                    status=payload.status,
                )
                self.db.add(user)
                self.db.flush()
                success += 1
            except IntegrityError:
                self.db.rollback()
                failed += 1
            except Exception:
                self.db.rollback()
                failed += 1
        self.db.commit()
        return success, failed
