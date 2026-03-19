from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.role import Role
from app.schemas.role import RoleCreate, RoleUpdate


class RoleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_roles(self) -> list[Role]:
        return self.db.query(Role).order_by(Role.name.asc()).all()

    def create_role(self, payload: RoleCreate) -> Role:
        role = Role(name=payload.name, permissions=payload.permissions)
        self.db.add(role)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("角色名称已存在") from exc
        self.db.refresh(role)
        return role

    def update_role(self, role_id: str, payload: RoleUpdate) -> Role:
        role = self.db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError("角色不存在")
        role.name = payload.name
        role.permissions = payload.permissions
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("角色名称已存在") from exc
        self.db.refresh(role)
        return role
