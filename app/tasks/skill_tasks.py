from __future__ import annotations

import hashlib
import tempfile
import zipfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.skill import ExternalSkillRevision, Skill
from app.services.sandbox import scan_code_security


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _normalize_github_url(source_url: str) -> str:
    # convert github blob URL to raw URL for source_type=github
    if "github.com" in source_url and "/blob/" in source_url:
        return source_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return source_url


def _extract_archive_and_pick_entry(archive_path: Path) -> tuple[Path, Path]:
    extract_root = Path(tempfile.mkdtemp(prefix="skill_pkg_"))
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            members = zf.infolist()
            if not members:
                raise ValueError("技能归档包为空")
            for member in members:
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("技能归档包包含非法路径")
            zf.extractall(extract_root)

        py_candidates = sorted([p for p in extract_root.rglob("*.py") if p.is_file()])
        if not py_candidates:
            raise ValueError("技能归档包中未找到可执行 .py 文件")

        preferred_names = ["main.py", "skill.py", "handler.py", "__init__.py"]
        for name in preferred_names:
            for candidate in py_candidates:
                if candidate.name == name:
                    return extract_root, candidate
        return extract_root, py_candidates[0]
    except Exception:
        shutil.rmtree(extract_root, ignore_errors=True)
        raise


def _download_code(source_type: str, source_url: str, package_path: str | None = None) -> str:
    if source_type == "local":
        if not package_path:
            raise ValueError("package_path is required for local source")
        file_path = Path(package_path)
        if not file_path.exists() or not file_path.is_file():
            raise ValueError("local package_path does not exist or is not a file")

        if file_path.suffix.lower() in {".zip", ".skill"}:
            extract_root, entry_file = _extract_archive_and_pick_entry(file_path)
            try:
                return entry_file.read_text(encoding="utf-8")
            finally:
                shutil.rmtree(extract_root, ignore_errors=True)

        return file_path.read_text(encoding="utf-8")

    if source_type == "github":
        source_url = _normalize_github_url(source_url)

    if source_type in {"http", "github"}:
        resp = requests.get(source_url, timeout=20)
        resp.raise_for_status()
        return resp.text

    raise ValueError(f"unsupported source_type: {source_type}")


@celery_app.task(name="app.tasks.load_external_skill_task", bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def load_external_skill_task(
    self,
    *,
    skill_id: str,
    source_type: str,
    source_url: str,
    source_version: str | None = None,
    expected_hash: str | None = None,
    package_path: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    db: Session = SessionLocal()
    try:
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            raise ValueError("Skill not found")

        code_content = _download_code(source_type, source_url, package_path)
        code_hash = _sha256(code_content)

        hash_verified = True
        if expected_hash:
            hash_verified = expected_hash.lower() == code_hash.lower()
            if not hash_verified:
                raise ValueError("checksum mismatch")

        scan_report = scan_code_security(code_content)
        scan_status = "passed" if scan_report["passed"] else "rejected"

        revision = ExternalSkillRevision(
            skill_id=skill.id,
            version=source_version,
            source_type=source_type,
            source_url=source_url,
            code_content=code_content,
            code_hash=code_hash,
            expected_hash=expected_hash,
            hash_verified=hash_verified,
            scan_status=scan_status,
            scan_report=scan_report,
            sandbox_policy={"timeout_seconds": 10},
            load_task_id=self.request.id,
            status="active" if scan_report["passed"] else "failed",
            error_message=None if scan_report["passed"] else "AST security scan rejected",
        )
        db.add(revision)
        db.flush()

        skill.source_type = source_type
        skill.source_url = source_url
        skill.source_version = source_version
        skill.checksum = code_hash
        skill.installed_at = datetime.now(timezone.utc)

        if scan_report["passed"]:
            skill.current_revision_id = revision.id
            skill.status = "active"
        else:
            skill.status = "disabled"

        db.commit()

        return {
            "task_id": self.request.id,
            "skill_id": skill.id,
            "revision_id": revision.id,
            "status": revision.status,
            "scan_status": scan_status,
            "hash_verified": hash_verified,
        }
    except Exception as exc:
        db.rollback()
        try:
            skill = db.query(Skill).filter(Skill.id == skill_id).first()
            if skill:
                skill.status = "disabled"
                db.commit()
        except Exception:
            db.rollback()

        # 把异常规范化，确保前端能看到明确原因而不是 Python 原始报错
        raise ValueError(f"技能加载失败：{exc}") from exc
    finally:
        if source_type == "local" and package_path:
            try:
                local_file = Path(package_path)
                if local_file.exists() and local_file.is_file():
                    local_file.unlink()
            except Exception:
                pass
        db.close()
