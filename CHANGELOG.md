# Changelog

本文件记录 Deep Data Agent 的用户可见行为、质量契约、验证证据和已知风险。版本号
用于仓库里程碑；是否形成正式发布标签，以 Git 中实际存在的标签为准。

## [Unreleased]

### 计划行为变化

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

### 当前验证证据

- `python -m pytest -q`：75 项通过，0 个警告；
  `python -m isort --check-only data_agent tests`：通过。
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
