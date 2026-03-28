from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import success_response
from app.schemas.auth import TokenResponse
from app.schemas.common import APIResponse
from app.schemas.user import UserLogin, UserOut, UserRegister
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=APIResponse)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> APIResponse:
    service = AuthService(db)
    try:
        user = service.register(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return success_response(UserOut.model_validate(user).model_dump())


@router.post("/login", response_model=APIResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> APIResponse:
    service = AuthService(db)
    try:
        token, expires_in, user = service.login(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    data = TokenResponse(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))
    return success_response(data.model_dump())


@router.post("/logout", response_model=APIResponse)
def logout(_: UserOut = Depends(get_current_user)) -> APIResponse:
    return success_response({})
