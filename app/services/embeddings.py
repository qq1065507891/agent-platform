from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings


def get_embeddings() -> Embeddings:
    """Load embeddings strictly via LangChain embedding config."""
    return OpenAIEmbeddings(
        base_url=settings.llm_embedding_base_url,
        api_key=settings.llm_embedding_api_key,
        model=settings.llm_embedding_model,
        request_timeout=settings.llm_embedding_timeout_seconds,
        tiktoken_enabled=False,
    )
