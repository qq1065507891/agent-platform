# Agent Platform v0.1.0

首个开源版本发布。

## Highlights

- 完成全栈 Agent 平台基础能力：FastAPI + Vue3
- 新增 Docker Compose 一键部署与生产化容器编排
- 支持 PostgreSQL + pgvector、Redis、Celery Worker、自动迁移
- 引入 Memory V3（向量记忆 schema + 回写链路）
- 增强 RAG 检索、指标统计、后台管理页面能力
- 提供可选 Caddy 网关（TLS/域名反代）

## Included Services

- backend
- frontend
- postgres (pgvector)
- redis
- db_preflight
- migrate
- worker
- caddy (optional profile)

## Breaking / Important Notes

- 运行前必须配置 `.env`（建议从 `.env.example` 复制）
- 生产环境请务必替换所有密钥与密码
- `DB_URL` 中密码若含特殊字符请使用 URL 编码

## Quick Start

```bash
cp .env.example .env
docker compose up -d --build
```

访问：
- Frontend: http://localhost:3000
- Backend: http://localhost:8000

## Acknowledgements

感谢所有测试与反馈，欢迎继续通过 Issue / PR 共建。
