from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.memory.service import MemoryService


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
    def __init__(self):
        self.added = []
        self.events = []
        self.outbox = []
        self.items = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)

    def add(self, obj):
        self.added.append(obj)
        name = obj.__class__.__name__
        if name == "MemoryEvent":
            self.events.append(obj)
        elif name == "MemoryOutbox":
            self.outbox.append(obj)
        elif name == "MemoryItemModel":
            self.items.append(obj)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "MemoryOutbox":
            return _FakeQuery(self.outbox)
        if name == "MemoryEvent":
            return _FakeQuery(self.events)
        if name == "MemoryItemModel":
            return _FakeQuery(self.items)
        return _FakeQuery([])


def test_enqueue_memory_event_creates_event_and_outbox(monkeypatch):
    service = MemoryService()
    fake_session = _FakeSession()

    monkeypatch.setattr("app.services.memory.service.SessionLocal", lambda: fake_session)

    event_id = service.enqueue_memory_event(
        user_id="u1",
        agent_id="a1",
        conversation_id="c1",
        trace_id="t1",
        candidate={"memory_type": "task", "content": "完成部署", "confidence": 0.9, "source": "user", "consistency_level": "eventual"},
    )

    assert event_id
    assert len(fake_session.events) == 1
    assert len(fake_session.outbox) == 1
    assert fake_session.events[0].status == "created"
    assert fake_session.outbox[0].published is False


def test_write_long_term_memories_strong_sync_eventual_async(monkeypatch):
    service = MemoryService()

    persisted: list[dict] = []
    enqueued: list[dict] = []
    indexed: list[dict] = []

    monkeypatch.setattr(
        service,
        "_persist_memory_item",
        lambda **kwargs: persisted.append(kwargs["candidate"]) or True,
    )
    monkeypatch.setattr(
        service,
        "enqueue_memory_event",
        lambda **kwargs: enqueued.append(kwargs["candidate"]) or "evt-1",
    )
    monkeypatch.setattr(
        service,
        "_index_candidates_to_vector_store",
        lambda **kwargs: indexed.extend(kwargs["candidates"]),
    )

    accepted = service.write_long_term_memories(
        user_id="u1",
        agent_id="a1",
        conversation_id="c1",
        trace_id="t1",
        candidates=[
            {"memory_type": "profile", "content": "我叫小明", "confidence": 0.9, "source": "user", "consistency_level": "strong"},
            {"memory_type": "task", "content": "今天完成上线", "confidence": 0.88, "source": "user", "consistency_level": "eventual"},
        ],
    )

    assert len(accepted) == 2
    assert len(persisted) == 1
    assert persisted[0]["memory_type"] == "profile"
    assert len(enqueued) == 1
    assert enqueued[0]["memory_type"] == "task"
    assert len(indexed) == 1


def test_process_outbox_batch_marks_rows_published(monkeypatch):
    service = MemoryService()
    fake_session = _FakeSession()
    now = datetime.now(timezone.utc)
    fake_session.outbox.append(
        SimpleNamespace(published=False, created_at=now, published_at=None, updated_at=now)
    )
    fake_session.outbox.append(
        SimpleNamespace(published=False, created_at=now, published_at=None, updated_at=now)
    )

    monkeypatch.setattr("app.services.memory.service.SessionLocal", lambda: fake_session)

    processed = service.process_outbox_batch(batch_size=10)

    assert processed == 2
    assert all(item.published for item in fake_session.outbox)
