from __future__ import annotations

from app.services.agent.mode_selector import select_agent_mode


def test_mode_selector_react_when_few_tools_and_simple_query():
    decision = select_agent_mode(
        user_query="帮我写一段问候语",
        selected_tools=[{"skill_id": "tool.a"}, {"skill_id": "tool.b"}],
    )
    assert decision["mode"] == "react"


def test_mode_selector_router_worker_when_many_tools():
    decision = select_agent_mode(
        user_query="请分步分析并汇总多个来源，最后给出计划",
        selected_tools=[{"skill_id": f"tool.{i}"} for i in range(8)],
    )
    assert decision["mode"] == "router_worker"
