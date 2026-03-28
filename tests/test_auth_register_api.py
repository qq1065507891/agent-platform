from __future__ import annotations

import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

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

from app.api.auth import router
from app.core.deps import get_db


class _InMemoryDB:
    def __init__(self) -> None:
        self.users: list[object] = []
        self._pending_user: object | None = None

    def add(self, user: object) -> None:
        self._pending_user = user

    def commit(self) -> None:
        if self._pending_user is None:
            return
        pending_username = getattr(self._pending_user, "username", None)
        pending_email = getattr(self._pending_user, "email", None)
        duplicated = any(
            getattr(existing, "username", None) == pending_username
            or getattr(existing, "email", None) == pending_email
            for existing in self.users
        )
        if duplicated:
            raise IntegrityError("", {}, Exception("duplicate"))
        self.users.append(self._pending_user)

    def rollback(self) -> None:
        self._pending_user = None

    def refresh(self, user: object) -> None:
        if not getattr(user, "id", None):
            setattr(user, "id", "u-test-id")



def _build_client(db: _InMemoryDB) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_register_success_returns_user_with_default_role_and_status():
    db = _InMemoryDB()
    client = _build_client(db)

    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": "new_user",
            "email": "new_user@example.com",
            "password": "abc12345",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert payload["data"]["username"] == "new_user"
    assert payload["data"]["email"] == "new_user@example.com"
    assert payload["data"]["role"] == "user"
    assert payload["data"]["status"] == "active"


def test_register_duplicate_username_or_email_returns_409():
    db = _InMemoryDB()
    client = _build_client(db)

    first = {
        "username": "dup_user",
        "email": "dup_user@example.com",
        "password": "abc12345",
    }
    second = {
        "username": "dup_user",
        "email": "other@example.com",
        "password": "abc12345",
    }

    resp1 = client.post("/api/v1/auth/register", json=first)
    assert resp1.status_code == 200

    resp2 = client.post("/api/v1/auth/register", json=second)
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "用户名或邮箱已存在"
