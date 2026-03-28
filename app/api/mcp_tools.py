from __future__ import annotations

import json
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db, require_admin
from app.core.responses import success_response
from app.models.skill import Skill
from app.schemas.common import APIResponse, Pagination
from app.schemas.mcp_tool import McpToolCreateRequest, McpToolTestResponse, McpToolUpdateRequest
from app.schemas.user import UserOut

router = APIRouter(prefix="/admin/mcp-tools", tags=["mcp-tools"])

_LAST_TEST_AT: dict[str, float] = {}


def _normalize_skill_code(name: str) -> str:
    return f"mcp_{name.strip().lower().replace(' ', '_').replace('-', '_')}"


def _validate_transport_payload(payload: McpToolCreateRequest | McpToolUpdateRequest, *, is_create: bool) -> None:
    transport = getattr(payload, "transport", None)
    endpoint_url = getattr(payload, "endpoint_url", None)
    command = getattr(payload, "command", None)

    resolved_transport = transport
    if resolved_transport is None and is_create:
        raise HTTPException(status_code=422, detail="transport 为必填")

    if resolved_transport in {"http", "sse"} and not endpoint_url:
        raise HTTPException(status_code=422, detail="http/sse 模式必须提供 endpoint_url")
    if resolved_transport == "stdio" and not command:
        raise HTTPException(status_code=422, detail="stdio 模式必须提供 command")


def _read_json_import_file(file: UploadFile) -> list[dict]:
    filename = (file.filename or "").lower()
    if not filename.endswith(".json"):
        raise HTTPException(status_code=422, detail="当前仅支持 .json 导入")

    try:
        content = file.file.read()
        payload = json.loads(content.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="JSON 文件解析失败") from exc

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise HTTPException(status_code=422, detail="导入文件必须为对象或对象数组")

    items = [item for item in payload if isinstance(item, dict)]
    if not items:
        raise HTTPException(status_code=422, detail="导入文件没有有效条目")
    return items


@router.post("", response_model=APIResponse)
def create_mcp_tool(
    payload: McpToolCreateRequest,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    _validate_transport_payload(payload, is_create=True)

    skill_code = _normalize_skill_code(payload.name)
    exists = db.query(Skill).filter(Skill.skill_id == skill_code).first()
    if exists:
        raise HTTPException(status_code=409, detail="同名 MCP 工具已存在")

    source_url = payload.endpoint_url or (f"stdio://{payload.command}" if payload.command else "mcp://manual")

    skill = Skill(
        skill_id=skill_code,
        name=payload.name,
        description=payload.description,
        version="1.0.0",
        category="custom",
        source_type="mcp",
        source_url=source_url,
        source_version="manual",
        status="active" if payload.enabled else "disabled",
        yaml_definition={"source_mode": "manual"},
        execution_config={
            "transport": payload.transport,
            "endpoint_url": payload.endpoint_url,
            "command": payload.command,
            "args": payload.args,
            "env": payload.env,
            "auth_config": payload.auth_config,
        },
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)

    return success_response(
        {
            "id": skill.id,
            "skill_id": skill.skill_id,
            "name": skill.name,
            "status": skill.status,
            "source_type": skill.source_type,
        }
    )


@router.post("/import", response_model=APIResponse)
def import_mcp_tools(
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    rows = _read_json_import_file(file)

    imported_count = 0
    failed_count = 0
    results: list[dict] = []

    for idx, row in enumerate(rows):
        try:
            payload = McpToolCreateRequest.model_validate(row)
            _validate_transport_payload(payload, is_create=True)
            skill_code = _normalize_skill_code(payload.name)
            existing = db.query(Skill).filter(Skill.skill_id == skill_code).first()

            if existing and not overwrite:
                raise ValueError("已存在同名工具（可开启 overwrite）")

            source_url = payload.endpoint_url or (
                f"stdio://{payload.command}" if payload.command else "mcp://import"
            )

            if existing:
                existing.name = payload.name
                existing.description = payload.description
                existing.version = "1.0.0"
                existing.category = "custom"
                existing.source_type = "mcp"
                existing.source_url = source_url
                existing.source_version = "import"
                existing.status = "active" if payload.enabled else "disabled"
                existing.yaml_definition = {"source_mode": "file"}
                existing.execution_config = {
                    "transport": payload.transport,
                    "endpoint_url": payload.endpoint_url,
                    "command": payload.command,
                    "args": payload.args,
                    "env": payload.env,
                    "auth_config": payload.auth_config,
                }
                skill_id = existing.skill_id
            else:
                skill = Skill(
                    skill_id=skill_code,
                    name=payload.name,
                    description=payload.description,
                    version="1.0.0",
                    category="custom",
                    source_type="mcp",
                    source_url=source_url,
                    source_version="import",
                    status="active" if payload.enabled else "disabled",
                    yaml_definition={"source_mode": "file"},
                    execution_config={
                        "transport": payload.transport,
                        "endpoint_url": payload.endpoint_url,
                        "command": payload.command,
                        "args": payload.args,
                        "env": payload.env,
                        "auth_config": payload.auth_config,
                    },
                )
                db.add(skill)
                skill_id = skill.skill_id

            imported_count += 1
            results.append({"index": idx, "name": payload.name, "ok": True, "skill_id": skill_id})
        except Exception as exc:
            failed_count += 1
            results.append({
                "index": idx,
                "name": row.get("name") if isinstance(row, dict) else None,
                "ok": False,
                "error": str(exc),
            })

    db.commit()

    return success_response(
        {
            "imported_count": imported_count,
            "failed_count": failed_count,
            "results": results,
        }
    )


@router.get("", response_model=APIResponse)
def list_mcp_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    keyword: str | None = None,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    query = db.query(Skill).filter(Skill.source_type == "mcp")
    if status_filter:
        query = query.filter(Skill.status == status_filter)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter((Skill.name.ilike(like)) | (Skill.skill_id.ilike(like)))

    total = query.count()
    items = (
        query.order_by(Skill.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    data = Pagination(
        list=[
            {
                "id": item.id,
                "skill_id": item.skill_id,
                "name": item.name,
                "description": item.description,
                "source_mode": (item.yaml_definition or {}).get("source_mode", "manual"),
                "transport": (item.execution_config or {}).get("transport"),
                "status": item.status,
                "enabled": item.status == "active",
                "last_check_at": None,
                "last_error": None,
                "created_at": item.created_at,
            }
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump())


@router.patch("/{tool_id}", response_model=APIResponse)
def update_mcp_tool(
    tool_id: str,
    payload: McpToolUpdateRequest,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    tool = db.query(Skill).filter(Skill.id == tool_id, Skill.source_type == "mcp").first()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP 工具不存在")

    if payload.name is not None:
        tool.name = payload.name
    if payload.description is not None:
        tool.description = payload.description

    cfg = dict(tool.execution_config or {})
    if payload.endpoint_url is not None:
        cfg["endpoint_url"] = payload.endpoint_url
    if payload.command is not None:
        cfg["command"] = payload.command
    if payload.args is not None:
        cfg["args"] = payload.args
    if payload.env is not None:
        cfg["env"] = payload.env
    if payload.auth_config is not None:
        cfg["auth_config"] = payload.auth_config
    tool.execution_config = cfg

    transport = cfg.get("transport")
    if transport in {"http", "sse"}:
        tool.source_url = cfg.get("endpoint_url")
    elif transport == "stdio":
        tool.source_url = f"stdio://{cfg.get('command') or ''}"

    if payload.enabled is not None:
        tool.status = "active" if payload.enabled else "disabled"

    db.commit()
    db.refresh(tool)

    return success_response(
        {
            "id": tool.id,
            "skill_id": tool.skill_id,
            "name": tool.name,
            "status": tool.status,
        }
    )


@router.delete("/{tool_id}", response_model=APIResponse)
def delete_mcp_tool(
    tool_id: str,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    tool = db.query(Skill).filter(Skill.id == tool_id, Skill.source_type == "mcp").first()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP 工具不存在")

    db.delete(tool)
    db.commit()
    return success_response({"id": tool_id, "deleted": True})


@router.post("/{tool_id}/test", response_model=APIResponse)
def test_mcp_tool(
    tool_id: str,
    _: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
) -> APIResponse:
    tool = db.query(Skill).filter(Skill.id == tool_id, Skill.source_type == "mcp").first()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP 工具不存在")

    now = time.time()
    last_ts = _LAST_TEST_AT.get(tool_id, 0.0)
    min_interval = max(int(settings.mcp_test_rate_limit_seconds), 0)
    if min_interval > 0 and now - last_ts < min_interval:
        wait_seconds = int(min_interval - (now - last_ts)) + 1
        raise HTTPException(status_code=429, detail=f"测试过于频繁，请 {wait_seconds}s 后再试")
    _LAST_TEST_AT[tool_id] = now

    started = time.perf_counter()
    config = tool.execution_config or {}
    transport = config.get("transport")
    ok = False
    message = ""

    if transport in {"http", "sse"}:
        endpoint = (config.get("endpoint_url") or "").strip()
        if not endpoint:
            message = "缺少 endpoint_url"
        else:
            try:
                req = Request(endpoint, method="HEAD")
                with urlopen(req, timeout=5) as resp:
                    status_code = getattr(resp, "status", 200)
                ok = 200 <= int(status_code) < 500
                message = f"网络可达，HTTP {status_code}"
            except HTTPError as exc:
                ok = True
                message = f"网络可达，HTTP {exc.code}"
            except URLError as exc:
                message = f"网络不可达：{exc.reason}"
            except Exception as exc:
                message = f"探活异常：{exc}"
    elif transport == "stdio":
        if not settings.mcp_stdio_test_enabled:
            message = "已禁用 stdio 实执行测试（可通过 MCP_STDIO_TEST_ENABLED 开启）"
        else:
            command = (config.get("command") or "").strip()
            args = config.get("args") or []
            if not command:
                message = "缺少 command"
            else:
                try:
                    cmd = [command, *[str(item) for item in args]]
                    proc = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=5,
                        text=True,
                        shell=False,
                    )
                    ok = proc.returncode == 0
                    if ok:
                        message = "命令执行成功"
                    else:
                        err = (proc.stderr or proc.stdout or "").strip()
                        message = f"命令执行失败，exit={proc.returncode}" + (f"：{err[:120]}" if err else "")
                except FileNotFoundError:
                    message = "命令不存在或不可执行"
                except subprocess.TimeoutExpired:
                    message = "命令执行超时（5s）"
                except Exception as exc:
                    message = f"执行异常：{exc}"
    else:
        message = "不支持的 transport"

    latency_ms = int((time.perf_counter() - started) * 1000)
    data = McpToolTestResponse(ok=ok, message=message, discovered_tools=0, latency_ms=latency_ms)
    return success_response(data.model_dump())
