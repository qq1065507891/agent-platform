# Memory System V3 重构设计（PostgreSQL + pgvector）

日期：2026-03-24  
作者：AI Assistant（with superpowers brainstorming）

## 1. 背景与目标

当前记忆系统存在以下典型问题：

- 写回链路在 `sync/stream` 两条路径上行为不一致，存在漂移风险。
- 记忆写入依赖异步任务时，容易出现“回答已返回但记忆未可靠落地”的窗口。
- 去重与幂等能力不足，重复写入、重试写入可能污染长期记忆。
- 召回与注入策略可观测性不足，难以定位“命中差/注入差/写回失败”的根因。

本次重构目标：

1. 使用 **PostgreSQL + pgvector** 作为统一记忆底座。
2. 建立 **关系数据 + 向量数据同事务提交** 的强一致写入链路。
3. 实现业务层 **Exactly-once 语义（基于幂等键）**。
4. 统一 `add_message` 与 `add_message_stream` 的记忆持久化行为。
5. 建立完整的可观测、告警、回放与验收体系。

## 2. 非目标

- 本期不引入跨系统分布式事务（只做单库事务一致性）。
- 本期不做“全自动遗忘策略”的复杂算法升级（仅保留基础衰减机制接口）。
- 本期不维持 Chroma 双写长期运行（迁移窗口后下线）。

## 3. 总体架构（V3）

将记忆系统拆分为三层：

### 3.1 Online 事务层（请求内）

职责：

- 消息落库
- 记忆候选抽取
- 幂等判定与 upsert
- embedding 写入 pgvector
- 提交后立即可检索

特性：

- 单个 PostgreSQL 事务完成 metadata + vector 的一致提交。

### 3.2 Query 检索层（只读）

职责：

- 短期上下文拼接
- 长期记忆 hybrid 召回
- rerank 与预算裁剪
- prompt 注入

特性：

- 纯读无副作用，低延迟，可独立优化。

### 3.3 Offline 维护层（异步增强）

职责：

- 质量重评分
- 记忆衰减/归档
- 聚合摘要
- 索引维护

特性：

- 仅做优化增强，不承担 correctness。

## 4. 数据模型设计

### 4.1 `memory_records`（主表）

建议字段：

- `id` uuid pk
- `user_id`, `agent_id`, `conversation_id`
- `memory_type`（如 profile/preference/fact/task/constraint）
- `content` text
- `content_norm` text（规范化内容）
- `idempotency_key` varchar unique
- `source_message_id`（触发来源）
- `confidence`, `consistency_level`
- `status`（active/suppressed/archived）
- `created_at`, `updated_at`

### 4.2 `memory_embeddings`

建议字段：

- `memory_id` pk fk -> `memory_records.id` on delete cascade
- `embedding` vector(n)
- `model`, `dim`
- `created_at`

### 4.3 `memory_links`（建议）

用于记录记忆之间的关系：

- supports / contradicts / updates

用于后续冲突消解与记忆演化。

### 4.4 `memory_write_audit`

记录写入尝试与结果：

- trace_id、request_id、idempotency_key
- 写入耗时、冲突命中、错误码
- 重试次数、最终状态

### 4.5 索引与约束

- `UNIQUE (idempotency_key)` on `memory_records`
- `INDEX (user_id, agent_id, created_at DESC)`
- `INDEX (user_id, agent_id, memory_type)`
- pgvector 索引（HNSW 或 IVFFLAT，按规模选型）
- 可选 `GIN(content_norm)` / trigram 索引用于词面补召回

## 5. 幂等与 Exactly-once 语义

### 5.1 幂等键生成

建议：

`idempotency_key = sha256(user_id + agent_id + conversation_id + source_message_id + memory_type + canonical_content)`

其中 `canonical_content` 包括：

- 空白折叠
- 全半角统一
- 数字/标点规范化
- 大小写规则统一（按语言策略）

### 5.2 写入策略

使用：

- `INSERT ... ON CONFLICT (idempotency_key) DO UPDATE ... RETURNING id`

保证重复请求、重试请求不会造成重复长期记忆。

## 6. 强一致事务边界

你选择的是“关系+向量同事务提交”，事务步骤如下：

1. 锁定会话行（必要时 `FOR UPDATE`）
2. 写入用户与助手消息
3. 运行候选抽取器
4. `memory_records` 执行幂等 upsert
5. `memory_embeddings` 写入/更新向量
6. 更新必要 cursor/引用
7. 提交事务

保证：提交成功后，下一次检索立即可见。

## 7. 服务分层与接口改造

### 7.1 ConversationService

改造为统一编排：

- `begin_message_transaction(...)`
- `compose_context_bundle(...)`
- `invoke_agent(...)`
- `persist_message_and_memories(...)`
- `commit_and_emit_observability(...)`

`add_message` 与 `add_message_stream` 必须复用 `persist_message_and_memories(...)`。

### 7.2 Memory 服务拆分

1. `MemoryExtractor`
   - 输入：user + assistant + context
   - 输出：候选列表
2. `MemoryDeduplicator`
   - 规范化文本
   - 幂等键计算
   - 冲突与覆盖判定
3. `MemoryRepository`
   - 事务内 SQL upsert
   - 向量写入
4. `MemoryRetriever`
   - 向量 + 词面混合检索
   - rerank 与 budget 裁剪

### 7.3 Streaming 路径规则

- 保持 token 流式输出。
- 在 `done` 事件前执行事务提交。
- 若提交失败，则请求应标记失败（或返回可恢复状态，取决于 API 约定）。

为了满足强一致，建议：**事务未提交则不发最终成功 done**。

## 8. 检索与注入策略

采用 Hybrid Retrieval：

1. 向量召回 `top_k_vec`
2. 词面召回 `top_k_lex`
3. 合并去重
4. 业务重排（时间衰减 + 类型优先级 + 一致性等级）
5. 预算裁剪后注入 prompt

建议初始参数：

- `top_k_vec=24`
- `top_k_lex=12`
- `final_k=8`
- 单条记忆注入上限 `180~240 chars`

## 9. 可观测与告警

### 9.1 指标

- `memory_txn_latency_ms`（P50/P95/P99）
- `memory_idempotent_hit_rate`
- `memory_write_fail_rate`
- `memory_retrieval_hit_rate`
- `memory_prompt_injection_chars`
- `stream_done_before_persist`（期望 0）

### 9.2 告警

- 5 分钟窗口 `write_fail_rate > 2%`
- `txn_p95 > 1200ms`
- `idempotent_hit_rate` 异常激增（可能抽取器重复）

## 10. 迁移方案（一次性重构）

### 10.1 迁移步骤

1. 引入 pgvector 扩展与新表迁移。
2. 上线 V3 写入路径（可配置开关）。
3. 回填历史记忆到 `memory_records + memory_embeddings`。
4. 回归验证：召回质量、写入幂等、延迟指标。
5. 切换读路径到 V3。
6. 下线 Chroma 写路径。
7. 观察窗口后移除遗留逻辑。

### 10.2 回滚策略

- 保留 `legacy_mode` 开关（短期）
- 保留回填映射关系与审计日志
- 回滚时只回切读写入口，不破坏新表数据

## 11. 测试与验收标准（DoD）

### 11.1 单元测试

- 幂等键稳定性
- canonical 规范化一致性
- dedupe / overwrite 决策正确性

### 11.2 集成测试

- 并发同内容写入仅产生 1 条有效记忆
- 事务失败时 message/memory/vector 全回滚
- 提交后下一轮立刻可检索命中

### 11.3 回归测试

- sync/stream 行为一致
- context bundle schema 稳定
- 迁移前后质量指标无明显回退

### 11.4 目标门槛

- 重复写入率下降 > 95%
- 记忆相关性指标显著提升（按 A/B 基线定义）
- P95 端到端时延增幅控制在阈值内（建议 < 15%）

## 12. 风险与缓解

1. **事务变重导致时延上升**
   - 缓解：候选上限、批处理 embedding、索引调优
2. **抽取质量波动导致噪声写入**
   - 缓解：confidence 阈值 + consistency_level + offline 复核
3. **迁移期间读写双栈复杂**
   - 缓解：严格开关治理 + 分阶段切流 + 审计可追踪

## 13. 实施建议（高层）

- 第 1 周：数据模型与 repository 层、迁移脚本、基础观测
- 第 2 周：ConversationService 编排重构、sync/stream 统一
- 第 3 周：retriever 混合召回、rerank、预算控制
- 第 4 周：历史回填、压测、灰度与切流

---

## 最终决策记录

- 数据底座：**PostgreSQL + pgvector**
- 一致性：**关系+向量同事务提交**
- 写入语义：**Exactly-once（基于 idempotency_key）**
- 迁移策略：**一次性重构 + 可回滚开关**
