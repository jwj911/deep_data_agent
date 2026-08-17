# 保护 Agent 租户边界 Spec

## Why

第一方 JWT 当前只保护 FastAPI 认证、会话和管理接口，主要 Chat UI 仍可匿名直连
LangGraph；线程检索没有主体所有权过滤，FastAPI `/api/query` 也未认证且响应缓存
仅由查询正文生成。同时，浏览器查询参数可覆盖 Agent Origin，并把 `localStorage`
中的 LangGraph API Key 发送到任意地址。进入文件与数据分析迭代前，必须让第一方
身份贯穿全部 Agent 入口并建立服务端默认拒绝的线程所有权。

## Decisions

- `DEC-001`：LangGraph threads 作为当前 Chat UI 的对话与运行状态主数据；MySQL
  继续作为用户、角色和既有 REST 会话 API 的主数据。本轮不做双写，也不声称两套
  会话历史一致。
- `DEC-002`：当前 LangGraph `0.7.28` 使用 `langgraph.json` 自定义 Auth 验证第一方
  JWT，并在资源层执行线程所有权；不新增 FastAPI 流式代理或独立网关。
- 浏览器只连接构建时注入的 `NEXT_PUBLIC_API_URL` 和
  `NEXT_PUBLIC_ASSISTANT_ID`，不接受查询参数、表单或运行时存储覆盖。
- 第一方 JWT 继续只存当前标签页 `sessionStorage`，并作为
  `Authorization: Bearer <token>` 发送到配置的 FastAPI 与 LangGraph Origin。
  旧 LangGraph API Key 从 `localStorage` 清理后不再读取或发送。
- LangGraph 所有者键使用不可变数据库用户 ID 的字符串形式；内部资源 metadata
  可以保存该标识，但日志、错误和诊断不得输出原始主体、Token 或消息正文。
- 当前仍只支持本地或受控网络部署。生产网络、TLS、Secret Store 与企业自托管
  支持边界继续由 `define-production-hosting-boundary` 决定。

## What Changes

- 新增 LangGraph Auth 模块：验证 Bearer JWT 的签名、算法、过期时间和 `sub`，
  再查询数据库确认用户仍存在并读取最新角色。
- `langgraph.json` 加载该 Auth；授权采用全局默认拒绝，只允许认证用户访问固定
  Agent 所需的 assistant 读取与自己的 thread/run 操作。
- 创建线程或 run 时服务端强制写入 `owner` metadata；读取、搜索、更新、删除和
  run 操作始终返回当前主体的 owner filter，管理员不绕过所有权。
- FastAPI `/api/query` 增加第一方认证与明确的 Agent 调用权限；AgentService 在
  服务层再次校验，并让缓存键包含主体、模型和工具策略边界。
- 前端移除 `apiUrl`、`assistantId` 查询参数覆盖、连接表单和 LangGraph API Key
  持久化；LangGraph SDK 固定连接构建配置并携带第一方 JWT。
- 为认证、资源授权、租户缓存和前端连接增加确定性测试及发布契约。
- 容器冒烟增加双用户线程隔离：匿名拒绝、各自只能搜索自己的线程、跨用户
  读/写/续跑/删除拒绝；测试不调用真实模型或搜索。
- 同步 README、AGENTS、项目分析、Roadmap、CHANGELOG 与本规格状态；验收后创建
  原子提交并推送 GitHub，等待全部 Hosted Job 通过。
- 本轮对匿名 `/api/query` 和匿名 LangGraph 资源访问是 **BREAKING** 变化：
  FastAPI 返回稳定 `401`；锁定的 LangGraph `0.7.28` 认证中间件返回稳定 `403`。

## Impact

- Affected specs:
  - `secure-user-sessions`
  - `add-rbac-audit`
  - `add-request-rate-limiting`
  - `restore-runtime-release-gates`
  - `audit-project-roadmap`
- Affected code:
  - `langgraph.json`
  - 新增 `data_agent/security/` 或等价 Auth 模块
  - `data_agent/services/auth_service.py`
  - `data_agent/services/authorization_service.py`
  - `data_agent/services/agent_service.py`
  - `data_agent/agent_server.py`
  - `agent_chatui/src/providers/`
  - `agent_chatui/src/lib/api-key.ts` 及认证客户端
  - `scripts/check_release_contracts.py`
  - `scripts/verify_container_smoke.py`
  - `tests/`
  - `.github/workflows/release-readiness.yml`（仅在冒烟命令需要时定向更新）
  - `README.md`、`AGENTS.md`
  - `.trae/documents/project_analysis.md`、`.trae/documents/roadmap.md`
  - `CHANGELOG.md`

## ADDED Requirements

### Requirement: LangGraph 使用第一方 JWT 认证

LangGraph 受保护资源 SHALL 使用与 FastAPI 相同的 JWT 签名配置、算法和用户表。
认证处理器 SHALL 要求标准 Bearer 头，验证签名、过期时间和正整数 `sub`，并查询
数据库确认用户存在。认证成功后 SHALL 返回稳定主体 identity 与当前角色对应的
权限；任何失败由锁定的 LangGraph 认证中间件返回稳定 `403`，不泄露 Token 或
用户存在性。

#### Scenario: 有效用户访问

- **WHEN** 已登录用户使用当前有效 JWT 请求 LangGraph 受保护资源
- **THEN** Auth 返回该数据库用户的稳定 identity，后续授权使用同一主体

#### Scenario: 缺失或无效 JWT

- **WHEN** 请求缺少 Bearer Token，或 Token 格式、签名、算法、过期时间、`sub`
  任一无效
- **THEN** 请求在访问资源前返回 `403`，错误体与日志不含 Token

#### Scenario: Token 对应用户已删除

- **WHEN** Token 仍通过密码学验证但数据库中已无对应用户
- **THEN** LangGraph 返回与其他无效凭据一致的 `403`

#### Scenario: 角色变更即时生效

- **WHEN** 用户角色在 Token 签发后发生变化
- **THEN** 后续请求使用数据库当前角色构造权限，不信任 Token 中的旧角色

### Requirement: LangGraph 线程和运行默认拒绝并按 owner 隔离

LangGraph 授权 SHALL 采用全局默认拒绝。认证用户只可创建和操作 owner 等于自己
identity 的 thread/run；服务端 SHALL 覆盖调用方提供的 owner metadata，且管理员
默认也不得访问其他用户资源。

#### Scenario: 创建线程

- **WHEN** 用户创建 thread 或在 thread 上创建 run
- **THEN** 服务端强制写入当前 identity 的 owner metadata，并返回同一 owner filter

#### Scenario: 搜索和读取线程

- **WHEN** 两个用户分别搜索或读取 threads
- **THEN** 每个用户只得到自己的 threads；指定其他用户 thread ID 时返回不可枚举的
  `404` 或等价资源不可见语义

#### Scenario: 更新、删除和继续运行

- **WHEN** 用户尝试更新、删除、读取历史、写入状态或在其他用户 thread 上创建 run
- **THEN** owner filter 阻止操作且资源保持不变

#### Scenario: 未声明资源

- **WHEN** 用户访问 cron、store、assistant 写操作或其他未显式允许的资源
- **THEN** 全局默认拒绝返回 `403`

#### Scenario: 固定 assistant 读取

- **WHEN** 已认证用户读取或搜索当前配置的 Agent assistant
- **THEN** 允许只读访问；assistant 创建、更新和删除仍被拒绝

### Requirement: FastAPI Agent 入口要求主体并隔离缓存

FastAPI `/api/query` SHALL 要求新的固定权限 `agent.invoke_own`。路由层与
AgentService SHALL 双层默认拒绝；缓存键 SHALL 至少包含主体 identity、模型标识、
工具策略版本和查询正文的不可逆摘要。

#### Scenario: 匿名查询

- **WHEN** 客户端不带有效第一方 JWT 调用 `/api/query`
- **THEN** 在模型、工具和缓存访问前返回 `401`

#### Scenario: 授权查询

- **WHEN** 已认证的 `user` 或 `admin` 调用 `/api/query`
- **THEN** 路由和服务权限检查通过，调用上下文包含主体 identity

#### Scenario: 相同查询不同用户

- **WHEN** 两个用户提交完全相同查询
- **THEN** 两次请求使用不同缓存键，任何用户都不能命中另一用户的私有结果

#### Scenario: 服务层旁路

- **WHEN** 内部调用方绕过 FastAPI 直接调用 AgentService 且没有合法 actor
- **THEN** 服务层拒绝执行，不调用缓存、模型或工具

### Requirement: 浏览器 Agent 连接固定且只使用第一方 JWT

生产前端 SHALL 只使用构建时 `NEXT_PUBLIC_API_URL` 和
`NEXT_PUBLIC_ASSISTANT_ID`。任何 URL 查询参数、表单、`localStorage` 或运行时状态
不得改变 Agent Origin 或 assistant。LangGraph 请求 SHALL 携带当前
`sessionStorage` 第一方 JWT，不得读取或发送旧 `lg:chat:apiKey`。

#### Scenario: 恶意 URL 覆盖

- **WHEN** 用户打开带 `apiUrl`、`assistantId`、相似域名、混合协议或重定向参数的 URL
- **THEN** LangGraph 客户端仍只连接构建配置，攻击者 Origin 不收到任何认证材料

#### Scenario: 旧 API Key 清理

- **WHEN** 浏览器 `localStorage` 中存在旧 `lg:chat:apiKey`
- **THEN** 应用删除该键且不读取其值用于请求

#### Scenario: 发送第一方 JWT

- **WHEN** 已登录用户创建客户端、检查 `/info`、搜索 thread 或流式运行
- **THEN** 请求只向配置的 Agent Origin 附加 `Authorization: Bearer <JWT>`

#### Scenario: 未登录浏览器

- **WHEN** 当前标签页没有第一方 Token
- **THEN** AuthSession 在创建 LangGraph 客户端或发送请求前跳转登录页

### Requirement: 对话主数据边界明确

Chat UI SHALL 以 LangGraph threads 作为当前对话列表、状态和运行历史的唯一来源。
本轮不得把同一消息同时写入 MySQL `messages` 与 LangGraph，也不得宣称既有 REST
会话 API 与 LangGraph 历史同步。

#### Scenario: Chat UI 创建对话

- **WHEN** 用户从主聊天界面创建并运行对话
- **THEN** 只创建 owner 受保护的 LangGraph thread，不隐式创建 MySQL session

#### Scenario: 既有 REST 会话 API

- **WHEN** 客户端显式调用 `/api/sessions/*`
- **THEN** 现有 MySQL 所有权语义保持不变，但该资源不自动出现在 Chat UI thread 列表

### Requirement: 跨租户验证与发布闭环

测试 SHALL 覆盖认证、全部 thread/run 关键动作、缓存隔离和固定 Origin。容器冒烟
SHALL 使用两个专用用户和假配置验证匿名及跨用户拒绝，不调用模型。迭代完成后
SHALL 推送 GitHub 并确认目标 SHA 的全部 Hosted Job 成功。

#### Scenario: 双用户容器冒烟

- **WHEN** 在专用数据库中注册并登录用户 A、B，分别创建 threads
- **THEN** A、B 各自只能搜索、读取和操作自己的 thread；匿名 LangGraph 请求为
  `403`，匿名 FastAPI Agent 请求为 `401`，跨用户操作为资源不可见，数据库和
  thread 状态不变

#### Scenario: 远端交付

- **WHEN** 25 项验收全部通过并推送 `main`
- **THEN** Backend、Frontend、Release Contracts、Container Smoke 均绑定目标 SHA
  且成功，本地与远端 SHA 一致、工作区干净

## MODIFIED Requirements

### Requirement: 第一方身份保护范围

第一方 JWT 的保护范围从 FastAPI 认证、会话和管理接口扩展到 FastAPI Agent 入口
及 LangGraph 线程/运行资源。JWT 仍不进入 URL、日志、错误提示或持久化浏览器存储。

### Requirement: 前端连接配置

`NEXT_PUBLIC_API_URL` 和 `NEXT_PUBLIC_ASSISTANT_ID` 仍为公开构建配置，但成为唯一
Agent 连接来源。配置只能承载公开地址与标识，不得承载 Secret。

### Requirement: 请求关联

LangGraph run SHALL 继续使用独立请求 ID，并在认证后的 configurable/metadata 中
传播；owner 与 request ID 分离，二者均不得包含用户名、邮箱、Token 或消息正文。

## REMOVED Requirements

### Requirement: 浏览器 LangGraph API Key

**Reason**: 当前部署改用第一方 JWT，自定义 Agent Origin 与持久化 Key 的组合会造成
凭据外发。

**Migration**: 删除连接表单、API Key 输入、`X-Api-Key` 头和
`lg:chat:apiKey` 读取；应用启动时清理该旧键。

### Requirement: 查询参数覆盖 Agent 连接

**Reason**: `apiUrl` 与 `assistantId` 查询参数属于未授权运行时配置，可改变凭据目标
和资源边界。

**Migration**: 忽略并停止写入这些参数，保留 `threadId` 作为固定 Origin 下的当前
线程导航状态。

## Non-Goals

- 不建设组织、租户表、自定义角色、SSO/OAuth、Refresh Token、计费或跨区域部署。
- 不迁移或合并 MySQL sessions/messages 与 LangGraph threads 的历史数据。
- 不在本轮增加前端测试框架；关键连接边界使用纯函数、发布契约和容器集成测试验证。
- 不开放文件分析、数据分析或任意代码执行的新能力。
- 不解决 Agent 总超时、Redis 自动恢复、分页、备份恢复或生产托管边界。
