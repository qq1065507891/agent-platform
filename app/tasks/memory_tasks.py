from __future__ import annotations

from typing import Any

import time

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.memory_embedding import MemoryEmbedding
from app.models.memory_item import MemoryItemModel
from app.models.memory_record import MemoryRecord
from app.observability.context import set_request_id, set_trace_id
from app.observability.service import ObservabilityService
from app.services.embeddings import get_embeddings
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


@celery_app.task(name="app.tasks.memory_v3_backfill_task", bind=True)
def memory_v3_backfill_task(
    self,
    batch_size: int = 500,
    *,
    after_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    migrated = 0
    skipped = 0
    failed = 0

    embeddings = get_embeddings()

    db = SessionLocal()
    try:
        query = db.query(MemoryItemModel).filter(MemoryItemModel.state == "active")
        if after_id:
            query = query.filter(MemoryItemModel.id > after_id)

        rows = query.order_by(MemoryItemModel.id.asc()).limit(batch_size).all()

        for row in rows:
            content = (row.content or "").strip()
            if not content:
                skipped += 1
                continue

            try:
                service = get_memory_service()
                source_message_id = row.created_by_event_id or f"legacy-{row.id}"
                idempotency_key = service.build_idempotency_key(
                    user_id=row.user_id,
                    agent_id=row.agent_id,
                    conversation_id=(row.tags or {}).get("conversation_id") if isinstance(row.tags, dict) else None,
                    source_message_id=source_message_id,
                    memory_type=row.memory_type,
                    content=content,
                )

                existing = db.query(MemoryRecord).filter(MemoryRecord.idempotency_key == idempotency_key).first()
                if existing:
                    skipped += 1
                    continue

                if dry_run:
                    migrated += 1
                    continue

                record = MemoryRecord(
                    user_id=row.user_id,
                    agent_id=row.agent_id,
                    conversation_id=(row.tags or {}).get("conversation_id") if isinstance(row.tags, dict) else None,
                    source_message_id=source_message_id,
                    memory_type=row.memory_type,
                    content=content,
                    content_norm=service._canonicalize_content(content),
                    idempotency_key=idempotency_key,
                    confidence=float(row.confidence or 0.0),
                    consistency_level=row.consistency_level or "strong",
                    status="active",
                    revision=int(row.version or 1),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                db.add(record)
                db.flush()

                vector = embeddings.embed_documents([content])[0]
                db.merge(
                    MemoryEmbedding(
                        memory_id=record.id,
                        embedding=[float(v) for v in vector],
                        model=(settings.llm_embedding or settings.llm_embedding_model),
                        dim=int(getattr(settings, "llm_embedding_dimensions", 1536)),
                        created_at=row.updated_at,
                    )
                )
                migrated += 1
            except Exception as exc:
                failed += 1
                logger.warning("memory_v3_backfill_item_failed", memory_item_id=row.id, err=str(exc))

        if dry_run:
            db.rollback()
        else:
            db.commit()

        next_after_id = rows[-1].id if rows else after_id
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "memory_v3_backfill_completed",
            task_id=self.request.id,
            batch_size=batch_size,
            after_id=after_id,
            next_after_id=next_after_id,
            dry_run=dry_run,
            migrated=migrated,
            skipped=skipped,
            failed=failed,
            latency_ms=latency_ms,
        )
        return {
            "task_id": self.request.id,
            "batch_size": batch_size,
            "after_id": after_id,
            "next_after_id": next_after_id,
            "dry_run": dry_run,
            "migrated": migrated,
            "skipped": skipped,
            "failed": failed,
            "latency_ms": latency_ms,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.memory_v3_verify_task", bind=True)
def memory_v3_verify_task(self, sample_size: int = 20) -> dict[str, Any]:
    db = SessionLocal()
    try:
        legacy_count = db.query(MemoryItemModel).filter(MemoryItemModel.state == "active").count()
        v3_count = db.query(MemoryRecord).filter(MemoryRecord.status == "active").count()
        embedding_count = db.query(MemoryEmbedding).count()

        missing_embedding = (
            db.query(MemoryRecord)
            .outerjoin(MemoryEmbedding, MemoryEmbedding.memory_id == MemoryRecord.id)
            .filter(MemoryRecord.status == "active", MemoryEmbedding.memory_id.is_(None))
            .count()
        )

        sample_records = (
            db.query(MemoryRecord)
            .filter(MemoryRecord.status == "active")
            .order_by(MemoryRecord.updated_at.desc())
            .limit(sample_size)
            .all()
        )

        sample_preview = [
            {
                "memory_id": item.id,
                "memory_type": item.memory_type,
                "content": item.content[:80],
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in sample_records
        ]

        retrieval_service = get_memory_service()
        retrieval_checked = 0
        retrieval_hit = 0
        for item in sample_records[: min(10, len(sample_records))]:
            query = (item.content or "").strip()[:50]
            if not query:
                continue
            retrieval_checked += 1
            hits = retrieval_service.retrieve_long_term_memories(
                user_id=item.user_id,
                agent_id=item.agent_id,
                query=query,
                top_k=5,
                use_prefetch_cache=False,
            )
            if hits:
                retrieval_hit += 1

        retrieval_hit_rate = (retrieval_hit / retrieval_checked) if retrieval_checked > 0 else 0.0

        result = {
            "legacy_count": legacy_count,
            "v3_count": v3_count,
            "embedding_count": embedding_count,
            "missing_embedding": missing_embedding,
            "sample_preview": sample_preview,
            "retrieval_checked": retrieval_checked,
            "retrieval_hit": retrieval_hit,
            "retrieval_hit_rate": retrieval_hit_rate,
            "healthy": (
                v3_count >= int(legacy_count * 0.95)
                and missing_embedding == 0
                and retrieval_hit_rate >= 0.8
            ),
        }
        logger.info("memory_v3_verify_completed", task_id=self.request.id, **result)
        return result
    finally:
        db.close()
