from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.skill import Skill


class SkillService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_skills(
        self,
        page: int,
        page_size: int,
        category: Optional[str],
        source_type: Optional[str],
        status: Optional[str],
    ) -> tuple[list[Skill], int]:
        query = self.db.query(Skill)
        if category:
            query = query.filter(Skill.category == category)
        if source_type:
            query = query.filter(Skill.source_type == source_type)
        if status:
            query = query.filter(Skill.status == status)
        total = query.count()
        items = query.order_by(Skill.installed_at.desc().nullslast(), Skill.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        return items, total
