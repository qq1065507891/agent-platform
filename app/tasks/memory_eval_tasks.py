from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.memory_event import MemoryEvent


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
    return float(values[idx])


@celery_app.task(name="app.tasks.memory_eval_daily_task")
def memory_eval_daily_task() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=1)

    with SessionLocal() as db:
        rows = db.query(MemoryEvent).filter(MemoryEvent.created_at >= start).all()

    retrieval_rows = [r for r in rows if r.event_type == "memory_retrieval"]
    write_rows = [r for r in rows if r.event_type == "memory_write_candidate"]

    retrieval_latencies = sorted([float((r.payload or {}).get("latency_ms", 0) or 0) for r in retrieval_rows])
    p95 = _percentile(retrieval_latencies, 0.95)
    p99 = _percentile(retrieval_latencies, 0.99)

    succeeded = [r for r in write_rows if r.status == "succeeded"]
    writeback_success_rate = float(len(succeeded) / len(write_rows)) if write_rows else 0.0

    lags: list[float] = []
    for row in succeeded:
        if row.updated_at and row.created_at:
            lags.append((row.updated_at - row.created_at).total_seconds())

    ingest_5s_rate = float(len([x for x in lags if x <= 5]) / len(lags)) if lags else 0.0
    ingest_10s_rate = float(len([x for x in lags if x <= 10]) / len(lags)) if lags else 0.0

    trace_coverage_rate = (
        float(len([r for r in write_rows if r.trace_id]) / len(write_rows)) if write_rows else 0.0
    )

    result = {
        "window": "24h",
        "retrieval_p95_ms": p95,
        "retrieval_p99_ms": p99,
        "ingest_5s_rate": ingest_5s_rate,
        "ingest_10s_rate": ingest_10s_rate,
        "writeback_success_rate_daily": writeback_success_rate,
        "trace_coverage_rate": trace_coverage_rate,
        "targets": {
            "retrieval_p95_ms": settings.memory_sla_retrieval_p95_ms,
            "retrieval_p99_ms": settings.memory_sla_retrieval_p99_ms,
            "ingest_5s_rate": settings.memory_sla_ingest_5s_rate,
            "ingest_10s_rate": settings.memory_sla_ingest_10s_rate,
            "writeback_success_rate_daily": settings.memory_sla_writeback_success_rate,
            "trace_coverage_rate": settings.memory_sla_trace_coverage_rate,
        },
        "ok": {
            "retrieval_p95": p95 <= settings.memory_sla_retrieval_p95_ms,
            "retrieval_p99": p99 <= settings.memory_sla_retrieval_p99_ms,
            "ingest_5s": ingest_5s_rate >= settings.memory_sla_ingest_5s_rate,
            "ingest_10s": ingest_10s_rate >= settings.memory_sla_ingest_10s_rate,
            "writeback_success": writeback_success_rate >= settings.memory_sla_writeback_success_rate,
            "trace_coverage": trace_coverage_rate >= settings.memory_sla_trace_coverage_rate,
        },
    }
    return result


@celery_app.task(name="app.tasks.memory_topk_eval_task")
def memory_topk_eval_task() -> dict[str, Any]:
    sample_size = int(settings.memory_eval_sample_size)
    with SessionLocal() as db:
        rows = (
            db.query(MemoryEvent)
            .filter(MemoryEvent.event_type == "memory_retrieval")
            .order_by(MemoryEvent.created_at.desc())
            .limit(sample_size)
            .all()
        )

    # 当前没有人工金标集时，先用 hit_count>0 作为在线代理指标。
    hit_rows = [row for row in rows if int((row.payload or {}).get("hit_count", 0) or 0) > 0]
    hit_rate = float(len(hit_rows) / len(rows)) if rows else 0.0
    return {
        "sample_size": len(rows),
        "topk_hit_rate_proxy": hit_rate,
        "target": 0.95,
        "ok": hit_rate >= 0.95,
    }
