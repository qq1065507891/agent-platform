from __future__ import annotations

from types import SimpleNamespace
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage

from app.schemas.conversation import MessageCreate
from app.services.conversations import ConversationService
from app.services.memory.service import MemoryService


class _DummyQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _DummySession:
    def __init__(self, conversation):
        self._conversation = conversation
        self.commit_count = 0

    def query(self, _model):
        return _DummyQuery(self._conversation)

    def commit(self):
        self.commit_count += 1

    def refresh(self, _obj):
        return None


def test_memory_service_compose_bundle_contains_sections(monkeypatch):
    service = MemoryService()
    history = [
        {"role": "user", "content": "我偏好中文"},
        {"role": "assistant", "content": "好的，我将使用中文"},
    ]

    monkeypatch.setattr(service, "_vector_store", lambda: SimpleNamespace(similarity_search_with_relevance_scores=lambda *_a, **_k: []))

    bundle = service.compose_context_bundle(
        user_query="继续",
        conversation_id="c1",
        user_id="u1",
        agent_id="a1",
        history=history,
    )

    assert "short_context" in bundle
    assert "summary" in bundle
    assert "long_memories" in bundle
    assert "budget" in bundle
    assert bundle["budget"]["input_chars"] >= 1


def test_stream_graph_fallback_and_persist(monkeypatch):
    conversation = SimpleNamespace(
        id="conv-1",
        agent_id="agent-1",
        user_id="user-1",
        messages=[{"role": "user", "content": "历史消息"}],
    )
    db = _DummySession(conversation)

    svc = ConversationService(db)
    svc.observability = SimpleNamespace(log_event=lambda **kwargs: None)
    memory_stub = SimpleNamespace(
        compose_context_bundle=lambda **kwargs: {"budget": {}},
        extract_write_candidates=lambda *_args, **_kwargs: [],
        write_long_term_memories=lambda **_kwargs: [],
    )
    task_calls: list[dict] = []
    monkeypatch.setattr("app.services.conversations.get_memory_service", lambda: memory_stub)
    monkeypatch.setattr(
        "app.services.conversations.memory_writeback_task",
        SimpleNamespace(delay=lambda **kwargs: task_calls.append(kwargs)),
    )

    monkeypatch.setattr("app.services.conversations.get_or_build_agent_graph", lambda agent_id=None: object())

    def _graph_stream(_graph, _messages):
        yield ("final", "已收到你的消息，但当前没有生成文本回复。", None)

    def _direct_stream(_messages):
        yield ("delta", "你好", None)
        yield ("final", "你好，fallback成功", None)

    monkeypatch.setattr("app.services.conversations.stream_assistant_message", _graph_stream)
    monkeypatch.setattr("app.services.conversations.stream_assistant_message_direct", _direct_stream)

    events = list(svc.add_message_stream(conversation, MessageCreate(content="测试fallback")))

    assert any("fallback成功" in event for event in events)
    assert db.commit_count == 1
    assert conversation.messages[-1]["role"] == "assistant"
    assert "fallback成功" in conversation.messages[-1]["content"]
    assert len(task_calls) == 1


def test_stream_persist_structured_message_from_final_state(monkeypatch):
    conversation = SimpleNamespace(
        id="conv-2",
        agent_id="agent-2",
        user_id="user-2",
        messages=[{"role": "user", "content": "历史消息"}],
    )
    db = _DummySession(conversation)

    svc = ConversationService(db)
    svc.observability = SimpleNamespace(log_event=lambda **kwargs: None)
    memory_stub = SimpleNamespace(
        compose_context_bundle=lambda **kwargs: {"budget": {}},
        extract_write_candidates=lambda *_args, **_kwargs: [],
        write_long_term_memories=lambda **_kwargs: [],
    )
    task_calls: list[dict] = []
    monkeypatch.setattr("app.services.conversations.get_memory_service", lambda: memory_stub)
    monkeypatch.setattr(
        "app.services.conversations.memory_writeback_task",
        SimpleNamespace(delay=lambda **kwargs: task_calls.append(kwargs)),
    )

    monkeypatch.setattr("app.services.conversations.get_or_build_agent_graph", lambda agent_id=None: object())

    final_state = [
        AIMessage(
            content="结构化回答",
            tool_calls=[{"id": "t1", "name": "retriever_tool", "args": {"query": "x"}}],
            response_metadata={"model_name": "demo"},
        )
    ]

    def _graph_stream(_graph, _messages):
        yield ("final", "结构化回答", final_state)

    monkeypatch.setattr("app.services.conversations.stream_assistant_message", _graph_stream)
    monkeypatch.setattr("app.services.conversations.stream_assistant_message_direct", lambda _messages: iter(()))

    _ = list(svc.add_message_stream(conversation, MessageCreate(content="测试结构化")))

    assert conversation.messages[-1]["role"] == "assistant"
    assert conversation.messages[-1]["content"] == "结构化回答"
    assert conversation.messages[-1]["tool_calls"][0]["name"] == "retriever_tool"
    assert len(task_calls) == 1


def test_memory_extraction_llm_json_retry_and_fallback(monkeypatch):
    service = MemoryService()

    class _LLM:
        def __init__(self):
            self.calls = 0

        def invoke(self, _messages, response_format=None):
            _ = response_format
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(content="not-json")
            return SimpleNamespace(content='{"items":[{"memory_type":"fact","content":"我在北京工作","confidence":0.86,"source":"user"}]}')

    monkeypatch.setattr("app.services.memory.service.ChatOpenAI", lambda **kwargs: _LLM())
    candidates = service.extract_write_candidates("我在北京工作", "收到")

    assert len(candidates) == 1
    assert candidates[0]["memory_type"] == "fact"
    assert candidates[0]["content"] == "我在北京工作"


def test_memory_writeback_deduplicates_and_threshold(monkeypatch):
    service = MemoryService()

    class _Store:
        def __init__(self):
            self.added = 0

        def similarity_search_with_relevance_scores(self, query, k=1, filter=None):
            if "重复" in query:
                return [(SimpleNamespace(page_content="重复", metadata={}), 0.99)]
            return []

        def add_documents(self, docs):
            self.added += len(docs)

    store = _Store()
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    candidates = [
        {"memory_type": "preference", "content": "重复偏好", "confidence": 0.9, "source": "user"},
        {"memory_type": "fact", "content": "我叫小明", "confidence": 0.8, "source": "user"},
        {"memory_type": "fact", "content": "低置信度", "confidence": 0.3, "source": "user"},
    ]

    accepted = service.write_long_term_memories(user_id="u1", agent_id="a1", candidates=candidates)

    assert len(accepted) == 1
    assert accepted[0]["content"] == "我叫小明"
    assert store.added == 1


def test_memory_extract_candidates_llm_fallback_to_rules(monkeypatch):
    service = MemoryService()

    monkeypatch.setattr(service, "_extract_candidates_by_llm", lambda *_args, **_kwargs: [])

    candidates = service.extract_write_candidates("我偏好中文，请给我计划", "已记录你的偏好")

    types = {item["memory_type"] for item in candidates}
    assert "preference" in types
    assert "task" in types


def test_memory_extract_candidates_llm_success(monkeypatch):
    service = MemoryService()

    llm_result = [
        {"memory_type": "preference", "content": "用户偏好中文", "confidence": 0.88, "source": "user"},
        {"memory_type": "task", "content": "用户要完成部署", "confidence": 0.81, "source": "user"},
    ]
    monkeypatch.setattr(service, "_extract_candidates_by_llm", lambda *_args, **_kwargs: llm_result)

    candidates = service.extract_write_candidates("我偏好中文", "收到")

    assert len(candidates) == 2
    assert candidates[0]["memory_type"] == "preference"
    assert candidates[1]["memory_type"] == "task"
