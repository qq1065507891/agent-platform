from __future__ import annotations

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.rag_service import RAGService


def test_exists_by_hash_returns_false_on_collection_errors(monkeypatch):
    service = RAGService()

    class _BrokenStore:
        class _Collection:
            @staticmethod
            def get(**_kwargs):
                raise RuntimeError("boom")

        _collection = _Collection()

    monkeypatch.setattr(service, "_vector_store", lambda: _BrokenStore())

    assert service._exists_by_hash(content_hash="abc", agent_id="agent-1") is False
