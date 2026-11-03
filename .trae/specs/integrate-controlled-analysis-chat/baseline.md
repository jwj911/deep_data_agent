# 任务 1：接入合同与前置基线

2026-11-02。依据已批准的本轮 spec/tasks/checklist，以及前轮
`deliver-controlled-analysis-slice/validation.md`。仅只读核验、离线测试和本文件，
不实现业务，不修改 spec/tasks/checklist，不提交、推送或部署。

## 结论与证据边界

- **统计服务基线通过：50 passed，33.62 秒，0 failed/error/skipped。**
  实际运行整个 `tests/test_file_statistics.py`，未使用 `-x`。
- 当前 Windows/Python 环境的 **134 个适用锁定包版本匹配**；
  `support_checked=false`，没有查询外部支持状态，也不是重新校验已安装 wheel 内容。
- 后端任务 2、前端任务 4 可以依据下列合同开始；任务 3 仍按 tasks 依赖任务 2。
  本文件不代表新工具、聊天卡片、下载生命周期或缓存修复已实现/通过。
- 默认 Node `v25.2.1` 不符合前端 `>=22.11.0 <23`；在 `agent_chatui` 中
  `pnpm --version` 实测 `10.5.1`。前端实施门禁需显式使用 Node 22，
  不能把默认 Node 的结果作为合规证据。本任务未运行前端四门禁或浏览器。
- 前轮 813 项和 HEAD 的 Hosted 成功是历史证据，本轮没有全后端、
  新 SHA Hosted、容器、部署、真实模型或生产放行证据。

## 工作树与控制条件

仓库 `D:\Code\deep_data_agent\deep_data_agent`；
HEAD `0aca6ee2c9adf1aabeff85b0f028fae6d185612f`。
首条命令为该仓库的 `git status --short`，结果如下：

```text
 M .trae/documents/roadmap.md
 M CHANGELOG.md
 M README.md
 M data_agent/routes/managed_file.py
 M data_agent/services/managed_file_service.py
?? .trae/specs/deliver-controlled-analysis-slice/
?? .trae/specs/integrate-controlled-analysis-chat/
?? data_agent/services/file_statistics.py
?? tests/test_file_statistics.py
```

已有 tracked 差异为 5 文件、152 行增加、1 行删除；不包括 untracked 文件。
写本文件前再次展开 status，与上述既有路径一致。前轮目录有 spec/tasks/checklist/
validation，本轮原有 spec/tasks/checklist，均未由本任务改写。
本轮 spec 已是“已批准，实施中”，不再编辑其状态。

核验时的文件 SHA-256（不是提交或完整工作树快照）：

```text
data_agent/services/file_statistics.py
345B66A649A6E959C9A4A09192B2BE8AA7E0C74F8F69FE9061A82D8D70D48225
tests/test_file_statistics.py
8F8805FD122C4527FE3615FDF3AEC3EE6F6D227198FE9B1FBCD46FB4C84DAC69
.trae/specs/integrate-controlled-analysis-chat/spec.md
059D966DAC62F21CDF10277521C2F5A82EFB8C793BAC062CFA84857843441DAF
```

未读取真实 `.env`。`tests/conftest.py` 使用 `sqlite://`、离线 Redis 替身和
公开测试身份；统计测试使用内存 SQLite、ASGITransport 和临时受管文件，
不发真实模型、搜索、MySQL 或业务 Redis 请求。

### 实际命令

PowerShell 5，工作目录为仓库根。测试执行命令如下；目录名为本次实际 UUID。
重跑必须生成新 UUID，不能复用此路径，pytest 自身会重建 basetemp。

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:LANGSMITH_TRACING = 'false'
$env:LOG_FILE_PATH = ''
$taskTemp = 'D:\Code\deep_data_agent\.dda-integrate-chat-task1-20261102-dc19fa278a36415a85b2685b985c0022'
if (Test-Path -LiteralPath $taskTemp) { throw 'Task directory already exists; refusing reuse' }
New-Item -ItemType Directory -Path $taskTemp -ErrorAction Stop | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$pytestBase = Join-Path $taskTemp 'pytest'
& 'D:\Code\.dda-recovery-admission-20261028\venv\Scripts\python.exe' -B -m pytest -q -ra -p no:cacheprovider --basetemp $pytestBase tests/test_file_statistics.py
```

执行标识 `f06ed51c3beefc0d4ad1891b3c06dd48`，exit 0：

```text
..................................................                       [100%]
50 passed in 33.62s
```

在同样六个环境开关下运行：

```powershell
& 'D:\Code\.dda-recovery-admission-20261028\venv\Scripts\python.exe' -B scripts/verify_runtime_lock.py
```

执行标识 `59955b82af4c722535874c6b67641f5d`，exit 0：
`{"gate": "runtime_lock", "packages": 134, "support_checked": false}`。
每次工具命令都应重新设置环境开关，不依赖跨命令 PowerShell 变量保留。

Python 实测 `3.12.9`，解释器路径与用户锁定路径相同。关键包实测并与锁匹配：
pytest 9.1.1、FastAPI 0.162.0、Starlette 1.10.0、Pydantic 2.14.1、
SQLAlchemy 2.1.6、HTTPX 0.28.1、LangChain 1.4.7、langchain-core 1.7.0、
LangGraph 1.2.18、langgraph-api 0.16.8、DeepAgents 0.7.32、AnyIO 4.15.1。

### 覆盖与失败记录

50 项包括参数化实例，不是 50 个函数：完整 CSV 尾部/Fraction、高精度和、
JSON 质量与类型重复、26 个不安全/歧义数据拒绝、4 个列名拒绝、
4 个资源维度、解析期限、20 次并行累计隔离、owner/管理员与来源、
API/download canonical 相等、6 个生命周期变更、匿名、
超限读取前拒绝及安全错误文本。引用 `tests/test_file_statistics.py:31-325`。
循环中的 20 次计算不另计为 20 个 pytest 用例。

本轮没有 pytest 失败；以下失败和限制不能省略：

1. `rg --files ...` exit 1：命令不存在，改用 `git ls-files`、
   `git grep`、`Get-Content` 和 `Select-String`，未安装工具。
2. 首次 `python -c` 版本探针 exit 1：
   `NameError: name 'python' is not defined`，PowerShell 5 引号传递失败。
   改用 here-string 经标准输入传给 `python -B -` 后成功，不是应用失败。
3. 尝试跨命令复用 `$protectedSnapshot` 的完整哈希比对 exit 1：
   `Protected snapshot unavailable or unexpected`。跨调用变量未保留，
   初次哈希表输出又被表格截断，因此不声称完成 15 文件逐字节前后比对。
   已重新记录上述完整哈希、核对 status，且本任务未写任何已有业务文件。
4. 默认 Node 版本不符合合同，必须切换。pnpm 版本检查通过不消除此缺口。
5. Git 给既有 5 个 modified 文件提示 LF 将转 CRLF；
   不为处理提示而格式化或重写用户文件。

前轮 validation 的两次 `510 passed / 303 errors`、basetemp
`PermissionError: [WinError 5]` 属历史失败，原文保留；
本轮使用外层 workspace 独立 UUID 目录，没有发生该权限失败。

## R1：Canonical 与工具协议

唯一数值来源为 `ManagedFileService.file_statistics`，
`data_agent/services/managed_file_service.py:586`，不得用预览、模型或浏览器重算。
`calculate_statistics` 的纯计算结果还没有 source/hash，必须使用服务最终 payload。
`normalize_file_id` 要求 UUID 的规范字符串；`column` 为严格字符串，长度 1–128，
精确匹配列名，不擅自 trim、大小写转换或选择首列。指标固定 sum。
模型可见 schema 仅 file_id/column，拒绝 owner/path/表达式/metric/预算等额外参数。
身份和当前角色从服务端取得，不由模型输入控制。

### 完整 Data 字段

| 字段 | 编码与含义 |
| --- | --- |
| `analysis_version` | 字符串，当前 `column-sum-v1` |
| `parser_version` | 字符串，当前 `strict-table-v1` |
| `parameters` | `{metric: "sum", column: string}` |
| `row_count` | 总数据行数，正整数，不含 CSV 表头 |
| `columns` | 非空数组，每项 `{name: string, types: string[], missing_count: integer}` |
| `columns[].types` | 排序后的实际非缺失类型，取值 number/string/boolean；全缺失列可为空数组 |
| `duplicate_row_count` | 非负整数，按完整行语义计数，重复行不排除 |
| `result.value` | 精确和的十进制字符串，非 JSON number |
| `result.unit` | 固定 `unspecified`，展示为“未指定” |
| `result.valid_count` | 目标列有效数，正整数 |
| `result.missing_count` | 目标列缺失数，非负整数；与有效数之和等于 row_count |
| `result.minimum/maximum` | 十进制字符串，不是 null；全缺失时接口失败 |
| `warnings` | 字符串数组，当前只有 unit_unspecified/missing_values_excluded/duplicate_rows_included |
| `summary` | 服务端固定模板字符串，与同一 data 数值一致 |
| `source` | `{file_id: string, sha256: string, size_bytes: integer, semantics: "current_file_at_read"}` |
| `result_sha256` | 64 位小写十六进制 SHA-256 |

source.file_id 是规范 UUID，source.sha256 是原始文件字节 SHA-256，
size_bytes 是完整原始字节数，不是预览或下载响应大小。
payload 没有原文件名、owner、路径、原始行、生成时间或下载 URL；
不要把上传 metadata 的 camelCase 字段混入此结构。

`file_statistics.py:131,236` 的 canonical v1：
对完整 data **仅去掉 result_sha256 本身**，
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`，
编码 ASCII 后 SHA-256。source、summary、warnings 和所有其他现有字段均参与。
对象键排序，数组顺序不变；不是简单的 JavaScript `JSON.stringify`。
不能将中文直接 UTF-8 序列化后的不同字节误认为 canonical v1。
REST `JSONResponse` 的传输字节不必等于 canonical 字节；合同是解码后的同一 payload。

当前边界：5 MiB、50,000 行、64 列、250,000 单元格、5 秒解析/遍历检查；
单值最多 38 位有效数字、18 位小数，累计使用 Decimal precision 80。
结果和可能比单个输入更长，前端不要把输入精度限制误套到结果和。
数值输出为规范固定小数字符串，无指数，无无意义尾零，零为 `"0"`。
CSV 仍拒绝 `= + - @` 前缀，包括 CSV 负数；负数成功样本用 JSON。
本轮不调整上传和解析政策。5 秒不等于能强制抢占阻塞读取或已运行解析器。

### 包裹与消息身份

```text
success = {
  type: "managed_file_statistics",
  version: 1,
  status: "success",
  data: <上表完整对象>
}
```

上例是协议形状示意，不是 JSON 固件；完整成功 data 样本见后文。
失败包裹为：

```json
{"type":"managed_file_statistics","version":1,"status":"error","error":{"code":"analysis_non_numeric","message":"Selected column contains a non-numeric value"}}
```

失败不得有 data。version 必须是数字 1，不是字符串 `"1"`。
外层不参与 canonical hash，不更名、删减、增加或转换 data 内的字段。
新统计工具的未知异常使用固定安全提示和稳定 code，不暴露异常、路径、原始单元格。
现有预览工具使用 `managed_file_auth_required` / `managed_file_not_found`；
REST 不可见文件使用 `file_not_found`。新工具需保持不可见语义，
前端不得把两种边界的历史 code 当成同一个字段或依赖某条英文原文。

承载消息是实际 `type: "tool"` 的 ToolMessage，其 `content` 为上述 JSON，
`tool_call_id` 必须关联 AI 消息中的 `name: "analyze_file_statistics"` 调用。
ToolMessage 的 type/status 与 content 内包裹的 type/status 是不同层次。
只看 JSON 外形或 message.name 不足以判定成功。普通 AI 文本、synthetic
`do-not-render-` 消息、未知协议、缺失字段、损坏 JSON、未完成/失败消息均不得出成功卡片。
若 SDK tool 状态明确为 error，也不能由 content.status=success 覆盖。

现有工具仅注册 internet_search/analyze_document；
`_TOOL_POLICY_VERSION="4"`，统计工具未接入、REST 缓存未修。
R2 共享 8/12 预算、身份、取消和线程适配仍由任务 2 实现并验证，50 项不证明这些新增行为。

## R3：前端呈现与缺失结果

卡片读取上表同一 data：列、精确和、总行/有效/缺失/重复数、质量提示、
固定说明和来源详情；source UUID、两个 SHA、两个版本均可取得。
默认标记“计算时快照”；source.semantics 说明计算时读取，不保证当前仍有效。
禁止 Number/parseFloat/浮点格式化或再次累计 value/minimum/maximum。
计数字段可验证为有界非负安全整数，布尔值和数字字符串不能冒充计数。

卡片按 thread、tool_call_id 和实际 message 身份关联、去重与稳定排序，
不按内容或只按 file_id 合并。相同文件的不同列、不同调用可以有不同卡片。
隐藏工具详情不隐藏业务卡片；错误有文字，动态列名/提示按文本渲染，
键盘/焦点/禁用态、窄屏及长数值可用，不创建任意 HTML 或 URL。

现有 `messages/ai.tsx` 会在 hideToolCalls 时直接隐藏所有 tool 消息；
`messages/tool-calls.tsx` 仅通用 JSON/文本展示，不能作为统计验证器。
`ensure-tool-responses.ts` 目前仅检查紧邻消息是否为任意 tool，
否则产生 `Successfully handled tool call.`，缺失调用 ID 还会写空 ID。
任务 4 必须按每个调用 ID 查真实后续结果，真实结果不改写，
缺失项仅补明确 error/未完成说明“没有取得工具结果”，重复补齐幂等。
`thread/index.tsx:216` 的提交路径须在缺失 ID 阻止续发时保留输入/附件，
不能走后面的无条件清空。不要把补齐说明推断成用户取消。

## R4：下载合同与状态

固定配置 `REST_API_URL`，复用 `managed-file-client.ts` 的 Origin/path 校验、
JWT、请求 ID 和 401 认证流程：

```text
POST /api/files/{规范且经校验的 file_id}/statistics?download=true
Content-Type: application/json
body: {"column":"卡片 parameters.column 的原值"}
```

不得使用工具/模型提供的 URL。REST 返回裸 data，不返回聊天包裹；
200 带 `Cache-Control: no-store`，
`Content-Disposition: attachment; filename="analysis-{file_id}.json"`。
客户端下载名仍由受控 UUID 构造，不信任外部文件名或 URL。

先完整验证响应结构，再比对 source.file_id/sha256/size_bytes/semantics、
parameters.metric/column、analysis_version、parser_version、result_sha256。
只在与原卡片一致时交付；以完整 data 相等检查防止其他展示字段悄悄变动也可行。
SHA 不能替代身份认证和来源复核。若前端重新计算 SHA，必须实现上述 canonical 编码，
不能先裁剪 payload，也不能对外层工具包裹求 hash。

| 状态/响应 | 交互合同 |
| --- | --- |
| 空闲 | 可点击“校验来源并下载 JSON”，不自动下载或重算历史卡片 |
| 请求中 | 禁止重复点击；保存 AbortController 和当前主体/thread/请求身份 |
| 200 且结构、一致性通过 | 才创建 Blob/下载；完成后释放 URL/请求资源 |
| 200 但版本、参数、来源或结果改变 | “结果已变化，请重新分析”；保留原卡片，不下载、不静默替换 |
| 200 损坏 JSON/缺失字段/非法数值类型 | 无法校验，不创建下载 |
| 401 | 走现有退出认证流程，不交付响应 |
| 404 | “源文件已不可用”；删除/过期/越权统一不可见，不泄漏 owner |
| 503 file_storage_invalid/unavailable | 无法校验来源；哈希/大小漂移、路径异常、物理文件缺失等不得下载 |
| 422 统计输入错误、413 超限、503 analysis_timeout | 安全错误文本，无成功 data，不回退旧下载 |
| 网络错误 | 明确失败，结束 loading，允许手动重试 |
| 切线程、退出登录、卸载或中止 | abort，并丢弃迟到响应；不得向新主体/线程交付；释放资源 |

目前 `request()` 的 catch 会把包括 AbortError 的 fetch 拒绝归为 network_error，
尚无统计下载函数；任务 4 需补中止识别和迟到响应隔离，而非只添加一个 fetch。
已授权历史卡片及已有本地副本不抹除，来源失效只阻止新统计/下载。

稳定错误清单来自现有路由/服务，不是本轮测试失败：

| HTTP | 现有 code |
| --- | --- |
| 400 | unsafe_csv_formula |
| 404 | file_not_found |
| 413 | analysis_table_limit |
| 422 | invalid_file_id、analysis_unsupported_type、analysis_invalid_table、analysis_invalid_columns、analysis_duplicate_key、analysis_non_finite、analysis_invalid_column、analysis_column_not_found、analysis_non_numeric、analysis_numeric_range、analysis_no_numeric_values |
| 503 | analysis_timeout、file_storage_invalid、file_storage_unavailable |

一般文件错误映射还包含 file_database_error；不是所有映射都在本次 50 项中单独触发。
REST Pydantic 额外字段/类型错误为 422 验证详情列表，并非统一 detail.code 对象；
前端应保留安全通用回退。匿名为 401，禁止把任何错误响应解析为成功 data。

## 公开样本准备方案

本任务仅在内存生成并核验样本，未新增 fixture 或业务代码。
后端/前端后续可将以下内容固化为各自测试固件；实际上传取得随机 UUID，
不能期待得到下列固定测试 UUID。需上传/临时存储的场景仍使用隔离 SQLite/公开字节。

### 已实际计算的成功基准

UTF-8、无 BOM、LF 换行、末尾 LF，共 34 字节：

```csv
amount,label
0.1,a
0.2,b
0.1,a
,c
```

以现有 calculate_statistics/attach_source 在内存生成，独立 Fraction 验证
`0.1 + 0.2 + 0.1 = 0.4`，另按 canonical 规则独立重编码/hash 一致；
执行标识 `3d9d584fffaf8a952ea53ed122d92759`，exit 0。此探针不是新增 pytest 用例，
也不是已注册工具调用。可直接作为 data 固件：

```json
{
  "analysis_version": "column-sum-v1",
  "parser_version": "strict-table-v1",
  "parameters": {"metric": "sum", "column": "amount"},
  "row_count": 4,
  "columns": [
    {"name": "amount", "types": ["number"], "missing_count": 1},
    {"name": "label", "types": ["string"], "missing_count": 0}
  ],
  "duplicate_row_count": 1,
  "result": {
    "value": "0.4", "unit": "unspecified", "valid_count": 3,
    "missing_count": 1, "minimum": "0.1", "maximum": "0.2"
  },
  "warnings": ["unit_unspecified", "missing_values_excluded", "duplicate_rows_included"],
  "summary": "完整文件共 4 行；列「amount」的 3 个有效数值之和为 0.4，缺失 1 行；重复行 1 行，保留参与计算；单位未指定。",
  "source": {
    "file_id": "11111111-1111-4111-8111-111111111111",
    "sha256": "b1f889c1cf3ea272f16f5d2e78b49e24514fcdeddfaf9d4e02354a47ba04e9fc",
    "size_bytes": 34,
    "semantics": "current_file_at_read"
  },
  "result_sha256": "cc11dc9d7a0e12dacf9d415ab70df65cb6fd4e3526e7a19ab5f0bc69418a4c43"
}
```

成功消息组：AI `id=ai-stat-1`，tool_calls 中
`id=call-stat-1/name=analyze_file_statistics/args={file_id:上述 UUID,column:"amount"}`；
实际 tool 消息 `id=tool-stat-1/tool_call_id=call-stat-1/name=analyze_file_statistics`，
content 为 `{type:"managed_file_statistics",version:1,status:"success",data:上述对象}`
的 JSON 字符串。SDK 状态若提供则为 success，不混用外层 type。

### 待实施的行为矩阵

| ID | 公开输入/变体准备 | 预期及责任 |
| --- | --- | --- |
| S1 | 上述 34 字节 CSV，配成功消息组 | 卡片 0.4，4/3/1/1；隐藏详情仍可见；工具/REST/下载一致，任务 2/4/5 |
| S2 | `["0.1","0.2"]` 交替 6,000 次，再加 `999.123456789012345678` 的 CSV | 12,001 行、尾部超过预览上限，和 `2799.123456789012345678`；服务已测，聊天待测 |
| S3 | 复用现有 JSON 质量用例的 0.1/0.10/-0.2/null/空串/0 | 和 `"0"`，有效 4/缺失 2/重复 1；验证负数及非浮点行为 |
| S4 | 两个 38 位 9 加 `0.000000000000000001` | 字符串原值，长数值不截断可取得内容；独立 Fraction 参考 |
| E1 | 请求不存在列、目标列 `not-a-number`、JSON bool/全 null | 稳定统计错误，error 包裹无 data，无数值卡片 |
| E2 | 同一文件先成功，再删除/过期/等长篡改/缺失/目录/非法路径 | 404 或 503，无新下载；历史快照保留，复用本次生命周期用例 |
| E3 | owner B、管理员、失效用户/角色、无主体调用 owner A 文件 | 统一不可见或认证错误，不泄漏来源；任务 2 补工具负控 |
| V1 | 将包裹 version 改 2 或 `"1"`，或改变 type | 不出成功卡片，安全未知状态 |
| V2 | 下载替身返回不同 analysis/parser 版本并重算合法 hash | 结果已变化，提示重新分析；不以一个旧 hash 假装版本相同 |
| V3 | 分别改变 UUID/SHA/size/column/metric/result_sha256 | 均不得交付；再加 200 损坏 JSON、删 source、数值改 number、计数改 bool |
| M1 | AI 有 c1/c2/c3，后续真实 tool 乱序 c3/c1，缺 c2 | 仅补 c2 未完成，保留 c1/c3，第二次补齐不重复 |
| M2 | AI 三调用后只有一条任意或无关 tool | 不能把整组视为完成；按 ID 匹配，不能按紧邻消息类型匹配 |
| M3 | AI 调用缺 id/空 id；失败后再次提交 | 不构造空 ID tool，不发送非法续发，保留输入与附件并提示恢复 |
| M4 | 普通 AI 正文含成功 JSON、synthetic 前缀消息含同 JSON、SDK status=error | 均不得伪装成成功统计卡片 |
| M5 | 相同 tool 消息流式更新/重复回放、刷新、切线程再回来 | 不重复或串用；相同文件不同调用仍正确关联 |
| D1 | HTTP 替身延迟成功，期间双击/切线程/登出/卸载 | 请求禁重，中止及迟到响应隔离，无下载/Blob 泄漏 |
| D2 | HTTP 401/404/422/503/网络失败，随后手动重试成功 | 认证与各状态文本正确，旧失败不覆盖新请求，资源释放 |

版本和损坏消息只能在前端纯行为/HTTP 替身中制造，不能改真实服务版本或线上来源。
成功固定 hash 固件只用于已注明的测试 UUID/字节；实际工具和 REST 比较必须
使用同一真实测试记录，不跨不同上传 UUID 比较 result_sha256。
浏览器聊天、隐藏详情、刷新、切线程、登出中止等仍由任务 5 实际验证；
本表是准备方案，不将源码阅读或样本生成计为浏览器通过。

## 收尾

本任务唯一保留产物为本文件。
独立临时目录已用完整固定路径删除，执行标识
`c346b08995e540ddbf87a985f3863522`，exit 0，`TASK_TEMP_EXISTS=False`。
未删除其他任务目录，未改 ACL，未删除或修改锁定 venv。

最终 `git status --short --untracked-files=all` 相较起始仅新增本文件；
已有 5 个 modified 文件及前轮、本轮原有 untracked 文件均保留。
`git diff --check` exit 0，只有原有 LF/CRLF 提示。
对 untracked 本文件使用
`git diff --no-index --check -- /dev/null .trae/specs/integrate-controlled-analysis-chat/baseline.md`，
exit 1，输出只有 LF/CRLF 提示，无 whitespace error；no-index 的 1 表示文件差异，
不冒记为 exit 0 或测试失败。以上不等于全工作树字节级前后比对，限制见失败记录。
tasks/checklist 保持原文，由主 Agent 按本证据同步任务状态。
