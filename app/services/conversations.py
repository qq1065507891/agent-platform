from __future__ import annotations

from collections.abc import Iterator
import json
import time

from langchain_core.messages import SystemMessage
from sqlalchemy.orm import Session

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
    build_agent_graph,
    ensure_user_message,
    extract_assistant_message,
    stream_assistant_message,
    stream_assistant_message_direct,
    to_langchain_messages,
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

    def _prepare_messages(self, conversation: Conversation, content: str) -> tuple[list[dict], list]:
        history = conversation.messages or []
        langchain_messages = to_langchain_messages(history)
        if not history:
            agent = self.db.query(Agent).filter(Agent.id == conversation.agent_id).first()
            prompt_template = (agent.prompt_template or "").strip() if agent else ""
            if prompt_template:
                langchain_messages = [SystemMessage(content=prompt_template), *langchain_messages]
        langchain_messages = ensure_user_message(langchain_messages, content)
        return history, langchain_messages

    def add_message(self, conversation: Conversation, payload: MessageCreate) -> dict[str, str]:
        trace_id = get_trace_id() or generate_trace_id()
        history, langchain_messages = self._prepare_messages(conversation, payload.content)
        set_agent_id(conversation.agent_id)
        set_conversation_id(conversation.id)

        graph = build_agent_graph(agent_id=conversation.agent_id)
        result = graph.invoke({"messages": langchain_messages})
        final_messages = result.get("messages", langchain_messages)
        assistant_message = extract_assistant_message(final_messages)

        updated_messages = [*history, {"role": "user", "content": payload.content}]
        updated_messages.append({"role": "assistant", "content": assistant_message})
        conversation.messages = updated_messages
        self.db.commit()
        self.db.refresh(conversation)

        self.observability.log_event(
            event_type="conversation_message_sent",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={
                "trace_id": trace_id,
                "message_length": len(payload.content),
                "mode": "sync",
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
        trace_id = get_trace_id() or generate_trace_id()
        history, langchain_messages = self._prepare_messages(conversation, payload.content)
        set_agent_id(conversation.agent_id)
        set_conversation_id(conversation.id)

        graph = build_agent_graph(agent_id=conversation.agent_id)

        assembled = ""
        got_delta = False

        # 优先走 graph 流，保留 tools / RAG 能力。
        for event_type, content, _final_state in stream_assistant_message(graph, langchain_messages):
            if event_type == "delta" and content:
                got_delta = True
                assembled += content
                server_ts_ms = int(time.time() * 1000)
                yield f"data: {json.dumps({'type': 'delta', 'content': content, 'server_ts_ms': server_ts_ms}, ensure_ascii=False)}\n\n"
            elif event_type == "final" and content:
                assembled = content

        # graph 没有产生真实 token 流时，降级为直接 LLM 流式（尽量满足低延迟显示）。
        if not got_delta:
            assembled = ""
            for event_type, content, _ in stream_assistant_message_direct(langchain_messages):
                if event_type == "delta" and content:
                    assembled += content
                    server_ts_ms = int(time.time() * 1000)
                    yield f"data: {json.dumps({'type': 'delta', 'content': content, 'server_ts_ms': server_ts_ms}, ensure_ascii=False)}\n\n"
                elif event_type == "final" and content:
                    assembled = content

        if not assembled:
            assembled = "已收到你的消息，但当前没有生成文本回复。"

        updated_messages = [*history, {"role": "user", "content": payload.content}]
        updated_messages.append({"role": "assistant", "content": assembled})

        db_conversation = self.db.query(Conversation).filter(Conversation.id == conversation.id).first()
        if db_conversation:
            db_conversation.messages = updated_messages
            self.db.commit()

        self.observability.log_event(
            event_type="conversation_message_sent",
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            conversation_id=conversation.id,
            metadata={
                "trace_id": trace_id,
                "message_length": len(payload.content),
                "mode": "stream",
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
