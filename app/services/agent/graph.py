from __future__ import annotations

from typing import Any, Iterable, Iterator, TypedDict
from typing_extensions import Annotated
import json
import logging
import time

from langchain_core.messages import AnyMessage, AIMessage, AIMessageChunk, HumanMessage, ToolMessage
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

EMPTY_ASSISTANT_REPLY = "已收到你的消息，但当前没有生成文本回复。"

logger = logging.getLogger(__name__)


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


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _load_llm() -> ChatOpenAI:
    # 开启底层流式，让 langgraph 能按 token/chunk 向上游抛出消息。
    return ChatOpenAI(
        base_url=settings.llm_gateway_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        streaming=True,
    )


def _should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool"
    return "end"


def _build_external_skill_tools(agent_id: str | None) -> list[Any]:
    if not agent_id:
        return []

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

            @tool(skill_code)
            def _external_tool(payload: str = "{}", _skill_code: str = skill_code) -> str:
                """执行外部自定义技能（沙箱模式）。"""
                start = time.perf_counter()
                try:
                    params = json.loads(payload) if payload else {}
                except json.JSONDecodeError:
                    params = {"raw": payload}

                script = service.get_skill_execution_code(_skill_code)
                if not script:
                    _log_skill_invocation(_skill_code, "failed", int((time.perf_counter() - start) * 1000), "skill_unavailable")
                    return json.dumps(
                        {
                            "ok": False,
                            "error": f"skill {_skill_code} is unavailable or disabled",
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
                    _log_skill_invocation(_skill_code, "failed", int((time.perf_counter() - start) * 1000), "5004")
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
                    _log_skill_invocation(_skill_code, "failed", int((time.perf_counter() - start) * 1000), "5002")
                    return json.dumps(
                        {
                            "ok": False,
                            "error": f"security_reject: {exc}",
                            "error_code": 5002,
                            "result": None,
                        },
                        ensure_ascii=False,
                    )

                _log_skill_invocation(_skill_code, "success", int((time.perf_counter() - start) * 1000), None)
                return json.dumps(result, ensure_ascii=False)

            tools.append(_external_tool)

        return tools
    finally:
        db.close()


def build_agent_graph(agent_id: str | None = None) -> Any:
    rag_service = get_rag_service()

    @tool
    def retriever_tool(query: str) -> str:
        """检索内部知识库，返回与问题最相关的片段。"""
        try:
            retriever = rag_service.as_retriever(agent_id=agent_id)
            docs = retriever.invoke(query)
            if not docs:
                return "知识库暂无匹配内容。"
            return rag_service.format_docs(docs)
        except Exception:
            return "知识库检索暂时不可用，请基于通用知识回答并提示用户稍后重试。"

    dynamic_tools = _build_external_skill_tools(agent_id)
    tools = [*list(BUILTIN_TOOLS.values()), retriever_tool, *dynamic_tools]
    llm = _load_llm().bind_tools(tools)

    def llm_node(state: AgentState) -> dict[str, Iterable[AnyMessage]]:
        start = time.perf_counter()
        response = llm.invoke(state.get("messages", []))
        latency_ms = int((time.perf_counter() - start) * 1000)

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

        return {"messages": [response]}

    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)
    graph.add_node("llm", llm_node)
    graph.add_node("tool", tool_node)
    graph.set_entry_point("llm")
    graph.add_conditional_edges("llm", _should_continue, {"tool": "tool", "end": END})
    graph.add_edge("tool", "llm")
    return graph.compile()


def ensure_user_message(messages: list[AnyMessage], content: str) -> list[AnyMessage]:
    return [*messages, HumanMessage(content=content)]


def to_langchain_messages(items: list[dict]) -> list[AnyMessage]:
    result: list[AnyMessage] = []
    has_pending_tool_call = False
    for item in items:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
            has_pending_tool_call = False
        elif role == "assistant":
            message = AIMessage(content=content)
            result.append(message)
            has_pending_tool_call = bool(message.tool_calls)
        elif role == "tool":
            tool_call_id = item.get("tool_call_id")
            if not tool_call_id or not has_pending_tool_call:
                continue
            result.append(ToolMessage(content=content, tool_call_id=tool_call_id))
            has_pending_tool_call = False
    return result


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


def extract_assistant_message(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = _extract_text_content(message.content)
            if text:
                return text
    return ""


def stream_assistant_message(
    graph: Any,
    messages: list[AnyMessage],
) -> Iterator[tuple[str, str, list[AnyMessage] | None]]:
    """通过 graph 的 messages 模式转发 token/chunk。"""
    app_env = getattr(settings, "app_env", "development")
    debug_stream = str(app_env).lower() != "production"
    assembled = ""
    chunk_count = 0

    if debug_stream:
        logger.info("[stream-debug] start stream(messages), history_len=%s", len(messages))

    for item in graph.stream({"messages": messages}, stream_mode="messages"):
        msg = item[0] if isinstance(item, tuple) else item

        if isinstance(msg, AIMessageChunk):
            chunk_count += 1
            text = _extract_text_content(msg.content)
            if debug_stream:
                logger.info("[stream-debug] graph chunk #%s text=%r", chunk_count, text)
            if text:
                assembled += text
                yield ("delta", text, None)

    if assembled and assembled.strip() and assembled.strip() != EMPTY_ASSISTANT_REPLY:
        if debug_stream:
            logger.info("[stream-debug] end by graph stream, chunk_count=%s assembled_len=%s", chunk_count, len(assembled))
        yield ("final", assembled, None)
        return

    # graph 流没有产出 chunk 时，退回一次 invoke。
    result = graph.invoke({"messages": messages})
    final_state = result.get("messages", messages)
    final_text = extract_assistant_message(final_state)
    if debug_stream:
        logger.info("[stream-debug] graph fallback final_text=%r", final_text)

    if final_text and final_text.strip():
        yield ("final", final_text, final_state)
    else:
        yield ("final", EMPTY_ASSISTANT_REPLY, final_state)


def stream_assistant_message_direct(messages: list[AnyMessage]) -> Iterator[tuple[str, str, list[AnyMessage] | None]]:
    """直接使用底层 LLM stream，保证真正 token 级输出。"""
    app_env = getattr(settings, "app_env", "development")
    debug_stream = str(app_env).lower() != "production"

    llm = _load_llm()
    assembled = ""
    chunk_count = 0

    if debug_stream:
        logger.info("[stream-debug] start direct llm stream, history_len=%s", len(messages))

    for msg in llm.stream(messages):
        if isinstance(msg, AIMessageChunk):
            chunk_count += 1
            text = _extract_text_content(msg.content)
            if debug_stream:
                logger.info("[stream-debug] direct chunk #%s text=%r", chunk_count, text)
            if text:
                assembled += text
                yield ("delta", text, None)

    if assembled and assembled.strip() and assembled.strip() != EMPTY_ASSISTANT_REPLY:
        if debug_stream:
            logger.info("[stream-debug] end by direct stream, chunk_count=%s assembled_len=%s", chunk_count, len(assembled))
        yield ("final", assembled, None)
        return

    result = llm.invoke(messages)
    final_text = _extract_text_content(result.content)
    if debug_stream:
        logger.info("[stream-debug] direct fallback final_text=%r", final_text)

    if final_text and final_text.strip():
        yield ("final", final_text, None)
    else:
        yield ("final", EMPTY_ASSISTANT_REPLY, None)
