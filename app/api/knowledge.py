from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import success_response
from app.schemas.common import APIResponse, Pagination
from app.schemas.user import UserOut
from app.observability.service import ObservabilityService
from app.services.agents import AgentService
from app.services.rag_service import (
    RAGTextExtractionError,
    RAGUnsupportedFileTypeError,
    get_rag_service,
)
from app.core.celery_app import celery_app
from app.tasks.knowledge_tasks import knowledge_purge_deleted_docs_task

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _ensure_agent_permission(*, agent_id: str, current_user: UserOut, db: Session):
    service = AgentService(db)
    agent = service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    if current_user.role != "admin" and agent.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")
    return agent


@router.post("/upload", response_model=APIResponse)
async def upload_knowledge(
    file: UploadFile = File(...),
    agent_id: str | None = Form(default=None),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未上传文件")
    if not (agent_id or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="agent_id 不能为空")

    _ensure_agent_permission(agent_id=agent_id, current_user=current_user, db=db)

    service = get_rag_service()
    try:
        result = await service.ingest_upload(file, agent_id=agent_id)
    except RAGUnsupportedFileTypeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RAGTextExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return success_response(
        {
            "doc_id": result.doc_id,
            "version": result.version,
            "chunk_count": result.chunk_count,
            "ingest_status": result.ingest_status,
            "status": result.ingest_status,
        }
    )


@router.get("/documents", response_model=APIResponse)
def list_knowledge_documents(
    agent_id: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, min_length=1, max_length=100),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    _ensure_agent_permission(agent_id=agent_id, current_user=current_user, db=db)

    rag_service = get_rag_service()
    items = rag_service.list_agent_documents(agent_id=agent_id, keyword=keyword)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paged = items[start:end]

    data = Pagination(
        list=[
            {
                "doc_id": item.doc_id,
                "source": item.source,
                "version": item.version,
                "chunk_count": item.chunk_count,
                "status": item.status,
                "created_at": item.created_at,
            }
            for item in paged
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump())


@router.delete("/documents/{doc_id}", response_model=APIResponse)
def delete_knowledge_document(
    doc_id: str,
    agent_id: str = Query(..., min_length=1),
    delete_mode: str = Query("soft", pattern="^(soft|hard)$"),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    _ensure_agent_permission(agent_id=agent_id, current_user=current_user, db=db)

    rag_service = get_rag_service()
    normalized_mode = "hard" if delete_mode == "hard" else "soft"
    deleted_chunks = rag_service.delete_agent_document(agent_id=agent_id, doc_id=doc_id, delete_mode=normalized_mode)
    if deleted_chunks <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    ObservabilityService(db).log_event(
        event_type="knowledge_doc_deleted",
        user_id=current_user.id,
        agent_id=agent_id,
        metadata={
            "doc_id": doc_id,
            "deleted_chunks": deleted_chunks,
            "delete_mode": normalized_mode,
            "batch": False,
        },
    )

    return success_response(
        {"deleted": True, "doc_id": doc_id, "deleted_chunks": deleted_chunks, "delete_mode": normalized_mode}
    )


@router.post("/documents/purge-deleted", response_model=APIResponse)
def purge_deleted_knowledge_documents(
    payload: dict,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    agent_id = str(payload.get("agent_id") or "").strip() or None
    doc_ids = payload.get("doc_ids") if isinstance(payload.get("doc_ids"), list) else None

    if current_user.role != "admin":
        if not agent_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非管理员必须指定 agent_id")
        _ensure_agent_permission(agent_id=agent_id, current_user=current_user, db=db)
    elif agent_id:
        _ensure_agent_permission(agent_id=agent_id, current_user=current_user, db=db)

    task = knowledge_purge_deleted_docs_task.delay(
        agent_id=agent_id,
        doc_ids=[str(x) for x in (doc_ids or [])] or None,
        requested_by=current_user.id,
    )

    ObservabilityService(db).log_event(
        event_type="knowledge_purge_deleted_docs_requested",
        user_id=current_user.id,
        agent_id=agent_id,
        metadata={
            "task_id": task.id,
            "requested_doc_ids": [str(x) for x in (doc_ids or [])],
        },
    )

    return success_response({"task_id": task.id, "status": "queued"})


@router.get("/tasks/{task_id}", response_model=APIResponse)
def get_knowledge_task_status(
    task_id: str,
    current_user: UserOut = Depends(get_current_user),
) -> APIResponse:
    task = celery_app.AsyncResult(task_id)
    state = str(task.state or "PENDING")

    response: dict = {"task_id": task_id, "state": state}
    if state == "SUCCESS":
        response["result"] = task.result if isinstance(task.result, dict) else {}
    elif state == "FAILURE":
        response["error"] = str(task.result)

    return success_response(response)


@router.post("/documents/batch-delete", response_model=APIResponse)
def batch_delete_knowledge_documents(
    payload: dict,
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    agent_id = str(payload.get("agent_id") or "").strip()
    doc_ids = payload.get("doc_ids") if isinstance(payload.get("doc_ids"), list) else []
    delete_mode = "hard" if str(payload.get("delete_mode") or "soft").strip().lower() == "hard" else "soft"
    if not agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="agent_id 不能为空")
    if not doc_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="doc_ids 不能为空")

    _ensure_agent_permission(agent_id=agent_id, current_user=current_user, db=db)

    rag_service = get_rag_service()
    normalized_doc_ids = [str(x) for x in doc_ids]
    delete_map = rag_service.delete_agent_documents(
        agent_id=agent_id,
        doc_ids=normalized_doc_ids,
        delete_mode=delete_mode,
    )
    results = [
        {
            "doc_id": doc_id,
            "deleted": count > 0,
            "deleted_chunks": count,
        }
        for doc_id, count in delete_map.items()
    ]
    success_count = sum(1 for item in results if item["deleted"])

    ObservabilityService(db).log_event(
        event_type="knowledge_docs_batch_deleted",
        user_id=current_user.id,
        agent_id=agent_id,
        metadata={
            "doc_ids": normalized_doc_ids,
            "requested_count": len(normalized_doc_ids),
            "success_count": success_count,
            "failed_count": len(results) - success_count,
            "delete_mode": delete_mode,
            "batch": True,
            "results": results,
        },
    )

    return success_response({"results": results, "success_count": success_count, "total": len(results)})
