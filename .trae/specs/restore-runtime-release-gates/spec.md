# 恢复运行时发布门禁 Spec

## Why

当前后端镜像未包含 `alembic.ini` 与 `migrations/`，但 FastAPI 启动时必须运行
Alembic，导致镜像构建可以成功而容器无法完成启动。现有 Hosted CI 只做宿主机测试、
前端构建和 Compose 静态解析，同时凭据内容扫描未覆盖全部 Git 跟踪文本，因此无法
阻止同类镜像缺件或扫描盲区进入主分支。

## What Changes

- 补齐后端镜像的 Alembic 配置与迁移版本资源，使 FastAPI 和 LangGraph 共用的镜像
  保持与宿主机一致的项目根目录契约。
- 为镜像运行资产增加发布契约与确定性测试，删除任一必需迁移资源时门禁必须失败。
- 将凭据内容扫描改为从 Git 跟踪文件和非忽略的待提交文件发现候选，扫描所有可识别
  UTF-8 文本，不再依赖少量固定文件和目录前缀。
- 扩展 GitHub Actions，在推送到 `main` 和合并请求时从干净 checkout 构建当前
  前后端镜像，并使用专用假配置启动 MySQL、Redis、FastAPI、LangGraph、Frontend
  五个服务。
- 容器冒烟验证五服务健康、FastAPI 容器内迁移到唯一 head、前端静态入口可访问，
  并覆盖空库、已在 head 和受支持旧基线三类数据库状态。
- 失败时只保留有界、脱敏的服务状态与日志，工作流无论成功失败都删除容器、网络、
  匿名卷和临时配置。
- 完成实现与验收后同步 README、AGENTS、项目分析、Roadmap、CHANGELOG 和本规格
  状态，创建原子提交并推送到 GitHub，确认目标 SHA 的 Hosted CI 全部成功。
- 本轮无 **BREAKING** API、数据库 schema 或用户界面变化。

## Impact

- Affected specs:
  - `enforce-release-readiness`
  - `add-versioned-migrations`
  - `audit-project-roadmap`
- Affected code:
  - `data_agent/Dockerfile`
  - `.github/workflows/release-readiness.yml`
  - `docker-config/docker-compose.yml`（仅在冒烟隔离或健康等待确有需要时定向修改）
  - `scripts/check_release_contracts.py`
  - `tests/test_release_contracts.py`
  - 容器冒烟所需的最小测试脚本或 fixture
  - `README.md`、`AGENTS.md`
  - `.trae/documents/project_analysis.md`、`.trae/documents/roadmap.md`
  - `CHANGELOG.md`

## ADDED Requirements

### Requirement: 后端发布镜像包含完整迁移运行资产

后端发布镜像 SHALL 在固定工作目录中包含应用源码、`langgraph.json`、
`alembic.ini`、`migrations/env.py`、迁移模板和全部版本文件。镜像不得复制本地
`.env`、虚拟环境、测试缓存、构建产物或 Git 元数据。

#### Scenario: 从空库启动 FastAPI

- **WHEN** 从干净构建上下文构建后端镜像，并以专用假配置连接空 MySQL 数据库
- **THEN** FastAPI 容器在应用可用前完成 `alembic upgrade head`，数据库 revision
  精确等于仓库唯一 head，健康检查最终通过

#### Scenario: 已在 head 的数据库重复启动

- **WHEN** 同一镜像再次连接已经处于唯一 head 的数据库
- **THEN** 迁移幂等完成，不重复建表、不修改既有业务数据，FastAPI 正常就绪

#### Scenario: 受支持旧基线升级

- **WHEN** 镜像连接由项目已知旧版 `create_all` 契约建立且与基线一致的专用数据库
- **THEN** 现有兼容路径可 stamp 到基线并升级到唯一 head，测试数据保持不变

#### Scenario: 镜像迁移资源回归

- **WHEN** Dockerfile 不再复制 `alembic.ini`、迁移目录或版本文件
- **THEN** 确定性发布契约或容器冒烟返回非零，不允许仅凭镜像构建成功通过

### Requirement: 全版本控制文本凭据扫描

发布契约 SHALL 以 Git 跟踪文件及非忽略的待提交文件作为内容扫描候选集合。对每个
候选普通文件，扫描器 SHALL 尝试按 UTF-8 文本读取；包含 NUL 或无法按 UTF-8 解码的
文件 SHALL 作为二进制跳过。扫描范围不得再受顶层目录或固定文件清单限制。

#### Scenario: 新目录中的凭据 canary

- **WHEN** 在 `scripts/`、`migrations/`、`.github/`、`tests/`、`.trae/` 或新的
  顶层目录中加入匹配规则的无效凭据 canary
- **THEN** 本地和 Hosted 发布契约均返回非零，并只输出规则名、相对路径和行号

#### Scenario: 非忽略的待提交文本

- **WHEN** 工作区存在尚未跟踪但未被 `.gitignore` 排除的 UTF-8 文本文件
- **THEN** 本地发布契约对其执行同等内容扫描，避免凭据在暂存前绕过检查

#### Scenario: 二进制文件与允许样例

- **WHEN** 仓库包含受跟踪二进制文件、合法占位值或拆分构造的测试 canary
- **THEN** 扫描器稳定跳过二进制内容并允许明确的非凭据样例，不输出文件内容或
  完整敏感值

### Requirement: Hosted 容器构建与五服务冒烟

GitHub Actions SHALL 为 `main` 推送和合并请求执行独立的 Container Smoke Job。
该 Job SHALL 从当前目标 SHA 的干净 checkout 构建前后端镜像，启动五服务，并把
运行结果绑定到该 SHA。

#### Scenario: 五服务正常启动

- **WHEN** Container Smoke Job 使用仅供 CI 的假模型、搜索和 JWT 配置启动 Compose
- **THEN** MySQL、Redis、FastAPI、LangGraph 和 Frontend 均达到健康状态，前端
  `/data_copilot/` 与 FastAPI `/api/health` 可访问，且过程不调用真实模型或搜索
  服务

#### Scenario: 验证容器内迁移 revision

- **WHEN** FastAPI 在容器内完成空库初始化
- **THEN** MySQL 中存在且仅存在一个 `alembic_version` 值，并与仓库唯一 migration
  head 完全一致

#### Scenario: 启动或健康检查失败

- **WHEN** 任一镜像构建、容器启动、迁移或健康检查失败或超时
- **THEN** Job 返回非零，输出有界的 `docker compose ps` 与脱敏日志摘要，并标识
  失败服务，不输出环境变量、Compose 展开配置、凭据或业务数据

#### Scenario: 工作流清理

- **WHEN** Container Smoke Job 成功、失败或被取消
- **THEN** 清理该 Job 创建的容器、网络、匿名卷和临时配置，不影响其他 Job

### Requirement: 发布证据与 GitHub 交付闭环

每轮迭代 SHALL 在实现、测试、规格和治理文档一致后创建原子提交并推送到
`origin/main`。验收 SHALL 记录提交 SHA 和对应 GitHub Actions run。

#### Scenario: 迭代成功交付

- **WHEN** 本地等价门禁、25 项验收清单和暂存范围检查全部通过
- **THEN** 提交并推送本轮变更，目标 SHA 的 Backend、Frontend、Release Contracts
  和 Container Smoke Job 全部成功，本地与远端 `main` 一致且工作区干净

## MODIFIED Requirements

### Requirement: 发布就绪持续集成

发布就绪工作流 SHALL 保留 Backend、Frontend 和 Release Contracts 三个既有 Job，
并新增 Container Smoke Job。静态 Compose 解析、宿主机测试或历史运行结果不得替代
当前 SHA 的镜像构建、容器内迁移和健康证据。

### Requirement: 发布契约文件发现

发布契约的内容扫描 SHALL 从 Git 文件集合发现文本候选，而不是维护
`SCAN_EXACT_FILES` 与 `SCAN_PREFIXES` 形式的有限覆盖。固定文件清单只可用于必须
存在的结构契约，不得再决定凭据内容扫描范围。

### Requirement: 数据库迁移发布验证

迁移确定性测试 SHALL 继续验证 SQLite 上的 schema 与模型一致性；发布镜像验收
同时 SHALL 在容器内使用 MySQL 证明迁移资源存在、revision 到达唯一 head 且重复
启动幂等。两类证据互补，任何一类不得替代另一类。

## REMOVED Requirements

无。本轮不删除既有质量门禁、迁移兼容路径、Compose 服务或发布文档。

## Non-Goals

- 不在本轮修复 `AUD-006`：不生成 Python 哈希锁、不固定基础镜像 digest 或
  GitHub Actions SHA，不引入 SBOM、漏洞扫描或自动依赖更新。
- 不修复 `AUD-007` 的未知 schema 盲 stamp；本轮旧库场景仅使用已知且结构完全
  一致的专用 fixture，未知或漂移 schema 的 fail-closed 治理由
  `prove-data-recovery` 负责。
- 不调用真实模型、搜索服务或生产数据，不部署生产环境，不重写 Git 历史。
- 不改变 API、认证授权、数据库业务 schema、前端交互或运行期健康语义。
