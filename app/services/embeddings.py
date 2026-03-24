from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings


def get_embeddings() -> Embeddings:
    """Load embeddings using LLM_EMBEDDING/LLM_EMBEDDING_MODEL config."""
    embedding_model = settings.llm_embedding or settings.llm_embedding_model
    return OpenAIEmbeddings(
        base_url=settings.llm_embedding_base_url,
        api_key=settings.llm_embedding_api_key,
        model=embedding_model,
        request_timeout=settings.llm_embedding_timeout_seconds,
        tiktoken_enabled=False,
    )
