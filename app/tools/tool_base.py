from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ToolType = Literal["skill", "api", "rag", "mcp"]


@dataclass(slots=True)
class Tool:
    """Unified tool descriptor used by registry and selectors."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    type: ToolType
    cost: float = 0.0
    latency: float = 0.0
    reliability: float = 1.0
