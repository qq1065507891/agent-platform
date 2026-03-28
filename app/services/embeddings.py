from __future__ import annotations

import logging

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)


def _clean_env_value(raw: str | None) -> str:
    value = str(raw or "").strip()
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    if value.startswith("#"):
        return ""
    return value


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def get_embeddings() -> Embeddings:
    """Load embeddings using LLM_EMBEDDING/LLM_EMBEDDING_MODEL config."""
    raw_model = str(settings.llm_embedding or settings.llm_embedding_model or "")
    raw_base_url = str(settings.llm_embedding_base_url or "")
    raw_api_key = str(settings.llm_embedding_api_key or "")

    embedding_model = _clean_env_value(raw_model)
    base_url = _clean_env_value(raw_base_url)
    api_key = _clean_env_value(raw_api_key)

    logger.info(
        "[embedding-config-raw] base_url=%s model=%s api_key=%s",
        raw_base_url,
        raw_model,
        _mask_secret(raw_api_key),
    )
    logger.info(
        "[embedding-config-clean] base_url=%s model=%s api_key=%s api_key_present=%s",
        base_url,
        embedding_model,
        _mask_secret(api_key),
        bool(api_key),
    )

    return OpenAIEmbeddings(
        base_url=base_url,
        api_key=api_key,
        model=embedding_model,
        request_timeout=settings.llm_embedding_timeout_seconds,
        tiktoken_enabled=False,
    )
