from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.tasks.memory_eval_tasks import memory_eval_daily_task, memory_topk_eval_task


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


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)

    def query(self, _model):
        return _FakeQuery(self.rows)


def test_memory_eval_daily_task(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(
            event_type="memory_retrieval",
            payload={"latency_ms": 200},
            status="succeeded",
            trace_id="tr-1",
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        ),
        SimpleNamespace(
            event_type="memory_write_candidate",
            payload={},
            status="succeeded",
            trace_id="tr-2",
            created_at=now - timedelta(seconds=3),
            updated_at=now,
        ),
    ]

    monkeypatch.setattr("app.tasks.memory_eval_tasks.SessionLocal", lambda: _FakeSession(rows))

    result = memory_eval_daily_task()
    assert "ok" in result
    assert "retrieval_p95_ms" in result


def test_memory_topk_eval_task(monkeypatch):
    rows = [
        SimpleNamespace(event_type="memory_retrieval", payload={"hit_count": 1}),
        SimpleNamespace(event_type="memory_retrieval", payload={"hit_count": 0}),
    ]
    monkeypatch.setattr("app.tasks.memory_eval_tasks.SessionLocal", lambda: _FakeSession(rows))

    result = memory_topk_eval_task()
    assert result["sample_size"] == 2
    assert "topk_hit_rate_proxy" in result
