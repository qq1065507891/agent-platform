from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import success_response
from app.schemas.common import APIResponse
from app.schemas.conversation import ConversationCreate, ConversationOut, ConversationRename, MessageCreate
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


@router.get("")
def list_conversations(
    agent_id: str | None = None,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = ConversationService(db)
    conversations = service.list_user_conversations(current_user.id, agent_id)
    data = [
        ConversationOut.model_validate(
            {
                **item.__dict__,
                "agent_name": item.agent.name if item.agent else None,
                "agent_description": item.agent.description if item.agent else None,
            }
        ).model_dump()
        for item in conversations
    ]
    return success_response(data)


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


@router.patch("/{conversation_id}", response_model=APIResponse)
def rename_conversation(
    conversation_id: str,
    payload: ConversationRename,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")
    try:
        conversation = service.rename_conversation(conversation_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success_response(ConversationOut.model_validate(conversation).model_dump())


@router.delete("/{conversation_id}", response_model=APIResponse)
def delete_conversation(
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
    try:
        service.delete_conversation(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success_response({"deleted": True, "conversation_id": conversation_id})


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


@router.post("/{conversation_id}/messages/stream")
def send_message_stream(
    conversation_id: str,
    payload: MessageCreate,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")

    return StreamingResponse(
        service.add_message_stream(conversation, payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
