# R5 缓存与 R2 慢线程最终合同独立复核

2026-11-02。范围仅为任务 3、任务 7，以及 checklist 7–9、18–21。
本次只读源码、测试和已有证据；唯一写入为本文件。没有运行 pytest、
模型、浏览器、容器或发布门禁，没有修改业务代码、tests、tasks/checklist，
没有读取 `.env`、提交、推送或部署。

## 结论与证据归属

**未发现本范围内可确认的运行时合同缺陷。7–9、18–21 的最终源码与测试设计
支持本机离线合同通过；BCV-01 的具体测试缺口已补齐。**
这不是本次重新执行测试所得的结论，也不是生产或真实模型放行。

- 主 Agent 执行：完整 pytest **958 passed / 99.04 秒**；慢线程与容量
  **10 passed / 80 deselected / 29.92 秒**。执行标识、环境及门禁结果引用
  [backend-validation.md](backend-validation.md)，不冒称本核验者执行或重放原始日志。
  10 项属于 958 项的子集，不相加。
- 前次独立执行 90 项及 BCV-01/02 原判断继续保留在
  [backend-contract-validation.md](backend-contract-validation.md)；
  90 项旧结果不能单独证明最终共享代码。此次通过独立源码复核与主 Agent
  最终执行记录承接，不回写历史结论。
- 本次先读取 status、根 AGENTS、本轮 spec/tasks/checklist；目标子树未发现
  额外 AGENTS。已列出本文件父目录。`rg` 不可用后使用 PowerShell，只做读取。
- HEAD 为 `0aca6ee2c9adf1aabeff85b0f028fae6d185612f` 加未提交工作树。
  文末九个目标文件复核前后哈希相同；这证明本次读取期间稳定，不冒称捕获了
  pytest 进程导入时的哈希或取得新 exact-SHA Hosted 结果。

## 逐项裁定

下表“满足”均指所述本机离线合同：独立检查实现与断言，执行结果归主 Agent。
行号对应本次文末快照；`cache tests` 指 `tests/test_agent_cache_admission.py`，
`stats tests` 指 `tests/test_statistics_tool.py`。

| Checklist | 裁定 | 代码与测试依据 |
| --- | --- | --- |
| 7 | 满足 | `agent_budget.py:90–105,239–245` 在 handler 前锁内预留工具额度，失败不退额；`agent_service.py:432–480,513–523` 为实际内联子图和父图安装同一类中间件。stats tests `322–354` 覆盖父/子 × 四调用面 × original/copy/with_config，实际文件 read 最多 12 次，子图因 task 扣额最多 11 次，全部 read 和 provider 共享同一 ledger。`373–398` 用三方 Barrier 证明父与双子在三个不同工作线程同时读取，共享主体和总账。预算 tests `251–290,293–330,368–388` 另覆盖模型第 9 次发送前拒绝、实际 SDK retry、并行 owner、锁竞争及摘要账本。不是仅根据最终消息数或配置文本判定。 |
| 8 | 满足；BCV-01 已补齐 | `tools/file_statistics.py:19–23,112–135` 为四 worker、提交前非阻塞槽位准入、实际 Future 完成释放槽位及异步等待。stats tests `464–635` 的九个生命周期组合现在等待完整 Future 和槽位 callback，终止后最终再次检查 0 成功 tool_end、0 cache、1 次模型请求、4 个槽位恢复，并有真实成功重试正控。`638–685` 另证明四个被取消但仍阻塞的 worker 占满容量，后续八次调用返回 analysis_busy，未新增读取。详见下一节时序；五秒解析期限不是同步读取硬抢占。 |
| 9 | 满足（应用生命周期） | `agent_service.py:245–294,302–372` 的同步私有 Context 与异步单 owned producer 保持退出归属，关闭等待清理，重复取消不打断 producer 清理；`agent_lease.py:438–485` 嵌套同主体复用 lease，真正持有者在 finally reset 后 release。stats tests `184–185,257–258,353–354,565–635` 检查正常/失败/关闭/取消/超时的 acquire/release 对、调用侧身份/预算清空、完整 worker 后无第二次释放，重试再有且仅有一对。不是实际 Redis key 删除证明。 |
| 18 | 满足 | `agent_service.py:57–62,392–414,607–620,647–655` 使用新 `agent:zero-tool-v1:` 命名空间，marker 或规范 UUID 请求跳过读写。cache tests `105–137` 预置新旧条目后检查不读取文件答案、不命中旧前缀且旧条目与搜索 sentinel 保留；MemoryCache 根本不提供清库 API。`140–181` 实际上传 CSV/JSON 后删除、过期、等长漂移，显式引用与隐式工具两路径都重新取得当前失败，不复用首次成功答案。 |
| 19 | 满足 | `agent_budget.py:113–177` 收集 graph-owned ledger，ContextVar 中的可变 collector 跨复制 Context/Task 保持，多个 scope 用 all 聚合而非最后一个覆盖。cache tests `184–206` 实际 task 子图/双子/内置 ls；`264–314` 同步 invoke/stream 在线程执行、astream 跨 Task，记录统计 worker 的线程/subject/ledger；`454–505` 并发 owner 和嵌套完整图隔离；`530–563` 在没有任何模型 tool 消息时，线程中经过真实工具中间件的统计调用仍阻止缓存。后者为显式构造的受控负控，不伪称自然模型选工具；自然父子/并行另由前述用例覆盖。 |
| 20 | 满足 | `agent_budget.py:47–77,124–128,158–177,219–245` 要求非空观察、模型已观察、正常 scope 完成、无工具/预算失败；任何不完整模型结果或异常只会否决，不会被后续 stop 恢复。`agent_service.py:260–268,318–324,417–429,645–655` 另否决配置/调用参数 interrupt、最终 interrupt、非完整 AI 答复。cache tests `71–81,317–369,372–451,508–527` 覆盖自述 cacheable 无效、无观察中间件、length/content_filter/缺失 finish_reason、静态 interrupt、实际预算拒绝、cancel/timeout 后完整 worker 及关闭真实流。concurrency tests `709–764` 用真实可缓存工厂进入阻塞 cache set，再检验 deadline/cancel，不再依赖不合格假图去命中写路径。 |
| 21 | 满足 | cache tests `84–102` 使用实际 factory 的 original/copy/with_config：双 owner 各执行一次，重复各命中，共两次 provider 请求、两个 key，命中也持有租约。tenant tests `95–145` 另提供不同 owner 的不同正文和同 owner 复用正控。cache tests `209–218` 验证模型/Base URL/温度隔离；`221–244` 证明搜索型答复不缓存，而独立搜索缓存成功时仍只请求提供方一次、失败不写。`search.py`、`cache_service.py`、`agent_lease.py` 无本轮工作树 diff。 |

## Task 7 的完整观察窗口

独立复核 stats tests 的实际时序如下，不再把读取结束当成 worker 结束：

1. `480–492` 先阻塞真实读取，再在真实统计 payload 已算出后第二次阻塞；
   此时 `_calculate` 仍未完成 DB 退出和成功外层封装。
2. `507–527` 捕获实际 `_submit` 返回的 concurrent Future。在真实槽位释放
   callback 之后注册完成事件，等待该事件，再在仍存活的 event loop 上
   `wrap_future` 取得完整结果，不以固定 sleep 或 fixture teardown 替代。
3. `549–574` 的 cancel/timeout 实际走 `AgentService.ainvoke`，且断言发生了
   cache lookup；终止时只剩三个可用槽位。close 分支走实际 graph stream，
   跨 Task 关闭后仍不提前释放正在计算的槽位。
4. `588–611` 取得完整成功 wrapper（精确值 0.3）之后检查只有一次 start、
   **零 tool_end、零 cache.aset 调用**、租约仍仅一对、槽位恢复四个、模型仍
   仅一次；流不能再取下一项，任务保留取消/超时状态。
5. `612–635` 重试实际 graph，观察器收到唯一真实成功 ToolMessage，新的 run ID
   与 ledger 不同；再次等待 worker，槽位仍为四个，最终恰好两对租约。
   这排除了只检查原本为空的 delivered 列表、或成功事件观察器未生效的假通过。

限定：这个九组合用例的重试走 graph，不是 REST HTTP；取消/超时首轮使用
REST 背后的真实 AgentService，缓存后端为 AsyncMock。另有 cache tests
`387–451` 在同一 AgentService 上完成取消/超时与重试，两轮均无答案缓存写入。
容量单例 `638–685` 仍以 fixture shutdown 等待残留 worker，且只检查租约总数；
不能把上述完整 Future/逐对租约断言误归给容量单例。完整终态证据来自九个
生命周期组合，容量证据来自另一个单例，两者共同支撑第 8 项。

## 真实性、角色与保守拒绝边界

- 零工具正控没有手工给假图结果塞入 `finish_reason=stop` 以绕过观察。
  `test_agent_aggregate_budget.py:150–201` 调用真实 `create_agent_graph`，
  使用真实 ChatOpenAI/HTTPX hooks；离线 provider 在标准 HTTP completion
  的 `choices.finish_reason` 返回 stop（`76–121`），由 SDK 生成 AIMessage
  metadata，再由真实模型中间件观察。测试自造带 stop 的 AIMessage 只用于
  unknown/missing observer 负控，仍被拒缓存。
- finish_reason 是 SDK 协议完成信号，不是可信的“无工具”声明。真实执行计数和
  scope 完成状态必须同时满足。length、content_filter、缺失/未知值保守拒绝，
  可能减少缓存收益；本次不验证实际提供方是否总返回预期字段。四种 graph
  调用面测试不等于已经证明所有提供方 token-SSE 格式都能取得缓存收益。
- tenant 进入 key，role 不进入 key，但 `AgentService.ainvoke:588–596`
  在 lookup 前授权；HTTP 入口依赖当前用户权限。工具则在 worker 新建 DB
  session、`db.get(User, subject)` 再交给文件服务授权（工具 `75–103`，
  文件服务 `513–520`）。stats tests `227–258` 覆盖 other/admin/deleted/角色
  变化；角色负控临时撤销 admin 文件权限，以检出旧角色读取，不代表生产策略
  禁止 admin 读取自己的文件。普通缓存正控不是重新验证整条 JWT/HTTP 链。
- 内联子 Agent 的 task 本身扣工具额度；嵌套完整图 scope 的合成测试
  `474–505` 是 collector 不丢证据的补充，不将两个独立完整图的不同账本
  冒称内联子图共用总账。传播保证针对现有受控 Task/复制 Context/线程路径，
  不推广到未受管的 detached 线程或未来绕开中间件的新工具。
- 本次未发现 backend-validation.md 正文与上述实现/断言存在实质归属错误。
  其“工具回调、完整 worker、槽位及重试正控”表述有源码支持；不可进一步
  改写成真实 Redis/HTTP 缓存事务、十个用例全部等待 callback，或本核验者
  重新独立执行了 958 项。取消网络请求也不等于已证明远端提交可被撤销。
- checklist 3 的澄清规则确已进入父/子 system prompt，但当前受控 provider
  按计划发工具调用，没有真实歧义输入澄清行为证据。真实模型不在本次授权，
  保持未验证，不用固定 provider 计划冒充模型理解/选择成功率。

## 稳定快照

下列 SHA-256 在本次源码复核前后两次读取一致：

| 文件 | SHA-256 |
| --- | --- |
| `data_agent/services/agent_budget.py` | `20798C99440F32BFDF0AA0AEF85C0FE0C7E7762E0A5B8CDB1816751A100F1E79` |
| `data_agent/services/agent_service.py` | `3A38C3DEE19B4D34FDE9A7B2813F3763C4901D779BBED85889D5AF31777191F8` |
| `data_agent/tools/file_statistics.py` | `97623FBE81E6DACBCE1DFAB5DA9BA5EAD9F82421E59AAA82D8BA72D3B7D57335` |
| `data_agent/tools/tool_manager.py` | `4DD634E631967F3C82222A074E70F595D5F5AB34B411F98593F2E67E5C781546` |
| `tests/test_agent_cache_admission.py` | `09AD2D4171533C21BFD23D1E5EC001B38730370CD8D53FB3C6C305EB1B472497` |
| `tests/test_statistics_tool.py` | `CDC2AE207ECD1DCD71EB3C5BF2BBE6556643BE67E4E3A4AB0DC24016770AD7A8` |
| `tests/test_agent_aggregate_budget.py` | `F821D49A637E6A0630101FC0462C266059B609D2C8231E1460B785510710AA02` |
| `tests/test_agent_concurrency.py` | `904D61F8195AB2579AC4772CD6A8A776D270DE507F6BAD7491C7536171746C9E` |
| `tests/test_agent_tenant_boundary.py` | `F7D8BEBBA51486745C5A8988A9D73D6F1C3BE1D9173422D31F7FD14837DF9D2C` |

本记录不修改 checklist；最终勾选由主 Agent 结合其执行证据完成。
浏览器、部署、Hosted、真实提供方效果和生产门禁不在本次裁定范围。
