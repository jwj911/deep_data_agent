# 任务 2：后端合同独立核验

2026-11-02。范围为本轮 R1/R2、checklist 1–9。只读实现和测试，
唯一保留写入为本文件；未修改 spec/tasks/checklist 或业务代码。

## 结论

**独立执行 `tests/test_statistics_tool.py` 一次：90 passed in 48.99s，
exit 0，无失败、错误或跳过。不能据此宣称 checklist 1–9 全部通过。**

- 未发现已复现的任务 2 运行时合同违规；发现下述验证缺口 BCV-01。
- checklist 3 只有 system 提示接入证据，没有歧义输入下的澄清行为证据。
  不以受控 provider 的固定调用计划证明真实模型理解或选择能力。
- checklist 8 的容量与取消路径通过，但完整 worker 结束后的迟到交付/缓存
  断言不完整，整项未通过。
- 核验前后 `agent_service.py` 和 `agent_budget.py` 发生任务 3 并行改动。
  本次运行结果不是最终合并工作树的 exact-SHA 验收；7/9 的最终验收保留未通过。
- 作者的 169 项（90 stats、53 预算、26 managed_file）仅为作者报告。
  本次只独立执行上述 90 项，没有把导入的 fixture 计作另 79 项执行。

## 发现与后续责任

### BCV-01：迟到交付测试没有覆盖完整 worker 完成后的观察窗口

类别：测试证据缺口，建议 P2；不是已经观察到迟到成功或缓存写入的运行时缺陷。
对应 checklist 8，定位 `tests/test_statistics_tool.py:454-461,509-526`。

源码复核步骤与实际时序：

1. `read()` 在 459 行调用真实 `_read_bytes`，461 行于其 `finally` 设置
   `finished`。此时只是读取结束；工具 `_calculate` 后续仍需执行统计、
   source/hash 封装及返回。参见
   `data_agent/services/managed_file_service.py:599-610`、
   `data_agent/tools/file_statistics.py:75-109`。
2. 515 行 `cache.aset.assert_not_awaited()` 发生在 518 行 `release.set()` 之前，
   证明的是慢读取尚未恢复时没有写缓存，不是恢复并完成后没有迟到写入。
3. 522 行只等上述读取事件，523 行固定睡眠 20ms；524–526 行检查 provider 次数
   及此前收集的流状态。`cancel/timeout` 分支的 `delivered` 本来就是空列表，
   这两个分支的该列表断言不能独立证明无迟到工具消息。
4. fixture 的 98 行最终会 `pool.shutdown(wait=True, cancel_futures=True)`，
   但发生在测试观察结束后，没有随之执行缓存、消息、租约的终态断言。
   这也不等于已证明等待的那个 worker 在 523 行前完成。

影响：当前测试确实验证取消传播、即时清理、没有后续模型发送以及可重试；
但无法单独支撑测试名称和 checklist 8 中完整的“无迟到成功或缓存”结论。
实际 `_ainvoke` 的 `wrap_future`、单 owned producer 清理，以及 worker 不直接访问
回答缓存的源码均支持安全方向；本记录不把证据不足夸大成已复现应用故障。
未做 mutation 或新增运行，遵守本次仅执行 90 项一次的限制。

建议由主 Agent 增补验证修复任务，再由另一 Agent 实施：
在测试中观察此次实际 `_submit` 返回的 concurrent Future 完成，保持事件循环存活；
完成后再次断言无缓存写入、无新增成功交付/模型请求、租约仍只释放一次，
再开始新 run。不要用读取结束事件或固定 sleep 代替整个执行完成。
保留这次失败的验收判断和 90 passed 原始记录，不自行修改业务或测试。

### BCV-02：最终共享代码快照尚未独立验证

类别：并行实施导致的证据边界，不是代码缺陷，不要求回滚任务 3。
核验前后两次哈希见后文。重新读取 diff 确认改动涉及回答缓存观察、
`RunBudget` 生命周期、模型中间件和 `AgentService.ainvoke`，不是纯注释变化。
未记录 pytest 进程实际导入这两个模块时的内容哈希，不能确定本次运行加载了
前置、后置或两者之间的哪个组合。

主 Agent 应在任务 3 完成、共享文件稳定后固定哈希，再安排后续完整后端及门禁。
本次不重复运行 90 项，不启动全后端、isort、release 或 migration。

## 逐项 Checkpoint

下表“通过”只适用于本次任务 2 范围及注明证据，不是最终工作树发布背书。
共享模块的最终快照仍需统一重验；未满足的部分明确标为未通过。
测试行号均对应本次前后不变的 `tests/test_statistics_tool.py`。

| 项 | 判定 | 独立实证与边界 |
| --- | --- | --- |
| 1 | 通过（所记录基线范围） | 初始 status、根 AGENTS、本轮 spec/tasks/checklist/baseline 均已读取；子目录未发现额外 AGENTS。前轮统计源/test 与本轮 spec 的三个 SHA 与 baseline 一致，测试后再次一致。没有写入已有代码或清理其他 Agent 产物；不声称 baseline 未提供哈希的全部文件逐字节未变。 |
| 2 | 通过 | 191–207 行 9 个 extra 负控；实际 provider 收到的 schema 只有 `file_id/column`，两项 required、`additionalProperties=false`；拒绝前若读文件会直接使测试失败。216–223 行另 7 个严格参数负控。工具 50–61、138–147 行同时约束运行校验与模型 schema，不暴露 owner/path/expression/metric/config/context/预算字段。 |
| 3 | 未通过完整行为验收；提示接入通过 | 372–403 行检查父/子真实 SDK 请求的 system 消息含澄清、禁止默认首项和预览工具说明；工具描述也有相同限制。但 74–80 行 provider 按 `plans` 发固定调用，输入为 `parent/child-*`，不是歧义附件/缺列名场景，没有实际澄清回合。仅验证 system 提示和受控 provider 协议，不主张真实智能能力或模型成功率。 |
| 4 | 通过（受控认证上下文） | 227–267 行含 owner、other、admin、deleted、role 及仅 config 身份的负控。工具从 active subject 新建 DB Session、`db.get(User, subject)`；真实服务 `get_file` 按当前权限、owner、expiry 过滤。role 用例提交角色变更并临时撤销该角色权限，使“用了旧 role”可被检测；不把该替身权限表当成生产角色政策。406–431 行两个并行 owner 返回 `0.3`/`8` 且账本隔离。未测试真实 JWT/HTTP Auth 或业务 MySQL。 |
| 5 | 通过 | 144–184 行共 24 项：CSV/JSON × 四调用面 × original/copy/with_config。每次实际上传并读取 12,001 行、超过 20,000 字节的文件；同 UUID/actor/column 的 ASGI REST payload 完全相等；独立 `Fraction` 校验和为 `2799.123456789012345678`，尾部纳入计算。REST 使用真正路由及文件服务，只有 DB/auth 依赖被隔离。 |
| 6 | 通过 | 成功检查真实 ToolMessage、外层精确键集、整数 version=1 和完整 data；独立排除 `result_sha256` 后按 canonical v1 重编码并哈希。293–318 行 6 个失败覆盖缺列、非数值、删除、过期、等长篡改、未知异常；错误 ToolMessage 与 wrapper 均为 error，无 data 或 private 明细。未知异常/执行器异常为受控注入，不是假装实际基础设施故障。 |
| 7 | 本次路径通过；最终快照未通过（待重验） | 324–353 行 24 项父/子 × 四调用面 × 三图形态；每批三调用可并行，实际 read 记录 subject/账本，父图最多 12 次 read，子图因 `task` 扣 1 次仅 11 次 read，第 13 次合计工具额度抛错。所有 ledger 为同对象，8/12 服务端上限未被 999 覆盖。356–369 行失败也扣额；372–403 行 Barrier 证明父+双子三线程同时读取且共享账本。没有在本次运行另测模型第 9 次实际发送拒绝或 SDK retry，原预算套件留待后续；最终共享模块见 BCV-02。 |
| 8 | 未通过（部分通过，见 BCV-01/02） | 442–537 行 9 项慢读取生命周期已实际通过；cancel/timeout 的 read 位于非事件循环线程，run 结束时 read 仍阻塞，缓存尚未写入。540–587 行容量测试已通过：四个取消 run 留下四个阻塞 worker，后续八个请求均 `analysis_busy`，新 read 不发生。实现用 4-worker pool、非阻塞 semaphore 提交前准入和 Future done callback 释放容量；取消等待不提前释放正在运行的槽位。完整 worker 结束后的无迟到结果/缓存证据仍缺失，不能整项通过。5 秒仅为解析遍历期限，不是同步读取硬抢占。 |
| 9 | 本次路径通过；最终快照未通过（待重验） | 183、256、352、512–516 行精确 acquire/release 事件对；134–138 行检查调用侧 subject/lease 均清空且 active budget 缺失。关闭流用不同 Task 的 `anext/aclose`，取消/timeout 后新 run 的账本不同。真实 lease contextmanager 被调用，底层 Redis acquire/release 是事件替身，证明调用次数而非真实 Redis key 删除；容量用例 24 次事件计数弱于逐租约断言，其余用例已有事件对。源码 `copy_context().run` 隔离 worker，未直接探测每个工作线程退出后的私有 Context；最终共享模块见 BCV-02。 |

## 测试真实性

- `chat` fixture 仅替换 DB 工厂、文件服务实例、同配置的独立四线程池、
  provider 和租约外部依赖，没有替换统计工具或工厂图执行结果。
- `tests/test_agent_aggregate_budget.py` 的 `factory` 使用
  `httpx.MockTransport`、真实 `ChatOpenAI` 和 `create_agent_graph`；
  `_run` 实际走 invoke/ainvoke/stream/astream。该文件本轮 diff 将旧 provider
  计划提取成 `_calls`，未发现因此删掉原预算断言；本次未执行其 53 项。
- `test_file_statistics.api` 的 fixture 按 pytest 的当前测试 fixture 查找规则，
  使用本模块文件型 SQLite 的 `files`。不是另一个空库或静态 JSON 成功替身。
  REST `get_current_user/get_db` 被隔离，不等价于真实认证链验收。
- 慢读取在真实 `_read_bytes` 前等待 Event，恢复后仍调用原读取；关闭流的 custom
  消息仅作为“已经 submit”的测试同步信号，不是伪造统计成功消息。
- 容量测试中的八次拒绝发生在释放四个实际阻塞读取之前；并非仅检查
  `ThreadPoolExecutor(max_workers=4)` 文本。每例 fixture 最后等待自己的 pool 退出。
- 90 为参数化实例数，来自 13 个测试函数：
  `24+9+7+5+1+1+6+24+1+1+1+9+1`。循环内请求、导入的测试模块、REST 对照调用
  不另加 pytest 计数。没有本轮新写测试冒充作者测试，也没有声称完成 mutation。

## 环境、命令与结果

仓库：`D:\Code\deep_data_agent\deep_data_agent`。
HEAD 实测 `0aca6ee2c9adf1aabeff85b0f028fae6d185612f`，不是新工具提交。
解释器实测 Python 3.12.9，固定使用
`D:\Code\.dda-recovery-admission-20261028\venv\Scripts\python.exe`。
本次未重跑 lock 验证；baseline 中 134 包匹配仍是任务 1 的历史证据。

先列外层 workspace 父目录，再生成唯一 UUID 目录，不复用别人的 basetemp。
实际测试命令如下；目录为本次实值，再次运行应生成新的 UUID：

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:LANGCHAIN_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:LANGSMITH_TRACING = 'false'
$env:LOG_FILE_PATH = ''
$taskTemp = 'D:\Code\deep_data_agent\.dda-backend-contract-20261102-29cd876839f44de2a0ad7744c93f4dab'
if (Test-Path -LiteralPath $taskTemp) { throw 'Refusing existing task temp' }
New-Item -ItemType Directory -Path $taskTemp -ErrorAction Stop | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
& 'D:\Code\.dda-recovery-admission-20261028\venv\Scripts\python.exe' -B -m pytest -q -ra -p no:cacheprovider --durations=10 --basetemp (Join-Path $taskTemp 'pytest') tests/test_statistics_tool.py
```

执行标识 `35145d558502333092870e0ecf445869`，exit 0：

```text
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 48.99s
```

耗时输出包含 `test_actual_slow_read_lifecycle_has_no_late_delivery[copy-timeout]`
0.43s、`[with_config-timeout]` 0.43s，
`test_cancelled_workers_keep_capacity_and_reject_without_queueing` 0.43s。
未读取真实 `.env`，未访问真实模型、搜索、业务 MySQL/Redis。
`tests/conftest.py` 覆盖离线配置；模型 SDK 请求在 HTTPX MockTransport 内处理。

## 快照与保留

初始 status 已有前轮 5 个 tracked 改动、统计源/test、前轮规格目录，
并有任务 2 的工具注册/提示/test 改动及任务 4 的前端与联调脚本。
未改这些文件。以下 SHA-256 前后相同：

```text
data_agent/services/file_statistics.py
345B66A649A6E959C9A4A09192B2BE8AA7E0C74F8F69FE9061A82D8D70D48225
tests/test_file_statistics.py
8F8805FD122C4527FE3615FDF3AEC3EE6F6D227198FE9B1FBCD46FB4C84DAC69
.trae/specs/integrate-controlled-analysis-chat/spec.md
059D966DAC62F21CDF10277521C2F5A82EFB8C793BAC062CFA84857843441DAF
data_agent/tools/file_statistics.py
97623FBE81E6DACBCE1DFAB5DA9BA5EAD9F82421E59AAA82D8BA72D3B7D57335
tests/test_statistics_tool.py
B2BA9995AC5D5B8F2E3E86DD8334C8F264BF80652FA7098ADE1E7BA30E718C89
```

前三项与 baseline 原值一致。共享模块的前/后哈希：

```text
data_agent/services/agent_service.py
before: 249456052D58E68ED3D33536E007C5682AE1B3A5D55DAC5375A7BB794966792D
after:  04F18CB904CC9B0760DAD88C604ECEEEDD89F24B2C6A74BD43D3683401FC5057
data_agent/services/agent_budget.py
before: C147CD0F82F35C943121DEFA96F8A5DFD9B3BA7B90BD388895460C3F436E58BA
after:  7CD105E46BE13E3D896B36EA89897CC9ED156CF193CFE17DCF9E87733A4F3279
```

“after”为测试结束后的观测值，不保证其他 Agent 后续不再改动。
status 另出现 `tests/test_agent_cache_admission.py` 及前端 `out/` 构建产物；
不是本次生成，未删除。后续引用共享源的行号应重新定位函数名。

## 收尾与未验证项

本次创建的唯一外层临时目录已在测试进程和 fixture 退出后，确认父目录及非
reparse point，再按完整固定路径删除。执行标识
`75718855f51e7190567f791bd6f179b9`，exit 0，`TASK_TEMP_EXISTS=False`。
没有清理其他任务目录、变更 ACL 或修改锁定 venv。

`rg` 不可用，首次文件搜索失败后改用 PowerShell/`git diff`，未安装工具。
不存在的父级 AGENTS 查询返回非零，不影响已读取仓库根 AGENTS；
没有把搜索失败算成应用测试失败。

完整后端、isort、发布契约、migration、前端门禁、浏览器、容器、
Hosted、真实模型和生产验收本次均未执行/未验证。
任务 3 的缓存合同不在本次验收范围，不以此记录提前勾选 18–21。
不提交、不推送、不部署；tasks/checklist 由主 Agent 根据本记录补任务并更新。

本文件执行 `git diff --no-index --check -- /dev/null <本文件>`，
exit 1，仅 LF/CRLF 提示，无 whitespace error；1 表示新增文件差异，不冒记 exit 0。
末次核对上述五个稳定 SHA 仍相同；status 又出现并行修改的
`tests/test_agent_concurrency.py`、`tests/test_agent_tenant_boundary.py`，
前端 `out/` 已不在 status 中。本次没有写入或删除这些路径。
