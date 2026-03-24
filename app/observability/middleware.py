from __future__ import annotations

import time
from typing import Callable

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.observability.context import generate_trace_id, set_request_id, set_trace_id, set_user_id
from app.observability.service import ObservabilityService

logger = get_logger(__name__)


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming_request_id = request.headers.get("X-Request-Id")
        incoming_trace_id = request.headers.get("X-Trace-Id") or incoming_request_id
        trace_id = incoming_trace_id or generate_trace_id()
        request_id = incoming_request_id or trace_id
        set_trace_id(trace_id)
        set_request_id(request_id)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # 用户信息由鉴权依赖填充；中间件阶段先置空，避免脏上下文
            set_user_id(None)

        start = time.perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            if response is not None:
                response.headers["X-Trace-Id"] = trace_id
                response.headers["X-Request-Id"] = request_id

            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=latency_ms,
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )

            await run_in_threadpool(
                self._write_request_log,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=latency_ms,
                trace_id=trace_id,
            )

    @staticmethod
    def _write_request_log(*, method: str, path: str, status_code: int, latency_ms: int, trace_id: str) -> None:
        db = SessionLocal()
        try:
            ObservabilityService(db).log_request(
                method=method,
                path=path,
                status_code=status_code,
                latency_ms=latency_ms,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.warning("observability_request_log_failed", error=str(exc))
            db.rollback()
        finally:
            db.close()
