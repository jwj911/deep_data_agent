# Deep Data Agent 项目指南

> 本文件面向 AI 编码助手。所有结论以当前工作树、正式规格和可重复命令为准；
> 不把 Roadmap 候选或尚未取得的发布证据描述为已实现能力。

## 1. 工作区与协作约束

项目根目录是：

```text
D:\Code\deep_data_agent\deep_data_agent
```

执行命令、解析相对路径和生成差异时均以该目录为根。开始任务前必须读取
`git status --short`、本文件、相关规格和目标文件。

- 工作区可能包含用户或其他任务的未提交改动。不得回滚、覆盖、格式化或顺带重构
  不属于当前任务的内容；并行改动影响当前任务时，重新读取后在最新内容上合并。
- 只编辑用户授权的文件。除非用户明确要求，否则不修改规格 tasks/checklist，
  不创建提交、不推送、不重写历史。
- 手工修改使用 `apply_patch`。运行格式化、测试或构建前先评估生成物，结束时清理
  任务产生且不应保留的缓存和构建目录。
- 不读取、输出或提交本地 `.env` 中的真实值。API Key、JWT、密码、Token、业务
  数据和可识别用户信息不得进入代码、文档、测试固件、日志或 CI 产物。
- 高风险工具、生产数据验证、凭据历史重写和模型批量调用必须由人工明确触发，
  并使用脱敏输入；不得由助手自行扩大执行范围。

## 2. 项目现状

Deep Data Agent 是前后端分离的 AI 数据探索项目，当前已完成可运行闭环和第一方
多用户认证：

- `data_agent/`：Python 3.12、FastAPI、LangGraph/DeepAgents、SQLAlchemy。
- `agent_chatui/`：Next.js 15、React 19、TypeScript、Tailwind CSS 静态前端。
- MySQL：持久化用户、会话和消息。
- Redis：缓存 Agent 与搜索结果；不可用时降级为未命中。
- Docker Compose：编排 MySQL、Redis、FastAPI、LangGraph 和前端 5 个服务。

当前正式迭代是 `.trae/specs/enforce-release-readiness/`。它聚焦前后端质量门禁、
CI、配置漂移防护、发布文档和五服务复验，不包含新的业务功能。

## 3. 关键结构

```text
deep_data_agent/
├── .env.example
├── AGENTS.md
├── CHANGELOG.md
├── README.md
├── langgraph.json
├── requirements.txt
├── tests/
├── .trae/
│   ├── documents/
│   │   ├── project_analysis.md
│   │   └── roadmap.md
│   └── specs/
├── agent_chatui/
│   ├── package.json
│   ├── next.config.mjs
│   └── src/
│       ├── app/
│       ├── components/
│       ├── config/
│       ├── lib/
│       └── providers/
├── data_agent/
│   ├── agent_graph.py
│   ├── agent_server.py
│   ├── config/
│   ├── models/
│   ├── routes/
│   ├── services/
│   └── tools/
└── docker-config/
    └── docker-compose.yml
```

### 3.1 服务入口

- `langgraph.json` 导出 `data_agent.agent_graph:agent`。该入口不依赖 MySQL 建表。
- `data_agent.agent_server:app` 是 FastAPI ASGI 入口，数据库初始化只发生在应用
  生命周期。
- `/api/health` 不触发模型调用；`/api/query` 将配置错误和上游错误映射为稳定的
  非 2xx 响应。
- `data_agent/routes/auth.py` 提供注册、登录和 `/me`；
  `data_agent/routes/session.py` 提供受保护的会话与消息接口。

### 3.2 前端连接

- `NEXT_PUBLIC_API_URL` 和 `NEXT_PUBLIC_ASSISTANT_ID` 用于 LangGraph。
- `NEXT_PUBLIC_REST_API_URL` 用于 FastAPI 第一方认证和会话接口。
- 两类公开地址在静态构建时写入，必须可由浏览器访问，不能使用 Docker 内部服务名。
- 第一方 JWT 存储在 `sessionStorage`，只附加到 FastAPI 请求。
- 可选 LangGraph API Key 使用独立 `localStorage` 键；非 FastAPI 的 401/403 不得
  清除第一方登录态。

## 4. 配置契约

复制 `.env.example` 为本地 `.env`，只在本地填入真实值。

| 变量 | 作用 | 约束 |
| --- | --- | --- |
| `MOONSHOT_API_KEY` | 模型调用 | 示例占位值无效；不得提交 |
| `TAVILY_API_KEY` | 互联网搜索 | 仅搜索工具需要；不得提交 |
| `MODEL_NAME`、`MODEL_BASE_URL`、`MODEL_TEMPERATURE` | 模型配置 | 与提供方契约一致 |
| `DATABASE_URL` | 宿主机数据库 | 默认使用 PyMySQL URL |
| `REDIS_URL` | 宿主机缓存 | 不可用时允许降级 |
| `JWT_SECRET_KEY` | 第一方 JWT 签名 | 至少 32 个字符且不能是占位值 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token 有效期 | 正整数 |
| `CORS_ALLOWED_ORIGINS` | FastAPI 来源白名单 | 逗号分隔绝对来源，禁止通配符 |
| `ENABLE_CODE_EXECUTION` | 任意 Python 执行开关 | 默认 `false`，仅受控环境人工启用 |
| `COMPOSE_DATABASE_URL`、`COMPOSE_REDIS_URL` | 容器内部连接 | 使用 `mysql`、`redis` 服务名 |
| `MYSQL_PORT`、`REDIS_PORT` 等 | 宿主机端口 | 端口冲突时只重映射宿主侧 |

Compose 的数据库凭据、数据库名和连接 URL 必须同步修改。前端公开 URL 与容器
内部地址是两套边界，不得互换。

## 5. 常用命令

### 5.1 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python -m isort --check-only data_agent tests
python -m uvicorn data_agent.agent_server:app --host 0.0.0.0 --port 8000
langgraph dev --host 0.0.0.0 --port 2024 --no-browser --allow-blocking
```

### 5.2 前端

前端版本契约是 Node.js 22.11 或更高的 22.x 版本、pnpm 10.5.1。

```powershell
Set-Location agent_chatui
pnpm install --frozen-lockfile
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
pnpm dev
```

生产构建使用静态导出和 `/data_copilot` base path。TypeScript、ESLint 或格式错误
不得通过配置绕过；Lint 的目标是零警告。

### 5.3 Docker Compose

```powershell
docker compose --env-file .env -f docker-config/docker-compose.yml config --quiet
docker compose --env-file .env -f docker-config/docker-compose.yml build
docker compose --env-file .env -f docker-config/docker-compose.yml up -d
docker compose --env-file .env -f docker-config/docker-compose.yml ps
```

完整运行需要 Docker Desktop Linux Engine，建议系统盘至少保留 10 GB。宿主机
`3306` 或 `6379` 冲突时，可在本地 `.env` 中改用 `MYSQL_PORT=3307` 或
`REDIS_PORT=6380`，不要修改容器内部的 `mysql:3306`、`redis:6379`。

## 6. 测试与验收策略

前两轮完成规格建立了 60 项确定性测试。本轮加入 4 项 ORM/UTC 兼容性回归后，
当前工作树共 64 项；测试使用 SQLite 等隔离依赖，不访问开发 MySQL、Redis、
Moonshot 或 Tavily。

覆盖范围包括：

- LangGraph/FastAPI 入口、生命周期和健康检查。
- 缺失模型配置、Redis 降级、代码执行开关和 Agent 错误映射。
- JWT 配置、注册、登录、`/me`、Token 异常和 CORS。
- 双用户会话读写删隔离及输入校验无部分写入。
- SQLAlchemy 共享元数据、UTC 默认值、序列化和会话排序。

文档或窄范围改动至少执行相关检查和定向 `git diff --check`。发布候选还必须执行
前端类型、零警告 Lint、格式、构建、Compose 解析、凭据扫描、当前源码镜像重建
及五服务双用户冒烟。没有 Docker 运行证据时，不得声称容器验收通过。

## 7. 安全现状

### 已落实

- JWT 密钥来自环境变量；无有效密钥时认证与会话接口返回稳定 503，健康检查可用。
- JWT `sub` 使用用户 ID，认证依赖校验签名、算法、有效期和用户存在性。
- CORS 使用明确白名单，启用凭据时不允许通配符。
- 会话和消息在服务层同时按 `session_id` 与 `user_id` 过滤；越权统一返回 404。
- 第一方 Token 使用 `sessionStorage`，不写 URL、日志或错误提示。
- 代码执行默认关闭；配置和日志具有占位值识别与敏感值脱敏边界。

### 仍有限制

- 本地 LangGraph 使用 noop 认证，第一方 JWT 只保护 FastAPI 认证与会话接口。
- 没有 Refresh Token、密码找回、邮箱验证、OAuth、RBAC、管理员审计或请求限流。
- 任意 Python 执行显式开启后仍无沙箱；本地文档分析只适用于受控文件。
- 数据库没有版本化迁移工具，仍由 `Base.metadata.create_all()` 初始化。
- 旧的已失效服务凭据仍在 Git 历史中；历史清理由人工在干净工作区另行处理。

## 8. 当前发布债

- 发布就绪迭代仍需完成自动 CI 与配置漂移防护。
- 当前前端类型检查、零警告 Lint 和格式检查通过。
- 当前本机 Node.js 25.2.1 超出支持的 22.x 范围，前端全量门禁必须在受支持版本
  复验，不能以该环境中的局部检查替代发布证据。
- 当前源码镜像的五服务健康检查、双用户认证隔离和 CORS 冒烟仍是最终发布门槛。
- 观测性目前只有基础脱敏日志和 `request_id`；统一 Trace、指标、告警和发布看板
  属于后续候选，不应写成现有能力。

## 9. 相关文档

- `README.md`：本地开发、配置、Docker 和验证命令。
- `.trae/documents/project_analysis.md`：实际架构、能力边界和技术债。
- `.trae/documents/roadmap.md`：已完成、当前和后续候选迭代。
- `CHANGELOG.md`：版本化行为变化、验证证据和已知风险。
- `.trae/specs/establish-runnable-baseline/`：可运行闭环规格。
- `.trae/specs/secure-user-sessions/`：第一方认证与隔离规格。
- `.trae/specs/enforce-release-readiness/`：当前发布治理规格。
