from __future__ import annotations

from typing import Any, Iterable, TypedDict
from typing_extensions import Annotated

from langchain_core.messages import AnyMessage, AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.services.skills.builtin import BUILTIN_TOOLS


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _load_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.llm_gateway_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )


def _should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool"
    return "end"


def build_agent_graph() -> Any:
    tools = list(BUILTIN_TOOLS.values())
    llm = _load_llm().bind_tools(tools)

    def llm_node(state: AgentState) -> dict[str, Iterable[AnyMessage]]:
        response = llm.invoke(state.get("messages", []))
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


def extract_assistant_message(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message.content if isinstance(message.content, str) else str(message.content)
    return ""
