from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Iterable
import logging
import time

from app.tools.tool_base import Tool

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolStats:
    """Runtime stats for tool ranking and observability."""

    calls: int = 0
    successes: int = 0
    failures: int = 0
    avg_latency_ms: float = 0.0
    last_updated_ts: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.calls <= 0:
            return 1.0
        return self.successes / self.calls


class ToolRegistry:
    """In-process singleton-like registry with immutable snapshot reads."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tools: dict[str, Tool] = {}
        self._stats: dict[str, ToolStats] = {}

    def register(self, tool: Tool) -> None:
        """Register or overwrite a tool definition."""
        with self._lock:
            self._tools[tool.name] = tool
            self._stats.setdefault(tool.name, ToolStats())
            logger.debug("tool registered: %s (%s)", tool.name, tool.type)

    def register_many(self, tools: Iterable[Tool]) -> None:
        """Bulk register tool definitions."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool | None:
        """Get one tool by name."""
        with self._lock:
            return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """Return all tools as a read-only snapshot list."""
        with self._lock:
            return list(self._tools.values())

    def list_by_type(self, tool_type: str) -> list[Tool]:
        """Return tools filtered by type."""
        with self._lock:
            return [tool for tool in self._tools.values() if tool.type == tool_type]

    def snapshot_stats(self) -> dict[str, ToolStats]:
        """Return a copy of all tool stats for scoring."""
        with self._lock:
            return {
                name: ToolStats(
                    calls=stats.calls,
                    successes=stats.successes,
                    failures=stats.failures,
                    avg_latency_ms=stats.avg_latency_ms,
                    last_updated_ts=stats.last_updated_ts,
                )
                for name, stats in self._stats.items()
            }

    def stats_update(self, name: str, *, success: bool, latency_ms: float) -> None:
        """Update runtime reliability and latency stats."""
        with self._lock:
            stats = self._stats.setdefault(name, ToolStats())
            prev_calls = stats.calls
            stats.calls += 1
            if success:
                stats.successes += 1
            else:
                stats.failures += 1

            if prev_calls <= 0:
                stats.avg_latency_ms = float(latency_ms)
            else:
                stats.avg_latency_ms = (stats.avg_latency_ms * prev_calls + float(latency_ms)) / stats.calls
            stats.last_updated_ts = time.time()

    def clear(self) -> None:
        """Clear all registered tools and stats."""
        with self._lock:
            self._tools.clear()
            self._stats.clear()


_registry: ToolRegistry | None = None
_registry_lock = RLock()


def get_tool_registry() -> ToolRegistry:
    """Return global tool registry instance."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ToolRegistry()
        return _registry
