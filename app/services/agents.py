from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.observability.service import ObservabilityService
from app.schemas.agent import AgentCreate, AgentUpdate


class AgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.observability = ObservabilityService(db)

    @staticmethod
    def _sanitize_skills(raw_skills: list[dict] | None) -> list[dict] | None:
        if raw_skills is None:
            return None
        if not isinstance(raw_skills, list):
            return None
        sanitized: list[dict] = []
        for item in raw_skills:
            if not isinstance(item, dict):
                continue
            skill_id = item.get("skill_id")
            if not skill_id:
                continue
            sanitized.append({**item, "skill_id": skill_id})
        return sanitized

    def list_agents(
        self,
        page: int,
        page_size: int,
        keyword: Optional[str],
        is_public: Optional[bool],
        user_id: Optional[str],
    ) -> tuple[list[Agent], int]:
        query = self.db.query(Agent)
        if keyword:
            like_keyword = f"%{keyword}%"
            query = query.filter(Agent.name.ilike(like_keyword))
        if is_public is not None:
            query = query.filter(Agent.is_public == is_public)
        if user_id:
            query = query.filter(Agent.owner_id == user_id)
        total = query.count()
        items = query.order_by(Agent.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        for item in items:
            item.skills = self._sanitize_skills(item.skills)
        return items, total

    def create_agent(self, payload: AgentCreate, owner_id: str) -> Agent:
        agent = Agent(
            name=payload.name,
            description=payload.description,
            owner_id=owner_id,
            prompt_template=payload.prompt_template,
            skills=self._sanitize_skills(payload.skills),
            is_public=payload.is_public,
            status=payload.status,
        )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        self.observability.log_event(
            event_type="agent_created",
            user_id=owner_id,
            agent_id=agent.id,
            metadata={"agent_id": agent.id, "status": agent.status},
        )
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if agent:
            agent.skills = self._sanitize_skills(agent.skills)
        return agent

    def update_agent(self, agent_id: str, payload: AgentUpdate) -> Agent:
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError("智能体不存在")
        update_data = payload.model_dump(exclude_unset=True)
        if "skills" in update_data:
            update_data["skills"] = self._sanitize_skills(update_data.get("skills"))
        for key, value in update_data.items():
            setattr(agent, key, value)
        self.db.commit()
        self.db.refresh(agent)
        agent.skills = self._sanitize_skills(agent.skills)
        return agent

    def delete_agent(self, agent_id: str) -> None:
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError("智能体不存在")
        try:
            self.db.delete(agent)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise RuntimeError("删除智能体失败，请稍后重试") from exc
