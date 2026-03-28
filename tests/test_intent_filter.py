from __future__ import annotations

from app.services.agent.intent_filter import classify_intent


def test_intent_filter_greeting_is_chat():
    decision = classify_intent("你好")
    assert decision["intent"] == "CHAT"


def test_intent_filter_short_non_task_is_chat():
    decision = classify_intent("你是谁")
    assert decision["intent"] == "CHAT"


def test_intent_filter_task_hint_is_task():
    decision = classify_intent("请帮我根据知识库总结今天的变更")
    assert decision["intent"] == "TASK"
