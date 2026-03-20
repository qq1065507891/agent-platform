# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用开发命令

### 后端
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
alembic upgrade head
alembic revision --autogenerate -m "describe_change"
python test_embedding_connectivity.py
```

### 前端
```bash
cd frontend && npm install
cd frontend && npm run dev
cd frontend && npm run build
cd frontend && npm run preview
```

### 当前仓库状态说明
- `frontend/package.json` 当前只提供 `dev` / `build` / `preview`，未配置单独的 lint/test script。
- 仓库中未发现成体系的 pytest 测试目录或 pytest 配置；当前唯一现成的“测试型”脚本是根目录的 `python test_embedding_connectivity.py`，用于验证 Embedding 接口连通性。
- 前端 Vite 开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`，联调时需要先启动后端。

## 高层架构

### 1. 后端是“Router → Service → Model/Schema”分层
- `app/main.py` 组装 FastAPI 应用，并统一挂载 `/api/v1` 下的 `auth`、`users`、`roles`、`permissions`、`agents`、`conversations`、`skills`、`knowledge` 路由。
- `app/api/*` 保持很薄：做参数校验、依赖注入、权限判断，然后把业务交给 `app/services/*`。
- `app/models/*` 是 SQLAlchemy 持久化模型，`app/schemas/*` 是 Pydantic 请求/响应模型。接口字段变化通常需要同时改这两层。

### 2. 所有接口都遵循统一响应包裹
- 后端成功响应统一通过 `app/core/responses.py` 返回 `{ code: 0, message: "ok", data: ... }`。
- 异常响应由 `app/main.py` 中的全局异常处理器收口为 `{ code, message, detail }`。
- 前端 `frontend/src/utils/request.ts` 会自动解包 `data`，并在 401/403 时清理本地登录态并跳转 `/login`。
- 这意味着**后端返回结构一旦变化，前端请求层和页面调用方要一起改**。

### 3. 认证与权限是后端依赖链的一部分，不只是前端路由守卫
- `app/core/deps.py` 中的 `get_current_user()` 负责从 Bearer Token 解码 JWT、加载当前用户并检查是否为 active。
- `require_admin()` 在后端执行管理员权限校验；不要只依赖前端 `meta.requireAdmin`。
- `app/core/security.py` 负责密码哈希校验和 JWT 签发/解析。
- 前端 `frontend/src/router/index.ts` 只是基于 `localStorage` 的体验层拦截，不是安全边界。

### 4. 对话链路的核心不在 Router，而在 `ConversationService + LangGraph`
- `app/services/conversations.py` 的 `add_message()` 是聊天主入口：
  1. 读取会话历史 JSON
  2. 转成 LangChain messages
  3. 在首轮对话时注入智能体 `prompt_template`
  4. 调用 `app/services/agent/graph.py` 构建的图执行
  5. 把用户消息和助手回复重新写回 `conversation.messages`
- 如果你要改聊天行为、上下文拼装、工具调用、知识检索注入，优先看这两处，而不是只看 API 路由。

### 5. Agent 运行时是一个 `llm -> tool -> llm` 的 LangGraph 循环
- `app/services/agent/graph.py` 用 `ChatOpenAI` + `StateGraph` 构建 Agent 图。
- 图里绑定了两类工具：
  - `app/services/skills/builtin.py` 里的内置工具
  - 针对当前 agent 动态生成的 `retriever_tool`
- `_should_continue()` 根据最后一条 AIMessage 是否包含 `tool_calls` 决定走工具节点还是结束。
- 因此，任何“让智能体会调用某个能力”的改动，通常需要同时考虑：工具定义、工具注册、技能列表暴露、前端配置入口。

### 6. Skills 列表不是纯数据库查询，而是“数据库技能 + 内置技能”的合并结果
- `app/api/skills.py` 会把 DB 中的技能记录与 `BuiltinSkillRegistry` 暴露的内置技能合并返回。
- `app/services/skills/registry.py` 负责把 LangChain 工具转换成技能元数据；`app/services/skills/service.py` 负责 DB 查询。
- 当前内置技能定义在 `app/services/skills/builtin.py`，目前实现较轻量（如 `calculator`、`current_time`）。
- 这类改动往往会同时影响：运行时工具调用能力、后台技能列表展示、智能体配置表单里的可选技能。

### 7. 知识库 / RAG 通过 Chroma 接入，并按 `agent_id` 做过滤
- `app/api/knowledge.py` 提供上传入口，真正的文档解析、切分、向量化和写入都在 `app/services/rag_service.py`。
- `RAGService` 支持 PDF / DOCX / 纯文本提取，使用 OpenAI 兼容 Embedding 接口生成向量。
- 当 `CHROMA_URL` 未配置时，向量会落到本地 `./chroma`；配置后走远程 Chroma 服务。
- 检索不是按独立 collection 分库，而是通过 metadata 中的 `agent_id` 过滤，所以“某个智能体绑定自己的知识库”本质上是检索过滤逻辑。

### 8. 数据库以 SQLAlchemy + Alembic 为准
- `app/core/database.py` 提供 `engine`、`SessionLocal`、`Base`；默认库是 `sqlite:///./app.db`，也可由 `DB_URL` 覆盖。
- `alembic/env.py` 会读取相同的 `DB_URL`，因此本地和迁移命令共享数据库配置来源。
- 仓库已经有 Alembic 迁移文件，不要再回到手写 `create_all()` 的方式维护表结构。

### 9. 前端是典型的“页面视图 + API 层 + 路由守卫”结构
- `frontend/src/main.ts` 启动 Vue 3、Pinia、Vue Router、Arco Design。
- `frontend/src/router/index.ts` 定义登录页、智能体市场、我的智能体、对话页、智能体专属对话页、管理员页面。
- `frontend/src/api/*` 是请求封装层；新增后端接口时，优先先补这里，再让页面调用。
- `frontend/src/views/ChatView.vue` 和 `frontend/src/views/AgentChatView.vue` 直接编排“创建会话 / 获取会话 / 发送消息”的交互流，是联调聊天功能时最关键的前端入口。

## 修改时优先联动检查的文件组

### 新增或修改接口
- 后端：`app/api/*`、`app/services/*`、`app/schemas/*`
- 前端：`frontend/src/api/*`，以及实际消费该接口的 `frontend/src/views/*`

### 修改登录态或用户字段
- 后端：`app/api/auth.py`、`app/services/auth.py`、`app/core/deps.py`、`app/core/security.py`
- 前端：`frontend/src/utils/request.ts`、`frontend/src/router/index.ts`、登录页及本地 `user` 存储使用点

### 修改聊天行为或智能体回答逻辑
- 后端优先看：`app/services/conversations.py`、`app/services/agent/graph.py`
- 前端优先看：`frontend/src/views/ChatView.vue`、`frontend/src/views/AgentChatView.vue`

### 修改知识库 / RAG
- 后端：`app/api/knowledge.py`、`app/services/rag_service.py`、`app/core/config.py`
- 前端：`frontend/src/api/knowledge.ts` 以及智能体配置相关页面

## 仓库约定与文档来源
- `.cursorrules` 定义了本项目最重要的接口约定：`/api/v1`、Bearer JWT、统一响应包裹、分页结构、常见错误码。
- `开发文档.md` 描述的是平台目标态（包含 RBAC/ABAC、RAG、Skills 生态、监控与部署等）；写代码时优先以当前实现为准，但不要破坏文档已明确的 API 包裹和分页约定。
- 如果文档与代码冲突：**优先相信当前代码行为，再判断是否需要顺手补文档或对齐实现**。
