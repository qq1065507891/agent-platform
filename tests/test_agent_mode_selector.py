from __future__ import annotations

from app.services.agent.mode_selector import (
    AgentCapabilityLevel,
    resolve_agent_capability_level,
    select_agent_mode,
)


def test_capability_level_3_when_has_knowledge_base():
    level = resolve_agent_capability_level(
        selected_tools=[{"skill_id": "tool.a"}],
        has_knowledge_base=True,
    )
    assert level == AgentCapabilityLevel.LEVEL_3


def test_capability_level_2_when_many_tools_without_knowledge():
    level = resolve_agent_capability_level(
        selected_tools=[{"skill_id": f"tool.{i}"} for i in range(5)],
        has_knowledge_base=False,
    )
    assert level == AgentCapabilityLevel.LEVEL_2


def test_capability_level_1_when_few_tools_without_knowledge():
    level = resolve_agent_capability_level(
        selected_tools=[{"skill_id": "tool.a"}, {"skill_id": "tool.b"}],
        has_knowledge_base=False,
    )
    assert level == AgentCapabilityLevel.LEVEL_1


def test_mode_selector_maps_level_1_to_react():
    decision = select_agent_mode(
        capability_level=AgentCapabilityLevel.LEVEL_1,
        user_query="帮我写一段问候语",
        selected_tools=[{"skill_id": "tool.a"}],
    )
    assert decision["mode"] == "react"


def test_mode_selector_maps_level_2_to_router_worker():
    decision = select_agent_mode(
        capability_level=AgentCapabilityLevel.LEVEL_2,
        user_query="请分步分析并汇总多个来源，最后给出计划",
        selected_tools=[{"skill_id": f"tool.{i}"} for i in range(8)],
    )
    assert decision["mode"] == "router_worker"


def test_mode_selector_maps_level_3_to_agentic_rag():
    decision = select_agent_mode(
        capability_level=AgentCapabilityLevel.LEVEL_3,
        user_query="根据知识库内容回答",
        selected_tools=[{"skill_id": "tool.a"}],
    )
    assert decision["mode"] == "agentic_rag"
