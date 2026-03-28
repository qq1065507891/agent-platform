from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
import logging
import time

from app.core.config import settings
from app.services.agent.mode_normalizer import normalize_mode_for_telemetry
from app.services.agent.mode_selector import ModeDecision, ModeSelector, RouteFeatures, estimate_complexity, infer_requires_rag
from app.services.agent.skill_selector import SelectedTool, SkillSelector
from app.tools.tool_base import Tool
from app.tools.tool_registry import ToolRegistry, get_tool_registry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OrchestrationRequest:
    """Input payload for orchestration routing."""

    conversation_id: str
    user_id: str
    agent_id: str | None
    query: str
    history: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrchestrationPlan:
    """Route result consumed by graph execution."""

    decision: ModeDecision
    selected_tools: list[SelectedTool] = field(default_factory=list)
    fallback_chain: list[str] = field(default_factory=list)
    debug_trace: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrchestrationResult:
    """Final orchestrated execution output."""

    mode: Literal["fast", "planner", "rag"]
    answer: str
    selected_tools: list[str] = field(default_factory=list)
    fallback_chain: list[str] = field(default_factory=list)
    debug_trace: dict[str, Any] = field(default_factory=dict)


class MetaOrchestrator:
    """Route scoring, progressive tool exposure, and fallback coordination."""

    def __init__(
        self,
        *,
        mode_selector: ModeSelector | None = None,
        skill_selector: SkillSelector | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.mode_selector = mode_selector or ModeSelector()
        self.skill_selector = skill_selector or SkillSelector(default_top_k=int(getattr(settings, "agent_skill_top_k", 6) or 6))
        self.tool_registry = tool_registry or get_tool_registry()

    async def route(self, request: OrchestrationRequest, context: dict[str, Any] | None = None) -> OrchestrationPlan:
        """Build route decision and selected tool subset before execution."""
        started_at = time.perf_counter()
        context_data = context or {}
        features = self._build_features(request=request, context=context_data)
        decision = self.mode_selector.select_mode(features=features, context=context_data)
        raw_mode = str(getattr(decision, "mode", "fast") or "fast")
        normalized_mode = self._coerce_standard_mode(raw_mode)
        if normalized_mode != raw_mode:
            logger.warning(
                "meta orchestrator normalized non-standard mode from selector: raw=%s normalized=%s",
                raw_mode,
                normalized_mode,
            )
        normalized_trace = dict(getattr(decision, "trace", {}) or {})
        normalized_trace.setdefault("raw_mode", raw_mode)
        decision = ModeDecision(
            mode=normalized_mode,
            score=float(getattr(decision, "score", 0.0) or 0.0),
            reason=str(getattr(decision, "reason", "normalized_mode") or "normalized_mode"),
            trace=normalized_trace,
        )

        tools = self._resolve_candidate_tools(request=request)
        selected_tools = self.skill_selector.select_top_k(
            query=request.query,
            tools=tools,
            tool_stats=self.tool_registry.snapshot_stats(),
            intent=str(context_data.get("intent") or "TASK"),
            top_k=int(context_data.get("top_k") or getattr(settings, "agent_skill_top_k", 6) or 6),
        )

        trace = {
            "features": {
                "complexity": features.complexity,
                "tool_count": features.tool_count,
                "requires_rag": features.requires_rag,
                "latency_budget": features.latency_budget,
                "cost_sensitivity": features.cost_sensitivity,
            },
            "mode_decision": {
                "mode": decision.mode,
                "raw_mode": decision.trace.get("raw_mode", decision.mode),
                "score": decision.score,
                "reason": decision.reason,
                "scores": decision.trace.get("scores", {}),
            },
            "selected_tools": [
                {"name": item.tool.name, "score": round(item.score, 6), "reason": item.reason}
                for item in selected_tools
            ],
            "route_latency_ms": int((time.perf_counter() - started_at) * 1000),
        }

        return OrchestrationPlan(
            decision=decision,
            selected_tools=selected_tools,
            fallback_chain=[],
            debug_trace=trace,
        )

    def build_fallback_chain(self, *, initial_mode: str, requires_rag: bool) -> list[str]:
        """Compute deterministic fallback chain for execution failures."""
        if initial_mode == "rag":
            return ["planner", "fast"]
        if initial_mode == "planner":
            return ["rag", "fast"] if requires_rag else ["fast", "rag"]
        return ["planner", "rag"]

    def _build_features(self, *, request: OrchestrationRequest, context: dict[str, Any]) -> RouteFeatures:
        complexity = float(context.get("complexity") or estimate_complexity(request.query))
        requires_rag = bool(context.get("requires_rag") if "requires_rag" in context else infer_requires_rag(request.query))
        latency_budget = float(context.get("latency_budget") or 0.8)
        cost_sensitivity = float(context.get("cost_sensitivity") or 0.5)

        tools = self._resolve_candidate_tools(request=request)
        return RouteFeatures(
            complexity=max(0.0, min(1.0, complexity)),
            tool_count=len(tools),
            requires_rag=requires_rag,
            latency_budget=max(0.0, min(1.0, latency_budget)),
            cost_sensitivity=max(0.0, min(1.0, cost_sensitivity)),
        )

    def _resolve_candidate_tools(self, *, request: OrchestrationRequest) -> list[Tool]:
        del request
        return self.tool_registry.list_all()

    def _coerce_standard_mode(self, raw_mode: str) -> Literal["fast", "planner", "rag"]:
        normalized = normalize_mode_for_telemetry(raw_mode)
        if normalized in {"fast", "planner", "rag"}:
            return normalized
        return "fast"
