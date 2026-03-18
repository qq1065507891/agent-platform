from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.conversation import Conversation
from app.schemas.conversation import ConversationCreate, MessageCreate
from app.services.agent.graph import (
    AgentState,
    build_agent_graph,
    ensure_user_message,
    extract_assistant_message,
    to_langchain_messages,
)
from langchain_core.messages import SystemMessage


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_conversation(self, payload: ConversationCreate, user_id: str) -> Conversation:
        agent = self.db.query(Agent).filter(Agent.id == payload.agent_id).first()
        if not agent:
            raise ValueError("智能体不存在")
        conversation = Conversation(
            agent_id=payload.agent_id,
            user_id=user_id,
            messages=[],
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def list_user_conversations(self, user_id: str, agent_id: str | None = None) -> list[Conversation]:
        query = self.db.query(Conversation).filter(Conversation.user_id == user_id)
        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)
        items = query.order_by(Conversation.created_at.desc()).all()
        return [item for item in items if item.messages]

    def add_message(self, conversation: Conversation, payload: MessageCreate) -> dict[str, str]:
        trace_id = f"t-{uuid4().hex[:12]}"
        history = conversation.messages or []

        langchain_messages = to_langchain_messages(history)
        if not history:
            agent = self.db.query(Agent).filter(Agent.id == conversation.agent_id).first()
            prompt_template = (agent.prompt_template or "").strip() if agent else ""
            if prompt_template:
                langchain_messages = [SystemMessage(content=prompt_template), *langchain_messages]
        langchain_messages = ensure_user_message(langchain_messages, payload.content)

        graph = build_agent_graph()
        result = graph.invoke({"messages": langchain_messages})
        final_messages = result.get("messages", langchain_messages)
        assistant_message = extract_assistant_message(final_messages)

        updated_messages = [*history, {"role": "user", "content": payload.content}]
        updated_messages.append({"role": "assistant", "content": assistant_message})
        conversation.messages = updated_messages
        self.db.commit()
        self.db.refresh(conversation)
        return {
            "assistant_message": assistant_message,
            "trace_id": trace_id,
        }
