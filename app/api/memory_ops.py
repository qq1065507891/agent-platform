from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db, require_admin
from app.core.responses import success_response
from app.models.memory_event import MemoryEvent
from app.schemas.common import APIResponse
from app.schemas.memory_ops import MemoryEventItem, MemoryEventListResponse, MemoryReplayResponse, MemorySLAResponse

router = APIRouter(prefix="/memory-ops", tags=["memory-ops"])


@router.get("/events", response_model=APIResponse)
def list_memory_events(
    status: str | None = Query(None),
    trace_id: str | None = Query(None),
    conversation_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> APIResponse:
    q = db.query(MemoryEvent)
    if status:
        q = q.filter(MemoryEvent.status == status)
    if trace_id:
        q = q.filter(MemoryEvent.trace_id == trace_id)
    if conversation_id:
        q = q.filter(MemoryEvent.conversation_id == conversation_id)

    rows = q.order_by(MemoryEvent.created_at.desc()).limit(limit).all()
    data = MemoryEventListResponse(
        total=len(rows),
        items=[
            MemoryEventItem(
                id=row.id,
                event_type=row.event_type,
                status=row.status,
                retry_count=int(row.retry_count or 0),
                trace_id=row.trace_id,
                conversation_id=row.conversation_id,
                created_at=row.created_at.isoformat(),
                updated_at=row.updated_at.isoformat(),
            )
            for row in rows
        ],
    )
    return success_response(data.model_dump())


@router.post("/events/replay-dead-letter", response_model=APIResponse)
def replay_dead_letter_events(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> APIResponse:
    rows = (
        db.query(MemoryEvent)
        .filter(MemoryEvent.status == "dead_letter")
        .order_by(MemoryEvent.updated_at.asc())
        .limit(limit)
        .all()
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        row.status = "retry"
        row.next_retry_at = now
        row.updated_at = now
    db.commit()

    return success_response(MemoryReplayResponse(replayed=len(rows)).model_dump())


@router.get("/sla", response_model=APIResponse)
def memory_sla_metrics(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> APIResponse:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=1)

    retrieval_rows = (
        db.query(MemoryEvent)
        .filter(
            MemoryEvent.event_type == "memory_retrieval",
            MemoryEvent.created_at >= window_start,
        )
        .all()
    )
    retrieval_latencies = [
        float((row.payload or {}).get("latency_ms", 0) or 0)
        for row in retrieval_rows
    ]
    retrieval_latencies.sort()

    def _percentile(values: list[float], ratio: float) -> float:
        if not values:
            return 0.0
        idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
        return float(values[idx])

    p95 = _percentile(retrieval_latencies, 0.95)
    p99 = _percentile(retrieval_latencies, 0.99)

    writeback_rows = (
        db.query(MemoryEvent)
        .filter(MemoryEvent.event_type == "memory_write_candidate", MemoryEvent.created_at >= window_start)
        .all()
    )
    success_rows = [row for row in writeback_rows if row.status == "succeeded"]
    writeback_success_rate = float(len(success_rows) / len(writeback_rows)) if writeback_rows else 0.0

    lags: list[float] = []
    for row in success_rows:
        if row.updated_at and row.created_at:
            lags.append((row.updated_at - row.created_at).total_seconds())

    ingest_5s_rate = float(len([x for x in lags if x <= 5]) / len(lags)) if lags else 0.0
    ingest_10s_rate = float(len([x for x in lags if x <= 10]) / len(lags)) if lags else 0.0

    trace_covered = [row for row in writeback_rows if row.trace_id]
    trace_coverage_rate = float(len(trace_covered) / len(writeback_rows)) if writeback_rows else 0.0

    payload = MemorySLAResponse(
        retrieval_p95_ms=p95,
        retrieval_p99_ms=p99,
        ingest_5s_rate=ingest_5s_rate,
        ingest_10s_rate=ingest_10s_rate,
        writeback_success_rate_daily=writeback_success_rate,
        trace_coverage_rate=trace_coverage_rate,
    )

    targets = {
        "retrieval_p95_ms": settings.memory_sla_retrieval_p95_ms,
        "retrieval_p99_ms": settings.memory_sla_retrieval_p99_ms,
        "ingest_5s_rate": settings.memory_sla_ingest_5s_rate,
        "ingest_10s_rate": settings.memory_sla_ingest_10s_rate,
        "writeback_success_rate_daily": settings.memory_sla_writeback_success_rate,
        "trace_coverage_rate": settings.memory_sla_trace_coverage_rate,
    }
    checks = {
        "retrieval_p95": p95 <= settings.memory_sla_retrieval_p95_ms,
        "retrieval_p99": p99 <= settings.memory_sla_retrieval_p99_ms,
        "ingest_5s": ingest_5s_rate >= settings.memory_sla_ingest_5s_rate,
        "ingest_10s": ingest_10s_rate >= settings.memory_sla_ingest_10s_rate,
        "writeback_success": writeback_success_rate >= settings.memory_sla_writeback_success_rate,
        "trace_coverage": trace_coverage_rate >= settings.memory_sla_trace_coverage_rate,
    }

    return success_response({
        "metrics": payload.model_dump(),
        "targets": targets,
        "checks": checks,
    })
