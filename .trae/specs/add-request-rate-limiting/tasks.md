# Tasks

- [x] Task 1: 建立限流配置契约：新增按路由类别的配额、窗口和可信代理跳数环境变量，保持默认有界且可关闭。
  - [x] SubTask 1.1: 在 `config.py` 增加认证、查询、会话、默认四类的 `*_LIMIT` 与 `*_WINDOW_SECONDS`、`RATE_LIMIT_ENABLED`、`TRUSTED_PROXY_COUNT` 解析，复用现有正整数/布尔校验并对非法值抛稳定 `ConfigurationError`。
  - [x] SubTask 1.2: 在 `.env.example` 与 `docker-config/docker-compose.yml` 增加对应变量，默认值有界且不改变现有服务地址边界。

- [x] Task 2: 实现 Redis 固定窗口限流服务：提供计数、剩余额度与重置时间，Redis 故障时 fail-open。
  - [x] SubTask 2.1: 新增 `data_agent/services/rate_limit_service.py`，用 `INCR`+首次 `EXPIRE` 实现固定窗口，返回是否放行、剩余次数与 `Retry-After` 秒数。
  - [x] SubTask 2.2: Redis 不可用或 `RedisError` 时放行并发出 `rate_limit.degraded` 结构化事件；配额键使用不可逆摘要，不含原始身份值。

- [x] Task 3: 挂载限流中间件与 429 语义：在请求 ID 绑定之后按身份维度与路由类别限流。
  - [x] SubTask 3.1: 新增 `data_agent/observability/rate_limit_middleware.py`，解析身份（JWT `sub` 无副作用解码 / 可信代理边界内的来源）、路由类别与配额键，放行时透传，超限返回 `429` `{code: "rate_limited", message, request_id}` 并附 `Retry-After`。
  - [x] SubTask 3.2: 在 `agent_server.py` 注册中间件（在 `ObservabilityMiddleware` 之后添加，使其在请求处理中位于其内层），豁免 `/api/health`，发出放行/拒绝的脱敏 `rate_limit.decision` 事件。

- [x] Task 4: 增加确定性测试：覆盖配额、隔离、fail-open、代理边界、豁免与脱敏。
  - [x] SubTask 4.1: 用假计数后端与离线 Redis 替身测试放行、超限 429、`Retry-After`、窗口重置、用户与来源计数隔离。
  - [x] SubTask 4.2: 测试 Redis 故障 fail-open、`TRUSTED_PROXY_COUNT=0` 忽略伪造 `X-Forwarded-For`、`/api/health` 不受限、事件不含原始 Token/来源/业务数据。

- [x] Task 5: 对齐发布契约与文档：扩展契约检查，同步运行文档、Roadmap 与变更记录。
  - [x] SubTask 5.1: 在 `scripts/check_release_contracts.py` 增加 `.env.example` 限流占位/默认校验，并补充对应契约测试。
  - [x] SubTask 5.2: 更新 `README.md`、`AGENTS.md`、`.trae/documents/project_analysis.md`、`.trae/documents/roadmap.md`、`CHANGELOG.md`，将限流从后续候选转为当前迭代并记录行为、验证与风险。

- [x] Task 6: 发布验证：执行后端、前端与契约门禁，形成可追溯发布证据。
  - [x] SubTask 6.1: 运行 `python -m pytest -q`、`python -m isort --check-only data_agent tests scripts`、`python scripts/check_release_contracts.py`、Compose 解析与 `git diff --check`。
  - [x] SubTask 6.2: 运行前端 `pnpm typecheck`、`pnpm lint`、`pnpm format:check`、`pnpm build`（限流仅后端，前端确认无回归），清理构建产物。

# Task Dependencies
- Task 2 depends on Task 1.
- Task 3 depends on Task 1 and Task 2.
- Task 4 depends on Task 2 and Task 3.
- Task 5 depends on Task 3（最终配置与命令）。
- Task 6 depends on Task 4 and Task 5.
