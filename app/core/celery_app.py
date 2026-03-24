from __future__ import annotations

import sys

from celery import Celery

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

celery_app = Celery(
    "agent_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=settings.celery_accept_content,
    task_time_limit=settings.celery_task_time_limit,
    timezone="UTC",
    enable_utc=True,
)
logger.info(
    "celery_configured",
    broker=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_time_limit=settings.celery_task_time_limit,
)

# Windows 平台使用 solo 池，避免 billiard prefork 在 fast_trace_task 下的 _loc 解包异常
if sys.platform.startswith("win"):
    celery_app.conf.update(
        worker_pool="solo",
    )

celery_app.autodiscover_tasks(["app.tasks"])
