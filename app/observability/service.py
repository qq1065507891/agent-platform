from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.event_log import EventLog
from app.models.llm_usage import LLMUsage
from app.models.request_log import RequestLog
from app.models.skill_invocation import SkillInvocation
from app.observability.context import (
    get_agent_id,
    get_conversation_id,
    get_trace_id,
    get_user_id,
)


class ObservabilityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def log_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        latency_ms: int,
        trace_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        record = RequestLog(
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
            trace_id=trace_id or get_trace_id(),
            user_id=user_id or get_user_id(),
            created_at=self._now(),
        )
        self.db.add(record)
        self.db.commit()

    def log_llm_usage(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost: float | Decimal = 0,
        latency_ms: int = 0,
        trace_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        record = LLMUsage(
            model=model,
            prompt_tokens=max(prompt_tokens, 0),
            completion_tokens=max(completion_tokens, 0),
            total_tokens=max(total_tokens, 0),
            cost=cost,
            latency_ms=max(latency_ms, 0),
            trace_id=trace_id or get_trace_id(),
            user_id=user_id or get_user_id(),
            agent_id=agent_id or get_agent_id(),
            conversation_id=conversation_id or get_conversation_id(),
            created_at=self._now(),
        )
        self.db.add(record)
        self.db.commit()

    def log_skill_invocation(
        self,
        *,
        skill_id: str,
        status: str,
        latency_ms: int,
        error_code: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        record = SkillInvocation(
            skill_id=skill_id,
            status=status,
            latency_ms=max(latency_ms, 0),
            error_code=error_code,
            trace_id=trace_id or get_trace_id(),
            user_id=user_id or get_user_id(),
            agent_id=agent_id or get_agent_id(),
            conversation_id=conversation_id or get_conversation_id(),
            created_at=self._now(),
        )
        self.db.add(record)
        self.db.commit()

    def log_event(
        self,
        *,
        event_type: str,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        payload = {**(metadata or {})}
        if trace_id or get_trace_id():
            payload.setdefault("trace_id", trace_id or get_trace_id())
        if conversation_id or get_conversation_id():
            payload.setdefault("conversation_id", conversation_id or get_conversation_id())

        record = EventLog(
            event_type=event_type,
            user_id=user_id or get_user_id(),
            agent_id=agent_id or get_agent_id(),
            conversation_id=conversation_id or get_conversation_id(),
            metadata_=payload,
            created_at=self._now(),
        )
        self.db.add(record)
        self.db.commit()
