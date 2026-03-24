from __future__ import annotations

import time
from typing import Any

from celery.signals import task_failure, task_postrun, task_prerun

from app.core.logging import get_logger
from app.observability.context import set_request_id, set_trace_id

logger = get_logger(__name__)
_task_start_ts: dict[str, float] = {}


def _bind_trace_context(task: Any) -> None:
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", {}) or {}
    trace_id = headers.get("trace_id") or headers.get("x-trace-id")
    request_id = headers.get("request_id") or headers.get("x-request-id") or trace_id
    if trace_id:
        set_trace_id(trace_id)
    if request_id:
        set_request_id(request_id)


@task_prerun.connect
def on_task_prerun(task_id: str, task: Any, *args: Any, **kwargs: Any) -> None:
    _bind_trace_context(task)
    _task_start_ts[task_id] = time.perf_counter()
    logger.info(
        "celery_task_started",
        task_id=task_id,
        task_name=getattr(task, "name", None),
    )


@task_postrun.connect
def on_task_postrun(task_id: str, task: Any, state: str, retval: Any, *args: Any, **kwargs: Any) -> None:
    _bind_trace_context(task)
    started = _task_start_ts.pop(task_id, None)
    latency_ms = int((time.perf_counter() - started) * 1000) if started else None
    logger.info(
        "celery_task_finished",
        task_id=task_id,
        task_name=getattr(task, "name", None),
        state=state,
        latency_ms=latency_ms,
    )


@task_failure.connect
def on_task_failure(task_id: str, task: Any, exception: BaseException, *args: Any, **kwargs: Any) -> None:
    _bind_trace_context(task)
    logger.exception(
        "celery_task_failed",
        task_id=task_id,
        task_name=getattr(task, "name", None),
        error_type=type(exception).__name__,
        error=str(exception),
        exc_info=exception,
    )
