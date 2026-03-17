from __future__ import annotations

from pydantic import BaseModel


class MetricsSummary(BaseModel):
    p95_ms: float
    success_rate: float
    token_day: int
    agent_created_day: int


class MetricsErrorItem(BaseModel):
    code: int
    count: int


class MetricsErrors(BaseModel):
    top_errors: list[MetricsErrorItem]


class MetricsTokenItem(BaseModel):
    date: str
    tokens: int
    cost: float


class MetricsAgents(BaseModel):
    created: int
    used: int
    retention_7d: float
