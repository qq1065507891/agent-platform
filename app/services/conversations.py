from __future__ import annotations

from collections.abc import Iterator
import hashlib
import json
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
    extract_assistant_message,
    get_or_build_agent_graph,
    serialize_message,
    stream_assistant_message,
    stream_assistant_message_direct,
    to_langchain_messages,
)
from app.services.agent.mode_selector import select_agent_mode
from app.services.agent.router_worker import invoke_router_worker, stream_router_worker
from app.services.memory.service import get_memory_service
from app.tasks.memory_tasks import memory_writeback_task

logger = logging.getLogger(__name__)

MEMORY_VERSION = 1


def _build_source_message_id(*, conversation_id: str, user_message: str, assistant_message: str) -> str:
    payload = f"{conversation_id}|{user_message}|{assistant_message}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:36]


def _should_prefer_direct_stream(content: str) -> bool:
    # 默认强制 graph 主路径，direct 仅作 fallback。
    if getattr(settings, "stream_force_graph", True):
        return False

    text = (content or "").strip().lower()
    if not text:
        return True

    graph_markers = {
        "知识库", "rag", "检索", "查询", "文档", "内部资料", "tool", "工具", "技能", "skill", "执行", "调用"
    }
    if any(marker in text for marker in graph_markers):
        return False

    return True


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


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.observability = ObservabilityService(db)

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
        mode_decision = select_agent_mode(
            user_query=payload.content,
            selected_tools=(agent.skills if agent else []),
        )
        self.observability.log_event(
            event_type="agent_mode_selected",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={
                "trace_id": trace_id,
                "mode": mode_decision.get("mode"),
                "reason": mode_decision.get("reason"),
                "features": mode_decision.get("features", {}),
            },
        )

        selected_mode = str(mode_decision.get("mode") or "react")
        retrieval_latency_ms = None
        if selected_mode == "router_worker":
            result = invoke_router_worker(
                agent_id=conversation.agent_id,
                messages=langchain_messages,
                context_bundle=_context_bundle,
                user_query=payload.content,
            )
            metrics = result.get("retrieval_metrics") if isinstance(result, dict) else None
            if isinstance(metrics, dict):
                retrieval_latency_ms = metrics.get("retrieval_latency_ms")
        else:
            graph = get_or_build_agent_graph(agent_id=conversation.agent_id)
            result = graph.invoke(
                {
                    "messages": langchain_messages,
                    "context_bundle": _context_bundle,
                    "user_query": payload.content,
                }
            )
        final_messages = result.get("messages", langchain_messages)
        assistant_message = extract_assistant_message(final_messages)

        updated_messages = [*history, {"role": "user", "content": payload.content}]
        final_ai_message = next((msg for msg in reversed(final_messages) if isinstance(msg, AIMessage)), None)
        if final_ai_message is not None:
            updated_messages.append(serialize_message(final_ai_message))
        else:
            updated_messages.append({"role": "assistant", "content": assistant_message})

        memory_transactional = bool(getattr(settings, "memory_transactional_write_enabled", True))
        memory_writeback_mode = (
            "transactional"
            if memory_transactional
            else ("async" if getattr(settings, "memory_writeback_async_enabled", True) else "sync")
        )
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
                conversation.messages = updated_messages
                self.db.commit()
                self.db.refresh(conversation)
                memory_writeback_task.delay(
                    user_id=conversation.user_id,
                    agent_id=conversation.agent_id,
                    conversation_id=conversation.id,
                    trace_id=trace_id,
                    user_message=payload.content,
                    assistant_message=assistant_message,
                )
            else:
                memory_service = get_memory_service()
                write_candidates = memory_service.extract_write_candidates(payload.content, assistant_message)
                accepted = memory_service.write_long_term_memories(
                    user_id=conversation.user_id,
                    agent_id=conversation.agent_id,
                    conversation_id=conversation.id,
                    trace_id=trace_id,
                    source_message_id=source_message_id,
                    candidates=write_candidates,
                    db=self.db,
                )
                accepted_count = len(accepted)
                conversation.messages = updated_messages
                self.db.commit()
                self.db.refresh(conversation)
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
        self.observability.log_event(
            event_type="conversation_message_sent",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={
                "trace_id": trace_id,
                "message_length": len(payload.content),
                "mode": "sync",
                "path": selected_mode,
                "retrieval_latency_ms": retrieval_latency_ms,
                "llm_total_ms": total_ms,
                "memory_writeback_mode": memory_writeback_mode,
            },
        )
        self.observability.log_event(
            event_type="agent_use",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={"trace_id": trace_id, "source": "conversation_message"},
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
        graph_reason = "ok"

        agent = self.db.query(Agent).filter(Agent.id == conversation.agent_id).first()
        mode_decision = select_agent_mode(
            user_query=payload.content,
            selected_tools=(agent.skills if agent else []),
        )
        self.observability.log_event(
            event_type="agent_mode_selected",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={
                "trace_id": trace_id,
                "mode": mode_decision.get("mode"),
                "reason": mode_decision.get("reason"),
                "features": mode_decision.get("features", {}),
            },
        )

        selected_mode = str(mode_decision.get("mode") or "react")
        llm_path = selected_mode
        graph = get_or_build_agent_graph(agent_id=conversation.agent_id)
        graph_input_state = {
            "messages": langchain_messages,
            "context_bundle": context_bundle,
            "user_query": payload.content,
        }
        try:
            stream_iter = (
                stream_router_worker(
                    agent_id=conversation.agent_id,
                    messages=langchain_messages,
                    context_bundle=context_bundle,
                    user_query=payload.content,
                )
                if selected_mode == "router_worker"
                else stream_assistant_message(graph, graph_input_state)
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
                    elif final_state:
                        stream_final_state = final_state
        except Exception as exc:
            graph_reason = f"graph_exception:{type(exc).__name__}"
            logger.warning("%s stream failed, fallback to direct: %s", selected_mode, exc)

        if not got_delta and not assembled:
            graph_reason = f"{selected_mode}_no_usable_text"
            used_direct_fallback = True
            llm_path = f"{selected_mode}+direct_fallback"
            for event_type, content, final_state in stream_assistant_message_direct(langchain_messages):
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

        if not assembled:
            assembled = "已收到你的消息，但当前没有生成文本回复。"

        updated_messages = [*history, {"role": "user", "content": payload.content}]

        final_ai_message = None
        if stream_final_state:
            final_ai_message = next((msg for msg in reversed(stream_final_state) if isinstance(msg, AIMessage)), None)

        if final_ai_message is not None:
            updated_messages.append(serialize_message(final_ai_message))
        else:
            updated_messages.append({"role": "assistant", "content": assembled})

        memory_transactional = bool(getattr(settings, "memory_transactional_write_enabled", True))
        memory_writeback_mode = (
            "transactional"
            if memory_transactional
            else ("async" if getattr(settings, "memory_writeback_async_enabled", True) else "sync")
        )
        source_message_id = _build_source_message_id(
            conversation_id=conversation.id,
            user_message=payload.content,
            assistant_message=assembled,
        )

        try:
            if memory_writeback_mode == "async":
                db_conversation = self.db.query(Conversation).filter(Conversation.id == conversation.id).first()
                if db_conversation:
                    db_conversation.messages = updated_messages
                    self.db.commit()
                memory_writeback_task.delay(
                    user_id=conversation.user_id,
                    agent_id=conversation.agent_id,
                    conversation_id=conversation.id,
                    trace_id=trace_id,
                    user_message=payload.content,
                    assistant_message=assembled,
                )
            else:
                memory_service = get_memory_service()
                write_candidates = memory_service.extract_write_candidates(payload.content, assembled)
                memory_service.write_long_term_memories(
                    user_id=conversation.user_id,
                    agent_id=conversation.agent_id,
                    conversation_id=conversation.id,
                    trace_id=trace_id,
                    source_message_id=source_message_id,
                    candidates=write_candidates,
                    db=self.db,
                )
                db_conversation = self.db.query(Conversation).filter(Conversation.id == conversation.id).first()
                if db_conversation:
                    db_conversation.messages = updated_messages
                    self.db.commit()
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

        logger.info(
            "[stream-summary] trace_id=%s path=%s graph_reason=%s direct_fallback=%s memory_writeback_mode=%s history_len=%s input_len=%s delta_count=%s first_delta_ms=%s total_ms=%s output_len=%s raw_event_count=%s unified_event_count=%s end_state=%s fallback_reason=%s context_budget=%s",
            trace_id,
            llm_path,
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

        self.observability.log_event(
            event_type="conversation_message_sent",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={
                "trace_id": trace_id,
                "message_length": len(payload.content),
                "mode": "stream",
                "path": llm_path,
                "retrieval_latency_ms": retrieval_latency_ms,
                "llm_total_ms": unified_total_ms,
                "memory_writeback_mode": memory_writeback_mode,
            },
        )
        self.observability.log_event(
            event_type="agent_use",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={"trace_id": trace_id, "source": "conversation_stream"},
        )

        yield f"data: {json.dumps({'type': 'done', 'assistant_message': assembled, 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
