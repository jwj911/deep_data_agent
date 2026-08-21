# Tasks

- [x] Task 1: 锁定基线、预算常量与 Redis/健康策略。
  - [x] SubTask 1.1: 记录 `main`、完整 HEAD/origin、干净工作区、295 项测试、8 项
    migration 测试和最终 SHA 的 Hosted 四 Job。
  - [x] SubTask 1.2: 验证 FastAPI 同步 `.invoke()`、LangGraph run、模型、默认工具、
    Redis 永久降级和 Compose 健康检查的真实调用链。
  - [x] SubTask 1.3: 固定 60 秒 deadline、25 recursion、8 model calls、12 tool
    calls、全局 4/用户 1 并发、模型 45 秒/1 retry/4,096 tokens 等默认值。
  - [x] SubTask 1.4: 固定 Redis 矩阵：cache 与低成本限流 fail-open；query 限流、
    Agent 租约和 readiness fail-closed；重连退避 1..30 秒。
  - [x] SubTask 1.5: 固定健康契约和 BREAKING 边界：`/api/live`、`/api/ready`、
    `/api/health` 兼容；运行时 Python 工具与 search raw/media topic 移除。

- [x] Task 2: 实现模型、run、工具和输入/输出预算。
  - [x] SubTask 2.1: 增加 Agent/model/search/Redis 恢复配置、正整数/关系校验、
    `.env.example`、Compose 默认值和发布契约。
  - [x] SubTask 2.2: 为 `create_deep_agent` 接入已安装的
    `ModelCallLimitMiddleware`、`ToolCallLimitMiddleware`，并强制 recursion limit。
  - [x] SubTask 2.3: 配置 ChatOpenAI timeout、retry 与最大输出 tokens；fake 模型
    测试证明客户端配置不能扩大上限。
  - [x] SubTask 2.4: 将搜索工具改为异步有界调用，只允许 general/news、5 条结果、
    2,000 字符 query、15 秒 timeout 和 64 KiB 输出，不暴露 raw content。
  - [x] SubTask 2.5: 保持受管文档 20,000 字符上限并纳入 tool-call 总预算；超限
    不缓存、不输出正文到日志。
  - [x] SubTask 2.6: 删除 `ENABLE_CODE_EXECUTION` 环境/Compose/提示/注册路径，
    发布契约证明残留变量不能启用 `execute_python_code`。

- [x] Task 3: 实现跨入口并发租约和异步 FastAPI Agent。
  - [x] SubTask 3.1: 新增 Redis 原子 global/user 双层租约，使用认证主体摘要、
    1 秒等待、deadline + grace TTL 与幂等释放。
  - [x] SubTask 3.2: 把租约 middleware 装配到共享 Agent 图，使 FastAPI 与
    LangGraph run 都在模型/工具前执行同一预算，管理员不绕过。
  - [x] SubTask 3.3: 将 AgentService 和 `/api/query` 改为 async `ainvoke`，使用
    60 秒总 deadline、服务端 recursion 和 8,000 字符查询校验。
  - [x] SubTask 3.4: 增加 32,000 字符最终响应上限；timeout、取消、并发拒绝、
    Redis 保护不可用和超大响应使用稳定错误码且不写缓存。
  - [x] SubTask 3.5: 验证同用户并发拒绝、不同用户隔离、全局上限、取消/异常释放、
    TTL 回收和客户端伪造 budget/user 配置无效。

- [x] Task 4: 让 Redis 降级自动恢复并执行固定策略矩阵。
  - [x] SubTask 4.1: 抽取可复用的单飞重连/退避状态，保留 Redis URL/client factory，
    使用 1..30 秒指数退避与有界抖动。
  - [x] SubTask 4.2: CacheService 在失败时返回 miss/false，并在退避后自动恢复；
    并发调用只产生一个 probe。
  - [x] SubTask 4.3: RateLimitService 决策增加保护状态/原因；query scope 失去 Redis
    时 fail-closed，auth/session/default 维持 fail-open。
  - [x] SubTask 4.4: Agent 租约失去 Redis 时返回
    `agent_protection_unavailable`，在任何缓存、模型或工具副作用前终止。
  - [x] SubTask 4.5: 增加断开、连续失败、退避、单飞、恢复、再次故障和策略矩阵
    确定性测试；事件不含 Redis URL、身份、query 或异常原文。

- [x] Task 5: 拆分 liveness/readiness 并更新容器健康契约。
  - [x] SubTask 5.1: 新增 `/api/live`，并让 `/api/health` 成为同语义兼容别名；
    两者不查依赖、不调用 Agent。
  - [x] SubTask 5.2: 新增 `/api/ready`，浅检查模型必要配置、MySQL `SELECT 1`、
    Alembic 唯一 head、Redis 与受管文件根；失败返回 503 固定组件码。
  - [x] SubTask 5.3: readiness 恢复后自动回 200，不输出 URL、凭据、路径、SQL、
    revision 之外的 schema 或异常原文。
  - [x] SubTask 5.4: FastAPI Compose healthcheck 改用 `/api/ready`；LangGraph
    healthcheck 同时验证 `/info` 与本地 readiness helper，不调用模型/搜索。
  - [x] SubTask 5.5: 更新 Container Smoke 的 HTTP 契约和 Redis stop/start canary：
    live 保持 200、ready 变 503、Agent fail-closed、恢复后无需重启变 200。

- [x] Task 5A: 修复预算与租约集成审计问题。
  - [x] SubTask 5A.A: 让 cache get/set 不能穿透 60 秒总 deadline；timeout 或取消后
    不写缓存，并增加阻塞 cache 回归测试。
  - [x] SubTask 5A.B: 将 `ModelCallLimitExceededError` 和
    `ToolCallLimitExceededError` 映射为稳定 `agent_model_budget_exceeded` 和
    `agent_tool_budget_exceeded`，且不写缓存。
  - [x] SubTask 5A.C: 修正 recursion 防伪测试，以包装器或实际递归行为验证服务端
    上限，而非检查节点内部 config。
  - [x] SubTask 5A.D: 将租约用户 key 从低熵裸 SHA-256 改为服务端密钥 HMAC，并
    保持 FastAPI 与 LangGraph 入口一致。
  - [x] SubTask 5A.E: 将搜索密钥校验移到缓存前；缺失 key 时稳定返回
    `configuration_error`。

- [x] Task 6: 完成全量验证、25 项验收和治理文档同步。
  - [x] SubTask 6.1: 扩展 Agent/工具测试：慢模型、run timeout、取消、递归、
    model/tool limit、输入/输出、缓存无副作用和稳定错误映射。
  - [x] SubTask 6.2: 扩展并发/Redis/health 测试和 Container Smoke，全部使用 fake
    外部客户端、脱敏主体与隔离容器。
  - [x] SubTask 6.3: 运行 Python 3.12 全量 pytest、isort、发布契约、Alembic、
    Compose 与 `git diff --check`。
  - [x] SubTask 6.4: 使用 Node 22/pnpm 10.5.1 运行 typecheck、零警告 lint、
    format:check、build，并清理生成物。
  - [x] SubTask 6.5: 更新 README、AGENTS、项目分析、Roadmap、CHANGELOG：关闭
    `AUD-004`/`AUD-008`/`AUD-009`，记录 RR-004/RR-006、BREAKING 与剩余
    1 P1 / 6 P2 / 1 P3。
  - [x] SubTask 6.6: 独立执行 `checklist.md` 25 项；失败项先新增修复任务并复验。

- [x] Task 7: 创建原子提交、推送并验证两轮 Hosted 闭环。
  - [x] SubTask 7.1: 复核暂存范围、凭据、诊断、容器和生成物，只包含本轮必要文件。
  - [x] SubTask 7.2: 创建 `bound-agent-resource-use` implementation 提交；远端前进
    时安全整合并重跑受影响门禁。
  - [x] SubTask 7.3: 推送 `main`，确认本地/origin/GitHub 完整 SHA 一致且工作区
    干净。
  - [x] SubTask 7.4: 通过 GitHub API 确认 implementation SHA 的 Backend、Frontend、
    Release Contracts、Container Smoke 全部成功。
  - [x] SubTask 7.5: 同步 implementation run 证据及最终验收条件、tasks/checklist/
    Roadmap/CHANGELOG，提交并推送验收记录，再等待最终 HEAD 四个 Hosted Job 成功。
  - implementation 证据：SHA `1090c3ea0954e84cc2cb6b945ef8c3913393cec8`，
    Hosted run `32431502248` 为 `completed/success`；Backend `96623829169`、
    Frontend `96623829344`、Release Contracts `96623829444`、Container Smoke
    `96623829378` 均为 `success`。
  - 后置条件：Task 7 与 SubTask 7.5 的勾选只有在最终验收文档提交已推送，且该
    exact SHA 的上述四个 Hosted Job 全部成功、本地/origin/GitHub SHA 一致、工作区
    干净时才成立。创建本记录时最终 SHA 与 run ID 尚未知，不记录推测值；若后续
    任一 Job 失败，则本勾选无效且不得报告闭环完成。

# Task Dependencies

- Task 2、Task 4、Task 5.1 可在 Task 1 后按文件边界并行。
- Task 3 依赖 Task 2 的 budget 配置和 Task 4 的 Redis 保护状态。
- Task 5.2..5.5 依赖 Task 4 的恢复状态和 Task 3 的 Agent fail-closed 语义。
- Task 5A 依赖 Task 2、Task 3、Task 4。
- Task 6 依赖 Task 5 和 Task 5A。
- Task 7 依赖 Task 6 与清单前 24 项；第 25 项及 Task 7/7.5 勾选均以上述最终
  exact-SHA Hosted 后置条件实际满足为准。
