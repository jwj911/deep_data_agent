# 请求限流与资源保护 Spec

## Why
第一方认证、可观测性基线已就位，但认证端点、模型查询和会话接口目前没有任何配额，
匿名暴力尝试或单用户突发调用可耗尽模型额度和后端资源。本迭代按身份维度加入
可观测、可降级的请求限流，保护高成本路径且不损害现有可用性。

## What Changes
- 新增基于 Redis 固定窗口计数的 `RateLimiter` 服务，Redis 故障时 **fail-open**
  并发出结构化降级事件。
- 新增 FastAPI 限流中间件：在请求 ID 绑定之后、业务处理之前执行，按身份维度和
  路由类别计数。
- 身份维度：认证请求按 JWT `sub`（仅解码签名与有效期，不查库）；匿名请求按客户端
  来源；来源解析遵循可信代理跳数边界，默认不信任 `X-Forwarded-For`。
- 路由类别配额：认证端点（防暴力）、高成本 `/api/query`（模型调用）、其他会话
  端点、全局默认，各自独立配额且计数隔离。
- 超限返回稳定 `429`，错误体为 `{code: "rate_limited", message, request_id}`，
  附 `Retry-After` 秒数；健康检查 `/api/health` 永不限流。
- 限流事件只记录维度类别、路由模板、配额键的不可逆摘要、窗口与计数，不记录原始
  Token、明文来源、提示词或业务数据。
- 新增环境变量契约、发布契约检查、确定性测试，并同步 README、AGENTS、
  项目分析、Roadmap 与 CHANGELOG。

## Impact
- Affected specs: add-observability-diagnostics（复用请求 ID 与事件）、
  secure-user-sessions（复用 JWT 身份）。
- Affected code:
  - `data_agent/config/config.py`（限流配置解析）
  - `data_agent/services/rate_limit_service.py`（新增）
  - `data_agent/observability/rate_limit_middleware.py`（新增）
  - `data_agent/agent_server.py`（挂载中间件与 429 语义）
  - `data_agent/services/auth_service.py`（复用无副作用的 token 解码）
  - `.env.example`、`docker-config/docker-compose.yml`
  - `scripts/check_release_contracts.py`
  - `tests/`（新增确定性测试）
  - `README.md`、`AGENTS.md`、`.trae/documents/project_analysis.md`、
    `.trae/documents/roadmap.md`、`CHANGELOG.md`

## ADDED Requirements

### Requirement: 按身份维度的请求限流
系统 SHALL 在 FastAPI 层按稳定身份维度对请求计数，并在超过对应路由类别配额时
拒绝请求。

#### Scenario: 认证用户超限被拒
- **WHEN** 同一 JWT `sub` 在窗口内对高成本端点的请求数超过该类别配额
- **THEN** 返回 `429`，错误体含 `code: "rate_limited"` 与 `request_id`，并携带
  `Retry-After`；窗口重置后同一用户恢复放行。

#### Scenario: 匿名来源按客户端隔离
- **WHEN** 两个不同客户端来源对认证端点发起请求
- **THEN** 各自独立计数；一个来源超限被拒不影响另一个来源。

#### Scenario: 不同用户计数隔离
- **WHEN** 用户 A 已达配额上限，用户 B 在同一窗口发起请求
- **THEN** 用户 B 不受用户 A 计数影响，正常放行。

### Requirement: Redis 故障时可用性优先
系统 SHALL 在 Redis 不可用时对限流采用 fail-open，放行请求并记录降级事件，不因
限流组件故障阻断正常业务。

#### Scenario: Redis 不可用放行
- **WHEN** 限流计数所需的 Redis 操作失败或不可用
- **THEN** 请求被放行，且发出 `rate_limit.degraded` 结构化事件，不返回 `429`。

### Requirement: 可信代理边界
系统 SHALL 仅在配置的可信代理跳数范围内解析 `X-Forwarded-For`，默认不信任该头，
以防伪造来源绕过匿名配额。

#### Scenario: 默认忽略伪造转发头
- **WHEN** `TRUSTED_PROXY_COUNT=0` 且请求携带伪造 `X-Forwarded-For`
- **THEN** 来源以直接连接地址为准，伪造头不改变计数键。

### Requirement: 脱敏的限流可观测性
系统 SHALL 使限流决策可通过请求 ID 关联，且事件不包含原始 Token、明文来源、
提示词或业务数据。

#### Scenario: 限流事件不泄露敏感值
- **WHEN** 发生放行或拒绝并产生限流事件
- **THEN** 事件仅含维度类别、路由模板、配额键摘要、窗口与计数，凭据与业务数据
  不出现在事件中。

### Requirement: 健康检查不受限流影响
系统 SHALL 永不对 `/api/health` 施加限流。

#### Scenario: 健康检查始终可达
- **WHEN** 其他端点已触发限流
- **THEN** `/api/health` 仍返回 `200`，不计入任何配额。

## MODIFIED Requirements

### Requirement: FastAPI 错误语义
FastAPI SHALL 在既有稳定错误码基础上新增 `429 rate_limited`，错误体保持
`{code, message, request_id}` 结构，并附 `Retry-After`；健康检查与既有 401/404/
503 语义不变。

## REMOVED Requirements
无。
