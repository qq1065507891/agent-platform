# Metrics Scope 改造设计

## 背景与目标
当前指标接口缺少统一权限与范围控制，普通用户可能通过 `user_id` 访问他人数据。目标是统一指标 scope 规则，确保普通用户只看自己、管理员可看全量或指定用户，并在管理员全量查询时记录审计事件。前端看板根据角色展示范围切换与提示文案，缓存 key 包含 scope 维度避免越权命中。

## 范围
- 后端 API：`/metrics/*` 统一权限与 scope 解析（支持 `overview/trends/skills/agents` 并保留旧路由兼容）。
- 服务层：新增 `MetricsQueryScope` 统一注入用户过滤条件。
- 审计：管理员全量查询写入 `metrics_admin_view` 事件。
- 前端看板：管理员可切换全量/按用户，普通用户隐藏用户筛选。
- 缓存：若存在缓存，key 必须包含 role、user_id/target_user_id、scope 与时间范围。

## 权限与 Scope 规则
- admin：
  - `scope=all`（默认）可看全量；允许 `user_id` 指定单用户。
- 非 admin：
  - 强制 `scope=self`。
  - 若传入 `user_id != current_user.id` 返回 403。

## API 设计
- 新增/统一接口：
  - `GET /metrics/overview`
  - `GET /metrics/trends`
  - `GET /metrics/skills`
  - `GET /metrics/agents`
- 兼容保留：`/summary`、`/tokens`、`/errors`、`/agents`（向后兼容）。
- 参数：
  - `scope`: `all|self`（默认 `self`，admin 可 `all`）
  - `user_id`: admin 可指定目标用户
  - `start_date`/`end_date`: 时间范围

## 服务层设计
- 新建 `MetricsQueryScope`（或在 `app/services/metrics.py` 定义）：
  - `current_user_id`, `role`, `scope`, `target_user_id`, `start_date`, `end_date`, `agent_id`, `trace_id`
- 提供 `apply_user_filter(query, user_field)`：
  - `admin + target_user_id`: `WHERE user_field = target_user_id`
  - `admin + all`: 无 user 过滤
  - `self`: `WHERE user_field = current_user_id`

## 审计日志
- 条件：`role=admin` 且 `scope=all`
- 事件：`metrics_admin_view`
- metadata：
  - `scope`
  - `filters`（时间范围、user_id/agent_id）
  - `trace_id`

## 前端看板
- 普通用户：隐藏用户筛选器；显示「数据范围：当前账号」。请求不携带 `user_id`。
- 管理员：显示范围切换（全量 / 按用户）；用户下拉来自用户列表；显示「数据范围：全量（管理员）」或「数据范围：指定用户」。
- 请求参数统一使用 `scope`、`user_id`、`start_date`、`end_date`。

## 缓存
- 若服务层有缓存：key 必含 `role + current_user_id + target_user_id + scope + time_range + filters`。
- 指标计算口径保持一致，仅改变过滤范围。

## 错误处理
- 非 admin 传 `user_id` 且不等于自身 -> 403。
- `start_date/end_date` 异常：保持现有参数校验逻辑。

## 测试与验收
- 普通用户：
  - 看不到他人数据
  - 传 `user_id=B` 返回 403
- admin：
  - 可看全量
  - 可按用户切换
- 审计：admin 全量查询写入 `metrics_admin_view` 事件
- 性能：全量查询时间范围限制有效
