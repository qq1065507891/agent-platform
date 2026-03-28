from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.tools.tool_base import Tool

logger = logging.getLogger(__name__)


class PlanValidationError(RuntimeError):
    """Raised when plan schema or tool references are invalid."""


class PlanExecutionError(RuntimeError):
    """Raised when a plan step fails and cannot be recovered."""


@dataclass(slots=True)
class PlanStep:
    """One executable planner step."""

    id: int
    tool: str
    input: dict[str, Any]
    status: Literal["pending", "running", "success", "failed"] = "pending"
    retries: int = 0


@dataclass(slots=True)
class Plan:
    """Planner output plan."""

    steps: list[PlanStep] = field(default_factory=list)


@dataclass(slots=True)
class PlannerExecutionResult:
    """Planner execution aggregate result."""

    outputs: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    failure_step_id: int | None = None


class PlannerEngine:
    """Plan-then-execute engine with step-level retry support."""

    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            base_url=settings.llm_gateway_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            streaming=False,
        )

    async def generate_plan(self, *, query: str, context: dict[str, Any], tools: list[Tool]) -> Plan:
        """Generate a structured plan from query and available tools."""
        tool_names = [tool.name for tool in tools]
        prompt = (
            "你是 Planner。请生成 JSON：{\"steps\":[{\"id\":1,\"tool\":\"name\",\"input\":{}}]}。"
            "仅使用可用工具，id 从 1 递增。"
        )
        try:
            response = await self._llm.ainvoke(
                [
                    SystemMessage(content=prompt),
                    SystemMessage(content=f"available_tools={tool_names}"),
                    SystemMessage(content=f"context={json.dumps(context, ensure_ascii=False)}"),
                    HumanMessage(content=query),
                ],
                response_format={"type": "json_object"},
            )
            content = response.content if isinstance(response, AIMessage) else ""
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            parsed = json.loads(text) if text else {"steps": []}
            return self._parse_plan(parsed)
        except Exception as exc:
            logger.exception("failed to generate plan")
            raise PlanValidationError(f"plan_generation_failed: {exc}") from exc

    def validate_plan(self, *, plan: Plan, tools: list[Tool]) -> bool:
        """Validate plan structure and tool existence."""
        if not plan.steps:
            raise PlanValidationError("plan_steps_empty")

        tool_names = {tool.name for tool in tools}
        seen_ids: set[int] = set()
        for step in plan.steps:
            if step.id in seen_ids:
                raise PlanValidationError(f"duplicate_step_id:{step.id}")
            seen_ids.add(step.id)
            if step.tool not in tool_names:
                raise PlanValidationError(f"unknown_tool:{step.tool}")
            if not isinstance(step.input, dict):
                raise PlanValidationError(f"invalid_step_input:{step.id}")
        return True

    async def execute_plan(
        self,
        *,
        plan: Plan,
        tool_executor: Any,
        max_retry: int = 1,
    ) -> PlannerExecutionResult:
        """Execute each plan step using provided async tool executor."""
        result = PlannerExecutionResult()
        for step in plan.steps:
            step.status = "running"
            try:
                output = await tool_executor(step.tool, step.input)
                step.status = "success"
                result.outputs.append({"step_id": step.id, "tool": step.tool, "output": output})
            except Exception as exc:
                retried = await self.retry_step(
                    step=step,
                    error=exc,
                    tool_executor=tool_executor,
                    max_retry=max_retry,
                )
                if retried is not None:
                    result.outputs.append({"step_id": step.id, "tool": step.tool, "output": retried})
                    continue

                step.status = "failed"
                result.success = False
                result.failure_step_id = step.id
                raise PlanExecutionError(f"step_failed:{step.id}:{type(exc).__name__}") from exc
        return result

    async def retry_step(
        self,
        *,
        step: PlanStep,
        error: Exception,
        tool_executor: Any,
        max_retry: int = 1,
    ) -> Any | None:
        """Retry single failed step with bounded retries."""
        logger.warning("planner step failed, retrying: step=%s error=%s", step.id, type(error).__name__)
        while step.retries < max_retry:
            step.retries += 1
            try:
                output = await tool_executor(step.tool, step.input)
                step.status = "success"
                return output
            except Exception as retry_exc:
                logger.warning(
                    "planner step retry failed: step=%s retries=%s error=%s",
                    step.id,
                    step.retries,
                    type(retry_exc).__name__,
                )
                continue
        return None

    def _parse_plan(self, payload: dict[str, Any]) -> Plan:
        raw_steps = payload.get("steps") if isinstance(payload, dict) else None
        if not isinstance(raw_steps, list):
            raise PlanValidationError("plan_schema_invalid")

        steps: list[PlanStep] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, dict):
                continue
            step_id = int(raw_step.get("id") or index)
            tool_name = str(raw_step.get("tool") or "").strip()
            input_payload = raw_step.get("input") if isinstance(raw_step.get("input"), dict) else {}
            if not tool_name:
                continue
            steps.append(PlanStep(id=step_id, tool=tool_name, input=input_payload))

        if not steps:
            raise PlanValidationError("plan_steps_empty")
        return Plan(steps=steps)
