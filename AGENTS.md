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

2026-10-28 已实施 run 合计账本、未知 schema 拒绝、三域停写恢复及
Python 3.12 跨平台哈希锁。实施 SHA `1910fdf` 的 Hosted 四 Job 全部成功：
Linux 后端 733 项、真实 Redis/TCP 20 个预算控制例、MySQL 20 个结构控制例、
新锁五服务、Chromium 七项及三域独立恢复通过；恢复实测 31.757 秒，
确认写入丢失 0、六项备份负控和非空目标拒绝通过。Windows 新锁全量
733 项也通过，首轮导入失败与重验条件留在运行时记录。最终文档提交自身
精确 SHA 的结果按工作区根 `release-gate-evidence.json` 核对。验证入口见
[运行时记录](.trae/specs/stabilize-delivery-baseline/validation.md)、
[预算记录](.trae/specs/enforce-aggregate-agent-budget/validation.md)、
[恢复记录](.trae/specs/prove-data-recovery/validation.md)。
下一产品候选为受控分析切片；自动异地备份、生产运行时与真实效果仍无证据，
生产持久业务保持 NO-GO。以下日期/提交对应的记录保留为历史。

Deep Data Agent 是前后端分离的 AI 数据探索项目，当前已完成可运行闭环和第一方
多用户认证：

- `data_agent/`：Python 3.12、FastAPI、LangGraph/DeepAgents、SQLAlchemy。
- `agent_chatui/`：Next.js 15、React 19、TypeScript、Tailwind CSS 静态前端。
- MySQL：持久化 users/RBAC、既有 REST sessions/messages 和受管文件 metadata，
  不是 Chat UI 主历史的存储。
- Redis：承载 Agent/搜索缓存、HTTP 限流和 Agent 并发租约；按调用面执行
  fail-open/fail-closed，并在退避后自动恢复。
- Docker Compose：编排 5 个服务，默认文件根配置让 FastAPI/LangGraph 共享受管文件卷。

截至 2026-10-27，仓库有 12 个既有已完成规格（11 个功能迭代和 1 个 audit），
本轮另完成一次 `review-project-modernization` 文档审查，不算第 12 个功能。
双独立复核与 25 项文档验收已完成，不代表运行/生产放行。
随后 `repair-agent-graph-copy` 完成本机及 Hosted 验收，成为第 12 个功能迭代；
代码提交 `8e552f3` 已推送到 `fix/agent-graph-copy`，PR #1 四 Job 全部成功，
包含 Ubuntu 图复制/TCP 回归及 Linux 镜像容器冒烟，尚未合并或批准生产。
`.trae/specs/bound-agent-resource-use/` 的历史本地实现与 implementation Hosted
验证已完成；该迭代增加 Agent、模型和工具预算，建立 Redis 自动恢复与分级保护，
拆分 liveness/readiness，并永久移除运行时任意 Python 执行能力。

2026-08-12 项目整体审计以 `f6cf4e65d8b15114fc164fd6921bd65d6ad27862` 为基线，
历史识别 18 个 2/2 高置信度问题（4 P0 / 3 P1 / 10 P2 / 1 P3）。
2026-08-21 文档快照记录仍开放 8 项、生产 NO-GO、8 个 Roadmap 候选且下一项为
`prove-data-recovery`；这些是历史判断。查询当前问题状态、双验证原值和条件裁定时
读取 [项目分析](.trae/documents/project_analysis.md)；选择迭代、依赖、验收及
停止条件时读取 [Roadmap](.trae/documents/roadmap.md)，不沿用旧快照。

本轮 48 主来源（18 AUD + 30 REV）另加 3 追溯，A/B 各覆盖 51 原值；
主项 2/2、1/2、0/2 支持分布为 47/0/1，不是开放 bug 数。`AUD-004` 两票反完整
closed、两票残余 `exists_current=true`，同步 Redis 残余归该 ID；原 `ainvoke`
修复保留，合计预算归 `REV-A02`。首轮 `repair-agent-graph-copy` 的复制合同已验证；
新增部署阻断已完成本机独立修复及重验，下一建议为 `enforce-aggregate-agent-budget` 与
`deliver-controlled-analysis-slice`；
UI、兼容矩阵与评测设计可并行，代码修复、升级与新功能另立规格。

图复制修复在 Python 3.12.9 下新增 149 项回归、全量后端 601 项通过；
isort、发布契约静态检查和差异检查通过。使用离线模型/租约与内存存储，
dotenv、追踪、自动插件和字节码禁用；未调用真实服务。具体范围与本轮运行
缺口见 [修复规格](.trae/specs/repair-agent-graph-copy/spec.md)，以下 452 项等
记录属于修复前复审基线，不覆盖新增工作树代码。
后续真实 TCP HTTP 补验通过，全量后端增至 602 项；Hosted run `40507150345`
的四 Job 全部成功。随后本机 Engine 恢复，受限只读容器中的当前源码复制/TCP
回归 150 项通过。测试控制条件、NumPy 初始化与缓存镜像范围以补验记录为准。
随后从修复提交重建本机五服务，新镜像 150 项回归、迁移和 Redis canary 通过；
实际工厂图退出发生身份 ContextVar reset 异常，取消租约未及时释放，浏览器
匿名入口/退出跳转丢失宿主端口。本机完整联调未通过，先修复新增部署阻断，
再继续合计预算；诊断与清理证据见 [补验记录](.trae/specs/repair-agent-graph-copy/validation.md)。

随后 `repair-async-lease-context` 已实施：异步图执行/身份/deadline/关闭归属
一个受控 Task，容量为 1 的队列保持背压；消费者结束等待清理，重复取消不打断
清理。同步流用私有 Context，两种 lease hold 的 reset 异常仍尝试一次 release。
本机全量 619 项、真实工厂 TCP HTTP 的身份/wait/stream/取消/timeout、
isort 与发布契约通过。前轮部署精确依赖的 Linux 194 项及独立 Redis 的
真实 HTTP 通过，4 次取得/释放相符、最终 DB 为 0 个 key；条件与源码证据见
[本轮验收](.trae/specs/repair-async-lease-context/validation.md)。
随后 `repair-static-auth-redirect` 通过 Nginx 相对 Location 修复映射端口丢失，
新增真实 HTTP CI 门禁。当前源码生产镜像、前端四门禁、Linux 194 项及独立五服务/
浏览器通过；实际 run、取消、timeout 与 6 次 Redis 租约释放相符。
控制条件、迁移与清理见[本轮部署验收](.trae/specs/repair-static-auth-redirect/validation.md)。
本轮工作树未提交、未验 Hosted；合计预算、恢复等生产门禁保持，生产仍 NO-GO。

2026-10-27 复审代码基线为 `main` 的 HEAD
`3d4ac6dbb540d7f8a46430f3bc311c071d4ba438`。以下本轮记录由基线 Agent 实际
执行，不是用户给定数据，本次文档同步未重跑：Python 3.12.9 下
全量 452 项测试、迁移定向 8 项和 release contract pytest 159 项通过；
isort、发布契约脚本、Alembic 唯一 head `b6f4e8c2a9d1`、不读取真实 `.env`
的 Compose 静态解析及差异检查通过。使用已有缓存 Node.js 22.22.2、pnpm 10.5.1
的 typecheck、零警告 lint、format:check、build 全部通过。
Docker CLI 29.4.1、Compose 5.1.3、Desktop 4.71.0.225177 已安装，但
`dockerDesktopLinuxEngine` pipe 不存在，本轮容器未验证；`gh` 缺失，目标 SHA
的四个 Hosted Job 状态未知。真实模型/搜索、业务效果、成本、延迟、浏览器 E2E
和生产恢复本轮均未测。2026-08-21 implementation Hosted 及容器证据明确属于
历史，详见 README“历史验收记录”，不能替代本轮证据。

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
- `/api/live` 与兼容 `/api/health` 只证明进程可响应；`/api/ready` 浅检查模型
  配置、MySQL、唯一 Alembic head、Redis 与受管文件根，不调用模型或搜索。
- `/api/query` 要求 `agent.invoke_own`，并将输入、并发、保护、预算、timeout、
  输出、配置和上游错误映射为稳定的非 2xx 响应。
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
- Compose 使用 `langgraph dev`；主历史写入 `/app/.langgraph_api`，
  已挂载 `langgraph_data`。保留卷不替代三域一致备份，也不表示生产运行时支持。
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
| `MODEL_REQUEST_TIMEOUT_SECONDS`、`MODEL_MAX_RETRIES`、`MODEL_MAX_OUTPUT_TOKENS` | 单次模型预算 | 默认 45 秒 / 1 次 / 4,096 tokens，只允许收紧固定上限 |
| `AGENT_QUERY_MAX_CHARS`、`AGENT_RESPONSE_MAX_CHARS` | FastAPI 输入/输出预算 | 默认 8,000 / 32,000 个字符 |
| `AGENT_RUN_TIMEOUT_SECONDS`、`AGENT_RECURSION_LIMIT` | run 总 deadline 与父子递归配置 | 默认 60 秒 / 25 层，客户端不能扩大 |
| `AGENT_MODEL_CALL_LIMIT`、`AGENT_TOOL_CALL_LIMIT` | 并发安全 run 合计总账 | 默认 8 次模型发送前预留 / 12 次工具执行；父子/摘要/重试共用，取消不退额 |
| `AGENT_GLOBAL_CONCURRENCY_LIMIT`、`AGENT_USER_CONCURRENCY_LIMIT` | Redis 双层租约 | 默认全局 4 / 单用户 1 |
| `AGENT_CONCURRENCY_WAIT_SECONDS`、`AGENT_CONCURRENCY_LEASE_TTL_SECONDS` | 租约等待与回收 | 默认 1 秒 / 75 秒，TTL 必须大于 run deadline |
| `SEARCH_*` | 搜索 query、结果数、timeout 与输出预算 | 默认 2,000 字符 / 5 条 / 15 秒 / 64 KiB，只允许 general/news |
| `DATABASE_URL` | 宿主机数据库 | 默认使用 PyMySQL URL |
| `REDIS_URL` | 宿主机 Redis | 缓存/低成本限流 fail-open；query/Agent/readiness fail-closed |
| `REDIS_RECOVERY_*` | Redis 恢复退避与抖动 | 初始 1 秒、最大 30 秒、抖动比例 `0.2` |
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
| `SERVICE_NAME`、`LOG_LEVEL` | 结构化事件来源与级别 | 服务名保持低基数 |
| `LOG_FILE_PATH`、`LOG_MAX_BYTES`、`LOG_BACKUP_COUNT` | 本地日志轮转 | 大小与备份数必须为正整数 |
| `DOCKER_LOG_MAX_SIZE`、`DOCKER_LOG_MAX_FILES` | 容器日志轮转 | 保持有界默认值 |
| `COMPOSE_DATABASE_URL`、`COMPOSE_REDIS_URL` | 容器内部连接 | 使用 `mysql`、`redis` 服务名 |
| `COMPOSE_FILE_STORAGE_ROOT` | 容器受管文件根 | 默认 `/data/managed-files` 是唯一已知的共享挂载配置；override 不同步改变固定 mount target，挂载外不共享、不随卷持久化 |
| `MYSQL_PORT`、`REDIS_PORT` 等 | 宿主机端口 | 端口冲突时只重映射宿主侧 |

Compose 的数据库凭据、数据库名和连接 URL 必须同步修改。前端公开 URL 与容器
内部地址是两套边界，不得互换。

## 5. 常用命令

### 5.1 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
python -m pytest
python -m pytest -q tests/test_migrations.py
python -m pytest -q tests/test_release_contracts.py
python -m isort --check-only data_agent tests scripts
python scripts/check_release_contracts.py
python -m alembic -c alembic.ini heads
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
- Agent 输入/输出、deadline、取消、递归、模型/工具调用和双层并发租约；失败时
  缓存无副作用并返回稳定错误码。
- 搜索 query/topic/结果数/timeout/输出边界、缺失配置、raw/media 移除及受管文档
  20,000 字符上限。
- Redis 断开、连续失败、退避、单飞、恢复、再次故障及 fail-open/fail-closed
  策略矩阵；代码执行残留变量无效。
- `/api/live`、兼容 `/api/health`、`/api/ready` 组件故障/恢复与响应脱敏。
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

本轮本地结果与缺口见第 2 节；历史验收记录见 README“历史验收记录”。
最终验收文档提交仍须由其自身 exact SHA 的四个 Hosted Job 证明，不能把历史
implementation 结果外推，也不能把静态 Compose 解析当作容器运行通过。
历史记录创建时最终文档 SHA 与 run ID 尚未知，该限定保留，不以本轮 HEAD 补填。

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
- 任意 Python 执行工具已从运行时、配置、Compose、提示和注册路径移除；残留环境
  变量不会恢复该能力。
- FastAPI 原图与 LangGraph Agent 包装共用服务端 deadline、单次模型参数和 Redis
  双层租约策略，管理员及客户端 config/context 不能扩大这些限制。父子递归为
  25，合计模型/工具 8/12；HTTPX 每次 SDK 请求前预留模型额度，所有父子工具
  执行前预留工具额度。资源图显式保存 manager，复制/API 装配后仍使用同一
  管理器。部署与控制条件按各独立验收记录核对。
- 日志使用固定结构化字段和有界轮转；诊断导出只读、人工触发且不自动外发。
- 按身份维度的请求限流：FastAPI 层用 Redis 固定窗口对认证、查询、会话与默认四类
  计数；Redis 故障时 auth/session/default fail-open，query fail-closed，均记录
  脱敏保护状态。缓存 fail-open，Agent 租约和 readiness fail-closed。
- Redis 客户端按 1..30 秒单飞指数退避自动恢复；`/api/live` 与 `/api/ready`
  分离，Compose 不再以无条件 liveness 作为就绪证据。
- 用户角色固定为 `user`/`admin` 且默认 `user`；管理员接口执行路由与服务双层
  授权，首位管理员只允许按用户 ID 人工引导，管理与拒绝事件只记录 HMAC 身份引用。

### 仍有限制

- `REV-A01` 已完成源码修复与本机 149 项复制回归，包括真实工厂与已安装
  API `get_graph`；后续本机真实 TCP HTTP wait/stream/state、取消及身份
  负控通过。使用测试模型/租约、隔离 SQLite/inmem 与启动时 NumPy 初始化；
  Hosted Ubuntu 的 602 项测试和 Linux 镜像冒烟通过；本机受限 Linux 容器
  及新建镜像各 150 项回归通过。本机五服务已重建，但实际 astream 身份
  reset/租约释放与前端认证跳转在前轮失败。本轮异步上下文修复的本机 619 项
  及加严 TCP HTTP、精确依赖 Linux 194 项、独立 Redis 实际释放通过；
  后续静态认证跳转已修，新生产镜像的完整五服务/浏览器通过。原任务 6、
  验收 18/19 保持历史记录，本轮独立验收不替代 exact-SHA Hosted 或生产放行。
- `REV-A02` 的父子/summary/retry 共享总账已实施，修复前漏账实证保留在
  [合计预算验收](.trae/specs/enforce-aggregate-agent-budget/validation.md)；
  判断是否已验证实际 SDK、Redis 或 Hosted 时读取该记录。
- `REV-A03`：REST 回答缓存 TTL 24 小时，缺文件活性/版本依赖；用户影响按
  当前重新分析或显式历史快照合同裁定，仅影响 FastAPI REST，不影响绕过该
  缓存的 LangGraph Chat UI。本轮未修缓存，失效模拟不是实际文件生命周期 E2E。
- 当前锁定 `langgraph-api 0.16.8`，直接依赖由 `requirements.in` 声明，
  Python 3.12 跨平台传递依赖与哈希由 `requirements.txt` 锁定。升级与部署验收
  归 `AUD-006`/[运行时门禁](.trae/specs/stabilize-delivery-baseline/validation.md)。
- 已加入按身份维度的请求限流与固定角色 RBAC，但仍无分布式令牌桶、自动封禁、
  Refresh Token、密码找回、邮箱验证、OAuth、自定义角色或管理员前端。
- 管理审计复用有界本地结构化日志，不是不可变长期审计数据库，也未接入外部 SIEM。
- 已提供 MySQL、LangGraph 主历史和受管文件的人工停写备份与独立空目标恢复；
  实际一致性及失败边界见[恢复验收](.trae/specs/prove-data-recovery/validation.md)。
  尚无自动异地加密备份与恢复运营证据。生产持久业务及不可重建数据
  仍为 NO-GO；schema/restore 门禁只约束相应持久目标，不锁定非敏感、可重建、
  隔离且不自动外发的统计开发，接入仍须 owner/文件边界和有效资源限制。
- 当前不支持 PDF、Office、压缩包、图片、OCR 或病毒扫描；只接受受管文本格式。
- 数据库初始化按实际完整结构识别空库、已知 revision 与已知无版本旧库；
  未知、部分或伪造结构拒绝 stamp/升级，保留目标数据。SQLite 与真实 MySQL
  证据见[结构拒绝验收](.trae/specs/reject-unknown-schema/validation.md)；
  不保证任意 legacy 可升级。
- 旧的已失效服务凭据仍在 Git 历史中；历史清理由人工在干净工作区另行处理。

## 8. 当前技术边界

- 结构化事件和诊断报告是轻量本地基线，不等同于分布式追踪平台或长期指标存储。
- 当前没有 OpenTelemetry Collector、Prometheus、Grafana、SLO 看板或自动告警
  通知；引入这些组件前必须另行评审成本、保留周期和访问控制。
- 2026-10-27 本机默认 Node.js 25.2.1、pnpm 10.33.2 不符合前端版本契约；
  本轮使用已有缓存 Node.js 22.22.2 与 pnpm 10.5.1 取得本地前端门禁证据。
- LangGraph 已使用第一方自定义 Auth，但日志与诊断报告仍不能作为授权或审计替代品。
- 请求限流为 Redis 固定窗口，非令牌桶或自动封禁系统；低成本 scope 在 Redis
  故障时按既定策略 fail-open，高成本 query 与 Agent 保护 fail-closed。
- 管理员角色只增加用户列表和他人角色变更能力，不允许跨用户读取、写入或删除
  会话；前端返回的角色字段不能作为授权依据。

## 9. 相关文档

- `README.md`：本地开发、配置、Docker 和验证命令。
- [项目分析](.trae/documents/project_analysis.md)：查询当前问题、双验证原值、
  条件裁定或发布边界时读取；历史审计与本轮文档结论分开保留。
- [Roadmap](.trae/documents/roadmap.md)：选择下一迭代或核对依赖、验收、停止条件
  时读取；包含历史候选处置，建议实施另需规格。
- [CHANGELOG](CHANGELOG.md)：本轮文档收口与逐字保留的历史验证、风险记录。
- [现代化复审规格](.trae/specs/review-project-modernization/spec.md)：本轮仅文档
  审查，25 项文档验收已完成，不表示运行/生产放行。
- [图复制修复规格](.trae/specs/repair-agent-graph-copy/spec.md)：修改图构造、
  复制、配置绑定或 API 装配时读取；记录四调用面、存储注入和保护回归边界。
- [HTTP 与部署补验](.trae/specs/repair-agent-graph-copy/validation.md)：判断
  TCP 请求链、容器或 Hosted 是否已验证，或诊断实际图退出/租约释放与认证
  跳转失败时读取；记录实际版本、响应与清理证据。
- [流上下文修复](.trae/specs/repair-async-lease-context/validation.md)：修改图流
  生命周期、取消或租约释放时读取；核验真实身份作用域、背压、重复取消及
  精确运行时/Redis 的证据边界。
- [静态认证与部署重验](.trae/specs/repair-static-auth-redirect/validation.md)：修改
  Nginx 跳转、公开 API 地址或判断五服务/浏览器是否通过时读取。
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
- `.trae/specs/bound-agent-resource-use/`：已完成本地与 implementation Hosted
  验证的 Agent 预算、Redis 恢复、健康语义与代码执行移除规格；其 Hosted 证据
  对应历史 implementation SHA，不作为当前复审基线的 Hosted 证据。
