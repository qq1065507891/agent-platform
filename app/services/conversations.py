from __future__ import annotations

from collections.abc import Iterator
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import time

from langchain_core.messages import AIMessage, SystemMessage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.observability.context import (
    generate_trace_id,
    get_trace_id,
    set_agent_id,
    set_conversation_id,
)
from app.observability.service import ObservabilityService
from app.schemas.conversation import ConversationCreate, ConversationRename, MessageCreate
from app.services.agent.graph import (
    EMPTY_ASSISTANT_REPLY,
    ensure_user_message,
    execute_mode_path,
    extract_assistant_message,
    get_or_build_agent_graph,
    serialize_message,
    stream_assistant_message,
    stream_assistant_message_direct,
    to_langchain_messages,
)
from app.services.agent.intent_filter import classify_intent
from app.services.agent.meta_orchestrator import MetaOrchestrator, OrchestrationRequest
from app.services.agent.mode_normalizer import normalize_mode_for_telemetry
from app.services.agent.mode_selector import resolve_agent_capability_level, select_agent_mode
from app.services.agent.router_worker import invoke_router_worker, stream_router_worker
from app.services.memory.service import get_memory_service
from app.services.rag_service import get_rag_service
from app.tasks.memory_tasks import memory_writeback_task

logger = logging.getLogger(__name__)

_ORCHESTRATOR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orchestrator-route")


def _chat_fast_config() -> tuple[str | None, float, str | None, str | None]:
    model = (getattr(settings, "llm_chat_fast_model", "") or "").strip() or None
    timeout_seconds = float(getattr(settings, "llm_chat_fast_timeout_seconds", 12.0))
    base_url = (getattr(settings, "llm_chat_fast_base_url", "") or "").strip() or None
    api_key = (getattr(settings, "llm_chat_fast_api_key", "") or "").strip() or None
    return model, timeout_seconds, base_url, api_key


def _build_source_message_id(*, conversation_id: str, user_message: str, assistant_message: str) -> str:
    payload = f"{conversation_id}|{user_message}|{assistant_message}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:36]


def trim_messages_for_budget(messages: list, max_turns: int) -> list:
    if max_turns <= 0:
        return messages

    system_messages = [m for m in messages if isinstance(m, SystemMessage)]
    non_system_messages = [m for m in messages if not isinstance(m, SystemMessage)]
    keep_count = max_turns * 2
    trimmed = non_system_messages[-keep_count:] if len(non_system_messages) > keep_count else non_system_messages
    return [*system_messages, *trimmed]


def _truncate_text(value: str, max_chars: int) -> str:
    text = (value or "").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + "...(已截断)"


def _normalize_empty_knowledge_reply(text: str) -> str:
    value = (text or "").strip()
    marker = "知识库暂无匹配内容"
    if not value:
        return value
    if marker not in value:
        return value

    count = value.count(marker)
    if count <= 1:
        return value

    return value.replace(f"{marker}。{marker}。", f"{marker}。")


def _enqueue_memory_writeback_task(
    *,
    conversation: Conversation,
    trace_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    memory_writeback_task.delay(
        user_id=conversation.user_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.id,
        trace_id=trace_id,
        user_message=user_message,
        assistant_message=assistant_message,
    )


def _persist_conversation_messages(
    db: Session,
    conversation: Conversation,
    updated_messages: list[dict],
    *,
    requery: bool = True,
    refresh: bool = True,
) -> None:
    target = conversation
    if requery:
        db_conversation = db.query(Conversation).filter(Conversation.id == conversation.id).first()
        if db_conversation is None:
            return
        target = db_conversation

    target.messages = updated_messages
    db.commit()
    if refresh:
        db.refresh(target)


def _write_long_term_memories_transactional(
    *,
    db: Session,
    conversation: Conversation,
    trace_id: str,
    user_message: str,
    assistant_message: str,
    source_message_id: str,
) -> int:
    memory_service = get_memory_service()
    write_candidates = memory_service.extract_write_candidates(user_message, assistant_message)
    accepted = memory_service.write_long_term_memories(
        user_id=conversation.user_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.id,
        trace_id=trace_id,
        source_message_id=source_message_id,
        candidates=write_candidates,
        db=db,
    )
    return len(accepted)


def _build_message_sent_metadata(
    *,
    trace_id: str,
    message_length: int,
    mode: str,
    path: str,
    retrieval_latency_ms: int | None,
    llm_total_ms: int,
    memory_writeback_mode: str,
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "message_length": message_length,
        "mode": mode,
        "path": path,
        "retrieval_latency_ms": retrieval_latency_ms,
        "llm_total_ms": llm_total_ms,
        "memory_writeback_mode": memory_writeback_mode,
    }


def _log_agent_use_event(
    service: ObservabilityService,
    *,
    conversation: Conversation,
    trace_id: str,
    source: str,
) -> None:
    service.log_event(
        event_type="agent_use",
        user_id=conversation.user_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.id,
        metadata={"trace_id": trace_id, "source": source},
    )


def _log_conversation_message_sent(
    service: ObservabilityService,
    *,
    conversation: Conversation,
    trace_id: str,
    message_length: int,
    mode: str,
    path: str,
    retrieval_latency_ms: int | None,
    llm_total_ms: int,
    memory_writeback_mode: str,
) -> None:
    service.log_event(
        event_type="conversation_message_sent",
        user_id=conversation.user_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.id,
        metadata=_build_message_sent_metadata(
            trace_id=trace_id,
            message_length=message_length,
            mode=mode,
            path=path,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_total_ms=llm_total_ms,
            memory_writeback_mode=memory_writeback_mode,
        ),
    )


def _log_post_response_events(
    service: ObservabilityService,
    *,
    conversation: Conversation,
    trace_id: str,
    source: str,
    message_length: int,
    mode: str,
    path: str,
    retrieval_latency_ms: int | None,
    llm_total_ms: int,
    memory_writeback_mode: str,
) -> None:
    _log_conversation_message_sent(
        service,
        conversation=conversation,
        trace_id=trace_id,
        message_length=message_length,
        mode=mode,
        path=path,
        retrieval_latency_ms=retrieval_latency_ms,
        llm_total_ms=llm_total_ms,
        memory_writeback_mode=memory_writeback_mode,
    )
    _log_agent_use_event(
        service,
        conversation=conversation,
        trace_id=trace_id,
        source=source,
    )


def _resolve_memory_writeback_mode(*, force_async: bool = False) -> str:
    memory_transactional = bool(getattr(settings, "memory_transactional_write_enabled", True))
    if force_async:
        return "async"
    if memory_transactional:
        return "transactional"
    return "async" if getattr(settings, "memory_writeback_async_enabled", True) else "sync"


def _build_memory_system_prompt(context_bundle: dict) -> str:
    short_context_raw = str(context_bundle.get("short_context") or "")
    summary_raw = str(context_bundle.get("summary") or "")
    long_memories = context_bundle.get("long_memories") or []

    summary = _truncate_text(summary_raw, int(getattr(settings, "memory_prompt_summary_max_chars", 1000)))
    short_context = _truncate_text(
        short_context_raw,
        int(getattr(settings, "memory_prompt_short_context_max_chars", 1200)),
    )

    max_items = int(getattr(settings, "memory_prompt_long_memories_max_items", 5))
    item_max_chars = int(getattr(settings, "memory_prompt_long_memory_item_max_chars", 220))

    memory_lines = []
    for item in long_memories[:max_items]:
        if not isinstance(item, dict):
            continue
        content = _truncate_text(str(item.get("content") or ""), item_max_chars)
        if not content:
            continue
        memory_type = str(item.get("memory_type") or "memory")
        memory_lines.append(f"- [{memory_type}] {content}")

    memory_block = "\n".join(memory_lines) if memory_lines else "- (暂无长期记忆命中)"

    return (
        "以下为上下文工程注入内容，请仅在相关时使用，不得编造事实。\n"
        f"【会话摘要】\n{summary or '(暂无摘要)'}\n\n"
        f"【短期记忆（最近轮次）】\n{short_context or '(暂无短期记忆)'}\n\n"
        f"【长期记忆召回】\n{memory_block}"
    )


def _agent_has_knowledge_base(agent: Agent | None) -> bool:
    if not agent:
        return False
    try:
        return get_rag_service().has_agent_knowledge(agent.id)
    except Exception:
        return False


def _record_agent_routing_decision(
    service: ObservabilityService,
    *,
    conversation: Conversation,
    trace_id: str,
    selected_mode: str,
    reason: str,
    features: dict,
    intent_decision: dict,
) -> None:
    service.log_event(
        event_type="agent_mode_selected",
        user_id=conversation.user_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.id,
        metadata={
            "trace_id": trace_id,
            "mode": selected_mode,
            "reason": reason,
            "features": features,
            "intent": intent_decision.get("intent"),
            "intent_reason": intent_decision.get("reason"),
            "intent_features": intent_decision.get("features", {}),
        },
    )


def _log_orchestrator_trace(
    service: ObservabilityService,
    *,
    conversation: Conversation,
    trace_id: str,
    mode: str,
    orchestration_plan: object,
    stream: bool = False,
) -> None:
    selected_tools = []
    fallback_chain = []
    debug_trace = {}

    if orchestration_plan is not None:
        selected_tools = [item.tool.name for item in getattr(orchestration_plan, "selected_tools", [])]
        fallback_chain = list(getattr(orchestration_plan, "fallback_chain", []) or [])
        debug_trace = dict(getattr(orchestration_plan, "debug_trace", {}) or {})

    service.log_event(
        event_type="agent_orchestrator_trace",
        user_id=conversation.user_id,
        agent_id=conversation.agent_id,
        conversation_id=conversation.id,
        metadata={
            "trace_id": trace_id,
            "mode": normalize_mode_for_telemetry(mode),
            "selected_skills": selected_tools,
            "fallback_chain": fallback_chain,
            "debug_trace": debug_trace,
            "stream": stream,
        },
    )


def _run_orchestrator_route_sync(
    orchestrator: MetaOrchestrator,
    orchestration_request: OrchestrationRequest,
    route_context: dict[str, object],
):
    """Run async orchestrator route safely from sync code paths."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(orchestrator.route(orchestration_request, route_context))

    future = _ORCHESTRATOR_EXECUTOR.submit(
        lambda: asyncio.run(orchestrator.route(orchestration_request, route_context))
    )
    return future.result(timeout=float(getattr(settings, "router_llm_timeout_seconds", 8.0) or 8.0) + 2.0)


def _invoke_agent_graph_mode(
    *,
    agent_id: str,
    messages: list,
    context_bundle: dict,
    user_query: str,
    enable_retriever_tool: bool,
) -> dict:
    graph = get_or_build_agent_graph(agent_id=agent_id, enable_retriever_tool=enable_retriever_tool)
    return graph.invoke(
        {
            "messages": messages,
            "context_bundle": context_bundle,
            "user_query": user_query,
        }
    )


def _stream_agent_graph_mode(
    *,
    agent_id: str,
    messages: list,
    context_bundle: dict,
    user_query: str,
    enable_retriever_tool: bool,
):
    graph = get_or_build_agent_graph(agent_id=agent_id, enable_retriever_tool=enable_retriever_tool)
    graph_input_state = {
        "messages": messages,
        "context_bundle": context_bundle,
        "user_query": user_query,
    }
    return stream_assistant_message(graph, graph_input_state)


def _execute_mode_sync(
    *,
    selected_mode: str,
    agent_id: str,
    messages: list,
    context_bundle: dict,
    user_query: str,
) -> tuple[dict, int | None]:
    if selected_mode == "router_worker":
        result = invoke_router_worker(
            agent_id=agent_id,
            messages=messages,
            context_bundle=context_bundle,
            user_query=user_query,
        )
        metrics = result.get("retrieval_metrics") if isinstance(result, dict) else None
        retrieval_latency_ms = metrics.get("retrieval_latency_ms") if isinstance(metrics, dict) else None
        return result, retrieval_latency_ms

    result = _invoke_agent_graph_mode(
        agent_id=agent_id,
        messages=messages,
        context_bundle=context_bundle,
        user_query=user_query,
        enable_retriever_tool=(selected_mode == "agentic_rag"),
    )
    return result, None


def _execute_mode_stream(
    *,
    selected_mode: str,
    agent_id: str,
    messages: list,
    context_bundle: dict,
    user_query: str,
):
    if selected_mode in {"planner", "router_worker"}:
        return stream_router_worker(
            agent_id=agent_id,
            messages=messages,
            context_bundle=context_bundle,
            user_query=user_query,
        )

    return _stream_agent_graph_mode(
        agent_id=agent_id,
        messages=messages,
        context_bundle=context_bundle,
        user_query=user_query,
        enable_retriever_tool=(selected_mode in {"rag", "agentic_rag"}),
    )


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.observability = ObservabilityService(db)
        self.meta_orchestrator = MetaOrchestrator()

    def create_conversation(self, payload: ConversationCreate, user_id: str) -> Conversation:
        agent = self.db.query(Agent).filter(Agent.id == payload.agent_id).first()
        if not agent:
            raise ValueError("智能体不存在")
        conversation = Conversation(
            agent_id=payload.agent_id,
            user_id=user_id,
            title=None,
            messages=[],
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        self.observability.log_event(
            event_type="conversation_created",
            user_id=user_id,
            agent_id=payload.agent_id,
            conversation_id=conversation.id,
            metadata={"conversation_id": conversation.id},
        )
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def list_user_conversations(self, user_id: str, agent_id: str | None = None) -> list[Conversation]:
        query = self.db.query(Conversation).filter(Conversation.user_id == user_id)
        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)
        items = query.order_by(Conversation.created_at.desc()).all()
        return [item for item in items if item.messages]

    def rename_conversation(self, conversation_id: str, payload: ConversationRename) -> Conversation:
        conversation = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conversation:
            raise ValueError("会话不存在")
        try:
            conversation.title = payload.title.strip()
            self.db.commit()
            self.db.refresh(conversation)
            return conversation
        except Exception as exc:
            self.db.rollback()
            raise RuntimeError("重命名会话失败，请稍后重试") from exc

    def delete_conversation(self, conversation_id: str) -> None:
        conversation = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conversation:
            raise ValueError("会话不存在")
        try:
            self.db.delete(conversation)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise RuntimeError("删除会话失败，请稍后重试") from exc

    def _prepare_history_messages(self, conversation: Conversation) -> tuple[list[dict], list]:
        history = conversation.messages or []
        langchain_messages = to_langchain_messages(history)
        if not history:
            agent = self.db.query(Agent).filter(Agent.id == conversation.agent_id).first()
            prompt_template = (agent.prompt_template or "").strip() if agent else ""
            if prompt_template:
                langchain_messages = [SystemMessage(content=prompt_template), *langchain_messages]
        return history, langchain_messages

    def _prepare_messages(
        self,
        conversation: Conversation,
        content: str,
        *,
        include_long_term: bool = True,
    ) -> tuple[list[dict], list, dict]:
        history, langchain_messages = self._prepare_history_messages(conversation)
        memory_service = get_memory_service()
        context_bundle = memory_service.compose_context_bundle(
            user_query=content,
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            history=history,
            include_long_term=include_long_term,
        )

        if getattr(settings, "memory_enabled", True):
            memory_prompt = _build_memory_system_prompt(context_bundle)
            langchain_messages = [SystemMessage(content=memory_prompt), *langchain_messages]

        langchain_messages = ensure_user_message(langchain_messages, content)
        langchain_messages = trim_messages_for_budget(
            langchain_messages,
            max_turns=int(getattr(settings, "max_history_turns", 10)),
        )
        return history, langchain_messages, context_bundle

    def add_message(self, conversation: Conversation, payload: MessageCreate) -> dict[str, str]:
        request_start = time.perf_counter()
        trace_id = get_trace_id() or generate_trace_id()
        history, langchain_messages, _context_bundle = self._prepare_messages(
            conversation,
            payload.content,
            include_long_term=True,
        )
        set_agent_id(conversation.agent_id)
        set_conversation_id(conversation.id)

        agent = self.db.query(Agent).filter(Agent.id == conversation.agent_id).first()
        has_knowledge_base = _agent_has_knowledge_base(agent)
        capability_level = resolve_agent_capability_level(
            selected_tools=(agent.skills if agent else []),
            has_knowledge_base=has_knowledge_base,
        )
        intent_decision = classify_intent(payload.content)

        selected_mode = "chat_bypass"
        reason = "intent_chat_bypass"
        features: dict = {
            "capability_level": capability_level.value,
            "has_knowledge_base": has_knowledge_base,
        }
        retrieval_latency_ms = None

        if intent_decision.get("intent") == "CHAT":
            result = {"messages": langchain_messages}
            assistant_message = ""
            fast_model, fast_timeout, fast_base_url, fast_api_key = _chat_fast_config()
            for event_type, content, _final_state in stream_assistant_message_direct(
                langchain_messages,
                model=fast_model,
                timeout_seconds=fast_timeout,
                base_url=fast_base_url,
                api_key=fast_api_key,
            ):
                if event_type == "final" and content:
                    assistant_message = content
            result["messages"] = [*langchain_messages, AIMessage(content=assistant_message)]
        else:
            orchestration_request = OrchestrationRequest(
                conversation_id=conversation.id,
                user_id=conversation.user_id,
                agent_id=conversation.agent_id,
                query=payload.content,
                history=history,
                context={"intent": intent_decision.get("intent")},
            )
            orchestration_plan = None
            if bool(getattr(settings, "orchestrator_v2_enabled", True)):
                try:
                    orchestration_plan = _run_orchestrator_route_sync(
                        self.meta_orchestrator,
                        orchestration_request,
                        {
                            "intent": intent_decision.get("intent"),
                            "requires_rag": has_knowledge_base,
                            "top_k": int(getattr(settings, "agent_skill_top_k", 6) or 6),
                        },
                    )
                except Exception as exc:
                    logger.warning("meta orchestrator route failed, fallback legacy mode: %s", exc)

            if orchestration_plan is not None:
                selected_mode = str(orchestration_plan.decision.mode)
                reason = str(orchestration_plan.decision.reason)
                features = orchestration_plan.debug_trace.get("features", features)

                mode_map = {"fast": "react", "planner": "router_worker", "rag": "agentic_rag"}
                route_mode = mode_map.get(selected_mode, "react")
                result = execute_mode_path(
                    mode=selected_mode,
                    agent_id=conversation.agent_id,
                    messages=langchain_messages,
                    context_bundle=_context_bundle,
                    user_query=payload.content,
                    enable_retriever_tool=(route_mode == "agentic_rag"),
                )
            else:
                mode_decision = select_agent_mode(
                    capability_level=capability_level,
                    user_query=payload.content,
                    selected_tools=(agent.skills if agent else []),
                )
                selected_mode = str(mode_decision.get("mode") or "react")
                reason = str(mode_decision.get("reason") or "capability_routing")
                features = mode_decision.get("features", {}) if isinstance(mode_decision.get("features"), dict) else features

                result, retrieval_latency_ms = _execute_mode_sync(
                    selected_mode=selected_mode,
                    agent_id=conversation.agent_id,
                    messages=langchain_messages,
                    context_bundle=_context_bundle,
                    user_query=payload.content,
                )

        telemetry_mode = normalize_mode_for_telemetry(selected_mode)

        _record_agent_routing_decision(
            self.observability,
            conversation=conversation,
            trace_id=trace_id,
            selected_mode=telemetry_mode,
            reason=reason,
            features=features,
            intent_decision=intent_decision,
        )
        if orchestration_plan is not None:
            _log_orchestrator_trace(
                self.observability,
                conversation=conversation,
                trace_id=trace_id,
                mode=selected_mode,
                orchestration_plan=orchestration_plan,
                stream=False,
            )
        final_messages = result.get("messages", langchain_messages)
        assistant_message = _normalize_empty_knowledge_reply(extract_assistant_message(final_messages))

        updated_messages = [*history, {"role": "user", "content": payload.content}]
        final_ai_message = next((msg for msg in reversed(final_messages) if isinstance(msg, AIMessage)), None)
        if final_ai_message is not None:
            updated_messages.append(serialize_message(final_ai_message))
        else:
            updated_messages.append({"role": "assistant", "content": assistant_message})

        force_stream_async_writeback = bool(getattr(settings, "memory_stream_force_async_writeback", True))
        memory_writeback_mode = _resolve_memory_writeback_mode(force_async=force_stream_async_writeback)
        writeback_start = time.perf_counter()
        writeback_status = "success"
        accepted_count = 0
        error_message = None
        source_message_id = _build_source_message_id(
            conversation_id=conversation.id,
            user_message=payload.content,
            assistant_message=assistant_message,
        )
        persist_before_done = memory_writeback_mode != "async"

        try:
            if memory_writeback_mode == "async":
                _persist_conversation_messages(
                    self.db,
                    conversation,
                    updated_messages,
                    requery=False,
                    refresh=True,
                )
                _enqueue_memory_writeback_task(
                    conversation=conversation,
                    trace_id=trace_id,
                    user_message=payload.content,
                    assistant_message=assistant_message,
                )
            else:
                accepted_count = _write_long_term_memories_transactional(
                    db=self.db,
                    conversation=conversation,
                    trace_id=trace_id,
                    user_message=payload.content,
                    assistant_message=assistant_message,
                    source_message_id=source_message_id,
                )
                _persist_conversation_messages(
                    self.db,
                    conversation,
                    updated_messages,
                    requery=False,
                    refresh=True,
                )
        except Exception as exc:
            writeback_status = "failed"
            error_message = str(exc)
            self.db.rollback()
            logger.warning("sync memory writeback failed: %s", exc)
            raise RuntimeError("会话写入失败，请稍后重试") from exc
        finally:
            self.observability.log_event(
                event_type="memory_writeback",
                user_id=conversation.user_id,
                agent_id=conversation.agent_id,
                conversation_id=conversation.id,
                metadata={
                    "trace_id": trace_id,
                    "status": writeback_status,
                    "latency_ms": int((time.perf_counter() - writeback_start) * 1000),
                    "accepted_count": accepted_count,
                    "error": error_message,
                    "source_message_id": source_message_id,
                },
            )

        self.observability.log_event(
            event_type="memory_stream_persist_consistency",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={
                "trace_id": trace_id,
                "persist_before_done": persist_before_done,
                "memory_writeback_mode": memory_writeback_mode,
                "source_message_id": source_message_id,
            },
        )
        total_ms = int((time.perf_counter() - request_start) * 1000)
        _log_post_response_events(
            self.observability,
            conversation=conversation,
            trace_id=trace_id,
            source="conversation_message",
            message_length=len(payload.content),
            mode="sync",
            path=telemetry_mode,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_total_ms=total_ms,
            memory_writeback_mode=memory_writeback_mode,
        )

        return {
            "assistant_message": assistant_message,
            "trace_id": trace_id,
        }

    def add_message_stream(self, conversation: Conversation, payload: MessageCreate) -> Iterator[str]:
        request_start = time.perf_counter()
        trace_id = get_trace_id() or generate_trace_id()
        stream_use_long_term = bool(getattr(settings, "memory_stream_use_long_term", False))
        history, langchain_messages, context_bundle = self._prepare_messages(
            conversation,
            payload.content,
            include_long_term=stream_use_long_term,
        )
        set_agent_id(conversation.agent_id)
        set_conversation_id(conversation.id)

        assembled = ""
        got_delta = False
        first_delta_ms: int | None = None
        delta_count = 0
        llm_path = "graph"
        selected_mode = "react"
        used_direct_fallback = False
        stream_final_state: list | None = None
        stream_metrics: dict | None = None
        stream_sources: list[dict] = []
        graph_reason = "ok"

        agent = self.db.query(Agent).filter(Agent.id == conversation.agent_id).first()
        has_knowledge_base = _agent_has_knowledge_base(agent)
        capability_level = resolve_agent_capability_level(
            selected_tools=(agent.skills if agent else []),
            has_knowledge_base=has_knowledge_base,
        )
        intent_decision = classify_intent(payload.content)

        selected_mode = "chat_bypass"
        reason = "intent_chat_bypass"
        features: dict = {
            "capability_level": capability_level.value,
            "has_knowledge_base": has_knowledge_base,
        }
        llm_path = selected_mode

        orchestration_plan = None
        try:
            if intent_decision.get("intent") == "CHAT":
                fast_model, fast_timeout, fast_base_url, fast_api_key = _chat_fast_config()
                stream_iter = stream_assistant_message_direct(
                    langchain_messages,
                    model=fast_model,
                    timeout_seconds=fast_timeout,
                    base_url=fast_base_url,
                    api_key=fast_api_key,
                )
            else:
                if bool(getattr(settings, "orchestrator_v2_enabled", True)):
                    try:
                        orchestration_plan = _run_orchestrator_route_sync(
                            self.meta_orchestrator,
                            OrchestrationRequest(
                                conversation_id=conversation.id,
                                user_id=conversation.user_id,
                                agent_id=conversation.agent_id,
                                query=payload.content,
                                history=history,
                                context={"intent": intent_decision.get("intent")},
                            ),
                            {
                                "intent": intent_decision.get("intent"),
                                "requires_rag": has_knowledge_base,
                                "top_k": int(getattr(settings, "agent_skill_top_k", 6) or 6),
                            },
                        )
                    except Exception as exc:
                        logger.warning("meta orchestrator(stream) route failed, fallback legacy mode: %s", exc)

                if orchestration_plan is not None:
                    selected_mode = str(orchestration_plan.decision.mode)
                    reason = str(orchestration_plan.decision.reason)
                    features = orchestration_plan.debug_trace.get("features", features)
                    llm_path = selected_mode

                    stream_iter = _execute_mode_stream(
                        selected_mode=selected_mode,
                        agent_id=conversation.agent_id,
                        messages=langchain_messages,
                        context_bundle=context_bundle,
                        user_query=payload.content,
                    )
                else:
                    mode_decision = select_agent_mode(
                        capability_level=capability_level,
                        user_query=payload.content,
                        selected_tools=(agent.skills if agent else []),
                    )
                    selected_mode = str(mode_decision.get("mode") or "react")
                    reason = str(mode_decision.get("reason") or "capability_routing")
                    features = mode_decision.get("features", {}) if isinstance(mode_decision.get("features"), dict) else features
                    llm_path = selected_mode
                    stream_iter = _execute_mode_stream(
                        selected_mode=selected_mode,
                        agent_id=conversation.agent_id,
                        messages=langchain_messages,
                        context_bundle=context_bundle,
                        user_query=payload.content,
                    )
            for event_type, content, final_state in stream_iter:
                if event_type == "delta" and content:
                    got_delta = True
                    delta_count += 1
                    if first_delta_ms is None:
                        first_delta_ms = int((time.perf_counter() - request_start) * 1000)
                    assembled += content
                    server_ts_ms = int(time.time() * 1000)
                    yield f"data: {json.dumps({'type': 'delta', 'content': content, 'server_ts_ms': server_ts_ms}, ensure_ascii=False)}\n\n"
                elif event_type == "final":
                    if content and content != EMPTY_ASSISTANT_REPLY:
                        assembled = content
                    if isinstance(final_state, dict):
                        stream_final_state = final_state.get("messages")
                        stream_metrics = final_state.get("stream_metrics")
                        stream_sources = final_state.get("sources") or []
                    elif final_state:
                        stream_final_state = final_state
        except Exception as exc:
            graph_reason = f"graph_exception:{type(exc).__name__}"
            logger.warning("%s stream failed, fallback to direct: %s", selected_mode, exc)

        telemetry_mode = normalize_mode_for_telemetry(selected_mode)

        _record_agent_routing_decision(
            self.observability,
            conversation=conversation,
            trace_id=trace_id,
            selected_mode=telemetry_mode,
            reason=reason,
            features=features,
            intent_decision=intent_decision,
        )
        if orchestration_plan is not None:
            _log_orchestrator_trace(
                self.observability,
                conversation=conversation,
                trace_id=trace_id,
                mode=selected_mode,
                orchestration_plan=orchestration_plan,
                stream=True,
            )

        if not got_delta and not assembled:
            graph_reason = f"{selected_mode}_no_usable_text"
            used_direct_fallback = True
            llm_path = f"{selected_mode}+direct_fallback"
            fast_model, fast_timeout, fast_base_url, fast_api_key = _chat_fast_config()
            for event_type, content, final_state in stream_assistant_message_direct(
                langchain_messages,
                model=fast_model,
                timeout_seconds=fast_timeout,
                base_url=fast_base_url,
                api_key=fast_api_key,
            ):
                if event_type == "delta" and content:
                    got_delta = True
                    delta_count += 1
                    if first_delta_ms is None:
                        first_delta_ms = int((time.perf_counter() - request_start) * 1000)
                    assembled += content
                    server_ts_ms = int(time.time() * 1000)
                    yield f"data: {json.dumps({'type': 'delta', 'content': content, 'server_ts_ms': server_ts_ms}, ensure_ascii=False)}\n\n"
                elif event_type == "final" and content and content != EMPTY_ASSISTANT_REPLY:
                    assembled = content
                    if isinstance(final_state, dict):
                        stream_metrics = final_state.get("stream_metrics")

        assembled = _normalize_empty_knowledge_reply(assembled)
        if not assembled:
            assembled = "已收到你的消息，但当前没有生成文本回复。"

        updated_messages = [*history, {"role": "user", "content": payload.content}]

        final_ai_message = None
        if stream_final_state:
            final_ai_message = next((msg for msg in reversed(stream_final_state) if isinstance(msg, AIMessage)), None)

        if final_ai_message is not None:
            final_payload = serialize_message(final_ai_message)
            if stream_sources:
                final_payload["sources"] = stream_sources
            updated_messages.append(final_payload)
        else:
            assistant_payload = {"role": "assistant", "content": assembled}
            if stream_sources:
                assistant_payload["sources"] = stream_sources
            updated_messages.append(assistant_payload)

        memory_writeback_mode = _resolve_memory_writeback_mode()
        source_message_id = _build_source_message_id(
            conversation_id=conversation.id,
            user_message=payload.content,
            assistant_message=assembled,
        )

        try:
            if memory_writeback_mode == "async":
                _persist_conversation_messages(
                    self.db,
                    conversation,
                    updated_messages,
                    requery=True,
                    refresh=False,
                )
                _enqueue_memory_writeback_task(
                    conversation=conversation,
                    trace_id=trace_id,
                    user_message=payload.content,
                    assistant_message=assembled,
                )
            else:
                _write_long_term_memories_transactional(
                    db=self.db,
                    conversation=conversation,
                    trace_id=trace_id,
                    user_message=payload.content,
                    assistant_message=assembled,
                    source_message_id=source_message_id,
                )
                _persist_conversation_messages(
                    self.db,
                    conversation,
                    updated_messages,
                    requery=True,
                    refresh=False,
                )
        except Exception as exc:
            self.db.rollback()
            logger.warning("stream memory transactional persist failed: %s", exc)
            raise RuntimeError("流式会话持久化失败，请稍后重试") from exc

        # 降低在线请求尾部抖动：stream 路径默认关闭响应后 prefetch 调度。
        if (
            bool(getattr(settings, "memory_stream_prefetch_after_response_enabled", False))
            and not stream_use_long_term
            and bool(getattr(settings, "memory_long_term_prefetch_enabled", True))
        ):
            try:
                get_memory_service().prefetch_long_term_memories(
                    user_id=conversation.user_id,
                    agent_id=conversation.agent_id,
                    query=payload.content,
                    top_k=int(getattr(settings, "memory_long_term_top_k", 5)),
                )
            except Exception as exc:
                logger.warning("memory prefetch schedule failed: %s", exc)

        total_ms = int((time.perf_counter() - request_start) * 1000)
        unified_delta_count = delta_count
        unified_first_delta_ms = first_delta_ms
        unified_total_ms = total_ms
        unified_fallback = used_direct_fallback
        unified_raw_event_count = None
        unified_event_count = None
        unified_end_state = None
        unified_fallback_reason = None

        if isinstance(stream_metrics, dict):
            unified_delta_count = int(stream_metrics.get("delta_text_count", unified_delta_count) or unified_delta_count)
            unified_first_delta_ms = stream_metrics.get("first_delta_ms", unified_first_delta_ms)
            unified_total_ms = int(stream_metrics.get("total_ms", unified_total_ms) or unified_total_ms)
            unified_fallback = bool(stream_metrics.get("fallback_triggered", unified_fallback))
            unified_raw_event_count = stream_metrics.get("raw_event_count")
            unified_event_count = stream_metrics.get("unified_event_count")
            unified_end_state = stream_metrics.get("end_state")
            unified_fallback_reason = stream_metrics.get("fallback_reason")

        retrieval_latency_ms = None
        if isinstance(stream_metrics, dict):
            retrieval_latency_ms = stream_metrics.get("retrieval_latency_ms")

        telemetry_path = normalize_mode_for_telemetry(llm_path)

        logger.info(
            "[stream-summary] trace_id=%s path=%s graph_reason=%s direct_fallback=%s memory_writeback_mode=%s history_len=%s input_len=%s delta_count=%s first_delta_ms=%s total_ms=%s output_len=%s raw_event_count=%s unified_event_count=%s end_state=%s fallback_reason=%s context_budget=%s",
            trace_id,
            telemetry_path,
            graph_reason,
            unified_fallback,
            memory_writeback_mode,
            len(history),
            len(payload.content or ""),
            unified_delta_count,
            unified_first_delta_ms,
            unified_total_ms,
            len(assembled),
            unified_raw_event_count,
            unified_event_count,
            unified_end_state,
            unified_fallback_reason,
            context_bundle.get("budget", {}),
        )

        _log_post_response_events(
            self.observability,
            conversation=conversation,
            trace_id=trace_id,
            source="conversation_stream",
            message_length=len(payload.content),
            mode="stream",
            path=telemetry_path,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_total_ms=unified_total_ms,
            memory_writeback_mode=memory_writeback_mode,
        )

        yield f"data: {json.dumps({'type': 'done', 'assistant_message': assembled, 'trace_id': trace_id, 'sources': stream_sources}, ensure_ascii=False)}\n\n"
