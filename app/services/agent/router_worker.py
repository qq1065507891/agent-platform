from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import json

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.services.rag_service import get_rag_service


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return ""


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
        futures = {}
        for name in worker_names:
            if name == "memory":
                futures[executor.submit(_memory_worker, context_bundle)] = name
            elif name == "knowledge":
                futures[executor.submit(_knowledge_worker, agent_id, user_query)] = name

        for future in as_completed(futures):
            worker_name = futures[future]
            try:
                outputs[worker_name] = str(future.result() or "")
            except Exception as exc:
                outputs[worker_name] = f"(worker_error:{type(exc).__name__})"

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
    final_ai = AIMessage(content=content or "")
    return {"messages": [*messages, final_ai]}


def stream_router_worker(
    *,
    agent_id: str | None,
    messages: list[AnyMessage],
    context_bundle: dict[str, Any],
    user_query: str,
) -> Iterator[tuple[str, str, list[AnyMessage] | None]]:
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

    assembled = ""
    for chunk in llm.stream([router_context, *messages]):
        if isinstance(chunk, AIMessageChunk):
            text = _extract_text_content(chunk.content)
            if text:
                assembled += text
                yield ("delta", text, None)

    if assembled.strip():
        final_state: list[AnyMessage] = [*messages, AIMessage(content=assembled)]
        yield ("final", assembled, final_state)
    else:
        yield ("final", "", None)
