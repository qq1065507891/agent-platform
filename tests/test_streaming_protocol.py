from __future__ import annotations

import pathlib
import sys

from langchain_core.messages import AIMessage, AIMessageChunk

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.streaming.adapters import iter_unified_events_from_graph_event, iter_unified_events_from_llm_stream
from app.services.streaming.assembler import StreamAssembler
from app.services.streaming.emitter import iter_public_stream_events
from app.services.streaming.protocol import EventType, StreamEndState, UnifiedEvent


def test_graph_addable_updates_dict_emits_delta_text():
    event = {
        "react": {
            "messages": [
                AIMessage(content="你好，欢迎使用导游助手")
            ]
        }
    }

    unified = list(iter_unified_events_from_graph_event(event))

    assert len(unified) >= 1
    assert any(e.type in {EventType.MESSAGE, EventType.DELTA_TEXT} for e in unified)
    assert any("导游助手" in (e.text or "") for e in unified)


def test_llm_chunk_stream_emits_delta_text():
    stream = [AIMessageChunk(content="第一段"), AIMessageChunk(content="第二段")]

    unified = list(iter_unified_events_from_llm_stream(stream))

    assert [e.type for e in unified] == [EventType.DELTA_TEXT, EventType.DELTA_TEXT]
    assert "".join([e.text for e in unified]) == "第一段第二段"


def test_tool_call_only_marks_stream_active_without_text():
    event = UnifiedEvent(
        type=EventType.DELTA_TOOL_CALL,
        tool_call_id="call_1",
        tool_name="retriever_tool",
        tool_arguments_delta='{"query":"曾怡霖是谁"}',
    )

    assembler = StreamAssembler()
    assembler.consume(event)
    assembled, metrics = assembler.finalize()

    assert assembled == ""
    assert metrics.delta_tool_call_count == 1
    assert metrics.end_state == StreamEndState.COMPLETED


def test_empty_stream_results_failed_empty_state():
    assembler = StreamAssembler()
    _, metrics = assembler.finalize()

    assert metrics.end_state == StreamEndState.FAILED_EMPTY


def test_emitter_meta_payload_is_json_for_tool_call():
    event = UnifiedEvent(
        type=EventType.DELTA_TOOL_CALL,
        tool_call_id="call_9",
        tool_name="calculator",
        tool_arguments_delta="1+1",
    )

    outputs = list(iter_public_stream_events(event))

    assert len(outputs) == 1
    name, payload = outputs[0]
    assert name == "meta"
    assert '"kind": "tool_call_delta"' in payload
    assert '"tool_name": "calculator"' in payload
