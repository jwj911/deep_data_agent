# 引入 RBAC 与脱敏审计 Spec

## Why

项目已有第一方认证、会话所有权隔离、请求限流、可观测性和版本化迁移，但所有已
认证用户仍只有同一种权限，管理员操作也没有统一授权与审计边界。根据 Roadmap，
下一轮先建立最小可用的 RBAC 与脱敏审计基线，再扩展数据分析和报告能力。

## What Changes

- 为用户增加固定 `user`、`admin` 角色；新用户和迁移后的既有用户均默认为
  `user`，不允许通过注册参数、用户名、邮箱或普通环境变量自动取得管理员角色。
- 建立集中式、默认拒绝的角色权限矩阵。会话权限限定为本人资源，管理员额外拥有
  用户列表读取和他人角色变更权限。
- 在路由依赖和服务层分别执行授权，避免仅依赖 HTTP 入口；管理员角色不绕过既有
  会话所有权过滤。
- 新增有界的管理员用户列表和角色变更 API；管理员不得修改自己的角色，防止通过
  当前请求移除最后一个可执行管理操作的身份。
- 新增仅按用户 ID、人工执行的管理员引导脚本，只允许把既有用户提升为
  `admin`，不接受用户名、邮箱、密码或 Token。
- 复用现有 UTC JSON Lines 与有界轮转日志记录管理员操作、授权拒绝、管理员引导
  和任意 Python 执行工具启用事件；身份只写入基于服务端密钥生成的稳定 HMAC
  引用，不写入原始用户 ID 或其他身份信息。
- 新增 Alembic 迁移、确定性授权/迁移/审计测试、发布契约和运行文档；前端仅同步
  当前用户的角色契约，本轮不提供管理员界面。
- 本轮不引入自定义角色/权限编辑、管理员代查他人会话、用户删除、Refresh Token、
  OAuth、长期审计数据库、外部 SIEM、自动封禁、数据导入分析或代码执行沙箱。

## Impact

- Affected specs: 第一方认证与会话隔离、版本化数据库迁移、可观测性与发布诊断、
  发布契约
- Affected code:
  - `data_agent/models/user.py`
  - `data_agent/services/auth_service.py`
  - `data_agent/services/session_service.py`
  - 新增授权、管理员与审计服务
  - `data_agent/routes/auth.py`、`data_agent/routes/session.py`
  - 新增 `data_agent/routes/admin.py`
  - `data_agent/agent_server.py`
  - `data_agent/observability/events.py`
  - `data_agent/tools/tool_manager.py`
  - 新增 `migrations/versions/*_add_user_role.py`
  - 新增 `scripts/bootstrap_admin.py`
  - `agent_chatui/src/lib/auth-client.ts`
  - `tests/`、发布契约与项目文档

## ADDED Requirements

### Requirement: 固定角色与默认拒绝权限矩阵

系统 SHALL 只定义 `user` 和 `admin` 两种角色，并在一个集中式权限矩阵中声明
角色能力。矩阵 SHALL 至少包含本人会话读取、写入、删除，以及管理员用户列表读取
和他人角色变更权限。未识别角色、未声明权限和缺失映射 SHALL 默认拒绝。

#### Scenario: 新注册用户取得最小权限

- **WHEN** 访客通过公开注册接口创建用户
- **THEN** 用户角色固定为 `user`，请求体中的额外角色字段不能提升权限

#### Scenario: 管理员只获得显式权限

- **WHEN** `admin` 用户请求受保护操作
- **THEN** 系统仅允许权限矩阵显式列出的能力，不授予读取或修改他人会话的隐式能力

#### Scenario: 未知角色默认拒绝

- **WHEN** 授权层收到不在固定角色集合中的角色值
- **THEN** 权限检查返回拒绝且不执行目标资源查询或写入

### Requirement: 路由与服务双层授权

受 RBAC 保护的操作 SHALL 在 FastAPI 路由依赖中先检查权限，并在执行数据访问的
服务方法中再次检查权限。服务层 SHALL 可被独立测试，不能假定调用方已经完成
授权。

#### Scenario: 普通用户尝试管理员操作

- **WHEN** 已认证 `user` 请求任意管理员用户或角色端点
- **THEN** 路由返回稳定 `403`（`code=forbidden`），且不查询目标用户是否存在

#### Scenario: 服务被绕过路由直接调用

- **WHEN** 调用方以 `user` 身份直接调用管理员服务
- **THEN** 服务在读取或写入前拒绝操作，数据库保持不变

#### Scenario: 管理员访问会话

- **WHEN** `admin` 尝试读取、写入或删除另一个用户的会话
- **THEN** 现有所有权过滤继续生效并返回与不存在资源一致的 `404`

### Requirement: 受限管理员用户管理 API

系统 SHALL 提供 `GET /api/admin/users` 和
`PATCH /api/admin/users/{user_id}/role`。用户列表 SHALL 使用非负 `offset` 和
`1..100` 的 `limit` 做有界分页，并按稳定用户 ID 排序。角色变更只接受固定角色，
在单个事务中完成，并对重复设置保持幂等。

#### Scenario: 管理员列出用户

- **WHEN** `admin` 使用合法分页参数请求用户列表
- **THEN** 返回有界、稳定排序的用户公开字段和角色，不返回密码哈希或 Token

#### Scenario: 管理员变更他人角色

- **WHEN** `admin` 将另一个既有用户的角色改为 `admin` 或 `user`
- **THEN** 事务提交后返回更新后的公开用户数据，后续请求立即使用数据库中的新角色

#### Scenario: 管理员修改自己的角色

- **WHEN** `admin` 以自己的用户 ID 调用角色变更端点
- **THEN** 返回稳定 `409`（`code=self_role_change_forbidden`）且角色不变

#### Scenario: 目标不存在

- **WHEN** 已通过管理员授权的调用方变更不存在的用户
- **THEN** 返回稳定 `404`（`code=user_not_found`）

### Requirement: 人工管理员引导

项目 SHALL 提供人工运行的 `scripts/bootstrap_admin.py --user-id <id>`。脚本
SHALL 使用应用数据库配置，只允许把既有 `user` 提升为 `admin`，对已是
`admin` 的目标保持幂等，并以非零退出码报告无效 ID、目标不存在、配置错误或
数据库失败。

#### Scenario: 引导首位管理员

- **WHEN** 操作者在受控环境中以正整数用户 ID 人工运行引导脚本
- **THEN** 对应既有用户被提升为 `admin`，脚本不输出用户名、邮箱、密码哈希、
  Token、连接串或原始用户 ID

#### Scenario: 不安全的引导输入

- **WHEN** 操作者提供用户名、邮箱、非正整数或未支持参数
- **THEN** 脚本拒绝执行且不修改数据库

### Requirement: 脱敏授权与管理审计

系统 SHALL 使用现有结构化事件管线记录管理员列表、角色变更、管理员引导、授权
拒绝和高风险代码执行工具启用。事件 SHALL 使用固定事件名和字段白名单，携带
可用的请求 ID、操作、权限、角色变化、结果及稳定 HMAC 身份引用；身份引用 SHALL
使用服务端 JWT 密钥派生，且事件不得包含原始用户 ID、用户名、邮箱、IP、Token、
密码、请求体、查询参数或数据库连接串。

#### Scenario: 角色变更成功

- **WHEN** 管理员成功改变另一个用户的角色
- **THEN** 产生可由请求 ID 关联的成功事件，包含脱敏 actor/target 引用及前后角色

#### Scenario: 授权被拒绝

- **WHEN** 已认证用户缺少管理员权限
- **THEN** 产生拒绝事件，但不记录目标是否存在或任何原始身份值

#### Scenario: 高风险工具启用

- **WHEN** 进程在人工配置 `ENABLE_CODE_EXECUTION=true` 后注册任意 Python 执行工具
- **THEN** 产生固定的高风险启用事件，且不把配置值或工具输入写入事件

### Requirement: 可重复的角色迁移

Alembic SHALL 在线性单 head 迁移中为 `users` 增加非空角色字段、固定值约束和
数据库默认值 `user`。升级 SHALL 把所有既有用户回填为 `user`，不删除或重建
用户、会话和消息；降级 SHALL 可移除本轮字段与约束。ORM metadata 与迁移后
schema SHALL 无漂移。

#### Scenario: 既有数据库升级

- **WHEN** 包含既有用户、会话和消息的数据库升级到新 head
- **THEN** 原数据保持不变，全部既有用户角色为 `user`

#### Scenario: 全新数据库初始化

- **WHEN** 空数据库直接升级到新 head
- **THEN** 新 schema 包含受约束的非空角色字段，注册用户默认角色为 `user`

### Requirement: 确定性验证与发布契约

本轮 SHALL 使用临时 SQLite、离线依赖和脱敏日志样本验证角色矩阵、双层授权、
水平/垂直越权、管理员引导、角色迁移、审计字段和前端响应解析，不访问真实
MySQL、Redis、模型、搜索服务或业务数据。发布契约 SHALL 阻止默认管理员、迁移
多 head、未受约束角色和敏感审计字段回归。

#### Scenario: 发布候选验证

- **WHEN** 执行后端、前端、迁移、发布契约、Compose 和工作区门禁
- **THEN** 所有检查通过，且测试产物、凭据和业务数据不进入版本控制

## MODIFIED Requirements

### Requirement: 当前用户响应包含角色

注册响应与 `GET /api/auth/me` SHALL 在既有 `id`、`username`、`email` 之外返回
固定 `role`。前端 `AuthUser` 解析 SHALL 验证角色只能是 `user` 或 `admin`；
本轮不依据该字段在浏览器端实现安全决策。

#### Scenario: 角色契约同步

- **WHEN** 前端获取当前用户
- **THEN** 合法角色被解析并保留，缺失或未知角色按无效服务响应处理

### Requirement: 会话所有权与角色权限共同生效

现有会话路由 SHALL 继续要求登录，并在路由和服务层检查本人会话权限；所有数据
查询 SHALL 继续同时按 `session_id` 和当前用户 ID 过滤。

#### Scenario: 角色升级不扩大资源范围

- **WHEN** 用户从 `user` 升级为 `admin`
- **THEN** 该用户仍只能访问自己的会话，其他用户资源继续表现为 `404`

### Requirement: 管理接口传输与资源保护

FastAPI CORS 白名单 SHALL 允许管理员角色变更所需的 `PATCH` 方法。管理员路由
继续受现有默认限流、请求 ID 和结构化 HTTP 事件保护；健康检查行为保持不变。

#### Scenario: 白名单来源调用管理接口

- **WHEN** 白名单来源对管理员角色端点发起合法预检
- **THEN** 响应允许 `PATCH` 和既有认证/请求 ID 请求头，非白名单来源不被放行

## REMOVED Requirements

无。本轮不移除既有 API、认证方式、所有权规则或诊断能力。
