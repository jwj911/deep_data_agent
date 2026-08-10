# 可观测性与发布诊断 Spec

## Why

当前系统只有 `/api/query` 局部 `request_id` 和文本日志，认证、会话、LangGraph、
工具、缓存与模型调用无法用统一 ID 串联，也缺少可重复、可脱敏验证的诊断导出。
本迭代建立轻量可观测性基线，使故障能够定位，同时避免引入尚未具备运维条件的
外部监控集群。

## What Changes

- 为全部 FastAPI 请求生成或校验 `X-Request-ID`，在响应头、错误响应和结构化日志
  中回传同一 ID。
- 前端 REST 请求和 LangGraph run 生成独立请求 ID；LangGraph 通过
  `configurable` 与 `metadata` 传递关联信息。
- 将后端日志改为 JSON Lines 结构化事件，统一 UTC 时间、服务名、事件名、结果、
  耗时和请求 ID，并继续执行凭据与连接串脱敏。
- 为 HTTP、缓存、Agent、模型和工具调用增加低基数事件；不得记录提示词、消息
  正文、用户名、邮箱、Token、API Key、连接串或原始业务数据。
- 使用标准输出和有界轮转文件作为本阶段存储方案；Docker 日志设置大小与文件数
  上限，防止无界磁盘增长。
- 增加人工触发的诊断导出 CLI，可按请求 ID 生成倒序时间线，折叠健康检查等高频
  噪声，并汇总错误率、延迟、缓存降级和模型失败告警信号。
- 更新环境示例、Compose、README、Roadmap、CHANGELOG 和发布契约测试。
- 外部 OpenTelemetry Collector、Prometheus、Grafana、告警通知渠道及长期日志
  存储不在本迭代范围内。

## Impact

- Affected specs: 请求关联、结构化日志、诊断导出、日志保留、发布验证。
- Affected code: FastAPI 中间件、日志配置、Agent/工具/缓存服务、前端 REST 与
  LangGraph 客户端、Docker Compose、测试、脚本与项目文档。

## ADDED Requirements

### Requirement: 全链路请求关联

系统 SHALL 为每个 FastAPI 请求提供符合格式要求的 32 位小写十六进制
`request_id`。合法的客户端 `X-Request-ID` SHALL 被复用；缺失或非法值 SHALL
被替换。响应 SHALL 通过 `X-Request-ID` 回传最终值。

#### Scenario: 客户端提供合法 ID

- **WHEN** 客户端携带合法 `X-Request-ID` 请求任意 FastAPI 路由
- **THEN** 响应头、请求完成事件和错误详情使用同一 ID

#### Scenario: 客户端 ID 缺失或非法

- **WHEN** 请求未携带 ID，或 ID 不符合 32 位小写十六进制格式
- **THEN** 服务生成新 ID，且不把非法原值写入日志

### Requirement: LangGraph 关联上下文

前端 SHALL 为每次新的 LangGraph 提交生成请求 ID，并通过 run `configurable` 与
`metadata` 传递。后端 Agent 与工具 SHALL 在可取得运行配置时绑定该 ID；直接
FastAPI 调用 SHALL 沿用中间件 ID。

#### Scenario: 前端提交 Agent 请求

- **WHEN** 用户提交、重试或处理人工中断
- **THEN** 对应 LangGraph run 带有请求 ID，工具事件可使用该 ID 关联

### Requirement: 结构化脱敏事件

系统 SHALL 以单行 JSON 输出事件。每条事件至少包含 schema 版本、UTC 时间、
日志级别、服务名、logger 和事件名；存在请求上下文时 SHALL 包含 `request_id`。
事件字段 SHALL 使用固定低基数白名单。

#### Scenario: 敏感信息进入日志参数或异常

- **WHEN** Token、API Key、密码、数据库连接串或 Redis 连接串出现在消息、
  事件字段或异常文本中
- **THEN** 输出使用 `[REDACTED]` 替代敏感值

#### Scenario: HTTP 请求完成

- **WHEN** FastAPI 请求返回或发生未处理异常
- **THEN** 事件只记录方法、路由模板、状态码、结果和耗时，不记录查询参数、
  请求体、客户端 IP 或用户身份

### Requirement: 有界日志保留

系统 SHALL 同时支持标准输出和可配置轮转文件。文件大小、备份数与 Docker 日志
上限 SHALL 有明确默认值和环境变量契约。

#### Scenario: 日志达到上限

- **WHEN** 单个日志文件或容器日志达到配置大小
- **THEN** 旧日志按备份数量轮转，不允许无界增长

### Requirement: 人工诊断导出

系统 SHALL 提供只读 CLI，从 JSON Lines 日志生成脱敏 JSON 报告。报告 SHALL
包含输入范围、摘要、告警信号、折叠统计和按时间新到旧排列的关键时间线。

#### Scenario: 按请求 ID 导出

- **WHEN** 操作者显式传入日志路径与请求 ID
- **THEN** 报告只包含该 ID 的事件，并汇总状态码、错误和总耗时

#### Scenario: 生成发布诊断摘要

- **WHEN** 操作者不指定请求 ID
- **THEN** 报告汇总 HTTP 错误率与延迟、缓存降级和模型失败，健康检查等高频
  事件只保留折叠计数

#### Scenario: 诊断输入包含非 JSON 或敏感文本

- **WHEN** 输入中存在无法解析的行或可能的敏感值
- **THEN** CLI 跳过无效行、再次执行脱敏，且不在错误信息中回显原始内容

### Requirement: 可验证发布契约

自动测试 SHALL 覆盖 ID 校验与传播、CORS 头、结构化字段、脱敏、日志轮转配置、
事件聚合、倒序时间线和噪声折叠。既有后端、前端与发布门禁 SHALL 保持通过。

#### Scenario: CI 执行

- **WHEN** 主分支推送或合并请求触发 Release Readiness
- **THEN** 新增可观测性测试与既有 Backend、Frontend、Release Contracts
  门禁共同执行，任何失败返回非零

## MODIFIED Requirements

### Requirement: 健康检查

`/api/health` SHALL 保持无需 JWT、模型或外部搜索凭据即可访问。健康请求 SHALL
产生可折叠事件，但不得触发 Agent、模型或外部工具调用。

### Requirement: 稳定错误响应

FastAPI 的错误响应 SHALL 保持既有状态码和错误码；统一中间件 SHALL 通过响应头
提供请求 ID，Agent 错误详情 SHALL 继续包含同一请求 ID。

### Requirement: 日志脱敏

现有脱敏规则 SHALL 应用于普通日志、结构化事件字段、格式化异常和诊断导出。
新增配置值不得削弱既有 Moonshot、Tavily、JWT、数据库和 Redis 脱敏能力。

## REMOVED Requirements

无。
