# 真实聊天浏览器验收 Harness

2026-11-02。任务 5 harness **最终静止源码快照 full 已通过**；
执行标识 `d87023fefe42439ea45b733889185c52`，后端指纹前后一致。
本文件不修改 spec/tasks/checklist 的状态，不替代主 Agent 的整体验收记录。

## 范围与边界

- 入口：`scripts/verify_controlled_analysis_chat.py`、同名前端 `.mjs`、
  `verify_controlled_analysis_chat_network.cjs`。
- `prepare` 为默认模式：启动真实 FastAPI、已安装 LangGraph API 和 Next dev，
  浏览器注册、退出、登录、上传公开 CSV/JSON；不提交任何聊天统计请求。
- `full` 仅在主 Agent 通知就绪后运行：真实 `useStream` → 工厂图 →
  ChatOpenAI → loopback OpenAI JSON/SSE → 真实统计工具；提供方只从最新 user
  的 `__managed_file_v1__` 和显式 `column="..."` 选择两参工具。
  未收到同次实际 tool_call_id 的 ToolMessage 不得完成；不生成或伪造统计 data。
- 合成 CSV/JSON 的大数尾部在 20,000 字符之外，独立 Fraction 与整数十进制
  编码参考和为 `12345678901234568010.023456789012345678`。
  Python 独立重编码 canonical hash，对比实际 tool、REST、下载三份 payload。
- 身份使用真实注册、JWT、数据库角色与 API 授权；SQLite 文件、绝对受管根、
  随机 JWT secret、日志、前端源码副本和构建缓存都在外层 workspace 唯一临时目录。
- 租约只替换同步/异步 acquire 与 release 存储，保留真实 hold/hold_async；
  **不是真 Redis 容量或 Lua 证据**。默认模型/工具预算仍为 8/12。
- 明确区分真实 DELETE / 临时 SQLite 过期 / 受管字节漂移，与仅验证 UI 的
  网络失败、版本变化、401、延迟响应注入。历史卡片不得被抹除。
- 不使用 Compose、生产 `/data_copilot`、真实 `.env`、真实模型/搜索凭据。
  不提交、推送、生产部署，不主张 Hosted、容器、真实模型效果或生产放行。

## 启动入口

先加载 `run`，浏览器操作前加载 `TRAE-browseruse` 与 `ego-browser`。
本次 `ego-browser skill` 命令不存在，未安装或外联；复用已有 Playwright harness。
公共 run 配置不存在，
已读取 `run-skill-generator`；本轮仅拥有验收文件，不写 `.trae/environments/`。
命令 cwd 为仓库根。CLI 显式参数优先，也接受 `DDA_NODE`、`DDA_PNPM`、
`DDA_PLAYWRIGHT_MODULE`。默认端口前端 3317、REST 8317、graph 2317；
启动前 bind 检查，不抢占或停止既有实例。

```powershell
& 'D:\Code\.dda-recovery-admission-20261028\venv\Scripts\python.exe' -I -B scripts/verify_controlled_analysis_chat.py --mode full --node 'C:\Users\34226\AppData\Local\npm-cache\_npx\ad5ebc7ce5bb5eba\node_modules\node\bin\node.exe' --pnpm 'C:\Users\34226\AppData\Local\npm-cache\_npx\ad5ebc7ce5bb5eba\node_modules\pnpm\bin\pnpm.cjs' --playwright 'D:\Code\project_rich_snowball\frontend\node_modules\playwright-core\index.mjs'
```

`--self-test` 不需 Node 参数；`--preflight-only` 只检查隔离前端 CLI，
不启动 API/浏览器。`--headed` 可显示 Chromium；默认无头行为验证不算用户可见窗口。
以上是本次获准的 full 命令；仅准备时改为 `--mode prepare`。
每次重新读取当时源码，不沿用准备结果。

本机指定 Node 22.22.2 / pnpm 10.5.1。Playwright-core 路径为本机复用的路径，
1.60.0 / Chromium 缓存 1223，实际运行版本写入 JSON；CI 版本如不同必须明示。

## 当前实际证据

- 已先 ls 父目录、status、AGENTS、spec/tasks/checklist，并读取 baseline.md。
  既有与并行业务文件不改写；任务 1 的 50 passed 为独立前置记录，不混算。
- `--self-test` exit 0：Fraction 参考、尾部位置、最新 user 选择与缺失 tool
  结果拒绝通过。不是业务聊天证据。`node --check` 首版入口 exit 0。
- 历史两次准备启动都已使真实 FastAPI liveness 与 LangGraph API 就绪，但前端
  未启动，当时没有注册、上传或任何浏览器成功记录。
  实际依赖：langgraph-api 0.16.8、langgraph 1.2.18、
  langchain-openai 1.7.3、FastAPI 0.162.0。
- 启动失败根因：命令沙箱创建 junction 时将目标改写为内部 device 路径，
  临时前端读不到 node_modules，报 `'next' is not recognized`。
  普通相对目录符号链接另报 WinError 1314，无权限。没有改 ACL/申请管理员。
- 改为子进程标准 PATH/NODE_PATH 复用原依赖；隔离副本
  `pnpm dev --help` 已 exit 0（执行标识 `07573be115b4024699b66095c2ac8422`）。
  后续 full 已验证实际 Next 编译、浏览器和清理。
- 上述准备失败的 API/前端子进程及本任务临时目录已清理；未停止其他任务资源。
- 主 Agent 已授权直接 full 联调，不需 prepare；任务 2 定向 169 tests 与前端
  120 tests 为其他 Agent 报告，本 harness 不混算。任务 3 的 REST 答案缓存
  并行修改不阻塞主聊天；每轮记录前端副本、后端源码聚合 SHA-256 与后端变化标志。
- 现有 next.config.mjs 不读取 NEXT_BUILD_DIR。本 harness 使用外层独立副本
  和独立 `.next`，不占用仓库 `.next`，不阻塞前端四门禁。
- 首轮 full（执行标识 `030881cf5f7cf3d36d1d6311b59f8065`）真实 API / Next
  启动，浏览器注册、退出、登录、CSV 上传及实际统计工具成功，模型请求 2 次，
  acquire/release 各 1、active 0、外网尝试 0。随后 harness 断言失败，
  尚未证明卡片、REST 和下载一致；不得记为最终成功。
  Playwright 1.60.0、Chromium 148.0.7778.96。开发页既有 logo 请求
  `/data_copilot/logo.png` 返回 404，未改生产资源路径。

## Full 联调结果

- 第二次 full `43561d7eeeb3d26923e8b19fd30a95b1` 保留失败：
  `readTool` 把仅用于受管文件的 UUID v1–5 限制误用到线程 ID。
  已安装 LangGraph 为该运行路径建立 UUIDv7 线程；harness 分离线程/文件校验，
  没有改生产 UUID 规则。该次后端源码指纹前后不同，不作为静止快照证据。
- 通过执行：`2aaa3fa64bd7ce754ed51f649f1889ad`，`--mode full` exit 0。
  6 次真实聊天（5 份主样本、第二 owner 的 1 份认证控制样本）均成功，
  loopback 提供方收到 12 次真实 SDK 请求、6 次实际统计结果，未计算或伪造数据。
- 五份样本均在 UI 上传、聊天调用真实工具；同主体 REST、实际下载与 ToolMessage
  payload 完全一致，Python 独立 Fraction 数值和 canonical SHA-256 校验通过。
  CSV 55,292 bytes、JSON 86,505 bytes，大数尾部均在 20k 字符外；共 1,201 行、
  1,200 有效值、1 缺失、1 重复。和为 `12345678901234568010.023456789012345678`。
- 页面：精确长数值、来源、警告、单位、隐藏工具详情、键盘展开/下载和 390px
  下载按钮布局通过；刷新、新线程、历史深链接恢复后每次只有 1 张真实卡片。
  这是正常流及恢复观察，不是人为重复 SSE/工具消息注入的去重压力测试。
- 7 次成功下载；固定 REST Origin、JWT 与请求 ID、受控下载文件名和 Blob
  释放通过。未发现浏览器外部目标请求或 JWT 发往其他 Origin。
- 真实生命周期：DELETE 后 404，临时 SQLite 过期后 404，受管字节等长漂移后
  503 / `file_storage_invalid`；均无新下载，历史卡片与“计算时快照”标记保留。
- 明确标记的 UI 响应注入：网络 abort 后手动重试使用真实 REST 并成功；
  真实 REST 响应修改版本后拒绝；延迟真实响应期间禁重，切线程与登出观测到
  AbortSignal，导航卸载使响应脱离旧页面，均无迟到下载；注入 401 走正常退出。
- 记录型租约 acquire/release 为 6/6，active 0；后端外网尝试 0、提供方错误 0。
  不是 Redis 容量、故障恢复或取消/timeout 的验证。
- 该次前端副本 85 个源码/配置文件聚合 SHA-256：
  `66517386b690848e4a6fe0d42d7e458a3bd7b7f6aa82ec1a555f6ddf9e1c9799`。
  后端运行前 41 个 Python 文件聚合 SHA-256：
  `17585f863964751f4173e68c4cd44c03c8e4df01a9a7bf8c29f2a76ba9da9ca0`。
  **backend_unchanged_during_run=false**，任务 3 并行修改中；本次是通过的联调，
  不冒充最终 exact snapshot。聚合规则为相对路径 → 文件 SHA-256 的排序 JSON 再 SHA-256。
- 本次己有进程、浏览器和临时目录已清理；仓库 `.next` 从未被本 harness 占用。
- 收尾检查：harness `--self-test`、`isort --check-only`、两个入口的
  `node --check`、Prettier check 均通过。四个未跟踪所有权文件另以
  `git diff --no-index --check NUL <file>` 检查，无空白错误；
  no-index 的差异退出码 1 不代表空白失败，未用普通 diff 的空输出冒充检查。
  独立 TCP 查询显示 3317/8317/2317 无监听，临时目录枚举为空。

## 最终冻结快照

- 命令执行 ID：`83b52625350e5f3e9f43430bc2f835f9`，exit 0。
  Harness execution_id：`d87023fefe42439ea45b733889185c52`。
  UTC：`2026-11-02T17:48:24.902482+00:00` 至
  `2026-11-02T17:49:32.145218+00:00`。
- `outcome=passed`、`browser_exit_code=0`、
  `statistics=real_tool_rest_download_fraction_reference_passed`、
  **`backend_unchanged_during_run=true`**、`owned_resources_cleaned=true`。
  后端变化现在是强制失败条件，不再只记录标志。
- 后端 41 个 Python 文件聚合 SHA-256：
  `5f51ddeadf427f858de9de41b8812677ba6d54e1a9428913eb2fa0014abe9779`。
  前端 85 个源码/配置文件聚合 SHA-256：
  `66517386b690848e4a6fe0d42d7e458a3bd7b7f6aa82ec1a555f6ddf9e1c9799`。
  聚合口径同上；前端运行的是该独立副本，后端是本次静止工作树，不是提交 SHA。
- 运行版本：Node 22.22.2、pnpm 10.5.1、Playwright 1.60.0、
  Chromium 148.0.7778.96、langgraph-api 0.16.8、langgraph 1.2.18、
  langchain-openai 1.7.3、FastAPI 0.162.0。
- **8 个真实聊天回合、14 次真实 SDK 请求、6 次成功统计工具结果、7 次下载**。
  8 次为 2 个澄清回合和 6 个统计回合；六次统计包含五份主样本及第二 owner 控制样本。
  提供方请求、issued/completed、租约断言分别更新为 14、6/6、8/8，
  不再误用历史 12 次 SDK / 6 个总回合。
- 五份主样本仍全部执行 UI 上传、真实聊天、同主体 REST 与真实下载比对，
  独立 Fraction 数值与 canonical SHA-256 均通过。目标列 `amount`、
  指标 `sum`，和 `12345678901234568010.023456789012345678`；
  总行数 1201、有效 1200、缺失 1、重复 1；最小值 `0.1`，
  最大值 `12345678901234567890.123456789012345678`。
  CSV/JSON 大数尾部在 20k 之外，大小仍为 55,292 / 86,505 bytes。
- 校验字段含 `source.file_id/sha256/size_bytes`、`parameters`、`result`、
  `row_count`、`duplicate_row_count`、`warnings`、`summary`、
  `parser_version=strict-table-v1`、`analysis_version=column-sum-v1`、
  `result_sha256`。CSV / JSON 本次结果 SHA 分别为
  `33bfe9aa9cfa58c28ab9e69a134195644748711298b5916983cececeaf7de0e8` /
  `63ced004a96e3373c672e6c9745eb0e7d70888966a81ca2250160bec47a5fcb3`；
  结果 hash 包含本次来源 UUID，不应当作跨运行固定值。
- 卡片精确长数值、逐项行数/警告、固定说明与来源、单位、隐藏工具详情、
  键盘展开/下载、390px 下载按钮布局，以及刷新/新线程/历史深链接全部重验通过。
  固定 REST Origin、JWT/请求 ID、受控下载名和 Blob 释放通过。
- 原有失败场景全部保留并通过：真实 DELETE 后 404、临时 SQLite 过期后 404、
  等长字节漂移后 503 / `file_storage_invalid`，均不下载并保留历史快照；
  网络 abort 后手动重试成功、版本响应注入拒绝、延迟下载禁重、
  切线程/登出 AbortSignal、导航卸载及无迟到下载、401 注入退出。
- 租约 acquire/release 8/8、active 0；后端外网尝试 0、提供方错误 0、
  浏览器 externalAttempts/foreignAuth 0/0，浏览器进程错误类型/位置为空。

## 两个澄清回合

真实 UI 上传和提交后，既核对页面澄清文本，也读取实际 LangGraph run/state：
每例 `runStatus=success`、`toolCalls=0`、`toolMessages=0`、`cards=0`。
随后在**同一线程**用输入框显式提交此前真实上传的唯一受管 UUID 和
`column="amount"`，取得唯一真实工具结果、卡片与一致下载。
这是显式引用语法的受控协议/UI 验收，**不代表自然语言真实模型效果**，
也不声称验证了已有附件选择器或只补列名的跨回合模型推断。

| 场景           | 实际输入与提供方观察                       | 澄清 run_id                            | 后续真实 tool_call_id                   |
| -------------- | ------------------------------------------ | -------------------------------------- | --------------------------------------- |
| 缺列名         | 1 个附件引用、0 个显式列名                 | `01a19d61-0225-74b6-9fd9-74b9a91d2813` | `call_b309789be748409c914ac006a2c820e4` |
| 多附件未选文件 | JSON 与独立 CSV 两个附件引用、1 个显式列名 | `01a19d61-23b7-76f9-9b14-43a3a0435c8b` | `call_cc19080dcf0d4397a1df297a97a442fb` |

多附件负控使用独立公开 `public-unselected.csv`，不修改五份原有主样本。
提供方只选择工具，不计算或伪造统计 payload。澄清及显式后续也纳入 self-test。

## 本次失败与收尾

- 失败执行 `56528f97a65acf04ba9ebf30e5c57fc3` /
  `41c4183ed489496ab9eb034283cec8c4`：缺列澄清成功，1 SDK、0 工具，
  随后 harness 错误地期望同 owner 同内容重新上传返回 201。
  产品约定为 `duplicate_file` / 409；修正为输入框显式引用已有真实 UUID，
  多附件额外样本独立生成，未放宽产品重复上传策略。
- 失败执行 `dd8df42781bfbe402de056494dd08ad1` /
  `d6d2e55b603b4078ace58d0b665a98b4`：3 SDK、1 个成功工具结果，
  后续浏览器进程无最终 JSON，`browser_no_report`，整轮失败。
  原脚本丢弃 stderr，**不能确定该次退出根因**；补充脱敏错误类型/源码位置，
  未处理 Promise rejection 与关闭异常均使门禁失败并保留报告。
  输出精简包装遇到无 statistics 字段的异常也已加存在性判断。
- 两次失败均 `backend_unchanged_during_run=true`，均清理本次资源；
  不将失败追认为通过。其后上述最终完整运行通过，未删减原有场景。
- 最终仅修改自有 `.py`、`.mjs` 和本文档；`.cjs` 复用且校验，
  不改产品、spec/tasks/checklist 或主 Agent 文档。
  临时目录继续使用外层 workspace 唯一前缀，未更改全局 TEMP 设置，
  不占用仓库 `.next`。己有进程及临时目录枚举为空。
- 最终 harness self-test、仅自有 Python 的 isort、两个 Node 入口语法检查、
  自有 JS/CJS 与本文档 Prettier check、四个文件逐项 no-index 空白检查通过。
  未跟踪文件用 `git diff --no-index --check NUL <file>`，不以普通 diff 空输出代替。
- 清理后独立 TCP bind 实测 3317/8317/2317 全部可用
  （执行 ID `11919260afcdf1f44387230a0015e18b`）。
  TCP 枚举曾显示 2317 / PID 0，未据此终止任何进程；以三端口实际 bind 及己有进程
  枚举为空作为资源释放证据。工作树后来出现的 `deep_data_agent.log.1` 不属于本任务，
  未读取或删除。

主 Agent 已另行报告全后端 `958 passed in 99.04s`、10 个慢 worker 补测、
isort、runtime 134、Alembic head、发布扫描，以及前端 120 与四门禁通过；
这些不是本浏览器任务重新执行结果，不混计。
服务取消/timeout、父子/并行预算、工具失败及缓存准入以其专门记录为准。
本次无真实 `.env`、真实模型/外联、提交、推送或部署，仍不证明 Redis、
Hosted、生产容器或真实模型效果；保留正常流去重观察与压力测试的区别。
