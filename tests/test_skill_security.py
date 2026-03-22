from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base
from app.main import app
from app.core.database import engine


client = TestClient(app)


def _setup_db() -> None:
    Base.metadata.create_all(bind=engine)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_skill_load_rejects_unsupported_source_type() -> None:
    _setup_db()
    resp = client.post(
        "/api/v1/skills/load",
        json={
            "source_type": "npm",
            "source_url": "https://example.com/skill.py",
        },
    )
    assert resp.status_code in {401, 422}


def test_skill_ast_scan_blocks_import_os() -> None:
    from app.services.sandbox import scan_code_security

    code = """
import os

def run(params):
    return {"ok": True}
"""
    report = scan_code_security(code)
    assert report["passed"] is False
    assert any(item["rule"] == "forbidden_import" for item in report["violations"])


def test_skill_timeout_triggers() -> None:
    from app.services.sandbox import SandboxTimeoutError, execute_skill_code_safely

    code = """

def run(params):
    while True:
        pass
"""
    with pytest.raises(SandboxTimeoutError):
        execute_skill_code_safely(code, params={}, timeout_seconds=1)
