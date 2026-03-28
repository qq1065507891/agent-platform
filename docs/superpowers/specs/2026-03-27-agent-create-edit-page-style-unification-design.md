# Agent 创建/编辑页面风格统一设计

日期：2026-03-27

## 背景与目标

当前“创建智能体/编辑智能体”使用抽屉组件（`AgentFormDrawer.vue`），其视觉样式与普通业务页面（如 `AgentsView`、`MyAgentsView`）的 glass 风格不一致。目标是将创建/编辑改为独立页面，并统一到业务风格，同时提升视觉美感与信息层级清晰度。

## 范围

- 新增独立页面：创建与编辑智能体
- 抽取表单复用组件以避免重复逻辑
- 调整入口路由与 `MyAgentsView` 的按钮跳转
- 保持现有功能（技能绑定、知识库上传、文档管理等）一致
- 不改变接口与后端逻辑

## 页面与路由设计

新增页面：
- `frontend/src/views/AgentCreateView.vue`
- `frontend/src/views/AgentEditView.vue`

路由：
- `/my-agents/create`
- `/my-agents/:id/edit`

入口策略：
- `MyAgentsView` 的“创建智能体”跳转到 `/my-agents/create`
- `MyAgentsView` 卡片“编辑”跳转到 `/my-agents/:id/edit`
- 兼容旧抽屉入口：保留 `AgentFormDrawer.vue`，内部改为使用新的表单组件，避免外部引用中断

## 组件重构

抽取表单主体为复用组件：
- `frontend/src/views/components/AgentFormPanel.vue`

职责拆分：
- `AgentFormPanel`：核心表单字段与业务逻辑（技能/工具绑定、知识库上传、文档管理、提交逻辑）
- `AgentCreateView`：页面壳层、文案、创建操作、成功提示与跳转
- `AgentEditView`：页面壳层、编辑加载与保存、返回入口
- `AgentFormDrawer`：改为壳层包裹 `AgentFormPanel`（可保留以兼容旧入口）

## 视觉风格（统一到普通业务页）

参考 `AgentsView` / `MyAgentsView`：

- 页面外层采用 `glass-panel`（模糊背景 + 玻璃边框 + 阴影）
- 顶部 Hero 区域：渐变背景（蓝紫/青），标题 + 副标题 + 状态 Tag
- 表单容器卡片：半透明底色、14-16px 圆角、轻边框、弱阴影
- 分组标题：左侧 3px 细色条 + 中等字重标题，降低“后台感”
- 按钮区：右侧对齐，主按钮高亮，次按钮弱化
- 知识库列表/上传区：卡片化分段与更清晰的层级色阶
- 去除原 Drawer 中的深色 header/body/footer 视觉（避免风格冲突）

## 交互与体验

- 创建页：提交成功后默认返回 `MyAgentsView` 并提示成功（可扩展为“继续创建”）
- 编辑页：进入后按 `id` 拉取数据并回填；保存成功提示“已保存”并停留页面
- 知识库管理功能仅在编辑态展示（与当前逻辑一致）
- 可选：若表单有改动未保存，路由离开前弹确认（实现成本低，提升安全性）

## 数据与状态

- 创建：保持与现有 `createAgent` 提交字段一致
- 编辑：使用 `updateAgent` 同样字段
- 技能与 MCP 工具：使用现有 `getSkills` 拉取，复用过滤逻辑
- 知识库上传：继续使用 `uploadKnowledge`，并在编辑页展示文档管理功能

## 受影响文件清单

- `frontend/src/router/index.ts`
- `frontend/src/views/MyAgentsView.vue`
- `frontend/src/views/components/AgentFormPanel.vue`（新）
- `frontend/src/views/AgentCreateView.vue`（新）
- `frontend/src/views/AgentEditView.vue`（新）
- `frontend/src/views/components/AgentFormDrawer.vue`（改造为兼容壳层）

## 测试点

- 创建页表单校验、提交成功提示与跳转
- 编辑页加载、保存、知识库管理区域可用
- 列表页跳转入口可用
- 原 Drawer 若仍被调用可正常展示表单

## 风险与缓解

- 路由变更导致旧入口失效：保留 `AgentFormDrawer` 兼容壳层
- 表单逻辑拆分易引发状态遗漏：严格对照 `AgentFormDrawer` 现有字段与逻辑

