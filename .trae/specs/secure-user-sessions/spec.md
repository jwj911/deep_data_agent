# 多用户认证与会话隔离 Spec

## Why

项目已具备可运行的前后端与容器闭环，但 FastAPI 的 JWT 密钥仍为硬编码占位值，会话接口固定使用 `user_id = 1`，资源读取、写入和删除均未校验归属，无法安全支持真实多用户。本轮建立最小可用的第一方认证与会话隔离边界，并让前端登录契约与后端一致。

## What Changes

- 将 JWT 密钥、有效期和 CORS 来源迁移为经过校验的环境配置。
- 增加统一的当前用户依赖和 `/api/auth/me`，使用不可变用户 ID 作为 JWT subject。
- 保护全部会话与消息接口，所有查询和变更均按当前用户过滤。
- 对注册、登录、会话标题、消息角色与正文增加稳定输入校验和错误语义。
- 将前端登录页改为与 FastAPI 对齐的用户名/密码登录和注册流程。
- 将前端认证 Token 从持久化 `localStorage` 迁移到当前标签页的 `sessionStorage`。
- 增加双用户越权、无效/过期 Token、CORS 与前端认证流程测试。
- 更新环境示例、Docker 配置和运行文档。
- **BREAKING**：移除未与当前后端对齐的授权码回调配置 `NEXT_PUBLIC_LOGIN_API_URL`，改用 `NEXT_PUBLIC_REST_API_URL`。

本轮不包含：

- LangGraph API 的生产认证；本地 LangGraph 仍使用现有 noop 认证。
- Refresh Token、密码找回、邮箱验证、OAuth、角色权限和管理员后台。
- 将 LangGraph 线程历史迁移到 FastAPI 会话表，或在聊天主界面展示 REST 会话列表。
- Alembic 等数据库迁移框架；本轮不修改现有表结构。

## Impact

- Affected specs: 用户注册与登录、JWT 身份解析、会话与消息访问控制、前端认证、CORS、自动化验证。
- Affected code: `data_agent/config/`、`data_agent/services/auth_service.py`、`data_agent/services/session_service.py`、`data_agent/routes/`、`data_agent/agent_server.py`、`agent_chatui/src/app/login/`、`agent_chatui/src/lib/api-key.ts`、前端配置、`.env.example`、Docker Compose、README 与测试文件。

## ADDED Requirements

### Requirement: 经过校验的认证配置

系统 SHALL 从环境变量读取 `JWT_SECRET_KEY`、`JWT_ACCESS_TOKEN_EXPIRE_MINUTES` 和 `CORS_ALLOWED_ORIGINS`。

`JWT_SECRET_KEY` SHALL 至少为 32 个字符且不得为示例占位值。健康检查 MAY 在未配置 JWT 时保持可用，但注册、登录、当前用户和会话接口 SHALL 返回稳定的 `503 auth_not_configured`，不得使用内置默认密钥签发 Token。

`CORS_ALLOWED_ORIGINS` SHALL 解析为明确来源列表；启用凭据时不得与通配符 `*` 同时使用。

#### Scenario: 缺少 JWT 密钥

- **WHEN** 服务未配置有效 `JWT_SECRET_KEY`
- **THEN** `/api/health` 返回 HTTP 200
- **THEN** 认证与会话接口返回 HTTP 503 和稳定错误码
- **THEN** 系统不签发使用默认密钥的 Token

#### Scenario: 配置多个前端来源

- **WHEN** `CORS_ALLOWED_ORIGINS` 包含多个逗号分隔来源
- **THEN** FastAPI 仅允许这些来源
- **THEN** 未列出的来源不获得跨域授权响应头

### Requirement: 当前用户身份依赖

系统 SHALL 提供统一的 `get_current_user` 依赖，从 Bearer Token 解析 JWT，校验签名、算法、有效期和 subject，并从数据库加载用户。

JWT 的 `sub` SHALL 使用用户 ID 字符串。无 Token、格式错误、签名错误、过期、subject 非法或用户不存在时，系统 SHALL 返回不泄露内部原因的 HTTP 401，并包含 `WWW-Authenticate: Bearer`。

#### Scenario: 获取当前用户

- **WHEN** 已登录用户携带有效 Bearer Token 请求 `/api/auth/me`
- **THEN** 返回当前用户 ID、用户名和邮箱
- **THEN** 响应不包含密码哈希或 Token 内容

#### Scenario: Token 已过期

- **WHEN** 客户端使用已过期 Token 请求受保护接口
- **THEN** 返回 HTTP 401 和统一认证错误
- **THEN** 日志不记录原始 Token

### Requirement: 用户注册与登录

系统 SHALL 校验用户名长度为 3–50 个字符、密码长度至少 8 个字符，并校验邮箱格式。重复用户名或邮箱 SHALL 返回稳定的 HTTP 409；数据库唯一约束竞争 SHALL 被转换为相同语义。

登录接口 SHALL 继续接受 OAuth2 Password Form，并以统一错误响应处理用户名不存在和密码错误。成功登录 SHALL 返回 `access_token`、`token_type = bearer` 和过期秒数。

#### Scenario: 注册并登录

- **WHEN** 用户使用有效且未占用的用户名、邮箱和密码注册
- **THEN** 密码只以哈希形式存储
- **WHEN** 用户使用正确凭据登录
- **THEN** 返回以用户 ID 为 subject 的限时访问 Token

#### Scenario: 重复注册

- **WHEN** 两个请求尝试注册相同用户名或邮箱
- **THEN** 至多创建一个用户
- **THEN** 失败请求返回 HTTP 409 且不暴露数据库异常

### Requirement: 会话资源按用户隔离

所有 `/api/sessions` 接口 SHALL 要求有效当前用户。创建和列表接口 SHALL 使用当前用户 ID，不得使用固定用户。

获取会话、读取消息、添加消息和删除会话 SHALL 同时按 `session_id` 与当前用户 ID 查询。不存在或属于其他用户的资源 SHALL 统一返回 HTTP 404，避免泄露资源存在性。

#### Scenario: 用户访问自己的会话

- **WHEN** 用户创建、查询、添加消息或删除自己的会话
- **THEN** 操作成功
- **THEN** 列表只包含该用户的会话

#### Scenario: 用户越权访问他人会话

- **WHEN** 用户 A 使用用户 B 的 `session_id` 读取、写入或删除
- **THEN** 每种操作均返回 HTTP 404
- **THEN** 用户 B 的会话与消息保持不变

### Requirement: 会话输入约束

会话标题 SHALL 去除首尾空白并限制为 1–255 个字符。消息角色 SHALL 仅允许 `user` 或 `assistant`，消息正文 SHALL 去除首尾空白并限制为 1–20000 个字符。

#### Scenario: 无效会话输入

- **WHEN** 客户端提交空标题、空消息、超长内容或未知角色
- **THEN** 返回 HTTP 422
- **THEN** 数据库不产生部分写入

### Requirement: 第一方前端认证

前端 SHALL 使用 `NEXT_PUBLIC_REST_API_URL` 连接 FastAPI。登录页 SHALL 提供用户名/密码登录与用户名/邮箱/密码注册，不再依赖授权码查询参数。

成功登录后，前端 SHALL 将 Bearer Token 保存到 `sessionStorage`，并能调用 `/api/auth/me` 验证身份。刷新同一标签页可保留登录状态，关闭标签页后 Token 不应长期持久化。

#### Scenario: 前端登录成功

- **WHEN** 用户在登录页提交正确凭据
- **THEN** 前端保存访问 Token、验证当前用户并返回聊天页
- **THEN** 后续 FastAPI 请求携带 Bearer Token

#### Scenario: 登录失效

- **WHEN** `/api/auth/me` 或受保护 FastAPI 请求返回 401
- **THEN** 前端清除 Token 并跳转到登录页
- **THEN** 不在 URL、日志或错误提示中展示 Token

### Requirement: 认证与隔离测试基线

项目 SHALL 使用独立测试数据库执行认证与会话集成测试，不依赖真实 MySQL、Redis、Moonshot 或 Tavily。

测试 SHALL 覆盖注册、登录、当前用户、无效/过期 Token、缺失 JWT 配置、重复注册、双用户会话隔离、输入校验和 CORS。

#### Scenario: 执行确定性认证测试

- **WHEN** 开发者运行后端测试套件
- **THEN** 认证和会话测试不访问外部服务
- **THEN** 测试数据不写入开发或容器数据库

## MODIFIED Requirements

### Requirement: FastAPI CORS 策略

FastAPI SHALL 使用配置的来源白名单替代 `allow_origins=["*"]`，并仅开放前端所需方法与请求头。配置错误 SHALL 在应用装配或启动时给出可定位且不泄密的错误。

#### Scenario: 非白名单来源请求

- **WHEN** 浏览器从未配置来源发起预检请求
- **THEN** 响应不包含允许该来源的 CORS 头

### Requirement: 会话服务查询契约

现有 `SessionService` 的单会话查询、消息查询、消息创建和删除方法 SHALL 接受 `user_id`，并在服务层完成归属过滤。路由层不得先无归属加载再单独比较，以减少遗漏访问控制的风险。

#### Scenario: 服务层归属过滤

- **WHEN** 服务方法收到与会话所有者不匹配的 `user_id`
- **THEN** 返回未找到语义
- **THEN** 不执行消息插入、删除或会话更新时间修改

### Requirement: 前端认证失败处理

现有全局请求处理 SHALL 只对 FastAPI 认证失败执行清理与登录跳转，不得将 LangGraph、第三方资源或其他 HTTP 401/403 一律视为第一方登录失效。

#### Scenario: LangGraph 或第三方返回 401

- **WHEN** 非 FastAPI 请求返回 401 或 403
- **THEN** 前端保留第一方登录状态
- **THEN** 使用原有错误展示处理该请求

## REMOVED Requirements

### Requirement: 授权码回调登录

**Reason**: 当前 `/login?code=...` 前端流程与 FastAPI 的 OAuth2 Password Form 不兼容，项目也没有实现授权码交换服务，保留该流程会制造不可用入口。

**Migration**: 移除 `NEXT_PUBLIC_LOGIN_API_URL`，配置 `NEXT_PUBLIC_REST_API_URL` 指向 FastAPI；用户通过第一方用户名/密码页面注册和登录。未来如引入 OAuth，应作为独立规格实现完整的 state、回调与 Token 交换流程。
