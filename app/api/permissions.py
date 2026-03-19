from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.core.responses import success_response
from app.schemas.common import APIResponse
from app.schemas.permission import PermissionGrant
from app.schemas.user import UserOut
from app.services.permissions import PermissionService

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.post("/grant", response_model=APIResponse)
def grant_permission(
    payload: PermissionGrant,
    current_user: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = PermissionService(db)
    grant = service.grant_permission(payload, actor_id=current_user.id)
    return success_response({"granted": True, "id": grant.id})
