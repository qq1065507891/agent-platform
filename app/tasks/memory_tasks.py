from __future__ import annotations

from typing import Any

import time

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.observability.context import set_request_id, set_trace_id
from app.observability.service import ObservabilityService
from app.services.memory.service import get_memory_service

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.memory_writeback_task", bind=True)
def memory_writeback_task(
    self,
    *,
    user_id: str,
    agent_id: str | None,
    conversation_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
    user_message: str,
    assistant_message: str,
    **_: Any,
) -> dict[str, Any]:
    set_trace_id(trace_id)
    set_request_id(request_id or trace_id)
    start = time.perf_counter()
    status = "success"
    accepted: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        logger.info(
            "memory_writeback_started",
            task_id=self.request.id,
            user_id=user_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
        )
        service = get_memory_service()
        candidates = service.extract_write_candidates(user_message, assistant_message)
        accepted = service.write_long_term_memories(
            user_id=user_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            candidates=candidates,
        )
        logger.info(
            "memory_writeback_succeeded",
            task_id=self.request.id,
            accepted_count=len(accepted),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
        return {
            "task_id": self.request.id,
            "accepted_count": len(accepted),
            "accepted": accepted,
        }
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        logger.exception(
            "memory_writeback_failed",
            task_id=self.request.id,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=exc,
        )
        raise
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        db = SessionLocal()
        try:
            ObservabilityService(db).log_event(
                event_type="memory_writeback",
                user_id=user_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                trace_id=trace_id,
                metadata={
                    "task_id": self.request.id,
                    "status": status,
                    "latency_ms": latency_ms,
                    "accepted_count": len(accepted),
                    "error": error_message,
                },
            )
        except Exception:
            db.rollback()
        finally:
            db.close()


@celery_app.task(name="app.tasks.memory_outbox_dispatch_task", bind=True)
def memory_outbox_dispatch_task(self, batch_size: int = 100) -> dict[str, Any]:
    started = time.perf_counter()
    service = get_memory_service()
    count = service.process_outbox_batch(batch_size=batch_size)
    logger.info(
        "memory_outbox_dispatch_completed",
        task_id=self.request.id,
        batch_size=batch_size,
        dispatched=count,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"dispatched": count}


@celery_app.task(name="app.tasks.memory_event_pipeline_task", bind=True)
def memory_event_pipeline_task(self, batch_size: int = 100) -> dict[str, Any]:
    started = time.perf_counter()
    service = get_memory_service()
    count = service.process_memory_events_batch(batch_size=batch_size)
    logger.info(
        "memory_event_pipeline_completed",
        task_id=self.request.id,
        batch_size=batch_size,
        processed=count,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"processed": count}
