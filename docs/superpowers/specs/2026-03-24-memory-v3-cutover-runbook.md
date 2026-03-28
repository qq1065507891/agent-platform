# Memory V3 切换与回滚 Runbook

## 1. 变更前检查

1. 确认已执行迁移：`20260324_01_memory_v3_pgvector`。
2. 确认 PostgreSQL 已启用 `vector` 扩展。
3. 确认应用配置：
   - `memory_backend=pgvector`
   - `memory_transactional_write_enabled=true`
4. 暂时保留 legacy 写回开关（用于紧急回滚）。

## 2. 回填阶段

### 2.1 执行回填任务

- 批量执行：`app.tasks.memory_v3_backfill_task`
- 建议参数：`batch_size=500`（根据实例容量调整）
- 重复执行直到 `migrated` 接近 0。

### 2.2 执行校验任务

- 执行：`app.tasks.memory_v3_verify_task`
- 重点检查：
  - `v3_count` 与 `legacy_count` 比例 >= 95%
  - `missing_embedding == 0`
  - `healthy == true`

## 3. 灰度切流

1. 小流量实例开启：
   - `memory_backend=pgvector`
   - `memory_transactional_write_enabled=true`
2. 观察指标（至少 30 分钟）：
   - `memory_transaction_write` 失败率
   - `memory_retrieval_breakdown` 延迟
   - `memory_stream_persist_consistency.persist_before_done`
3. 若稳定，逐步扩大流量到全量。

## 4. 全量切换后观察

建议观察 24h：

- 写入成功率 >= 98%
- 重复命中（`idempotent_hits`）在预期范围
- 检索延迟 P95 未明显恶化

## 5. 回滚预案

触发条件示例：

- `memory_transaction_write` 失败率持续 > 2%
- 检索性能严重退化且无法快速恢复
- 线上出现大量写入阻塞

回滚步骤：

1. 切换配置：
   - `memory_backend=chroma`
   - `memory_transactional_write_enabled=false`
2. 保留新表数据，不做 destructive 回滚。
3. 保持回填任务暂停，保留审计与日志用于根因排查。
4. 问题修复后再进行二次灰度。

## 6. 下线 legacy 路径（稳定后）

满足以下条件可下线：

- 连续 7 天稳定
- 回填与校验任务全部通过
- 无高优先级 memory 相关告警

下线动作：

1. 关闭 legacy 写回与 Chroma 读路径。
2. 清理不再使用的代码分支。
3. 更新运维文档与值班手册。
