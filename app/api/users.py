from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.core.responses import success_response
from app.schemas.common import APIResponse, Pagination
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=APIResponse)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, min_length=1, max_length=64),
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = UserService(db)
    users, total = service.list_users(page, page_size, keyword)
    data = Pagination(
        list=[UserOut.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump())


@router.post("", response_model=APIResponse)
def create_user(
    payload: UserCreate,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = UserService(db)
    try:
        user = service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return success_response(UserOut.model_validate(user).model_dump())


@router.put("/{user_id}", response_model=APIResponse)
def update_user(
    user_id: str,
    payload: UserUpdate,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = UserService(db)
    try:
        user = service.update_user(user_id, payload)
    except ValueError as exc:
        if "已存在" in str(exc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return success_response(UserOut.model_validate(user).model_dump())


@router.post("/import", response_model=APIResponse)
def import_users(
    payload: dict,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    users_payload = payload.get("users", [])
    service = UserService(db)
    success, failed = service.import_users([UserCreate.model_validate(item) for item in users_payload])
    return success_response({"success": success, "failed": failed})
