# Tasks

- [x] Task 1: 引入 Alembic 工具与骨架：新增依赖与迁移目录，env.py 复用应用配置与共享 Base.metadata。
  - [x] SubTask 1.1: 在 `requirements.txt` 增加 `alembic`（与现有 SQLAlchemy 2.x 兼容），保持排序风格。
  - [x] SubTask 1.2: 新增 `alembic.ini` 与 `migrations/`（env.py、script.py.mako）；env.py 从 `data_agent.config.database._database_url()` 取 URL，`target_metadata` 指向 `data_agent.models.user.Base.metadata`（导入 session 模型以注册全部表），支持离线/在线模式与 SQLite/`MySQL`。
  - [x] SubTask 1.3: 配置 env.py 的 `render_as_batch=True`（兼容 SQLite ALTER），并禁用 alembic 自带日志覆盖项目日志配置。

- [x] Task 2: 生成初始迁移基线：精确表达当前三张表结构，作为 base revision。
  - [x] SubTask 2.1: 新增 `migrations/versions/<base>_initial_schema.py`，用 op.create_table 表达 users/sessions/messages 的列、主键、唯一约束（username、email、session_id）、索引与外键（sessions.user_id→users.id、messages.session_id→sessions.id），`down_revision=None`。
  - [x] SubTask 2.2: 校验：对干净 SQLite 运行 upgrade head 后，用 SQLAlchemy inspector 比对表/列/索引/外键与 `Base.metadata` 等价。

- [x] Task 3: 应用初始化改用迁移：init_db 运行迁移到 head，保持生命周期调用点不变且幂等。
  - [x] SubTask 3.1: 在 `data_agent/config/database.py` 新增 `run_migrations()`（用 Alembic Config 以编程方式 upgrade 到 head，绑定当前 engine/URL），将 `init_db()` 改为调用它；保留 `get_engine`/`get_session_factory`/`get_db` 不变。
  - [x] SubTask 3.2: 提供对既有一致数据库 stamp 到 base 的兼容路径（若检测到表已存在但无 alembic 版本表，则 stamp base 后 upgrade），确保不删除或重建已有数据；`agent_server.py` lifespan 调用保持不变。

- [x] Task 4: 迁移契约与确定性测试。
  - [x] SubTask 4.1: 在 `scripts/check_release_contracts.py` 增加校验：`migrations/versions` 存在且 head 唯一（解析 down_revision 链或调用 alembic ScriptDirectory），新增规则名如 `MIGRATION_HEAD`；补充契约测试。
  - [x] SubTask 4.2: 新增 `tests/test_migrations.py`：干净 SQLite 上 upgrade head 建出等价 schema；head 唯一；模型与迁移无漂移（对升级后的库与 `Base.metadata` 做结构比较，或用 alembic autogenerate 比较无 diff）。

- [x] Task 5: 文档与发布验证。
  - [x] SubTask 5.1: 更新 `README.md`、`AGENTS.md`、`.trae/documents/project_analysis.md`、`.trae/documents/roadmap.md`、`CHANGELOG.md`：记录迁移命令、初始化行为变化、已有数据库 stamp 流程，将版本化迁移标为已完成/当前迭代并从后续候选移除。
  - [x] SubTask 5.2: 运行 `python -m pytest -q`、`python -m isort --check-only data_agent tests scripts`、`python scripts/check_release_contracts.py`、Compose 解析、`git diff --check`，以及前端 `pnpm typecheck/lint/format:check/build` 确认无回归并清理产物。

# Task Dependencies
- Task 2 depends on Task 1.
- Task 3 depends on Task 2.
- Task 4 depends on Task 2 and Task 3.
- Task 5 depends on Task 3 and Task 4.
