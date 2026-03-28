from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.agent.meta_orchestrator import MetaOrchestrator, OrchestrationRequest
from app.tools.tool_base import Tool
from app.tools.tool_registry import ToolRegistry


class _FakeModeSelector:
    def select_mode(self, *, features, context):
        del features, context
        return SimpleNamespace(
            mode="react",
            score=0.88,
            reason="legacy_react_for_test",
            trace={"scores": {"fast": 0.88, "planner": 0.12, "rag": -0.1}},
        )


def test_meta_orchestrator_trace_mode_is_normalized_with_raw_mode_preserved():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="search_docs",
            description="Search knowledge docs",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            type="rag",
        )
    )

    orchestrator = MetaOrchestrator(mode_selector=_FakeModeSelector(), tool_registry=registry)
    request = OrchestrationRequest(
        conversation_id="conv-1",
        user_id="user-1",
        agent_id="agent-1",
        query="根据知识库回答这个问题",
    )

    plan = asyncio.run(orchestrator.route(request, {"intent": "RAG", "requires_rag": True, "top_k": 3}))

    decision_trace = plan.debug_trace["mode_decision"]
    assert decision_trace["mode"] == "fast"
    assert decision_trace["raw_mode"] == "react"
    assert plan.debug_trace["selected_tools"]
