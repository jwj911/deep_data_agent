# Deep Data Agent

Deep Data Agent 是一个前后端分离的 AI 数据探索项目。后端同时提供
FastAPI REST 服务和 LangGraph 图服务，前端使用 Next.js 静态导出，
MySQL 用于用户、会话与消息持久化，Redis 用于可降级缓存。第一方注册、
登录与会话所有权校验由 FastAPI 提供。

## 服务与访问地址

| 服务 | 默认地址 | 用途 |
| --- | --- | --- |
| 前端 | `http://localhost:3000/data_copilot/` | 聊天界面 |
| LangGraph | `http://localhost:2024/info` | 线程与流式 Agent API |
| FastAPI | `http://localhost:8000/api/health` | REST API 与健康检查 |
| MySQL | `localhost:3306` | 用户、会话和消息持久化 |
| Redis | `localhost:6379` | Agent 与搜索结果缓存 |

## 环境准备

- Python 3.12
- Node.js 22.11 或更高的 22.x 版本
- pnpm 10.5.1
- Docker Desktop（运行完整容器栈时需要 Linux Engine）
- Docker 构建与运行前，建议确认系统盘至少有 10 GB 可用空间

复制 `.env.example` 为 `.env`，再填写本地密钥：

```powershell
Copy-Item .env.example .env
```

`MOONSHOT_API_KEY` 是模型查询所需配置，`TAVILY_API_KEY` 仅在调用互联网
搜索工具时需要。示例文件中的占位值不会被当作有效密钥；真实 API Key、
JWT 密钥、密码和 Token 只能写入本地 `.env` 或部署环境，不能写入文档或提交。

## 本地开发

安装并验证后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python -m isort --check-only data_agent tests
```

分别启动 FastAPI 与 LangGraph：

```powershell
python -m uvicorn data_agent.agent_server:app --host 0.0.0.0 --port 8000
langgraph dev --host 0.0.0.0 --port 2024 --no-browser --allow-blocking
```

FastAPI 只在应用生命周期启动时初始化数据库。导入
`data_agent.agent_graph:agent` 不要求 MySQL 可连接。

安装、验证并启动前端：

```powershell
Set-Location agent_chatui
pnpm install --frozen-lockfile
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
pnpm dev
```

前端默认连接 `http://localhost:2024` 上的 `agent` 图。也可以在构建前通过
`NEXT_PUBLIC_API_URL` 和 `NEXT_PUBLIC_ASSISTANT_ID` 修改。公开 URL 会写入静态
产物，必须是浏览器可访问的地址，不能使用 `langgraph` 等仅容器内部可解析的
主机名。

## Docker Compose

在仓库根目录执行：

```powershell
docker compose --env-file .env -f docker-config/docker-compose.yml config
docker compose --env-file .env -f docker-config/docker-compose.yml build
docker compose --env-file .env -f docker-config/docker-compose.yml up -d
docker compose --env-file .env -f docker-config/docker-compose.yml ps
```

Compose 会启动 `mysql`、`redis`、`fastapi`、`langgraph` 和 `frontend`，
并通过健康检查控制依赖顺序。宿主机进程使用 `DATABASE_URL` 和 `REDIS_URL`；
容器内后端改用 `COMPOSE_DATABASE_URL` 和 `COMPOSE_REDIS_URL`，默认通过
`mysql:3306` 和 `redis:6379` 服务地址连接，不继承宿主机的 `localhost`
地址。修改 MySQL 凭据或数据库名时，需要同步更新 `MYSQL_ROOT_PASSWORD`、
`MYSQL_DATABASE` 和 `COMPOSE_DATABASE_URL`。修改对外端口时，可在 `.env` 中设置
`MYSQL_PORT`、`REDIS_PORT`、`FASTAPI_PORT`、`LANGGRAPH_PORT` 和
`FRONTEND_PORT`。若宿主机的 `3306` 或 `6379` 已被占用，可分别设置
`MYSQL_PORT=3307` 或 `REDIS_PORT=6380`；容器内部仍使用 `mysql:3306` 和
`redis:6379`，无需修改 Compose 内部地址。

停止服务但保留数据：

```powershell
docker compose --env-file .env -f docker-config/docker-compose.yml down
```

删除 MySQL 与 Redis 数据卷需显式执行：

```powershell
docker compose --env-file .env -f docker-config/docker-compose.yml down -v
```

## 认证边界

本地 LangGraph 聊天默认使用 noop 认证，不校验 JWT。浏览器没有 LangSmith
API Key 时，前端会省略对应请求头；LangSmith API Key 存储于浏览器
`localStorage`，仅在存在非空值时发送，且只用于向 LangGraph 服务鉴权。

前端的第一方登录态与 LangGraph 相互独立，由 FastAPI REST API 提供：

- 注册：`POST /api/auth/register`，提交用户名、邮箱和密码，返回用户公开字段。
- 登录：`POST /api/auth/login`，使用 OAuth2 密码表单（`username`、`password`），
  成功后返回 `access_token`、`token_type=bearer` 和 `expires_in`（单位为秒）。
- 当前用户：`GET /api/auth/me`，返回持有有效 Token 的用户信息。

签发的 JWT 以用户 ID 作为 `sub`。未配置 JWT 密钥时，认证相关端点返回 503
`auth_not_configured`；Token 无效、过期或越权时统一返回 401，不泄露具体原因。
会话资源（`/api/sessions`）按当前用户隔离，访问不属于自己的会话返回 404。

前端第一方 Token 存储于 `sessionStorage`（不是 `localStorage`），仅对 FastAPI
（`NEXT_PUBLIC_REST_API_URL`，默认 `http://localhost:8000`）请求附加
`Authorization: Bearer`。LangGraph 或其他第三方服务返回 401/403 不会清理第一方
登录态；只有第一方 FastAPI 返回 401 时，前端才会清除 Token 并跳转回登录页。

后端认证由以下环境变量控制：

- `JWT_SECRET_KEY`：签名密钥，至少 32 个字符；占位值或过短时视为未配置，
  认证端点将返回 503。
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`：访问令牌有效期（分钟），默认 30。
- `CORS_ALLOWED_ORIGINS`：以逗号分隔的来源白名单，默认 `http://localhost:3000`。
  由于启用了凭据，白名单不允许 `*`，且每一项都必须是绝对来源（含协议）。白名单
  内来源的预检请求会返回允许的方法与请求头，非白名单来源不会获得放行。

在本地生成强随机密钥：

```powershell
[Convert]::ToBase64String((1..36 | % {Get-Random -Max 256}))
```

只将生成结果写入本地 `.env` 的 `JWT_SECRET_KEY`，或通过环境变量注入；不要将
命令输出粘贴到终端记录、文档、Issue 或提交中。密钥、Token 和 `.env` 绝不进入
版本控制。

## 高风险工具

任意 Python 代码执行工具默认关闭：

```dotenv
ENABLE_CODE_EXECUTION=false
```

只有在受控的本地环境中人工设置 `ENABLE_CODE_EXECUTION=true` 才会注册该工具。
当前实现不是安全沙箱，不应在面向不可信用户的环境中启用。

## 验证清单

后端确定性测试不调用真实模型或搜索服务。前两轮完成规格建立了 60 项基线测试；
当前发布治理工作树加入 ORM/UTC 兼容性回归后共 64 项，覆盖健康检查、LangGraph
导出、缺失模型配置、Redis 降级、代码执行默认关闭、查询错误映射、第一方认证、
CORS、双用户会话隔离和时间字段兼容：

```powershell
python -m pytest
python -m isort --check-only data_agent tests
```

前端质量门禁：

```powershell
Set-Location agent_chatui
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
Set-Location ..
```

Compose 静态校验和工作区检查：

```powershell
docker compose --env-file .env -f docker-config/docker-compose.yml config --quiet
docker buildx bake -f docker-config/docker-compose.yml --print
git diff --check
git status --short
```

完整冒烟检查还需 Docker Linux Engine 正常运行，并在 `.env` 中提供有效模型
密钥及至少 32 个字符的 JWT 密钥。启动后依次访问前端、FastAPI 健康端点和
LangGraph `/info`，再从前端创建线程并向 `agent` 图提交一条消息。所有冒烟和
数据分析验证必须人工触发，输入使用脱敏或专用测试数据；密钥、Token、`.env`
和业务数据不得提交到版本控制。

配置有效 `JWT_SECRET_KEY` 后，第一方认证冒烟检查建议覆盖：注册并登录两个
不同用户，各自通过 `GET /api/auth/me` 确认身份；用一个用户的 Token 访问另一个
用户的会话应返回 404；不带 Token 访问 `/api/sessions` 应返回 401；分别用白名单
与非白名单来源发起预检，确认前者获得放行、后者不返回允许头。

## 凭据安全

旧硬编码的 Moonshot 与 Tavily 凭据均已轮换，新凭据仅保存在本地 `.env`。
本轮接受已失效旧值仍留在 Git 历史中的风险；因当前工作区存在未提交改动，
历史清理延期。后续须在干净分支使用专门的历史清理工具，并与所有协作者协调
强制推送及重新拉取。

## 发布文档

- `.trae/documents/project_analysis.md`：当前架构、能力边界、质量状态与技术债。
- `.trae/documents/roadmap.md`：已完成基线、当前发布治理和后续候选迭代。
- `CHANGELOG.md`：版本化行为变化、验证证据与已知风险。
