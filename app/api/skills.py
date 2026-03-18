from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import success_response
from app.schemas.common import APIResponse, Pagination
from app.schemas.skill import SkillOut
from app.schemas.user import UserOut
from app.services.skills.registry import BuiltinSkillRegistry
from app.services.skills.service import SkillService

router = APIRouter(prefix="/skills", tags=["skills"])


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

    # Merge (dedupe by skill_id; DB has higher priority)
    db_skill_ids = {item.skill_id for item in db_items}
    merged: list[Any] = [SkillOut.model_validate(item) for item in db_items]

    for builtin in builtin_items:
        if builtin["skill_id"] in db_skill_ids:
            continue
        merged.append(SkillOut.model_validate(builtin))

    # Pagination semantics:
    # - For now, DB list is paged and built-ins are appended on the first page only.
    #   This keeps compatibility with existing DB pagination while still exposing built-ins.
    if page != 1:
        merged = [SkillOut.model_validate(item) for item in db_items]

    total = db_total + len([b for b in builtin_items if b["skill_id"] not in db_skill_ids]) if page == 1 else db_total

    data = Pagination(
        list=[item.model_dump() for item in merged],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump())
