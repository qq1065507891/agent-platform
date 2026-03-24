from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory_ops import router
from app.core.deps import get_db, require_admin
from app.models.memory_event import MemoryEvent


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, _n):
        return self

    def all(self):
        return self.rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _FakeQuery(self.rows)

    def commit(self):
        return None


def _build_app(rows):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def _fake_db():
        yield _FakeDB(rows)

    def _fake_admin():
        return object()

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[require_admin] = _fake_admin
    return app


def test_memory_ops_events_list():
    now = datetime.now(timezone.utc)
    row = MemoryEvent(
        id="evt-1",
        event_type="memory_write_candidate",
        status="created",
        retry_count=0,
        trace_id="tr-1",
        conversation_id="cv-1",
        created_at=now,
        updated_at=now,
    )

    client = TestClient(_build_app([row]))
    resp = client.get("/api/v1/memory-ops/events")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == "evt-1"


def test_memory_ops_sla_calculation():
    now = datetime.now(timezone.utc)
    rows = [
        MemoryEvent(
            id="evt-2",
            event_type="memory_retrieval",
            status="succeeded",
            retry_count=0,
            trace_id="tr-2",
            payload={"latency_ms": 120},
            created_at=now,
            updated_at=now,
        ),
        MemoryEvent(
            id="evt-3",
            event_type="memory_write_candidate",
            status="succeeded",
            retry_count=0,
            trace_id="tr-3",
            created_at=now - timedelta(seconds=1),
            updated_at=now,
        ),
    ]

    client = TestClient(_build_app(rows))
    resp = client.get("/api/v1/memory-ops/sla")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "retrieval_p95_ms" in data
    assert "writeback_success_rate_daily" in data
