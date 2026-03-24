from __future__ import annotations

from pydantic import BaseModel


class MemoryEventItem(BaseModel):
    id: str
    event_type: str
    status: str
    retry_count: int
    trace_id: str | None = None
    conversation_id: str | None = None
    created_at: str
    updated_at: str


class MemoryEventListResponse(BaseModel):
    total: int
    items: list[MemoryEventItem]


class MemoryReplayResponse(BaseModel):
    replayed: int


class MemorySLAResponse(BaseModel):
    retrieval_p95_ms: float
    retrieval_p99_ms: float
    ingest_5s_rate: float
    ingest_10s_rate: float
    writeback_success_rate_daily: float
    trace_coverage_rate: float
