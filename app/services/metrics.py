from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.event_log import EventLog
from app.models.llm_usage import LLMUsage
from app.models.request_log import RequestLog


ScopeType = Literal["all", "self"]


@dataclass(frozen=True)
class MetricsQueryScope:
    current_user_id: str
    role: str
    scope: ScopeType
    target_user_id: str | None
    start: datetime
    end: datetime
    agent_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def effective_user_id(self) -> str | None:
        if not self.is_admin:
            return self.current_user_id
        if self.target_user_id:
            return self.target_user_id
        if self.scope == "self":
            return self.current_user_id
        return None

    @property
    def effective_scope(self) -> str:
        return "all" if self.effective_user_id is None else "self"

    @property
    def filters(self) -> dict[str, str | None]:
        return {
            "start_date": self.start.date().isoformat(),
            "end_date": self.end.date().isoformat(),
            "target_user_id": self.target_user_id,
            "effective_user_id": self.effective_user_id,
            "agent_id": self.agent_id,
        }

    @property
    def cache_scope_key(self) -> str:
        # 统一缓存维度（当前未接入缓存，预留 key 口径，避免跨 scope 污染）
        return "|".join(
            [
                f"role:{self.role}",
                f"current_user:{self.current_user_id}",
                f"scope:{self.scope}",
                f"target_user:{self.target_user_id or '-'}",
                f"effective_user:{self.effective_user_id or 'all'}",
                f"agent_id:{self.agent_id or '-'}",
                f"start:{self.start.date().isoformat()}",
                f"end:{self.end.date().isoformat()}",
            ]
        )


class MetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def parse_window(start_date: str | None, end_date: str | None) -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        if start_date and end_date:
            start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        else:
            end = now
            start = now - timedelta(days=7)
        if end < start:
            start, end = end, start
        return start, end

    @staticmethod
    def apply_user_filter(filters: list, *, column, scope: MetricsQueryScope) -> list:
        user_id = scope.effective_user_id
        if user_id:
            filters.append(column == user_id)
        return filters

    def get_overview(self, scope: MetricsQueryScope) -> dict[str, float | int]:
        request_filters = [RequestLog.created_at >= scope.start, RequestLog.created_at <= scope.end]
        self.apply_user_filter(request_filters, column=RequestLog.user_id, scope=scope)

        p95_ms = (
            self.db.query(func.percentile_cont(0.95).within_group(RequestLog.latency_ms))
            .filter(*request_filters)
            .scalar()
        )
        total_requests = self.db.query(func.count(RequestLog.id)).filter(*request_filters).scalar() or 0
        success_requests = (
            self.db.query(func.count(RequestLog.id))
            .filter(*request_filters, RequestLog.status_code >= 200, RequestLog.status_code < 400)
            .scalar()
            or 0
        )
        success_rate = float(success_requests / total_requests) if total_requests else 0.0

        llm_filters = [LLMUsage.created_at >= scope.start, LLMUsage.created_at <= scope.end]
        self.apply_user_filter(llm_filters, column=LLMUsage.user_id, scope=scope)
        token_total = self.db.query(func.coalesce(func.sum(LLMUsage.total_tokens), 0)).filter(*llm_filters).scalar() or 0

        agent_filters = [
            Agent.created_at >= scope.start,
            Agent.created_at <= scope.end,
            Agent.status.in_(["draft", "published"]),
        ]
        self.apply_user_filter(agent_filters, column=Agent.owner_id, scope=scope)
        agent_created = self.db.query(func.count(Agent.id)).filter(*agent_filters).scalar() or 0

        return {
            "p95_ms": float(p95_ms or 0),
            "success_rate": success_rate,
            "token_total": int(token_total),
            "agent_created": int(agent_created),
        }

    def get_trends(self, scope: MetricsQueryScope) -> list[dict[str, str | int | float]]:
        day_col = func.date_trunc("day", LLMUsage.created_at)
        llm_filters = [LLMUsage.created_at >= scope.start, LLMUsage.created_at <= scope.end]
        self.apply_user_filter(llm_filters, column=LLMUsage.user_id, scope=scope)

        rows = (
            self.db.query(
                day_col.label("d"),
                func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LLMUsage.cost), 0).label("cost"),
            )
            .filter(*llm_filters)
            .group_by(day_col)
            .order_by(day_col)
            .all()
        )

        return [
            {
                "date": row.d.date().isoformat(),
                "tokens": int(row.tokens or 0),
                "cost": float(row.cost or 0),
            }
            for row in rows
        ]

    def get_skills(self, scope: MetricsQueryScope, *, top_n: int = 10) -> dict[str, list[dict[str, int]]]:
        request_filters = [
            RequestLog.created_at >= scope.start,
            RequestLog.created_at <= scope.end,
            RequestLog.status_code >= 400,
        ]
        self.apply_user_filter(request_filters, column=RequestLog.user_id, scope=scope)

        rows = (
            self.db.query(RequestLog.status_code, func.count(RequestLog.id).label("count"))
            .filter(*request_filters)
            .group_by(RequestLog.status_code)
            .order_by(func.count(RequestLog.id).desc())
            .limit(top_n)
            .all()
        )

        return {
            "top_errors": [{"code": row.status_code, "count": row.count} for row in rows],
        }

    def get_agents(self, scope: MetricsQueryScope) -> dict[str, int | float]:
        agent_filters = [Agent.created_at >= scope.start, Agent.created_at <= scope.end]
        self.apply_user_filter(agent_filters, column=Agent.owner_id, scope=scope)
        created = self.db.query(func.count(Agent.id)).filter(*agent_filters).scalar() or 0

        event_filters = [
            EventLog.created_at >= scope.start,
            EventLog.created_at <= scope.end,
            EventLog.event_type == "agent_use",
        ]
        self.apply_user_filter(event_filters, column=EventLog.user_id, scope=scope)
        used = self.db.query(func.count(distinct(EventLog.user_id))).filter(*event_filters).scalar() or 0

        first_window_start = scope.start
        first_window_end = scope.start + timedelta(days=7)
        retention_window_end = first_window_end + timedelta(days=7)

        first_week_filters = [
            EventLog.event_type == "agent_use",
            EventLog.user_id.isnot(None),
            EventLog.created_at >= first_window_start,
            EventLog.created_at < first_window_end,
        ]
        self.apply_user_filter(first_week_filters, column=EventLog.user_id, scope=scope)

        first_week_users_subq = (
            self.db.query(EventLog.user_id.label("uid"))
            .filter(*first_week_filters)
            .group_by(EventLog.user_id)
            .subquery()
        )

        retained_filters = [
            EventLog.event_type == "agent_use",
            EventLog.user_id.in_(self.db.query(first_week_users_subq.c.uid)),
            EventLog.created_at >= first_window_end,
            EventLog.created_at < retention_window_end,
        ]
        self.apply_user_filter(retained_filters, column=EventLog.user_id, scope=scope)

        retained_users = self.db.query(func.count(distinct(EventLog.user_id))).filter(*retained_filters).scalar() or 0
        first_week_users = self.db.query(func.count(first_week_users_subq.c.uid)).scalar() or 0
        retention_7d = float(retained_users / first_week_users) if first_week_users else 0.0

        return {
            "created": int(created),
            "used": int(used),
            "retention_7d": retention_7d,
        }
