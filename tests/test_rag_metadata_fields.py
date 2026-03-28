from __future__ import annotations

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from app.services.rag_service import RAGService


@pytest.mark.rag_light
def test_build_documents_contains_expected_metadata_fields():
    service = RAGService()
    chunks = ["alpha content", "beta content"]

    docs = service._build_documents(
        chunks,
        doc_id="doc-1",
        source_name="sample.txt",
        doc_type="txt",
        content_hash="hash-123",
    )

    assert len(docs) == 2
    for idx, doc in enumerate(docs):
        metadata = doc.metadata
        assert metadata["doc_id"] == "doc-1"
        assert metadata["source"] == "sample.txt"
        assert metadata["doc_type"] == "txt"
        assert metadata["content_hash"] == "hash-123"
        assert metadata["chunk_index"] == idx
        assert metadata["token_estimate"] >= 1
