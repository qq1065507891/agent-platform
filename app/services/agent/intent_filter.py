from __future__ import annotations

import re
from typing import TypedDict


class IntentDecision(TypedDict):
    intent: str
    reason: str
    features: dict[str, object]


_GREETING_PATTERNS = (
    r"^你好[呀啊吗]?$",
    r"^您好[呀啊吗]?$",
    r"^hi$",
    r"^hello$",
    r"^在吗\??$",
    r"^早上好$",
    r"^晚上好$",
    r"^嗨$",
)

_TASK_HINTS = (
    "请",
    "帮我",
    "执行",
    "调用",
    "工具",
    "查询",
    "检索",
    "知识库",
    "根据文档",
    "基于文档",
    "总结",
    "分析",
    "步骤",
    "计划",
    "代码",
    "写一个",
)


def classify_intent(user_query: str) -> IntentDecision:
    text = (user_query or "").strip()
    normalized = text.lower()

    if not text:
        return {
            "intent": "CHAT",
            "reason": "empty_query",
            "features": {"len": 0, "greeting": False, "task_hint": False},
        }

    greeting = any(re.match(pattern, normalized, flags=re.IGNORECASE) for pattern in _GREETING_PATTERNS)
    task_hint = any(hint in text or hint in normalized for hint in _TASK_HINTS)

    # 轻量旁路策略：
    # - 明确问候 => CHAT
    # - 超短且无任务信号 => CHAT
    # - 其余 => TASK
    if greeting:
        return {
            "intent": "CHAT",
            "reason": "greeting",
            "features": {"len": len(text), "greeting": True, "task_hint": task_hint},
        }

    if len(text) <= 20 and not task_hint:
        return {
            "intent": "CHAT",
            "reason": "short_non_task",
            "features": {"len": len(text), "greeting": False, "task_hint": False},
        }

    return {
        "intent": "TASK",
        "reason": "default_task",
        "features": {"len": len(text), "greeting": greeting, "task_hint": task_hint},
    }
