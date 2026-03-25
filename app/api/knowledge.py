from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.deps import get_current_user
from app.core.responses import success_response
from app.schemas.common import APIResponse
from app.schemas.user import UserOut
from app.services.rag_service import get_rag_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/upload", response_model=APIResponse)
async def upload_knowledge(
    file: UploadFile = File(...),
    agent_id: str | None = Form(default=None),
    current_user: UserOut = Depends(get_current_user),
) -> APIResponse:
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未上传文件")
    service = get_rag_service()
    try:
        result = await service.ingest_upload(file, agent_id=agent_id)
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
