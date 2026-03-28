from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time


class EventType(str, Enum):
    DELTA_TEXT = "delta_text"
    DELTA_REASONING = "delta_reasoning"
    DELTA_TOOL_CALL = "delta_tool_call"
    MESSAGE = "message"
    META = "meta"
    DONE = "done"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class StreamEndState(str, Enum):
    INIT = "init"
    STARTED = "started"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED_EMPTY = "failed_empty"
    FAILED_ERROR = "failed_error"


@dataclass
class UnifiedEvent:
    type: EventType
    text: str = ""
    reasoning_text: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_arguments_delta: str = ""
    finish_reason: str | None = None
    raw_provider: str | None = None
    raw_node: str | None = None
    raw_payload: Any = None
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class StreamSessionMetrics:
    raw_event_count: int = 0
    unified_event_count: int = 0
    delta_text_count: int = 0
    delta_reasoning_count: int = 0
    delta_tool_call_count: int = 0
    first_event_ms: int | None = None
    first_delta_ms: int | None = None
    total_ms: int = 0
    fallback_triggered: bool = False
    fallback_reason: str | None = None
    end_state: StreamEndState = StreamEndState.INIT
