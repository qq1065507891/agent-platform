from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk

from app.services.streaming.protocol import EventType, UnifiedEvent


def extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)

    if isinstance(content, dict):
        for key in ("text", "content", "output_text", "delta", "value", "reasoning_content", "reasoning"):
            if key in content:
                extracted = extract_text_content(content.get(key))
                if extracted:
                    return extracted

        if content.get("type") == "text":
            extracted = extract_text_content(content.get("text"))
            if extracted:
                return extracted

        parts = [extract_text_content(v) for v in content.values()]
        return "".join([p for p in parts if p])

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            extracted = extract_text_content(item)
            if extracted:
                parts.append(extracted)
        return "".join(parts)

    return ""


def iter_unified_events_from_message(message: Any, *, node_name: str | None = None) -> Iterator[UnifiedEvent]:
    if isinstance(message, AIMessageChunk):
        text = extract_text_content(getattr(message, "content", None))
        if text:
            yield UnifiedEvent(
                type=EventType.DELTA_TEXT,
                text=text,
                raw_node=node_name,
                raw_payload=message,
            )

        for tc in getattr(message, "tool_calls", None) or []:
            yield UnifiedEvent(
                type=EventType.DELTA_TOOL_CALL,
                tool_call_id=str(tc.get("id") or "") or None,
                tool_name=tc.get("name"),
                tool_arguments_delta=extract_text_content(tc.get("args") or tc.get("arguments") or ""),
                raw_node=node_name,
                raw_payload=tc,
            )
        return

    if isinstance(message, AIMessage):
        text = extract_text_content(getattr(message, "content", None))
        if text:
            yield UnifiedEvent(
                type=EventType.MESSAGE,
                text=text,
                raw_node=node_name,
                raw_payload=message,
            )

        for tc in getattr(message, "tool_calls", None) or []:
            yield UnifiedEvent(
                type=EventType.DELTA_TOOL_CALL,
                tool_call_id=str(tc.get("id") or "") or None,
                tool_name=tc.get("name"),
                tool_arguments_delta=extract_text_content(tc.get("args") or tc.get("arguments") or ""),
                raw_node=node_name,
                raw_payload=tc,
            )
        return

    generic_content = extract_text_content(getattr(message, "content", None))
    if generic_content:
        yield UnifiedEvent(
            type=EventType.DELTA_TEXT,
            text=generic_content,
            raw_node=node_name,
            raw_payload=message,
        )


def iter_unified_events_from_graph_event(event: Any) -> Iterator[UnifiedEvent]:
    mode: str | None = None
    item: Any = event

    if isinstance(event, tuple) and len(event) == 2 and isinstance(event[0], str):
        mode = event[0]
        item = event[1]

    # LangGraph updates dict path, e.g. AddableUpdatesDict
    if mode is None and isinstance(item, dict):
        for node_name, node_update in item.items():
            if not isinstance(node_update, dict):
                continue
            node_messages = node_update.get("messages")
            if isinstance(node_messages, list):
                for m in node_messages:
                    yield from iter_unified_events_from_message(m, node_name=str(node_name))
        return

    if mode in (None, "messages"):
        msg = item[0] if isinstance(item, tuple) else item
        yield from iter_unified_events_from_message(msg)
        return

    if mode == "values" and isinstance(item, dict):
        state_messages = item.get("messages")
        if isinstance(state_messages, list):
            for m in state_messages:
                # values 通道用于最终态快照，统一视为 message 候选
                if isinstance(m, AIMessage):
                    text = extract_text_content(getattr(m, "content", None))
                    if text:
                        yield UnifiedEvent(type=EventType.MESSAGE, text=text, raw_payload=m)
        return


def iter_unified_events_from_llm_stream(stream: Iterable[Any]) -> Iterator[UnifiedEvent]:
    for item in stream:
        yield from iter_unified_events_from_message(item)
