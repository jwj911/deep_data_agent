# 数据库结构拒绝验收记录

2026-10-28；当前工作树，未提交，尚未取得本轮 Hosted 证据。

修复前，实际测试构建「完整旧 schema + 未知额外表」并清除版本号；
`_prepare_database()` 未拒绝，执行了 stamp/升级。对应红灯命令：

```text
python -m pytest -q -x tests/test_migrations.py -k unknown_unversioned -p no:cacheprovider
```

修复后，迁移模块支持 Alembic 显式连接；参考结构在独立内存 SQLite 中执行
实际 revision 迁移构建，不在待识别数据库试执行。结构匹配之后才允许 stamp/升级。
已知版本号也必须匹配对应完整结构，空版本表和伪造 revision 不能绕过检查。

本机 `tests/test_migrations.py` **25 项通过**：

- 原有八项迁移、metadata、旧库数据保留和 downgrade 回归保持。
- 十一种无版本号负控：额外表、缺失表、非空但无 users、错误类型/长度、
  可空密码、额外默认值、缺失唯一索引、缺失外键、额外列、视图、触发器。
  各自返回 `database_schema_unknown`，拒绝前后 SQLite schema 快照完全相同，
  没有创建 `alembic_version`。
- 空版本号、未知版本号、伪造当前 head 的部分 schema 均拒绝，
  版本号和结构快照保持不变。
- 初始、RBAC、当前 head 三个已知 revision 都能初始化并重复执行，
  canary 账户字段保留，角色回填为 user，版本收敛到唯一 head `b6f4e8c2a9d1`。

全量后端 684 项通过时已包含前 21 项 schema 回归；新增触发器及三项已知版本
正控另由上述 25 项集合验证。最终工作树的完整集合在最终发布前重跑。

真实隔离 MySQL 8.4 的 `scripts/verify_mysql_schema.py` **20 个控制例通过**。
使用缓存官方镜像、随机映射 loopback 端口及 tmpfs 数据目录，无既有业务库。
空库、三个已知 revision、无版本完整旧库能升级并保留用户/REST canary；
额外/缺失表、列类型/可空性/默认值漂移、缺失唯一索引/外键、视图/触发器、
非 InnoDB、缺失自增、空/未知/伪造版本均拒绝，SHOW CREATE、版本和数据
快照不变。反射规范化无须额外修补。进程结束已删除该自有容器。

该门禁不证明备份可用或全域一致恢复。新运行时锁另需独立回归。

## 新锁 Hosted 实证通过（2026-10-28）

完整实施 SHA `1910fdfa8653beb3233e48f0e5d29ac2d1e42514` 的
[run 40635353761](https://github.com/jwj911/deep_data_agent/actions/runs/40635353761)
四 Job 均 success。Backend `122640951876` 在新哈希锁下完整
**733 项通过**，真实 MySQL 8.4 **20 个结构控制例通过**；
Container Smoke 的空库、head 重启和 known legacy canary 升级成功。
结构门禁与另行执行的三域独立恢复各自有实证，范围见
[运行时记录](../stabilize-delivery-baseline/validation.md)。
不把已知 legacy 支持扩展为任意旧库兼容，生产持久业务仍 NO-GO。
