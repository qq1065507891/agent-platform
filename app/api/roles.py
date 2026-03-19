from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.core.responses import success_response
from app.schemas.common import APIResponse
from app.schemas.role import RoleCreate, RoleOut, RoleUpdate
from app.schemas.user import UserOut
from app.services.roles import RoleService

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=APIResponse)
def list_roles(
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = RoleService(db)
    roles = service.list_roles()
    return success_response([RoleOut.model_validate(role).model_dump() for role in roles])


@router.post("", response_model=APIResponse)
def create_role(
    payload: RoleCreate,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = RoleService(db)
    try:
        role = service.create_role(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return success_response(RoleOut.model_validate(role).model_dump())


@router.put("/{role_id}", response_model=APIResponse)
def update_role(
    role_id: str,
    payload: RoleUpdate,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = RoleService(db)
    try:
        role = service.update_role(role_id, payload)
    except ValueError as exc:
        if "已存在" in str(exc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return success_response(RoleOut.model_validate(role).model_dump())
