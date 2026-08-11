# 验收清单

- [x] `requirements.txt` 新增 `alembic`，与现有 SQLAlchemy 2.x 兼容。
- [x] `alembic.ini` 与 `migrations/`（env.py、script.py.mako、versions/）存在且结构规范。
- [x] env.py 从应用配置解析数据库 URL，`target_metadata` 指向共享 `Base.metadata`（已注册 users/sessions/messages 三张表）。
- [x] env.py 启用 `render_as_batch=True`，SQLite 与 MySQL 均可运行迁移。
- [x] 初始迁移 `down_revision=None`，精确表达三张表的列、主键、唯一约束（username/email/session_id）、索引与外键。
- [x] 干净 SQLite 上 `upgrade head` 后，表/列/索引/外键与 `Base.metadata` 等价。
- [x] 迁移历史 head 唯一，迁移链可线性升级。
- [x] `init_db()` 改为运行迁移到 head，FastAPI 生命周期调用点不变，且对已在 head 的库幂等。
- [x] 对已由旧初始化建立且结构一致的数据库，可 stamp 到基线 revision 而不删除或重建数据。
- [x] 现有表结构、字段、所有权语义与 API 行为不因迁移引入而改变。
- [x] 发布契约检查校验 `migrations/versions` 存在且 head 唯一，缺失或多 head 返回非零。
- [x] 新增确定性测试覆盖：升级到 head 建出等价 schema、head 唯一、模型与迁移无漂移，全部通过。
- [x] 后端 `pytest`、`isort --check-only`、Compose 解析、`git diff --check` 通过。
- [x] 前端 `pnpm typecheck`、`pnpm lint`、`pnpm format:check`、`pnpm build` 通过，无构建产物残留。
- [x] README、AGENTS、项目分析、Roadmap、CHANGELOG 与迁移实现一致，Roadmap 将版本化迁移标为已完成/当前迭代。
