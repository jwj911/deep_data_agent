# Tasks

- [x] Task 1: 建立认证配置与身份依赖：移除硬编码 JWT 密钥，增加经过校验的认证/CORS 配置、Token 签发解析和当前用户接口。
  - [x] SubTask 1.1: 增加 `JWT_SECRET_KEY`、Token 有效期、`CORS_ALLOWED_ORIGINS` 与 `NEXT_PUBLIC_REST_API_URL` 配置契约。
  - [x] SubTask 1.2: 使用用户 ID 作为 JWT subject，实现统一的 Token 签发、解析和 `get_current_user`。
  - [x] SubTask 1.3: 增加 `/api/auth/me`，统一缺配置、无效 Token、过期 Token和用户不存在的错误语义。
  - [x] SubTask 1.4: 将 CORS 通配符替换为来源白名单，并限制允许的方法与请求头。

- [x] Task 2: 强化注册与登录接口：增加输入校验、重复注册竞争处理和稳定响应契约。
  - [x] SubTask 2.1: 校验用户名、邮箱和密码，并确保响应不包含密码哈希。
  - [x] SubTask 2.2: 将重复用户名/邮箱及数据库唯一约束竞争映射为 HTTP 409。
  - [x] SubTask 2.3: 登录成功返回 Bearer Token 与过期秒数，失败使用统一 HTTP 401。

- [x] Task 3: 实现会话与消息所有权隔离：移除固定用户 ID，在服务层按当前用户过滤全部资源操作。
  - [x] SubTask 3.1: 为全部会话路由注入当前用户，创建和列表使用真实用户 ID。
  - [x] SubTask 3.2: 修改单会话、消息和删除服务方法，使其同时接收 `session_id` 与 `user_id`。
  - [x] SubTask 3.3: 对他人资源统一返回 HTTP 404，并保证失败写入不修改数据库。
  - [x] SubTask 3.4: 增加标题、消息角色和正文的长度及空白校验。

- [x] Task 4: 对齐前端第一方认证：使用 FastAPI 注册/登录契约替换授权码回调，并限制认证失败拦截范围。
  - [x] SubTask 4.1: 增加 REST API 配置与认证客户端，移除 `NEXT_PUBLIC_LOGIN_API_URL`。
  - [x] SubTask 4.2: 实现登录/注册表单、错误提示、`/api/auth/me` 验证和登出能力。
  - [x] SubTask 4.3: 将 Token 存储迁移到 `sessionStorage`，并仅为 FastAPI 请求附加 Bearer Token。
  - [x] SubTask 4.4: 仅在第一方 FastAPI 返回 401 时清理登录状态和跳转，不影响 LangGraph 请求。

- [x] Task 5: 建立认证与隔离验证：增加后端集成测试、前端质量检查和双用户容器冒烟，并更新运行文档。
  - [x] SubTask 5.1: 使用独立测试数据库覆盖注册、登录、`/me`、无效/过期 Token、缺配置和重复注册。
  - [x] SubTask 5.2: 覆盖用户 A 无法读取、写入或删除用户 B 会话，以及无效输入不产生部分写入。
  - [x] SubTask 5.3: 验证 CORS 白名单与非白名单来源行为。
  - [x] SubTask 5.4: 执行后端测试、`isort`、前端类型检查、Lint、格式检查和生产构建。
  - [x] SubTask 5.5: 更新 `.env.example`、Docker Compose 与 README，并验证镜像构建及五服务健康。
  - [x] SubTask 5.6: 在容器环境注册两个临时用户，验证登录、`/me`、会话隔离和登出流程。
  - [x] SubTask 5.7: 执行凭据扫描、`git diff --check` 和生成物清理，确认未覆盖上一轮用户改动。

# Task Dependencies

- Task 2 depends on Task 1.
- Task 3 depends on Task 1 and may run in parallel with Task 2.
- Task 4 depends on Task 1 and the finalized authentication response contract from Task 2.
- Task 5 depends on Task 2, Task 3, and Task 4.

# Verification Fixups

- [x] Task 6: 修复 README 认证文档缺口（checklist L29）：重写「可选认证」章节，删除已移除的 `NEXT_PUBLIC_LOGIN_API_URL` 授权码登录描述，改为记录第一方 FastAPI 注册/登录/`/me` 流程；更正 Token 存储为 `sessionStorage`；补充 CORS 白名单（`CORS_ALLOWED_ORIGINS`）与 REST API 认证配置（`NEXT_PUBLIC_REST_API_URL`、JWT 密钥长度≥32、`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`）及验证命令说明。
