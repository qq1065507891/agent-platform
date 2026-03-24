from __future__ import annotations

from typing import Any, TypedDict

from app.core.config import settings


class AgentModeDecision(TypedDict):
    mode: str
    reason: str
    features: dict[str, Any]


_COMPLEXITY_HINTS = (
    "并且",
    "同时",
    "先",
    "再",
    "然后",
    "分步",
    "步骤",
    "对比",
    "汇总",
    "分析",
    "计划",
)


def _estimate_task_complexity(user_query: str) -> float:
    text = (user_query or "").strip()
    if not text:
        return 0.0

    score = min(len(text) / 300.0, 0.4)
    hint_hits = sum(1 for hint in _COMPLEXITY_HINTS if hint in text)
    score += min(hint_hits * 0.08, 0.4)

    if "\n" in text:
        score += 0.1
    return max(0.0, min(1.0, score))


def _count_selected_tools(skills: list | None) -> int:
    if not skills:
        return 0
    count = 0
    for item in skills:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue
        if item.get("skill_id"):
            count += 1
    return count


def select_agent_mode(*, user_query: str, selected_tools: list | None) -> AgentModeDecision:
    forced = (getattr(settings, "agent_mode_force", "") or "").strip().lower()
    if forced in {"react", "router_worker"}:
        return {
            "mode": forced,
            "reason": "forced_by_config",
            "features": {
                "tool_count": _count_selected_tools(selected_tools),
                "task_complexity": _estimate_task_complexity(user_query),
            },
        }

    tool_count = _count_selected_tools(selected_tools)
    task_complexity = _estimate_task_complexity(user_query)
    tool_threshold = int(getattr(settings, "agent_mode_tool_threshold", 5))
    complexity_threshold = float(getattr(settings, "agent_mode_complexity_threshold", 0.6))

    if tool_count <= tool_threshold and task_complexity < complexity_threshold:
        mode = "react"
        reason = "below_threshold"
    else:
        mode = "router_worker"
        reason = "above_threshold"

    return {
        "mode": mode,
        "reason": reason,
        "features": {
            "tool_count": tool_count,
            "task_complexity": task_complexity,
            "tool_threshold": tool_threshold,
            "complexity_threshold": complexity_threshold,
        },
    }
