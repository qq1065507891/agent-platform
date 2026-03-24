from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import agents as agents_router
from app.api import auth as auth_router
from app.api import conversations as conversations_router
from app.api import knowledge as knowledge_router
from app.api import memory_ops as memory_ops_router
from app.api import metrics as metrics_router
from app.api import permissions as permissions_router
from app.api import roles as roles_router
from app.api import skills as skills_router
from app.api import users as users_router
from app.core.logging import get_logger, setup_logging
from app.observability.context import get_request_id, get_trace_id
from app.observability.middleware import TraceMiddleware
from app.schemas.common import ErrorDetail, ErrorResponse


setup_logging()
logger = get_logger("agent-platform")

app = FastAPI(title="Agent Platform API", version="v1")
app.add_middleware(TraceMiddleware)

app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(users_router.router, prefix="/api/v1")
app.include_router(roles_router.router, prefix="/api/v1")
app.include_router(permissions_router.router, prefix="/api/v1")
app.include_router(agents_router.router, prefix="/api/v1")
app.include_router(conversations_router.router, prefix="/api/v1")
app.include_router(skills_router.router, prefix="/api/v1")
app.include_router(knowledge_router.router, prefix="/api/v1")
app.include_router(memory_ops_router.router, prefix="/api/v1")
app.include_router(metrics_router.router, prefix="/api/v1")


@app.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    trace_id = get_trace_id()
    detail = ErrorDetail(reason="参数错误", trace_id=trace_id)
    if exc.errors():
        first = exc.errors()[0]
        detail.field = ".".join(str(item) for item in first.get("loc", []))
        detail.reason = first.get("msg", "参数错误")
    payload = ErrorResponse(code=4001, message="参数错误", detail=detail)
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    trace_id = get_trace_id()
    request_id = get_request_id()
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=str(exc.detail),
    )
    payload = ErrorResponse(
        code=exc.status_code,
        message=exc.detail if isinstance(exc.detail, str) else "请求错误",
        detail=ErrorDetail(reason=str(exc.detail), trace_id=trace_id),
    )
    response = JSONResponse(status_code=exc.status_code, content=payload.model_dump())
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    trace_id = get_trace_id()
    request_id = get_request_id()
    logger.exception("unhandled_exception", error_type=type(exc).__name__, error=str(exc), exc_info=exc)
    payload = ErrorResponse(
        code=5000,
        message="服务器内部错误",
        detail=ErrorDetail(reason=str(exc), trace_id=trace_id),
    )
    response = JSONResponse(status_code=500, content=payload.model_dump())
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return response
