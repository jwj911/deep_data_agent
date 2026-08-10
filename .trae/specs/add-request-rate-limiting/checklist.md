# 验收清单

- [x] 限流配置支持认证、查询、会话和默认四类的独立配额与窗口，非法值抛出稳定 `ConfigurationError`。
- [x] `RATE_LIMIT_ENABLED` 可整体关闭限流，关闭时不产生 429 且不调用 Redis。
- [x] `.env.example` 与 Compose 含有界默认的限流变量，未改变既有服务地址与端口边界。
- [x] 限流服务使用 Redis 固定窗口（`INCR`+首次 `EXPIRE`），返回放行状态、剩余次数与 `Retry-After`。
- [x] Redis 不可用或出错时限流 fail-open 放行，并发出 `rate_limit.degraded` 事件，不返回 429。
- [x] 中间件在请求 ID 绑定之后执行，按 JWT `sub` 或来源解析配额键；JWT 解码无数据库副作用。
- [x] `TRUSTED_PROXY_COUNT` 默认不信任 `X-Forwarded-For`，伪造转发头不改变匿名计数键。
- [x] 超限返回 `429`，错误体为 `{code: "rate_limited", message, request_id}` 且含 `Retry-After`。
- [x] 认证端点、`/api/query`、会话端点计数相互隔离；不同用户、不同来源计数相互隔离。
- [x] `/api/health` 永不被限流，且不计入任何配额。
- [x] 限流事件仅含维度类别、路由模板、配额键摘要、窗口与计数，不含原始 Token、明文来源、提示词或业务数据。
- [x] 既有 401/404/503 语义、CORS 与请求 ID 传播不受限流引入影响。
- [x] 新增确定性测试覆盖配额、超限、窗口重置、隔离、fail-open、代理边界、健康豁免与脱敏，全部通过。
- [x] 发布契约检查覆盖限流环境变量，`check_release_contracts.py` 通过。
- [x] 后端 `pytest`、`isort --check-only`、Compose 解析、`git diff --check` 通过。
- [x] 前端 `pnpm typecheck`、`pnpm lint`、`pnpm format:check`、`pnpm build` 通过，无构建产物残留。
- [x] README、AGENTS、项目分析、Roadmap、CHANGELOG 与限流实现一致，Roadmap 将限流标为当前迭代。
