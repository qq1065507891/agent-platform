from __future__ import annotations

import importlib
import io
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.deps import require_admin
from app.main import app


class _DummyAsyncResult:
    def __init__(self, task_id: str = "task-123") -> None:
        self.id = task_id


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_admin] = lambda: {"id": "admin-test", "role": "admin"}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def mocked_delay(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_delay(*args: Any, **kwargs: Any) -> _DummyAsyncResult:
        calls.append({"args": args, "kwargs": kwargs})
        return _DummyAsyncResult()

    try:
        skills_api = importlib.import_module("app.api.skills")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected app.api.skills to be importable, but import failed: {exc}")

    task_obj = getattr(skills_api, "load_external_skill_task", None)
    if task_obj is None:
        pytest.fail("Expected app.api.skills.load_external_skill_task to exist for upload tests")

    monkeypatch.setattr(task_obj, "delay", fake_delay, raising=False)
    return calls


@pytest.fixture
def skill_archive_bytes() -> bytes:
    return build_skill_archive_bytes(name="Demo Skill", description="Skill used in upload tests")


@pytest.fixture
def invalid_archive_bytes() -> bytes:
    return b"this is not a zip archive"



def build_skill_archive_bytes(*, name: str | None, description: str | None, newline: str = "\n") -> bytes:
    frontmatter_lines = ["---"]
    if name is not None:
        frontmatter_lines.append(f'name: "{name}"')
    if description is not None:
        frontmatter_lines.append(f'description: "{description}"')
    frontmatter_lines.append('version: "0.1.0"')
    frontmatter_lines.append("---")
    frontmatter_lines.append("")
    frontmatter_lines.append("# Example skill")
    skill_md = newline.join(frontmatter_lines)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_md)
        zf.writestr("handler.py", "def run():\n    return 'ok'\n")
    return buf.getvalue()



def build_archive_without_skill_md() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("handler.py", "def run():\n    return 'ok'\n")
    return buf.getvalue()



def upload_skill(client: TestClient, *, filename: str, content: bytes):
    return client.post(
        "/api/v1/skills/upload",
        files={"file": (filename, content, "application/octet-stream")},
    )



def assert_success_async_payload(payload: dict[str, Any]) -> None:
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert isinstance(payload["data"], dict)
    assert payload["data"]["task_id"] == "task-123"
    assert payload["data"]["status"] in {"queued", "pending"}



def import_skill_tasks_module():
    try:
        return importlib.import_module("app.tasks.skill_tasks")
    except ModuleNotFoundError as exc:
        pytest.fail(
            "Expected app.tasks.skill_tasks to exist for local archive loading parity tests, "
            f"but import failed: {exc}"
        )



def test_upload_valid_zip_skill_archive_returns_async_success_payload(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
    skill_archive_bytes: bytes,
) -> None:
    response = upload_skill(client, filename="demo.zip", content=skill_archive_bytes)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert_success_async_payload(payload)
    assert len(mocked_delay) == 1



def test_upload_valid_skill_extension_archive_also_returns_async_success_payload(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
    skill_archive_bytes: bytes,
) -> None:
    response = upload_skill(client, filename="demo.skill", content=skill_archive_bytes)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert_success_async_payload(payload)
    assert len(mocked_delay) == 1



def test_upload_valid_skill_archive_with_crlf_frontmatter_returns_async_success_payload(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
) -> None:
    archive = build_skill_archive_bytes(
        name="CRLF Skill",
        description="Windows line endings should be accepted",
        newline="\r\n",
    )

    response = upload_skill(client, filename="crlf.skill", content=archive)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert_success_async_payload(payload)
    assert len(mocked_delay) == 1



def test_upload_fake_non_archive_skill_returns_422_with_clear_message(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
    invalid_archive_bytes: bytes,
) -> None:
    response = upload_skill(client, filename="broken.skill", content=invalid_archive_bytes)

    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["code"] in {4001, 422}
    joined = " ".join(
        str(part)
        for part in [
            payload.get("message", ""),
            payload.get("detail", {}).get("reason", ""),
            payload.get("detail", {}).get("field", ""),
        ]
    ).lower()
    assert any(keyword in joined for keyword in ["archive", "zip", "压缩", "归档", "无效"])
    assert not mocked_delay



def test_upload_archive_missing_skill_md_returns_422(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
) -> None:
    response = upload_skill(client, filename="missing-skill-md.zip", content=build_archive_without_skill_md())

    assert response.status_code == 422, response.text
    payload = response.json()
    joined = " ".join(
        str(part)
        for part in [payload.get("message", ""), payload.get("detail", {}).get("reason", "")]
    )
    assert "SKILL.md" in joined
    assert not mocked_delay



def test_upload_archive_with_skill_md_missing_name_returns_422(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
) -> None:
    archive = build_skill_archive_bytes(name=None, description="missing name")
    response = upload_skill(client, filename="missing-name.skill", content=archive)

    assert response.status_code == 422, response.text
    payload = response.json()
    joined = " ".join(
        str(part)
        for part in [payload.get("message", ""), payload.get("detail", {}).get("reason", "")]
    ).lower()
    assert "name" in joined or "frontmatter" in joined
    assert not mocked_delay



def test_upload_archive_with_skill_md_missing_description_returns_422(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
) -> None:
    archive = build_skill_archive_bytes(name="Demo Skill", description=None)
    response = upload_skill(client, filename="missing-description.skill", content=archive)

    assert response.status_code == 422, response.text
    payload = response.json()
    joined = " ".join(
        str(part)
        for part in [payload.get("message", ""), payload.get("detail", {}).get("reason", "")]
    ).lower()
    assert "description" in joined or "frontmatter" in joined
    assert not mocked_delay



def test_upload_real_bazi_zip_with_crlf_frontmatter_returns_async_success_payload(
    client: TestClient,
    mocked_delay: list[dict[str, Any]],
) -> None:
    archive_path = Path(r"D:/Downloads/openclaw-skills-bazi.zip")
    assert archive_path.exists(), f"Missing test fixture archive: {archive_path}"

    response = upload_skill(client, filename=archive_path.name, content=archive_path.read_bytes())

    assert response.status_code == 200, response.text
    payload = response.json()
    assert_success_async_payload(payload)
    assert len(mocked_delay) == 1



def test_download_code_treats_skill_and_zip_paths_the_same(skill_archive_bytes: bytes) -> None:
    skill_tasks = import_skill_tasks_module()
    download_code = getattr(skill_tasks, "_download_code", None)
    if download_code is None:
        pytest.fail("Expected app.tasks.skill_tasks._download_code to exist")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        zip_path = tmp_path / "demo.zip"
        skill_path = tmp_path / "demo.skill"
        zip_path.write_bytes(skill_archive_bytes)
        skill_path.write_bytes(skill_archive_bytes)

        zip_output = download_code("local", "upload://demo.zip", str(zip_path))
        skill_output = download_code("local", "upload://demo.skill", str(skill_path))

        assert zip_output == skill_output
        assert "def run" in zip_output
