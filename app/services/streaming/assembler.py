from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.services.streaming.protocol import EventType, StreamEndState, StreamSessionMetrics, UnifiedEvent


@dataclass
class StreamAssembler:
    started_at: float = field(default_factory=time.perf_counter)
    metrics: StreamSessionMetrics = field(default_factory=StreamSessionMetrics)
    assembled_text: str = ""
    seen_effective_event: bool = False

    def consume(self, event: UnifiedEvent) -> None:
        self.metrics.unified_event_count += 1

        if self.metrics.first_event_ms is None:
            self.metrics.first_event_ms = int((time.perf_counter() - self.started_at) * 1000)
            self.metrics.end_state = StreamEndState.STARTED

        if event.type == EventType.DELTA_TEXT and event.text:
            self.metrics.delta_text_count += 1
            self.assembled_text += event.text
            self._mark_active()
            return

        if event.type == EventType.MESSAGE and event.text:
            if not self.assembled_text.strip():
                self.assembled_text = event.text
            self._mark_active()
            return

        if event.type == EventType.DELTA_REASONING and event.reasoning_text:
            self.metrics.delta_reasoning_count += 1
            self._mark_active()
            return

        if event.type == EventType.DELTA_TOOL_CALL:
            self.metrics.delta_tool_call_count += 1
            self._mark_active()
            return

        if event.type == EventType.ERROR:
            self.metrics.end_state = StreamEndState.FAILED_ERROR

    def _mark_active(self) -> None:
        self.seen_effective_event = True
        self.metrics.end_state = StreamEndState.ACTIVE
        if self.metrics.first_delta_ms is None:
            self.metrics.first_delta_ms = int((time.perf_counter() - self.started_at) * 1000)

    def finalize(self) -> tuple[str, StreamSessionMetrics]:
        self.metrics.total_ms = int((time.perf_counter() - self.started_at) * 1000)

        if self.metrics.end_state == StreamEndState.FAILED_ERROR:
            return self.assembled_text, self.metrics

        if self.seen_effective_event or (self.assembled_text and self.assembled_text.strip()):
            self.metrics.end_state = StreamEndState.COMPLETED
            return self.assembled_text, self.metrics

        self.metrics.end_state = StreamEndState.FAILED_EMPTY
        return self.assembled_text, self.metrics
