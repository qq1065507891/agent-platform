from __future__ import annotations

from types import SimpleNamespace
import pathlib
import sys

from langchain_core.messages import AIMessage, HumanMessage

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.models.agent import Agent
from app.models.conversation import Conversation
from app.schemas.agent import AgentUpdate
from app.schemas.conversation import MessageCreate
from app.services import agents as agents_module
from app.services.agent import graph as graph_module
from app.services.conversations import ConversationService


class _DummyQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _DummySession:
    def __init__(self, conversation: Conversation | None = None, agent: Agent | None = None):
        self._conversation = conversation
        self._agent = agent
        self.commit_count = 0

    def query(self, model):
        if model is Conversation:
            return _DummyQuery(self._conversation)
        if model is Agent:
            return _DummyQuery(self._agent)
        return _DummyQuery(None)

    def commit(self):
        self.commit_count += 1

    def refresh(self, _obj):
        return None


def test_add_message_stream_persists_structured_final_state(monkeypatch):
    conversation = SimpleNamespace(
        id="conv-1",
        agent_id="agent-1",
        user_id="user-1",
        messages=[{"role": "user", "content": "历史消息"}],
    )
    db_conversation = SimpleNamespace(
        id="conv-1",
        agent_id="agent-1",
        user_id="user-1",
        messages=list(conversation.messages),
    )
    db = _DummySession(conversation=db_conversation)
    service = ConversationService(db)
    service.observability = SimpleNamespace(log_event=lambda **kwargs: None)
    memory_stub = SimpleNamespace(
        compose_context_bundle=lambda **kwargs: {"budget": {}},
        extract_write_candidates=lambda *_args, **_kwargs: [],
        write_long_term_memories=lambda **_kwargs: [],
    )
    monkeypatch.setattr("app.services.conversations.get_memory_service", lambda: memory_stub)

    final_state = [
        HumanMessage(content="你好"),
        AIMessage(
            content="工具调用完成",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "demo_tool",
                    "args": {"x": 1},
                    "type": "tool_call",
                }
            ],
            response_metadata={"model_name": "demo-model"},
            usage_metadata={"total_tokens": 12},
        ),
    ]

    def _fake_stream_assistant_message(_graph, _messages):
        yield ("delta", "工具", None)
        yield ("final", "工具调用完成", final_state)

    monkeypatch.setattr("app.services.conversations.get_or_build_agent_graph", lambda agent_id=None: object())
    monkeypatch.setattr("app.services.conversations.stream_assistant_message", _fake_stream_assistant_message)
    monkeypatch.setattr("app.services.conversations.stream_assistant_message_direct", lambda _messages: iter(()))

    payload = MessageCreate(content="帮我调用工具")
    events = list(service.add_message_stream(conversation, payload))

    assert events[-1].startswith("data: ")
    assert db.commit_count == 1
    assert db_conversation.messages[-1]["role"] == "assistant"
    assert db_conversation.messages[-1]["content"] == "工具调用完成"
    assert db_conversation.messages[-1]["tool_calls"][0]["name"] == "demo_tool"


def test_invalidate_agent_graph_cache_clears_only_target_agent():
    graph_module._GRAPH_CACHE.clear()
    graph_module._TOOLS_CACHE.clear()
    graph_module._AGENT_SKILLS_FINGERPRINT_CACHE.clear()

    graph_module._GRAPH_CACHE[("agent-a", "fp1", "m1")] = (0.0, object())
    graph_module._GRAPH_CACHE[("agent-b", "fp2", "m1")] = (0.0, object())
    graph_module._TOOLS_CACHE[("agent-a", "fp1")] = (0.0, [])
    graph_module._TOOLS_CACHE[("agent-b", "fp2")] = (0.0, [])
    graph_module._AGENT_SKILLS_FINGERPRINT_CACHE["agent-a"] = (0.0, "fp1")
    graph_module._AGENT_SKILLS_FINGERPRINT_CACHE["agent-b"] = (0.0, "fp2")

    graph_module.invalidate_agent_graph_cache("agent-a")

    assert ("agent-a", "fp1", "m1") not in graph_module._GRAPH_CACHE
    assert ("agent-a", "fp1") not in graph_module._TOOLS_CACHE
    assert "agent-a" not in graph_module._AGENT_SKILLS_FINGERPRINT_CACHE

    assert ("agent-b", "fp2", "m1") in graph_module._GRAPH_CACHE
    assert ("agent-b", "fp2") in graph_module._TOOLS_CACHE
    assert "agent-b" in graph_module._AGENT_SKILLS_FINGERPRINT_CACHE


def test_update_agent_triggers_cache_invalidation(monkeypatch):
    agent = SimpleNamespace(id="agent-1", name="old", skills=[{"skill_id": "s1"}])
    db = _DummySession(agent=agent)
    service = agents_module.AgentService(db)

    calls: list[str] = []
    monkeypatch.setattr(agents_module, "invalidate_agent_graph_cache", lambda agent_id: calls.append(agent_id))

    payload = AgentUpdate(name="new-name", skills=[{"skill_id": "s2"}])
    result = service.update_agent("agent-1", payload)

    assert result.name == "new-name"
    assert result.skills == [{"skill_id": "s2"}]
    assert calls == ["agent-1"]
