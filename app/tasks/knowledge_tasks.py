from __future__ import annotations

from typing import Any

import time

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.observability.service import ObservabilityService
from app.services.rag_service import get_rag_service

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.knowledge_purge_deleted_docs_task", bind=True)
def knowledge_purge_deleted_docs_task(
    self,
    *,
    agent_id: str | None = None,
    doc_ids: list[str] | None = None,
    requested_by: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    status = "success"
    error: str | None = None
    result_map: dict[str, int] = {}

    db = SessionLocal()
    try:
        rag_service = get_rag_service()
        result_map = rag_service.purge_deleted_documents(agent_id=agent_id, doc_ids=doc_ids)
        deleted_total = int(sum(result_map.values()))
        logger.info(
            "knowledge_purge_deleted_docs_completed",
            task_id=self.request.id,
            agent_id=agent_id,
            requested_count=len(doc_ids or []),
            deleted_total=deleted_total,
        )
        return {
            "task_id": self.request.id,
            "agent_id": agent_id,
            "deleted_total": deleted_total,
            "results": result_map,
        }
    except Exception as exc:
        status = "failed"
        error = str(exc)
        logger.exception(
            "knowledge_purge_deleted_docs_failed",
            task_id=self.request.id,
            agent_id=agent_id,
            err=error,
            exc_info=exc,
        )
        raise
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            ObservabilityService(db).log_event(
                event_type="knowledge_purge_deleted_docs",
                user_id=requested_by,
                agent_id=agent_id,
                metadata={
                    "task_id": self.request.id,
                    "status": status,
                    "latency_ms": latency_ms,
                    "requested_doc_ids": doc_ids or [],
                    "results": result_map,
                    "deleted_total": int(sum(result_map.values())) if result_map else 0,
                    "error": error,
                },
            )
        except Exception:
            db.rollback()
        finally:
            db.close()
