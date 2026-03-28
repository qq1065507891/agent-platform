from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    # ===== 应用基础配置 =====
    app_name: str = "agent_platform"  # 应用名称，用于日志/监控标识
    app_env: str = "dev"  # 运行环境（dev/staging/prod）
    app_host: str = "0.0.0.0"  # 服务监听地址
    app_port: int = 8000  # 服务监听端口
    log_level: str = "INFO"  # 默认日志级别
    log_level_dev: str = "DEBUG"  # 开发环境日志级别
    log_level_staging: str = "INFO"  # 预发环境日志级别
    log_level_prod: str = "INFO"  # 生产环境日志级别
    log_info_sample_rate: float = 1.0  # INFO 日志采样率（0~1）
    log_max_field_length: int = 2000  # 单个日志字段最大长度
    log_max_collection_items: int = 50  # 日志中集合字段最多保留项数

    # ===== 主对话 LLM 配置 =====
    llm_gateway_url: str = ""  # LLM 网关地址（OpenAI 兼容）
    llm_api_key: str = ""  # LLM API Key
    llm_model: str = ""  # 默认对话模型
    llm_timeout_seconds: float = 45.0  # 主请求超时时间（秒）
    llm_chat_fast_base_url: str = ""  # CHAT 旁路专用网关（为空则回落 llm_gateway_url）
    llm_chat_fast_api_key: str = ""  # CHAT 旁路专用 API Key（为空则回落 llm_api_key）
    llm_chat_fast_model: str = ""  # CHAT 旁路专用快模型（为空则回落 llm_model）
    llm_chat_fast_timeout_seconds: float = 12.0  # CHAT 旁路专用超时（秒）
    llm_fallback_timeout_seconds: float = 20.0  # 降级/兜底请求超时（秒）
    stream_protocol_version: str = "v1"  # 流式协议版本
    stream_meta_event_enabled: bool = True  # 是否输出流式 meta 事件
    stream_fallback_on_empty_enabled: bool = True  # 流式无文本时是否启用兜底
    stream_debug_raw_event_limit: int = 8  # 流式调试时保留原始事件数量上限
    stream_graph_invoke_fallback_enabled: bool = False  # 是否启用 graph.invoke 兜底
    stream_graph_invoke_fallback_timeout_seconds: float = 1.2  # graph.invoke 兜底超时（秒）

    # ===== Embedding 配置（可独立于主 LLM） =====
    llm_embedding_base_url: str = ""  # Embedding 服务地址（OpenAI 兼容）
    llm_embedding_api_key: str = ""  # Embedding API Key
    llm_embedding: str = ""  # 兼容旧字段（预留）
    llm_embedding_model: str = "text-embedding-3-small"  # Embedding 模型名
    llm_embedding_timeout_seconds: float = 12.0  # Embedding 请求超时（秒）
    llm_embedding_dimensions: int = 1024  # 向量维度

    # ===== Chroma 向量库配置 =====
    chroma_url: str = ""  # 远程 Chroma 地址；为空则使用本地持久化
    chroma_persist_path: str = "./chroma"  # 本地 Chroma 数据目录

    # ===== RAG 检索配置 =====
    rag_chunk_size: int = 800  # 默认切片长度
    rag_chunk_overlap: int = 120  # 默认切片重叠长度
    rag_pdf_chunk_size: int = 1000  # PDF 切片长度
    rag_pdf_chunk_overlap: int = 160  # PDF 切片重叠长度
    rag_docx_chunk_size: int = 900  # DOC/DOCX 切片长度
    rag_docx_chunk_overlap: int = 140  # DOC/DOCX 切片重叠长度
    rag_recall_k: int = 24  # 初始召回数量
    rag_final_k: int = 5  # 最终用于回答的文档数量
    rag_sparse_k: int = 5  # 稀疏检索召回数量
    rag_search_type: str = "mmr"  # 检索类型（如 mmr/similarity）
    rag_mmr_fetch_k: int = 5  # MMR 候选池大小
    rag_mmr_lambda_mult: float = 0.5  # MMR 多样性权重
    rag_similarity_min_score: float = 0.68  # 最低相似度阈值
    rag_threshold_diversify_enabled: bool = True  # 阈值检索后是否做多样化
    rag_hybrid_enabled: bool = True  # 是否启用混合检索
    rag_rerank_enabled: bool = True   # 是否启用重排
    rag_rerank_timeout_ms: int = 300  # 重排超时（毫秒）
    rag_context_budget_tokens: int = 2200  # RAG 注入上下文 token 预算
    rag_ingest_dedup_enabled: bool = True  # 入库时是否按内容哈希去重

    # ===== Redis/Celery 配置 =====
    redis_url: str = "redis://127.0.0.1:6379/0"  # Redis 主库地址
    celery_broker_url: str = "redis://127.0.0.1:6379/1"  # Celery Broker
    celery_result_backend: str = "redis://127.0.0.1:6379/2"  # Celery 结果后端
    celery_task_serializer: str = "json"  # Celery 任务序列化格式
    celery_result_serializer: str = "json"  # Celery 结果序列化格式
    celery_accept_content: list[str] = ["json"]  # Celery 接受的消息格式
    celery_task_time_limit: int = 30  # Celery 任务硬超时（秒）

    # ===== 技能沙箱配置 =====
    skill_sandbox_mode: str = "isolated"  # 技能执行沙箱模式
    skill_sandbox_timeout_seconds: int = 10  # 技能执行超时（秒）

    # ===== MCP 工具测试安全配置 =====
    mcp_test_rate_limit_seconds: int = 10  # 同一工具测试最小间隔（秒）
    mcp_stdio_test_enabled: bool = False  # 是否允许执行 stdio 测试命令

    # ===== 图编排与工具缓存配置 =====
    graph_cache_ttl_seconds: int = 120  # Agent 图缓存 TTL（秒）
    tools_cache_ttl_seconds: int = 120  # 工具列表缓存 TTL（秒）
    stream_force_graph: bool = True  # 流式是否强制走 graph 路径
    max_history_turns: int = 10  # 注入模型的最大历史轮次

    # ===== 记忆系统配置 =====
    memory_enabled: bool = True  # 是否启用记忆系统
    memory_short_term_max_turns: int = 10  # 短期记忆窗口轮次
    memory_long_term_top_k: int = 5  # 长期记忆召回数量
    # Stream 路径优化：默认首 token 前不做长期记忆向量召回
    memory_stream_use_long_term: bool = False  # 流式路径是否启用长期记忆召回
    # 两阶段增强：响应后异步预取下轮长期记忆
    memory_long_term_prefetch_enabled: bool = True  # 是否启用长期记忆预取
    memory_long_term_prefetch_ttl_seconds: int = 120  # 预取缓存 TTL（秒）
    memory_stream_prefetch_after_response_enabled: bool = False  # 流式完成后是否触发预取
    memory_summary_enabled: bool = True  # 是否启用会话摘要
    memory_summary_max_chars: int = 1500  # 摘要最大字符数
    memory_prompt_summary_max_chars: int = 1000  # Prompt 中摘要截断上限
    memory_prompt_short_context_max_chars: int = 1200  # Prompt 中短期上下文截断上限
    memory_prompt_long_memories_max_items: int = 5  # Prompt 中长期记忆最多条数
    memory_prompt_long_memory_item_max_chars: int = 220  # 单条长期记忆截断上限
    memory_writeback_enabled: bool = True  # 是否启用记忆回写
    memory_writeback_async_enabled: bool = True  # 是否异步回写记忆
    memory_transactional_write_enabled: bool = True  # 是否事务性回写记忆
    memory_stream_force_async_writeback: bool = True  # 流式路径是否强制异步回写，降低 done 尾延迟
    memory_backend: str = "pgvector"  # 记忆存储后端（pgvector/chroma 等）
    memory_writeback_similarity_threshold: float = 0.92  # 回写去重相似度阈值
    memory_writeback_min_confidence: float = 0.7  # 回写候选最小置信度
    memory_extraction_use_llm: bool = True  # 记忆抽取是否使用 LLM
    memory_extraction_base_url: str = ""  # 记忆抽取专用网关（为空则跟随 llm_gateway_url）
    memory_extraction_api_key: str = ""  # 记忆抽取专用 API Key（为空则跟随 llm_api_key）
    memory_extraction_model: str = ""  # 记忆抽取模型（为空则跟随 llm_model）
    memory_extraction_timeout_seconds: float = 15.0  # 记忆抽取超时（秒）
    memory_extraction_json_retry_count: int = 1  # JSON 解析失败重试次数
    memory_event_max_retries: int = 5  # 记忆事件最大重试次数
    memory_default_ttl_seconds: int = 0  # 记忆默认 TTL（0 表示不过期）
    memory_sla_retrieval_p95_ms: int = 800  # 记忆检索 P95 SLA（毫秒）
    memory_sla_retrieval_p99_ms: int = 800  # 记忆检索 P99 SLA（毫秒）
    memory_vector_recall_enabled: bool = True  # 是否启用向量召回
    memory_vector_recall_timeout_seconds: float = 1.2  # 向量召回超时（秒）
    memory_sla_ingest_5s_rate: float = 0.95  # 入库 5 秒内完成率 SLA
    memory_sla_ingest_10s_rate: float = 0.99  # 入库 10 秒内完成率 SLA
    memory_sla_writeback_success_rate: float = 0.98  # 回写成功率 SLA
    memory_sla_trace_coverage_rate: float = 0.98  # 观测 trace 覆盖率 SLA
    memory_eval_sample_size: int = 200  # 记忆评估采样量

    # ===== Agent 模式选择配置 =====
    agent_mode_selector_enabled: bool = True  # 是否启用模式选择器
    agent_mode_tool_threshold: int = 5  # 工具数量阈值（影响模式判定）
    agent_mode_complexity_threshold: float = 0.6  # 问题复杂度阈值
    agent_mode_force: str = ""  # 强制指定模式（为空表示自动）
    agent_react_max_steps: int = 6  # ReAct 最大推理步数
    agent_react_decision_log_enabled: bool = True  # 是否记录 ReAct 决策日志

    # ===== Router-Worker 配置（网关字段） =====
    router_llm_gateway_url: str = ""  # Router LLM 网关地址（兼容旧命名）
    router_llm_api_key: str = ""  # Router LLM API Key
    router_llm_model: str = ""  # Router LLM 模型名
    router_llm_timeout_seconds: float = 8.0  # Router LLM 超时（秒）
    router_worker_timeout_seconds: float = 3.0  # Worker 总超时（秒）
    router_worker_max_workers: int = 2  # 并行 worker 数量上限

    # ===== Router-Worker 配置（base_url 字段） =====
    # 说明：同一字段在类体后续重复定义时，Python 以后者为准。
    # 下方字段保留是为了兼容已有环境变量命名。
    router_llm_base_url: str = ""  # Router LLM 基础地址（优先实际被使用）
    router_llm_api_key: str = ""  # Router LLM API Key（重复定义，值以最后一次为准）
    router_llm_model: str = ""  # Router LLM 模型（重复定义，值以最后一次为准）
    router_llm_timeout_seconds: float = 8.0  # Router LLM 超时（重复定义）

    # ===== Router-Worker 聚合模型配置（可独立于 Router LLM） =====
    router_worker_base_url: str = ""  # Router-Worker 聚合专用网关（为空则回落 llm_gateway_url）
    router_worker_api_key: str = ""  # Router-Worker 聚合专用 API Key（为空则回落 llm_api_key）
    router_worker_model: str = ""  # Router-Worker 聚合专用模型（为空则回落 llm_model）

    # ===== 编排版本开关 =====
    orchestrator_v2_enabled: bool = True  # 是否启用编排 V2



@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
