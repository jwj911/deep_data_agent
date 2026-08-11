# 版本化数据库迁移 Spec

## Why
当前数据库表结构仅由 `Base.metadata.create_all()` 初始化，无法表达增量结构变更，
无法在已有数据上安全升级，也无法在 CI 中校验 schema 与模型是否漂移。引入 Alembic
版本化迁移可让全新安装与已有数据升级都可重复执行，并成为 RBAC 等后续候选的前置。

## What Changes
- 引入 Alembic 迁移工具与 `alembic.ini`、`migrations/` 目录（env.py 复用应用配置与
  共享 `Base.metadata`）。
- 新增初始迁移（revision base），精确表达当前 `users`、`sessions`、`messages`
  三张表及其列、主键、唯一约束、索引与外键，作为版本化基线。
- 应用启动初始化改为运行迁移到 head，替换直接 `Base.metadata.create_all()`；
  提供一个幂等的 `run_migrations()` 入口，已有数据库不重复建表。
- 提供 stamp 能力：对已存在（由旧 `create_all` 建立）且结构与基线一致的数据库，
  可标记到基线 revision 而不重复创建，避免升级失败。
- 新增 CI/发布契约校验：迁移 head 唯一、模型与迁移基线无漂移（autogenerate 无差异）。
- 确定性测试覆盖：迁移可在干净 SQLite 上升级到 head 并建出等价 schema；head 唯一；
  模型与迁移一致。
- 同步 `requirements.txt`、README、AGENTS、项目分析、Roadmap 与 CHANGELOG。

## Impact
- Affected specs: establish-runnable-baseline（数据库初始化方式）、
  enforce-release-readiness（发布契约新增迁移校验）。
- Affected code:
  - `requirements.txt`（新增 alembic）
  - `alembic.ini`（新增）
  - `migrations/env.py`、`migrations/script.py.mako`、`migrations/versions/<base>.py`（新增）
  - `data_agent/config/database.py`（`init_db` 改为运行迁移；保留引擎/会话工厂）
  - `data_agent/agent_server.py`（lifespan 调用迁移入口，不改变对外行为）
  - `scripts/check_release_contracts.py`（迁移 head 唯一性校验）
  - `tests/`（新增迁移确定性测试）
  - `README.md`、`AGENTS.md`、`.trae/documents/project_analysis.md`、
    `.trae/documents/roadmap.md`、`CHANGELOG.md`

## ADDED Requirements

### Requirement: 版本化迁移基线
系统 SHALL 使用 Alembic 管理数据库结构，初始迁移精确等价于当前模型定义的
`users`、`sessions`、`messages` 表。

#### Scenario: 干净数据库升级到 head
- **WHEN** 对一个空数据库运行 `alembic upgrade head`（或应用迁移入口）
- **THEN** 创建出与模型 `Base.metadata` 等价的三张表（列、类型、主键、唯一约束、
  索引、外键一致），且 `alembic current` 指向 head。

#### Scenario: 迁移 head 唯一
- **WHEN** 校验迁移历史
- **THEN** 有且仅有一个 head revision，迁移链可线性升级。

### Requirement: 应用初始化使用迁移
系统 SHALL 在应用启动时通过运行迁移到 head 来准备数据库，而非直接调用
`Base.metadata.create_all()`；该操作对已处于 head 的数据库幂等。

#### Scenario: 启动时准备数据库
- **WHEN** FastAPI 生命周期启动且数据库为空
- **THEN** 迁移将数据库升级到 head；已在 head 时不做重复变更且不报错。

#### Scenario: 已有数据兼容
- **WHEN** 数据库已由旧初始化方式建立且结构与基线一致
- **THEN** 可标记（stamp）到基线 revision 后继续，无需删除或重建已有数据。

### Requirement: 模型与迁移一致性校验
系统 SHALL 提供确定性校验，确保模型定义与迁移基线不漂移。

#### Scenario: 无漂移
- **WHEN** 以模型 `Base.metadata` 对升级到 head 的数据库做结构比较
- **THEN** 不存在缺失或多余的表、列、索引或约束差异。

### Requirement: 迁移契约校验
发布契约检查 SHALL 校验 `migrations/versions` 存在且 head 唯一。

#### Scenario: 契约通过
- **WHEN** 运行发布契约检查
- **THEN** 迁移目录存在、head 唯一时通过；缺失或多 head 时返回非零并输出规则名与路径。

## MODIFIED Requirements

### Requirement: 数据库初始化
数据库初始化 SHALL 由版本化迁移驱动。`init_db()` 语义改为“将数据库迁移到 head”，
保持对 FastAPI 生命周期的既有调用点不变，且不改变现有表结构、字段与所有权语义。

## REMOVED Requirements

### Requirement: 直接 create_all 初始化
**Reason**: 无法表达增量变更、无法在已有数据上安全升级、无法在 CI 校验漂移。
**Migration**: 保留 `Base.metadata` 作为迁移基线来源与测试建表用途；生产初始化改为
运行 Alembic 迁移；对既有一致数据库使用 stamp 到基线 revision。
