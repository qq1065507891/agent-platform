from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, TypedDict
from dataclasses import asdict
from typing_extensions import Annotated
import json
import logging
import time

from langchain_core.messages import AnyMessage, AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.agent import Agent
from app.observability.context import get_agent_id, get_conversation_id, get_trace_id, get_user_id
from app.observability.service import ObservabilityService
from app.services.rag_service import get_rag_service
from app.services.sandbox import SandboxSecurityError, SandboxTimeoutError, execute_skill_code_safely
from app.services.skills.builtin import BUILTIN_TOOLS
from app.services.skills.service import SkillService
from app.services.streaming import (
    StreamAssembler,
    extract_text_content,
    iter_public_stream_events,
    iter_unified_events_from_graph_event,
    iter_unified_events_from_llm_stream,
)

EMPTY_ASSISTANT_REPLY = "已收到你的消息，但当前没有生成文本回复。"

logger = logging.getLogger(__name__)

REACT_LOOP_CONTINUE = "continue"
REACT_LOOP_DONE = "done"
REACT_LOOP_MAX_STEPS = "max_steps"

_GRAPH_CACHE: dict[tuple[str | None, str, str], tuple[float, Any]] = {}
_TOOLS_CACHE: dict[tuple[str | None, str], tuple[float, list[Any]]] = {}
_AGENT_SKILLS_FINGERPRINT_CACHE: dict[str, tuple[float, str]] = {}


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    context_bundle: dict[str, Any]
    user_query: str
    step_count: int


def _log_skill_invocation(skill_id: str, status: str, latency_ms: int, error_code: str | None) -> None:
    db = SessionLocal()
    try:
        ObservabilityService(db).log_skill_invocation(
            skill_id=skill_id,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
            trace_id=get_trace_id(),
            user_id=get_user_id(),
            agent_id=get_agent_id(),
            conversation_id=get_conversation_id(),
        )
    except Exception as exc:
        logger.warning("failed to persist skill invocation: %s", exc)
        db.rollback()
    finally:
        db.close()


def _log_llm_usage(response: AIMessage, latency_ms: int, agent_id: str | None) -> None:
    usage = getattr(response, "usage_metadata", None) or {}
    prompt_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))

    db = SessionLocal()
    try:
        ObservabilityService(db).log_llm_usage(
            model=getattr(response, "response_metadata", {}).get("model_name") or settings.llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=0,
            latency_ms=latency_ms,
            trace_id=get_trace_id(),
            user_id=get_user_id(),
            agent_id=get_agent_id() or agent_id,
            conversation_id=get_conversation_id(),
        )
    except Exception as exc:
        logger.warning("failed to persist llm usage: %s", exc)
        db.rollback()
    finally:
        db.close()


def _log_react_loop_event(event_type: str, metadata: dict[str, Any]) -> None:
    if not bool(getattr(settings, "agent_react_decision_log_enabled", True)):
        return

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
        logger.warning("failed to persist react loop event: %s", exc)
        db.rollback()
    finally:
        db.close()


def _load_llm(*, streaming: bool = True) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.llm_gateway_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        streaming=streaming,
    )


def _is_cache_valid(cached_at: float, ttl_seconds: int) -> bool:
    return (time.time() - cached_at) <= ttl_seconds


def _make_external_tool(skill_code: str, service: SkillService) -> Callable[..., str]:
    @tool(skill_code)
    def _external_tool(payload: str = "{}") -> str:
        """执行外部自定义技能（沙箱模式）。"""
        start = time.perf_counter()
        try:
            params = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            params = {"raw": payload}

        script = service.get_skill_execution_code(skill_code)
        if not script:
            _log_skill_invocation(skill_code, "failed", int((time.perf_counter() - start) * 1000), "skill_unavailable")
            return json.dumps(
                {
                    "ok": False,
                    "error": f"skill {skill_code} is unavailable or disabled",
                    "result": None,
                },
                ensure_ascii=False,
            )

        try:
            result = execute_skill_code_safely(
                code=script,
                params=params,
                timeout_seconds=settings.skill_sandbox_timeout_seconds,
            )
        except SandboxTimeoutError as exc:
            _log_skill_invocation(skill_code, "failed", int((time.perf_counter() - start) * 1000), "5004")
            return json.dumps(
                {
                    "ok": False,
                    "error": f"timeout: {exc}",
                    "error_code": 5004,
                    "result": None,
                },
                ensure_ascii=False,
            )
        except SandboxSecurityError as exc:
            _log_skill_invocation(skill_code, "failed", int((time.perf_counter() - start) * 1000), "5002")
            return json.dumps(
                {
                    "ok": False,
                    "error": f"security_reject: {exc}",
                    "error_code": 5002,
                    "result": None,
                },
                ensure_ascii=False,
            )

        _log_skill_invocation(skill_code, "success", int((time.perf_counter() - start) * 1000), None)
        return json.dumps(result, ensure_ascii=False)

    return _external_tool


def _get_agent_skills_fingerprint(agent_id: str | None) -> str:
    if not agent_id:
        return "no-agent"

    cached = _AGENT_SKILLS_FINGERPRINT_CACHE.get(agent_id)
    ttl_seconds = int(getattr(settings, "tools_cache_ttl_seconds", 120))
    if cached and _is_cache_valid(cached[0], ttl_seconds):
        return cached[1]

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        skills = agent.skills if agent and isinstance(agent.skills, list) else []
        normalized = json.dumps(skills, ensure_ascii=False, sort_keys=True, default=str)
        fingerprint = str(hash(normalized))
        _AGENT_SKILLS_FINGERPRINT_CACHE[agent_id] = (time.time(), fingerprint)
        return fingerprint
    finally:
        db.close()


def _build_external_skill_tools(agent_id: str | None) -> list[Any]:
    if not agent_id:
        return []

    fingerprint = _get_agent_skills_fingerprint(agent_id)
    cache_key = (agent_id, fingerprint)
    ttl_seconds = int(getattr(settings, "tools_cache_ttl_seconds", 120))
    cached = _TOOLS_CACHE.get(cache_key)
    if cached and _is_cache_valid(cached[0], ttl_seconds):
        return cached[1]

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent or not isinstance(agent.skills, list):
            return []

        service = SkillService(db)
        tools: list[Any] = []

        for skill_item in agent.skills:
            if not isinstance(skill_item, dict):
                continue
            code = skill_item.get("skill_id")
            if not code or code in BUILTIN_TOOLS:
                continue

            skill_code = str(code)
            tools.append(_make_external_tool(skill_code, service))

        _TOOLS_CACHE[cache_key] = (time.time(), tools)
        return tools
    finally:
        db.close()


def _extract_text_content(content: Any) -> str:
    """Best-effort text extraction for provider-specific chunk payloads."""
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, (int, float, bool)):
        return str(content)

    if isinstance(content, dict):
        # 常见结构：{"text": "..."} / {"content": "..."} / {"delta": "..."}
        for key in ("text", "content", "output_text", "delta", "value"):
            value = content.get(key)
            extracted = _extract_text_content(value)
            if extracted:
                return extracted

        # OpenAI-compatible content blocks：{"type": "text", "text": "..."}
        if content.get("type") == "text":
            text_value = content.get("text")
            extracted = _extract_text_content(text_value)
            if extracted:
                return extracted

        # 兜底递归扫描 dict values
        parts = [_extract_text_content(value) for value in content.values()]
        return "".join(part for part in parts if part)

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            extracted = _extract_text_content(item)
            if extracted:
                parts.append(extracted)
        return "".join(parts)

    return ""


def _build_memory_system_message(context_bundle: dict[str, Any] | None) -> SystemMessage | None:
    if not context_bundle:
        return None

    short_context = str(context_bundle.get("short_context") or "")
    summary = str(context_bundle.get("summary") or "")
    long_memories = context_bundle.get("long_memories") or []

    memory_lines: list[str] = []
    for item in long_memories:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        memory_type = str(item.get("memory_type") or "memory")
        memory_lines.append(f"- [{memory_type}] {content}")

    memory_block = "\n".join(memory_lines) if memory_lines else "- (暂无长期记忆命中)"
    prompt = (
        "以下为上下文工程注入内容，请仅在相关时使用，不得编造事实。\n"
        f"【会话摘要】\n{summary or '(暂无摘要)'}\n\n"
        f"【短期记忆（最近轮次）】\n{short_context or '(暂无短期记忆)'}\n\n"
        f"【长期记忆召回】\n{memory_block}"
    )
    return SystemMessage(content=prompt)


def _get_react_max_steps() -> int:
    return max(1, int(getattr(settings, "agent_react_max_steps", 6)))


def handle_max_steps_reached(state: AgentState) -> AIMessage:
    max_steps = _get_react_max_steps()
    step_count = int(state.get("step_count") or 0)
    messages = state.get("messages", [])
    assistant_text = extract_assistant_message(messages)

    _log_react_loop_event(
        event_type="react_max_steps_reached",
        metadata={
            "step_count": step_count,
            "max_steps": max_steps,
            "has_partial_answer": bool(assistant_text),
        },
    )

    if assistant_text:
        return AIMessage(content=assistant_text)
    return AIMessage(content="当前任务较复杂，已达到工具调用上限。请缩小问题范围后重试。")


def should_continue(state: AgentState) -> str:
    max_steps = _get_react_max_steps()
    step_count = int(state.get("step_count") or 0)
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    has_tool_calls = bool(isinstance(last_message, AIMessage) and last_message.tool_calls)

    if step_count >= max_steps:
        decision = REACT_LOOP_MAX_STEPS
    elif has_tool_calls:
        decision = REACT_LOOP_CONTINUE
    else:
        decision = REACT_LOOP_DONE

    _log_react_loop_event(
        event_type="react_loop_decision",
        metadata={
            "decision": decision,
            "step_count": step_count,
            "max_steps": max_steps,
            "has_tool_calls": has_tool_calls,
        },
    )

    return decision


def build_agent_graph(agent_id: str | None = None) -> Any:
    rag_service = get_rag_service()

    @tool
    def retriever_tool(query: str) -> str:
        """检索内部知识库，返回与问题最相关的片段。"""
        start = time.perf_counter()
        recall_k = int(getattr(settings, "rag_recall_k", 24))
        try:
            retriever = rag_service.as_retriever(agent_id=agent_id)
            docs = retriever.invoke(query)
            _log_react_loop_event(
                event_type="retrieval_trace",
                metadata={
                    "query_len": len(query or ""),
                    "recall_k": recall_k,
                    "returned_k": len(docs or []),
                    "latency_retrieve_ms": int((time.perf_counter() - start) * 1000),
                    "fallback_reason": None,
                    "source": "graph_retriever_tool",
                },
            )
            if not docs:
                return "知识库暂无匹配内容。"
            return rag_service.format_docs(docs)
        except Exception as exc:
            _log_react_loop_event(
                event_type="retrieval_trace",
                metadata={
                    "query_len": len(query or ""),
                    "recall_k": recall_k,
                    "returned_k": 0,
                    "latency_retrieve_ms": int((time.perf_counter() - start) * 1000),
                    "fallback_reason": f"{type(exc).__name__}",
                    "source": "graph_retriever_tool",
                },
            )
            return "知识库检索暂时不可用，请稍后重试。"

    dynamic_tools = _build_external_skill_tools(agent_id)
    tools = [*list(BUILTIN_TOOLS.values()), retriever_tool, *dynamic_tools]

    react_llm = _load_llm().bind_tools(tools)

    def memory_retrieve_node(state: AgentState) -> dict[str, Any]:
        # context_bundle currently prepared in ConversationService (v2 phase-1).
        return {
            "context_bundle": state.get("context_bundle") or {},
            "step_count": int(state.get("step_count") or 0),
        }

    def react_node(state: AgentState) -> Iterator[dict[str, Iterable[AnyMessage] | int]]:
        start = time.perf_counter()
        final_chunk: AIMessageChunk | None = None
        final_message: AIMessage | None = None

        messages = state.get("messages", [])
        planner_contract = SystemMessage(
            content=(
                "你是 ReAct 单模型代理。请严格遵循："
                "若无需调用工具，直接输出最终答复；"
                "仅在确实需要外部信息或动作时发起 tool_calls；"
                "不要输出空内容。"
            )
        )
        # memory system prompt 已在 ConversationService 统一注入，避免重复注入。
        react_input = [planner_contract, *messages]

        for chunk in react_llm.stream(react_input):
            if isinstance(chunk, AIMessageChunk):
                final_chunk = chunk if final_chunk is None else final_chunk + chunk
                yield {"messages": [chunk]}
                continue

            # 兼容部分供应商/SDK在 stream() 中回传 AIMessage（非 chunk）的情况
            if isinstance(chunk, AIMessage):
                final_message = chunk
                text = _extract_text_content(chunk.content)
                if text:
                    yield {"messages": [AIMessageChunk(content=text)]}

        latency_ms = int((time.perf_counter() - start) * 1000)

        if final_chunk is not None:
            response = AIMessage(
                content=final_chunk.content,
                additional_kwargs=getattr(final_chunk, "additional_kwargs", {}) or {},
                tool_calls=getattr(final_chunk, "tool_calls", None) or [],
                response_metadata=getattr(final_chunk, "response_metadata", {}) or {},
                usage_metadata=getattr(final_chunk, "usage_metadata", {}) or {},
            )
        elif final_message is not None:
            response = AIMessage(
                content=final_message.content,
                additional_kwargs=getattr(final_message, "additional_kwargs", {}) or {},
                tool_calls=getattr(final_message, "tool_calls", None) or [],
                response_metadata=getattr(final_message, "response_metadata", {}) or {},
                usage_metadata=getattr(final_message, "usage_metadata", {}) or {},
            )
        else:
            response = AIMessage(content="", tool_calls=[])

        _log_llm_usage(response, latency_ms, agent_id)
        yield {
            "messages": [response],
            "step_count": int(state.get("step_count") or 0) + 1,
        }

    def max_steps_node(state: AgentState) -> dict[str, list[AIMessage]]:
        return {"messages": [handle_max_steps_reached(state)]}

    graph = StateGraph(AgentState)
    graph.add_node("memory_retrieve", memory_retrieve_node)
    graph.add_node("react", react_node)
    graph.add_node("tool", ToolNode(tools))
    graph.add_node("max_steps", max_steps_node)

    graph.set_entry_point("memory_retrieve")
    graph.add_edge("memory_retrieve", "react")
    graph.add_conditional_edges(
        "react",
        should_continue,
        {
            REACT_LOOP_CONTINUE: "tool",
            REACT_LOOP_DONE: END,
            REACT_LOOP_MAX_STEPS: "max_steps",
        },
    )
    graph.add_edge("tool", "react")
    graph.add_edge("max_steps", END)

    return graph.compile()


def get_or_build_agent_graph(agent_id: str | None = None) -> Any:
    fingerprint = _get_agent_skills_fingerprint(agent_id)
    cache_key = (agent_id, fingerprint, settings.llm_model)
    ttl_seconds = int(getattr(settings, "graph_cache_ttl_seconds", 120))

    cached = _GRAPH_CACHE.get(cache_key)
    if cached and _is_cache_valid(cached[0], ttl_seconds):
        return cached[1]

    graph = build_agent_graph(agent_id=agent_id)
    _GRAPH_CACHE[cache_key] = (time.time(), graph)
    return graph


def invalidate_agent_graph_cache(agent_id: str | None) -> None:
    keys_to_delete = [key for key in _GRAPH_CACHE if key[0] == agent_id]
    for key in keys_to_delete:
        _GRAPH_CACHE.pop(key, None)

    tool_keys_to_delete = [key for key in _TOOLS_CACHE if key[0] == agent_id]
    for key in tool_keys_to_delete:
        _TOOLS_CACHE.pop(key, None)

    if agent_id:
        _AGENT_SKILLS_FINGERPRINT_CACHE.pop(agent_id, None)


def ensure_user_message(messages: list[AnyMessage], content: str) -> list[AnyMessage]:
    return [*messages, HumanMessage(content=content)]


def serialize_message(message: AnyMessage) -> dict[str, Any]:
    if isinstance(message, HumanMessage):
        return {
            "role": "user",
            "content": message.content,
        }

    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": getattr(message, "tool_call_id", None),
            "name": getattr(message, "name", None),
        }

    if isinstance(message, AIMessage):
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": message.content,
        }
        if getattr(message, "tool_calls", None):
            payload["tool_calls"] = message.tool_calls
        if getattr(message, "response_metadata", None):
            payload["response_metadata"] = message.response_metadata
        if getattr(message, "usage_metadata", None):
            payload["usage_metadata"] = message.usage_metadata
        return payload

    return {
        "role": "assistant",
        "content": getattr(message, "content", "") or "",
    }


def serialize_messages(messages: list[AnyMessage]) -> list[dict[str, Any]]:
    return [serialize_message(message) for message in messages]


def to_langchain_messages(items: list[dict]) -> list[AnyMessage]:
    result: list[AnyMessage] = []
    for item in items:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
            continue

        if role == "assistant":
            tool_calls = item.get("tool_calls") or []
            response_metadata = item.get("response_metadata") or {}
            usage_metadata = item.get("usage_metadata") or {}
            result.append(
                AIMessage(
                    content=content,
                    tool_calls=tool_calls,
                    response_metadata=response_metadata,
                    usage_metadata=usage_metadata,
                )
            )
            continue

        if role == "tool":
            tool_call_id = item.get("tool_call_id")
            if not tool_call_id:
                continue
            result.append(
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                    name=item.get("name"),
                )
            )
    return result


def extract_assistant_message(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = _extract_text_content(message.content)
            if text:
                return text
    return ""


def stream_assistant_message(
    graph: Any,
    input_state: dict[str, Any] | list[AnyMessage],
) -> Iterator[tuple[str, str, list[AnyMessage] | None]]:
    """通过统一协议适配 graph stream 并转发 SSE 事件。"""
    app_env = getattr(settings, "app_env", "development")
    debug_stream = str(app_env).lower() != "production"

    state_input: dict[str, Any]
    if isinstance(input_state, dict):
        state_input = input_state
    else:
        state_input = {"messages": input_state}

    if debug_stream:
        logger.info("[stream-debug] start stream(messages), history_len=%s", len(state_input.get("messages", [])))

    assembler = StreamAssembler()
    final_state_messages: list[AnyMessage] | None = None

    for raw_event in graph.stream(state_input, stream_mode=["messages", "values"]):
        assembler.metrics.raw_event_count += 1
        for ue in iter_unified_events_from_graph_event(raw_event):
            assembler.consume(ue)
            for public_event, payload in iter_public_stream_events(ue):
                yield (public_event, payload, None)

    assembled, metrics = assembler.finalize()

    if assembled and assembled.strip() and assembled.strip() != EMPTY_ASSISTANT_REPLY:
        if debug_stream:
            logger.info(
                "[stream-debug] end by graph stream, raw_event_count=%s unified_event_count=%s delta_text_count=%s first_delta_ms=%s total_ms=%s",
                metrics.raw_event_count,
                metrics.unified_event_count,
                metrics.delta_text_count,
                metrics.first_delta_ms,
                metrics.total_ms,
            )
        yield ("final", assembled, {"messages": final_state_messages, "stream_metrics": asdict(metrics)})
        return

    # graph 流为空时，按配置决定是否先走 graph.invoke 兜底（可关闭以降低长尾延迟），再退化为纯 LLM 兜底。
    non_stream_text = ""
    fallback_timeout_seconds = float(getattr(settings, "llm_fallback_timeout_seconds", 20.0))

    if bool(getattr(settings, "stream_graph_invoke_fallback_enabled", False)):
        graph_invoke_start = time.perf_counter()
        try:
            invoke_result = graph.invoke(state_input)
            invoke_messages = invoke_result.get("messages") if isinstance(invoke_result, dict) else None
            if isinstance(invoke_messages, list) and invoke_messages:
                non_stream_text = extract_assistant_message(invoke_messages)
                final_state_messages = invoke_messages
        except Exception as exc:
            if debug_stream:
                logger.warning("[stream-debug] graph invoke fallback failed: %s", exc)
        finally:
            if debug_stream:
                graph_invoke_ms = int((time.perf_counter() - graph_invoke_start) * 1000)
                logger.info("[stream-debug] graph invoke fallback latency_ms=%s", graph_invoke_ms)

    if (not non_stream_text or not non_stream_text.strip()):
        llm_fallback_start = time.perf_counter()
        try:
            fallback_messages = state_input.get("messages", [])
            if isinstance(fallback_messages, list) and fallback_messages:
                non_stream_text = _invoke_llm_non_stream(
                    fallback_messages,
                    timeout_seconds=fallback_timeout_seconds,
                )
        except Exception as exc:
            if debug_stream:
                logger.warning("[stream-debug] graph non-stream llm fallback failed: %s", exc)
        finally:
            if debug_stream:
                llm_fallback_ms = int((time.perf_counter() - llm_fallback_start) * 1000)
                logger.info(
                    "[stream-debug] graph non-stream llm fallback latency_ms=%s timeout_s=%s",
                    llm_fallback_ms,
                    fallback_timeout_seconds,
                )

    if non_stream_text and non_stream_text.strip() and non_stream_text.strip() != EMPTY_ASSISTANT_REPLY:
        if debug_stream:
            logger.info("[stream-debug] graph non-stream fallback succeeded, output_len=%s", len(non_stream_text))
        fallback_metrics = assembler.metrics
        fallback_metrics.fallback_triggered = True
        fallback_metrics.fallback_reason = "graph_stream_empty"
        yield ("final", non_stream_text, {"messages": final_state_messages, "stream_metrics": asdict(fallback_metrics)})
        return

    if debug_stream:
        logger.info("[stream-debug] graph stream has no usable text")
    yield ("final", EMPTY_ASSISTANT_REPLY, final_state_messages)


def _invoke_llm_non_stream(messages: list[AnyMessage], *, timeout_seconds: float | None = None) -> str:
    """Fallback for providers that stream empty chunks but return content in non-stream mode."""
    llm = ChatOpenAI(
        base_url=settings.llm_gateway_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=(timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds),
        streaming=False,
    )
    response = llm.invoke(messages)
    if isinstance(response, AIMessage):
        return _extract_text_content(response.content)
    return _extract_text_content(getattr(response, "content", ""))


def _safe_json(value: Any, max_len: int = 1200) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = repr(value)
    if len(text) > max_len:
        return text[:max_len] + "...<truncated>"
    return text


def stream_assistant_message_direct(messages: list[AnyMessage]) -> Iterator[tuple[str, str, list[AnyMessage] | None]]:
    app_env = getattr(settings, "app_env", "development")
    debug_stream = str(app_env).lower() != "production"

    llm = _load_llm()
    assembler = StreamAssembler()

    if debug_stream:
        logger.info("[stream-debug] start direct llm stream, history_len=%s", len(messages))

    for raw_item in llm.stream(messages):
        assembler.metrics.raw_event_count += 1
        for ue in iter_unified_events_from_llm_stream([raw_item]):
            assembler.consume(ue)
            for public_event, payload in iter_public_stream_events(ue):
                yield (public_event, payload, None)

    assembled, metrics = assembler.finalize()

    if assembled and assembled.strip() and assembled.strip() != EMPTY_ASSISTANT_REPLY:
        if debug_stream:
            logger.info(
                "[stream-debug] end by direct stream, raw_event_count=%s unified_event_count=%s delta_text_count=%s first_delta_ms=%s total_ms=%s",
                metrics.raw_event_count,
                metrics.unified_event_count,
                metrics.delta_text_count,
                metrics.first_delta_ms,
                metrics.total_ms,
            )
        yield ("final", assembled, {"messages": None, "stream_metrics": asdict(metrics)})
        return

    # 流式为空时尝试非流式兜底，避免供应商 chunk 兼容问题导致空回复。
    non_stream_text = ""
    fallback_timeout_seconds = float(getattr(settings, "llm_fallback_timeout_seconds", 20.0))
    llm_fallback_start = time.perf_counter()
    try:
        non_stream_text = _invoke_llm_non_stream(messages, timeout_seconds=fallback_timeout_seconds)
    except Exception as exc:
        if debug_stream:
            logger.warning("[stream-debug] non-stream fallback failed: %s", exc)
    finally:
        if debug_stream:
            llm_fallback_ms = int((time.perf_counter() - llm_fallback_start) * 1000)
            logger.info(
                "[stream-debug] direct non-stream fallback latency_ms=%s timeout_s=%s",
                llm_fallback_ms,
                fallback_timeout_seconds,
            )

    if non_stream_text and non_stream_text.strip():
        if debug_stream:
            logger.info("[stream-debug] direct non-stream fallback succeeded, output_len=%s", len(non_stream_text))
        yield ("final", non_stream_text, None)
        return

    if debug_stream:
        logger.info("[stream-debug] direct stream produced no usable text; return empty fallback")
    yield ("final", EMPTY_ASSISTANT_REPLY, None)
