from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, TypedDict
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


AgentMode = Literal["fast", "planner", "rag"]


class AgentCapabilityLevel(StrEnum):
    LEVEL_1 = "level_1"
    LEVEL_2 = "level_2"
    LEVEL_3 = "level_3"


class AgentModeDecision(TypedDict):
    mode: str
    reason: str
    features: dict[str, Any]


@dataclass(slots=True)
class RouteFeatures:
    """Normalized features for orchestration mode scoring."""

    complexity: float
    tool_count: int
    requires_rag: bool
    latency_budget: float = 0.8
    cost_sensitivity: float = 0.5


@dataclass(slots=True)
class ModeDecision:
    """Mode selection result used by orchestrator."""

    mode: AgentMode
    score: float
    reason: str
    trace: dict[str, Any] = field(default_factory=dict)


class ModeSelector:
    """Score-based mode selector replacing rule-only routing."""

    def select_mode(self, *, features: RouteFeatures, context: dict[str, Any] | None = None) -> ModeDecision:
        """Compute mode scores and pick the best route."""
        try:
            scores = {
                "fast": self._score_fast(features),
                "planner": self._score_planner(features),
                "rag": self._score_rag(features),
            }

            if not features.requires_rag:
                scores["rag"] -= 0.3
            else:
                scores["rag"] += 0.25

            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            mode, score = ranked[0]
            reason = self._build_reason(mode=mode, scores=scores, features=features)
            return ModeDecision(mode=mode, score=float(score), reason=reason, trace={"scores": scores, "context": context or {}})
        except Exception as exc:
            logger.exception("mode selection failed, fallback to fast")
            return ModeDecision(
                mode="fast",
                score=0.0,
                reason=f"selector_error:{type(exc).__name__}",
                trace={"scores": {"fast": 0.0, "planner": 0.0, "rag": 0.0}},
            )

    def _score_fast(self, features: RouteFeatures) -> float:
        complexity_bonus = max(0.0, 1.0 - features.complexity)
        latency_bonus = features.latency_budget
        tool_penalty = min(1.0, features.tool_count / 12.0)
        return 0.45 * complexity_bonus + 0.35 * latency_bonus - 0.2 * tool_penalty

    def _score_planner(self, features: RouteFeatures) -> float:
        complexity_bonus = features.complexity
        tool_bonus = min(1.0, features.tool_count / 10.0)
        latency_penalty = max(0.0, features.latency_budget - 0.5)
        return 0.45 * complexity_bonus + 0.35 * tool_bonus - 0.2 * latency_penalty

    def _score_rag(self, features: RouteFeatures) -> float:
        rag_bonus = 1.0 if features.requires_rag else 0.0
        complexity_bonus = 0.6 * features.complexity
        cost_penalty = 0.2 * features.cost_sensitivity
        return 0.6 * rag_bonus + complexity_bonus - cost_penalty

    def _build_reason(self, *, mode: str, scores: dict[str, float], features: RouteFeatures) -> str:
        if mode == "rag":
            return f"rag_preferred: requires_rag={features.requires_rag}, score={scores['rag']:.3f}"
        if mode == "planner":
            return f"planner_preferred: complexity={features.complexity:.2f}, tools={features.tool_count}, score={scores['planner']:.3f}"
        return f"fast_preferred: low_complexity={1.0 - features.complexity:.2f}, score={scores['fast']:.3f}"


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


def resolve_agent_capability_level(*, selected_tools: list | None, has_knowledge_base: bool) -> AgentCapabilityLevel:
    """Backward-compatible capability level resolver."""
    if has_knowledge_base:
        return AgentCapabilityLevel.LEVEL_3

    tool_count = _count_selected_tools(selected_tools)
    threshold = int(getattr(settings, "agent_mode_tool_threshold", 5))
    return AgentCapabilityLevel.LEVEL_2 if tool_count >= threshold else AgentCapabilityLevel.LEVEL_1


def select_agent_mode(*, capability_level: AgentCapabilityLevel, user_query: str, selected_tools: list | None) -> AgentModeDecision:
    """Backward-compatible selector output for existing callsites/tests."""
    forced = (getattr(settings, "agent_mode_force", "") or "").strip().lower()
    forced_map = {"react": "react", "router_worker": "router_worker", "agentic_rag": "agentic_rag"}
    if forced in forced_map:
        return {
            "mode": forced_map[forced],
            "reason": "forced_by_config",
            "features": {
                "tool_count": _count_selected_tools(selected_tools),
                "capability_level": capability_level.value,
                "query_len": len((user_query or "").strip()),
            },
        }

    if capability_level == AgentCapabilityLevel.LEVEL_1:
        mode = "react"
        reason = "capability_level_1"
    elif capability_level == AgentCapabilityLevel.LEVEL_2:
        mode = "router_worker"
        reason = "capability_level_2"
    else:
        mode = "agentic_rag"
        reason = "capability_level_3"

    return {
        "mode": mode,
        "reason": reason,
        "features": {
            "tool_count": _count_selected_tools(selected_tools),
            "capability_level": capability_level.value,
            "query_len": len((user_query or "").strip()),
        },
    }


def estimate_complexity(user_query: str) -> float:
    """Heuristic complexity estimation in [0, 1]."""
    text = (user_query or "").strip()
    if not text:
        return 0.0

    length_factor = min(1.0, len(text) / 220.0)
    structured_markers = ["步骤", "计划", "并且", "然后", "最后", "先", "再", "同时"]
    marker_hits = sum(1 for marker in structured_markers if marker in text)
    marker_factor = min(1.0, marker_hits / 4.0)
    return min(1.0, 0.6 * length_factor + 0.4 * marker_factor)


def infer_requires_rag(user_query: str) -> bool:
    """Lightweight rag intent detection."""
    text = (user_query or "").lower()
    markers = ("知识库", "文档", "资料", "根据文档", "基于文档", "rag", "检索")
    return any(marker in text for marker in markers)
