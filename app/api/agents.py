from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import success_response
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate
from app.schemas.common import APIResponse, Pagination
from app.schemas.user import UserOut
from app.services.agents import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=APIResponse)
def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, min_length=1, max_length=64),
    is_public: bool | None = None,
    mine: bool | None = Query(None, description="仅查询当前用户创建的智能体"),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = AgentService(db)
    user_id = current_user.id if mine else None
    agents, total = service.list_agents(page, page_size, keyword, is_public, user_id)
    data = Pagination(
        list=[AgentOut.model_validate(agent) for agent in agents],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump())


@router.post("", response_model=APIResponse)
def create_agent(
    payload: AgentCreate,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = AgentService(db)
    agent = service.create_agent(payload, owner_id=current_user.id)
    return success_response(AgentOut.model_validate(agent).model_dump())


@router.get("/{agent_id}", response_model=APIResponse)
def get_agent(
    agent_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = AgentService(db)
    agent = service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    return success_response(AgentOut.model_validate(agent).model_dump())


@router.put("/{agent_id}", response_model=APIResponse)
def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    service = AgentService(db)
    agent = service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    if current_user.role != "admin" and agent.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")
    try:
        agent = service.update_agent(agent_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return success_response(AgentOut.model_validate(agent).model_dump())
