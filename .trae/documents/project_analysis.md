# Deep Data Agent 项目分析

> 状态日期：2026-08-10。本文以当前工作树、已完成规格和本地确定性检查为依据，
> 不把候选能力或尚未取得的发布证据写成既成事实。

## 1. 当前定位

Deep Data Agent 是一个前后端分离的 AI 数据探索与智能问答项目。当前版本已经
完成可运行闭环和第一方多用户认证，不再是只有单一 Agent 脚本的原型：

- Next.js 前端通过 LangGraph SDK 访问流式 Agent，通过独立 REST 客户端访问
  FastAPI 认证接口。
- LangGraph 图和 FastAPI 应用已拆分为两个入口，职责和生命周期相互独立。
- MySQL 持久化用户、会话与消息，Redis 缓存 Agent 与搜索结果并支持故障降级。
- Docker Compose 编排 MySQL、Redis、FastAPI、LangGraph 和前端 5 个服务。
- 第一方认证使用 FastAPI、JWT 和 CORS 白名单，会话资源在服务层按用户隔离。

当前迭代是 `enforce-release-readiness`。目标不是扩展业务功能，而是把已经实现的
能力固化为不可静默绕过、可重复验证、可追溯的发布基线。

## 2. 实际架构

### 2.1 后端入口与调用链

`langgraph.json` 加载 `data_agent.agent_graph:agent`；图构建位于
`data_agent/services/agent_service.py`，不会导入 FastAPI 或触发数据库建表。
FastAPI 则从 `data_agent.agent_server:app` 启动，只在应用生命周期中调用
`init_db()`。

FastAPI 当前提供以下边界：

- `/api/health`：不调用真实模型的健康检查。
- `/api/query`：调用 Agent，使用稳定的非 2xx 配置错误和上游错误语义。
- `/api/auth/*`：注册、OAuth2 密码表单登录和当前用户查询。
- `/api/sessions/*`：要求 Bearer Token 的会话与消息接口。

Agent 默认注册互联网搜索和本地文档分析工具。任意 Python 代码执行工具只有在
人工设置 `ENABLE_CODE_EXECUTION=true` 时才会注册；当前实现不是沙箱。

### 2.2 数据与缓存

SQLAlchemy 模型共享同一份 `Base.metadata`，MySQL 表包括 `users`、`sessions`
和 `messages`。会话服务在创建、列表、读取、写入和删除时均使用当前用户 ID；
访问其他用户的资源统一返回 404，避免泄露资源存在性。

Redis 通过 `REDIS_URL` 配置。连接、读取或写入失败时，缓存服务降级为未命中，
不会阻断 Agent 主流程；诊断日志不输出查询正文或凭据。Agent 响应缓存当前使用
24 小时有效期。

### 2.3 前端边界

前端是 Next.js 15、React 19 和 TypeScript 项目，生产构建静态导出到
`/data_copilot/`。浏览器侧明确区分两类地址：

- `NEXT_PUBLIC_API_URL`：LangGraph 服务地址。
- `NEXT_PUBLIC_REST_API_URL`：FastAPI 第一方认证与会话服务地址。

第一方登录页直接调用 FastAPI 注册、登录和 `/api/auth/me`，不依赖外部授权码
交换。JWT 只保存在当前标签页的 `sessionStorage`，并且只附加到同源于配置的
FastAPI 请求。LangGraph API Key 如存在，仍由独立的 `localStorage` 键管理；
LangGraph 或第三方 401/403 不会清除第一方登录态。

### 2.4 容器闭环

Compose 使用以下服务名：`mysql`、`redis`、`fastapi`、`langgraph` 和
`frontend`。数据库与缓存的容器内连接使用服务名，浏览器公开地址则在前端构建
阶段注入，不能使用只在 Docker 网络中可解析的主机名。关键依赖通过健康检查和
`service_healthy` 控制启动顺序。

完整运行依赖 Docker Desktop Linux Engine。系统盘空间不足或宿主机 `3306`、
`6379` 端口冲突会阻断构建或启动；端口冲突应只通过 `.env` 中的宿主端口变量
重映射，不改变容器内部地址。

## 3. 已完成能力与验证基线

### 3.1 可运行闭环

`establish-runnable-baseline` 已完成入口拆分、依赖补齐、缺失前端工具模块修复、
公开地址统一、缓存降级、代码执行默认关闭、五服务 Compose 编排和端到端冒烟。
健康检查和确定性测试不需要真实模型响应。

### 3.2 第一方认证与所有权隔离

`secure-user-sessions` 已完成以下安全边界：

- JWT 密钥和有效期从环境变量读取，密钥缺失、过短或为占位值时不签发 Token。
- JWT `sub` 使用不可变用户 ID，并校验签名、算法、有效期和用户存在性。
- CORS 使用明确来源白名单；启用凭据时拒绝通配符来源。
- 注册、登录、`/me`、会话标题、消息角色和正文具有稳定校验及错误语义。
- 所有会话和消息操作均在服务层按 `session_id` 与 `user_id` 联合过滤。
- 前端第一方 Token 从持久化存储迁移到 `sessionStorage`。

前两轮完成规格建立了 60 项自动测试，覆盖运行入口、配置错误、Redis 降级、
认证、CORS 和双用户越权场景。本轮新增 4 项 ORM/UTC 兼容性回归后，当前工作树
执行 `python -m pytest -q` 为 `64 passed`，`isort --check-only` 也已通过。

## 4. 发布质量现状

### 4.1 当前迭代已在收敛的项目

- Next.js 的 TypeScript/ESLint 构建绕过已从当前工作树移除。
- 前端 Lint 已改为 `eslint . --max-warnings=0`，显式加载 Next.js ESLint 规则，
  当前严格检查以零警告通过。
- Node.js 22 与 pnpm 10.5.1 的版本契约正在固化。
- ORM 声明式基类已使用 SQLAlchemy 2.x 推荐导入；时间默认值和会话更新时间已
  使用明确 UTC 语义，同时保持现有无时区数据库字段和 API 序列化兼容。
- 环境示例、README、项目分析、Roadmap 和变更记录正在统一。

上述项目仍须以本轮最终的类型检查、Lint、格式、构建、全量测试、Compose 和容器
冒烟结果为发布证据，不能仅以文件已修改判定完成。

### 4.2 当前阻塞和技术债

1. **CI 尚未建立**：截至本文更新时仓库没有 `.github` 工作流，质量命令仍依赖
   人工执行，无法阻止合并后回退。当前迭代必须补齐推送和合并请求门禁。
2. **最终发布证据待生成**：最新工作树的前端类型检查、零警告 Lint 和格式检查
   已通过，但本机 Node.js 25.2.1 不在受支持的 22.x 范围内；仍需在受支持版本
   完成生产构建以及五服务重建和双用户冒烟。
3. **迁移能力有限**：数据库仍依赖 `Base.metadata.create_all()`，没有 Alembic
   或版本化 schema 迁移流程。
4. **LangGraph 认证边界有限**：本地 LangGraph 仍使用 noop 认证；第一方 JWT
   目前只保护 FastAPI 认证与会话接口。
5. **授权模型有限**：尚无 Refresh Token、密码找回、邮箱验证、OAuth、RBAC、
   管理员审计或请求限流。
6. **高风险工具未沙箱化**：代码执行虽默认关闭，但显式启用后仍可运行任意
   Python；文档分析也只适用于受控本地文件。
7. **可观测性不足**：已有脱敏日志和 `request_id`，但尚无统一 Trace、指标、
   告警、容量基线和发布看板。
8. **历史凭据风险已接受但未消除**：旧 Moonshot/Tavily 凭据已轮换失效，新值
   仅存本地；旧值仍在 Git 历史中。历史重写必须在干净工作区人工发起，并与所有
   协作者协调，不能在业务迭代中直接执行。

## 5. 发布判断

项目已经具备本地开发和受控 Docker 环境中的功能基线，但在自动 CI、最新镜像
重建和发布证据完成前，不应宣称达到无人值守生产发布条件。当前正确顺序是先完成
发布治理，再按 Roadmap 评审观测性、限流、RBAC 和数据分析能力。

任何后续能力验证都必须人工触发，使用脱敏数据或专用测试数据；真实密钥、Token、
业务数据和可识别用户信息不得进入提示词、日志、测试固件、CI 产物或版本控制。
