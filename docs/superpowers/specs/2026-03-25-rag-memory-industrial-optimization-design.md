# RAG + Memory 工业级一体化优化方案（Superpowers Design）

日期：2026-03-25  
作者：AI Assistant（with superpowers brainstorming）

## 1. 背景与目标

当前系统已具备可用的 RAG 与 Agent 编排能力，但在工业化场景下仍存在三类核心挑战：

1. **质量上限不足**：召回与重排能力偏基础，复杂问题命中率波动大。  
2. **一致性策略不统一**：stream/sync 路径与 memory/RAG 落库策略存在分歧。  
3. **可运维性不足**：缺少端到端可追溯与发布门禁，难以稳定迭代。

本方案目标：

- 建立 **RAG + Memory 一体化在线编排**，支持分级一致性策略。
- 建立 **Hybrid Retrieval + Rerank + Context Packing** 的工业检索链路。
- 建立 **可观测、可审计、可回放** 的稳定运行体系。
- 以阶段化交付方式在质量、时延、成本之间取得可控平衡。

## 2. 范围与非目标

### 2.1 本期范围（P0/P1）

- 在线编排统一（query planning / retrieval / ranking / generation / persist）
- 分级一致性（Tier A 强一致 / Tier B 异步一致）
- 知识与记忆统一检索（dense + sparse + memory）
- 基础评测体系与发布门禁

### 2.2 非目标

- 本期不做全自动知识图谱构建与复杂推理链。
- 本期不引入跨地域多活一致性事务。
- 本期不强制替换现有所有组件，实现“最小侵入演进”。

## 3. 方案对比与决策

## 3.1 方案 A：检索中台先行（RAG-first）

- 优点：质量提升快，用户感知明显。
- 缺点：一致性与持久化语义容易延后，风险后置。

## 3.2 方案 B：事务中台先行（Memory-first）

- 优点：数据治理和一致性稳。
- 缺点：短期回答质量提升感知弱。

## 3.3 方案 C：双轨并进（推荐）

- 在线链路：统一会话编排与一致性策略。
- 检索链路：同步上线 hybrid + rerank 最小闭环。
- 离线链路：同步建设评测与门禁。

**决策**：采用方案 C（双轨并进）。

## 4. 目标架构（P0）

整体分为四层：

1. **在线请求编排层（Orchestrator）**  
   负责策略决策、调用检索、调用模型、触发持久化。

2. **统一检索层（Unified Retrieval）**  
   并行召回（knowledge dense / sparse / memory），融合与重排后输出证据。

3. **一体化存储层（Data Plane）**  
   PostgreSQL + pgvector，支撑知识与记忆结构化存储与向量检索。

4. **观测与评测层（Observability + Evaluation）**  
   记录检索路径、证据、降级、落库状态，提供发布门禁依据。

## 5. 模块边界与接口契约

### 5.1 模块边界

1. **Query Planner**：query rewrite、意图分类、检索策略选择。  
2. **Retriever Hub**：并行召回（dense/sparse/memory）。  
3. **Ranker**：融合、重排、去重、多样性控制。  
4. **Context Packer**：token 预算裁剪与证据打包。  
5. **Generation Orchestrator**：流式/非流式生成与引证拼装。  
6. **Persistence Coordinator**：按 tier 执行强一致或异步一致持久化。

### 5.2 推荐接口（抽象）

- `plan(query, context) -> retrieval_plan`
- `retrieve(retrieval_plan) -> candidates[]`
- `rank(query, candidates) -> evidence[]`
- `pack(evidence, budget) -> prompt_context`
- `generate(prompt_context) -> answer + citations`
- `persist(answer_event, tier) -> persist_receipt`

### 5.3 证据与引证统一结构

每条 citation 至少包含：

- `source_type`（knowledge/memory）
- `source_id`（doc_id/memory_id）
- `locator`（page/chunk_idx/section）
- `snippet_hash`（可追溯、防篡改）

## 6. 分级一致性策略（核心）

### 6.1 Tier A（核心会话，强一致优先）

- `done` 之前必须完成消息与记忆关键写入。
- 持久化失败时不得返回“成功 done”，应返回可恢复失败态。

### 6.2 Tier B（普通会话，时延优先）

- 允许先响应后异步落库。
- 必须写入重试队列与审计日志，保证最终一致。

### 6.3 策略切换依据

- 按 agent 配置、会话等级、业务标签、或请求头策略。
- 需支持灰度切换与回滚。

## 7. 请求状态机与降级机制

标准状态机：

`RECEIVED -> PLANNED -> RETRIEVED -> RANKED -> GENERATED -> PERSISTED -> DONE`

异常分支：

- `RETRIEVE_TIMEOUT`：降级为 sparse-only 或 memory-only
- `RERANK_TIMEOUT`：使用融合分直接截断
- `PERSIST_FAIL`：
  - Tier A：返回可恢复失败
  - Tier B：标记 `deferred_persist` 并重试

**强规则**：知识问答场景禁止“无证据强答”。证据不足时返回保守说明与补充建议。

## 8. 检索链路工业化设计

## 8.1 多路召回

- Dense（向量召回）
- Sparse（关键词/BM25/FTS）
- Memory（长期记忆向量召回）

## 8.2 融合与重排

- 融合：RRF 或可配置加权融合
- 重排：cross-encoder（初期）/LLM reranker（可选）
- 去重：同源 chunk 合并、近似重复剔除

## 8.3 上下文打包

- 预算优先级：证据 > 必要对话历史 > 辅助上下文
- 规则：避免单文档霸占上下文，保证证据来源多样性

## 9. 数据模型与治理（建议）

知识相关：

- `knowledge_docs`
- `knowledge_chunks`
- `knowledge_embeddings`

记忆相关：

- `memory_records`
- `memory_embeddings`
- `memory_write_audit`

观测相关：

- `retrieval_trace`
- `answer_trace`

治理策略：

- 上传幂等（`agent_id + content_hash`）
- 文档版本（active/inactive/version）
- 元数据完整性（page/section/chunk_idx/type/hash）

## 10. 可观测与发布门禁

### 10.1 核心指标

- 质量：Recall@20、nDCG@10、Groundedness、Hallucination Rate
- 性能：TTFT P50/P95、端到端 P95
- 稳定性：检索超时率、持久化失败率、降级触发率
- 成本：每千请求模型成本、重排成本、索引成本

### 10.2 发布门禁（建议）

新策略上线必须满足：

- Recall@20 不低于 baseline
- Groundedness 提升（目标 +10% 起）
- Hallucination Rate 下降（目标 -20% 起）
- P95 时延增幅控制在阈值内（建议 < 20%）

## 11. 实施路线图（12 周）

### Phase 0（第 1-2 周）：基础治理

- 参数中心化与策略开关
- metadata 补齐与上传幂等
- 统一观测 schema

### Phase 1（第 3-5 周）：检索质量闭环

- hybrid 检索
- rerank 与 context packing
- 标准化 citation 输出

### Phase 2（第 6-8 周）：一致性与可靠性

- Tier A/B 一致性策略落地
- stream/sync 持久化语义统一
- 重试与回放机制

### Phase 3（第 9-10 周）：评测与灰度

- 离线评测集构建（>=300 条）
- A/B 灰度（10% -> 30% -> 100%）
- 达门禁后全量切换

### Phase 4（第 11-12 周）：运维与成本优化

- 动态策略路由
- 成本看板与限流
- 索引与缓存优化

## 12. 风险与缓解

1. **时延上升风险**（hybrid + rerank 增加开销）  
   缓解：超时切断、分级策略、轻量模型优先。

2. **策略复杂度上升**（多开关导致行为难解释）  
   缓解：配置分层、默认策略收敛、变更审计。

3. **评测覆盖不足**（线上收益不可复现）  
   缓解：建立标准评测集与发布门禁硬约束。

4. **异步补写积压**（Tier B 风险）  
   缓解：队列监控、死信处理、回放工具化。

## 13. 验收标准（Definition of Done）

- 架构：统一编排链路与接口完成，stream/sync 语义一致。
- 质量：相对 baseline 达到门禁指标。
- 稳定性：Tier A 不出现“done 先于关键持久化”。
- 可运维：单次回答可追溯证据链、降级路径、持久化状态。
- 可发布：具备灰度、回滚、审计能力。

## 14. 最终决策记录

- 优化路径：**双轨并进（方案 C）**
- 一致性策略：**分级一致性（Tier A 强一致 / Tier B 异步一致）**
- 检索策略：**Hybrid + Rerank + Context Packing**
- 交付方式：**12 周阶段化演进 + 指标门禁驱动上线**
