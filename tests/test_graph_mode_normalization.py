from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.services.agent import graph as graph_module


class _FakeGraph:
    def invoke(self, payload):
        return {"messages": payload.get("messages", [])}


def test_execute_mode_path_normalizes_modes_and_routes_safely(monkeypatch):
    captured_flags: list[bool] = []

    def _fake_get_or_build_agent_graph(*, agent_id, enable_retriever_tool):
        del agent_id
        captured_flags.append(bool(enable_retriever_tool))
        return _FakeGraph()

    monkeypatch.setattr(graph_module, "get_or_build_agent_graph", _fake_get_or_build_agent_graph)

    base_kwargs = {
        "agent_id": "agent-1",
        "messages": [HumanMessage(content="hello")],
        "context_bundle": {},
        "user_query": "hello",
    }

    graph_module.execute_mode_path(mode="react", **base_kwargs)
    graph_module.execute_mode_path(mode="router_worker", **base_kwargs)
    graph_module.execute_mode_path(mode="agentic_rag", **base_kwargs)
    graph_module.execute_mode_path(mode="unknown_mode", **base_kwargs)

    assert captured_flags == [False, True, True, False]
