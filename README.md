# Deep Data Agent

Deep Data Agent 是一个前后端分离的 AI 数据探索项目。后端同时提供
FastAPI REST 服务和 LangGraph 图服务，前端使用 Next.js 静态导出，
MySQL 用于用户、会话、消息与受管文件 metadata，Redis 用于缓存、限流、Agent
并发租约与就绪保护。第一方注册、登录与角色由 FastAPI 提供；同一 JWT 同时保护
FastAPI Agent 入口与 LangGraph thread/run 所有权。前端、FastAPI、LangGraph、
Agent、工具与缓存使用请求 ID 和结构化脱敏事件形成轻量诊断链路。

## 服务与访问地址

| 服务 | 默认地址 | 用途 |
| --- | --- | --- |
| 前端 | `http://localhost:3000/data_copilot/` | 聊天界面 |
| LangGraph | `http://localhost:2024/info` | 线程与流式 Agent API |
| FastAPI | `http://localhost:8000/api/live` | REST API 与进程存活检查 |
| MySQL | `localhost:3306` | 用户、会话和消息持久化 |
| Redis | `localhost:6379` | 缓存、限流、Agent 并发租约与就绪保护 |

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

Agent、模型与搜索的默认预算如下。模型与搜索上限只能收紧；Agent 配置必须为
正整数，并满足模型/搜索 timeout 不超过 run deadline、单用户并发不超过全局并发、
租约 TTL 大于 run deadline 等关系：

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| `MODEL_REQUEST_TIMEOUT_SECONDS` / `MODEL_MAX_RETRIES` / `MODEL_MAX_OUTPUT_TOKENS` | 45 秒 / 1 次 / 4,096 tokens | 单次模型请求预算 |
| `AGENT_QUERY_MAX_CHARS` / `AGENT_RESPONSE_MAX_CHARS` | 8,000 / 32,000 个字符 | FastAPI 输入与最终响应上限 |
| `AGENT_RUN_TIMEOUT_SECONDS` / `AGENT_RECURSION_LIMIT` | 60 秒 / 25 层 | run 总 deadline 与递归上限 |
| `AGENT_MODEL_CALL_LIMIT` / `AGENT_TOOL_CALL_LIMIT` | 8 次 / 12 次 | 每个 run 的模型与工具调用上限 |
| `AGENT_GLOBAL_CONCURRENCY_LIMIT` / `AGENT_USER_CONCURRENCY_LIMIT` | 4 / 1 | Redis 原子全局与用户租约上限 |
| `AGENT_CONCURRENCY_WAIT_SECONDS` / `AGENT_CONCURRENCY_LEASE_TTL_SECONDS` | 1 秒 / 75 秒 | 租约等待与异常回收边界 |
| `SEARCH_QUERY_MAX_CHARS` / `SEARCH_MAX_RESULTS` | 2,000 个字符 / 5 条 | 搜索输入与结果数上限 |
| `SEARCH_TIMEOUT_SECONDS` / `SEARCH_MAX_OUTPUT_BYTES` | 15 秒 / 65,536 字节（64 KiB） | 搜索调用与序列化输出上限 |

Redis 连接故障后按 `REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS=1` 到
`REDIS_RECOVERY_MAX_BACKOFF_SECONDS=30` 的指数退避执行单飞探测，默认抖动比例
`REDIS_RECOVERY_JITTER_RATIO=0.2`；恢复后无需重启。固定策略为：

| 调用面 | Redis 不可用时 |
| --- | --- |
| Agent/搜索缓存 | fail-open 为 miss/未写入 |
| `auth` / `session` / `default` 限流 | fail-open，并记录脱敏降级状态 |
| `/api/query` 限流 | fail-closed，返回 503 |
| FastAPI/LangGraph Agent 并发租约 | fail-closed，返回 `agent_protection_unavailable` |
| `/api/ready` | 返回 503，固定标记 Redis 未就绪 |

## 本地开发

安装并验证后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python -m isort --check-only data_agent tests scripts
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

## 数据库迁移

项目使用 Alembic 版本化管理数据库 schema。FastAPI 生命周期启动时调用
`init_db()` 会自动将数据库升级到最新的 head，无需手动建表。若数据库已由早期
`Base.metadata.create_all()` 建立（存在业务表但没有 Alembic 版本记录），首次
启动会被标记（stamp）到初始基线，既不重建也不删除已有数据。

迁移使用的数据库地址与应用共用同一来源，取自 `DATABASE_URL`（容器内为
`COMPOSE_DATABASE_URL`）；`alembic.ini` 不写入任何真实凭据。生成迁移须在受控
环境经人工评审后执行，真实密钥、密码和连接串不进入版本控制。

常用命令使用系统或 venv 的 `python`：

```powershell
python -m alembic -c alembic.ini revision --autogenerate -m "描述"
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini heads
python -m alembic -c alembic.ini history
```

`revision --autogenerate` 依据模型与当前 schema 的差异生成迁移草稿，须先人工
评审再纳入版本库；`upgrade head` 将数据库升级到最新版本；`current`、`heads` 和
`history` 分别查看当前版本、head 列表和迁移历史。

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

删除 MySQL、Redis 与受管文件数据卷需显式执行：

```powershell
docker compose --env-file .env -f docker-config/docker-compose.yml down -v
```

健康端点采用分层语义：

- `GET /api/live` 只证明进程事件循环可响应，不访问 MySQL、Redis、Agent、模型或
  搜索；`GET /api/health` 暂时保留为同语义兼容别名。
- `GET /api/ready` 浅检查模型必要配置、MySQL `SELECT 1`、Alembic 唯一 head、
  Redis 和受管文件根。全部就绪返回 200，任一组件失败返回 503；响应只包含固定
  组件状态和请求 ID。
- FastAPI Compose healthcheck 使用 `/api/ready`；LangGraph 同时检查 `/info`
  与本地 readiness helper。健康检查不调用模型或搜索。

## 认证边界

FastAPI 与 LangGraph 共用第一方 JWT 签名配置、HS256 算法、过期时间和正整数
用户 ID `sub` 语义。LangGraph 每次请求都从 MySQL 重新加载用户与当前角色，
并以数据库用户 ID 字符串作为 owner；调用方提供的 owner metadata 会被服务端
覆盖。thread 的创建、搜索、读取、history/state、更新、复制、删除和 create_run
均按 owner 过滤，管理员也不绕过所有权；未声明资源和 assistant 写操作默认拒绝。

FastAPI REST API 提供：

- 注册：`POST /api/auth/register`，提交用户名、邮箱和密码，返回用户公开字段。
- 登录：`POST /api/auth/login`，使用 OAuth2 密码表单（`username`、`password`），
  成功后返回 `access_token`、`token_type=bearer` 和 `expires_in`（单位为秒）。
- 当前用户：`GET /api/auth/me`，返回持有有效 Token 的用户信息。

签发的 JWT 以用户 ID 作为 `sub`。未配置 JWT 密钥时，FastAPI 认证端点返回 503
`auth_not_configured`；Token 无效或过期时，FastAPI 返回 401，锁定的 LangGraph
`0.7.28` 认证中间件返回 403，均不泄露具体原因；FastAPI 权限不足返回 403。
会话资源
（`/api/sessions`）按当前用户隔离，访问不属于自己的会话返回 404；
`/api/query` 要求 `agent.invoke_own`，并在路由和 AgentService 两层授权。

前端第一方 Token 存储于 `sessionStorage`（不是 `localStorage`），仅对 FastAPI
（`NEXT_PUBLIC_REST_API_URL`，默认 `http://localhost:8000`）和固定的 LangGraph
Origin（`NEXT_PUBLIC_API_URL`，默认 `http://localhost:2024`）请求附加
`Authorization: Bearer`。浏览器不再接受 `apiUrl`/`assistantId` 查询参数或连接
表单覆盖 Agent 目标，不再读取或发送 LangGraph API Key；启动时只删除旧
`localStorage` 键 `lg:chat:apiKey`。只有第一方 FastAPI 返回 401 时，前端才会
清除 Token 并跳转回登录页。

Chat UI 以 LangGraph threads 作为对话列表、状态和运行历史的主数据；MySQL
users/RBAC 是身份主数据。既有 MySQL sessions/messages REST API 保留原有所有权
语义，但不与 LangGraph 双写，也不宣称两套历史同步。

## 受管文件

文件摄取采用 owner 绑定的受管存储，不接受服务器绝对/相对路径。浏览器先把文件
上传到固定 FastAPI REST Origin，MySQL `managed_files` 保存 owner 与安全 metadata，
FastAPI/LangGraph 共享卷保存原始字节；LangGraph thread 只保存随机 UUID
`file_id` 引用，不保存 Data URL 或 Base64 正文。

当前只允许严格 UTF-8 的 `.txt`、`.md`、`.csv`、`.json`。JPEG、PNG、GIF、WebP、
PDF、Office、压缩包及其他二进制格式在专用解析器和资源预算完成前保持拒绝。
CSV 中去除前导空白后以 `=`, `+`, `-`, `@` 开头的单元格会被整批拒绝；JSON 必须
完整通过标准解析器。

默认边界：

- 每批和每条消息最多 5 个文件。
- 单文件最大 5 MiB，批次最大 10 MiB。
- 每用户最多 100 个文件、总计 100 MiB。
- 默认保留 168 小时；列表、上传或分析时惰性清理当前用户的过期文件。
- `analyze_document` 只接受 owner 绑定的 UUID `file_id`，模型不能传入路径；
  管理员也不能读取其他用户文件。

文件 API：

- `POST /api/files`：multipart 批量上传。
- `GET /api/files`：列出当前用户未过期文件。
- `GET /api/files/{file_id}`：读取安全 metadata。
- `GET /api/files/{file_id}/analysis`：读取有界文本分析。
- `DELETE /api/files/{file_id}`：删除当前用户文件。

相关配置包括 `FILE_STORAGE_ROOT`、`FILE_UPLOAD_MAX_BYTES`、
`FILE_UPLOAD_BATCH_MAX_BYTES`、`FILE_UPLOAD_REQUEST_MAX_BYTES`、
`FILE_UPLOAD_BATCH_MAX_COUNT`、`FILE_USER_QUOTA_BYTES`、
`FILE_USER_MAX_COUNT`、`FILE_RETENTION_HOURS` 和
`FILE_ANALYSIS_MAX_CHARS`。容器通过 `COMPOSE_FILE_STORAGE_ROOT` 使用共享卷；
本地卷没有备份，不得据此扩大 `RR-001` 的数据恢复边界。

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

## 角色权限与管理员引导

用户只有 `user` 和 `admin` 两种固定角色。新注册用户以及从旧 schema 升级的既有
用户均默认为 `user`；注册参数、用户名、邮箱和环境变量不能自动授予管理员角色。
注册响应和 `/api/auth/me` 会返回当前角色，但浏览器中的角色字段只用于展示和
协议校验，不能替代后端授权。

权限矩阵采用默认拒绝策略，并在 FastAPI 路由和服务层分别检查。两种角色都只能
读写删除自己的会话与受管文件；`admin` 额外拥有以下管理 API：

- `GET /api/admin/users?offset=0&limit=50`：按用户 ID 稳定分页列出用户，
  `limit` 范围为 `1..100`。
- `PATCH /api/admin/users/{user_id}/role`：把另一个用户的角色设为 `user` 或
  `admin`。管理员不能修改自己的角色。

首位管理员必须由授权人员在受控环境中按内部用户 ID 人工建立。先以普通用户登录，
从 `/api/auth/me` 获取 ID，再在仓库根目录执行：

```powershell
python scripts/bootstrap_admin.py --user-id <用户 ID>
```

脚本只允许把既有用户提升为 `admin`，重复执行保持幂等，不接受用户名、邮箱、
密码或 Token。角色变更后无需重新签发 JWT；后续请求会从数据库加载最新角色。

管理员列表、角色变更、引导操作和授权拒绝均写入现有 UTC 结构化日志。用户身份
只记录由服务端 JWT 密钥派生的 HMAC 引用，不记录原始用户 ID、用户名、邮箱、
Token、IP 或请求体。本轮不提供管理员前端界面、可编辑角色、跨用户会话访问、
长期审计数据库或外部 SIEM。

## 请求限流

FastAPI 层在请求 ID 绑定之后、业务处理之前，对认证端点、高成本 `/api/query`、
会话/文件端点和全局默认类别按身份维度做 Redis 固定窗口限流。四类配额相互独立、
计数隔离：某一类超限不影响其他类别。

身份维度按稳定标识计数：认证请求按 JWT `sub`（仅无副作用地校验签名与有效期，
不查库），匿名请求按客户端来源。不同用户、不同来源的计数相互隔离，一个身份
超限不影响另一个身份。

超限返回稳定 `429`，错误体为 `{code: "rate_limited", message, request_id}`，并
携带 `Retry-After` 秒数；窗口重置后同一身份恢复放行。`/api/live`、
`/api/health` 和 `/api/ready` 永不被限流，也不计入任何配额。

`TRUSTED_PROXY_COUNT` 默认 `0`，即不信任 `X-Forwarded-For`，来源以直接连接地址
为准，伪造转发头不会改变计数键。Redis 不可用或计数出错时，
`auth`/`session`/`default` 限流 fail-open；高成本 `/api/query` 限流 fail-closed，
在 Agent 前返回 503。两类路径都记录固定、脱敏的保护状态，事件不含原始 Token、
明文来源、提示词或业务数据。设 `RATE_LIMIT_ENABLED=false` 可整体关闭 HTTP
固定窗口限流，但不会关闭 Agent 的 Redis 并发租约。

当前限流是单实例本地 Redis 固定窗口，不是分布式令牌桶，也不含自动封禁或黑名单。
相关环境变量与默认值如下：

- `RATE_LIMIT_ENABLED`：限流总开关，默认 `true`。
- `TRUSTED_PROXY_COUNT`：信任的反向代理跳数，默认 `0`（不信任 `X-Forwarded-For`）。
- `RATE_LIMIT_AUTH_MAX_REQUESTS`、`RATE_LIMIT_AUTH_WINDOW_SECONDS`：认证端点配额，
  默认每 `60` 秒 `10` 次。
- `RATE_LIMIT_QUERY_MAX_REQUESTS`、`RATE_LIMIT_QUERY_WINDOW_SECONDS`：`/api/query`
  配额，默认每 `60` 秒 `20` 次。
- `RATE_LIMIT_SESSION_MAX_REQUESTS`、`RATE_LIMIT_SESSION_WINDOW_SECONDS`：会话端点
  配额，默认每 `60` 秒 `60` 次。
- `RATE_LIMIT_DEFAULT_MAX_REQUESTS`、`RATE_LIMIT_DEFAULT_WINDOW_SECONDS`：全局默认
  配额，默认每 `60` 秒 `120` 次。

各配额上限与窗口秒数均须为正整数，非法值在启动时抛出稳定 `ConfigurationError`。

## 可观测性与诊断

FastAPI 接受严格的 32 位小写十六进制 `X-Request-ID`。合法值会在响应头中原样
返回；缺失或非法值会被替换，非法原值不会写入日志。CORS 白名单来源可以发送并
读取该响应头。前端 REST 请求和每次 LangGraph 提交、重试或人工中断处理都会
生成独立 ID；认证失败页面会显示可用于排障的诊断 ID。

后端日志使用单行 JSON，包含 UTC 时间、服务名、事件名、结果、耗时和可用的
请求 ID。事件只允许固定低基数字段，不记录提示词、消息正文、用户名、邮箱、
请求体、查询参数、客户端 IP、工具输入输出或原始异常文本。凭据、Token、密码和
连接串会再次脱敏。

本阶段不部署外部 OpenTelemetry、Prometheus、Grafana 或自动告警渠道。日志写入
标准输出和本地轮转文件；默认单文件上限 10 MiB、保留 3 份备份。Docker
`json-file` 日志默认每份 10 MiB、保留 3 份。相关变量如下：

- `SERVICE_NAME`：结构化日志服务名。
- `LOG_FILE_PATH`：轮转文件路径；设为空可关闭文件输出。
- `LOG_MAX_BYTES`：单个文件上限，必须为正整数。
- `LOG_BACKUP_COUNT`：备份数量，必须为正整数。
- `DOCKER_LOG_MAX_SIZE`、`DOCKER_LOG_MAX_FILES`：容器日志上限。

诊断导出必须由人工触发。按请求 ID 生成倒序时间线：

```powershell
python scripts/export_diagnostics.py `
  --input deep_data_agent.log `
  --request-id 0123456789abcdef0123456789abcdef `
  --output diagnostic-report.json
```

省略 `--request-id` 可生成发布诊断摘要。报告会折叠健康检查，汇总请求数、
HTTP 错误率、平均/最大/P95 延迟、缓存降级和模型失败，并产生本地告警信号，
但不会上传或外发。输入中的无效行只计数，不回显原文；报告仍须在分享前人工
复核，且不得使用包含真实业务数据的日志做自动验证。

## Agent 资源预算

Agent 默认限制为：run 60 秒、递归 25 层、模型调用 8 次、工具调用 12 次，
全局并发 4、单用户并发 1，租约等待 1 秒、TTL 75 秒。FastAPI 查询最多
8,000 个字符、最终响应最多 32,000 个字符；timeout、取消、并发拒绝、模型/工具
调用超限和超大响应均使用稳定错误码，失败结果不写缓存。客户端 config/context
和管理员角色都不能扩大预算。

ChatOpenAI 单次请求固定为 45 秒 timeout、1 次 retry 和 4,096 最大输出 tokens。
互联网搜索只允许 `general`/`news`，query 最多 2,000 个字符、结果最多 5 条、
15 秒 timeout，输出最多 64 KiB；模型 schema 不再暴露 raw content 或
images/videos/files topic。`analyze_document` 继续限制为 20,000 个字符，并计入
同一 tool-call 总预算。

任意 Python 代码执行已永久移出运行时。部署环境中残留的
`ENABLE_CODE_EXECUTION` 会被忽略，不能注册或调用 `execute_python_code`。

## 验证清单

后端确定性测试不调用真实模型或搜索服务。测试覆盖健康检查、LangGraph JWT Auth、
thread/run owner 默认拒绝、assistant 只读边界、Agent 双层授权与租户缓存、
受管文件格式/配额/事务/owner/路径/符号链接/哈希/保留、LangGraph 导出、
缺失模型配置、Redis 降级、代码执行残留变量无效、查询错误映射、第一方认证、CORS、
双用户会话隔离、RBAC 管理、管理员引导、角色迁移、时间字段兼容、请求 ID、
结构化脱敏事件、诊断报告、发布镜像资产和容器冒烟辅助逻辑：

```powershell
python -m pytest
python -m pytest -q tests/test_migrations.py
python -m pytest -q tests/test_release_contracts.py
python -m isort --check-only data_agent tests scripts
python scripts/check_release_contracts.py
python -m alembic -c alembic.ini heads
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

`bound-agent-resource-use` 已取得 2026-08-21 本地证据：Python 3.12.9 下全量
**452 项通过**，迁移定向测试 **8 项通过**，release contract pytest
**159 项通过**；isort、发布契约脚本、Alembic 唯一 head、Compose 和
`git diff --check` 通过。Node.js 22.22.2、pnpm 10.5.1 下 `typecheck`、零警告
`lint`、`format:check` 和 `build` 全部通过。

Docker Engine 29.4.1、Docker Desktop 4.71.0、Compose 5.1.3 下，当前源码镜像的
empty、head、legacy 场景以及 Redis stop/start canary 全部通过。canary 证明 Redis
停止时 liveness 保持 200、readiness 转为 503、Agent fail-closed，Redis 恢复后
后端无需重启即重新 ready。全程模型与搜索调用均为 0，容器、网络、卷、临时配置
和生成物已清理。

`bound-agent-resource-use` implementation SHA
`1090c3ea0954e84cc2cb6b945ef8c3913393cec8` 的 GitHub Actions
[run `32431502248`](https://github.com/jwj911/deep_data_agent/actions/runs/32431502248)
（2026-08-21T00:08:27Z..00:11:51Z）为 `completed/success`，且 `head_sha`
精确匹配 implementation SHA：

- [Backend `96623829169`](https://github.com/jwj911/deep_data_agent/actions/runs/32431502248/job/96623829169)：`success`
- [Frontend `96623829344`](https://github.com/jwj911/deep_data_agent/actions/runs/32431502248/job/96623829344)：`success`
- [Release Contracts `96623829444`](https://github.com/jwj911/deep_data_agent/actions/runs/32431502248/job/96623829444)：`success`
- [Container Smoke `96623829378`](https://github.com/jwj911/deep_data_agent/actions/runs/32431502248/job/96623829378)：`success`

以上只证明 implementation 提交。最终验收文档提交只有在其自身 exact SHA 的
Backend、Frontend、Release Contracts、Container Smoke 全部成功后才成立；创建
本文档内容时最终 SHA 与 run ID 尚未知，因此不记录推测值，也不能用
`32431502248` 替代最终 Hosted 证据。

以下提交与运行标识记录其他既有 change-id 的历史远端证据：

implementation SHA `9fe0c40bd66a01db427fe37169a0ec0f65f24f85` 的 GitHub Actions
run `32008059164` 为 `completed/success`；Backend、Frontend、Release Contracts、
Container Smoke 四个 Job 全部成功，Container Smoke 的空库双用户、head 重启、
legacy 升级和 cleanup 均成功。

前一 `restore-runtime-release-gates` implementation SHA
`30e7992fa48c350a0b0ae8a6faa12c80cfe2202d` 的 GitHub Actions run
`31959537002` 已为 `completed/success`。`secure-agent-tenant-boundaries`
implementation SHA
`9699f90f6fd2a90d63d82728208fb656cb4fe8e3` 的 run `31994602064` 也为
`completed/success`；Backend、Frontend、Release Contracts、Container Smoke
四个 Job 全部成功，Container Smoke 的空库双用户、head 重启、legacy 升级和
cleanup 均成功。需要真实模型的产品行为冒烟仍须由授权人员人工触发，并使用脱敏
或专用测试数据；密钥、Token、`.env` 和业务数据不得提交到版本控制。本轮不关闭
`AUD-006` 的依赖/镜像/Actions 可重复性，也不关闭 `AUD-007` 的未知或漂移 schema
fail-closed 边界。

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

- `.trae/documents/project_analysis.md`：2026-08-12 项目整体审计快照、当前架构、
  历史识别的 18 个 2/2 高置信度问题，以及当前开放的 8 项
  （0 P0 / 1 P1 / 6 P2 / 1 P3）；生产发布判断仍为 NO-GO。
- `.trae/documents/roadmap.md`：11 个已完成 change-id 和 8 个候选迭代；
  `bound-agent-resource-use` 已完成，下一候选为 `prove-data-recovery`。
- `CHANGELOG.md`：版本化行为变化、验证证据与已知风险。
- `.trae/specs/audit-project-roadmap/`：项目整体审计与后续迭代规划规格。
- `.trae/specs/add-rbac-audit/`：固定角色、双层授权、管理员 API、人工引导和
  脱敏审计规格。
- `.trae/specs/restore-runtime-release-gates/`：已完成的镜像迁移资产、全仓库
  凭据扫描和容器发布门禁规格；Hosted 四个 Job 已在 implementation SHA
  `30e7992fa48c350a0b0ae8a6faa12c80cfe2202d` 上验证成功。
- `.trae/specs/secure-agent-tenant-boundaries/`：已完成本地与 Hosted 验收的
  Agent 第一方身份、租户所有权和固定浏览器 Origin 规格。
- `.trae/specs/isolate-file-ingestion/`：已完成本地与 Hosted 验收的 owner 受管
  文件、格式/配额和无 Base64 摄取规格。
