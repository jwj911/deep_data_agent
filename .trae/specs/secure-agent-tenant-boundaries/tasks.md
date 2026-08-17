# Tasks

- [x] Task 1: 固定身份与主数据契约：记录基线并把 DEC-001/DEC-002 转为可测试设计。
  - [x] SubTask 1.1: 记录分支、完整 HEAD、工作区、当前 189 项测试和目标 SHA 的四个
    Hosted Job；确认仅本规格文件为新增改动。
  - [x] SubTask 1.2: 固定 LangGraph threads 为 Chat UI 主数据、MySQL users/RBAC
    为身份主数据，记录不双写和不迁移既有会话的边界。
  - [x] SubTask 1.3: 盘点当前 LangGraph `0.7.28` Auth 的受保护资源、action、公开
    `/ok`/`/info` 健康路由和前端 SDK header 契约。
  - 基线证据：`main`、HEAD/origin `37381ecbb19adfb9be4405565b7b751dd0d28bc7`，
    工作区仅新增本规格；run `31960155841` 的 Backend、Frontend、Release Contracts、
    Container Smoke 均成功。当前 SDK Auth 支持 threads 的 create/read/search/
    update/delete/create_run 与 assistants 资源处理，`/ok`、`/info` 为公开 meta
    路由；前端 SDK 支持 `defaultHeaders`。

- [x] Task 2: 实现 LangGraph 第一方认证与默认拒绝线程所有权。
  - [x] SubTask 2.1: 提取可供 FastAPI 与 LangGraph 共用的 JWT Bearer 验证和数据库
    用户加载逻辑，保持 LangGraph 无效凭据稳定 `403`、角色读取数据库最新值。
  - [x] SubTask 2.2: 新增 LangGraph Auth 模块与 `langgraph.json` 配置，返回稳定
    identity/permissions，错误和日志不含 Token、用户名或邮箱。
  - [x] SubTask 2.3: 增加全局默认拒绝；允许 thread create/read/search/update/delete/
    create_run 时强制 owner metadata/filter，管理员不绕过所有权。
  - [x] SubTask 2.4: 只允许认证用户读取/搜索固定 Agent assistant；拒绝 assistant
    写操作、cron、store 和其他未声明资源。
  - [x] SubTask 2.5: 增加 Auth 单元测试，覆盖有效、缺失、格式、签名、过期、subject、
    删除用户、角色变化、owner 覆盖、跨用户和默认拒绝。

- [x] Task 3: 保护 FastAPI Agent 入口并按主体隔离缓存。
  - [x] SubTask 3.1: 增加 `agent.invoke_own` 权限，并在 `/api/query` 路由要求第一方
    用户；匿名或无效 Token 在任何缓存/模型/工具访问前返回 `401`。
  - [x] SubTask 3.2: AgentService 接收 actor 并执行服务层权限检查；无 actor、未知
    角色或旁路调用默认拒绝。
  - [x] SubTask 3.3: 将 Agent 缓存键升级为包含主体、模型、工具策略版本和查询摘要
    的租户键，不记录明文主体或查询。
  - [x] SubTask 3.4: 增加路由与服务测试，覆盖双层授权、相同查询跨用户不共享缓存、
    同用户缓存命中和拒绝路径无副作用。

- [x] Task 4: 收敛前端 Agent 连接与浏览器凭据边界。
  - [x] SubTask 4.1: Thread/Stream/Client 只读取编译期 Agent URL 和 assistant ID，
    移除 `apiUrl`/`assistantId` 查询状态、连接表单和运行时 Origin 覆盖。
  - [x] SubTask 4.2: LangGraph SDK、`/info` 检查和流式请求统一附加
    `sessionStorage` 第一方 JWT 的 Authorization header，不再发送 X-Api-Key。
  - [x] SubTask 4.3: 删除 LangGraph Key 的读取、写入与 UI；启动时只删除旧
    `lg:chat:apiKey`，不把其值用于请求。
  - [x] SubTask 4.4: 将 Studio 链接等剩余 Agent URL 使用点改为固定配置；保留
    `threadId` 导航参数且不把 Token 放入 URL。
  - [x] SubTask 4.5: 增加发布契约或无新框架的确定性测试，证明恶意 apiUrl/
    assistantId 参数不能改变客户端目标，旧 Key 不会进入 header。

- [x] Task 5: 建立跨租户回归与容器实证。
  - [x] SubTask 5.1: 扩展后端全量测试，覆盖 LangGraph Auth 与 FastAPI Agent
    身份边界，并保持既有认证/RBAC/限流/观测测试通过。
  - [x] SubTask 5.2: 扩展 Container Smoke：使用两个专用用户登录取得 JWT，只创建
    thread 而不运行模型，验证 LangGraph 匿名 `403`、FastAPI Agent 匿名 `401`、
    各自搜索隔离和跨用户读/改/删/续跑拒绝。
  - [x] SubTask 5.3: 验证调用方伪造 owner metadata、管理员角色、相同 thread ID、
    并发搜索或重试均不能跨租户，拒绝后资源不变。
  - [x] SubTask 5.4: 更新发布契约，强制 `langgraph.json` Auth、前端固定 Origin、
    禁止旧 API Key/可变 Agent URL，并为回归样例增加测试。

- [x] Task 6: 完成全量门禁、五服务验收和治理文档同步。
  - [x] SubTask 6.1: 运行 Python 3.12 全量 pytest、isort、发布契约、迁移、Compose
    解析和 `git diff --check`。
  - [x] SubTask 6.2: 使用 Node 22 与 pnpm 10.5.1 运行 typecheck、零警告 lint、
    format:check、build，并清理 `.next`、`out`、`*.tsbuildinfo`。
  - [x] SubTask 6.3: 使用显式临时假配置重建五服务并执行双用户 LangGraph 冒烟；
    不读取仓库 `.env`、不调用模型/搜索，成功失败均完整清理。
  - [x] SubTask 6.4: 更新 README、AGENTS、项目分析、Roadmap、CHANGELOG：关闭
    `AUD-001`/`AUD-003`，记录 DEC-001/002、BREAKING 匿名语义和仍开放风险。
  - [x] SubTask 6.5: 独立执行 `checklist.md` 的 25 项验收；任何失败先新增修复任务，
    修复并复验后才能进入提交。

  本地证据：Python 3.12.9 全量 **250 passed**，迁移定向 **7 passed**；isort、
  发布契约、Compose 解析与 `git diff --check` 通过。Node 22.22.2/pnpm 10.5.1
  的 typecheck、零警告 lint、format:check 通过，同一前端源码已有 build 通过
  证据；最终本地重试因 Google Fonts 网络不可达失败，Hosted Frontend Job 已
  完成生产构建并成功。
  五服务空库双用户、head 重启、legacy 升级通过，资源与临时配置已清理。

- [x] Task 7: 创建原子提交、推送 GitHub 并验证远端闭环。
  - [x] SubTask 7.1: 复核暂存范围、凭据和生成物，只包含本轮代码、测试、规格和
    必要治理文档。
  - [x] SubTask 7.2: 创建 `secure-agent-tenant-boundaries` 原子实现提交；远端前进
    时安全整合并重跑受影响门禁。
  - [x] SubTask 7.3: 推送 `main` 到 `origin/main`，确认本地与远端完整 SHA 一致、
    工作区干净。
  - [x] SubTask 7.4: 通过 GitHub API 确认目标 SHA 的 Backend、Frontend、
    Release Contracts、Container Smoke 全部成功；同步最终证据并推送验收记录。

  Hosted 证据：implementation SHA
  `9699f90f6fd2a90d63d82728208fb656cb4fe8e3` 的 Release Readiness run
  `31994602064` 为 `completed/success`；Backend、Frontend、Release Contracts、
  Container Smoke 四个 Job 均为 `success`。Container Smoke 的空库双用户、
  head 重启、legacy 升级和 cleanup 均为 `success`。

# Task Dependencies

- Task 2、Task 3、Task 4 依赖 Task 1；Task 2.1 完成后，后端 Auth、FastAPI Agent
  和前端连接可按文件边界并行。
- Task 5 依赖 Task 2、Task 3、Task 4。
- Task 6 依赖 Task 5。
- Task 7 依赖 Task 6 和全部 25 项清单通过。
