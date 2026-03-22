from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.skill import ExternalSkillRevision, Skill
from app.services.skills.registry import BuiltinSkillRegistry


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

    def get_by_id(self, skill_id: str) -> Skill | None:
        return self.db.query(Skill).filter(Skill.id == skill_id).first()

    def get_by_skill_code(self, skill_code: str) -> Skill | None:
        return self.db.query(Skill).filter(Skill.skill_id == skill_code).first()

    def upsert_external_skill_stub(
        self,
        *,
        source_type: str,
        source_url: str | None,
        source_version: str | None,
        skill_code: str | None = None,
        name: str | None = None,
    ) -> Skill:
        resolved_skill_code = (skill_code or "external_skill").strip() or "external_skill"
        existing = self.get_by_skill_code(resolved_skill_code)
        if existing:
            return existing

        skill = Skill(
            skill_id=resolved_skill_code,
            name=name or resolved_skill_code,
            version=source_version or "1.0.0",
            category="custom",
            source_type=source_type,
            source_url=source_url,
            source_version=source_version,
            status="disabled",
            yaml_definition={},
        )
        self.db.add(skill)
        self.db.commit()
        self.db.refresh(skill)
        return skill

    def disable_skill(self, skill_id: str, reason: str | None = None) -> Skill:
        skill = self.get_by_id(skill_id)

        # 支持禁用 built-in：若传入的是 built-in 的稳定 UUID，则在 DB 创建/更新覆盖记录
        if not skill:
            builtin_items = BuiltinSkillRegistry().list_skills()
            builtin = next((item for item in builtin_items if item["id"] == skill_id), None)
            if builtin:
                existing = self.get_by_skill_code(builtin["skill_id"])
                if existing:
                    skill = existing
                else:
                    skill = Skill(
                        skill_id=builtin["skill_id"],
                        name=builtin["name"],
                        description=builtin.get("description"),
                        version=builtin["version"],
                        category=builtin["category"],
                        source_type=builtin["source_type"],
                        status="active",
                        yaml_definition={},
                    )
                    self.db.add(skill)
                    self.db.commit()
                    self.db.refresh(skill)
            else:
                raise ValueError("技能不存在")

        skill.status = "disabled"
        if skill.current_revision_id:
            revision = (
                self.db.query(ExternalSkillRevision)
                .filter(ExternalSkillRevision.id == skill.current_revision_id)
                .first()
            )
            if revision:
                revision.status = "disabled"
                if reason:
                    revision.error_message = reason

        self.db.commit()
        self.db.refresh(skill)
        return skill

    def enable_skill(self, skill_id: str) -> Skill:
        skill = self.get_by_id(skill_id)

        # 支持启用 built-in：若传入的是 built-in 的稳定 UUID，则在 DB 创建/更新覆盖记录
        if not skill:
            builtin_items = BuiltinSkillRegistry().list_skills()
            builtin = next((item for item in builtin_items if item["id"] == skill_id), None)
            if builtin:
                existing = self.get_by_skill_code(builtin["skill_id"])
                if existing:
                    skill = existing
                else:
                    skill = Skill(
                        skill_id=builtin["skill_id"],
                        name=builtin["name"],
                        description=builtin.get("description"),
                        version=builtin["version"],
                        category=builtin["category"],
                        source_type=builtin["source_type"],
                        status="disabled",
                        yaml_definition={},
                    )
                    self.db.add(skill)
                    self.db.commit()
                    self.db.refresh(skill)
            else:
                raise ValueError("技能不存在")

        skill.status = "active"
        if skill.current_revision_id:
            revision = (
                self.db.query(ExternalSkillRevision)
                .filter(ExternalSkillRevision.id == skill.current_revision_id)
                .first()
            )
            if revision:
                revision.status = "active"

        self.db.commit()
        self.db.refresh(skill)
        return skill

    def delete_skill(self, skill_id: str) -> None:
        skill = self.get_by_id(skill_id)

        # 允许传 built-in 稳定 UUID：若存在 DB 覆盖记录则删除该记录
        if not skill:
            builtin_items = BuiltinSkillRegistry().list_skills()
            builtin = next((item for item in builtin_items if item["id"] == skill_id), None)
            if builtin:
                existing = self.get_by_skill_code(builtin["skill_id"])
                if not existing:
                    raise ValueError("内置技能不可删除")
                skill = existing
            else:
                raise ValueError("技能不存在")

        # 打断 Skill.current_revision_id -> ExternalSkillRevision 的引用，避免删除环依赖
        if skill.current_revision_id:
            skill.current_revision_id = None
            self.db.flush()

        # 显式删除关联 revisions，再删除 skill，避免 SQLAlchemy CircularDependencyError
        for revision in list(skill.revisions):
            self.db.delete(revision)

        self.db.delete(skill)
        self.db.commit()

    def get_skill_execution_code(self, skill_code: str) -> str | None:
        skill = self.get_by_skill_code(skill_code)
        if not skill or not skill.current_revision_id or skill.status != "active":
            return None

        revision = (
            self.db.query(ExternalSkillRevision)
            .filter(ExternalSkillRevision.id == skill.current_revision_id)
            .first()
        )
        if not revision or revision.status != "active":
            return None
        return revision.code_content
