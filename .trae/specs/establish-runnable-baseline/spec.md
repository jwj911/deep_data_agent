# 建立可运行闭环 Spec

## Why

项目已有后端模块化、会话持久化和容器化改动，但 LangGraph 导出、FastAPI 入口、前端配置和 Docker 启动协议尚未对齐，当前无法形成可重复验证的端到端运行闭环。本轮先建立稳定的开发基线，为后续认证强化和数据分析能力迭代消除基础阻塞。

## What Changes

- 分离 LangGraph 图导出与 FastAPI 应用启动职责，消除数据库初始化等导入期副作用。
- 补齐后端实际使用的运行时与测试依赖，统一数据库、Redis、模型和服务地址配置。
- 默认禁用任意 Python 代码执行工具，仅允许通过显式环境变量人工启用。
- 补齐前端缺失的 `src/lib` 契约，统一流式调用与线程列表使用的 LangGraph 地址及助手 ID。
- 修正前端可选认证行为，不再发送空 Bearer Token，也不因未配置登录地址而阻断本地聊天。
- 校正静态前端、FastAPI、LangGraph、MySQL 和 Redis 的 Docker Compose 构建及启动关系。
- 增加不依赖真实模型调用的后端测试、前端静态检查、Compose 校验和端到端冒烟检查。
- 更新项目运行说明与环境变量示例，使本地开发和容器启动步骤可复现。

本轮不包含：

- 完整的 JWT 会话归属与角色权限改造。
- 代码执行沙箱；本轮仅默认关闭高风险工具。
- 新增文件导入、图表、报告生成或多模型切换能力。
- 生产级 LangGraph 部署、CI/CD、监控告警或自动扩缩容。

## Impact

- Affected specs: LangGraph 对话、FastAPI 服务、前端聊天连接、运行时配置、容器化开发、质量验证。
- Affected code: `langgraph.json`、`.env.example`、`requirements.txt`、`data_agent/`、`agent_chatui/`、`docker-config/docker-compose.yml`、`README.md` 及新增测试文件。

## ADDED Requirements

### Requirement: 可独立加载的服务入口

系统 SHALL 分别提供可被 `langgraph.json` 加载的 LangGraph 图对象和可被 ASGI 服务器加载的 FastAPI `app`，且加载任一入口时不得隐式启动另一个服务器。

数据库建表、外部连接探测等生命周期操作 SHALL 在对应服务启动阶段执行，不得在普通模块导入阶段执行。

#### Scenario: 加载 LangGraph 图

- **WHEN** LangGraph CLI 按 `langgraph.json` 导入配置的图路径
- **THEN** 路径存在并导出名为 `agent` 的可运行图对象
- **THEN** 导入过程不要求 MySQL 已经可连接

#### Scenario: 加载 FastAPI 应用

- **WHEN** Uvicorn 导入 FastAPI 应用
- **THEN** 应用导出成功且 `/api/health` 可用于健康检查
- **THEN** 健康检查不触发真实模型调用

### Requirement: 明确且完整的运行时配置

系统 SHALL 在依赖清单中声明代码实际导入的 Python 包，并移除重复依赖项。

系统 SHALL 通过环境变量配置模型密钥、数据库、Redis、服务监听地址和高风险工具开关；示例环境文件 SHALL 仅包含占位值，不得包含真实凭据。

缺少模型调用所需配置时，系统 SHALL 返回可定位的配置错误，不得在日志或响应中泄露密钥。

#### Scenario: 无密钥执行确定性检查

- **WHEN** 开发者未提供真实 Moonshot 或 Tavily 密钥而运行单元测试、类型检查或健康检查
- **THEN** 所有不需要外部模型的检查均可执行
- **THEN** 系统不会发起外部模型或搜索请求

#### Scenario: Redis 不可用

- **WHEN** Redis 暂时不可连接
- **THEN** Agent 查询可降级为不使用缓存
- **THEN** 日志记录可诊断的降级信息而不泄露查询敏感数据或凭据

### Requirement: 高风险工具默认关闭

系统 SHALL 默认不向 Agent 注册任意 Python 代码执行工具。只有开发者显式启用对应环境变量时，系统 MAY 注册该工具，并 SHALL 在启动日志中记录不含敏感信息的风险提示。

#### Scenario: 使用默认配置创建 Agent

- **WHEN** 开发者未设置代码执行启用开关
- **THEN** Agent 工具列表不包含任意 Python 代码执行能力

### Requirement: 可构建的前端连接层

前端 SHALL 补齐所有被引用的本地工具模块，并使用与当前 LangGraph SDK 版本兼容的类型和行为。

流式对话、线程查询和连接状态检查 SHALL 使用同一组解析后的 LangGraph 地址、助手 ID 和可选认证信息。认证信息为空时，前端 SHALL 省略对应请求头。

构建流程 SHALL 启用 TypeScript 与 ESLint 错误检查，不得通过 `ignoreBuildErrors` 或 `ignoreDuringBuilds` 隐藏失败。

#### Scenario: 本地无认证连接

- **WHEN** 前端使用本地 LangGraph 地址且浏览器中没有 API Key 或 JWT
- **THEN** 前端不发送空的 `Authorization` 或 `X-Api-Key` 请求头
- **THEN** 状态检查、线程列表和消息流均指向同一个 LangGraph 服务

#### Scenario: 前端生产构建

- **WHEN** 开发者执行前端类型检查、Lint 和生产构建
- **THEN** 缺失模块、未导出配置或类型错误会导致检查失败
- **THEN** 通过检查后生成可部署的静态产物

### Requirement: 可复现的本地容器闭环

Docker Compose SHALL 能从仓库根上下文构建所需镜像，并启动 MySQL、Redis、FastAPI、LangGraph 和静态前端服务。

浏览器使用的公开 LangGraph 地址 SHALL 在前端构建阶段注入，不得使用仅容器内部可解析的主机名。服务间依赖 SHALL 使用健康检查或等价的就绪条件，避免仅依赖启动顺序。

#### Scenario: 启动完整开发栈

- **WHEN** 开发者提供必要密钥并执行文档中的 Docker Compose 启动命令
- **THEN** 前端静态页面可通过文档约定路径访问
- **THEN** FastAPI 健康端点与 LangGraph 信息端点均可访问
- **THEN** 前端可建立线程并向 `agent` 图提交消息

#### Scenario: 校验 Compose 配置

- **WHEN** 开发者执行 `docker compose config`
- **THEN** 构建上下文、变量引用、网络、卷和服务依赖均可被解析

### Requirement: 最小自动验证基线

项目 SHALL 提供不调用真实外部 AI 服务的后端测试，并 SHALL 提供前端类型检查、Lint、格式检查和生产构建命令。

Python 导入顺序 SHALL 通过 `isort` 检查。冒烟验证 SHALL 覆盖 FastAPI 健康端点、LangGraph 信息端点和前端静态入口。

#### Scenario: 执行本地质量检查

- **WHEN** 开发者按照文档执行验证命令
- **THEN** 后端测试、`isort`、前端类型检查、Lint、格式检查和构建均明确通过或以非零状态失败
- **THEN** 验证过程不依赖真实模型响应的内容与可用性

## MODIFIED Requirements

### Requirement: Agent 查询错误语义

现有 Agent 查询能力 SHALL 保留缓存与工具调用行为，但内部异常不得被包装成以 `Error:` 开头的成功响应。FastAPI SHALL 将可预期的配置错误与上游调用错误映射为明确的非 2xx 响应，并记录可关联、已脱敏的诊断信息。

#### Scenario: 上游模型调用失败

- **WHEN** 模型提供方拒绝请求或暂时不可用
- **THEN** 查询 API 返回非 2xx 状态和稳定的错误结构
- **THEN** 服务日志包含可关联的诊断信息但不包含 API Key

### Requirement: 前端认证为可选集成

现有登录回调和 Token 存储 SHALL 不再成为本地 LangGraph 聊天的强制前置条件。只有配置了登录入口时，前端 MAY 在认证失败后跳转；未配置时 SHALL 保留当前页面并展示错误提示。

#### Scenario: 未配置登录入口

- **WHEN** 请求返回认证错误且前端没有配置登录地址
- **THEN** 前端清理失效 Token 并展示提示
- **THEN** 前端不跳转到空地址、未定义地址或不存在的登录接口

