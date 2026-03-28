# Agent Platform

一个可私有化部署的智能体平台（Agent Platform），提供：

- 多 Agent 管理
- 对话编排与流式输出
- RAG 知识库检索
- 记忆系统（Memory）
- 技能执行（Skills）
- 观测与指标（Metrics）

本仓库已提供**生产可用的 Docker Compose 一键启动方案**。

---

## 技术栈

### 后端
- Python 3.12
- FastAPI + Gunicorn + UvicornWorker
- SQLAlchemy + Alembic
- Celery + Redis
- PostgreSQL + pgvector

### 前端
- Vue 3 + Vite
- Nginx（容器内静态托管 + 反向代理 `/api`）

### 编排与部署
- Docker / Docker Compose
- 可选 Caddy 网关（HTTPS / 证书自动签发）

---

## 架构说明（Docker）

默认启动以下服务：

- `postgres`：数据库（`pgvector/pgvector:pg16`）
- `redis`：任务队列与缓存
- `db_preflight`：数据库预检（验证连接与 `vector` 扩展）
- `migrate`：Alembic 迁移（`alembic upgrade head`）
- `backend`：FastAPI 主服务
- `worker`：Celery Worker
- `frontend`：前端静态站点 + `/api` 反代

可选服务：
- `caddy`（`--profile gateway`）：统一 80/443 网关与 TLS

启动链路为：`postgres/redis` → `db_preflight` → `migrate` → `backend/worker` → `frontend`。

---

## 快速开始（推荐）

### 1) 准备环境变量

```bash
cp .env.example .env
```

至少填写以下字段：

- `POSTGRES_PASSWORD`
- `JWT_SECRET`
- `LLM_GATEWAY_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

> 说明：
> - `DB_URL` 必须使用容器网络地址 `postgres`（不是 `localhost`）
> - 若密码包含特殊字符（如 `@`, `!`, `%`），请使用 URL 编码（例如 `@ -> %40`）

### 2) 一键启动

```bash
docker compose up -d --build
```

### 3) 访问地址

- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000`
- 后端健康检查：`http://localhost:8000/`

---

## 常用命令

### 查看服务状态

```bash
docker compose ps
```

### 查看全部日志

```bash
docker compose logs -f
```

### 查看单服务日志

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f worker
docker compose logs -f migrate
docker compose logs -f db_preflight
```

### 重启单服务

```bash
docker compose restart backend
```

### 停止服务

```bash
docker compose down
```

### 停止并清空数据卷（危险操作）

```bash
docker compose down -v
```

---

## 可选：启用 TLS 网关（Caddy）

1. 在 `.env` 设置：

- `GATEWAY_DOMAIN=your.domain.com`
- `GATEWAY_TLS_EMAIL=you@example.com`

2. 启动：

```bash
docker compose --profile gateway up -d --build
```

启用后：
- `80/443` 由 Caddy 接管
- `/api/*` 转发至后端
- 其他请求转发至前端

---

## 生产部署建议

- 使用强密码与随机密钥：`POSTGRES_PASSWORD`、`JWT_SECRET`
- 不要将真实 API Key 提交到 Git（建议使用 CI/CD Secrets）
- 定期备份 PostgreSQL 与关键卷
- 对外开放时建议启用 Caddy（HTTPS）
- 根据机器资源调整 `docker-compose.yml` 中 `mem_limit` / `cpus`

---

## 目录中的关键部署文件

- `Dockerfile`：后端/worker/migrate 镜像（多阶段构建）
- `.dockerignore`：后端构建忽略
- `frontend/Dockerfile`：前端镜像（多阶段构建，非 root）
- `frontend/nginx.conf`：前端站点与 `/api` 反代配置
- `frontend/nginx.main.conf`：Nginx 主配置（非 root 兼容）
- `frontend/.dockerignore`：前端构建忽略
- `docker-compose.yml`：完整编排（含健康检查、预检、迁移链路）
- `.env.example`：环境变量模板
- `deploy/Caddyfile`：可选 HTTPS 网关配置

---

## 常见问题（FAQ）

### 1) `migrate` 失败：`extension "vector" is not available`
请确认数据库镜像为 `pgvector/pgvector:pg16`，并查看：

```bash
docker compose logs --tail=120 db_preflight
```

### 2) `migrate` 连接失败（`localhost:5432`）
请检查 `.env` 的 `DB_URL` 是否为：

```text
...@postgres:5432/...
```

### 3) 前端 3000 端口无法访问
请检查：

```bash
docker compose ps
docker compose logs --tail=120 frontend
```

---

## 开源发布前检查清单

- [ ] `.env` 未提交（仅提交 `.env.example`）
- [ ] 移除 README 和代码中的真实密钥
- [ ] `docker compose up -d --build` 在干净环境可成功拉起
- [ ] `backend` 健康检查通过、`frontend` 可访问
- [ ] `migrate` 执行成功（`Exited (0)`）

---

