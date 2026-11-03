# 前端独立验证

2026-11-02。范围：已批准的任务 4，checklist 10–17、22–23，以及 25 的前端门禁。
本文件只记录本次独立执行，不替代浏览器 Agent、后端验证或主 Agent 的最终验收。

## 结论

- **独立重跑 120/120 测试通过**，失败、取消、跳过、TODO 均为 0。
- **前端四门禁通过**：typecheck、lint（0 warning）、format:check、build 均 exit 0。
  实际 Node **22.22.2**、pnpm **10.5.1**。typecheck 使用
  `--incremental false`，仅禁止改写原有增量缓存，不关闭任何类型检查。
- 未发现可以复现并据以提出修复任务的实质性产品偏离。未知字段在各层被严格拒绝，
  **没有静默裁剪 canonical payload 的问题**；不以测试数量推断全部浏览器行为通过。
- 另完成 18 项 parser/关联/编码探针、10 项真实 Node loopback HTTP 重定向负控、
  4 项实际提交处理函数探针。它们**不计入 120 项**，也不计为浏览器测试。
- checklist 12、13、16、17 的完整页面行为仍需浏览器实证；本记录不能单独使这些项
  或 checklist 24、25 整体勾选。特别是 Blob **实际保存交付**、键盘、窄屏、刷新、
  切线程与登出时的真实组件清理，本次没有声称完成。

## 基线与控制条件

仓库 `D:\Code\deep_data_agent\deep_data_agent`，
HEAD `0aca6ee2c9adf1aabeff85b0f028fae6d185612f` 加未提交改动。
先执行 `git status --short`，读取 AGENTS、本轮 spec/tasks/checklist/baseline；
任务 4 起始已勾选，checklist 尚待独立验证。首个 status 执行标识
`3ca5c578480c9a18f0c75c2e640eeef5`。

起始已有改动：roadmap、README、CHANGELOG、前端 package.json/Thread/AssistantMessage/
api-key/ensure-tool-responses/managed-file-client，以及后端路由、文件服务、AgentService、
工具管理与预算测试；新统计模块、测试、两个 spec 目录与浏览器 harness 均已存在。
本任务未编辑这些文件，没有安装依赖、读取真实 `.env`、使用真实服务 key、
调用真实模型、提交、推送或部署。

测试前设置公开 loopback 配置与 `NEXT_TELEMETRY_DISABLED=1`。原测试 runner
`agent_chatui/tests/run.mjs:26-30` 将 REST 地址编译为
`https://statistics.example.test/rest`，HTTP 用例全部替换 `globalThis.fetch`，
不会访问该域名；本次附加的真实 HTTP 探针只访问临时 `127.0.0.1` 端口。
前端目录不存在 `.env*`，build 命令在启动前仅检查文件名，发现此类文件即拒绝执行。
Next 的项目目录是 `agent_chatui`，未以仓库根的真实 `.env` 启动。

build 前已在对话中提出协调请求；收到主 Agent 的执行协调答复：
“harness 使用外层 workspace 独立前端源码副本/.next，可以直接在 repo 前端跑完整 build”。
其后执行 build；未修改 `next.config.mjs`，未停止其他进程。清理前再次核对
`scripts/verify_controlled_analysis_chat.py:603-605,612-614,673-674`，
harness 仍复制前端、排除 `.next/out/.env*`，以副本为 cwd。

本机实际依赖版本（读取已安装 package.json，不是 package.json 的范围推测）：

| 组件 | 版本 |
| --- | --- |
| Node / pnpm | 22.22.2 / 10.5.1 |
| Next / TypeScript | 15.3.2 / 5.7.3 |
| ESLint / Prettier | 9.27.0 / 3.5.3 |
| esbuild / Zod | 0.25.4 / 4.1.12 |
| React / React DOM | 19.1.0 / 19.1.0 |

## 门禁命令与结果

PowerShell 5，cwd 固定为
`D:\Code\deep_data_agent\deep_data_agent\agent_chatui`。
每次命令重新设置 PATH 和公开环境，不依赖跨工具调用的变量保存。
以下把重复前缀合并展示；不是使用默认 Node/pnpm 得到的结果。

```powershell
$node = 'C:\Users\34226\AppData\Local\npm-cache\_npx\ad5ebc7ce5bb5eba\node_modules\node\bin\node.exe'
$pnpm = 'C:\Users\34226\AppData\Local\npm-cache\_npx\ad5ebc7ce5bb5eba\node_modules\pnpm\bin\pnpm.cjs'
$env:PATH = (Split-Path $node) + ';' + $env:PATH
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:NEXT_PUBLIC_REST_API_URL = 'http://127.0.0.1:8317'
$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:2317'
& $node --version
& $node $pnpm --version
& $node $pnpm test
& $node $pnpm typecheck --incremental false
& $node $pnpm lint
& $node $pnpm format:check
```

build 另设置 `NEXT_PUBLIC_ASSISTANT_ID=data_agent`；它是公开构建值，不是模型、
真实 graph 或该 assistant 可用性的验证。

```powershell
$env:NEXT_PUBLIC_ASSISTANT_ID = 'data_agent'
$dotenv = @(Get-ChildItem -Force -File -Filter '.env*')
if ($dotenv.Count -gt 0) { throw 'Frontend dotenv file exists; refusing automatic dotenv read' }
if ((Test-Path '.next') -or (Test-Path 'out')) {
  throw 'Build output already exists; ownership needs coordination'
}
& $node $pnpm build
```

| 实际命令 | 结果 | 执行标识 |
| --- | --- | --- |
| `pnpm test` | exit 0；120 pass，0 fail/cancelled/skipped/todo；TAP duration 665.6463 ms | `81cf556cb7bf8ff75fdaff696dc4a546` |
| `pnpm typecheck --incremental false` | exit 0；`tsc --noEmit "--incremental" "false"` | `60a5872f538d12f64dfdb2b6f9db28f2` |
| `pnpm lint` | exit 0；`eslint . --max-warnings=0`，0 warning | `edc2e8db5a769979363dc30dc6c0c59c` |
| `pnpm format:check` | exit 0；All matched files use Prettier code style | `fc55dd6ea3c7bd46ee9505ff30009971` |
| `pnpm build` | exit 0；compiled in 88s；静态页 7/7，export 3/3 | `4018c9ac4b2e8d0027db67e05d4f063f` |
| `git diff --check -- agent_chatui`（仓库根） | exit 0；只有已有 LF/CRLF 提示 | `d96d6948d21013712140895261e0fa9b` |

build 原始提示必须保留：

```text
No build cache found. Please configure build caching for faster rebuilds.
The Next.js plugin was not detected in your ESLint configuration.
```

第二条是 Next build 的插件检测提示，不是本次独立 ESLint 命令产生的警告。
现有 `eslint.config.js` 以动态 require 注册 `@next` 并启用 recommended/
core-web-vitals；本任务没有为消除提示修改配置，也没有把 build 描述成“零提示”。
产物路由 `/`、`/_not-found`、`/login`、`/test-chart`；
首页 537 kB、First Load JS 663 kB 是构建统计，不代表性能浏览器验收。
build ID `CCgJr0BBjSPcuIbBCzkh-`。

## 逐项证据

以下 lib 短名位于 `agent_chatui/src/lib/`；卡片、`messages/ai.tsx` 位于
`agent_chatui/src/components/thread/messages/`；Thread 位于
`agent_chatui/src/components/thread/index.tsx`。T 表示
`agent_chatui/tests/statistics.test.ts` 的实际执行测试，不表示源码字符串匹配。

| 验收项 | 独立核验与位置 | 裁定/剩余边界 |
| --- | --- | --- |
| 10 | `statistics-result.ts:129-186` 校验包裹、SDK status 和两参；`statistics-messages.ts:15-75` 仅匹配先前实际 AI 调用与非合成 tool，要求消息 ID，拒绝歧义复用 call ID。T:287-344,401-415；附加 6 种 args 负控 | Node 行为通过；普通 AI JSON、synthetic、损坏/空 JSON、块数组、未知版本、SDK error 不生成成功卡片 |
| 11 | `statistics-result.ts:4-108` 保留十进制字符串，校验各计数、列、警告及固定 summary；`statistics-card.tsx:53-89,129-149` 直接显示同一 data。T:95-285 | 完整固件深相等、已知 Python ASCII canonical hash、精度与 SSR 文本通过；不代表真实聊天/REST 数值三方联调 |
| 12 | `statistics-messages.ts:18-26,60-71` 按 message/call 身份最新值替换、稳定位置；T:346-370,418-431。`messages/ai.tsx:148-158` 的业务卡片不受 hideToolCalls 隐藏；`thread/index.tsx:421-437` key 包含 threadId | 纯函数去重通过；hideToolCalls 接线、thread key 仅源码确认；刷新、真实流式更新和切回旧线程仍待浏览器 |
| 13 | 卡片按钮为现有 Button，来源 aria-expanded/controls、错误 role=status、换行样式；T:222-285,329-344 执行 SSR 与转义断言；`ui/button-variants.ts:4` 有焦点/禁用样式 | SSR 安全文本通过；键盘焦点、实际禁用、390px 排版、完整长数可取得性不能由 SSR 或 class 名判定 |
| 14 | `managed-file-client.ts:51-54,86-125,192-201` 固定配置地址、UUID 路径、列名 body、JWT/request ID、redirect:error；T:460-523。附加真实 HTTP 同源/跨端口 301/302/303/307/308 共 10 负控 | Node HTTP 通过；目标端 0 请求，初始请求 10 个独立 request ID。不是浏览器 CORS/JWT 验证 |
| 15 | `managed-file-client.ts:184-250` 重验结构、版本并比较完整 data；`statistics-result.ts:111-118` 比较严格 schema 重排后的对象；T:525-619 | UUID、SHA、size、参数、版本、result hash、数值字段变动均拒绝；完整相等而非只比较 hash。未知字段被拒绝，不裁剪；前端按设计不重算 Python hash |
| 16 | T:562-606,621-664 对变化及 404/503 做 HTTP 替身负控；`statistics-download.ts:12-24` 映射安全文案；卡片固定“计算时快照”，下载控制器不替换原 data | 失败/变化行为通过；404 不区分删除、过期、越权。**替身状态码不是实际文件删除/过期/漂移证据**，历史页面保留仍待浏览器 |
| 17 | `statistics-download.ts:65-107` 禁重、current 身份、cancel/dispose、finally abort；`managed-file-client.ts:120-123,205-220` 迟到认证/解码检查；`statistics-card.tsx:28-39` layout effect 清理和 token 事件。T:666-876 | 控制器、认证事件、迟到响应、网络重试、Blob 内容与清理替身通过；真实组件卸载/线程切换以及 Blob **实际交付**仍待浏览器 |
| 22 | `ensure-tool-responses.ts:15-44` 按每次调用 ID 查后续结果，只返回缺失 error，原消息不改；T:372-399,434-445 | 乱序、部分、无关/先前结果、真实 error、幂等补齐通过；文案为“没有取得工具结果”，不是成功或臆测取消 |
| 23 | `ensure-tool-responses.ts:21-24` 拒绝 undefined/空白 ID，T:447-458；`thread/index.tsx:198-251` 在构造/提交/清空前返回；附加 AST 提交函数 4 例 | 三个缺 ID 例均 0 submit、0 清附件、输入保留且有提示；正常 ID 对照可 submit/清空。是实际函数执行，不是 React 挂载/用户事件测试 |
| 25 前端 | 上述四门禁、前端差异检查 | 本机前端部分通过。全后端、发布契约、迁移、公共文档与 Hosted/部署不由本任务证明 |

### 120 项测试究竟验证什么

- `tests/run.mjs` 用已有 esbuild 将实际 TypeScript 模块及测试打包，随后执行
  `node --test --test-concurrency=1`，finally 删除独立 `.dda-chat-behavior-*` 目录。
  测试并非依赖源码文本是否出现某个字符串来判断产品逻辑。
- T:95-118 使用已知 34 字节公开 CSV 的固件验证 canonical/hash；不是运行 Python
  服务。其排序覆盖当前 schema 的固定键，不能外推为任意 JSON 的 canonical 实现。
- T:222-285 的精度/转义来自 `renderToStaticMarkup`，没有浏览器布局或 hook effect。
  改 value 的固件沿用原 hash，是专门检查显示编码，不是合法新后端结果的 hash 证明。
- T:346-370 的两次纯函数调用不是页面刷新。hideToolCalls 与 Thread 提交处理函数
  没有被原 120 项挂载执行；后者由本次隔离函数探针补足部分行为证据。
- T:729-768 中名为 `thread-change`、`unmount` 的例子实际直接调用 controller.dispose；
  logout/identity-change 使用测试 EventTarget，并由测试自己绑定 cancel。
  它们不能证明 React effect 和真实路由切换已经触发这些操作。
- T:835-875 使用真实 Blob 和 `blob.text()`，但 document、anchor click、ObjectURL API
  被替换。它能检查文件名、字节、remove/revoke，包括 click 抛错；**不能证明浏览器已保存
  文件**，也不能证明真实浏览器对同步 revoke 时序的处理。
- T:562-606 的版本/字段变体没有重新签算合法 hash，证明前端拒绝变化的分支；
  “真实合法另一版本”及工具/REST/下载 canonical 三份一致仍由联调负责。

## 附加独立探针

所有探针用指定 Node 的 `--input-type=module -` 从 PowerShell here-string 执行；
esbuild `write:false`，Module 编译仅在内存，没有新增产品/测试源文件。
附录保留可重放代码。不是新加入 pnpm test 的长期回归。

| 探针 | 实际结果 | 执行标识 |
| --- | --- | --- |
| Parser/关联 | data、parameters、source、result、columns[0] 共 5 层额外字段拒绝；6 个错误 args 拒绝；对象键反序后相等；6 个 decimal/hash/UUID 尾随换行负控均拒绝且成功卡片数 0 | `65b31b43d8ee24259434e12238fac528` |
| 真实 HTTP 重定向 | 两个临时 loopback server；同源及跨端口各 5 种重定向全部拒绝；10 个初始认证请求、10 个 request ID、目标收到 0 次；finally 已关闭两服务 | `ab5ec3c4d89a5525ae50fa40369078fd` |
| 提交处理函数 | TypeScript AST 提取实际 handleSubmit，注入其闭包依赖执行；undefined/空串/空白三个 ID 未发送未清空；有效 ID 正向对照正常发送/清空 | `09c49cc5ce216034ef3de2f68d813a9d` |

HTTP 探针的 Authorization 值是公开测试占位串，只验证 header 的附带及不转发，
不是签名 JWT 的认证/授权验证。

## 失败、提示与未验证

没有 pnpm test 或四门禁失败；没有用反复重跑掩盖失败。以下辅助失败如实保留：

1. `rg --files ...` exit 1，系统没有 rg；改用 git/PowerShell。
2. 初始尝试读取 `D:\user_profile.md` 等不存在的记忆/父级路径，exit 1；
   后续只读实际 `.trae-cn/memory` 的项目记忆，当前 AGENTS/用户授权优先于旧记忆。
3. 读取误猜的 `agent_chatui/src/config.ts` exit 1；实际配置为 `src/config/index.ts`，
   后续已核对。不是应用导入失败。
4. 第一版内存 parser 探针未使用 `String.raw`，换行被外层模板提前解释，
   esbuild 报 `Unterminated string literal`，exit 1，
   执行标识 `923d90ccf943b2aa811da3514f2927e6`。只修正探针转义后重跑成功，
   未修改产品 parser，也未将此编译失败计为产品 bug。
5. build 两条提示及 Git 既有 LF/CRLF 提示见前节；没有改配置/格式消除提示。

没有启动或使用浏览器，没有实际注册、上传、聊天、刷新、切线程或落盘下载。
没有运行整个后端、发布契约扫描、迁移、真实 MySQL/Redis、容器、Hosted、
真实模型效果或生产门禁。本文件的通过范围不包含上述项目。

## 工作树保护与清理

前后 SHA-256 比对 19 个保护路径，**18/19 相同**，其中全部 13 个目标前端源码/
测试/manifest 路径和原有 `tsconfig.tsbuildinfo`、`next-env.d.ts` 保持不变。
唯一变化为并行主 Agent 的 tasks.md：任务 2 从未勾选变为已勾选。
已重新读取确认，没有回滚它；本任务从未写 tasks/checklist/公共文档。
保护比对执行标识 `95c9ab6196dacc8dd7527691c8836565`。

| 路径（相对仓库） | 验证时 SHA-256 |
| --- | --- |
| `AGENTS.md` | `3651DAE991B19DEE2EEBC1449EF5E0C8DC3F0A786F18E1872AB04B730CD3CE57` |
| 本轮 `spec.md` | `059D966DAC62F21CDF10277521C2F5A82EFB8C793BAC062CFA84857843441DAF` |
| 本轮 `checklist.md` | `ECC023D0BE9D55CDDFCE11A10E9432FA6105665363B4C3632FE2E9325D7E42A1` |
| 本轮 `tasks.md` 起始 | `1904D2AE4CA62CFB0AA6EE1EEA6871295C1BF84F76D3DF085B720FA4F664DDFB` |
| 本轮 `tasks.md` 并行更新后 | `E6249C2132556F083D5D2050E5F50295463843E69CD01FE27A07BC77D2C5158D` |
| `agent_chatui/package.json` | `A364C0F54ADE3A7CCA8EF5F1770F41A02377CB12D4604410D99C59075B138A95` |
| `agent_chatui/src/lib/api-key.ts` | `4F741D61A09F665D5DF16553AECF19D424464EBCAAD1F3431BB132EF382A7D88` |
| `agent_chatui/src/lib/ensure-tool-responses.ts` | `1EE5A98695D483A6532F00A1DBD9207072CACD885B8295C33E010D82216BC71E` |
| `agent_chatui/src/lib/managed-file-client.ts` | `C14BE2B6C9387F15246471A539DF3EE5E7CC8A245F654C5EDA7EC4F51262E17F` |
| `agent_chatui/src/lib/statistics-download.ts` | `3927D9882B0000E1263A1DEE35219C28FD6401115267A29795CFCD9B80994850` |
| `agent_chatui/src/lib/statistics-messages.ts` | `B274A5B6817D0FFA3F1AB8E806D9C298D62188CD6FCCABD9325124702FD7FD95` |
| `agent_chatui/src/lib/statistics-result.ts` | `D78F7675EDA9C391744E3BD800BE866C8FCBF41A043A801E5F7C14AB99405DDA` |
| `agent_chatui/src/components/thread/index.tsx` | `D61339CB210BB13D22821BB6F6F061E7E27BD492D97C486C64BD07ADD4BED41C` |
| `agent_chatui/src/components/thread/messages/ai.tsx` | `1FC787B0B6309A5C66A88ACBBC48283DF79730CD36CCFF22D59CCD67FBBD8A3C` |
| `agent_chatui/src/components/thread/messages/statistics-card.tsx` | `12EBDE7224E6C62EB988506F7E9B733A674444CEB2BD324E46C118EE4048A4B8` |
| `agent_chatui/tests/run.mjs` | `042FE3022F58C7CA01CF2D134B77E4FC32863C323F613102F2A8C765CAED0959` |
| `agent_chatui/tests/statistics-fixture.ts` | `84C34A5CE02D3009E47988549F3DAEC87D418417F26535F7E498AADDF0F1D5CF` |
| `agent_chatui/tests/statistics.test.ts` | `B49DC9FD31D199D58D5F1EFD62762226ECC8B9DA83D87163A3C1EF0C124AC326` |
| `agent_chatui/tsconfig.tsbuildinfo` | `3211BE8B48A39A06C35E2B07C1E7D9B32A12B1307D4D1F208D2DAB7847F8D2DD` |
| `agent_chatui/next-env.d.ts` | `9A964C445118D72402F630B029A9F48CB1B5682C49DF14EC08E66513096929EC` |

13 个目标前端路径包括 package、6 个 lib、3 个组件、3 个测试；连同 2 个原有
缓存/声明文件及 AGENTS/spec/checklist，共 18 个保持不变。这不是整个并行工作树
的全文件哈希证明。

build 启动前 `.next/out` 均不存在。清理时验证 `.next/BUILD_ID` 与本次结果一致，
并拒绝 reparse point，然后仅删除这两个确切路径。执行标识
`dd4f7e738c944154662635e750ddd980`，exit 0：

```text
.next exists=False
out exists=False
PRESERVED node_modules exists=True
PRESERVED .tmp exists=True
PRESERVED tsconfig.tsbuildinfo exists=True
PRESERVED next-env.d.ts exists=True
```

测试 runner 的 `.dda-chat-behavior-*` 目录最终列表为空（执行标识
`b7dff096c2131a0c77afe3bcc9feb4a7`）。没有删除其他 Agent 的工作目录、venv 或依赖。
并行后端新增 agent_budget、并发/租户/缓存测试等改动均保留，不声称其 status 不变。
本任务唯一保留的手工写入产物为本文件。

最终 `git status --short`（`05084ff562b12a94730084659f029c69`）中已无 `out`。
`git diff --exit-code -- agent_chatui/next.config.mjs agent_chatui/next-env.d.ts
agent_chatui/tsconfig.json agent_chatui/pnpm-lock.yaml` exit 0，无差异
（`e5cdc2caf65dade6f0249248ed16196d`）。
对新增报告执行
`git diff --no-index --check -- /dev/null .trae/specs/integrate-controlled-analysis-chat/frontend-validation.md`，
exit 1，只有 LF/CRLF 提示，没有 whitespace error
（`6a75e336d6080df78cb7f7a371c71f26`）；no-index 的 1 是新文件差异，不冒记为 exit 0。

## 可重放探针代码

cwd 与前述门禁相同。以下每个 JavaScript 块分别放入 PowerShell 的
`@' ... '@ | & $node --input-type=module -` 执行；均不落地临时源码。

### Parser 与参数

```javascript
import { build } from 'esbuild';
import Module from 'node:module';
const source = String.raw`
import assert from 'node:assert/strict';
import { parseStatisticsData, parseStatisticsContent, sameStatisticsData } from './src/lib/statistics-result';
import { buildMessageViews } from './src/lib/statistics-messages';
import { statisticsFixture, updateSummary, envelope, callMessage, toolMessage } from './tests/statistics-fixture';
const unknown = [];
for (const path of ['', 'parameters', 'source', 'result', 'columns.0']) {
  const d = statisticsFixture();
  let target: any = d;
  for (const part of path.split('.').filter(Boolean)) target = target[part];
  target.future_field = 'public-probe';
  assert.equal(parseStatisticsData(d), null);
  unknown.push(path || 'data');
}
const args = callMessage().tool_calls![0].args;
const argsCases = [undefined, {}, { ...args, column: 'other' }, { ...args, file_id: '22222222-2222-4222-8222-222222222222' }, { ...args, url: 'http://127.0.0.1:9/' }, { ...args, column: 'amount ' }];
for (const a of argsCases) assert.notEqual(parseStatisticsContent(envelope(), a).status, 'success');
const reversed = (x: any): any => Array.isArray(x) ? x.map(reversed) : x && typeof x === 'object' ? Object.fromEntries(Object.entries(x).reverse().map(([k,v]) => [k,reversed(v)])) : x;
assert.ok(sameStatisticsData(parseStatisticsData(statisticsFixture())!, parseStatisticsData(reversed(statisticsFixture()))!));
const probes = [];
for (const [path, suffix] of [['result.value', '\n'], ['result.minimum', '\r'], ['result.maximum', '\r\n'], ['result_sha256', '\n'], ['source.sha256', '\n'], ['source.file_id', '\n']]) {
  const d = statisticsFixture();
  let target: any = d;
  const keys = path.split('.');
  for (const k of keys.slice(0,-1)) target = target[k];
  target[keys.at(-1)!] += suffix;
  updateSummary(d);
  const call = callMessage();
  call.tool_calls![0].args.file_id = d.source.file_id;
  probes.push({path,suffix:JSON.stringify(suffix),parserAccepted:parseStatisticsData(d)!==null,successfulCards:buildMessageViews([call,toolMessage('call-1',envelope(d))]).filter(v=>v.statistics?.status==='success').length});
}
console.log(JSON.stringify({unknownFieldsRejected:unknown,argsCasesRejected:argsCases.length,keyOrderIndependent:true,encodingBoundaryProbes:probes},null,2));
`;
const result = await build({stdin:{contents:source,resolveDir:process.cwd(),sourcefile:'independent-frontend-probe.ts',loader:'ts'},bundle:true,platform:'node',format:'cjs',target:'node22',write:false});
const compiled = new Module(process.cwd() + '/independent-frontend-probe.cjs');
compiled.paths = Module._nodeModulePaths(process.cwd());
compiled._compile(result.outputFiles[0].text,compiled.filename = process.cwd() + '/independent-frontend-probe.cjs');
```

### 真实重定向

```javascript
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {build} from 'esbuild';
import Module from 'node:module';
let destinationHits=0, credentialedRequests=0, requestIds=new Set(), requests=0;
let redirectStatus=307, crossOrigin=false, destinationOrigin='';
const destination=createServer((req,res)=>{destinationHits++;res.end('{}');});
const origin=createServer((req,res)=>{
  if (!req.url.startsWith('/rest/api/files/')) {destinationHits++;res.end('{}');return;}
  requests++;
  assert.equal(req.method,'POST');
  assert.equal(req.headers.authorization,'Bearer test-token');
  assert.match(req.headers['x-request-id'],/^[a-f0-9]{32}$/);
  credentialedRequests++;
  requestIds.add(req.headers['x-request-id']);
  req.resume();
  res.writeHead(redirectStatus,{Location:crossOrigin ? destinationOrigin+'/target' : '/same-origin-target'});
  res.end();
});
try {
  destination.listen(0,'127.0.0.1'); await once(destination,'listening');
  origin.listen(0,'127.0.0.1'); await once(origin,'listening');
  destinationOrigin='http://127.0.0.1:'+destination.address().port;
  const rest='http://127.0.0.1:'+origin.address().port+'/rest';
  const result=await build({stdin:{contents:"export {fetchFileStatistics} from './src/lib/managed-file-client'; export {statisticsFixture} from './tests/statistics-fixture';",resolveDir:process.cwd(),sourcefile:'redirect-probe.ts',loader:'ts'},bundle:true,platform:'node',format:'cjs',target:'node22',write:false,define:{'process.env.NEXT_PUBLIC_REST_API_URL':JSON.stringify(rest)}});
  const m=new Module(process.cwd()+'/redirect-probe.cjs');
  m.paths=Module._nodeModulePaths(process.cwd());
  m._compile(result.outputFiles[0].text,m.filename=process.cwd()+'/redirect-probe.cjs');
  globalThis.window=Object.assign(new EventTarget(),{sessionStorage:{getItem:()=> 'test-token'}});
  let refusals=0;
  for (const cross of [false,true]) for (const status of [301,302,303,307,308]) {
    crossOrigin=cross;redirectStatus=status;
    await assert.rejects(m.exports.fetchFileStatistics(m.exports.statisticsFixture(),AbortSignal.timeout(3000)),e=>e.code==='network_error');
    refusals++;
  }
  assert.equal(destinationHits,0);assert.equal(requests,10);assert.equal(requestIds.size,10);
  console.log(JSON.stringify({runtime:process.version,transport:'Node fetch to two temporary loopback HTTP servers; not browser',redirectRefusals:refusals,credentialedInitialRequests:credentialedRequests,uniqueRequestIds:requestIds.size,redirectDestinationHits:destinationHits}));
} finally {
  delete globalThis.window;
  await Promise.all([origin,destination].map(server=>new Promise(resolve=>{
    server.closeAllConnections();server.close(resolve);
  })));
  console.log('LOOPBACK_SERVERS_CLOSED');
}
```

### 实际提交函数

```javascript
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import Module from 'node:module';
import {build} from 'esbuild';
const path='src/components/thread/index.tsx';
const source=ts.createSourceFile(path,readFileSync(path,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let handler;
function visit(node) {
  if(ts.isVariableDeclaration(node)&&node.name.getText(source)==='handleSubmit') handler=node.initializer;
  ts.forEachChild(node,visit);
}
visit(source);assert.ok(handler);
const text=ts.createPrinter().printNode(ts.EmitHint.Expression,handler,source);
const helpers=await build({stdin:{contents:"export {ensureToolCallsHaveResponses,MissingToolCallIdError} from './src/lib/ensure-tool-responses'; export {callMessage} from './tests/statistics-fixture';",resolveDir:process.cwd(),sourcefile:'submit-helpers.ts',loader:'ts'},bundle:true,platform:'node',format:'cjs',target:'node22',write:false});
const helperModule=new Module(process.cwd()+'/submit-helpers.cjs');
helperModule.paths=Module._nodeModulePaths(process.cwd());
helperModule._compile(helpers.outputFiles[0].text,helperModule.filename=process.cwd()+'/submit-helpers.cjs');
const {ensureToolCallsHaveResponses,MissingToolCallIdError,callMessage}=helperModule.exports;
const js=ts.transpileModule(text,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText.trim().replace(/;$/,'');
const names=['input','contentBlocks','isLoading','uploading','ensureToolCallsHaveResponses','MissingToolCallIdError','stream','toast','setFirstTokenReceived','uuidv4','createManagedFileContentBlock','artifactContext','createRunCorrelation','setInput','clearSubmittedFiles'];
const make=new Function(...names,'return ('+js+')');
const results=[];
for (const id of [undefined,'','  ','call-valid']) {
  const message=callMessage();message.tool_calls[0].id=id;
  let input='public draft retained';
  const blocks=[{fileId:'11111111-1111-4111-8111-111111111111'}];
  let prevented=0,submitted=0,cleared=0,firstTokenSet=0;
  const errors=[];
  const handle=make(input,blocks,false,false,ensureToolCallsHaveResponses,MissingToolCallIdError,{messages:[message],submit:()=>submitted++},{error:m=>errors.push(m)},()=>firstTokenSet++,()=> 'public-human-id',b=>b,{},()=>({config:{},metadata:{}}),value=>input=value,()=>cleared++);
  handle({preventDefault:()=>prevented++});
  assert.equal(prevented,1);
  if (id==='call-valid') {
    assert.equal(submitted,1);assert.equal(cleared,1);assert.equal(input,'');
  } else {
    assert.equal(submitted,0);assert.equal(cleared,0);assert.equal(input,'public draft retained');
    assert.equal(firstTokenSet,0);assert.equal(errors.length,1);
    assert.ok(errors[0].includes('输入和附件已保留'));
  }
  results.push({id:id??'undefined',submitted,attachmentClearCalls:cleared,inputRetained:input==='public draft retained',errors:errors.length});
}
console.log(JSON.stringify({method:'execute actual handleSubmit AST with injected closure dependencies; no component mount/browser',cases:results},null,2));
```
