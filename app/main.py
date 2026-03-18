from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import agents as agents_router
from app.api import auth as auth_router
from app.api import conversations as conversations_router
from app.api import skills as skills_router
from app.api import users as users_router
from app.schemas.common import ErrorDetail, ErrorResponse


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-platform")

app = FastAPI(title="Agent Platform API", version="v1")

app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(users_router.router, prefix="/api/v1")
app.include_router(agents_router.router, prefix="/api/v1")
app.include_router(conversations_router.router, prefix="/api/v1")
app.include_router(skills_router.router, prefix="/api/v1")


@app.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    detail = ErrorDetail(reason="参数错误")
    if exc.errors():
        first = exc.errors()[0]
        detail.field = ".".join(str(item) for item in first.get("loc", []))
        detail.reason = first.get("msg", "参数错误")
    payload = ErrorResponse(code=4001, message="参数错误", detail=detail)
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    payload = ErrorResponse(
        code=exc.status_code,
        message=exc.detail if isinstance(exc.detail, str) else "请求错误",
        detail=ErrorDetail(reason=str(exc.detail)),
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


@app.exception_handler(Exception)
async def global_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    payload = ErrorResponse(
        code=5000,
        message="服务器内部错误",
        detail=ErrorDetail(reason=str(exc)),
    )
    return JSONResponse(status_code=500, content=payload.model_dump())
