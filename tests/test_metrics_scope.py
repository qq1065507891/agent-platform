from __future__ import annotations

import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

from app.api.metrics import router
from app.core.deps import get_current_user, get_db


class _DummyQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def scalar(self):
        return 0

    def group_by(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return []

    def subquery(self):
        class _SubQ:
            class c:
                uid = "uid"

        return _SubQ()


class _DummyDB:
    def query(self, *_args, **_kwargs):
        return _DummyQuery()

    def add(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None


def _build_client(user: dict):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def _fake_user():
        return types.SimpleNamespace(**user)

    def _fake_db():
        yield _DummyDB()

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_non_admin_cannot_query_other_user_metrics():
    client = _build_client(
        {
            "id": "u-self",
            "username": "u",
            "email": "u@example.com",
            "role": "user",
            "status": "active",
        }
    )

    resp = client.get("/api/v1/metrics/overview", params={"user_id": "u-other"})

    assert resp.status_code == 403


def test_admin_can_query_all_scope():
    client = _build_client(
        {
            "id": "u-admin",
            "username": "admin",
            "email": "admin@example.com",
            "role": "admin",
            "status": "active",
        }
    )

    resp = client.get("/api/v1/metrics/overview", params={"scope": "all"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
