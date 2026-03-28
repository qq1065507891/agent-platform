from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import success_response
from app.models.user import User
from app.observability.context import get_trace_id
from app.observability.service import ObservabilityService
from app.schemas.common import APIResponse
from app.schemas.metrics import MetricsAgents, MetricsErrors, MetricsSummary, MetricsTokenItem
from app.services.metrics import MetricsQueryScope, MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])


_ALLOWED_SCOPE = {"all", "self"}


def _resolve_metrics_scope(
    *,
    current_user: User,
    requested_scope: str | None,
    requested_user_id: str | None,
    start_date: str | None,
    end_date: str | None,
) -> MetricsQueryScope:
    parsed_scope = (requested_scope or "self").strip().lower() or "self"
    if parsed_scope not in _ALLOWED_SCOPE:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scope 参数非法")

    normalized_target_user_id = (requested_user_id or "").strip() or None

    if current_user.role != "admin":
        if normalized_target_user_id and normalized_target_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限查看其他用户指标")

        scope_value = "self"
        target_user_id = current_user.id
    else:
        scope_value = parsed_scope
        target_user_id = normalized_target_user_id

    start, end = MetricsService.parse_window(start_date, end_date)
    return MetricsQueryScope(
        current_user_id=current_user.id,
        role=current_user.role,
        scope=scope_value,  # type: ignore[arg-type]
        target_user_id=target_user_id,
        start=start,
        end=end,
    )


def _audit_admin_all_scope_if_needed(
    *,
    db: Session,
    current_user: User,
    scope: MetricsQueryScope,
    endpoint: str,
) -> None:
    if current_user.role != "admin":
        return
    if scope.effective_scope != "all":
        return

    ObservabilityService(db).log_event(
        event_type="metrics_admin_view",
        user_id=current_user.id,
        metadata={
            "scope": scope.effective_scope,
            "filters": scope.filters,
            "endpoint": endpoint,
            "trace_id": get_trace_id(),
            "cache_scope_key": scope.cache_scope_key,
        },
    )


@router.get("/overview", response_model=APIResponse)
def get_metrics_overview(
    scope: str | None = Query("self", description="self/all，all 仅管理员可用"),
    start_date: str | None = Query(None, description="ISO 日期，例如 2026-03-01"),
    end_date: str | None = Query(None, description="ISO 日期，例如 2026-03-22"),
    user_id: str | None = Query(None, description="仅管理员可指定某用户"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    query_scope = _resolve_metrics_scope(
        current_user=current_user,
        requested_scope=scope,
        requested_user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    _audit_admin_all_scope_if_needed(db=db, current_user=current_user, scope=query_scope, endpoint="overview")

    data = MetricsService(db).get_overview(query_scope)
    payload = MetricsSummary(**data).model_dump()
    return success_response(payload)


@router.get("/trends", response_model=APIResponse)
def get_metrics_trends(
    scope: str | None = Query("self", description="self/all，all 仅管理员可用"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    user_id: str | None = Query(None, description="仅管理员可指定某用户"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    query_scope = _resolve_metrics_scope(
        current_user=current_user,
        requested_scope=scope,
        requested_user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    _audit_admin_all_scope_if_needed(db=db, current_user=current_user, scope=query_scope, endpoint="trends")

    data = MetricsService(db).get_trends(query_scope)
    payload = [MetricsTokenItem(**item).model_dump() for item in data]
    return success_response(payload)


@router.get("/skills", response_model=APIResponse)
def get_metrics_skills(
    scope: str | None = Query("self", description="self/all，all 仅管理员可用"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    top_n: int = Query(10, ge=1, le=50),
    user_id: str | None = Query(None, description="仅管理员可指定某用户"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    query_scope = _resolve_metrics_scope(
        current_user=current_user,
        requested_scope=scope,
        requested_user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    _audit_admin_all_scope_if_needed(db=db, current_user=current_user, scope=query_scope, endpoint="skills")

    data = MetricsService(db).get_skills(query_scope, top_n=top_n)
    payload = MetricsErrors(**data).model_dump()
    return success_response(payload)


@router.get("/agents", response_model=APIResponse)
def get_metrics_agents(
    scope: str | None = Query("self", description="self/all，all 仅管理员可用"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    user_id: str | None = Query(None, description="仅管理员可指定某用户"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    query_scope = _resolve_metrics_scope(
        current_user=current_user,
        requested_scope=scope,
        requested_user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    _audit_admin_all_scope_if_needed(db=db, current_user=current_user, scope=query_scope, endpoint="agents")

    data = MetricsService(db).get_agents(query_scope)
    payload = MetricsAgents(**data).model_dump()
    return success_response(payload)


# backward-compatible aliases
@router.get("/summary", response_model=APIResponse)
def get_metrics_summary_alias(
    scope: str | None = Query("self"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    user_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    return get_metrics_overview(scope, start_date, end_date, user_id, db, current_user)


@router.get("/tokens", response_model=APIResponse)
def get_metrics_tokens_alias(
    scope: str | None = Query("self"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    user_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    return get_metrics_trends(scope, start_date, end_date, user_id, db, current_user)


@router.get("/errors", response_model=APIResponse)
def get_metrics_errors_alias(
    scope: str | None = Query("self"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    top_n: int = Query(10, ge=1, le=50),
    user_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    return get_metrics_skills(scope, start_date, end_date, top_n, user_id, db, current_user)
