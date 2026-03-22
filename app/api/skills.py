from __future__ import annotations

from typing import Any
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.responses import success_response
from app.schemas.common import APIResponse, Pagination
from app.schemas.skill import SkillDisableRequest, SkillLoadRequest, SkillLoadResponse, SkillOut, SkillTaskStatusResponse
from app.schemas.user import UserOut
from app.services.skills.registry import BuiltinSkillRegistry
from app.services.skills.service import SkillService
from app.core.celery_app import celery_app
from app.tasks.skill_tasks import load_external_skill_task
from app.models.skill import Skill

router = APIRouter(prefix="/skills", tags=["skills"])


def _persist_upload_file(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "skill.zip").suffix or ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = upload.file.read()
        tmp.write(content)
        return tmp.name


def _extract_skill_frontmatter(content: str) -> dict[str, str]:
    # 仅解析最小 frontmatter：--- ... ---
    text = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md 缺少 YAML frontmatter")

    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        raise ValueError("SKILL.md frontmatter 格式不正确")

    yaml_block = text[4:end_idx]
    result: dict[str, str] = {}
    for raw_line in yaml_block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        value = v.strip().strip('"').strip("'")
        result[key] = value
    return result


def _validate_and_parse_skill_archive(package_path: str) -> dict[str, str]:
    path = Path(package_path)
    try:
        with zipfile.ZipFile(path, "r") as zf:
            members = zf.infolist()
            if not members:
                raise ValueError("技能归档包为空")

            # 方案B：兼容两种打包方式
            # 1) 单顶层目录/my-skill/SKILL.md
            # 2) 直接在压缩包根目录放 SKILL.md
            skill_member = None

            for member in members:
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("技能归档包包含非法路径")
                if not member_path.parts:
                    continue

                if member_path.name.lower() == "skill.md":
                    skill_member = member

            if not skill_member:
                raise ValueError("技能归档包必须包含 SKILL.md 文件")

            raw = zf.read(skill_member).decode("utf-8")
            fm = _extract_skill_frontmatter(raw)
            name = fm.get("name", "").strip()
            description = fm.get("description", "").strip()

            if not name:
                raise ValueError("SKILL.md frontmatter 缺少 name")
            if not description:
                raise ValueError("SKILL.md frontmatter 缺少 description")

            skill_path = Path(skill_member.filename)
            inferred_skill_id = skill_path.parts[0] if len(skill_path.parts) > 1 else name

            return {
                "skill_id": inferred_skill_id,
                "name": name,
                "description": description,
            }
    except zipfile.BadZipFile as exc:
        raise ValueError("无效的技能归档包") from exc


@router.post("/upload", response_model=APIResponse)
def upload_and_load_local_skill(
    file: UploadFile = File(...),
    source_version: str | None = Form(None),
    expected_hash: str | None = Form(None),
    skill_id: str | None = Form(None),
    name: str | None = Form(None),
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    filename = (file.filename or "").lower()
    if not (filename.endswith(".zip") or filename.endswith(".skill")):
        raise HTTPException(status_code=422, detail="仅支持 .skill 或 .zip 压缩包")

    package_path = _persist_upload_file(file)

    try:
        meta = _validate_and_parse_skill_archive(package_path)
    except ValueError as exc:
        try:
            Path(package_path).unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    service = SkillService(db)
    resolved_skill_code = (skill_id or meta["skill_id"] or Path(filename).stem or "external_skill").strip() or "external_skill"
    skill = service.upsert_external_skill_stub(
        source_type="local",
        source_url=f"upload://{file.filename or 'skill.zip'}",
        source_version=source_version,
        skill_code=resolved_skill_code,
        name=name or meta["name"],
    )
    skill.description = meta["description"]
    db.commit()
    db.refresh(skill)

    task = load_external_skill_task.delay(
        skill_id=skill.id,
        source_type="local",
        source_url=f"upload://{file.filename or 'skill.zip'}",
        source_version=source_version,
        expected_hash=expected_hash,
        package_path=package_path,
    )

    data = SkillLoadResponse(task_id=task.id, skill_id=skill.id, status="pending")
    return success_response(data.model_dump())


@router.post("/load", response_model=APIResponse)
def load_external_skill(
    payload: SkillLoadRequest,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    if payload.source_type in {"github", "http"} and not payload.source_url:
        raise HTTPException(status_code=422, detail="source_url 为必填")
    if payload.source_type == "local" and not payload.package_path:
        raise HTTPException(status_code=422, detail="package_path 为必填")
    if payload.source_type in {"npm", "private_registry"}:
        raise HTTPException(status_code=422, detail="当前版本暂不支持 npm/private_registry，请使用 http/github/local")

    service = SkillService(db)
    skill = service.upsert_external_skill_stub(
        source_type=payload.source_type,
        source_url=payload.source_url,
        source_version=payload.source_version,
        skill_code=payload.skill_id,
        name=payload.name,
    )

    source_url = payload.source_url or "local://package_path"

    task = load_external_skill_task.delay(
        skill_id=skill.id,
        source_type=payload.source_type,
        source_url=source_url,
        source_version=payload.source_version,
        expected_hash=payload.expected_hash,
        package_path=payload.package_path,
    )

    data = SkillLoadResponse(task_id=task.id, skill_id=skill.id, status="pending")
    return success_response(data.model_dump())


@router.get("/tasks/{task_id}", response_model=APIResponse)
def get_skill_load_task_status(
    task_id: str,
    _: UserOut = Depends(require_admin),
) -> APIResponse:
    async_result = celery_app.AsyncResult(task_id)

    result_payload: dict | None = None
    error_message: str | None = None

    if async_result.successful():
        if isinstance(async_result.result, dict):
            result_payload = async_result.result
        else:
            result_payload = {"result": async_result.result}
    elif async_result.failed():
        error_message = str(async_result.result)

    data = SkillTaskStatusResponse(
        task_id=task_id,
        status=async_result.status,
        result=result_payload,
        error=error_message,
    )
    return success_response(data.model_dump())


@router.post("/{skill_id}/disable", response_model=APIResponse)
def disable_skill(
    skill_id: str,
    payload: SkillDisableRequest,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = SkillService(db)
    try:
        skill = service.disable_skill(skill_id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return success_response({"id": skill.id, "status": skill.status})


@router.post("/{skill_id}/enable", response_model=APIResponse)
def enable_skill(
    skill_id: str,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = SkillService(db)
    try:
        skill = service.enable_skill(skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return success_response({"id": skill.id, "status": skill.status})


@router.delete("/{skill_id}", response_model=APIResponse)
def delete_skill(
    skill_id: str,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = SkillService(db)
    try:
        service.delete_skill(skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return success_response({"id": skill_id, "deleted": True})


@router.get("", response_model=APIResponse)
def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    """技能列表（包含内置 + DB 注册）。

    返回结构遵循文档 5.4：分页结构 data: {list,total,page,page_size}
    """

    # DB skills
    service = SkillService(db)
    db_items, db_total = service.list_skills(page, page_size, category, source_type, status)

    # Built-in skills (Phase 3 tools)
    builtin_items = BuiltinSkillRegistry().list_skills(category=category, source_type=source_type, status=status)

    # DB 中可能存在对 built-in 的覆盖记录（例如禁用），需要用 skill_id 去重并覆盖 builtin 展示状态
    db_skill_rows = db.query(Skill.skill_id, Skill.status).all()
    db_status_by_skill_id = {row[0]: row[1] for row in db_skill_rows}

    # Merge (dedupe by skill_id; DB has higher priority)
    db_skill_ids = {item.skill_id for item in db_items}
    merged: list[Any] = [SkillOut.model_validate(item) for item in db_items]

    for builtin in builtin_items:
        overridden_status = db_status_by_skill_id.get(builtin["skill_id"])
        if overridden_status:
            builtin = {**builtin, "status": overridden_status}

        # 若前端传了 status=active，则被禁用的 builtin 不应再出现
        if status and builtin["status"] != status:
            continue

        if builtin["skill_id"] in db_skill_ids:
            continue
        merged.append(SkillOut.model_validate(builtin))

    # Pagination semantics:
    # - For now, DB list is paged and built-ins are appended on the first page only.
    #   This keeps compatibility with existing DB pagination while still exposing built-ins.
    if page != 1:
        merged = [SkillOut.model_validate(item) for item in db_items]

    total = db_total + len([
        b for b in builtin_items
        if (not status or db_status_by_skill_id.get(b["skill_id"], b["status"]) == status)
        and b["skill_id"] not in db_skill_ids
    ]) if page == 1 else db_total

    data = Pagination(
        list=[item.model_dump() for item in merged],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump())
