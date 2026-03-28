from __future__ import annotations


def normalize_mode_for_telemetry(mode: str) -> str:
    """Normalize legacy/new mode values for unified metrics."""

    value = (mode or "").strip().lower()
    mode_map = {
        "react": "fast",
        "fast": "fast",
        "router_worker": "planner",
        "planner": "planner",
        "agentic_rag": "rag",
        "rag": "rag",
        "chat_bypass": "chat_bypass",
    }
    return mode_map.get(value, value or "unknown")
