# Changelog

本文件记录 Deep Data Agent 的用户可见行为、质量契约、验证证据和已知风险。版本号
用于仓库里程碑；是否形成正式发布标签，以 Git 中实际存在的标签为准。

## [Unreleased]

### 合计预算、依赖锁与恢复门禁（2026-10-28）

- 同一 run 的父子、摘要和 SDK 重试共用原子账本；模型发送前预留，
  工具执行前扣额，取消不退额，分支拒绝持续到顶层且不写成功缓存。
- 启动迁移前识别完整 schema；未知或漂移结构显式拒绝，不自动 stamp。
  保留已知 legacy/迁移 head 的正确升级路径。
- API 升至 active minor `0.16.8`，建立包含传递依赖、跨平台条件和 SHA-256
  的安装锁；Docker/Hosted 强制哈希安装。新锁 Windows 733 项回归通过，
  真实 MySQL 20 控制例和真实 Redis/TCP 20 预算控制例通过。
- LangGraph 主历史挂载独立卷；增加三域停写备份、清单/归档兼容性与空目标
  校验、独立恢复演练及负控。四 Hosted Job 检出 PR head 精确 SHA，
  新增 Chromium 认证/对话和全域恢复门禁，执行结果以对应 SHA 回执为准。
- Hosted 修复轮使匿名断言严格匹配新锁 API 的 401；浏览器控制器延后加载
  HTTPX，恢复在成功 bootstrap 后独立执行。恢复端口识别同端口双栈绑定；
  内存脚本通过子进程输入管道发送，归档保持文件流式传输。
  相关回归先红后绿，恢复/锁/浏览器定向 44 项通过；历史失败轮保留在
  [运行时记录](.trae/specs/stabilize-delivery-baseline/validation.md)。
- 实施 SHA `1910fdf` 的 Hosted run `40635353761` 四 Job 全部成功：
  Linux 后端 733 项、135 个活动包锁匹配、预算/MySQL 各 20 项、
  新锁五服务和 Chromium 七项通过。三域独立恢复实测 31.757 秒，
  确认写入丢失 0；六项备份负控、非空目标拒绝、head/legacy 与清理通过。
  最终文档提交自身的精确 SHA 回执存工作区根，不预写未来运行结果。
- 本机新锁 Linux 构建因磁盘保护中止；未以不完整下载的哈希改写锁。
  前轮证据与任务勾选保留，生产持久业务 NO-GO；人工快照不承诺自动
  异地备份、生产运行时或真实模型效果。

### 修复静态认证跳转并重验五服务（2026-10-28）

- Nginx 使用相对 Location，修复登录及目录跳转丢失宿主映射端口；新增真实
  HTTP 的 Origin/端口/路径/查询回归门禁并接入 Container Smoke CI。
- 从当前工作树与原 Dockerfile 重建生产静态镜像。前端四门禁、新后端镜像
  194 项回归与 pip check、五服务健康、双用户/管理员/文件隔离均通过。
- 浏览器匿名入口、登录、对话、深链接刷新、错误密码、退出与再登录通过；
  正常 run 最终 success，取消 interrupted，timeout 为稳定 agent_timeout。
  LangGraph 5 次、FastAPI 1 次租约取得/释放相符，各结束点无 lease key。
- 两次 Redis 故障自动恢复、空库/head 重启/known legacy canary 迁移通过。
  原启动命令保持，模型仅为隔离 HTTP/SSE 传输替身。IDE 浏览器桥接两次超时后，
  本机浏览器完成剩余 UI 检查；未将工具超时认定为产品失败。
- 本轮独立资源已清理，原五个业务容器及缓存镜像保持。未改历史任务勾选、
  未提交/推送/合并；本轮 Hosted、合计预算、恢复与真实模型等门禁保持，生产
  仍 NO-GO。条件、版本、指纹及机器证据见
  [本轮部署验收](.trae/specs/repair-static-auth-redirect/validation.md)。

### 修复流退出的身份上下文与租约释放（2026-10-27）

- `repair-async-lease-context` 将异步图执行、deadline、身份绑定与关闭放入
  同一个受控 Task；容量为 1 的队列保持背压，消费者关闭/取消时等待清理。
  重复取消不会打断已开始的清理，清理异常继续传播。同步流使用私有 Context。
- 两种租约上下文的 reset 与 release 分别由 `finally` 保证，身份清理异常
  仍尝试一次释放。嵌套单租约、复制、身份、预算与错误映射合同保留。
- 新增 17 项回归，全量后端 **619 项通过，89.67 秒**；真实工厂 TCP HTTP
  wait/stream/取消/timeout 与身份负控通过，4 次租约取得及释放相符。
  前轮部署精确依赖下 Linux **194 项通过，17.00 秒**，独立 Redis 的
  真实 HTTP 4 次取得/释放相符、最终 DB 为 0 个 key。isort 与发布契约通过；
  环境、源码及控制条件见
  [本轮验收](.trae/specs/repair-async-lease-context/validation.md)。
- 前轮五服务失败证据保持；静态认证跳转尚未修复，未重跑完整五服务/浏览器，
  未提交或推送，本轮工作树未取得 Hosted 证据，生产仍 NO-GO。

### 本机当前源码五服务验收（2026-10-27）

- 从提交 `8e552f3` 与原 Dockerfile 重建独立前后端镜像。后端使用文件系统
  不变、仅指定清华 PyPI 地址的临时基底；未修改源码、依赖文件或全局配置。
  实际依赖重新解析为 DeepAgents 0.7.32、LangGraph 1.2.18、API 0.7.28，
  新镜像 **150 项通过，12.29 秒**，pip check 与容器源码指纹核对通过。
- 五服务健康、空库/双用户/受管文件冒烟、Redis 故障自动恢复、head 重启和
  known legacy canary 迁移通过；原有容器与镜像保持，本轮独立资源已清理。
- **本机完整联调未通过**：实际 LangGraph 工厂图的 wait/stream 退出发生
  身份 ContextVar reset 异常，随后租约释放未执行；取消请求虽为 200，
  run 为 error，新增 Redis 租约在 10 秒内未释放。
- 浏览器从显式登录页可登录、提交并渲染测试答案，但 run 为 error；
  匿名入口/退出登录的 301 跳转丢失宿主端口。任务 6 与验收 18/19 未勾，
  先独立修复异步租约上下文和静态认证跳转，再继续合计预算。
- Hosted 与既有复制回归保留其原通过范围，生产仍 NO-GO。完整条件、
  失败响应和清理证据见 [补验记录](.trae/specs/repair-agent-graph-copy/validation.md)。

### 本机 Linux 容器补验（2026-10-27）

- 用户启动 Engine 后确认 Docker 29.4.1 Linux/amd64 可用。使用缓存依赖镜像
  和只读当前源码，在无外部网络、只读根与有界 RAM 临时目录的容器中运行
  复制/TCP HTTP 回归，**150 项通过，18.81 秒**；四文件源码指纹一致，
  自有容器自动清理，其他运行容器保持。
- 缓存环境为 Python 3.12.13、DeepAgents 0.7.6、LangGraph 1.2.11、
  API 0.7.28；它不是新建发布镜像，该阶段完整本机五服务重建/联调未执行。
  项目指南的系统盘 10 GB 为建议值；此前将其表述成硬门槛过严。
  完整镜像冒烟与当前 PR 的 Hosted 证据继续独立保留，见
  [补验记录](.trae/specs/repair-agent-graph-copy/validation.md)。

### 图复制修复的 HTTP 与部署补验（2026-10-27）

- 新增 `scripts/verify_agent_graph_http.py` 与 TCP HTTP 回归，运行安装版
  LangGraph API 的真实路由和 worker；wait/stream/state、身份与 owner 负控、
  复制依赖和取消释放十个断言通过。三次租约取得与释放相符。
- 使用测试模型/租约、隔离 SQLite/inmem 和动态测试签名密钥；启动时先初始化
  NumPy 2.5.2，避免本机首次在 worker 加载原生扩展的阻塞。该条件与结果一起
  记录，未修改产品运行时或依赖，未将替身证据等同于真实 MySQL/Redis/模型。
- 全量后端 **602 项通过**，isort、发布契约与差异检查通过；验证进程及本轮
  临时目录已清理，修复文件字节指纹保持不变。
- 本机 Docker 初查因磁盘和日志写权限阻碍未能运行，该状态保留。后续经授权
  安装 gh 2.103.3，四个代码文件提交为 `8e552f3` 并推送到 `fix/agent-graph-copy`。
- PR #1 的 run `40507150345` 四 Job 均 success：Backend 602 项通过；
  Frontend、Release Contracts、Container Smoke 成功。Linux 源码镜像空库、
  Redis 故障恢复、head 重启、known legacy 升级及清理均通过。
- PR 测试合并提交 `18ceda2d9ec907c0a9da9c842a737694b4f74696` 与修复 head
  代码树完全相同；PR 尚未合并，本机 Docker 未恢复，生产门禁仍保持。证据见
  [补验记录](.trae/specs/repair-agent-graph-copy/validation.md)。

### 修复 Agent 图复制后的运行失败（2026-10-27，本机离线验收）

- `repair-agent-graph-copy` 修复 `REV-A01`：`Pregel.copy` 用实例属性重建子类，
  原后置注入的 `_agent_lease_manager` 被基础构造器忽略。资源图现在显式接收
  并保存该依赖，工厂在构造时注入，复制后继续使用同一管理器。
- 保持 `CompiledStateGraph`、`copy`/`with_config`/重复复制与 API `get_graph`
  合同；原图不被修改，checkpoint/store 注入可实际读写。
- 新增 149 项离线回归，覆盖原图/复制图四种调用、真实 DeepAgents 工厂、
  两主体/请求 ID、递归覆盖、租约拒绝、模型/工具预算错误、同步 deadline、
  异步超时/取消和提前关闭流后的单次释放。
- Python 3.12.9 全量后端 **601 项通过**；isort、标准库发布契约与
  `git diff --check` 通过。使用离线模型/租约与内存存储，禁用 dotenv、
  追踪、自动 pytest 插件和字节码；未使用真实凭据、业务文件或模型/搜索。
- 本轮不升级依赖、不改前端或部署配置；父子/摘要合计预算 `REV-A02` 和
  REST 文件缓存 `REV-A03` 保持开放。下一轮为 `enforce-aggregate-agent-budget`。
- 未提交/推送、未验 Linux 镜像、真实 HTTP、Hosted 或生产。下方复审数字和
  A/B 原始判断保留为修复前快照；本机修复通过不解除其他生产 NO-GO 门禁。

### 项目现代化文档复审（2026-10-27，文档结论收口）

- `review-project-modernization` 的双独立复核与文档结论已收口，最终治理交付待
  独立验收；正式结论见 [项目分析](.trae/documents/project_analysis.md)，后续安排见
  [Roadmap](.trae/documents/roadmap.md)。12 个历史规格为 11 个功能迭代加 1 个
  audit，本轮另完成一次现代化 review 文档审查，不是第 12 个功能。
- 范围覆盖前后端、两个 Agent 入口、身份/租户、文件/缓存/预算、迁移恢复、
  构建部署、依赖、遗留模块及业务效果证据。保留第一方 JWT/current role、
  owner、固定 Origin、受管 UUID、Redis 恢复、浅 readiness 和既有发布门禁；
  不建议全量重写。主要业务短板是完整确定性计算、同源图表/报告与可取得产物。
- 48 个主来源为 18 AUD + 30 REV，另有 3 条历史追溯；A/B 各覆盖 51 条原值，
  主项 2/2、1/2、0/2 支持分布为 47/0/1，不是 47 个开放 bug。
  `AUD-004` 的 0/2 否定无条件完整关闭，两票 `exists_current=true` 指向同步
  Redis 残余 P2；原 `ainvoke` 修复与历史验收保留，合计预算单独归 `REV-A02`。
- **当前预算作用域修正**：8 次模型/12 次工具是主图局部 middleware 限额，
  父子 `task`、summary、retry 没有共享 run 总账。本机默认离线探针取得
  parent 2 + child 8 = 10 次模型、child 19 + parent task 1 = 20 次工具，
  child recursion 为 9999；仅将模型 limit 收紧为 1 时 summary + parent 实际
  调用 2 次、父计数 1。deadline、单次模型参数、身份与单租约保护仍有效；
  不代表所有 run 无保护，也未测实际收费、发生率或同步 IO 硬中断。
- `REV-A01`：本机 API 0.7.28 / LangGraph 1.2.11 / DeepAgents 0.7.5 的实际
  `copy`、`with_config`、API `get_graph` 复制路径丢失租约 manager，复制图调用
  报错；原始图四种调用面仍可用。条件 P1 限于该组合承担主 run 的复制路径，
  不是原图构造失败。本轮未修复，不外推 Linux 镜像、真实 HTTP 或生产。
- `REV-A03`：FastAPI REST 回答缓存 TTL 24 小时，未绑定文件活性/版本依赖；
  当前文件重新分析与显式历史快照合同须另定。仅影响 REST 回答缓存，不影响
  绕过该缓存的 LangGraph Chat UI；失效模拟不等于真实文件删除/过期 E2E。
- 优先前三轮为 `repair-agent-graph-copy` →
  `enforce-aggregate-agent-budget` → `deliver-controlled-analysis-slice`；
  UI 真实状态/行为回归、稳定兼容矩阵与评测设计可并行。代码修复、依赖升级和
  新功能分别另立规格，本轮只改文档，不实施这些建议。
- 生产持久业务与不可重建数据仍为 **NO-GO**：未知 schema 拒绝 `AUD-007`、
  身份/thread/file 一致恢复 `RR-001` 和目标部署运行证据未满足。
  schema/restore 门禁按相应持久目标触发，不锁定非敏感、可重建、隔离且不自动
  外发的统计开发；真实 owner/文件边界和有效资源限制仍是接入前置。
- 本轮代码基线为 `main` @ `3d4ac6dbb540d7f8a46430f3bc311c071d4ba438`。
  2026-10-27 基线 Agent 实际执行 Python 3.12.9 下 pytest **452**、迁移
  **8**、release contract pytest **159** 项通过；isort、发布契约脚本、
  Alembic 唯一 head `b6f4e8c2a9d1`、安全 Compose 静态解析和差异检查通过。
  本次文档同步未重跑上述门禁，不是用户给定的验收数据。
- 已有缓存 Node.js 22.22.2 / pnpm 10.5.1 下 typecheck、零警告 lint、
  format:check、build 通过；默认 Node.js 25.2.1 / pnpm 10.33.2 不符契约。
  Docker CLI 29.4.1、Compose 5.1.3、Desktop 4.71.0.225177 已安装，但
  `dockerDesktopLinuxEngine` pipe 缺失；`gh` 缺失，本 SHA 四个 Hosted Job、
  容器、浏览器 E2E、真实模型/搜索效果、成本、延迟及生产 restore 均未知或未测。
- 文档审查完成不等于运行/生产放行。下方 2026-08-21 等历史正文、预算说法、
  问题原等级、候选顺序与 SHA/run/Job/时间/当时未知限定逐字保留；
  历史 implementation、容器或浅 ready 证据不替代当前 exact-SHA 验收。

### 约束 Agent 资源使用（2026-08-21，本地与 Hosted 完成）

- `bound-agent-resource-use` 已完成本地实现与 implementation Hosted 验证，成为
  第 11 个已完成 change-id；Roadmap 余下 8 个候选，下一候选为
  `prove-data-recovery`。
- 新增 Agent、模型、搜索和 Redis 恢复预算配置、关系校验、Compose 默认值与发布
  契约。FastAPI 查询/最终响应默认上限为 8,000/32,000 个字符；每 run 默认
  60 秒、recursion 25、模型调用 8 次、工具调用 12 次。
- FastAPI AgentService 改为 async `ainvoke`；总 deadline 覆盖可取消 cache
  get/set 与图调用，timeout、取消、预算超限和超大响应不写缓存，并映射稳定错误码。
- FastAPI 与 LangGraph Agent 共用 Redis 原子全局 4/用户 1 双层租约，等待 1 秒、
  TTL 75 秒；管理员及客户端 config/context 不能扩大预算或伪造主体。
- `create_deep_agent` 接入 LangChain 模型/工具调用限制 middleware，并在同步与异步
  图入口强制服务端 recursion limit；ChatOpenAI 固定 45 秒 timeout、1 次 retry 和
  4,096 最大输出 tokens。
- 搜索改用异步 Tavily client，只暴露 `general`/`news`、最多 2,000 个字符 query
  和 5 条结果，执行 15 秒 timeout 与 64 KiB 输出上限。受管文档分析继续执行
  20,000 个字符硬上限，并计入共享 tool-call budget。
- Redis cache、rate limit 与 Agent lease 使用 1..30 秒单飞指数退避和有界抖动，
  故障后可无重启恢复。缓存及 auth/session/default 限流 fail-open；query 限流、
  Agent 租约和 readiness fail-closed。
- 新增 `/api/live` 与 `/api/ready`，`/api/health` 保留为 liveness 兼容别名。
  readiness 浅检查模型必要配置、MySQL、Alembic 唯一 head、Redis 与受管文件根，
  不调用模型或搜索；FastAPI/LangGraph Compose 和 Container Smoke 使用 readiness。
- **BREAKING**：任意 Python 执行工具、`ENABLE_CODE_EXECUTION`、Compose 传递、
  系统提示和注册路径已删除；残留部署变量不能恢复 `execute_python_code`。
- **BREAKING**：搜索 schema 不再暴露 raw content 或 images/videos/files topic；
  只接受 `general`/`news`，输出只保留有界字段。
- Python 3.12.9 下全量 pytest **452 项通过**，迁移定向测试 **8 项通过**，
  release contract pytest **159 项通过**；isort、发布契约脚本、Alembic 唯一
  head、Compose 和差异检查通过。
- Node.js 22.22.2、pnpm 10.5.1 下 `typecheck`、零警告 `lint`、`format:check`、
  `build` 全部通过。
- Docker Engine 29.4.1、Docker Desktop 4.71.0、Compose 5.1.3 下 empty、head、
  legacy 与 Redis stop/start canary 全部通过；Redis 停止时 live 保持 200、ready
  转 503、Agent fail-closed，恢复后后端无需重启。模型/搜索调用为 0，容器、网络、
  卷、临时配置和生成物已清理。
- implementation SHA `1090c3ea0954e84cc2cb6b945ef8c3913393cec8` 的 GitHub
  Actions run `32431502248`（2026-08-21T00:08:27Z..00:11:51Z）为
  `completed/success`；Backend `96623829169`、Frontend `96623829344`、Release
  Contracts `96623829444`、Container Smoke `96623829378` 均为 `success`。
- 最终验收文档提交只有在其自身 exact SHA 的上述四个 Hosted Job 全部成功后才
  成立；创建本记录时最终 SHA 与 run ID 尚未知，不记录推测值，也不以
  implementation run 代替最终证据。
- 历史 18 项新增关闭 `AUD-004`、`AUD-008`、`AUD-009`，当前开放
  **8 项：0 P0 / 1 P1 / 6 P2 / 1 P3**；`RR-004` 以删除运行时代码执行收口，
  `RR-006` 以固定 Redis 策略矩阵和自动恢复收口。生产仍为 **NO-GO**：唯一剩余
  P1 `AUD-007` 与 `RR-001` 的迁移/备份恢复边界尚未关闭。

### 隔离文件摄取（2026-08-17，本地与 Hosted 完成）

- `isolate-file-ingestion` 已完成本地验收，成为第 10 个已完成 change-id；Roadmap
  余下 9 个未启动候选。`DEC-004` 已确定 MySQL owner metadata + 受管共享卷 +
  opaque UUID，LangGraph thread 只保存引用。
- **BREAKING**：`analyze_document` 不再接受服务器路径，只接受 owner 绑定 UUID
  `file_id`；新上传只支持严格 UTF-8 TXT/Markdown/CSV/JSON。JPEG、PNG、GIF、
  WebP、PDF 和其他二进制 Base64 新上传已移除，历史 block 仅兼容只读显示。
- 新增 `managed_files` 模型和线性 migration `b6f4e8c2a9d1`，记录 owner、随机
  UUID、规范媒体类型、大小、SHA-256、内部 storage key、创建和过期时间。
- 新增 `file.read_own`、`file.write_own`、`file.delete_own` 与认证文件 API；
  路由/服务双层 owner 过滤，管理员不绕过，跨用户统一资源不可见。
- 上传在 multipart 解析前限制 11 MiB 请求体，并强制每批 5 个、单文件 5 MiB、
  批次 10 MiB、每用户 100 个/100 MiB、默认 168 小时保留。文件名、扩展名、
  MIME、UTF-8/NUL、JSON、CSV 公式、重复和整批事务均 fail-closed。
- `analyze_document` 只暴露 `file_id`；主体从隐藏
  `langgraph_auth_user_id` 恢复。打开文件前再次验证 owner、受管根、普通文件、
  非符号链接、大小和 SHA-256，错误/事件不输出文件名、内容、路径、ID 或哈希。
- 前端选择、拖放、粘贴共用同一受管上传函数，新增附件图标、上传中、metadata
  预览和草稿删除；新 thread payload 不含 Data URL/Base64。
- 发布契约新增文件配置、模型/路由/服务/工具/前端、共享卷、任意路径、Base64
  上传和远程构建字体门禁。Next.js 构建改用系统 sans 字体，不再依赖 Google Fonts。
- Python 3.12.9 下 `python -B -m pytest -q` 共 **295 项通过**，迁移定向测试
  **8 项通过**；isort、发布契约、Alembic 唯一 head、Compose 和差异检查通过。
- Node.js 22.22.2、pnpm 10.5.1 下 `typecheck`、零警告 `lint`、`format:check`、
  `build` 全部通过；无凭据 Chromium mock 验证附件预览、删除 API 与草稿移除。
- Docker Linux Engine 当前源码五服务的空库双用户、head 重启和 legacy 升级均
  通过；文件场景覆盖上传/列表/分析/删除、FastAPI/LangGraph 共享卷、跨用户与
  管理员拒绝、非法 JSON、超限和资源不变。全程未调用模型、搜索或生产数据，
  容器、网络、卷、临时配置和生成物已清理。
- 历史 18 项新增关闭 `AUD-002`、`AUD-005`，当前开放
  **11 项：0 P0 / 3 P1 / 7 P2 / 1 P3**。生产仍为 **NO-GO**；`AUD-004`、
  `AUD-007`、`AUD-008` 三个 P1 及 `RR-001` 等边界未扩大。
- implementation SHA `9fe0c40bd66a01db427fe37169a0ec0f65f24f85` 的 GitHub
  Actions run `32008059164` 为 `completed/success`；Backend、Frontend、Release
  Contracts、Container Smoke 四个 Job 全部成功，Container Smoke 的空库双用户、
  head 重启、legacy 升级和 cleanup 均成功。

### 保护 Agent 租户边界（2026-08-17，本地与 Hosted 完成）

- `secure-agent-tenant-boundaries` 已完成本地验收，成为第 9 个已完成 change-id；
  Roadmap 余下 10 个未启动候选。`DEC-001` 已确定 LangGraph threads 为 Chat UI
  对话主数据、MySQL users/RBAC 为身份主数据且不双写；`DEC-002` 已确定使用当前
  LangGraph 自定义 Auth，不新增 FastAPI 流式代理。
- **BREAKING**：FastAPI `/api/query` 现在要求第一方 JWT，无效或匿名请求返回
  `401`；LangGraph thread/run/assistant 资源要求同一 JWT，锁定的
  `langgraph-api 0.7.28` 对认证失败返回 `403`。
- LangGraph Auth 每次从 MySQL 加载当前用户和角色，使用数据库用户 ID 作为稳定
  identity；全局默认拒绝，thread/run 强制 owner metadata/filter，管理员不绕过
  所有权，assistant 搜索/读取固定到 `agent` graph，写操作保持拒绝。
- FastAPI 增加 `agent.invoke_own` 路由与服务双层授权；Agent 缓存键包含用户、
  模型、Base URL、温度、工具策略版本和查询，仅持久化 SHA-256 摘要，阻止相同
  查询跨用户复用。
- 前端删除 `apiUrl`/`assistantId` 查询状态、连接表单、LangGraph API Key 输入、
  `X-Api-Key` 和旧 Key 读写；只使用构建时 Agent URL/assistant，并从
  `sessionStorage` 向固定 Agent Origin 发送第一方 Bearer JWT。启动时只删除旧
  `lg:chat:apiKey`。
- 发布契约新增 LangGraph Auth、owner 授权、固定 Agent Origin、旧 API Key 禁止和
  Bearer JWT 检查。Container Smoke 新增双用户隔离，覆盖固定 assistant、伪造
  owner、并发重复搜索、跨用户 history/state/copy/读改删/create_run、管理员不
  绕过、拒绝后资源不变和无 MySQL 双写。
- Python 3.12.9 下 `python -B -m pytest -q` 共 **250 项通过**，迁移定向测试
  **7 项通过**；isort、发布契约、Alembic 单 head、Compose 解析和差异检查通过。
- Node.js 22.22.2、pnpm 10.5.1 下 `typecheck`、零警告 `lint` 和
  `format:check` 通过；同一前端源码已有 `build` 通过证据。本次最终本地重试仅因
  无法获取 Google Fonts 而失败；目标 SHA 的 Hosted Frontend Job 已完成生产构建
  并成功。
- Docker Linux Engine 从当前源码重建五服务后，空库双用户、head 重启和已知
  legacy 升级三场景均通过；只使用专用假配置和不可外连模型地址，未调用模型、
  搜索或业务查询，容器、网络、卷、临时配置和生成物均已清理。
- 历史 18 个问题中新增关闭 `AUD-001`、`AUD-003`，当前开放
  **13 个：1 P0 / 3 P1 / 8 P2 / 1 P3**；生产仍为 **NO-GO**。容器中的
  `langgraph-api 0.7.28` 已 EOL，其升级与兼容回归归入 `AUD-006`，本轮未扩大
  依赖升级范围。
- implementation SHA `9699f90f6fd2a90d63d82728208fb656cb4fe8e3` 的 GitHub
  Actions run `31994602064` 为 `completed/success`；Backend、Frontend、Release
  Contracts、Container Smoke 四个 Job 全部成功，Container Smoke 的空库双用户、
  head 重启、legacy 升级和 cleanup 均成功。

### 恢复运行时发布门禁（2026-08-16，本地与 Hosted 完成）

- `restore-runtime-release-gates` 已按本地与 Hosted 证据标为第 8 个已完成
  change-id；Roadmap 余下 11 个未启动候选继续按风险驱动排序。
- 后端镜像现包含 `alembic.ini` 和完整 `migrations/` 运行资产；发布契约新增镜像
  资产检查，并将凭据内容扫描扩展到全部 Git 跟踪文本和非忽略的待提交文本，同时
  保持二进制跳过、允许样例及错误输出脱敏。
- GitHub Actions 新增独立 Container Smoke Job，从目标 SHA 的干净 checkout
  构建前后端镜像，验证空库、已在 head 和已知旧基线三类 MySQL 状态，并在失败时
  只输出有界脱敏诊断、无条件清理容器资源和临时配置。
- Python 3.12.9 下 `python -m pytest -q` 共 **189 项通过**，
  `tests/test_migrations.py` 迁移定向测试 **7 项通过**；isort、发布契约、Alembic
  单 head/升级、Compose 解析和差异检查通过。
- Node.js 22.22.2、pnpm 10.5.1 下 `typecheck`、零警告 `lint`、
  `format:check` 和 `build` 均通过，前端任务生成物已清理。
- Docker Linux Engine 从当前源码重建镜像后，MySQL、Redis、FastAPI、LangGraph、
  Frontend 五服务均健康；FastAPI `/api/health`、LangGraph `/info`、Frontend
  `/data_copilot/` 三个 HTTP 端点通过。空库到达唯一 head `8f3c1b7a2d4e`，
  head 重启 canary 保持不变，已知旧基线升级后 canary 保持且角色回填为 `user`。
- 本地容器验收只使用专用假配置与不可外连的模型地址，不发送业务查询，未调用真实
  模型、搜索服务或生产数据；容器、网络、匿名卷、临时配置和生成物已完整清理。
- 历史审计仍识别 18 个 2/2 高置信度问题；当前工作树关闭 `AUD-014`、`AUD-011`
  和 `AUD-015`，开放项变为 **15 个：3 P0 / 3 P1 / 8 P2 / 1 P3**。生产发布仍为
  **NO-GO**，`AUD-006` 的可重复供应链、`AUD-007` 的未知 schema fail-closed 与
  其他既有边界均未扩大。
- implementation SHA `30e7992fa48c350a0b0ae8a6faa12c80cfe2202d` 的 GitHub
  Actions run `31959537002` 为 `completed/success`；Backend、Frontend、Release
  Contracts、Container Smoke 四个 Job 均为 `success`。Container Smoke 的空库、
  head 重启、legacy 升级和 cleanup 均为 `success`。

### 项目整体审计（2026-08-12，2026-08-16 交付复核）

- 本轮以 `main` @ `f6cf4e65d8b15114fc164fd6921bd65d6ad27862` 为锁定基线，
  审计浏览器与 Next.js 前端、FastAPI、LangGraph/Agent、MySQL、Redis、模型与
  工具、Docker Compose、GitHub Actions、迁移、认证授权、可观测性、发布契约及
  未接入主应用的 `utils/` 边界。
- Python 3.12.9 下 `python -m pytest -q` 共 **155 项通过**；后端格式、发布契约、
  Alembic、Compose 静态解析及前端类型、Lint、格式和构建门禁通过。
- 目标 SHA 的 GitHub Actions run `31554712031` 为 `completed/success`；Backend、
  Frontend、Release Contracts 三个 Job 均成功。
- 2026-08-16 在相同运行时代码基线上重跑 155 项后端测试、前端类型/Lint/格式/
  构建、发布契约、Compose 解析和差异检查；两名新的独立验证者再次逐项确认
  18/18 个最终问题，复核仅收紧证据边界，不改变严重度、数量或 Roadmap 映射。
- 两名独立验证者共同确认 **18 个 2/2 高置信度问题**；按 Spec P0-P3 定义最终
  裁决为 **4 个 P0、3 个 P1、10 个 P2 和 1 个 P3**。验证者原始 P1/P2 建议保留
  在 21 候选 × 2 验证矩阵中，不由最终裁决反写；当前生产发布判断为 **NO-GO**，
  本地开发与受控审计只能在项目分析记录的约束下继续。
- 去重与排除结果为：`AUD-013` 合并到 `AUD-010`，`AUD-021` 合并到 `AUD-006`；
  `AUD-019` 因 0/2 确认而排除，不进入问题清单或 Roadmap；项目分析附录保存了
  21 个候选的 42 条验证者存在性、原始 severity、理由、校正证据和最终动作。
- 审计当时的 Roadmap 将发现映射为 **12 个未启动后续候选**：
  `restore-runtime-release-gates`、`stabilize-delivery-baseline`、
  `secure-agent-tenant-boundaries`、`isolate-file-ingestion`、
  `bound-agent-resource-use`、`prove-data-recovery`、
  `harden-identity-administration`、`paginate-session-history`、
  `deliver-data-analysis-reports`、`rewrite-credential-history`、
  `define-production-hosting-boundary` 和 `persist-compliance-audit-records`。
  这些条目在审计时均为候选，不代表当时已经实现、启动或取得验收证据；当前状态
  以本节上方的运行时发布门禁记录为准。
- 本轮仅更新审计、Roadmap 与治理记录，无运行时代码、测试、依赖或部署配置变化。
  本轮未取得 Docker 五服务实际启动、容器内迁移或真实模型、搜索、业务数据等外部
  服务证据；Hosted CI 和静态 Compose 检查不能替代这些证据。

### 既有未发布行为变化

- 前端生产构建不再跳过 TypeScript 或 ESLint 错误，Lint 出现警告即返回非零。
- Node.js 运行范围固定为 22.x，pnpm 固定为 10.5.1，并严格使用锁文件安装。
- 后端使用 SQLAlchemy 2.x 声明式基类和明确 UTC 时间语义，同时保持现有无时区
  数据库字段、排序和 API 序列化兼容。
- 主分支推送和合并请求将自动执行后端、前端、Compose、配置漂移、凭据和工作区
  卫生检查；任一门禁失败都必须阻止发布。
- 第一方认证统一由 `NEXT_PUBLIC_REST_API_URL` 指向 FastAPI；已废弃的外部授权码
  登录配置从环境示例和运行文档中移除。
- 项目分析、Roadmap、README、环境示例和 AI 助手指南与当前五服务架构及认证边界
  对齐。
- FastAPI 全路由统一生成、校验并回传 `X-Request-ID`；前端 REST 与 LangGraph
  run 使用同格式诊断 ID。
- 后端日志改为 UTC JSON Lines，HTTP、Agent、模型、缓存和工具事件只允许固定
  低基数字段，并隔离第三方 logger。
- 本地文件与 Docker 日志增加大小和备份数量上限，避免日志无界占用磁盘。
- 新增人工诊断导出，可按请求 ID 生成倒序时间线，折叠健康检查并汇总 HTTP
  错误率、延迟、缓存降级和模型失败信号。
- FastAPI 层新增按身份维度的 Redis 固定窗口限流，对认证端点、`/api/query`、
  会话端点和全局默认四类分别计数：认证请求按 JWT `sub`、匿名按来源，四类配额
  与不同身份计数相互隔离；`/api/health` 永不受限，`RATE_LIMIT_ENABLED=false`
  可整体关闭。
- 超限返回稳定 `429`，错误体为 `{code: "rate_limited", message, request_id}`
  并附 `Retry-After`；既有 401/404/503 语义不变。
- Redis 不可用或出错时限流 fail-open 放行，并发出脱敏 `rate_limit.degraded`
  事件；限流事件只含维度类别、路由模板、配额键摘要、窗口与计数。
- `TRUSTED_PROXY_COUNT` 默认 `0`，不信任 `X-Forwarded-For`，伪造转发头不改变
  匿名计数键。
- 新增限流环境变量契约与发布契约检查（`RATE_LIMIT_ENV_DEFAULT`），并补充覆盖
  配额默认值的确定性契约测试。
- 引入 Alembic 版本化迁移与初始基线（`users`、`sessions`、`messages`），
  `alembic.ini` 与 `migrations/` 复用应用配置和共享 `Base.metadata`。
- 数据库初始化改为迁移驱动：全新库 upgrade 到 head、由旧 `create_all` 建立的
  一致数据库 stamp 到基线，对已处于 head 的库幂等；不重建也不删除已有数据。
- 新增 `MIGRATION_HEAD` 发布契约校验，静态确认 `migrations/versions` 存在且
  head 唯一。
- 新增迁移确定性测试，覆盖干净 SQLite 升级到 head 建出等价 schema、模型与迁移
  无漂移以及 head 唯一；本地全量确定性测试为 134 项通过。
- 用户新增固定 `user`/`admin` 角色；新注册用户及从初始基线升级的既有用户均
  默认为 `user`，数据库使用非空字段、固定值约束和线性 Alembic revision。
- 新增默认拒绝权限矩阵，以及 `GET /api/admin/users` 和
  `PATCH /api/admin/users/{user_id}/role`；路由和服务层分别授权，普通用户返回
  稳定 `403`，管理员不能修改自己的角色，也不能跨用户访问会话。
- 新增人工 `scripts/bootstrap_admin.py --user-id <id>` 引导；只允许把既有用户
  提升为管理员，不接受用户名、邮箱、密码或 Token，重复执行保持幂等。
- 管理员列表、角色变更、授权拒绝和人工引导接入 UTC 结构化审计，身份仅使用 JWT
  密钥派生的 HMAC 引用。
- 注册和 `/api/auth/me` 返回固定角色，前端严格解析但不以浏览器角色字段替代后端
  授权；CORS 白名单增加 `PATCH` 支持。
- 发布契约新增默认角色、角色约束、环境自动提权和审计身份字段门禁；全量确定性
  测试扩展到 155 项。
- Alembic 配置同时声明新版 `path_separator` 与兼容键
  `version_path_separator`，消除 Python 3.12 虚拟环境中的配置弃用警告。

### 既有迭代验证证据

- `python -m pytest -q`：155 项通过；
  `python -m isort --check-only data_agent tests scripts`：通过。
- 新增 28 项确定性测试，覆盖请求 ID 校验与传播、CORS 关联头、LangGraph 配置、
  结构化字段白名单、异常脱敏、轮转配置、诊断过滤、倒序、折叠、指标、告警信号
  和发布配置漂移。
- 前端 `pnpm typecheck`、`pnpm lint`、`pnpm format:check` 和 `pnpm build` 四项
  门禁通过；构建后再次执行 `pnpm lint`，仍以零警告通过。
- CI workflow 与 release contract 的本地等价检查通过，包括 Compose 配置、
  配置漂移、凭据和工作区卫生契约。
- 目标提交 `14b1b8ee42351cc446febfa9695761be402ae7e7` 的 GitHub Actions run
  `31353045802`（https://github.com/jwj911/deep_data_agent/actions/runs/31353045802）
  为 `completed/success`；Backend、Frontend 和 Release Contracts 均为
  `completed/success`，`head_sha` 精确匹配 `main` push。
- 发布镜像为后端
  `sha256:c504a231c0c500994805be6fd022f1a633fd16a8d3b12e0f681b1d4c51f4acab`
  与前端
  `sha256:a5c839ffa0ea6ae3791532f83c43e9fe358bebb38d6c4d77c91d2d844214cb21`。
- MySQL、Redis、FastAPI、LangGraph 和前端 5 个服务均为 `healthy`；宿主端口为
  `3307`、`6380`、`8000`、`2024` 和 `3000`。
- 双用户 HTTP 冒烟通过：A/B 注册、登录和 `/me` 均返回 200；B 创建会话并写入
  1 条消息返回 200；A 读取、写入和删除 B 的会话均返回 404，B 再次读取仍为
  1 条消息；无 Token 访问会话返回 401。
- CORS 预检通过：`http://localhost:3000` 返回 ACAO，
  `https://evil.example` 不返回 ACAO；FastAPI 健康检查、LangGraph `/info` 和
  前端 `/data_copilot/` 均返回 200，前端根路径返回 302。
- 冒烟临时数据已定向清理：前置 `users/sessions/messages=2/1/1`，删除
  `2/1/1`，后置 `0/0/0`；唯一系统 TEMP 脚本已删除。
- 本机 Node.js 25.2.1 会产生超出声明范围的本地警告；CI 与 Docker 使用受支持的
  Node.js 22，不受该本机版本警告影响。

### 已知风险

- 旧 Moonshot/Tavily 凭据已轮换失效，但旧值仍存在于 Git 历史。本轮接受该历史
  风险；历史重写延期到干净工作区，由人工协调所有协作者后执行。
- 宿主机 `3306` 或 `6379` 被占用时，MySQL 或 Redis 无法按默认端口启动。只允许
  通过 `.env` 中的 `MYSQL_PORT`、`REDIS_PORT` 重映射宿主端口，不能修改容器内部
  服务地址。
- 完整镜像构建和冒烟依赖 Docker Desktop Linux Engine、充足系统盘空间以及本地
  有效模型/JWT 配置。环境不满足时，不得把静态检查结果等同于容器发布证据。
- 当前锁定的容器运行时 `langgraph-api 0.7.28` 已 EOL；升级、依赖锁定和兼容
  回归仍归入 `AUD-006`/`stabilize-delivery-baseline`。
- 当前诊断能力使用本地轮转日志和 Docker 日志，不包含 OpenTelemetry、
  Prometheus、Grafana、长期存储或自动告警通知；这些能力需要单独评审访问控制、
  成本和保留周期。
- 请求限流为 Redis 固定窗口，非分布式令牌桶，也无自动封禁或黑名单；Redis 故障
  时 auth/session/default 按既定策略 fail-open，高成本 query 与 Agent 保护
  fail-closed。多实例全局配额与高可用 Redis 拓扑仍未建立。
- 版本化迁移当前是单 head 本地基线，测试用 SQLite、生产用 MySQL；尚无自动数据
  备份与回滚演练流程，升级前的备份与恢复须人工在受控环境执行。
- 当前 RBAC 只有固定 `user`/`admin` 角色，没有管理员前端、自定义角色、用户删除
  或跨用户会话权限；管理审计复用有界轮转日志，不是不可变长期审计存储或外部
  SIEM。

## [0.2.0] - 2026-08-10

### Added

- FastAPI 第一方注册、登录和 `/api/auth/me`。
- JWT 当前用户依赖、CORS 来源白名单和服务层会话所有权隔离。
- 双用户越权、Token 异常、输入校验和 CORS 确定性测试。

### Changed

- 前端登录改为用户名/密码注册与登录，第一方 Token 改存 `sessionStorage`。
- FastAPI 401 只清理第一方登录态，不受 LangGraph 或第三方 401/403 影响。
- 自动测试基线扩展到 60 项，五服务容器和双用户冒烟通过。

## [0.1.0] - 2026-08-09

### Added

- 独立的 LangGraph 图入口与 FastAPI 应用入口。
- MySQL 会话持久化、可降级 Redis 缓存和稳定的 Agent 错误语义。
- Next.js 静态前端连接层及 MySQL、Redis、FastAPI、LangGraph、前端五服务
  Docker Compose 闭环。

### Security

- 任意 Python 代码执行工具改为默认关闭，只允许在受控环境人工启用。
- 模型、搜索、数据库和缓存配置迁移到环境变量，示例文件只保留非生产占位值。
