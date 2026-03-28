from __future__ import annotations

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from app.services.rag_service import RAGService


@pytest.mark.rag_light
def test_exists_by_hash_returns_false_on_collection_errors(monkeypatch):
    service = RAGService()

    class _BrokenStore:
        @staticmethod
        def get(**_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(service, "_vector_store", lambda: _BrokenStore())

    assert service._exists_by_hash(content_hash="abc", agent_id="agent-1") is False


@pytest.mark.rag_light
def test_exists_by_hash_uses_agent_filter(monkeypatch):
    service = RAGService()

    captured: dict[str, object] = {}

    class _Store:
        @staticmethod
        def get(**kwargs):
            captured.update(kwargs)
            return {"ids": ["id-1"]}

    monkeypatch.setattr(service, "_vector_store", lambda: _Store())

    assert service._exists_by_hash(content_hash="h1", agent_id="agent-42") is True
    where = captured.get("where")
    assert isinstance(where, dict)
    assert where["content_hash"] == "h1"
    assert where["agent_id"] == "agent-42"
