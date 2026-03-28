# Agent Platform

一个面向企业场景的全栈 Agent 平台，支持多模型对话、RAG 检索增强、Memory 记忆系统、后台管理与可观测能力。

## 核心特性

- 后端：FastAPI + SQLAlchemy + Alembic + Celery
- 前端：Vue 3 + Vite + Arco Design
- 数据层：PostgreSQL（pgvector）+ Redis + Chroma 持久化目录
- Agent 能力：流式响应、模式选择、Router-Worker、工具注册与调用
- 知识库：文档入库、切片、去重、检索与重排
- 记忆系统：Memory V3（向量记忆、回写链路、评估与指标）
- 部署：Docker Compose 一键部署，支持可选 Caddy TLS 网关

## 技术栈

- Backend: Python 3.12, FastAPI, Gunicorn/Uvicorn, Celery
- Frontend: Vue 3, Vite, TypeScript, Arco Design
- Database: PostgreSQL 16 + pgvector
- Cache/Queue: Redis 7
- Migration: Alembic
- Container: Docker / Docker Compose

## 目录结构

```text
.
├─ app/                    # 后端应用代码
├─ alembic/                # 数据库迁移脚本
├─ frontend/               # 前端应用
├─ deploy/                 # 网关配置（Caddy）
├─ docs/                   # 文档与发布说明
├─ docker-compose.yml      # 编排入口
├─ Dockerfile              # 后端/worker 镜像
├─ .env.example            # 环境变量模板
└─ README.md
```

## 快速开始（Docker）

### 1) 准备环境变量

```bash
cp .env.example .env
```

至少配置：

- `POSTGRES_PASSWORD`
- `JWT_SECRET`
- `LLM_GATEWAY_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

> 生产环境务必替换所有密钥。

### 2) 启动服务

```bash
docker compose up -d --build
```

服务地址：

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

### 3) 常用命令

```bash
# 查看状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止
docker compose down

# 停止并清理卷（谨慎）
docker compose down -v
```

## 启动链路说明

编排中包含以下关键服务顺序：

1. `postgres` / `redis` 健康检查通过
2. `db_preflight` 检查数据库可连接且 `vector` 扩展可用
3. `migrate` 自动执行 `alembic upgrade head`
4. `backend` / `worker` 启动
5. `frontend` 启动

## 可选：启用 TLS 网关（Caddy）

在 `.env` 配置：

- `GATEWAY_DOMAIN`
- `GATEWAY_TLS_EMAIL`

然后启动：

```bash
docker compose --profile gateway up -d --build
```

## 本地开发

### Backend

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## 测试

```bash
# 后端测试
pytest

# 前端测试
cd frontend
npm run test
```

## 开源与安全说明

- 仓库不包含真实密钥，使用 `.env.example` 作为模板
- 请勿提交 `.env`、本地数据库/向量数据与缓存文件
- 若发现安全问题，请通过 Issue 私信维护者或提交安全修复 PR

## 路线图（Roadmap）

- [ ] 完整 API 文档站点
- [ ] 更完善的权限模型与租户隔离
- [ ] 更丰富的工具市场与插件生态
- [ ] 完整基准测试与可观测 dashboard 模板

## 许可证

本项目基于 [MIT License](./LICENSE) 开源。
