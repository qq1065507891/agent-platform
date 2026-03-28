from __future__ import annotations

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from langchain_core.documents import Document

from app.services.rag_service import RAGService


def _make_doc(doc_id: str, source: str) -> Document:
    return Document(page_content=f"content-{doc_id}", metadata={"doc_id": doc_id, "source": source})


@pytest.mark.rag_light
def test_retrieve_threshold_filters_and_diversifies_mmr(monkeypatch):
    service = RAGService()

    scored_docs = [
        (_make_doc("d1", "source-a"), 0.95),
        (_make_doc("d2", "source-a"), 0.92),
        (_make_doc("d3", "source-b"), 0.91),
        (_make_doc("d4", "source-c"), 0.4),
    ]

    class _Store:
        @staticmethod
        def similarity_search_with_relevance_scores(*_args, **_kwargs):
            return scored_docs

    monkeypatch.setattr(service, "_vector_store", lambda: _Store())
    monkeypatch.setattr(
        "app.services.rag_service.settings",
        type(
            "S",
            (),
            {
                "rag_similarity_min_score": 0.9,
                "rag_search_type": "mmr",
                "rag_recall_k": 2,
                "rag_mmr_fetch_k": 4,
            },
        )(),
    )

    docs = service.retrieve("query")
    sources = [doc.metadata.get("source") for doc in docs]

    assert len(docs) == 2
    assert set(sources) == {"source-a", "source-b"}


@pytest.mark.rag_light
def test_retrieve_threshold_fallback_when_all_filtered(monkeypatch):
    service = RAGService()

    scored_docs = [
        (_make_doc("d1", "source-a"), 0.4),
        (_make_doc("d2", "source-b"), 0.3),
    ]

    class _Store:
        @staticmethod
        def similarity_search_with_relevance_scores(*_args, **_kwargs):
            return scored_docs

    monkeypatch.setattr(service, "_vector_store", lambda: _Store())
    monkeypatch.setattr(
        "app.services.rag_service.settings",
        type(
            "S",
            (),
            {
                "rag_similarity_min_score": 0.9,
                "rag_search_type": "similarity",
                "rag_recall_k": 2,
                "rag_mmr_fetch_k": 4,
            },
        )(),
    )

    docs = service.retrieve("query")

    assert [doc.metadata.get("doc_id") for doc in docs] == ["d1", "d2"]
