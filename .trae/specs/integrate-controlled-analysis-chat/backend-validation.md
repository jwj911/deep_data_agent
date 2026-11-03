# 后端最终回归

2026-11-02。基线 `main @ 0aca6ee2c9adf1aabeff85b0f028fae6d185612f`，
叠加上一轮统计后端及本轮聊天接入的未提交改动。当前结果不代表 Hosted、
容器部署或真实模型效果。

## 最终执行

| 检查 | 结果 | 执行标识 |
| --- | --- | --- |
| 完整后端 pytest | **958 passed，99.04 秒**，exit 0 | `7d32ceb0bb6b3b292677d1be114f3090` |
| 完整 worker 生命周期与容量定向 | 10 passed，80 deselected，29.92 秒，exit 0 | `5efdf1c29de6d38c847f0dd293b18597` |
| `isort --check-only data_agent tests scripts` | exit 0 | `f682050035aaa1c4331399939064e40f` |
| `scripts/verify_runtime_lock.py` | 134 个适用包匹配；`support_checked=false` | `14d6198217e19af0219b9de020d7c77d` |
| `alembic -c alembic.ini heads` | 唯一 `b6f4e8c2a9d1 (head)`，exit 0 | `ba9407819d55822a3140c38b0ff0097e` |
| `scripts/check_release_contracts.py` 复检 | Release contracts passed，exit 0 | `669226d4dc3626c1a81a21af2b9ab3ee` |
| `git diff --check` | exit 0；既有 LF/CRLF 提示保留 | `59e71c95828ce73e7d4d7c5d4c8d93a4` |

完整 pytest 包含迁移、发布契约、文件统计、统计工具、缓存准入、预算、复制、
租户、取消与恢复等现有测试，不把上述定向 10 项另外相加到 958。
命令 cwd 为仓库根；Python 为锁定环境
`D:\Code\.dda-recovery-admission-20261028\venv\Scripts\python.exe`。

每次测试命令独立设置以下环境，未读取真实 `.env`：

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:LANGSMITH_TRACING = 'false'
$env:LOG_FILE_PATH = ''
```

实际完整测试命令为 `python -B -m pytest -q -ra -p no:cacheprovider --basetemp
D:\Code\.dda-chat-full-4aad116de54f4d42921bc9056aa1dd6e\pytest`。
同一唯一目录同时设为 TEMP/TMP，测试结束后删除。定向执行同样使用
`D:\Code\.dda-chat-worker-1498b46828b74a3281f772ecec400543`，
追加 `tests/test_statistics_tool.py -k
'actual_slow_read_lifecycle or cancelled_workers_keep_capacity'`，结束后删除。
重跑应生成新 UUID 目录，不能复用历史 basetemp。

## 独立核验缺口与修复

首次独立统计工具核验 90 项通过，但 BCV-01 指出原慢读取测试仅等待读取结束，
未等待完整 worker 后再断言缓存和成功消息，详见
[首次记录](backend-contract-validation.md)。该证据不足没有被测试通过数掩盖。

补强用真实文件、真实工厂图、实际 concurrent Future 和工具回调：
取消、超时及关闭流分别覆盖原图、copy、with_config。文件读取和统计返回前
设两处受控屏障；终止 run 后放行，等待实际 worker 完成及真实槽位释放回调，
再断言没有工具成功结束事件、缓存写入、额外模型请求或重复租约释放。
取消/超时路径使用真实 `AgentService`；关闭流检查流确已终止。
随后以独立 run 重试，确认同一事件观察器能观测真实成功 ToolMessage，
排除“观察器根本未生效”的假通过。

首轮补强曾出现 9 失败、1 通过：新增断言错误假定取消必触发
`on_tool_error`，LangChain 不保证该回调。去掉该非合同假设后，保留实际
调用端取消/超时状态、完整 worker、开始/成功结束事件、缓存、槽位、租约
及重试对照，取得上述 10 项和全量 958 项通过。未发现需要修改生产工具实现的
迟到交付故障；本次修复的是验证缺口。

## 本轮失败与限制

- 首次后台完整测试命令 `a039e5ccf6ba80506da35b58c0014865` 在创建
  `D:\Code\.dda-chat-full-9ca76c3af6454c5794702e33cd889789` 时被拒绝。
  pytest 未启动，没有产生测试失败数。随后正常启动命令创建新目录，超过
  60 秒后由工具转后台，取得完整结果；没有修改 ACL 或放宽权限。
- 发布扫描首次 `8882cc79b9e75a84a5c4838972e1d18f` 发现
  `frontend-validation.md:316` 的公开测试 Bearer 字面量符合凭据模式。
  附录改为明确的 `test-token` 占位值，运行行为不变，扫描器未修改；复检通过。
  附录的脱敏占位值不是原运行使用的字面量，原运行证明的是请求头转发规则。
- 上轮及本轮早期单独通过数保留原归属，不计入最终 958 项之外的总数。
- 使用离线提供方、SQLite 和测试租约/缓存替身。没有向真实模型、搜索、
  业务 MySQL 或业务 Redis 发送请求；本机离线通过不等于生产放行。
- 缓存契约的独立源码复核和最终静止快照浏览器结果分别记录，不以本表替代。
