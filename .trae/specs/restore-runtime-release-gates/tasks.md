# Tasks

- [x] Task 1: 固定迭代基线与冒烟契约：确认目标 SHA、Docker 可用性、迁移 head、
  五服务健康定义和专用假配置边界。
  - [x] SubTask 1.1: 记录开始时的分支、完整 HEAD、工作区状态和现有
    Backend/Frontend/Release Contracts Hosted CI 结果，不覆盖并行用户改动。
  - [x] SubTask 1.2: 解析唯一 migration head，定义空库、已在 head、已知旧基线三类
    专用 MySQL fixture 及必须保持的数据不变量。
  - [x] SubTask 1.3: 定义 Container Smoke Job 的无真实外部调用假配置、健康等待
    超时、失败诊断白名单和无条件清理命令。
  - 基线证据（2026-08-16）：
    - Git/CI：开始分支为 `main`，完整 HEAD 与刷新后的 `origin/main` 均为
      `d9c56099e849e35bab121adc85375c100e0ae090`；初始工作区仅本规格 3 个文件未跟踪。
      该 SHA 的 Hosted run `31936858331` 成功，Backend、Frontend、Release Contracts
      均为 success，尚无 Container Smoke Job。
    - 主机前置：Docker CLI `29.4.1` 可执行，但 Docker Desktop Linux Engine 管道
      不存在，故本地容器运行证据阻塞；C 盘剩余 `49.56 GiB`。`3306` 由 `mysqld`
      （PID `8388`）监听，`6379/8000/2024/3000` 空闲；本地冒烟须将 MySQL 宿主端口
      改为 `3307`，容器内仍使用 `mysql:3306`。
    - 迁移/fixture：静态解析 2 个 revision，唯一 head 为 `8f3c1b7a2d4e`。空库须创建
      业务表并仅记录该 head；head 库重启须保持 revision 及脱敏用户、会话、消息
      canary 的主外键、字段和值不变；已知旧基线为无 `alembic_version`、无 `role`
      列且结构匹配 `4e43e097f22b` 的三表库，升级须保留上述 canary 并将角色回填为
      `user`。
    - 冒烟契约：干净 CI checkout 临时生成仓库根 `.env`，仅放非生产模型/搜索假值、
      不可外连的回环模型地址、运行时生成的 32 字符以上 JWT 假值、同步的 MySQL
      假密码/库名/连接 URL、容器 Redis URL、`RATE_LIMIT_ENABLED=false`、
      `ENABLE_CODE_EXECUTION=false` 及浏览器可达的 localhost 前端 URL；不发送业务
      查询。五服务按 Compose 现有 `mysqladmin ping`、`redis-cli ping`、
      `/api/health`、`/info`、`/data_copilot/` 判定健康，`--wait-timeout 300`，
      外层命令硬上限 `360s`。
    - 失败诊断只允许有界的 `docker compose ps --all` 和五服务各末尾 100 行经脱敏
      日志，单命令上限 `30s`；禁止输出 `compose config`、`inspect`、环境变量或业务
      数据。`always()` 清理使用
      `timeout 60s docker compose --env-file "$CI_ENV_FILE" -f docker-config/docker-compose.yml -p "$COMPOSE_PROJECT_NAME" down --volumes --remove-orphans --timeout 10 || true`，
      随后无条件执行 `rm -f "$CI_ENV_FILE"`。

- [x] Task 2: 修复后端镜像运行资产：让容器内 FastAPI 能够发现并执行完整 Alembic
  迁移。
  - [x] SubTask 2.1: 定向修改 `data_agent/Dockerfile`，在固定 `/app` 项目根中复制
    `alembic.ini`、`migrations/` 和现有应用运行资产，不扩大到 `.env`、测试、
    虚拟环境或 Git 元数据。
  - [x] SubTask 2.2: 扩展发布契约，校验 Dockerfile 的迁移配置、迁移目录和版本文件
    复制契约；删除任一资产时检查必须失败。
  - [x] SubTask 2.3: 增加确定性测试，验证镜像资产契约的成功与失败分支，错误输出
    只含规则、路径和行号。
  - [x] SubTask 2.4: 从干净上下文构建后端镜像，分别验证空库启动、head 幂等重启和
    已知旧基线升级，确认 revision 精确到唯一 head 且测试数据保持不变。

- [x] Task 3: 扩展全仓库凭据内容扫描：覆盖全部 Git 跟踪文本和非忽略的待提交文本，
  同时保持二进制与输出脱敏边界。
  - [x] SubTask 3.1: 用 Git 文件集合替换有限的 `SCAN_EXACT_FILES`/
    `SCAN_PREFIXES` 内容发现逻辑；保留必须文件清单只服务结构契约。
  - [x] SubTask 3.2: 对候选普通文件统一执行 NUL/UTF-8 文本判定，扫描可识别文本，
    稳定跳过二进制和无法解码内容，不读取被忽略的本地 `.env`。
  - [x] SubTask 3.3: 扩展契约测试，覆盖 `scripts/`、`migrations/`、`.github/`、
    `tests/`、`.trae/`、新顶层目录及未跟踪文本中的无效 canary。
  - [x] SubTask 3.4: 增加二进制、合法占位值、拆分测试样例和错误输出脱敏测试，
    确认扫描失败不回显完整匹配值。

- [x] Task 4: 增加 Hosted Container Smoke Job：从当前 SHA 构建并验证实际五服务
  发布拓扑。
  - [x] SubTask 4.1: 在 `release-readiness.yml` 新增独立 Container Smoke Job，
    使用干净 checkout 和专用假配置构建当前前后端镜像，不调用真实模型或搜索服务。
  - [x] SubTask 4.2: 启动 MySQL、Redis、FastAPI、LangGraph、Frontend，使用有界
    轮询等待 Compose 健康并验证前端 `/data_copilot/` 与 FastAPI `/api/health`。
  - [x] SubTask 4.3: 在运行中的拓扑内读取 MySQL `alembic_version`，与仓库静态解析
    的唯一 head 比较，确认容器内迁移已真实执行。
  - [x] SubTask 4.4: 为失败路径输出有界 `docker compose ps` 和脱敏日志摘要；
    使用 `always()` 或等价机制无条件删除容器、网络、匿名卷和临时配置。
  - [x] SubTask 4.5: 验证工作流在 `main` 推送与合并请求触发，Job 结果绑定目标
    SHA，任一构建、迁移、健康或清理前检查失败均返回非零。

- [ ] Task 5: 完成本地回归与治理文档同步：证明本轮只关闭约定的运行时发布门禁，
  不提前宣称其他审计问题已解决。
  - [x] SubTask 5.1: 运行 Python 3.12 全量 pytest、isort、发布契约、Alembic 单
    head/升级校验、Compose 解析和 `git diff --check`。
  - [x] SubTask 5.2: 运行前端 typecheck、零警告 lint、format:check 和 build，并
    清理 `.next/`、`out/`、`*.tsbuildinfo` 等任务生成物。
  - Node 22 证据（2026-08-16）：临时 PATH 使用指定 `node.exe`，`node v22.22.2`、`pnpm 10.5.1`；`typecheck`、零警告 `lint`、`format:check`、`build` 均成功，生成物已清理。
  - [x] SubTask 5.3: 在 Docker Linux Engine 上从当前源码重建镜像并执行本地五服务
    冒烟；记录未调用外部服务、迁移 head、健康状态和清理结果。
  - [x] SubTask 5.4: 更新 `README.md`、`AGENTS.md`、项目分析、Roadmap 和
    `CHANGELOG.md`，将 `restore-runtime-release-gates` 标为已完成，仅关闭
    `AUD-014`、`AUD-011`、`AUD-015`，并保留 `AUD-006`、`AUD-007` 等边界。
  - [ ] SubTask 5.5: 逐项执行 `checklist.md` 的 25 个检查点；失败项新增修复任务，
    修复后重新执行相关门禁和清单。

- [ ] Task 6: 创建原子提交并推送 GitHub：完成一次可追溯的迭代交付闭环。
  - [x] SubTask 6.1: 复核暂存范围、凭据扫描和生成物，确认只包含本轮源码、测试、
    CI、规格和必要治理文档。
  - [x] SubTask 6.2: 创建 `restore-runtime-release-gates` 原子提交；若远端前进，
    以保留双方成果的方式整合并重跑受影响门禁。
  - [x] SubTask 6.3: 推送 `main` 到 `origin/main`，确认本地与远端完整 SHA 一致且
    工作区干净。
  - [ ] SubTask 6.4: 通过 GitHub Actions API 验证目标 SHA 的 Backend、Frontend、
    Release Contracts 和 Container Smoke 四个 Job 全部成功；失败则修复、重新
    验证并再次提交推送，不把失败 run 记录为完成。

- [x] Task 7: 修复验收缺口并复验。
  - [x] SubTask 7.1: 将根 `.dockerignore` 收敛为后端镜像运行资产 allowlist，并
    增加发布契约和确定性测试防止范围回退。
  - [x] SubTask 7.2: 将 `README.md`、`AGENTS.md`、项目分析、Roadmap 和
    `CHANGELOG.md` 中当前全量测试数从 188 同步为 189，不误改历史数字。
  - [x] SubTask 7.3: 使用显式临时 env/override 和重映射端口，在修复后镜像上重跑
    空库、head、legacy 三类本地冒烟，并记录运行过程不读取仓库 `.env`。
    - 合规运行证据（2026-08-16）：release contract 通过；`deepdata-smoke-local4`
      的首条及全部 Compose 调用均显式传临时 env、base+override 和 project name，
      override 唯一指定临时 `env_file`，端口为 `3307/6380/8001/2025/3001`。
    - 当前源码镜像重建后，五服务、三个非业务 HTTP、唯一 head `8f3c1b7a2d4e`、
      head 重启 canary 及 legacy 升级均通过，legacy 角色为 `user`；未发送业务查询，
      未触发模型或搜索调用。
    - local4 容器、网络、卷、专属镜像及本轮临时文件均已删除；其他 Docker
      容器、网络、卷和镜像 ID 集合前后差异均为 0。
  - [x] SubTask 7.4: 独立复验 checklist 2、4、7、8、9、24，并根据复验结果更新
    清单。

# Task Dependencies

- Task 2 与 Task 3 依赖 Task 1；二者可并行实施。
- Task 4 依赖 Task 2 的可运行镜像，并消费 Task 3 的发布契约；Task 4.1 可与
  Task 2、Task 3 的测试准备并行，但运行验收必须等待两者完成。
- Task 5 依赖 Task 2、Task 3、Task 4。
- Task 6 依赖 Task 5 和全部 25 项检查通过，并需要 GitHub 远端访问。
- Task 7 依赖 Task 5.4 和 Task 5.5 的首次清单验证。
