from __future__ import annotations

from typing import TypedDict


class MemoryItem(TypedDict, total=False):
    memory_type: str
    content: str
    score: float
    source: str
    user_id: str
    agent_id: str | None


class MemoryWriteCandidate(TypedDict, total=False):
    memory_type: str
    content: str
    confidence: float
    source: str
    consistency_level: str


class ContextBudget(TypedDict, total=False):
    input_chars: int
    short_context_chars: int
    summary_chars: int
    long_memory_chars: int


class ContextBundle(TypedDict, total=False):
    short_context: str
    summary: str
    long_memories: list[MemoryItem]
    budget: ContextBudget
