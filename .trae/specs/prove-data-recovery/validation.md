# 恢复门禁验收记录

2026-10-28；当前工作树，未提交。完整独立恢复演练尚未执行，不提前裁定通过。

Compose 已为 LangGraph 主历史增加 `langgraph_data:/app/.langgraph_api`，
并保持其与 FastAPI 共享受管文件卷。`scripts/data_recovery.py` 要求所有
写入服务正常停止；导出 MySQL、主历史和受管文件三个域；恢复前核验固定
清单、全部大小和 SHA-256、归档路径及条目类型、迁移/依赖锁兼容性，
然后检查目标数据库和两个文件卷为空。

本机新增文件恢复与运行时锁测试 **32 项通过**。恢复负控覆盖每个域的
缺失/篡改/截断、清单格式/停写/运行时不符，以及重算哈希之后仍拒绝的
目录穿越、绝对路径、Windows 路径、符号/硬链接和 FIFO。拒绝发生在
Docker/数据库恢复调用之前；非空数据库/文件卷不可覆盖，活动 writer
阻止创建备份目录。该结果只证明这些拒绝边界。

随后补入恢复目标实际代码/安装版本校验，以及 Python `-O` 下仍须拒绝
非停写清单的回归；两项均先红后绿。新锁下恢复/锁与发布契约集合
**193 项通过**（34 项恢复/锁 + 159 项发布契约）。全部恢复校验使用显式拒绝，
不会随 Python 优化模式关闭。

全量后端 **717 项通过，138.73 秒**时已包含前 29 项新测试；新增三项
目标/写入保护随后由上述 32 项定向集合验证，最终新锁仍须重跑完整集合。

`scripts/verify_data_recovery.py` 已建立隔离演练：三身份/RBAC、REST 历史、
UUID 主 thread 的 state/history、实际磁盘 store、受管文件版本、删除、
过期、篡改及越权控制；全新 Compose 项目/数据库/卷恢复，重新登录后比较。
实际执行、负控目标无写入与恢复耗时仍需取得证据。
引用采用前端实际的 JSON 内容块，checkpoint 包含虚拟文件。独立目标 API
使用动态发现的 Origin；前端公开 Origin 的灾难切换不属于该演练。
本机新镜像构建因磁盘保护中止，完整恢复转到精确提交 Hosted 验证。

备份归档包含私有业务数据，只写任务临时目录，不提交到 Git；清单哈希检测
意外损坏和与可信清单不符的修改，不提供外部攻击者重写清单时的签名认证。
该实现是人工停写快照；无自动异地备份、生产 dev runtime 支持或长期
RPO/RTO 承诺，不能据此裁定生产持久业务 GO。

最终 Windows 新锁全量 **723 项通过，131.69 秒**；本轮完整独立恢复、
负控目标无写入、各域逐值对比和耗时等待对应精确 SHA 的 Hosted 实证。
该提交包含演练入口及门禁，不在提交前写入尚未取得的成功结果。

## Hosted 修复轮（2026-10-28）

上述未提交和待执行描述保留其记录时点。后续实际运行按提交分别裁定：

- `e665a4b` 的 run `40633932174`：Chromium 七项 UI 通过；恢复在
  `recovery_drill_port_invalid` 拒绝，尚未创建备份。
- `2f8e348` 的 run `40634732017`：四个 Job 中 Backend、Frontend、
  Release Contracts 成功；729 项后端回归通过，Chromium 七项再次通过。
  恢复准备篡改 canary 时发生 `io.UnsupportedOperation: fileno`，
  未进入备份；Container Smoke 失败且自有资源清理成功。
- 双栈端口修复按唯一宿主端口去重，保留 IPv4 可达性与非歧义拒绝。
  内存脚本输入修复保留真实文件的流式传输，仅将无文件描述符的内存字节
  交给子进程输入管道。真实子进程四组合回归先 2 红 / 2 绿，修后恢复、
  运行时锁和浏览器定向 **44 项通过，18.50 秒**。

这些修复结果只证明相应接口；完整三域恢复仍以之后成功的精确提交
Hosted 运行、负控和逐值比较为准。

## 独立恢复实证通过

完整 SHA `1910fdfa8653beb3233e48f0e5d29ac2d1e42514` 的
[run 40635353761](https://github.com/jwj911/deep_data_agent/actions/runs/40635353761)
四 Job 均为 success；Container Smoke `122640951730` 的
`Verify three-domain backup and fresh restore` 成功，返回
`data_recovery: passed` 和 `independent_target: true`。

来源停写并正常关闭后，备份 MySQL、LangGraph 历史/store 卷及受管文件卷；
恢复到新 Compose 项目、空数据库和新文件卷，使用空 Redis。
快照用时 **4.754 秒**；从创建目标到恢复、登录及全部验证完成
**31.757 秒**，迁移为 `b6f4e8c2a9d1`，确认写入丢失 **0**。
这两个时间是本次合成数据演练测量，不能外推生产数据量或长期 RPO/RTO。

- 用户、角色及 REST/file metadata 原始业务行完全相同；新登录和管理员角色
  正确，REST 会话及消息逐值相同。
- thread 的 state/history 逐值相同；UUID 受管引用、checkpoint 虚拟文件和
  独立进程读取的磁盘 store 值保持；文件字节与摘要校验通过。
- 另一用户及管理员访问 owner 会话、文件、thread/state/history 均拒绝；
  删除/过期返回 404，篡改文件返回 503，store API 保持 403。
- 每个域实际执行缺失和篡改恢复，共 **6 项负控**；均在写入前拒绝，
  目标数据库保持为空。完整恢复后再次调用被非空目标保护拒绝，
  业务行保持不变。

独立目标 teardown、来源重新启动、head 重启、known legacy 升级和最终
自有资源清理均成功。完整脱敏回执位于工作区根
`release-gate-implementation-evidence.json`；备份业务归档只存在 runner 临时目录。
公开前端 Origin 的灾难切换、自动异地备份和生产运行时不在本次通过范围，
生产持久业务仍 NO-GO。
