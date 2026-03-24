from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "agent_platform"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    log_level_dev: str = "DEBUG"
    log_level_staging: str = "INFO"
    log_level_prod: str = "INFO"
    log_info_sample_rate: float = 1.0
    log_max_field_length: int = 2000
    log_max_collection_items: int = 50

    llm_gateway_url: str = ""
    llm_api_key: str = "EMPTY"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 45.0
    llm_fallback_timeout_seconds: float = 20.0

    # Embedding endpoint can be configured independently (e.g. ModelScope OpenAI-compatible API)
    llm_embedding_base_url: str = ""
    llm_embedding_api_key: str = ""
    llm_embedding: str = ""
    llm_embedding_model: str = "text-embedding-3-small"
    llm_embedding_timeout_seconds: float = 12.0

    chroma_url: str = ""
    chroma_persist_path: str = "./chroma"

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_accept_content: list[str] = ["json"]
    celery_task_time_limit: int = 30

    skill_sandbox_mode: str = "isolated"
    skill_sandbox_timeout_seconds: int = 10

    graph_cache_ttl_seconds: int = 120
    tools_cache_ttl_seconds: int = 120
    stream_force_graph: bool = True
    max_history_turns: int = 10

    memory_enabled: bool = True
    memory_short_term_max_turns: int = 10
    memory_long_term_top_k: int = 5
    # Stream path optimization: skip vector recall before first token by default.
    memory_stream_use_long_term: bool = False
    # Two-stage enhancement: allow async prefetch for next-turn context quality.
    memory_long_term_prefetch_enabled: bool = True
    memory_long_term_prefetch_ttl_seconds: int = 120
    memory_summary_enabled: bool = True
    memory_summary_max_chars: int = 1500
    memory_prompt_summary_max_chars: int = 1000
    memory_prompt_short_context_max_chars: int = 1200
    memory_prompt_long_memories_max_items: int = 5
    memory_prompt_long_memory_item_max_chars: int = 220
    memory_writeback_enabled: bool = True
    memory_writeback_async_enabled: bool = True
    memory_writeback_similarity_threshold: float = 0.92
    memory_writeback_min_confidence: float = 0.7
    memory_extraction_use_llm: bool = True
    memory_extraction_model: str = ""
    memory_extraction_timeout_seconds: float = 15.0
    memory_extraction_json_retry_count: int = 1
    memory_event_max_retries: int = 5
    memory_default_ttl_seconds: int = 0
    memory_sla_retrieval_p95_ms: int = 800
    memory_sla_retrieval_p99_ms: int = 800
    memory_sla_ingest_5s_rate: float = 0.95
    memory_sla_ingest_10s_rate: float = 0.99
    memory_sla_writeback_success_rate: float = 0.98
    memory_sla_trace_coverage_rate: float = 0.98
    memory_eval_sample_size: int = 200

    agent_mode_selector_enabled: bool = True
    agent_mode_tool_threshold: int = 5
    agent_mode_complexity_threshold: float = 0.6
    agent_mode_force: str = ""
    agent_react_max_steps: int = 6
    agent_react_decision_log_enabled: bool = True

    router_llm_gateway_url: str = ""
    router_llm_api_key: str = ""
    router_llm_model: str = ""
    router_llm_timeout_seconds: float = 8.0
    router_worker_timeout_seconds: float = 3.0
    router_worker_max_workers: int = 2

    agent_mode_selector_enabled: bool = True
    agent_mode_tool_threshold: int = 5
    agent_mode_complexity_threshold: float = 0.6
    agent_mode_force: str = ""

    agent_mode_selector_enabled: bool = True
    agent_mode_tool_threshold: int = 5
    agent_mode_complexity_threshold: float = 0.6
    agent_mode_force: str = ""

    router_llm_base_url: str = ""
    router_llm_api_key: str = ""
    router_llm_model: str = ""
    router_llm_timeout_seconds: float = 8.0

    orchestrator_v2_enabled: bool = True

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
