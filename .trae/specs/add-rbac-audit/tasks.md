# Tasks

- [x] Task 1: 建立角色模型与版本化迁移：为用户增加固定、默认最小权限的角色字段，并保持既有数据可重复升级。
  - [x] SubTask 1.1: 在用户模型中定义 `user`、`admin` 固定角色及非空 `role` 字段，应用默认值和数据库默认值均为 `user`，注册接口不接受角色输入。
  - [x] SubTask 1.2: 新增线性 Alembic revision，为 `users.role` 增加固定值约束，安全回填既有用户为 `user`，支持 SQLite batch 与 MySQL upgrade/downgrade，且不重建业务数据。
  - [x] SubTask 1.3: 扩展迁移测试，验证全新库、包含既有用户/会话/消息的升级、默认值、约束、单 head、降级路径及 ORM metadata 无漂移。

- [x] Task 2: 实现集中式默认拒绝授权与脱敏审计：定义角色权限矩阵，并复用结构化事件管线记录安全决策。
  - [x] SubTask 2.1: 新增授权服务，集中定义本人会话读/写/删、管理员用户列表和角色变更权限；未知角色或权限默认拒绝，并提供路由依赖与可独立调用的服务层检查。
  - [x] SubTask 2.2: 新增审计辅助能力，以 JWT 服务端密钥对内部用户 ID 生成稳定 HMAC 引用；扩展事件字段白名单，只接受固定操作、权限、角色、决策和身份引用。
  - [x] SubTask 2.3: 对授权拒绝和 `ENABLE_CODE_EXECUTION=true` 下的高风险工具注册发出固定审计事件，确保不记录原始身份、配置值、工具输入或业务数据。

- [x] Task 3: 提供受限管理员 API 与人工引导：让已授权管理员管理他人角色，同时提供安全的首位管理员建立路径。
  - [x] SubTask 3.1: 新增管理员服务，实现按 ID 稳定排序的有界用户列表和事务化、幂等的他人角色变更；服务方法在任何查询或写入前再次授权。
  - [x] SubTask 3.2: 新增 `GET /api/admin/users` 与 `PATCH /api/admin/users/{user_id}/role`，实现稳定的 401/403/404/409/422 语义，禁止管理员修改自己的角色，并在应用中注册路由。
  - [x] SubTask 3.3: 新增 `scripts/bootstrap_admin.py --user-id <id>`，只允许人工按正整数 ID 把既有用户提升为管理员，对重复执行幂等，对失败返回非零且不输出敏感信息。
  - [x] SubTask 3.4: 为管理员列表、角色变更和管理员引导写入脱敏审计事件；成功角色变更包含请求 ID、HMAC actor/target 引用和前后角色。

- [x] Task 4: 将 RBAC 接入既有认证、会话与前端契约：保持所有权不变并同步角色响应。
  - [x] SubTask 4.1: 让注册响应和 `/api/auth/me` 返回固定角色；更新前端 `AuthUser` 与解析校验，但不新增浏览器端授权判断或管理员界面。
  - [x] SubTask 4.2: 在会话路由和服务层接入本人会话权限检查，继续按当前用户 ID 与会话 ID 联合过滤；验证管理员也不能访问他人会话。
  - [x] SubTask 4.3: 在 CORS 中允许 `PATCH`，确认管理员路由继续使用现有默认限流、请求 ID 和 HTTP 结构化事件，且健康检查不受影响。

- [x] Task 5: 补全确定性安全测试与发布契约：覆盖纵向/横向越权、引导和审计回归。
  - [x] SubTask 5.1: 新增角色矩阵及双层授权单元测试，覆盖 `user`、`admin`、未知角色、服务直调拒绝，以及拒绝发生在目标查询之前。
  - [x] SubTask 5.2: 新增管理员 API 集成测试，覆盖未登录 401、普通用户 403、分页边界、角色变更、重复设置、自我变更 409、目标不存在 404，以及旧 JWT 在后续请求中使用数据库最新角色。
  - [x] SubTask 5.3: 扩展双用户会话测试，验证角色升级前后均不能横向读取、写入或删除他人会话，拒绝后数据不变。
  - [x] SubTask 5.4: 新增管理员引导和审计测试，验证人工提升成功/幂等/错误退出，以及日志不存在原始 ID、用户名、邮箱、Token、密码、IP、请求体或连接串。
  - [x] SubTask 5.5: 扩展发布契约，拒绝默认管理员、未受约束角色、敏感审计字段和迁移多 head；同步测试契约的通过与失败样例。

- [x] Task 6: 对齐文档并执行发布验证：记录角色矩阵、管理员引导、安全边界和完整证据。
  - [x] SubTask 6.1: 更新 `README.md`、`AGENTS.md`、`.trae/documents/project_analysis.md`、`.trae/documents/roadmap.md` 和 `CHANGELOG.md`，把 RBAC 与审计标为当前/已完成迭代，并明确无管理员 UI、无跨用户会话权限、无长期审计存储。
  - [x] SubTask 6.2: 运行 `python -m pytest -q`、`python -m isort --check-only data_agent tests scripts`、`python scripts/check_release_contracts.py`、Alembic 单 head/升级检查、Compose 解析和 `git diff --check`。
  - [x] SubTask 6.3: 运行前端 `pnpm typecheck`、`pnpm lint`、`pnpm format:check`、`pnpm build`；检查并清理任务产生的缓存/构建产物，确认工作区不含凭据、业务数据或无关改动。

# Task Dependencies

- Task 2 依赖 Task 1 的角色定义。
- Task 3 依赖 Task 1 和 Task 2。
- Task 4 依赖 Task 1 和 Task 2；其前端契约与会话接入可并行。
- Task 5 依赖 Task 1、Task 2、Task 3 和 Task 4。
- Task 6 依赖 Task 5。
