from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import success_response
from app.schemas.common import APIResponse
from app.schemas.conversation import ConversationCreate, ConversationOut, MessageCreate
from app.schemas.user import UserOut
from app.services.conversations import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=APIResponse)
def create_conversation(
    payload: ConversationCreate,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = ConversationService(db)
    try:
        conversation = service.create_conversation(payload, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return success_response(ConversationOut.model_validate(conversation).model_dump())


@router.get("/{conversation_id}", response_model=APIResponse)
def get_conversation(
    conversation_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")
    return success_response(ConversationOut.model_validate(conversation).model_dump())


@router.post("/{conversation_id}/messages", response_model=APIResponse)
def send_message(
    conversation_id: str,
    payload: MessageCreate,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")
    result = service.add_message(conversation, payload)
    return success_response(result)
