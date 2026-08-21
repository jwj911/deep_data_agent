# 约束 Agent 资源使用 Spec

## Why

当前 FastAPI 异步路由直接执行同步 Agent 图，模型、递归、工具调用、搜索结果和总
时长缺少统一预算；Redis 一次连接故障后缓存与限流会永久降级，而无条件成功的健康
端点仍被 Compose 当作 readiness。该组合会让少量慢请求、递归工具调用或瞬时 Redis
故障长期放大延迟、成本与滥用风险。

`secure-agent-tenant-boundaries` 与 `isolate-file-ingestion` 已建立主体和文件边界。
本轮 SHALL 在不调用真实付费服务的前提下关闭 `AUD-004`、`AUD-008`、`AUD-009`，
并收口 `RR-004`、`RR-006`。

## 基线证据

2026-08-21 实施前基线：分支 `main`、本地 `HEAD`、`origin/main` 与远端 `main`
均为 `32383faf0a3f7f0ac009896608209945633c92c1`；tracked 工作树无改动，仅本轮
新规格目录未跟踪。Python 3.12.9 全量 295 项测试与 migration 定向 8 项测试通过；
Hosted run `32009290905` 的 Backend、Frontend、Release Contracts、Container
Smoke 均为 `success`。真实调用链以及本规格的预算、Redis、健康与 BREAKING 决策
均已核实。

以上仅记录本轮实施前基线，不是 Task 2+ 新 implementation 的验收证据；后续实现
仍须按本规格重新取得本地与 Hosted 证据。

## Decisions

- Agent 默认预算：
  - 查询正文最大 8,000 个字符，FastAPI 最终响应最大 32,000 个字符。
  - 每个 run 总 wall time 60 秒，LangGraph recursion limit 25。
  - 每个 run 最多 8 次模型调用、12 次工具调用。
  - 全局最多 4 个并发 run，每个用户最多 1 个；租约等待最多 1 秒。
  - 模型单次请求 timeout 45 秒、最多 1 次 SDK retry、最大输出 4,096 tokens。
- 搜索工具只允许 `general`/`news`，查询最大 2,000 个字符、结果最多 5 条、timeout
  15 秒、总结果最大 64 KiB；`include_raw_content`、图片、视频和文件搜索不再暴露给
  模型。该变化为 **BREAKING**。
- 使用 LangChain 已安装的 `ModelCallLimitMiddleware` 与
  `ToolCallLimitMiddleware`，不自行实现模型/工具计数器。总时长和并发租约由项目
  自有 budget middleware 执行，覆盖 FastAPI 与 LangGraph 两个 Agent 入口。
- 并发租约存放在 Redis，使用原子脚本同时检查全局与用户计数；租约 TTL 大于 run
  deadline，正常完成显式释放，进程退出或取消后由 TTL 回收。Redis key 不记录或
  输出原始用户、查询、Token 或消息正文。
- Redis 策略矩阵：
  - 缓存继续 fail-open 为 miss，不阻断业务。
  - auth/session/default 固定窗口限流在 Redis 不可用时继续 fail-open。
  - `/api/query` 限流、Agent 并发租约和 Agent readiness 在 Redis 不可用时
    fail-closed，避免失去付费入口保护。
- CacheService 与 RateLimitService SHALL 使用单飞重连、指数退避和有界抖动；
  初始 1 秒、最大 30 秒。恢复后无需重启进程。
- 健康语义：
  - `/api/live` 只证明进程事件循环可响应，稳定返回 200。
  - `/api/ready` 不调用模型或搜索，检查配置、MySQL、Alembic 当前 revision、
    Redis 与受管文件根；任一必需项失败返回 503 和固定组件状态。
  - `/api/health` 暂时保留为 `/api/live` 的兼容别名，但 Compose 与发布门禁改用
    `/api/ready`。
- 运行时任意 Python 执行永久关闭：删除 `ENABLE_CODE_EXECUTION` 公共配置和工具
  注册路径；即使部署环境残留该变量也不能注册 `execute_python_code`。这是
  **BREAKING** 变化，并以当前运行边界关闭 `RR-004`；未来若需恢复必须新建独立
  沙箱 change-id。
- 本轮不使用真实模型、搜索、业务文件或生产 Redis/MySQL 做验收；所有超时、取消、
  并发、恢复和健康证据使用 fake client、脱敏 canary 与隔离容器。

## What Changes

- 增加 Agent/model/search/Redis 恢复预算配置及关系校验，写入 `.env.example`、
  Compose 和发布契约。
- Agent 图接入模型/工具调用限制；ChatOpenAI 固定 timeout、retry 和最大输出。
- FastAPI AgentService 改为异步调用，执行总 deadline、recursion limit、输出上限
  和稳定错误映射；取消或超时不写缓存。
- 新增覆盖两个 Agent 入口的 Redis 原子并发租约 middleware；调用方不能通过
  config/context 提高预算或伪造主体。
- 搜索工具改为异步有界调用，删除 raw content 与高体积 topic，限制查询、结果数、
  timeout 和序列化输出。
- 删除运行时 Python 工具开关、注册、提示词和环境示例；发布契约阻止恢复。
- CacheService/RateLimitService 增加单飞探测、指数退避、自动恢复和状态观测；
  RateLimitDecision 明确 degraded 与 fail-open/fail-closed 原因。
- 拆分 `/api/live`、`/api/ready`，保留兼容 `/api/health`；Compose 与 Container
  Smoke 使用 readiness，并增加 Redis 断开/恢复 canary。
- 更新确定性测试、容器冒烟和脱敏诊断；同步 README、AGENTS、项目分析、Roadmap、
  CHANGELOG 与本规格状态。
- 迭代验收后创建原子 implementation 提交并推送 GitHub；记录目标 SHA 四个 Hosted
  Job 后，再提交并推送验收文档，最终 HEAD 继续通过四个 Job。

## Impact

- Affected specs:
  - `secure-agent-tenant-boundaries`
  - `isolate-file-ingestion`
  - `add-request-rate-limiting`
  - `add-observability-diagnostics`
  - `restore-runtime-release-gates`
  - `audit-project-roadmap`
- Affected code:
  - `data_agent/services/agent_service.py`
  - 新增 Agent budget/concurrency middleware 或等价模块
  - `data_agent/services/cache_service.py`
  - `data_agent/services/rate_limit_service.py`
  - `data_agent/observability/rate_limit_middleware.py`
  - `data_agent/tools/search.py`
  - `data_agent/tools/tool_manager.py`
  - `data_agent/tools/code_execution.py`（移出运行时边界）
  - `data_agent/security/langgraph_auth.py`
  - `data_agent/config/config.py`
  - `data_agent/config/database.py`
  - `data_agent/agent_server.py`
  - `agent_chatui/src/providers/Stream.tsx`（仅在错误/取消契约需要时）
  - `.env.example`
  - `docker-config/docker-compose.yml`
  - `scripts/check_release_contracts.py`
  - `scripts/verify_container_smoke.py`
  - `.github/workflows/release-readiness.yml`（仅在验证步骤需要时）
  - `tests/`
  - `README.md`、`AGENTS.md`
  - `.trae/documents/project_analysis.md`、`.trae/documents/roadmap.md`
  - `CHANGELOG.md`

## ADDED Requirements

### Requirement: 所有 Agent 入口执行同一服务端预算

FastAPI `/api/query` 与 LangGraph run SHALL 使用同一组服务端预算。客户端提交的
`recursion_limit`、并发、timeout、model/tool call limit 或 retry 值不得扩大服务端
上限；管理员不绕过预算。

#### Scenario: 正常请求

- **WHEN** 已认证用户在所有预算内完成 Agent run
- **THEN** 返回结果并允许写入该用户缓存，事件记录总耗时和预算结果但不含正文

#### Scenario: 客户端提高预算

- **WHEN** 客户端在 config/context 中提交更大的 recursion、timeout 或调用次数
- **THEN** 服务端覆盖或收紧到配置上限，不使用客户端扩大值

#### Scenario: 模型调用超限

- **WHEN** 同一 run 尝试第 9 次模型调用
- **THEN** run 以稳定 `agent_model_budget_exceeded` 终止，不继续调用模型或写缓存

#### Scenario: 工具调用超限

- **WHEN** 同一 run 尝试第 13 次工具调用
- **THEN** run 以稳定 `agent_tool_budget_exceeded` 终止，后续工具没有副作用

### Requirement: 总 deadline、取消和输出保持有界

Agent run SHALL 在 60 秒总 deadline 内完成。FastAPI SHALL 使用异步图调用，客户端
取消、任务取消和 timeout SHALL 传播到图；超时或取消后不得缓存部分结果。

#### Scenario: 慢模型

- **WHEN** fake 模型超过单次 45 秒或 run 总计 60 秒
- **THEN** FastAPI 返回稳定 504 `agent_timeout`，LangGraph run 标记失败/timeout，
  关联请求 ID 保留且底层异常不回显

#### Scenario: 客户端断开

- **WHEN** 客户端在 Agent 执行中取消请求或流
- **THEN** 异步任务收到取消信号、租约最终释放或到期，结果不进入缓存

#### Scenario: 超大响应

- **WHEN** FastAPI 最终文本超过 32,000 个字符
- **THEN** 返回稳定 `agent_response_too_large`，不缓存或记录响应正文

#### Scenario: 输入超限

- **WHEN** `/api/query` 查询超过 8,000 个字符或为空白
- **THEN** Pydantic 在 Agent、缓存、模型与工具前返回稳定 422

### Requirement: 并发租约按全局和用户双层限制

每个进程/worker SHALL 最多执行 4 个 Agent run；每个用户 SHALL 最多执行 1 个。
Redis 脚本 SHALL 原子检查并写入全局/用户租约，TTL 覆盖 run deadline 与清理余量。

#### Scenario: 同用户并发

- **WHEN** 同一用户已有 run 且在 1 秒等待窗口内再次发起
- **THEN** 第二个请求稳定返回 429 `agent_busy` 与 `Retry-After`，第一个不受影响

#### Scenario: 不同用户并发

- **WHEN** 不同用户在全局上限内并行执行
- **THEN** 用户租约彼此独立，单个用户不能占用超过自己的 1 个槽位

#### Scenario: 全局并发耗尽

- **WHEN** 4 个不同用户正在运行且第五个请求到达
- **THEN** 第五个请求在等待 1 秒后稳定拒绝，不启动模型或工具

#### Scenario: 异常退出

- **WHEN** run 被取消、超时、抛错或 worker 退出
- **THEN** 正常路径显式释放租约；未执行清理时 TTL 在有界时间内回收

### Requirement: 模型与搜索外部调用预算固定

ChatOpenAI SHALL 使用 45 秒 timeout、1 次 SDK retry 和 4,096 最大输出 tokens。
搜索 SHALL 为异步调用，只接受有界 query、topic 与结果数，并禁止 raw content。

#### Scenario: 搜索参数扩大

- **WHEN** 模型请求超过 5 条结果、raw content 或非 `general`/`news` topic
- **THEN** schema 不暴露该能力或服务端稳定拒绝，不向外部服务发送扩大参数

#### Scenario: 搜索 timeout

- **WHEN** fake Tavily 调用超过 15 秒
- **THEN** 工具返回稳定 `search_timeout`，不重试到 run deadline 之外

#### Scenario: 搜索输出过大

- **WHEN** fake 搜索响应序列化后超过 64 KiB
- **THEN** 工具返回稳定 `search_response_too_large`，不缓存或送入模型上下文

#### Scenario: 外部配置缺失

- **WHEN** 模型或搜索密钥缺失
- **THEN** 保持稳定配置错误语义，不尝试网络连接

### Requirement: Redis 故障可恢复且策略矩阵明确

CacheService 与 RateLimitService SHALL 在连接故障后按 1..30 秒指数退避执行单飞
探测。成功后自动恢复，无需重启。所有调用点 SHALL 按固定矩阵选择 fail-open 或
fail-closed。

#### Scenario: 缓存故障

- **WHEN** Redis 在 cache get/set 期间断开
- **THEN** 当前操作降级为 miss/未写入，记录一次有界 degraded 事件，并调度恢复探测

#### Scenario: Redis 恢复

- **WHEN** fake/容器 Redis 在退避窗口后重新可用
- **THEN** 单个探测恢复 client，后续 cache 与 rate limit 操作成功，无重连风暴

#### Scenario: 低成本端点限流故障

- **WHEN** Redis 不可用且 auth/session/default 请求到达
- **THEN** 保持 fail-open，并在响应/事件中体现保护降级但不泄露身份

#### Scenario: 高成本 Agent 保护故障

- **WHEN** Redis 不可用且 `/api/query` 或 LangGraph run 到达
- **THEN** 在模型、工具和 Agent 缓存前稳定 503 `agent_protection_unavailable`

### Requirement: liveness 与 readiness 分离

系统 SHALL 提供 `/api/live` 和 `/api/ready`。readiness SHALL 只执行本地/基础设施
浅检查，不调用付费模型或搜索。`/api/health` SHALL 暂时兼容 liveness，但不得继续
作为 Compose readiness。

#### Scenario: 进程存活

- **WHEN** 事件循环可响应但数据库或 Redis 故障
- **THEN** `/api/live` 与兼容 `/api/health` 返回 200

#### Scenario: 全部依赖就绪

- **WHEN** 配置有效、MySQL 可查询、Alembic revision 为唯一 head、Redis 可用且
  受管文件根可访问
- **THEN** `/api/ready` 返回 200 和固定组件状态，不含 URL、凭据或异常原文

#### Scenario: 关键依赖故障

- **WHEN** MySQL、migration、Redis、模型必要配置或文件根任一失败
- **THEN** `/api/ready` 返回 503 与固定错误码；恢复后自动回到 200

#### Scenario: Compose 健康检查

- **WHEN** FastAPI 或 LangGraph 容器启动
- **THEN** 健康检查使用 readiness 契约，不能仅凭无条件 200 标记 healthy

### Requirement: 预算观测与发布验证不泄露业务数据

预算开始、完成、拒绝、timeout、取消、Redis degraded/recovered 与 readiness 事件
SHALL 使用固定低基数字段。测试 SHALL 使用 fake 模型/搜索和隔离 Redis/MySQL。

#### Scenario: 预算事件

- **WHEN** 请求成功、超限、并发拒绝或 timeout
- **THEN** 事件包含预算类型、结果、耗时、limit 与请求 ID；不含查询、输出、Token、
  用户 ID、文件名、外部响应或异常原文

#### Scenario: Redis 容器故障注入

- **WHEN** Container Smoke 暂停/停止 Redis 后恢复
- **THEN** Agent 高成本入口 fail-closed，liveness 保持 200，readiness 变 503；
  Redis 恢复后无需重启 FastAPI/LangGraph 即恢复 readiness

#### Scenario: 远端交付

- **WHEN** 25 项验收全部通过并推送 `main`
- **THEN** implementation 与最终文档 SHA 的 Backend、Frontend、Release Contracts、
  Container Smoke 全部成功，本地/远端 SHA 一致且工作区干净

## MODIFIED Requirements

### Requirement: FastAPI Agent 错误语义

`/api/query` 除既有 401/503/502 外 SHALL 增加 422 输入错误、429 `agent_busy`、
503 `agent_protection_unavailable`、504 `agent_timeout` 和有界响应错误；所有错误
继续携带请求 ID，不暴露底层异常。

### Requirement: LangGraph run 所有权

owner 过滤保持不变；创建 run 时 SHALL 额外强制服务端预算和认证主体。预算 metadata
不得替代 owner，也不得由管理员绕过。

### Requirement: 发布容器门禁

五服务空库、head、legacy 场景继续通过，并增加 readiness 与 Redis 断开/恢复
canary。失败诊断继续有界脱敏且 `always()` 清理容器、网络、卷与临时配置。

## REMOVED Requirements

### Requirement: 运行时任意 Python 工具开关

**Reason**: 30 秒 subprocess timeout 不是 CPU、内存、网络或文件系统沙箱，不能在
多用户 Agent 运行时作为可启用能力保留。

**Migration**: 删除 `ENABLE_CODE_EXECUTION` 环境示例、Compose 传递、默认工具注册
和系统提示；残留部署变量被忽略或在配置检查中稳定拒绝。未来恢复必须使用独立、
无凭据、无宿主挂载的隔离执行器并新建 change-id。

### Requirement: 搜索 raw content 与高体积 topic

**Reason**: raw content 和 images/videos/files topic 会绕过有界结果数，放大上下文、
网络与模型成本。

**Migration**: 模型工具 schema 只保留 query、`general|news` 和最多 5 条结果；
需要媒体或原始网页内容时另建受控摄取规格。

## Non-Goals

- 不建设通用分布式调度器、计费、自动封禁、跨区域配额或完整 SRE 平台。
- 不解决 Python 依赖锁定、LangGraph EOL 升级、备份恢复、schema 指纹或生产 TLS。
- 不调用真实模型、Tavily、生产 Redis/MySQL 或业务数据完成验收。
- 不以 liveness/readiness 代替外部监控、SLO、告警或长期指标。
- 不为已删除的 Python 执行工具实现半成品沙箱。
