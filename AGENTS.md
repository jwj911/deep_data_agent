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
- MySQL：持久化用户、会话、消息和受管文件 metadata。
- Redis：缓存 Agent 与搜索结果；不可用时降级为未命中。
- Docker Compose：编排 5 个服务，并让 FastAPI/LangGraph 共享受管文件卷。

仓库现有 10 个已完成 change-id；最近完成本地与 Hosted 验收的是
`.trae/specs/isolate-file-ingestion/`，以 owner 受管 UUID 文件替代任意服务器
路径与浏览器 Base64 摄取。implementation SHA
`9fe0c40bd66a01db427fe37169a0ec0f65f24f85` 的 run `32008059164` 已成功。

2026-08-12 项目整体审计以 `f6cf4e65d8b15114fc164fd6921bd65d6ad27862` 为基线，
历史识别 18 个 2/2 高置信度问题（4 P0 / 3 P1 / 10 P2 / 1 P3）。当前工作树已关闭
`AUD-014`、`AUD-011`、`AUD-015`、`AUD-001`、`AUD-003`、`AUD-002`、`AUD-005`，
仍开放 11 项（0 P0 / 3 P1 / 7 P2 / 1 P3），
生产发布判断仍为 NO-GO；`AUD-006`、`AUD-007` 等边界不因本轮容器证据而关闭。
Roadmap 现有 9 个未启动候选，下一候选继续按风险驱动排序。

本轮本地证据为 Python 3.12.9 下 295 项测试、迁移定向测试 8 项；Node.js
22.22.2、pnpm 10.5.1 下 typecheck、零警告 lint、format:check、build 全部通过，
构建已移除 Google Fonts 网络依赖。当前源码镜像的空库双用户受管文件、head 重启
和 legacy 升级均通过；无凭据 Chromium mock 验证附件预览/删除。过程未调用外部
模型/搜索或发送业务查询，容器、网络、卷、临时配置和生成物已完整清理。

本轮 Hosted 证据为上述 SHA 的 Backend、Frontend、Release Contracts、Container
Smoke 四个 Job 均为 `success`；Container Smoke 的空库双用户、head 重启、
legacy 升级和 cleanup 均为 `success`。

## 3. 关键结构

```text
deep_data_agent/
├── .env.example
├── AGENTS.md
├── CHANGELOG.md
├── README.md
├── alembic.ini
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
│   ├── observability/
│   ├── routes/
│   ├── security/
│   ├── services/
│   └── tools/
├── docker-config/
│   └── docker-compose.yml
├── migrations/
│   ├── env.py
│   └── versions/
└── scripts/
    ├── bootstrap_admin.py
    ├── check_release_contracts.py
    ├── export_diagnostics.py
    └── verify_container_smoke.py
```

### 3.1 服务入口

- `langgraph.json` 导出 `data_agent.agent_graph:agent`，并加载
  `data_agent.security.langgraph_auth:auth`。LangGraph Auth 读取 MySQL 用户和
  当前角色，但不负责建表。
- `data_agent.agent_server:app` 是 FastAPI ASGI 入口，数据库初始化只发生在应用
  生命周期。
- `/api/health` 不触发模型调用；`/api/query` 要求 `agent.invoke_own`，并将配置
  错误和上游错误映射为稳定的非 2xx 响应。
- `data_agent/routes/auth.py` 提供注册、登录和 `/me`；
  `data_agent/routes/session.py` 提供受保护的会话与消息接口。
- `data_agent/routes/admin.py` 提供受 RBAC 保护的用户列表和他人角色变更接口；
  管理员不绕过会话所有权。
- `data_agent/routes/managed_file.py` 提供受保护的文件上传、列表、metadata、分析
  和删除；服务再次按 `user_id + file_id` 校验 owner，管理员不绕过。
- `data_agent/tools/document_analysis.py` 只接受 UUID `file_id`，从隐藏
  `langgraph_auth_user_id` 恢复主体，不接受或打开模型提供的路径。

### 3.2 前端连接

- `NEXT_PUBLIC_API_URL` 和 `NEXT_PUBLIC_ASSISTANT_ID` 用于 LangGraph。
- `NEXT_PUBLIC_REST_API_URL` 用于 FastAPI 第一方认证和会话接口。
- 两类公开地址在静态构建时写入，必须可由浏览器访问，不能使用 Docker 内部服务名。
- 第一方 JWT 存储在 `sessionStorage`，只附加到配置的 FastAPI 与固定 LangGraph
  Origin；不得进入 URL、日志或持久化存储。
- `apiUrl`/`assistantId` 查询状态、连接表单、`X-Api-Key` 和 LangGraph API Key
  读写均已移除；启动时只清理旧 `lg:chat:apiKey`。
- Chat UI 以 LangGraph threads 为对话主数据；MySQL users/RBAC 为身份主数据，
  既有 sessions/messages REST API 不与 LangGraph 双写。
- 新文件先上传固定 FastAPI Origin；thread 只保存 `__managed_file_v1__` UUID
  引用，不保存 Data URL/Base64。历史 Base64 block 仅兼容只读渲染。
- REST 请求使用 `X-Request-ID`；LangGraph run 通过 `configurable` 与
  `metadata` 传递独立请求 ID。不得把提示词、消息正文或用户身份写入关联字段。

## 4. 配置契约

复制 `.env.example` 为本地 `.env`，只在本地填入真实值。

| 变量 | 作用 | 约束 |
| --- | --- | --- |
| `MOONSHOT_API_KEY` | 模型调用 | 示例占位值无效；不得提交 |
| `TAVILY_API_KEY` | 互联网搜索 | 仅搜索工具需要；不得提交 |
| `MODEL_NAME`、`MODEL_BASE_URL`、`MODEL_TEMPERATURE` | 模型配置 | 与提供方契约一致 |
| `DATABASE_URL` | 宿主机数据库 | 默认使用 PyMySQL URL |
| `REDIS_URL` | 宿主机缓存 | 不可用时允许降级 |
| `FILE_STORAGE_ROOT` | 宿主机受管文件根 | 默认 `var/managed_files`；不得作为 API 输入 |
| `FILE_UPLOAD_MAX_BYTES`、`FILE_UPLOAD_BATCH_MAX_BYTES`、`FILE_UPLOAD_REQUEST_MAX_BYTES` | 文件、批次、请求体上限 | 默认 5 MiB / 10 MiB / 11 MiB，正整数且单调 |
| `FILE_UPLOAD_BATCH_MAX_COUNT`、`FILE_USER_MAX_COUNT`、`FILE_USER_QUOTA_BYTES` | 批次与用户配额 | 默认 5 个 / 100 个 / 100 MiB |
| `FILE_RETENTION_HOURS`、`FILE_ANALYSIS_MAX_CHARS` | 保留与工具输出预算 | 默认 168 小时 / 20,000 字符 |
| `JWT_SECRET_KEY` | 第一方 JWT 签名 | 至少 32 个字符且不能是占位值 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token 有效期 | 正整数 |
| `CORS_ALLOWED_ORIGINS` | FastAPI 来源白名单 | 逗号分隔绝对来源，禁止通配符 |
| `RATE_LIMIT_ENABLED` | 请求限流总开关 | 默认 `true`，设 `false` 关闭且不调用 Redis |
| `TRUSTED_PROXY_COUNT` | 可信反向代理跳数 | 非负整数，默认 `0` 不信任 `X-Forwarded-For` |
| `RATE_LIMIT_*_MAX_REQUESTS`、`RATE_LIMIT_*_WINDOW_SECONDS` | 认证、查询、会话、默认四类配额与窗口 | 正整数、有界；四类计数隔离 |
| `ENABLE_CODE_EXECUTION` | 任意 Python 执行开关 | 默认 `false`，仅受控环境人工启用 |
| `SERVICE_NAME`、`LOG_LEVEL` | 结构化事件来源与级别 | 服务名保持低基数 |
| `LOG_FILE_PATH`、`LOG_MAX_BYTES`、`LOG_BACKUP_COUNT` | 本地日志轮转 | 大小与备份数必须为正整数 |
| `DOCKER_LOG_MAX_SIZE`、`DOCKER_LOG_MAX_FILES` | 容器日志轮转 | 保持有界默认值 |
| `COMPOSE_DATABASE_URL`、`COMPOSE_REDIS_URL` | 容器内部连接 | 使用 `mysql`、`redis` 服务名 |
| `COMPOSE_FILE_STORAGE_ROOT` | 容器受管文件根 | 默认 `/data/managed-files`，FastAPI/LangGraph 共享 |
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
python -m isort --check-only data_agent tests scripts
python -m uvicorn data_agent.agent_server:app --host 0.0.0.0 --port 8000
langgraph dev --host 0.0.0.0 --port 2024 --no-browser --allow-blocking
python scripts/export_diagnostics.py --input deep_data_agent.log --output diagnostic-report.json
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini revision --autogenerate -m "描述"
python -m alembic -c alembic.ini current
python scripts/bootstrap_admin.py --user-id <用户 ID>
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

测试使用 SQLite、离线 Redis 替身和脱敏日志样本，不访问开发 MySQL、Redis、
Moonshot 或 Tavily。

覆盖范围包括：

- LangGraph/FastAPI 入口、生命周期和健康检查。
- LangGraph 第一方 JWT、当前数据库角色、全局默认拒绝、thread/run owner、
  固定 assistant 只读边界和 FastAPI Agent 双层授权。
- 双用户租户缓存、前端固定 Origin/旧 Key 发布契约，以及容器中的并发重复搜索、
  跨租户 history/state/copy/读改删/create_run 和管理员不绕过。
- 受管文件请求体、UTF-8/MIME/扩展名、JSON/CSV、数量/字节/用户配额、整批事务、
  owner、过期、路径/符号链接/普通文件、大小/哈希漂移和脱敏事件。
- 容器双用户上传/列表/分析/删除、FastAPI/LangGraph 共享卷、跨用户/管理员拒绝、
  恶意 JSON、超限文件和无 Base64 新上传。
- 缺失模型配置、Redis 降级、代码执行开关和 Agent 错误映射。
- JWT 配置、注册、登录、`/me`、Token 异常和 CORS。
- 双用户会话读写删隔离及输入校验无部分写入。
- 固定角色矩阵、路由/服务双层授权、管理员分页与角色变更、人工引导和 HMAC
  身份审计。
- SQLAlchemy 共享元数据、UTC 默认值、序列化和会话排序。
- 请求 ID 校验与传播、CORS 响应头、结构化事件字段和异常脱敏。
- 诊断报告过滤、倒序时间线、高频折叠、延迟指标和本地告警信号。
- 迁移在干净 SQLite 升级到 head 建出等价 schema、模型与迁移无漂移和 head 唯一。
- 后端镜像迁移资产、全仓库凭据文本发现，以及五服务/HTTP/head/canary/旧基线
  容器冒烟辅助逻辑。

文档或窄范围改动至少执行相关检查和定向 `git diff --check`。发布候选还必须执行
前端类型、零警告 Lint、格式、构建、Compose 解析、凭据与发布契约扫描（含迁移
head 唯一性 `MIGRATION_HEAD`）、当前源码镜像重建及五服务双用户冒烟。没有 Docker
运行证据时，不得声称容器验收通过。

2026-08-17 的当前工作树已取得 Python 3.12.9 共 295 项测试、8 项迁移定向测试、
Node.js 22.22.2 与 pnpm 10.5.1 前端四门禁、本地 Docker 三场景和无凭据 Chromium
交互证据。implementation SHA `9fe0c40bd66a01db427fe37169a0ec0f65f24f85`
的 Hosted 四个 Job 已在 run `32008059164` 验证成功。

## 7. 安全现状

### 已落实

- JWT 密钥来自环境变量；无有效密钥时认证与会话接口返回稳定 503，健康检查可用。
- JWT `sub` 使用用户 ID，认证依赖校验签名、算法、有效期和用户存在性。
- 同一 JWT 保护 FastAPI Agent 与 LangGraph；每次 LangGraph 请求读取数据库当前
  角色，thread/run 按 owner 默认隔离，管理员不绕过所有权。
- Agent 缓存键包含用户、模型、Base URL、温度、工具策略版本和查询的 SHA-256
  摘要；同查询不会跨用户复用。
- 文件只通过随机 UUID 引用；上传、读取、分析、删除在路由和服务层双重授权，
  工具打开文件前复核 owner、受管根、普通文件、非符号链接、大小和 SHA-256。
- 新上传只支持有界 UTF-8 TXT/Markdown/CSV/JSON；图片/PDF Base64 新摄取已移除。
- CORS 使用明确白名单，启用凭据时不允许通配符。
- 会话和消息在服务层同时按 `session_id` 与 `user_id` 过滤；越权统一返回 404。
- 第一方 Token 使用 `sessionStorage`，不写 URL、日志或错误提示。
- 代码执行默认关闭；配置和日志具有占位值识别与敏感值脱敏边界。
- 日志使用固定结构化字段和有界轮转；诊断导出只读、人工触发且不自动外发。
- 按身份维度的请求限流：FastAPI 层用 Redis 固定窗口对认证、查询、会话与默认四类
  计数，Redis 故障时 fail-open 放行并记录脱敏降级事件，配额键仅用不可逆摘要。
- 用户角色固定为 `user`/`admin` 且默认 `user`；管理员接口执行路由与服务双层
  授权，首位管理员只允许按用户 ID 人工引导，管理与拒绝事件只记录 HMAC 身份引用。

### 仍有限制

- 当前锁定的容器运行时 `langgraph-api 0.7.28` 已 EOL；升级、兼容回归与依赖锁定
  归入 `AUD-006`/`stabilize-delivery-baseline`，本轮不静默扩大升级范围。
- 已加入按身份维度的请求限流与固定角色 RBAC，但仍无分布式令牌桶、自动封禁、
  Refresh Token、密码找回、邮箱验证、OAuth、自定义角色或管理员前端。
- 管理审计复用有界本地结构化日志，不是不可变长期审计数据库，也未接入外部 SIEM。
- 任意 Python 执行显式开启后仍无沙箱；受管文件卷没有备份、加密或跨实例共享。
- 当前不支持 PDF、Office、压缩包、图片、OCR 或病毒扫描；只接受受管文本格式。
- 数据库已引入 Alembic 版本化迁移，`init_db` 改为迁移驱动，旧库首次启动 stamp
  到基线兼容；但仍无自动数据备份与回滚演练流程。
- 旧的已失效服务凭据仍在 Git 历史中；历史清理由人工在干净工作区另行处理。

## 8. 当前技术边界

- 结构化事件和诊断报告是轻量本地基线，不等同于分布式追踪平台或长期指标存储。
- 当前没有 OpenTelemetry Collector、Prometheus、Grafana、SLO 看板或自动告警
  通知；引入这些组件前必须另行评审成本、保留周期和访问控制。
- 本机默认 Node.js 25.2.1 超出支持的 22.x 范围；本轮通过临时 PATH 使用
  Node.js 22.22.2 与 pnpm 10.5.1 取得本地前端发布证据。
- LangGraph 已使用第一方自定义 Auth，但日志与诊断报告仍不能作为授权或审计替代品。
- 请求限流为单实例本地 Redis 固定窗口，非全局分布式速率控制；无令牌桶、自动
  封禁或跨实例配额共享，Redis 故障时 fail-open。
- 管理员角色只增加用户列表和他人角色变更能力，不允许跨用户读取、写入或删除
  会话；前端返回的角色字段不能作为授权依据。

## 9. 相关文档

- `README.md`：本地开发、配置、Docker 和验证命令。
- `.trae/documents/project_analysis.md`：2026-08-12 项目整体审计快照、问题清单、
  证据边界与发布判断。
- `.trae/documents/roadmap.md`：10 个已完成 change-id 和 9 个未启动候选迭代。
- `CHANGELOG.md`：版本化行为变化、验证证据和已知风险。
- `.trae/specs/audit-project-roadmap/`：项目整体审计与后续迭代规划规格。
- `.trae/specs/establish-runnable-baseline/`：可运行闭环规格。
- `.trae/specs/secure-user-sessions/`：第一方认证与隔离规格。
- `.trae/specs/enforce-release-readiness/`：已完成的发布治理规格。
- `.trae/specs/add-observability-diagnostics/`：已完成的可观测性与诊断规格。
- `.trae/specs/add-versioned-migrations/`：版本化数据库迁移规格。
- `.trae/specs/add-rbac-audit/`：已完成的 RBAC 与脱敏审计规格。
- `.trae/specs/restore-runtime-release-gates/`：已完成的运行时发布门禁规格；
  Hosted 四个 Job 已在 implementation SHA
  `30e7992fa48c350a0b0ae8a6faa12c80cfe2202d` 上验证成功。
- `.trae/specs/secure-agent-tenant-boundaries/`：已完成本地与 Hosted 验收的
  Agent 第一方身份与租户边界规格。
- `.trae/specs/isolate-file-ingestion/`：已完成本地与 Hosted 验收的 owner 受管
  文件与安全摄取规格。
