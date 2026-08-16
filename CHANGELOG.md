# Changelog

本文件记录 Deep Data Agent 的用户可见行为、质量契约、验证证据和已知风险。版本号
用于仓库里程碑；是否形成正式发布标签，以 Git 中实际存在的标签为准。

## [Unreleased]

### 项目整体审计（2026-08-12，2026-08-16 交付复核）

- 本轮以 `main` @ `f6cf4e65d8b15114fc164fd6921bd65d6ad27862` 为锁定基线，
  审计浏览器与 Next.js 前端、FastAPI、LangGraph/Agent、MySQL、Redis、模型与
  工具、Docker Compose、GitHub Actions、迁移、认证授权、可观测性、发布契约及
  未接入主应用的 `utils/` 边界。
- Python 3.12.9 下 `python -m pytest -q` 共 **155 项通过**；后端格式、发布契约、
  Alembic、Compose 静态解析及前端类型、Lint、格式和构建门禁通过。
- 目标 SHA 的 GitHub Actions run `31554712031` 为 `completed/success`；Backend、
  Frontend、Release Contracts 三个 Job 均成功。
- 2026-08-16 在相同运行时代码基线上重跑 155 项后端测试、前端类型/Lint/格式/
  构建、发布契约、Compose 解析和差异检查；两名新的独立验证者再次逐项确认
  18/18 个最终问题，复核仅收紧证据边界，不改变严重度、数量或 Roadmap 映射。
- 两名独立验证者共同确认 **18 个 2/2 高置信度问题**；按 Spec P0-P3 定义最终
  裁决为 **4 个 P0、3 个 P1、10 个 P2 和 1 个 P3**。验证者原始 P1/P2 建议保留
  在 21 候选 × 2 验证矩阵中，不由最终裁决反写；当前生产发布判断为 **NO-GO**，
  本地开发与受控审计只能在项目分析记录的约束下继续。
- 去重与排除结果为：`AUD-013` 合并到 `AUD-010`，`AUD-021` 合并到 `AUD-006`；
  `AUD-019` 因 0/2 确认而排除，不进入问题清单或 Roadmap；项目分析附录保存了
  21 个候选的 42 条验证者存在性、原始 severity、理由、校正证据和最终动作。
- Roadmap 将发现映射为 **12 个未启动后续候选**：
  `restore-runtime-release-gates`、`stabilize-delivery-baseline`、
  `secure-agent-tenant-boundaries`、`isolate-file-ingestion`、
  `bound-agent-resource-use`、`prove-data-recovery`、
  `harden-identity-administration`、`paginate-session-history`、
  `deliver-data-analysis-reports`、`rewrite-credential-history`、
  `define-production-hosting-boundary` 和 `persist-compliance-audit-records`。
  这些条目均为候选，不代表已经实现、启动或取得验收证据。
- 本轮仅更新审计、Roadmap 与治理记录，无运行时代码、测试、依赖或部署配置变化。
  本轮未取得 Docker 五服务实际启动、容器内迁移或真实模型、搜索、业务数据等外部
  服务证据；Hosted CI 和静态 Compose 检查不能替代这些证据。

### 既有未发布行为变化

- 前端生产构建不再跳过 TypeScript 或 ESLint 错误，Lint 出现警告即返回非零。
- Node.js 运行范围固定为 22.x，pnpm 固定为 10.5.1，并严格使用锁文件安装。
- 后端使用 SQLAlchemy 2.x 声明式基类和明确 UTC 时间语义，同时保持现有无时区
  数据库字段、排序和 API 序列化兼容。
- 主分支推送和合并请求将自动执行后端、前端、Compose、配置漂移、凭据和工作区
  卫生检查；任一门禁失败都必须阻止发布。
- 第一方认证统一由 `NEXT_PUBLIC_REST_API_URL` 指向 FastAPI；已废弃的外部授权码
  登录配置从环境示例和运行文档中移除。
- 项目分析、Roadmap、README、环境示例和 AI 助手指南与当前五服务架构及认证边界
  对齐。
- FastAPI 全路由统一生成、校验并回传 `X-Request-ID`；前端 REST 与 LangGraph
  run 使用同格式诊断 ID。
- 后端日志改为 UTC JSON Lines，HTTP、Agent、模型、缓存和工具事件只允许固定
  低基数字段，并隔离第三方 logger。
- 本地文件与 Docker 日志增加大小和备份数量上限，避免日志无界占用磁盘。
- 新增人工诊断导出，可按请求 ID 生成倒序时间线，折叠健康检查并汇总 HTTP
  错误率、延迟、缓存降级和模型失败信号。
- FastAPI 层新增按身份维度的 Redis 固定窗口限流，对认证端点、`/api/query`、
  会话端点和全局默认四类分别计数：认证请求按 JWT `sub`、匿名按来源，四类配额
  与不同身份计数相互隔离；`/api/health` 永不受限，`RATE_LIMIT_ENABLED=false`
  可整体关闭。
- 超限返回稳定 `429`，错误体为 `{code: "rate_limited", message, request_id}`
  并附 `Retry-After`；既有 401/404/503 语义不变。
- Redis 不可用或出错时限流 fail-open 放行，并发出脱敏 `rate_limit.degraded`
  事件；限流事件只含维度类别、路由模板、配额键摘要、窗口与计数。
- `TRUSTED_PROXY_COUNT` 默认 `0`，不信任 `X-Forwarded-For`，伪造转发头不改变
  匿名计数键。
- 新增限流环境变量契约与发布契约检查（`RATE_LIMIT_ENV_DEFAULT`），并补充覆盖
  配额默认值的确定性契约测试。
- 引入 Alembic 版本化迁移与初始基线（`users`、`sessions`、`messages`），
  `alembic.ini` 与 `migrations/` 复用应用配置和共享 `Base.metadata`。
- 数据库初始化改为迁移驱动：全新库 upgrade 到 head、由旧 `create_all` 建立的
  一致数据库 stamp 到基线，对已处于 head 的库幂等；不重建也不删除已有数据。
- 新增 `MIGRATION_HEAD` 发布契约校验，静态确认 `migrations/versions` 存在且
  head 唯一。
- 新增迁移确定性测试，覆盖干净 SQLite 升级到 head 建出等价 schema、模型与迁移
  无漂移以及 head 唯一；本地全量确定性测试为 134 项通过。
- 用户新增固定 `user`/`admin` 角色；新注册用户及从初始基线升级的既有用户均
  默认为 `user`，数据库使用非空字段、固定值约束和线性 Alembic revision。
- 新增默认拒绝权限矩阵，以及 `GET /api/admin/users` 和
  `PATCH /api/admin/users/{user_id}/role`；路由和服务层分别授权，普通用户返回
  稳定 `403`，管理员不能修改自己的角色，也不能跨用户访问会话。
- 新增人工 `scripts/bootstrap_admin.py --user-id <id>` 引导；只允许把既有用户
  提升为管理员，不接受用户名、邮箱、密码或 Token，重复执行保持幂等。
- 管理员列表、角色变更、授权拒绝、人工引导和任意 Python 执行工具启用接入 UTC
  结构化审计，身份仅使用 JWT 密钥派生的 HMAC 引用。
- 注册和 `/api/auth/me` 返回固定角色，前端严格解析但不以浏览器角色字段替代后端
  授权；CORS 白名单增加 `PATCH` 支持。
- 发布契约新增默认角色、角色约束、环境自动提权和审计身份字段门禁；全量确定性
  测试扩展到 155 项。
- Alembic 配置同时声明新版 `path_separator` 与兼容键
  `version_path_separator`，消除 Python 3.12 虚拟环境中的配置弃用警告。

### 既有迭代验证证据

- `python -m pytest -q`：155 项通过；
  `python -m isort --check-only data_agent tests scripts`：通过。
- 新增 28 项确定性测试，覆盖请求 ID 校验与传播、CORS 关联头、LangGraph 配置、
  结构化字段白名单、异常脱敏、轮转配置、诊断过滤、倒序、折叠、指标、告警信号
  和发布配置漂移。
- 前端 `pnpm typecheck`、`pnpm lint`、`pnpm format:check` 和 `pnpm build` 四项
  门禁通过；构建后再次执行 `pnpm lint`，仍以零警告通过。
- CI workflow 与 release contract 的本地等价检查通过，包括 Compose 配置、
  配置漂移、凭据和工作区卫生契约。
- 目标提交 `14b1b8ee42351cc446febfa9695761be402ae7e7` 的 GitHub Actions run
  `31353045802`（https://github.com/jwj911/deep_data_agent/actions/runs/31353045802）
  为 `completed/success`；Backend、Frontend 和 Release Contracts 均为
  `completed/success`，`head_sha` 精确匹配 `main` push。
- 发布镜像为后端
  `sha256:c504a231c0c500994805be6fd022f1a633fd16a8d3b12e0f681b1d4c51f4acab`
  与前端
  `sha256:a5c839ffa0ea6ae3791532f83c43e9fe358bebb38d6c4d77c91d2d844214cb21`。
- MySQL、Redis、FastAPI、LangGraph 和前端 5 个服务均为 `healthy`；宿主端口为
  `3307`、`6380`、`8000`、`2024` 和 `3000`。
- 双用户 HTTP 冒烟通过：A/B 注册、登录和 `/me` 均返回 200；B 创建会话并写入
  1 条消息返回 200；A 读取、写入和删除 B 的会话均返回 404，B 再次读取仍为
  1 条消息；无 Token 访问会话返回 401。
- CORS 预检通过：`http://localhost:3000` 返回 ACAO，
  `https://evil.example` 不返回 ACAO；FastAPI 健康检查、LangGraph `/info` 和
  前端 `/data_copilot/` 均返回 200，前端根路径返回 302。
- 冒烟临时数据已定向清理：前置 `users/sessions/messages=2/1/1`，删除
  `2/1/1`，后置 `0/0/0`；唯一系统 TEMP 脚本已删除。
- 本机 Node.js 25.2.1 会产生超出声明范围的本地警告；CI 与 Docker 使用受支持的
  Node.js 22，不受该本机版本警告影响。

### 已知风险

- 旧 Moonshot/Tavily 凭据已轮换失效，但旧值仍存在于 Git 历史。本轮接受该历史
  风险；历史重写延期到干净工作区，由人工协调所有协作者后执行。
- 宿主机 `3306` 或 `6379` 被占用时，MySQL 或 Redis 无法按默认端口启动。只允许
  通过 `.env` 中的 `MYSQL_PORT`、`REDIS_PORT` 重映射宿主端口，不能修改容器内部
  服务地址。
- 完整镜像构建和冒烟依赖 Docker Desktop Linux Engine、充足系统盘空间以及本地
  有效模型/JWT 配置。环境不满足时，不得把静态检查结果等同于容器发布证据。
- LangGraph 本地服务仍使用 noop 认证；任意 Python 代码执行工具虽默认关闭，但
  显式启用后仍不具备安全沙箱。
- 当前诊断能力使用本地轮转日志和 Docker 日志，不包含 OpenTelemetry、
  Prometheus、Grafana、长期存储或自动告警通知；这些能力需要单独评审访问控制、
  成本和保留周期。
- 请求限流为单实例本地 Redis 固定窗口，非分布式令牌桶，也无自动封禁或黑名单；
  Redis 故障时 fail-open 放行，可能在缓存不可用期间放宽配额，需依赖降级事件监控。
- 版本化迁移当前是单 head 本地基线，测试用 SQLite、生产用 MySQL；尚无自动数据
  备份与回滚演练流程，升级前的备份与恢复须人工在受控环境执行。
- 当前 RBAC 只有固定 `user`/`admin` 角色，没有管理员前端、自定义角色、用户删除
  或跨用户会话权限；管理审计复用有界轮转日志，不是不可变长期审计存储或外部
  SIEM。

## [0.2.0] - 2026-08-10

### Added

- FastAPI 第一方注册、登录和 `/api/auth/me`。
- JWT 当前用户依赖、CORS 来源白名单和服务层会话所有权隔离。
- 双用户越权、Token 异常、输入校验和 CORS 确定性测试。

### Changed

- 前端登录改为用户名/密码注册与登录，第一方 Token 改存 `sessionStorage`。
- FastAPI 401 只清理第一方登录态，不受 LangGraph 或第三方 401/403 影响。
- 自动测试基线扩展到 60 项，五服务容器和双用户冒烟通过。

## [0.1.0] - 2026-08-09

### Added

- 独立的 LangGraph 图入口与 FastAPI 应用入口。
- MySQL 会话持久化、可降级 Redis 缓存和稳定的 Agent 错误语义。
- Next.js 静态前端连接层及 MySQL、Redis、FastAPI、LangGraph、前端五服务
  Docker Compose 闭环。

### Security

- 任意 Python 代码执行工具改为默认关闭，只允许在受控环境人工启用。
- 模型、搜索、数据库和缓存配置迁移到环境变量，示例文件只保留非生产占位值。
