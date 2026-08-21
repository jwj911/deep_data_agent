# 验收清单

- [x] 基线记录 `main`、完整 HEAD/origin、干净工作区、295 项测试、8 项 migration 测试和最终 SHA 的 Hosted 四 Job。
- [x] Agent/model/search/Redis 恢复预算使用安全默认值、正数与关系校验，`.env.example`、Compose、代码和发布契约一致。
- [x] `/api/query` 拒绝空白或超过 8,000 字符的输入，且在缓存、租约、模型和工具前返回稳定 422。
- [x] ChatOpenAI 强制 45 秒 timeout、1 次 retry、4,096 最大输出 tokens，客户端 config/context 不能扩大。
- [x] FastAPI 与 LangGraph run 都强制 recursion 25、每 run 8 次模型调用和 12 次工具调用，管理员不绕过。
- [x] Agent 总 deadline 为 60 秒；timeout、任务取消和客户端断开传播到异步图，部分结果不写缓存。
- [x] FastAPI 最终响应超过 32,000 字符时稳定拒绝，不缓存、不记录正文或底层异常。
- [x] Redis 原子租约同时限制全局 4 和每用户 1 个 run，等待最多 1 秒，拒绝发生在模型/工具前。
- [x] 租约正常完成显式释放；timeout、取消、异常和 worker 退出由 finally 或 deadline + grace TTL 有界回收。
- [x] 同用户、不同用户、全局耗尽、管理员、伪造主体/budget 和并发重试测试证明租约隔离与不可扩大。
- [x] 搜索只暴露 2,000 字符 query、general/news、最多 5 条；raw content 与 images/videos/files topic 不可请求。
- [x] 搜索使用异步 15 秒 timeout 与 64 KiB 输出上限；timeout/超大/配置缺失稳定返回且不缓存正文。
- [x] 受管文档继续执行 20,000 字符输出上限，并计入共享 tool-call budget。
- [x] `ENABLE_CODE_EXECUTION` 从环境、Compose、提示和注册路径移除；任何残留变量都不能注册或调用 `execute_python_code`。
- [x] CacheService Redis 故障继续降级为 miss/false，使用 1..30 秒单飞指数退避并可无重启恢复。
- [x] RateLimitService 明确 protection 状态：auth/session/default 故障 fail-open，query 故障 fail-closed。
- [x] Agent 并发保护在 Redis 不可用时稳定 503 `agent_protection_unavailable`，不访问 Agent cache、模型或工具。
- [x] Redis 连续失败、并发 probe、恢复、再次故障和策略矩阵测试通过，事件不含 URL、身份、query、Token 或异常原文。
- [x] `/api/live` 与兼容 `/api/health` 只证明进程可响应，不触碰 MySQL、Redis、Agent、模型或搜索。
- [x] `/api/ready` 浅检查配置、MySQL、唯一 Alembic head、Redis、受管文件根；成功 200，任一失败 503，恢复后自动转绿。
- [x] readiness 响应/日志只含固定组件状态和请求 ID，不含连接串、路径、SQL、凭据、业务数据或异常原文。
- [x] FastAPI/ LangGraph Compose healthcheck 与发布脚本使用 readiness，不以无条件 `/api/health` 作为就绪证据。
- [x] Container Smoke 验证 Redis stop/start：live 200、ready 503、Agent fail-closed，恢复后无需重启 ready 200；不调用模型/搜索。
- [x] Python 3.12 全量 pytest、isort、发布契约、Alembic、Compose、`git diff --check` 和 Node 22/pnpm 10.5.1 四项前端门禁全部通过，文档与证据一致。
- [x] 25 项清单、tasks、README、AGENTS、项目分析、Roadmap、CHANGELOG 已同步；implementation 与最终文档提交均推送，最终 HEAD 四个 Hosted Job 成功且工作区干净。

第 25 项勾选是最终验收文档提交的后置验收登记，只在该提交已推送，且其 exact SHA
的 Backend、Frontend、Release Contracts、Container Smoke 全部成功、本地/origin/
GitHub SHA 一致、工作区干净时成立。创建本记录时最终 SHA 与 run ID 尚未知，不
记录推测值，也不能使用 implementation run `32431502248` 替代；若任一 Job 失败，
该勾选无效且不得报告闭环完成。
