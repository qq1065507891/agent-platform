from __future__ import annotations

from io import BytesIO
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

if "pgvector" not in sys.modules:
    from sqlalchemy.types import JSON

    pgvector_mod = types.ModuleType("pgvector")
    pgvector_sqlalchemy_mod = types.ModuleType("pgvector.sqlalchemy")

    def _fake_vector(*_args, **_kwargs):
        return JSON()

    pgvector_sqlalchemy_mod.Vector = _fake_vector
    pgvector_mod.sqlalchemy = pgvector_sqlalchemy_mod
    sys.modules["pgvector"] = pgvector_mod
    sys.modules["pgvector.sqlalchemy"] = pgvector_sqlalchemy_mod

import pytest

from app.api.knowledge import router
from app.core.deps import get_current_user
from app.services.rag_service import (
    IngestResult,
    RAGTextExtractionError,
    RAGUnsupportedFileTypeError,
)


class _SvcUnsupported:
    async def ingest_upload(self, *_args, **_kwargs):
        raise RAGUnsupportedFileTypeError("unsupported file type: .exe")


class _SvcExtractError:
    async def ingest_upload(self, *_args, **_kwargs):
        raise RAGTextExtractionError("failed to extract text")


class _SvcUnknownError:
    async def ingest_upload(self, *_args, **_kwargs):
        raise RuntimeError("unexpected")


class _SvcOK:
    async def ingest_upload(self, *_args, **_kwargs):
        return IngestResult(doc_id="doc-1", version=1, chunk_count=3, ingest_status="indexed")


def _build_client(monkeypatch, svc):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def _fake_user():
        return {
            "id": "u-1",
            "username": "tester",
            "email": "tester@example.com",
            "role": "admin",
            "status": "active",
        }

    app.dependency_overrides[get_current_user] = _fake_user
    monkeypatch.setattr("app.api.knowledge.get_rag_service", lambda: svc)
    return TestClient(app)


def _upload_payload(filename: str = "a.txt"):
    return {"file": (filename, BytesIO(b"hello"), "text/plain")}


@pytest.mark.requires_optional_deps
def test_upload_returns_400_for_unsupported_file(monkeypatch):
    client = _build_client(monkeypatch, _SvcUnsupported())
    resp = client.post(
        "/api/v1/knowledge/upload",
        files=_upload_payload("bad.exe"),
        data={"agent_id": "a-1"},
    )

    assert resp.status_code == 400
    assert "unsupported file type" in resp.json()["detail"]


@pytest.mark.requires_optional_deps
def test_upload_returns_422_for_extraction_error(monkeypatch):
    client = _build_client(monkeypatch, _SvcExtractError())
    resp = client.post(
        "/api/v1/knowledge/upload",
        files=_upload_payload("a.pdf"),
        data={"agent_id": "a-1"},
    )

    assert resp.status_code == 422
    assert "failed to extract" in resp.json()["detail"]


@pytest.mark.requires_optional_deps
def test_upload_returns_500_for_unexpected_error(monkeypatch):
    client = _build_client(monkeypatch, _SvcUnknownError())
    resp = client.post(
        "/api/v1/knowledge/upload",
        files=_upload_payload("a.txt"),
        data={"agent_id": "a-1"},
    )

    assert resp.status_code == 500
    assert "unexpected" in resp.json()["detail"]


@pytest.mark.requires_optional_deps
def test_upload_success_schema(monkeypatch):
    client = _build_client(monkeypatch, _SvcOK())
    resp = client.post(
        "/api/v1/knowledge/upload",
        files=_upload_payload("a.txt"),
        data={"agent_id": "a-1"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["doc_id"] == "doc-1"
    assert payload["data"]["status"] == "indexed"


@pytest.mark.requires_optional_deps
def test_upload_returns_400_when_agent_id_missing(monkeypatch):
    client = _build_client(monkeypatch, _SvcOK())
    resp = client.post("/api/v1/knowledge/upload", files=_upload_payload("a.txt"))

    assert resp.status_code == 400
    assert "agent_id" in resp.json()["detail"]
