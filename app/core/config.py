from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_gateway_url: str = ""
    llm_api_key: str = "EMPTY"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 45.0

    # Embedding endpoint can be configured independently (e.g. ModelScope OpenAI-compatible API)
    llm_embedding_base_url: str = ""
    llm_embedding_api_key: str = ""
    llm_embedding_model: str = "text-embedding-3-small"
    llm_embedding_timeout_seconds: float = 12.0

    chroma_url: str = ""
    chroma_persist_path: str = "./chroma"

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
