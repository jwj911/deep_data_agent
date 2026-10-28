# 图复制修复：HTTP 与部署补验

日期：2026-10-27。项目：`D:/Code/deep_data_agent/deep_data_agent`。
本机补验时 HEAD：`3d4ac6dbb540d7f8a46430f3bc311c071d4ba438`。
随后经用户授权，四个修复/验收代码文件已提交并推送：
`8e552f393aafd919fcf564f2b43c9856e6ff71f9`，分支 `fix/agent-graph-copy`。
本文记录本轮补验，不替代此前本机 149 项回归、601 项后端测试或历史 Hosted 记录。

| 场景 | 本轮结果 | 证据与边界 |
| --- | --- | --- |
| 本机真实 HTTP | **通过** | 安装版 LangGraph API 的真实 TCP 路由、worker 和 get_graph/copy；模型/租约为替身、身份库为隔离 SQLite、API 存储为隔离 inmem |
| Linux 容器 | **回归通过，本机联调未通过** | Hosted 冒烟通过；本机缓存及新建镜像各 150 项回归通过。新镜像五服务启动成功，但实际图运行发生 ContextVar 重置异常、租约未及时释放 |
| 本机浏览器 | **局部页面正控通过，整体未通过** | 显式登录页可登录、提交并显示测试答案；对应 run 为 error，匿名入口及退出跳转丢失宿主端口 |
| Hosted | **四项全部成功** | [PR #1](https://github.com/jwj911/deep_data_agent/pull/1) 的 [run 40507150345](https://github.com/jwj911/deep_data_agent/actions/runs/40507150345)，head SHA 对应修复；Backend、Frontend、Release Contracts、Container Smoke 均 completed/success |

HTTP 命令：

```powershell
.\.venv\Scripts\python.exe -I -B scripts/verify_agent_graph_http.py
```

该命令实际 exit 0。十个断言通过：匿名拒绝、跨 owner/管理员拒绝、wait run、
stream run、checkpoint 状态读取、可信主体传播、保留身份字段拒绝、跨 owner
发起 run 拒绝、复制依赖保持、取消及单次租约释放。wait/stream/state 正控为
HTTP 200；客户端指定 `langgraph_auth_user_id` 的负控为 HTTP 422。
租约 acquire/release 均为 3，作用主体为两个合成测试用户；最后回归中
出站连接尝试为 0。

对应修复文件的 SHA-256：
`c75a49e3cf4519d926dbda4680e2322de0367064ab9b2803dca41ce5d6d1e8c7`。
这是文件字节指纹，不是 Git commit SHA 或完整镜像指纹。

脚本在系统临时目录启动独立子进程，使用动态测试签名密钥，不读取项目 `.env`
或用户数据。API 路由和执行逻辑不替换；复制观察器委托原方法。模型、租约和
身份存储属于测试控制条件，未证明真实 MySQL/Redis 并发、付费模型效果或生产恢复。
测试进程在启动阶段先于 worker 初始化本机 NumPy 2.5.2；该条件必须随结果保留。

首轮 HTTP 初始化暴露日志级别配置和读就绪协议问题，已修正验证脚本。
保留身份字段首次被当成正控时返回 422，源码核实这是 API 的预期安全校验，
之后拆为负控。一次等待试验未设置整体响应期限，被停止后留下一个自有临时
目录；后续加入整体期限和失败清理。线程栈确认序列化首次在 worker 导入
NumPy 原生扩展时阻塞，主线程导入通过，启动预初始化后 HTTP 完整链路通过。
这不是租约管理器缺失复发，也未修改运行时代码或安装库来绕过问题。

首次 Docker 尝试（历史）：`docker version --format '{{json .}}'` 返回 Client
29.4.1、Server=null、exit 1；`docker desktop start` 报日志写权限拒绝，
该次启动已停止。当时系统盘空间不足，未继续完整构建。项目指南原文为
“建议系统盘至少保留 10 GB”；此前将建议值当成硬门槛过严。以下本机补验
在 Engine 恢复后使用受限只读容器，不将其等同于完整服务重建。

## 本机 Linux Engine 恢复后的补验

用户启动 Engine 后，实际查询 Client/Server 均为 29.4.1，Server OS=linux、
arch=amd64，Docker Desktop 4.71.0（225177），WSL2 kernel
6.6.87.2-microsoft-standard-WSL2。C 盘约 2.0 GiB，D 盘约 37.64 GiB。

采用已有 `deep-data-agent-backend:local` 作为缓存依赖环境，镜像 ID 为
`sha256:c02f38c9d134788f54b8a498fffef51e66e8ce83d2a55cbf7ade712f05a93104`。
当前 `data_agent/`、测试和 HTTP 验收脚本通过只读绑定供容器执行；它不是
本轮新建的发布镜像。实际依赖：Python 3.12.13、DeepAgents 0.7.6、
LangGraph 1.2.11、API 0.7.28、CLI 0.4.31、SDK 0.4.2、LangChain 1.3.15、
pytest 9.1.1、NumPy 2.5.2。该安装组合与此前 Windows DeepAgents 0.7.5
快照分别记录。

容器 `dda-copy-8e552f3-local` 使用 `--network none --read-only`、1 GiB 内存、
2 CPU、256 PID 上限与 64 MiB RAM 临时目录。实际执行
`tests/test_agent_graph_copy.py` 和 `tests/test_agent_graph_http.py`：
**150 passed，18.81 秒，exit 0**。其中 149 项复制回归及 1 项真实 TCP HTTP
回归在本机 Linux 容器内运行；HTTP 使用容器内 loopback，不等于宿主机公开
端口的五服务联调。模型/租约为替身，身份与 API 存储仍为隔离 SQLite/inmem。

容器读入四个文件的 SHA-256 与宿主文件相符：

| 文件 | SHA-256 |
| --- | --- |
| `data_agent/services/agent_service.py` | `c75a49e3cf4519d926dbda4680e2322de0367064ab9b2803dca41ce5d6d1e8c7` |
| `tests/test_agent_graph_copy.py` | `2fabeb5729c8095c84cdbb933fd40f879a6a3ff07990fd321a105ec9377c7e9c` |
| `tests/test_agent_graph_http.py` | `33f7c79dd5cd555322645a8a01568e976ffbc86a89257231e533233dada3686c` |
| `scripts/verify_agent_graph_http.py` | `1d137b4de915d28e86291a90ef9aa9650221d8962d2e2dde1940cd24d9a5a9a2` |

仅出现 Passlib 关于 Python 3.13 移除 `crypt` 的弃用警告，当前 Python 3.12
测试通过。`--rm` 后查询该容器为空，原有五个运行容器 ID 保持不变。
该阶段没有拉取或重建镜像、删除缓存/卷或读取真实 `.env`；完整本机五服务重建
当时尚未执行，其既有 Linux 冒烟证据来自下述 Hosted run。

## 本机当前源码五服务补验

本轮补验使用 `git archive 8e552f3` 导出的已提交构建源码、原 Dockerfile 和
Compose 服务定义。项目名 `dda-five-b79e0535`，后端及前端使用同名独立镜像标签；
五个端口仅绑定宿主 `127.0.0.1`，网络初始设为 internal，随后按下文实测调整；
数据库和受管文件使用独立卷。
临时配置使用随机测试密钥和合成用户，未读取项目真实 `.env`。

开始时 C 盘剩余 `2189037568` 字节。系统盘 10 GB 为建议值；本轮复用缓存，
设置剩余空间低于 1 GiB 或构建超时即停止的保护，不清理用户共享缓存。
Compose 5.1.3 两次在构建开始前报
`use docker --context=desktop-linux buildx to switch to context "desktop-linux"`；
随后改用显式 context 和 builder 的 buildx 执行原 Dockerfile，未改全局选择。
后端依赖层未命中缓存，未锁定依赖重新解析后的安装组合另见下表。
旧镜像、当前 Git 对象和 LF 工作树的 requirements SHA-256 均为
`bf80dd7af617bcdfca28f2044f71eabd32691b7d61fc2640ffe93186522f2022`，
本轮 CRLF 归档为 `c2298c04b81d01670e5007b4a782f6a9f5ce036cb50d685cca1b1ca812b726b5`。
最终核对确认 Git `core.autocrlf=true` 导出 CRLF，七个关键文件的归档指纹均
严格等于 Git/LF 工作树的 LF→CRLF 转换；声明内容没有改变。缓存未命中与字节
换行差异有关，不应将这两个哈希解释为 requirements 实质修改。容器指纹与归档
字节一致，机器证据同时保留 Git 与归档指纹；未修改 Git 全局/仓库配置。
首轮原 Dockerfile 构建仍在解析依赖时被验证脚本的 900 秒限时停止，
并非已发现安装或产品运行错误，磁盘未触及 1 GiB 保护值。
公共 PyPI 和清华源的容器连接测试均为 HTTP 200；wheel metadata 下载也成功。
后续改为显式 host 构建网络、180 秒无输出保护和更长整体限时，磁盘保护保留。

前端原 Dockerfile 的本机构建已完成。BuildKit ref 为
`i6czynvhi2reheudvem3f99k7`，开始于 `2026-10-27T22:09:09.107445739+08:00`，
完成于 `2026-10-27T22:19:58.769587740+08:00`，耗时 649.66 秒，16/16 步完成。
独立标签为 `deep-data-agent-frontend:dda-five-b79e0535`，镜像 ID 为
`sha256:b17122b918b6396858aa2261b95a69dcb57303717d8b2debfe0643e3eb167c64`。
Node.js 22.23.2、pnpm 10.5.1 frozen install 成功，Next.js 15.3.2 静态构建成功；
两个 API 的本轮 loopback 地址均在实际静态 JS 中检出。安装脚本限制及
ESLint Next 插件提示保留为非失败警告。首次外层命令 300 秒超时，而 BuildKit
子构建继续完成；实际完成状态、日志和镜像均独立查询确认，不把外层 exit 1
改写为成功。后续执行器已使用进程树停止和更长总期限。

前端构建后 C 盘约剩 0.89 GiB。仅按精确 ID 回收本轮前端中间层：
`s9quxdt50fxn8botni2ywpoix`（618.7 MB）、
`laqlwuk6zwgh5fm0xf05z28w5`（995.3 kB）、
`i6xau6dkgkfdq7e5wfxfs4o7c`（1.088 GB）。
三个记录均于本轮创建；使用带精确 ID filter 的 `buildx prune --all`，
未执行全局 prune。最终前端镜像仍存在，旧镜像和旧缓存未删除。
虚拟磁盘内部约 1.707 GB 可复用空间不会立即缩小宿主 VHD 文件；后端重试
保留 C 盘 700 MiB 停止线、180 秒无进度停止及 2,700 秒整体期限。
此前错误或未命中的 filter 调用未删除任何记录，成功回收以实际返回的 ID 为准。
后端依赖解析继续时再次测得 C 盘剩余 `3026153472` 字节（约 2.82 GiB）；
宿主可用空间回升，不据此将 10 GB 建议值改成运行门槛。

第二轮后端构建 ref `8zdoyo17gwkkjkwouhslkyfer` 在 21 分 16 秒后被 180 秒
无日志保护停止；记录为 `disk=false, idle=true, wall=false`，最低宿主空余
`904519680` 字节。实际已完成依赖解析并开始下载 wheel：
bcrypt 的 593.7 kB 下载速率为 19.6 kB/s，随后 cryptography 4.5 MB 单包下载
超过无日志期限；没有安装错误。自有 Python/Docker/buildx 子进程均已退出，
后续自动验收链正确停止，没有把缺失的后端镜像当成通过。

独立下载诊断随后从清华源读取同一 cryptography 46.0.7 Linux wheel：
4,459,756 字节、索引加完整下载耗时 1.70 秒；SHA-256 为
`42a1e5f98abb6391717978baf9f90dc28a743b7d9be7f0751a6f56a75d14065b`，
与 PyPI 发布者 JSON 中的相应 wheel 哈希相符。后续构建将使用明确记录的
临时下载地址条件；仍须完成镜像、实际依赖、回归和运行验证。

第三轮已构建独立临时 Python 基底，仅增加
`PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。实际 inspect 比较确认
RootFS 完全相同，Config 的唯一差异为该环境变量；未覆盖原 Python 标签、
修改仓库 Dockerfile/requirements 或全局 pip 配置。构建通过
`--build-context python:3.12-slim=docker-image://deep-data-agent-transport:dda-five-b79e0535`
将该基底供原 Dockerfile 使用，保留 `--network host`；无日志期限延长为
600 秒，整体 2,700 秒和剩余 700 MiB 保护保持。实际 wheel 日志已指向清华源，
下载速率样本为 28–58 MB/s；后续构建与验收结果如下。

第三轮后端构建随后成功，ref `vo405uz7m2sxnuybum8vr5q8v`：
`2026-10-27T22:54:38.131279941+08:00` 至
`2026-10-27T22:57:00.2544105+08:00`，142.12 秒、13/13 步完成，外层 exit 0；
构建期间 C 盘最低剩余约 2.84 GiB。镜像 index ID 为
`sha256:b65f5b2293b7bc3e69ceb284f4cb287092bd968e7900848d5221b2d66f4b1a7e`，
linux/amd64 manifest 为
`sha256:c5f0ad7fed1ad3c4d4b6ebdc7d2ceb493df24662011da6552763f07ead9c8512`。

未锁传递依赖重新解析后，本轮实际安装组合与缓存镜像不同，不能复用旧组合的
通过结论：

| 对象 | 新后端镜像实际版本 |
| --- | --- |
| Python / pytest / NumPy | 3.12.13 / 9.1.1 / 2.5.4 |
| DeepAgents / LangGraph / API | 0.7.32 / 1.2.18 / 0.7.28 |
| CLI / SDK / runtime-inmem | 0.4.40 / 0.4.10 / 0.24.1 |
| LangChain / core / OpenAI adapter | 1.4.7 / 1.7.0 / 1.7.3 |
| FastAPI / SQLAlchemy / Pydantic / Redis client | 0.162.0 / 2.1.6 / 2.14.1 / 8.1.0 |

新镜像回归首次收集 exit 2：验收执行器使用 `python -I`，未显式把 `/app`
加入 `sys.path`，因此报 `ModuleNotFoundError: No module named 'data_agent'`。
已仅修正临时验收执行器的导入路径；仓库源码与依赖未修改，随后回归结果另记。

前端容器首次在 internal 网络下健康，但 Engine 的实际
`NetworkSettings.Ports` 为 `{"80/tcp":[]}`，宿主连接被拒绝；这属于本轮临时
隔离配置与 Engine 的交互，未据此认定正式前端有故障。仅重建本轮网络并保留
空数据库卷，改用 bridge、`internal=false`、
`com.docker.network.bridge.enable_ip_masquerade=false`；所有发布端口仍绑定
`127.0.0.1`。随后前端主页及登录页的宿主 HTTP 均为 200，响应分别为
7,211 和 12,447 字节；MySQL 仍为 0 表，Redis PONG。
该网络中两个公共 IP 的 TCP 443 连接均在 3 秒期限内超时；这是受限出口样本，
不外推为完整防火墙证明。临时网络调整没有修改仓库 Compose。

### 新镜像实际回归与运行阻断

修正临时执行器导入路径后，新镜像 **150 passed，12.29 秒，exit 0**；
`pip check` 通过。随后原 Compose 的五服务全部启动并健康，FastAPI/LangGraph
读入的运行时文件及 requirements 指纹与导出源码一致。空库迁移及既有双用户/
受管文件冒烟通过；Redis canary 实际 stop/start 后，live 保持 200、
ready/query fail-closed 为 503，再自动恢复 ready 200，后端容器未重启。

模型传输替身位于本轮 LangGraph 容器 9001 端口；图、API worker、MySQL 认证
和 Redis 租约均为真实执行。FastAPI 查询取得测试答案且租约 0→0；
LangGraph 的跨 owner/匿名请求拒绝、保留身份字段 422 负控有效，但实际工厂图
run 退出失败：

```text
ValueError: <Token var=<ContextVar name='active_agent_subject' ...>>
was created in a different Context
```

初次 `runs/wait` 已返回该错误；独立诊断再次复现。HTTP 200 的内容是
`{"__error__": ...}`，不包含成功结果，不能按状态码判定通过。stream 也为 200，
先发出含 `local-copy-ok` 的 values，再发出 error 事件。wait/stream 后的 Redis
全局租约成员数分别从 0→1、1→2。使用第三个合成用户发起受控阻塞模型调用，
租约 2→3；取消请求 HTTP 200，run 最终为 error，新增成员在取消后的 10 秒内
仍存在，未达到及时释放验收。

堆栈定位至 `agent_service.py` 的 `astream` 退出 `hold_async`，
以及 `agent_lease.py:475` 的身份 Token reset；reset 抛错发生在两项上下文
恢复和 `release` 顺序中的首项，因此跳过后续释放调用。Redis 设置 75 秒租约
到期时间及键 TTL，新 acquire 会清除到期成员；这是兜底回收，不是已验证的正常
或取消释放。尚未通过版本对照或任务
上下文探针确定究竟是哪项依赖/调度变化导致跨 Context；不将因果关系归给某个
新版本，也不把该异常写成原复制依赖缺失复发。

本轮完整五服务图执行门禁为 **FAIL**。150 项回归与已有 Hosted 成功保持其原
通过范围；它们没有覆盖该实际工厂/流式调度退出场景。运行时代码及依赖文件
保持修复 SHA，未在验收中改变代码来把同一提交的失败改写为通过。

### 浏览器页面与重定向

使用浏览器真实输入合成用户 `container-tenant-a`，从显式
`/data_copilot/login/` 页面提交登录；进入 Chat UI，发送
“浏览器验收：请完成一次简短分析。”，页面独立显示 `local-copy-ok`，
发送按钮恢复空闲。该提示未包含预期答案，且服务端查询确认对应 thread 的
唯一 run 为 **error**；没有把部分答案渲染当作分析成功。

匿名进入 `/data_copilot/` 和点击“退出登录”均进入浏览器连接错误页。单独读取
无尾斜线登录地址，实际响应为 301：

```text
Location: http://127.0.0.1/data_copilot/login/
```

该跳转丢失本轮宿主端口 5669；显式带尾斜线地址返回 200。原 Nginx 配置
`listen 80` 和目录 `try_files` 在端口映射下产生该行为，仓库配置未修改。
登录/提交/答案渲染有页面证据，匿名入口、退出返回及成功 run 的完整正控未通过，
浏览器整体验收为 **FAIL**。只关闭本轮创建的页签；没有查询或输出浏览器凭据。

诊断初次新增用户使用 `.invalid` 邮箱，注册校验未通过；随后沿用既有测试的
`example.com` 合成格式。该执行器问题单独保留，不归为产品注册缺陷。

### 迁移补验

实际 `seed-head`、FastAPI restart、五服务 readiness 和 `verify --scenario head`
均通过；users/sessions/messages 的预置 canary 逐字段保留。随后仅删除本轮卷，
在新空库建立已知 legacy fixture，五服务启动并迁移至唯一 head
`b6f4e8c2a9d1`，legacy canary 逐字段保持且默认 user 角色有效。
这些结果证明本轮空库、head 重启和已知旧基线的受控迁移，不证明任意旧库、
完整 schema 指纹、备份/回滚或一致恢复。

### 清理与证据

本轮 Compose down 删除自有容器、网络及独立卷，移除独立前后端和 transport
镜像标签；按本轮 requirements 层及其后代、已确认的前端/transport source
精确 ID 回收 11 个缓存记录，随后再次查询确认这些记录不再存在。此前已回收的
三个 pnpm 中间层另见构建记录，未执行全局 prune。

按本轮 project label 查询 container/volume/network 均为空；原有五个运行容器
的完整 ID 集合及两个 `:local` 镜像 ID 与开始时一致，原 `python:3.12-slim`
标签 ID 也保持。清理完成时 C 盘剩余 `2997547008` 字节，约 2.79 GiB。
确认私有临时树没有 reparse point 后，导出源码、测试配置、模型替身、日志、
辅助脚本及含随机测试密钥的 state 均已删除；脱敏证据保留在
[本机五服务机器证据](local-five-service-evidence.json)，含构建时间/指纹、
完整安装清单、实际失败响应、租约快照、浏览器结果与清理记录。

本轮补验执行与记录已结束，但验收结果为 **FAIL**，任务 6 与验收 18/19
保持未勾。下一步为独立修复异步租约上下文与静态认证跳转，再重做相应验收；
生产 NO-GO、父子合计预算与真实模型效果等边界保持。

## Hosted 验收

Hosted 初次补验受 gh 缺失与未提交状态阻碍。用户随后授权安装 gh、
将修复/验收代码提交到新分支并推送。gh 2.103.3 已通过 winget 安装，
命令使用 Git 现有仓库凭据的临时 GH_TOKEN 认证；没有扩大组织权限。
已创建 PR #1 触发 pull_request 工作流，没有合并或推送 main。

本次 PR head 为 `8e552f393aafd919fcf564f2b43c9856e6ff71f9`，base 为
`3d4ac6dbb540d7f8a46430f3bc311c071d4ba438`；GitHub 测试合并提交为
`18ceda2d9ec907c0a9da9c842a737694b4f74696`。实际 fetch PR merge ref 后，
其 tree 与修复 head 均为 `3a5a0c41793aaf796b5bf4303ed3ed9644d45b24`，
差异为空。Hosted run 的 head SHA 对应修复，checkout 的 PR 合并树与修复代码
一致；它不是 main push 或合并后发布验收。

run 时间为 `2026-10-27T12:51:55Z` 至 `2026-10-27T12:55:55Z`；
`gh run watch --exit-status` exit 0，最终查询为 completed/success。

| Job | ID | 最终结果 | 验证范围 |
| --- | --- | --- | --- |
| Backend | 122199251342 | success | Ubuntu 后端 **602 passed**、isort；包含图复制四调用面与真实 TCP HTTP 回归 |
| Frontend | 122199251308 | success | typecheck、lint、format、build |
| Release Contracts | 122199250889 | success | 差异、Compose 静态配置、发布契约 |
| Container Smoke | 122199251283 | success | 源码 SHA 核对、隔离镜像/五服务、空库、Redis canary、head 重启、known legacy 升级及资源清理 |

Linux 的图复制与 TCP 请求链由 Backend 回归验证；Linux 镜像的实际容器路径由
Container Smoke 验证。它们均使用非生产控制数据，不代表付费模型任务、任意旧库、
生产恢复或所有部署模式已通过。CI 的 Actions 内部 Node.js 运行时迁移和
ubuntu-latest 标签迁移提示属于非失败注释，不混同于项目 Node 22 契约。

本轮全量后端 **602 项通过，90.11 秒，exit 0**，包含新增真实 TCP HTTP
回归。之后仅给验证脚本增加“必须使用新的私有临时目录”保护，定向 HTTP
回归 **1 项通过，30.23 秒，exit 0**。isort、发布契约与差异检查通过。
运行时修复文件指纹保持不变，前轮审计原值、历史记录和未提交文档保留。

正常试验的子进程及临时目录均自动清理。被停止的早期试验留下的唯一目录
`dda-graph-http-h77fxypk` 已在确认归属、没有 reparse point 后删除，exit 0；
本轮 HTTP 进程已退出。没有删除用户缓存、项目状态、Docker 卷或真实配置。
本机 Engine 已恢复，受限及新镜像回归通过；本机完整五服务已重建，实际图运行
与浏览器整体验收失败，不能由 Hosted 冒烟替代。PR 保持 OPEN，尚未合并。
本地治理文档改动保留，未纳入这次仅四个代码文件的提交。
