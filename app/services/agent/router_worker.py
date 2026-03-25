from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import json
import logging
import time

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.database import SessionLocal
from app.observability.context import get_agent_id, get_conversation_id, get_trace_id, get_user_id
from app.observability.service import ObservabilityService
from app.services.rag_service import get_rag_service
from app.services.streaming import (
    StreamAssembler,
    extract_text_content,
    iter_public_stream_events,
    iter_unified_events_from_llm_stream,
)


logger = logging.getLogger(__name__)


def _log_worker_event(event_type: str, metadata: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        ObservabilityService(db).log_event(
            event_type=event_type,
            metadata=metadata,
            trace_id=get_trace_id(),
            user_id=get_user_id(),
            agent_id=get_agent_id(),
            conversation_id=get_conversation_id(),
        )
    except Exception as exc:
        logger.warning("failed to persist router worker event: %s", exc)
        db.rollback()
    finally:
        db.close()


def _extract_text_content(content: Any) -> str:
    # Keep local function for backward compatibility in this module.
    return extract_text_content(content)


def _load_llm(*, streaming: bool = True) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.llm_gateway_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        streaming=streaming,
    )


def _route_workers_by_rules(user_query: str) -> list[str]:
    text = (user_query or "").lower()
    workers: list[str] = ["memory"]

    rag_markers = {
        "知识库",
        "检索",
        "文档",
        "资料",
        "rag",
        "reference",
        "manual",
        "spec",
    }
    if any(marker in text for marker in rag_markers):
        workers.append("knowledge")

    if len(text) > 180 and "knowledge" not in workers:
        workers.append("knowledge")

    return workers


def _route_workers(user_query: str) -> list[str]:
    router_model = (settings.router_llm_model or "").strip()
    if not router_model:
        return _route_workers_by_rules(user_query)

    llm = ChatOpenAI(
        base_url=(settings.router_llm_base_url or settings.llm_gateway_url),
        api_key=(settings.router_llm_api_key or settings.llm_api_key),
        model=router_model,
        timeout=float(getattr(settings, "router_llm_timeout_seconds", 8.0)),
        streaming=False,
    )

    prompt = (
        "你是工具路由器。请根据用户问题只返回 JSON: {\"workers\":[...]}。"
        "workers 只能从 [\"memory\",\"knowledge\"] 中选择。"
        "默认至少包含 memory。"
    )
    try:
        response = llm.invoke(
            [
                SystemMessage(content=prompt),
                SystemMessage(content=f"user_query={user_query}"),
            ],
            response_format={"type": "json_object"},
        )
        text = _extract_text_content(response.content)
        parsed = json.loads(text) if text else {}
        workers = parsed.get("workers") if isinstance(parsed, dict) else None
        if isinstance(workers, list):
            output = [str(w).strip().lower() for w in workers if str(w).strip().lower() in {"memory", "knowledge"}]
            if "memory" not in output:
                output.insert(0, "memory")
            return output or ["memory"]
    except Exception:
        return _route_workers_by_rules(user_query)

    return _route_workers_by_rules(user_query)


def _memory_worker(context_bundle: dict[str, Any]) -> str:
    long_memories = context_bundle.get("long_memories") or []
    if not isinstance(long_memories, list) or not long_memories:
        return "(无长期记忆命中)"

    lines: list[str] = []
    for item in long_memories[:8]:
        if not isinstance(item, dict):
            continue
        memory_type = str(item.get("memory_type") or "memory")
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"- [{memory_type}] {content}")

    return "\n".join(lines) if lines else "(无长期记忆命中)"


def _knowledge_worker(agent_id: str | None, user_query: str) -> str:
    rag_service = get_rag_service()
    retriever = rag_service.as_retriever(agent_id=agent_id)
    docs = retriever.invoke(user_query)
    if not docs:
        return "(知识库未命中)"
    return rag_service.format_docs(docs)


def _run_workers(*, worker_names: list[str], agent_id: str | None, user_query: str, context_bundle: dict[str, Any]) -> dict[str, str]:
    outputs: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max(1, len(worker_names))) as executor:
        futures: dict[Any, tuple[str, float]] = {}
        for name in worker_names:
            started_at = time.perf_counter()
            if name == "memory":
                futures[executor.submit(_memory_worker, context_bundle)] = (name, started_at)
            elif name == "knowledge":
                futures[executor.submit(_knowledge_worker, agent_id, user_query)] = (name, started_at)

        for future in as_completed(futures):
            worker_name, started_at = futures[future]
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            try:
                value = str(future.result() or "")
                outputs[worker_name] = value
                _log_worker_event(
                    event_type="router_worker_trace",
                    metadata={
                        "worker_name": worker_name,
                        "worker_latency_ms": latency_ms,
                        "worker_success": True,
                        "error_type": None,
                        "fallback_reason": "knowledge_miss" if worker_name == "knowledge" and "未命中" in value else None,
                    },
                )
            except Exception as exc:
                outputs[worker_name] = f"(worker_error:{type(exc).__name__})"
                _log_worker_event(
                    event_type="router_worker_trace",
                    metadata={
                        "worker_name": worker_name,
                        "worker_latency_ms": latency_ms,
                        "worker_success": False,
                        "error_type": type(exc).__name__,
                        "fallback_reason": "worker_exception",
                    },
                )

    return outputs


def _build_router_context(*, worker_names: list[str], worker_outputs: dict[str, str], context_bundle: dict[str, Any]) -> SystemMessage:
    summary = str(context_bundle.get("summary") or "")
    short_context = str(context_bundle.get("short_context") or "")
    worker_block = "\n\n".join([f"[{name}]\n{worker_outputs.get(name, '')}" for name in worker_names])

    content = (
        "你是 Router-Worker 聚合器。请基于 workers 输出，给出准确、简洁、可执行的最终答复。"
        "当 worker 缺失信息时明确说明，不要编造。\n\n"
        f"已启用 workers: {', '.join(worker_names)}\n\n"
        f"【会话摘要】\n{summary or '(暂无)'}\n\n"
        f"【短期上下文】\n{short_context or '(暂无)'}\n\n"
        f"【Worker 输出】\n{worker_block or '(暂无)'}"
    )
    return SystemMessage(content=content)


def invoke_router_worker(
    *,
    agent_id: str | None,
    messages: list[AnyMessage],
    context_bundle: dict[str, Any],
    user_query: str,
) -> dict[str, Any]:
    total_start = time.perf_counter()
    worker_names = _route_workers(user_query)
    worker_outputs = _run_workers(
        worker_names=worker_names,
        agent_id=agent_id,
        user_query=user_query,
        context_bundle=context_bundle,
    )

    llm = _load_llm(streaming=False)
    router_context = _build_router_context(
        worker_names=worker_names,
        worker_outputs=worker_outputs,
        context_bundle=context_bundle,
    )
    response = llm.invoke([router_context, *messages])
    content = _extract_text_content(response.content)
    _log_worker_event(
        event_type="retrieval_trace",
        metadata={
            "source": "router_worker",
            "query_len": len(user_query or ""),
            "recall_k": int(getattr(settings, "rag_recall_k", 24)),
            "returned_k": 1 if content else 0,
            "latency_retrieve_ms": int((time.perf_counter() - total_start) * 1000),
            "fallback_reason": None if content else "empty_router_output",
            "workers": worker_names,
        },
    )
    final_ai = AIMessage(content=content or "")
    return {
        "messages": [*messages, final_ai],
        "retrieval_metrics": {
            "retrieval_latency_ms": int((time.perf_counter() - total_start) * 1000),
            "path": "router_worker",
            "fallback_reason": None if content else "empty_router_output",
        },
    }


def stream_router_worker(
    *,
    agent_id: str | None,
    messages: list[AnyMessage],
    context_bundle: dict[str, Any],
    user_query: str,
) -> Iterator[tuple[str, str, list[AnyMessage] | None]]:
    total_start = time.perf_counter()
    worker_names = _route_workers(user_query)
    worker_outputs = _run_workers(
        worker_names=worker_names,
        agent_id=agent_id,
        user_query=user_query,
        context_bundle=context_bundle,
    )

    llm = _load_llm()
    router_context = _build_router_context(
        worker_names=worker_names,
        worker_outputs=worker_outputs,
        context_bundle=context_bundle,
    )

    assembler = StreamAssembler()
    for chunk in llm.stream([router_context, *messages]):
        assembler.metrics.raw_event_count += 1
        for ue in iter_unified_events_from_llm_stream([chunk]):
            assembler.consume(ue)
            for public_event, payload in iter_public_stream_events(ue):
                yield (public_event, payload, None)

    assembled, metrics = assembler.finalize()
    retrieval_latency_ms = int((time.perf_counter() - total_start) * 1000)
    metrics["retrieval_latency_ms"] = retrieval_latency_ms
    metrics["path"] = "router_worker"
    _log_worker_event(
        event_type="retrieval_trace",
        metadata={
            "source": "router_worker_stream",
            "query_len": len(user_query or ""),
            "recall_k": int(getattr(settings, "rag_recall_k", 24)),
            "returned_k": 1 if assembled.strip() else 0,
            "latency_retrieve_ms": int((time.perf_counter() - total_start) * 1000),
            "fallback_reason": None if assembled.strip() else "empty_router_output",
            "workers": worker_names,
        },
    )

    if assembled.strip():
        final_state: list[AnyMessage] = [*messages, AIMessage(content=assembled)]
        yield ("final", assembled, {"messages": final_state, "stream_metrics": metrics})
    else:
        yield ("final", "", {"messages": None, "stream_metrics": metrics})
