from __future__ import annotations

from collections.abc import Iterator
import json

from app.core.config import settings
from app.services.streaming.protocol import EventType, UnifiedEvent


def iter_public_stream_events(event: UnifiedEvent) -> Iterator[tuple[str, str]]:
    """Map unified events to public SSE events.

    Backward-compatible output:
    - delta
    - final

    Optional extended output:
    - meta
    """
    if event.type == EventType.DELTA_TEXT and event.text:
        yield ("delta", event.text)
        return

    if bool(getattr(settings, "stream_meta_event_enabled", True)):
        if event.type == EventType.DELTA_REASONING and event.reasoning_text:
            payload = {
                "kind": "reasoning_delta",
                "text": event.reasoning_text,
                "ts_ms": event.ts_ms,
            }
            yield ("meta", json.dumps(payload, ensure_ascii=False))
            return
        if event.type == EventType.DELTA_TOOL_CALL:
            payload = {
                "kind": "tool_call_delta",
                "tool_call_id": event.tool_call_id,
                "tool_name": event.tool_name,
                "arguments_delta": event.tool_arguments_delta,
                "ts_ms": event.ts_ms,
            }
            yield ("meta", json.dumps(payload, ensure_ascii=False))
            return
