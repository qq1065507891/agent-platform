from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import re

from app.tools.tool_base import Tool
from app.tools.tool_registry import ToolStats

logger = logging.getLogger(__name__)

_WORD_SPLIT = re.compile(r"[^\w\u4e00-\u9fff]+")


@dataclass(slots=True)
class SelectedTool:
    """Tool selected for current request with score/reason."""

    tool: Tool
    score: float
    reason: str


class SkillSelector:
    """Select top-k relevant tools with progressive disclosure."""

    def __init__(self, *, default_top_k: int = 6) -> None:
        self.default_top_k = max(1, default_top_k)

    def select_top_k(
        self,
        *,
        query: str,
        tools: list[Tool],
        tool_stats: dict[str, ToolStats] | None = None,
        intent: str | None = None,
        top_k: int | None = None,
    ) -> list[SelectedTool]:
        """Rank tools and return top-k candidates for exposure to LLM."""
        if not tools:
            return []

        stats_map = tool_stats or {}
        query_tokens = self._tokenize(query)
        k = max(1, top_k or self.default_top_k)

        scored: list[SelectedTool] = []
        for tool in tools:
            stat = stats_map.get(tool.name)
            semantic_score = self._semantic_score(query_tokens, tool)
            intent_score = self._intent_score(intent, tool)
            reliability_score = stat.success_rate if stat is not None else float(tool.reliability)
            latency_penalty = self._latency_penalty(stat.avg_latency_ms if stat else tool.latency)
            cost_penalty = self._cost_penalty(tool.cost)

            score = (
                0.45 * semantic_score
                + 0.25 * intent_score
                + 0.20 * reliability_score
                - 0.05 * latency_penalty
                - 0.05 * cost_penalty
            )
            reason = (
                f"semantic={semantic_score:.2f},intent={intent_score:.2f},"
                f"reliability={reliability_score:.2f},latency_penalty={latency_penalty:.2f},"
                f"cost_penalty={cost_penalty:.2f}"
            )
            scored.append(SelectedTool(tool=tool, score=score, reason=reason))

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:k]

    def _tokenize(self, text: str) -> set[str]:
        return {token for token in _WORD_SPLIT.split((text or "").lower()) if token}

    def _semantic_score(self, query_tokens: set[str], tool: Tool) -> float:
        if not query_tokens:
            return 0.0
        corpus = f"{tool.name} {tool.description}".lower()
        tool_tokens = {token for token in _WORD_SPLIT.split(corpus) if token}
        if not tool_tokens:
            return 0.0
        overlap = query_tokens.intersection(tool_tokens)
        return len(overlap) / max(1, len(query_tokens))

    def _intent_score(self, intent: str | None, tool: Tool) -> float:
        if not intent:
            return 0.5
        normalized = intent.strip().upper()
        if normalized == "RAG" and tool.type == "rag":
            return 1.0
        if normalized in {"TASK", "ACTION"} and tool.type in {"skill", "api", "mcp"}:
            return 0.9
        if normalized == "CHAT" and tool.type == "rag":
            return 0.3
        return 0.6

    def _latency_penalty(self, latency_ms: float) -> float:
        if latency_ms <= 0:
            return 0.0
        return min(1.0, math.log1p(latency_ms) / math.log1p(5000.0))

    def _cost_penalty(self, cost: float) -> float:
        if cost <= 0:
            return 0.0
        return min(1.0, cost / 10.0)
