from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
agent_id_var: ContextVar[str | None] = ContextVar("agent_id", default=None)
conversation_id_var: ContextVar[str | None] = ContextVar("conversation_id", default=None)


def generate_trace_id() -> str:
    return uuid4().hex


def set_trace_id(value: str | None) -> None:
    trace_id_var.set(value)


def get_trace_id() -> str | None:
    return trace_id_var.get()


def set_request_id(value: str | None) -> None:
    request_id_var.set(value)


def get_request_id() -> str | None:
    return request_id_var.get()


def set_user_id(value: str | None) -> None:
    user_id_var.set(value)


def get_user_id() -> str | None:
    return user_id_var.get()


def set_agent_id(value: str | None) -> None:
    agent_id_var.set(value)


def get_agent_id() -> str | None:
    return agent_id_var.get()


def set_conversation_id(value: str | None) -> None:
    conversation_id_var.set(value)


def get_conversation_id() -> str | None:
    return conversation_id_var.get()
