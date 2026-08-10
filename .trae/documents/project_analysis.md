# Deep Data Agent 项目分析

> 状态日期：2026-08-10。本文以当前工作树、已完成规格和本地确定性检查为依据，
> 不把候选能力或尚未取得的发布证据写成既成事实。

## 1. 当前定位

Deep Data Agent 是一个前后端分离的 AI 数据探索与智能问答项目。当前版本已经
完成可运行闭环和第一方多用户认证，不再是只有单一 Agent 脚本的原型：

- Next.js 前端通过 LangGraph SDK 访问流式 Agent，通过独立 REST 客户端访问
  FastAPI 认证接口。
- LangGraph 图和 FastAPI 应用已拆分为两个入口，职责和生命周期相互独立。
- MySQL 持久化用户、会话与消息，Redis 缓存 Agent 与搜索结果并支持故障降级。
- Docker Compose 编排 MySQL、Redis、FastAPI、LangGraph 和前端 5 个服务。
- 第一方认证使用 FastAPI、JWT 和 CORS 白名单，会话资源在服务层按用户隔离。

发布就绪治理已经完成并通过 GitHub Hosted CI。当前迭代是
`add-observability-diagnostics`，目标是用轻量、有界、可脱敏验证的事件与诊断
报告补齐定位能力，不在缺少运维方案时提前引入外部监控集群。

## 2. 实际架构

### 2.1 后端入口与调用链

`langgraph.json` 加载 `data_agent.agent_graph:agent`；图构建位于
`data_agent/services/agent_service.py`，不会导入 FastAPI 或触发数据库建表。
FastAPI 则从 `data_agent.agent_server:app` 启动，只在应用生命周期中调用
`init_db()`。

FastAPI 当前提供以下边界：

- `/api/health`：不调用真实模型的健康检查。
- `/api/query`：调用 Agent，使用稳定的非 2xx 配置错误和上游错误语义。
- `/api/auth/*`：注册、OAuth2 密码表单登录和当前用户查询。
- `/api/sessions/*`：要求 Bearer Token 的会话与消息接口。

Agent 默认注册互联网搜索和本地文档分析工具。任意 Python 代码执行工具只有在
人工设置 `ENABLE_CODE_EXECUTION=true` 时才会注册；当前实现不是沙箱。

FastAPI 全路由通过中间件建立请求上下文。客户端可发送严格的 32 位小写十六进制
`X-Request-ID`；服务会替换缺失或非法值，并在响应头中回传最终 ID。
`/api/query`、Agent、缓存和工具共享该上下文。前端为 LangGraph run 生成同格式
ID，并通过 `configurable` 和 `metadata` 传递，使工具事件可关联到对应 run。

### 2.2 数据与缓存

SQLAlchemy 模型共享同一份 `Base.metadata`，MySQL 表包括 `users`、`sessions`
和 `messages`。会话服务在创建、列表、读取、写入和删除时均使用当前用户 ID；
访问其他用户的资源统一返回 404，避免泄露资源存在性。

Redis 通过 `REDIS_URL` 配置。连接、读取或写入失败时，缓存服务降级为未命中，
不会阻断 Agent 主流程；诊断日志不输出查询正文或凭据。Agent 响应缓存当前使用
24 小时有效期。缓存命中、未命中、写入、无效值和不可用均使用固定低基数事件，
不记录缓存键或缓存内容。

### 2.3 前端边界

前端是 Next.js 15、React 19 和 TypeScript 项目，生产构建静态导出到
`/data_copilot/`。浏览器侧明确区分两类地址：

- `NEXT_PUBLIC_API_URL`：LangGraph 服务地址。
- `NEXT_PUBLIC_REST_API_URL`：FastAPI 第一方认证与会话服务地址。

第一方登录页直接调用 FastAPI 注册、登录和 `/api/auth/me`，不依赖外部授权码
交换。JWT 只保存在当前标签页的 `sessionStorage`，并且只附加到同源于配置的
FastAPI 请求。LangGraph API Key 如存在，仍由独立的 `localStorage` 键管理；
LangGraph 或第三方 401/403 不会清除第一方登录态。

REST 客户端为每次请求生成 `X-Request-ID`，并从响应头读取诊断 ID。新的
LangGraph 提交、重试、消息编辑和人工中断处理均生成独立 run 关联 ID。关联字段
不包含用户名、邮箱、消息正文或 Token。

### 2.4 容器闭环

Compose 使用以下服务名：`mysql`、`redis`、`fastapi`、`langgraph` 和
`frontend`。数据库与缓存的容器内连接使用服务名，浏览器公开地址则在前端构建
阶段注入，不能使用只在 Docker 网络中可解析的主机名。关键依赖通过健康检查和
`service_healthy` 控制启动顺序。

后端应用日志使用 UTC JSON Lines，同时写入标准输出与有界轮转文件。Compose 的
五个服务统一使用 Docker `json-file` 大小与文件数上限。当前默认上限为单份
10 MiB、3 份文件或备份；这是本地与受控部署基线，不是长期日志存储方案。

完整运行依赖 Docker Desktop Linux Engine。系统盘空间不足或宿主机 `3306`、
`6379` 端口冲突会阻断构建或启动；端口冲突应只通过 `.env` 中的宿主端口变量
重映射，不改变容器内部地址。

## 3. 已完成能力与验证基线

### 3.1 可运行闭环

`establish-runnable-baseline` 已完成入口拆分、依赖补齐、缺失前端工具模块修复、
公开地址统一、缓存降级、代码执行默认关闭、五服务 Compose 编排和端到端冒烟。
健康检查和确定性测试不需要真实模型响应。

### 3.2 第一方认证与所有权隔离

`secure-user-sessions` 已完成以下安全边界：

- JWT 密钥和有效期从环境变量读取，密钥缺失、过短或为占位值时不签发 Token。
- JWT `sub` 使用不可变用户 ID，并校验签名、算法、有效期和用户存在性。
- CORS 使用明确来源白名单；启用凭据时拒绝通配符来源。
- 注册、登录、`/me`、会话标题、消息角色和正文具有稳定校验及错误语义。
- 所有会话和消息操作均在服务层按 `session_id` 与 `user_id` 联合过滤。
- 前端第一方 Token 从持久化存储迁移到 `sessionStorage`。

发布就绪治理将自动测试扩展到 75 项，并建立 Backend、Frontend 与 Release
Contracts 三个 Hosted CI job。当前可观测性迭代继续增加请求 ID、结构化事件、
脱敏、日志轮转、诊断聚合、倒序时间线和高频折叠测试；当前全量确定性测试为
103 项，且不调用真实模型或搜索服务。

### 3.3 按身份维度的请求限流

`add-request-rate-limiting` 在 FastAPI 层加入按身份维度的请求限流，复用现有请求
ID 与低基数脱敏事件：

- 限流中间件在请求 ID 绑定之后、业务处理之前执行，对认证端点、高成本
  `/api/query`、其他会话端点和全局默认四类分别计数，四类配额相互独立且计数隔离。
- 认证请求按 JWT `sub`（无副作用解码，不查库）计数，匿名请求按客户端来源计数；
  不同用户、不同来源相互隔离。
- 计数使用 Redis 固定窗口（`INCR` 加首次 `EXPIRE`）；超限返回稳定 `429`，错误体
  为 `{code: "rate_limited", message, request_id}` 并附 `Retry-After`。
- `TRUSTED_PROXY_COUNT` 默认 `0`，不信任 `X-Forwarded-For`，伪造转发头不改变
  计数键；`/api/health` 永不受限，`RATE_LIMIT_ENABLED=false` 可整体关闭。
- Redis 不可用或出错时 fail-open 放行并发出 `rate_limit.degraded` 事件；限流
  事件只含维度类别、路由模板、配额键摘要、窗口与计数，不含原始 Token、明文
  来源、提示词或业务数据。

## 4. 可观测性与诊断现状

### 4.1 当前实现

- 事件 schema 固定包含版本、UTC 时间、级别、服务、logger、事件名和可选请求
  ID；业务字段只允许固定白名单。
- HTTP 事件使用路由模板，不记录查询参数、请求体、客户端 IP 或身份字段。
- Agent、模型、缓存和工具记录开始、完成、失败或降级生命周期，不记录提示词、
  消息正文、工具输入输出或缓存键值。
- 日志消息、异常类型、结构化字段和诊断导出复用凭据、Token、密码与连接串
  脱敏规则。
- `scripts/export_diagnostics.py` 由人工触发，可按请求 ID 过滤或生成整体摘要；
  时间线按新到旧排序，健康检查折叠统计。
- 报告汇总请求数、5xx 错误率、平均/最大/P95 延迟、缓存降级和模型失败，并生成
  本地告警信号，不自动上传或发送通知。

### 4.2 当前边界与技术债

1. **外部观测平台延期**：当前没有 OpenTelemetry Collector、Prometheus、
   Grafana、SLO 看板、长期日志存储或通知渠道。引入前必须评审访问控制、成本和
   保留周期。
2. **迁移能力有限**：数据库仍依赖 `Base.metadata.create_all()`，没有 Alembic
   或版本化 schema 迁移流程。
3. **LangGraph 认证边界有限**：本地 LangGraph 仍使用 noop 认证；第一方 JWT
   目前只保护 FastAPI 认证与会话接口。
4. **授权模型有限**：已加入按身份维度的请求限流，但仍无 Refresh Token、密码
   找回、邮箱验证、OAuth、RBAC 或管理员审计。限流为单实例本地 Redis 固定窗口，
   非分布式令牌桶，也无自动封禁；Redis 故障时 fail-open。
5. **高风险工具未沙箱化**：代码执行虽默认关闭，但显式启用后仍可运行任意
   Python；文档分析也只适用于受控本地文件。
6. **历史凭据风险已接受但未消除**：旧 Moonshot/Tavily 凭据已轮换失效，新值
   仅存本地；旧值仍在 Git 历史中。历史重写必须在干净工作区人工发起，并与所有
   协作者协调，不能在业务迭代中直接执行。

## 5. 发布判断

项目已具备本地开发、受控 Docker 环境和自动 CI 的发布基线。可观测性迭代提供
可重复的本地诊断能力，但不应被描述为完整生产监控平台。请求限流已复用当前低
基数事件和脱敏边界，采用 Redis 故障时 fail-open 策略与默认不信任 `X-Forwarded-For`
的可信代理边界；它是单实例本地固定窗口，不等同于分布式速率控制。

任何后续能力验证都必须人工触发，使用脱敏数据或专用测试数据；真实密钥、Token、
业务数据和可识别用户信息不得进入提示词、日志、测试固件、CI 产物或版本控制。
