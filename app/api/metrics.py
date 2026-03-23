from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, and_, case, cast, distinct, func
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.core.responses import success_response
from app.models.agent import Agent
from app.models.event_log import EventLog
from app.models.llm_usage import LLMUsage
from app.models.request_log import RequestLog
from app.schemas.common import APIResponse
from app.schemas.metrics import MetricsAgents, MetricsErrorItem, MetricsErrors, MetricsSummary, MetricsTokenItem

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _parse_window(start_date: str | None, end_date: str | None) -> tuple[datetime, datetime]:
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


@router.get("/summary", response_model=APIResponse)
def get_metrics_summary(
    start_date: str | None = Query(None, description="ISO 日期，例如 2026-03-01"),
    end_date: str | None = Query(None, description="ISO 日期，例如 2026-03-22"),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> APIResponse:
    start, end = _parse_window(start_date, end_date)

    window_filter = and_(RequestLog.created_at >= start, RequestLog.created_at <= end)

    p95_ms = (
        db.query(func.percentile_cont(0.95).within_group(RequestLog.latency_ms))
        .filter(window_filter)
        .scalar()
    )

    total_requests = db.query(func.count(RequestLog.id)).filter(window_filter).scalar() or 0
    success_requests = (
        db.query(func.count(RequestLog.id))
        .filter(window_filter, RequestLog.status_code >= 200, RequestLog.status_code < 400)
        .scalar()
        or 0
    )
    success_rate = float(success_requests / total_requests) if total_requests else 0.0

    token_total = (
        db.query(func.coalesce(func.sum(LLMUsage.total_tokens), 0))
        .filter(LLMUsage.created_at >= start, LLMUsage.created_at <= end)
        .scalar()
        or 0
    )

    agent_created = (
        db.query(func.count(Agent.id))
        .filter(
            Agent.created_at >= start,
            Agent.created_at <= end,
            Agent.status.in_(["draft", "published"]),
        )
        .scalar()
        or 0
    )

    data = MetricsSummary(
        p95_ms=float(p95_ms or 0),
        success_rate=success_rate,
        token_total=int(token_total),
        agent_created=int(agent_created),
    )
    return success_response(data.model_dump())


@router.get("/errors", response_model=APIResponse)
def get_metrics_errors(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    top_n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> APIResponse:
    start, end = _parse_window(start_date, end_date)

    rows = (
        db.query(RequestLog.status_code, func.count(RequestLog.id).label("count"))
        .filter(
            RequestLog.created_at >= start,
            RequestLog.created_at <= end,
            RequestLog.status_code >= 400,
        )
        .group_by(RequestLog.status_code)
        .order_by(func.count(RequestLog.id).desc())
        .limit(top_n)
        .all()
    )

    data = MetricsErrors(
        top_errors=[MetricsErrorItem(code=row.status_code, count=row.count) for row in rows]
    )
    return success_response(data.model_dump())


@router.get("/tokens", response_model=APIResponse)
def get_metrics_tokens(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> APIResponse:
    start, end = _parse_window(start_date, end_date)

    day_col = func.date_trunc("day", LLMUsage.created_at)
    rows = (
        db.query(
            day_col.label("d"),
            func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(LLMUsage.cost), 0).label("cost"),
        )
        .filter(LLMUsage.created_at >= start, LLMUsage.created_at <= end)
        .group_by(day_col)
        .order_by(day_col)
        .all()
    )

    data = [
        MetricsTokenItem(
            date=row.d.date().isoformat(),
            tokens=int(row.tokens or 0),
            cost=float(row.cost or 0),
        ).model_dump()
        for row in rows
    ]
    return success_response(data)


@router.get("/agents", response_model=APIResponse)
def get_metrics_agents(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> APIResponse:
    start, end = _parse_window(start_date, end_date)

    created = (
        db.query(func.count(Agent.id))
        .filter(Agent.created_at >= start, Agent.created_at <= end)
        .scalar()
        or 0
    )

    used = (
        db.query(func.count(distinct(EventLog.user_id)))
        .filter(
            EventLog.created_at >= start,
            EventLog.created_at <= end,
            EventLog.event_type == "agent_use",
        )
        .scalar()
        or 0
    )

    first_window_start = start
    first_window_end = start + timedelta(days=7)
    retention_window_end = first_window_end + timedelta(days=7)

    first_week_users_subq = (
        db.query(EventLog.user_id.label("uid"))
        .filter(
            EventLog.event_type == "agent_use",
            EventLog.user_id.isnot(None),
            EventLog.created_at >= first_window_start,
            EventLog.created_at < first_window_end,
        )
        .group_by(EventLog.user_id)
        .subquery()
    )

    retained_users = (
        db.query(func.count(distinct(EventLog.user_id)))
        .filter(
            EventLog.event_type == "agent_use",
            EventLog.user_id.in_(db.query(first_week_users_subq.c.uid)),
            EventLog.created_at >= first_window_end,
            EventLog.created_at < retention_window_end,
        )
        .scalar()
        or 0
    )

    first_week_users = db.query(func.count(first_week_users_subq.c.uid)).scalar() or 0
    retention_7d = float(retained_users / first_week_users) if first_week_users else 0.0

    data = MetricsAgents(created=int(created), used=int(used), retention_7d=retention_7d)
    return success_response(data.model_dump())
