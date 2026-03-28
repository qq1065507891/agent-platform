from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Lock

from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.memory_embedding import MemoryEmbedding
from app.models.memory_event import MemoryEvent
from app.models.memory_item import MemoryItemModel
from app.models.memory_outbox import MemoryOutbox
from app.models.memory_record import MemoryRecord
from app.observability.context import get_trace_id
from app.services.embeddings import get_embeddings
from app.services.memory.prompts import MEMORY_EXTRACTION_SYSTEM_PROMPT
from app.services.memory.types import ContextBundle, MemoryItem, MemoryWriteCandidate
from app.services.rag_service import _disable_chroma_telemetry


logger = logging.getLogger(__name__)

_PREFETCH_CACHE: dict[tuple[str, str | None, str], tuple[float, list[MemoryItem]]] = {}
_PREFETCH_CACHE_LOCK = Lock()
_PREFETCH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory-prefetch")

STRONG_TYPES = {"profile", "constraint", "preference"}
EVENTUAL_TYPES = {"episode", "summary", "task", "fact"}


class MemoryService:
    def __init__(self) -> None:
        self._collection_name = "user_memories"
        self._persist_path = settings.chroma_persist_path

    def build_short_term_context(self, conversation_messages: list[dict], max_turns: int) -> str:
        if max_turns <= 0:
            return ""

        keep = conversation_messages[-(max_turns * 2) :] if conversation_messages else []
        lines: list[str] = []
        for item in keep:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    def build_running_summary(self, conversation_id: str, messages: list[dict]) -> str:
        if not messages:
            return ""
        tail = messages[-6:]
        parts: list[str] = []
        for item in tail:
            role = item.get("role", "unknown")
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            parts.append(f"{role}: {content[:120]}")
        return " | ".join(parts)

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join((query or "").strip().lower().split())

    @staticmethod
    def _normalize_content(content: str) -> str:
        return " ".join((content or "").strip().lower().split())

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonicalize_content(content: str) -> str:
        text = (content or "").strip().lower()
        text = " ".join(text.split())
        replacements = {
            "，": ",",
            "。": ".",
            "：": ":",
            "；": ";",
            "（": "(",
            "）": ")",
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return text

    def build_idempotency_key(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        conversation_id: str | None,
        source_message_id: str | None,
        memory_type: str,
        content: str,
    ) -> str:
        canonical_content = self._canonicalize_content(content)
        parts = [
            user_id or "",
            agent_id or "",
            conversation_id or "",
            source_message_id or "",
            memory_type or "",
            canonical_content,
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def _prefetch_cache_key(self, user_id: str, agent_id: str | None, query: str) -> tuple[str, str | None, str]:
        return (user_id, agent_id, self._normalize_query(query))

    def _get_prefetch_cache(self, user_id: str, agent_id: str | None, query: str) -> list[MemoryItem] | None:
        ttl = int(getattr(settings, "memory_long_term_prefetch_ttl_seconds", 120))
        now = time.time()
        key = self._prefetch_cache_key(user_id, agent_id, query)

        with _PREFETCH_CACHE_LOCK:
            cached = _PREFETCH_CACHE.get(key)
            if not cached:
                return None
            ts, items = cached
            if (now - ts) > ttl:
                _PREFETCH_CACHE.pop(key, None)
                return None
            return items

    def _set_prefetch_cache(self, user_id: str, agent_id: str | None, query: str, items: list[MemoryItem]) -> None:
        key = self._prefetch_cache_key(user_id, agent_id, query)
        with _PREFETCH_CACHE_LOCK:
            _PREFETCH_CACHE[key] = (time.time(), items)

    def prefetch_long_term_memories(self, user_id: str, agent_id: str | None, query: str, top_k: int = 5) -> None:
        if not getattr(settings, "memory_long_term_prefetch_enabled", True):
            return

        normalized = self._normalize_query(query)
        if not normalized:
            return

        if self._get_prefetch_cache(user_id, agent_id, query) is not None:
            return

        def _job() -> None:
            start = time.perf_counter()
            try:
                items = self.retrieve_long_term_memories(user_id=user_id, agent_id=agent_id, query=query, top_k=top_k)
                self._set_prefetch_cache(user_id, agent_id, query, items)
                logger.info(
                    "[memory-prefetch] done user_id=%s agent_id=%s top_k=%s hit_count=%s latency_ms=%s",
                    user_id,
                    agent_id,
                    top_k,
                    len(items),
                    int((time.perf_counter() - start) * 1000),
                )
            except Exception as exc:
                logger.warning("[memory-prefetch] failed user_id=%s agent_id=%s err=%s", user_id, agent_id, exc)

        _PREFETCH_EXECUTOR.submit(_job)

    def retrieve_long_term_memories(
        self,
        user_id: str,
        agent_id: str | None,
        query: str,
        top_k: int = 5,
        *,
        use_prefetch_cache: bool = True,
    ) -> list[MemoryItem]:
        if not query:
            return []

        if use_prefetch_cache:
            cached = self._get_prefetch_cache(user_id, agent_id, query)
            if cached is not None:
                return cached

        where = self._build_where_filter(user_id=user_id, agent_id=agent_id)

        vector_start = time.perf_counter()
        vector_hits = self._vector_recall_with_timeout(
            query=query,
            top_k=top_k,
            where=where,
            user_id=user_id,
            agent_id=agent_id,
        )
        vector_latency_ms = int((time.perf_counter() - vector_start) * 1000)

        keyword_start = time.perf_counter()
        keyword_hits = self._keyword_recall(user_id=user_id, agent_id=agent_id, query=query, top_k=top_k)
        keyword_latency_ms = int((time.perf_counter() - keyword_start) * 1000)

        merged = self._merge_and_rerank(
            query=query,
            vector_hits=vector_hits,
            keyword_hits=keyword_hits,
            top_k=top_k,
        )

        total_latency_ms = vector_latency_ms + keyword_latency_ms
        self._record_memory_retrieval_event(
            user_id=user_id,
            agent_id=agent_id,
            query=query,
            hit_count=len(merged),
            latency_ms=total_latency_ms,
        )
        self._record_memory_retrieval_breakdown_event(
            user_id=user_id,
            agent_id=agent_id,
            query=query,
            top_k=top_k,
            vector_hits=len(vector_hits),
            lexical_hits=len(keyword_hits),
            merged_hits=len(merged),
            vector_latency_ms=vector_latency_ms,
            lexical_latency_ms=keyword_latency_ms,
            total_latency_ms=total_latency_ms,
        )

        if use_prefetch_cache:
            self._set_prefetch_cache(user_id, agent_id, query, merged)

        logger.info(
            "[memory-recall] user_id=%s agent_id=%s top_k=%s vector_hits=%s keyword_hits=%s merged=%s vector_latency_ms=%s keyword_latency_ms=%s",
            user_id,
            agent_id,
            top_k,
            len(vector_hits),
            len(keyword_hits),
            len(merged),
            vector_latency_ms,
            keyword_latency_ms,
        )
        return merged

    def _vector_recall(
        self,
        *,
        query: str,
        top_k: int,
        where: dict[str, Any],
        user_id: str,
        agent_id: str | None,
    ) -> list[MemoryItem]:
        backend = str(getattr(settings, "memory_backend", "pgvector") or "pgvector").lower()
        if backend == "pgvector":
            return self._vector_recall_pgvector(
                query=query,
                top_k=top_k,
                user_id=user_id,
                agent_id=agent_id,
            )

        store = self._vector_store()
        results = store.similarity_search_with_relevance_scores(query, k=top_k, filter=where)
        memories: list[MemoryItem] = []
        for doc, score in results:
            metadata = doc.metadata or {}
            memories.append(
                {
                    "memory_type": metadata.get("memory_type", "memory"),
                    "content": doc.page_content,
                    "score": float(score),
                    "source": metadata.get("source", "memory"),
                    "user_id": metadata.get("user_id", user_id),
                    "agent_id": metadata.get("agent_id", agent_id),
                }
            )
        return memories

    def _vector_recall_with_timeout(
        self,
        *,
        query: str,
        top_k: int,
        where: dict[str, Any],
        user_id: str,
        agent_id: str | None,
    ) -> list[MemoryItem]:
        if not bool(getattr(settings, "memory_vector_recall_enabled", True)):
            return []

        timeout_s = float(getattr(settings, "memory_vector_recall_timeout_seconds", 1.2))
        if timeout_s <= 0:
            return []

        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory-vector-recall") as executor:
                future = executor.submit(
                    self._vector_recall,
                    query=query,
                    top_k=top_k,
                    where=where,
                    user_id=user_id,
                    agent_id=agent_id,
                )
                return future.result(timeout=timeout_s)
        except TimeoutError:
            logger.warning(
                "[memory-recall] vector timeout user_id=%s agent_id=%s timeout_s=%s query_len=%s",
                user_id,
                agent_id,
                timeout_s,
                len(query or ""),
            )
            return []
        except Exception as exc:
            logger.warning("[memory-recall] vector failed user_id=%s agent_id=%s err=%s", user_id, agent_id, exc)
            return []

    def _keyword_recall(self, *, user_id: str, agent_id: str | None, query: str, top_k: int) -> list[MemoryItem]:
        normalized = self._normalize_content(query)
        if not normalized:
            return []

        backend = str(getattr(settings, "memory_backend", "pgvector") or "pgvector").lower()
        if backend == "pgvector":
            return self._keyword_recall_pgvector(
                user_id=user_id,
                agent_id=agent_id,
                query=normalized,
                top_k=top_k,
            )

        with SessionLocal() as db:
            q = db.query(MemoryItemModel).filter(MemoryItemModel.user_id == user_id, MemoryItemModel.state == "active")
            if agent_id:
                q = q.filter(or_(MemoryItemModel.agent_id == agent_id, MemoryItemModel.agent_id.is_(None)))

            rows = (
                q.filter(MemoryItemModel.normalized_content.contains(normalized))
                .order_by(MemoryItemModel.updated_at.desc())
                .limit(top_k)
                .all()
            )
            return [
                {
                    "memory_type": row.memory_type,
                    "content": row.content,
                    "score": 0.8,
                    "source": row.source,
                    "user_id": row.user_id,
                    "agent_id": row.agent_id,
                }
                for row in rows
            ]

    def _vector_recall_pgvector(
        self,
        *,
        query: str,
        top_k: int,
        user_id: str,
        agent_id: str | None,
    ) -> list[MemoryItem]:
        query_vec = self._embed_text(query)

        with SessionLocal() as db:
            stmt = (
                select(
                    MemoryRecord.id,
                    MemoryRecord.memory_type,
                    MemoryRecord.content,
                    MemoryRecord.user_id,
                    MemoryRecord.agent_id,
                    (1 - MemoryEmbedding.embedding.cosine_distance(query_vec)).label("score"),
                )
                .join(MemoryEmbedding, MemoryEmbedding.memory_id == MemoryRecord.id)
                .where(MemoryRecord.user_id == user_id)
                .where(MemoryRecord.status == "active")
            )
            if agent_id:
                stmt = stmt.where(or_(MemoryRecord.agent_id == agent_id, MemoryRecord.agent_id.is_(None)))
            stmt = stmt.order_by(desc("score")).limit(top_k)

            rows = db.execute(stmt).all()
            return [
                {
                    "memory_id": row.id,
                    "memory_type": row.memory_type,
                    "content": row.content,
                    "score": float(row.score or 0.0),
                    "source": "memory_record",
                    "user_id": row.user_id,
                    "agent_id": row.agent_id,
                }
                for row in rows
            ]

    def _keyword_recall_pgvector(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        query: str,
        top_k: int,
    ) -> list[MemoryItem]:
        tokens = [token for token in query.split(" ") if token]
        if not tokens:
            return []

        with SessionLocal() as db:
            stmt = (
                select(
                    MemoryRecord.id,
                    MemoryRecord.memory_type,
                    MemoryRecord.content,
                    MemoryRecord.user_id,
                    MemoryRecord.agent_id,
                    MemoryRecord.updated_at,
                )
                .where(MemoryRecord.user_id == user_id)
                .where(MemoryRecord.status == "active")
            )
            if agent_id:
                stmt = stmt.where(or_(MemoryRecord.agent_id == agent_id, MemoryRecord.agent_id.is_(None)))

            for token in tokens:
                stmt = stmt.where(MemoryRecord.content_norm.contains(token))

            stmt = stmt.order_by(desc(MemoryRecord.updated_at)).limit(top_k)
            rows = db.execute(stmt).all()
            return [
                {
                    "memory_id": row.id,
                    "memory_type": row.memory_type,
                    "content": row.content,
                    "score": 0.75,
                    "source": "memory_record_lexical",
                    "user_id": row.user_id,
                    "agent_id": row.agent_id,
                }
                for row in rows
            ]

    def _merge_and_rerank(
        self,
        *,
        query: str,
        vector_hits: list[MemoryItem],
        keyword_hits: list[MemoryItem],
        top_k: int,
    ) -> list[MemoryItem]:
        _ = query
        merged: dict[str, MemoryItem] = {}
        for hit in [*vector_hits, *keyword_hits]:
            memory_id = str(hit.get("memory_id") or "").strip()
            key = memory_id or self._normalize_content(str(hit.get("content") or ""))
            if not key:
                continue
            current = merged.get(key)
            if current is None or float(hit.get("score") or 0) > float(current.get("score") or 0):
                merged[key] = hit

        ranked = sorted(merged.values(), key=lambda item: float(item.get("score") or 0), reverse=True)
        return ranked[:top_k]

    def extract_write_candidates(self, user_message: str, assistant_message: str) -> list[MemoryWriteCandidate]:
        llm_candidates = self._extract_candidates_by_llm(user_message, assistant_message)
        if llm_candidates:
            return self._enrich_consistency_levels(llm_candidates)
        return self._enrich_consistency_levels(self._extract_candidates_by_rules(user_message, assistant_message))

    def _enrich_consistency_levels(self, candidates: list[MemoryWriteCandidate]) -> list[MemoryWriteCandidate]:
        output: list[MemoryWriteCandidate] = []
        for item in candidates:
            memory_type = str(item.get("memory_type") or "").strip().lower()
            if memory_type in STRONG_TYPES:
                consistency = "strong"
            else:
                consistency = "eventual"
            output.append(
                {
                    **item,
                    "consistency_level": consistency,
                }
            )
        return output

    def _extract_candidates_by_llm(self, user_message: str, assistant_message: str) -> list[MemoryWriteCandidate]:
        if not getattr(settings, "memory_extraction_use_llm", True):
            return []

        payload = {
            "user_message": (user_message or "").strip(),
            "assistant_message": (assistant_message or "").strip(),
        }
        if not payload["user_message"] and not payload["assistant_message"]:
            return []

        model_name = settings.memory_extraction_model or settings.llm_model
        base_url = settings.memory_extraction_base_url or settings.llm_gateway_url
        api_key = settings.memory_extraction_api_key or settings.llm_api_key
        llm = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            timeout=float(getattr(settings, "memory_extraction_timeout_seconds", 15.0)),
            streaming=False,
        )

        try:
            parsed = self._invoke_llm_for_memory_json(llm, payload)
            if not isinstance(parsed, list):
                return []

            candidates: list[MemoryWriteCandidate] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                memory_type = str(item.get("memory_type") or "").strip().lower()
                if memory_type not in {"preference", "fact", "task", "episode", "profile", "constraint", "summary"}:
                    continue
                text = str(item.get("content") or "").strip()
                if not text:
                    continue
                confidence = float(item.get("confidence") or 0)
                source = str(item.get("source") or "user").strip().lower()
                if source not in {"user", "assistant", "system"}:
                    source = "user"
                candidates.append(
                    {
                        "memory_type": memory_type,
                        "content": text,
                        "confidence": max(0.0, min(1.0, confidence)),
                        "source": source,
                    }
                )
            return candidates
        except Exception:
            return []

    def _invoke_llm_for_memory_json(self, llm: ChatOpenAI, payload: dict[str, str]) -> list[Any]:
        messages = [
            {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

        response = llm.invoke(
            messages,
            response_format={"type": "json_object"},
        )
        content = response.content if isinstance(response.content, str) else ""

        try:
            parsed = json.loads(content) if content else []
        except json.JSONDecodeError:
            parsed = []

        if isinstance(parsed, dict):
            if isinstance(parsed.get("items"), list):
                return parsed["items"]
            if isinstance(parsed.get("memories"), list):
                return parsed["memories"]
            return []

        if isinstance(parsed, list):
            return parsed

        retry_count = int(getattr(settings, "memory_extraction_json_retry_count", 1))
        if retry_count <= 0:
            return []

        retry_prompt = (
            "你上一次没有返回有效 JSON。"
            "请严格返回 JSON 对象，格式为: {\"items\":[...]}，不要输出任何解释文本。"
        )
        retry_response = llm.invoke(
            [
                {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                {"role": "user", "content": retry_prompt},
            ],
            response_format={"type": "json_object"},
        )
        retry_content = retry_response.content if isinstance(retry_response.content, str) else ""
        try:
            retry_parsed = json.loads(retry_content) if retry_content else {}
        except json.JSONDecodeError:
            return []

        if isinstance(retry_parsed, dict):
            if isinstance(retry_parsed.get("items"), list):
                return retry_parsed["items"]
            if isinstance(retry_parsed.get("memories"), list):
                return retry_parsed["memories"]
        if isinstance(retry_parsed, list):
            return retry_parsed

        return []

    def _extract_candidates_by_rules(self, user_message: str, assistant_message: str) -> list[MemoryWriteCandidate]:
        candidates: list[MemoryWriteCandidate] = []
        user_text = (user_message or "").strip()
        assistant_text = (assistant_message or "").strip()

        if "我喜欢" in user_text or "我偏好" in user_text:
            candidates.append(
                {
                    "memory_type": "preference",
                    "content": user_text,
                    "confidence": 0.82,
                    "source": "user",
                }
            )
        if "我叫" in user_text or "我是" in user_text:
            candidates.append(
                {
                    "memory_type": "profile",
                    "content": user_text,
                    "confidence": 0.78,
                    "source": "user",
                }
            )
        if "计划" in user_text or "目标" in user_text or "TODO" in user_text.upper():
            candidates.append(
                {
                    "memory_type": "task",
                    "content": user_text,
                    "confidence": 0.74,
                    "source": "user",
                }
            )
        if assistant_text and "已记录" in assistant_text:
            candidates.append(
                {
                    "memory_type": "episode",
                    "content": assistant_text,
                    "confidence": 0.7,
                    "source": "assistant",
                }
            )

        return candidates

    def write_long_term_memories(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        candidates: list[MemoryWriteCandidate],
        conversation_id: str | None = None,
        trace_id: str | None = None,
        source_message_id: str | None = None,
        db: Session | None = None,
    ) -> list[MemoryWriteCandidate]:
        if not candidates:
            return []

        if not getattr(settings, "memory_writeback_enabled", True):
            return []

        backend = str(getattr(settings, "memory_backend", "pgvector") or "pgvector").lower()
        transactional_enabled = bool(getattr(settings, "memory_transactional_write_enabled", True))

        if backend == "pgvector" and transactional_enabled:
            return self._write_long_term_memories_pgvector(
                user_id=user_id,
                agent_id=agent_id,
                candidates=candidates,
                conversation_id=conversation_id,
                trace_id=trace_id,
                source_message_id=source_message_id,
                db=db,
            )

        accepted: list[MemoryWriteCandidate] = []
        persisted: list[MemoryWriteCandidate] = []
        for candidate in candidates:
            consistency = str(candidate.get("consistency_level") or "eventual")
            if consistency == "strong":
                if self._persist_memory_item(
                    user_id=user_id,
                    agent_id=agent_id,
                    candidate=candidate,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                ):
                    persisted.append(candidate)
                    accepted.append(candidate)
            else:
                self.enqueue_memory_event(
                    user_id=user_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                    candidate=candidate,
                )
                accepted.append(candidate)

        if persisted:
            self._index_candidates_to_vector_store(user_id=user_id, agent_id=agent_id, candidates=persisted)

        return accepted

    def _embed_text(self, content: str, expected_dim: int | None = None) -> list[float]:
        vectors = get_embeddings().embed_documents([content])
        if not vectors:
            raise ValueError("embedding is empty")
        vector = [float(v) for v in vectors[0]]
        if expected_dim is not None and len(vector) != expected_dim:
            raise ValueError(
                f"embedding dimension mismatch: expected={expected_dim}, actual={len(vector)}, "
                f"model={settings.llm_embedding or settings.llm_embedding_model}"
            )
        return vector

    def _write_long_term_memories_pgvector(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        candidates: list[MemoryWriteCandidate],
        conversation_id: str | None,
        trace_id: str | None,
        source_message_id: str | None,
        db: Session | None,
    ) -> list[MemoryWriteCandidate]:
        accepted: list[MemoryWriteCandidate] = []
        owns_session = db is None
        session = db or SessionLocal()
        now = datetime.now(timezone.utc)
        idempotent_hits = 0
        write_start = time.perf_counter()
        write_status = "success"
        write_error: str | None = None

        try:
            for candidate in candidates:
                content = str(candidate.get("content") or "").strip()
                if not content:
                    continue

                memory_type = str(candidate.get("memory_type") or "fact").strip().lower()
                confidence = float(candidate.get("confidence") or 0.0)
                min_confidence = float(getattr(settings, "memory_writeback_min_confidence", 0.7))
                if confidence < min_confidence:
                    continue

                canonical = self._canonicalize_content(content)
                idempotency_key = self.build_idempotency_key(
                    user_id=user_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    source_message_id=source_message_id,
                    memory_type=memory_type,
                    content=content,
                )

                record_insert = insert(MemoryRecord).values(
                    user_id=user_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    source_message_id=source_message_id,
                    memory_type=memory_type,
                    content=content,
                    content_norm=canonical,
                    idempotency_key=idempotency_key,
                    confidence=confidence,
                    consistency_level=str(candidate.get("consistency_level") or "strong"),
                    status="active",
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                record_upsert = record_insert.on_conflict_do_update(
                    index_elements=[MemoryRecord.idempotency_key],
                    set_={
                        "content": content,
                        "content_norm": canonical,
                        "confidence": confidence,
                        "updated_at": now,
                    },
                ).returning(MemoryRecord.id)
                existing = session.execute(
                    select(MemoryRecord.id).where(MemoryRecord.idempotency_key == idempotency_key)
                ).scalar_one_or_none()
                if existing is not None:
                    idempotent_hits += 1

                memory_id = str(session.execute(record_upsert).scalar_one())

                target_dim = int(getattr(settings, "llm_embedding_dimensions", 1024))
                vector = self._embed_text(content, expected_dim=target_dim)
                embedding_insert = insert(MemoryEmbedding).values(
                    memory_id=memory_id,
                    embedding=vector,
                    model=(settings.llm_embedding or settings.llm_embedding_model),
                    dim=target_dim,
                    created_at=now,
                )
                embedding_upsert = embedding_insert.on_conflict_do_update(
                    index_elements=[MemoryEmbedding.memory_id],
                    set_={
                        "embedding": vector,
                        "model": (settings.llm_embedding or settings.llm_embedding_model),
                        "dim": target_dim,
                        "created_at": now,
                    },
                )
                session.execute(embedding_upsert)
                accepted.append(candidate)

            if owns_session:
                session.commit()
            return accepted
        except Exception as exc:
            write_status = "failed"
            write_error = str(exc)
            if owns_session:
                session.rollback()
            raise
        finally:
            latency_ms = int((time.perf_counter() - write_start) * 1000)
            try:
                self._record_memory_transaction_event(
                    user_id=user_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                    status=write_status,
                    accepted_count=len(accepted),
                    candidate_count=len(candidates),
                    idempotent_hits=idempotent_hits,
                    latency_ms=latency_ms,
                    error=write_error,
                )
            except Exception as obs_exc:
                logger.warning("memory transaction event log failed: %s", obs_exc)

            if owns_session:
                session.close()

    def enqueue_memory_event(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        conversation_id: str | None,
        trace_id: str | None,
        candidate: MemoryWriteCandidate,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": user_id,
            "agent_id": agent_id,
            "conversation_id": conversation_id,
            "trace_id": trace_id or get_trace_id(),
            "candidate": dict(candidate),
            "created_at": now.isoformat(),
        }

        with SessionLocal() as db:
            event = MemoryEvent(
                event_type="memory_write_candidate",
                user_id=user_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                trace_id=trace_id or get_trace_id(),
                schema_version=1,
                status="created",
                retry_count=0,
                payload=payload,
                created_at=now,
                updated_at=now,
            )
            outbox = MemoryOutbox(
                topic="memory.writeback",
                payload=payload,
                headers={"schema_version": 1},
                published=False,
                fail_count=0,
                created_at=now,
                updated_at=now,
            )
            db.add(event)
            db.add(outbox)
            db.commit()
            return event.id

    def process_outbox_batch(self, batch_size: int = 100) -> int:
        processed = 0
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            rows = (
                db.query(MemoryOutbox)
                .filter(MemoryOutbox.published.is_(False))
                .order_by(MemoryOutbox.created_at.asc())
                .limit(batch_size)
                .all()
            )
            for row in rows:
                row.published = True
                row.published_at = now
                row.updated_at = now
                processed += 1
            db.commit()
        return processed

    def process_memory_events_batch(self, batch_size: int = 100) -> int:
        processed = 0
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            rows = (
                db.query(MemoryEvent)
                .filter(
                    and_(
                        MemoryEvent.status.in_(["created", "queued", "retry"]),
                        or_(MemoryEvent.next_retry_at.is_(None), MemoryEvent.next_retry_at <= now),
                    )
                )
                .order_by(MemoryEvent.created_at.asc())
                .limit(batch_size)
                .all()
            )

            min_confidence = float(getattr(settings, "memory_writeback_min_confidence", 0.7))
            similarity_threshold = float(getattr(settings, "memory_writeback_similarity_threshold", 0.92))
            max_retries = int(getattr(settings, "memory_event_max_retries", 5))

            for event in rows:
                payload = event.payload or {}
                candidate = dict(payload.get("candidate") or {})
                user_id = str(payload.get("user_id") or "")
                agent_id = payload.get("agent_id")
                conversation_id = payload.get("conversation_id")
                trace_id = payload.get("trace_id")

                event.status = "processing"
                event.updated_at = now

                try:
                    content = str(candidate.get("content") or "").strip()
                    confidence = float(candidate.get("confidence") or 0)
                    if not content or confidence < min_confidence:
                        event.status = "succeeded"
                        event.updated_at = datetime.now(timezone.utc)
                        processed += 1
                        continue

                    inserted = self._persist_memory_item(
                        user_id=user_id,
                        agent_id=agent_id,
                        candidate=candidate,
                        conversation_id=conversation_id,
                        trace_id=trace_id,
                        similarity_threshold=similarity_threshold,
                        event_id=event.id,
                        db=db,
                    )
                    if inserted:
                        self._index_candidates_to_vector_store(
                            user_id=user_id,
                            agent_id=agent_id,
                            candidates=[candidate],
                        )
                    event.status = "succeeded"
                    event.error_code = None
                    event.error_message = None
                    event.updated_at = datetime.now(timezone.utc)
                    processed += 1
                except Exception as exc:
                    event.retry_count = int(event.retry_count or 0) + 1
                    event.error_code = "processing_failed"
                    event.error_message = str(exc)
                    if event.retry_count >= max_retries:
                        event.status = "dead_letter"
                        event.next_retry_at = None
                    else:
                        event.status = "retry"
                        backoff_seconds = min(2 ** event.retry_count, 300)
                        event.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                    event.updated_at = datetime.now(timezone.utc)

            db.commit()

        return processed

    def _persist_memory_item(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        candidate: MemoryWriteCandidate,
        conversation_id: str | None,
        trace_id: str | None,
        similarity_threshold: float | None = None,
        event_id: str | None = None,
        db: Session | None = None,
    ) -> bool:
        content = str(candidate.get("content") or "").strip()
        if not content:
            return False

        confidence = float(candidate.get("confidence") or 0)
        min_confidence = float(getattr(settings, "memory_writeback_min_confidence", 0.7))
        if confidence < min_confidence:
            return False

        threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else float(getattr(settings, "memory_writeback_similarity_threshold", 0.92))
        )

        normalized_content = self._normalize_content(content)
        where = self._build_where_filter(user_id=user_id, agent_id=agent_id)
        similar = self._vector_store().similarity_search_with_relevance_scores(content, k=1, filter=where)
        if similar:
            _doc, score = similar[0]
            if float(score) >= threshold:
                return False

        owns_session = db is None
        session = db or SessionLocal()
        now = datetime.now(timezone.utc)

        try:
            memory_type = str(candidate.get("memory_type") or "fact")
            source = str(candidate.get("source") or "user")
            consistency_level = str(candidate.get("consistency_level") or "eventual")

            if memory_type in STRONG_TYPES:
                previous = (
                    session.query(MemoryItemModel)
                    .filter(
                        MemoryItemModel.user_id == user_id,
                        MemoryItemModel.agent_id == agent_id,
                        MemoryItemModel.memory_type == memory_type,
                        MemoryItemModel.state == "active",
                    )
                    .all()
                )
                for row in previous:
                    row.state = "superseded"
                    row.updated_at = now

            item = MemoryItemModel(
                user_id=user_id,
                agent_id=agent_id,
                memory_type=memory_type,
                consistency_level=consistency_level,
                source=source,
                content=content,
                normalized_content=normalized_content,
                confidence=confidence,
                state="active",
                version=1,
                ttl_seconds=int(getattr(settings, "memory_default_ttl_seconds", 0) or 0) or None,
                valid_from=now,
                valid_to=None,
                tags={
                    "conversation_id": conversation_id,
                    "content_hash": self._content_hash(normalized_content),
                },
                created_by_event_id=event_id,
                trace_id=trace_id or get_trace_id(),
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            if owns_session:
                session.commit()
            return True
        except Exception:
            if owns_session:
                session.rollback()
            raise
        finally:
            if owns_session:
                session.close()

    def _record_memory_retrieval_event(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        query: str,
        hit_count: int,
        latency_ms: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            db.add(
                MemoryEvent(
                    event_type="memory_retrieval",
                    user_id=user_id,
                    agent_id=agent_id,
                    trace_id=get_trace_id(),
                    schema_version=1,
                    status="succeeded",
                    retry_count=0,
                    payload={
                        "query": query,
                        "hit_count": hit_count,
                        "latency_ms": latency_ms,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

    def _record_memory_retrieval_breakdown_event(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        query: str,
        top_k: int,
        vector_hits: int,
        lexical_hits: int,
        merged_hits: int,
        vector_latency_ms: int,
        lexical_latency_ms: int,
        total_latency_ms: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            db.add(
                MemoryEvent(
                    event_type="memory_retrieval_breakdown",
                    user_id=user_id,
                    agent_id=agent_id,
                    trace_id=get_trace_id(),
                    schema_version=1,
                    status="succeeded",
                    retry_count=0,
                    payload={
                        "query": query,
                        "top_k": top_k,
                        "vector_hits": vector_hits,
                        "lexical_hits": lexical_hits,
                        "merged_hits": merged_hits,
                        "vector_latency_ms": vector_latency_ms,
                        "lexical_latency_ms": lexical_latency_ms,
                        "total_latency_ms": total_latency_ms,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

    def _record_memory_transaction_event(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        conversation_id: str | None,
        trace_id: str | None,
        status: str,
        accepted_count: int,
        candidate_count: int,
        idempotent_hits: int,
        latency_ms: int,
        error: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            db.add(
                MemoryEvent(
                    event_type="memory_transaction_write",
                    user_id=user_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    trace_id=trace_id or get_trace_id(),
                    schema_version=1,
                    status=status,
                    retry_count=0,
                    error_message=error,
                    payload={
                        "accepted_count": accepted_count,
                        "candidate_count": candidate_count,
                        "idempotent_hits": idempotent_hits,
                        "latency_ms": latency_ms,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

    def _index_candidates_to_vector_store(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        candidates: list[MemoryWriteCandidate],
    ) -> None:
        if not candidates:
            return

        store = self._vector_store()
        documents: list[Document] = []
        for candidate in candidates:
            content = str(candidate.get("content") or "").strip()
            if not content:
                continue
            metadata = {
                "user_id": user_id,
                "agent_id": agent_id,
                "memory_type": candidate.get("memory_type", "memory"),
                "source": candidate.get("source", "user"),
                "consistency_level": candidate.get("consistency_level", "eventual"),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            documents.append(Document(page_content=content, metadata=metadata))

        if documents:
            store.add_documents(documents)

    def compose_context_bundle(
        self,
        *,
        user_query: str,
        conversation_id: str,
        user_id: str,
        agent_id: str | None,
        history: list[dict],
        include_long_term: bool = True,
    ) -> ContextBundle:
        short_context = self.build_short_term_context(
            history,
            max_turns=int(getattr(settings, "memory_short_term_max_turns", 10)),
        )
        summary = self.build_running_summary(conversation_id, history)
        long_memories = (
            self.retrieve_long_term_memories(
                user_id=user_id,
                agent_id=agent_id,
                query=user_query,
                top_k=int(getattr(settings, "memory_long_term_top_k", 5)),
                use_prefetch_cache=True,
            )
            if include_long_term
            else []
        )

        long_memory_text = "\n".join([f"- {item.get('content', '')}" for item in long_memories])
        budget = {
            "input_chars": len(user_query or "") + len(short_context) + len(summary) + len(long_memory_text),
            "short_context_chars": len(short_context),
            "summary_chars": len(summary),
            "long_memory_chars": len(long_memory_text),
        }

        return {
            "short_context": short_context,
            "summary": summary,
            "long_memories": long_memories,
            "budget": budget,
        }

    @staticmethod
    def _build_where_filter(user_id: str, agent_id: str | None) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"user_id": {"$eq": user_id}}]
        if agent_id:
            clauses.append({"agent_id": {"$eq": agent_id}})
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def _vector_store(self) -> Chroma:
        _disable_chroma_telemetry()
        from chromadb.config import Settings as ChromaSettings
        import chromadb

        chroma_settings = ChromaSettings(anonymized_telemetry=False)
        if settings.chroma_url:
            client = chromadb.HttpClient(host=settings.chroma_url, settings=chroma_settings)
        else:
            client = chromadb.PersistentClient(path=str(self._persist_path), settings=chroma_settings)

        return Chroma(
            client=client,
            collection_name=self._collection_name,
            embedding_function=get_embeddings(),
        )


def get_memory_service() -> MemoryService:
    return MemoryService()
