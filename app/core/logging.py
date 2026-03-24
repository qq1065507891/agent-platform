from __future__ import annotations

import json
import logging
import logging.config
import random
import time
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

import structlog

from app.core.config import settings
from app.observability.context import (
    get_agent_id,
    get_conversation_id,
    get_request_id,
    get_trace_id,
    get_user_id,
)

_SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "secret",
    "api_key",
}

_ALLOWED_KEYS = {
    "event",
    "level",
    "logger",
    "timestamp",
    "ts",
    "service",
    "env",
    "trace_id",
    "request_id",
    "user_id",
    "agent_id",
    "conversation_id",
    "status_code",
    "method",
    "path",
    "latency_ms",
    "task_id",
    "task_name",
    "error",
    "error_type",
    "exc_info",
    "batch_size",
    "processed",
    "dispatched",
    "accepted_count",
    "detail",
    "client_ip",
    "user_agent",
    "state",
    "broker",
    "result_backend",
    "task_time_limit",
}


def _mask_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def _truncate_scalar(value: Any) -> Any:
    if isinstance(value, str) and len(value) > settings.log_max_field_length:
        return value[: settings.log_max_field_length] + "...[truncated]"
    return value


def _redact(data: Any, parent_key: str | None = None) -> Any:
    if isinstance(data, Mapping):
        redacted: dict[str, Any] = {}
        for k, v in data.items():
            normalized = str(k).lower()
            if normalized in _SENSITIVE_KEYS:
                redacted[str(k)] = _mask_value(v)
            else:
                redacted[str(k)] = _redact(v, parent_key=normalized)
        return redacted
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        max_items = max(settings.log_max_collection_items, 1)
        items = [_redact(item, parent_key=parent_key) for item in data[:max_items]]
        if len(data) > max_items:
            items.append(f"...[{len(data) - max_items} more]")
        return items
    if parent_key in _SENSITIVE_KEYS:
        return _mask_value(data)
    if isinstance(data, str) and len(data) > 40 and ("bearer " in data.lower() or "sk-" in data.lower()):
        return _mask_value(data)
    return _truncate_scalar(data)


def add_common_fields(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    event_dict.setdefault("service", settings.app_name)
    event_dict.setdefault("env", settings.app_env)
    event_dict.setdefault("trace_id", get_trace_id())
    event_dict.setdefault("request_id", get_request_id())
    event_dict.setdefault("user_id", get_user_id())
    event_dict.setdefault("agent_id", get_agent_id())
    event_dict.setdefault("conversation_id", get_conversation_id())
    event_dict["ts"] = int(time.time() * 1000)
    return event_dict


def keep_allowed_fields(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    filtered = {k: v for k, v in event_dict.items() if k in _ALLOWED_KEYS}
    for k in ("event", "level", "logger", "timestamp"):
        if k in event_dict:
            filtered[k] = event_dict[k]
    return filtered


def sample_info_logs(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    level = str(event_dict.get("level", "")).lower()
    if level != "info":
        return event_dict
    if settings.log_info_sample_rate >= 1.0:
        return event_dict
    if settings.log_info_sample_rate <= 0.0:
        raise structlog.DropEvent
    if random.random() > settings.log_info_sample_rate:
        raise structlog.DropEvent
    return event_dict


def redact_sensitive(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    return _redact(event_dict)


def _json_renderer(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> str:
    return json.dumps(event_dict, ensure_ascii=False, default=str)


def _resolve_log_level() -> str:
    env = settings.app_env.lower()
    if env == "dev":
        return settings.log_level_dev
    if env in {"staging", "stage", "test"}:
        return settings.log_level_staging
    if env in {"prod", "production"}:
        return settings.log_level_prod
    return settings.log_level


def setup_logging() -> None:
    processors = [
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        add_common_fields,
        keep_allowed_fields,
        redact_sensitive,
        sample_info_logs,
        structlog.processors.format_exc_info,
        _json_renderer,
    ]

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "format": "%(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "plain",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": _resolve_log_level(),
            },
            "loggers": {
                "uvicorn": {"level": "WARNING"},
                "uvicorn.error": {"level": "WARNING", "propagate": True},
                "uvicorn.access": {"level": "WARNING", "propagate": False},
                "sqlalchemy.engine": {"level": "WARNING", "propagate": False},
            },
        }
    )

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
