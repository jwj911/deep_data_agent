# Tasks

- [x] Task 1: 恢复前端可信质量门禁：移除构建绕过，修复全部格式与 Lint 警告，并让警告导致门禁失败。
  - [x] SubTask 1.1: 保留 `isProd` 动态配置，删除 `ignoreBuildErrors` 与 `ignoreDuringBuilds`，修复 `next.config.mjs` 格式。
  - [x] SubTask 1.2: 修复当前 React Hook、未使用变量和 Fast Refresh 等 Lint 警告，不通过禁用规则掩盖真实问题。
  - [x] SubTask 1.3: 固化受支持的 Node.js/pnpm 版本契约，并让 Lint 脚本在出现警告时返回非零状态。
  - [x] SubTask 1.4: 执行 `typecheck`、Lint、格式检查和生产构建，清理生成物。

- [x] Task 2: 收敛后端兼容性技术债：消除项目代码直接产生的 ORM 与 UTC 时间弃用警告，并保持接口和数据库兼容。
  - [x] SubTask 2.1: 使用 SQLAlchemy 2.x 推荐的声明式基类导入，确认用户与会话模型共享同一元数据。
  - [x] SubTask 2.2: 将模型默认时间和会话更新时间改为明确的 UTC 语义，不改变现有 API 字段格式和所有权逻辑。
  - [x] SubTask 2.3: 增加针对时间字段与模型元数据的回归测试，并执行全量 `pytest`、`isort --check-only`。

- [x] Task 3: 建立自动化 CI 与配置漂移防护：为主分支和合并请求增加不可静默绕过的发布检查。
  - [x] SubTask 3.1: 增加后端 CI 任务，使用 Python 3.12 执行依赖安装、测试和导入排序检查。
  - [x] SubTask 3.2: 增加前端 CI 任务，使用 Node.js LTS 与锁定 pnpm 执行类型、Lint、格式和构建门禁。
  - [x] SubTask 3.3: 增加仓库契约任务，执行 `git diff --check`、Compose 配置解析、质量绕过检查、过时登录变量检查和脱敏凭据扫描。
  - [x] SubTask 3.4: 配置并发取消与依赖缓存，确保失败日志可定位且不上传包含凭据的构建产物。

- [x] Task 4: 对齐发布文档与路线图：清理过时配置，更新项目现状并形成后续迭代顺序。
  - [x] SubTask 4.1: 从 `.env.example`、Compose、README 和源码中移除 `NEXT_PUBLIC_LOGIN_API_URL` 残留，并复核第一方认证配置。
  - [x] SubTask 4.2: 更新项目分析，反映已完成的运行闭环、认证隔离、缓存、容器化和当前技术债。
  - [x] SubTask 4.3: 新增 Roadmap，区分已完成、当前发布治理和后续候选迭代，并标注依赖与进入条件。
  - [x] SubTask 4.4: 更新变更记录与验证命令，记录本轮质量门禁、已知风险和 Docker 环境前置条件。

- [x] Task 5: 完成发布就绪验收：执行本地与 CI 门禁、容器重建、五服务健康检查和双用户冒烟。
  - [x] SubTask 5.1: 验证 CI 工作流语法与本地等价命令，确认失败条件不会被忽略。
  - [x] SubTask 5.2: 在 Docker Engine 可用时重建当前源码镜像并启动五服务，必要时仅通过环境变量处理宿主端口冲突。
  - [x] SubTask 5.3: 复验注册、登录、`/me`、无 Token 401、跨用户会话读写删 404、数据不变和 CORS 白名单。
  - [x] SubTask 5.4: 清理临时用户、会话、消息和构建产物，执行凭据扫描、`git diff --check` 与工作区卫生检查。
  - [x] SubTask 5.5: 更新规格任务与验收清单，形成可追溯的发布证据。

- [x] Task 6: 完成远程发布验证：提交并推送本轮改动，确认 GitHub Hosted CI 在远端实际通过。
  - [x] SubTask 6.1: 提交前复核暂存范围、凭据与生成物，确保只包含本轮预期源码、测试、CI、规格和文档。
  - [x] SubTask 6.2: 创建原子化提交；若远端有新提交，采用保留双方成果的方式整合并重新执行关键门禁。
  - [x] SubTask 6.3: 推送 `main` 到 `origin/main`，确认本地与远端提交一致且工作区干净。
  - [x] SubTask 6.4: 通过 GitHub Actions API 确认 `release-readiness` workflow 的 Backend、Frontend、Release Contracts 三个 job 均成功。

# Task Dependencies

- Task 1 and Task 2 may run in parallel.
- Task 3 depends on the finalized commands and contracts from Task 1 and Task 2.
- Task 4 may run in parallel with Task 1 and Task 2, but must reflect their final configuration.
- Task 5 depends on Task 1, Task 2, Task 3, and Task 4.
- Task 6 depends on Task 5 and requires remote repository access.
