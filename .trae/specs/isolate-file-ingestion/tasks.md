# Tasks

- [x] Task 1: 锁定基线、DEC-004 和文件信任边界。
  - [x] SubTask 1.1: 记录 `main`、完整 HEAD/origin、干净工作区、250 项测试和最终
    Hosted 四 Job 基线。
  - [x] SubTask 1.2: 验证 `AUD-002` 任意路径工具与 `AUD-005` Base64 无界上传的
    真实可达调用链。
  - [x] SubTask 1.3: 确认 LangGraph `0.7.28` 将认证 identity 注入
    `langgraph_auth_user_id`，且 `RunnableConfig` 可作为模型不可见工具参数。
  - [x] SubTask 1.4: 批准 DEC-004：首期使用 MySQL owner metadata + 受管共享卷 +
    opaque UUID，格式只允许严格 UTF-8 TXT/Markdown/CSV/JSON。
  - 基线证据：`main`、HEAD/origin
    `e1d2548991e0806bf3e0a1e8d4021d150ff3e0c7`，工作区干净；Release Readiness
    run `31995503353` 的 Backend、Frontend、Release Contracts、Container Smoke
    均为 `success`，本地确定性测试为 250 项。

- [x] Task 2: 建立文件 metadata、配置、迁移和受管存储。
  - [x] SubTask 2.1: 新增 `managed_files` ORM 与线性 Alembic migration，包含 owner、
    UUID、媒体类型、大小、SHA-256、内部 storage key、创建/过期时间及必要约束。
  - [x] SubTask 2.2: 更新共享 `Base.metadata`、迁移导入、schema 对齐测试、空库/head/
    legacy 升级与 downgrade 数据保持测试。
  - [x] SubTask 2.3: 增加文件根目录、单文件/批次/用户配额、保留期和分析字符预算
    配置，并在 `.env.example` 与发布契约中固定安全默认值。
  - [x] SubTask 2.4: 实现严格文件名、扩展名、声明 MIME、UTF-8、JSON、CSV 和公式
    前缀验证；所有失败使用稳定错误码且不回显内容。
  - [x] SubTask 2.5: 实现有界批量读取、用户行锁配额、随机 storage key、原子写入、
    整批事务、失败清理和惰性过期回收。

- [x] Task 3: 增加双层授权文件 API 与请求体门禁。
  - [x] SubTask 3.1: 新增 `file.read_own`、`file.write_own`、`file.delete_own` 权限，
    `user`/`admin` 均只操作自己的文件。
  - [x] SubTask 3.2: 新增上传体有界 ASGI middleware，在 multipart 解析前限制
    `/api/files` 请求体，覆盖 Content-Length 与分块请求。
  - [x] SubTask 3.3: 新增认证批量上传、列表、metadata、分析和删除路由，路由层与
    服务层双重授权，跨用户/过期统一 `404`。
  - [x] SubTask 3.4: 确保 API 只返回安全 metadata/有界分析，不返回 storage key、
    绝对路径、哈希或原始异常。
  - [x] SubTask 3.5: 增加上传成功、整批原子性、匿名/未知角色、跨用户、管理员、
    重复、配额、到期和删除回归测试。

- [x] Task 4: 把文档工具改为 owner 绑定的 opaque file ID。
  - [x] SubTask 4.1: 将 `analyze_document` 模型可见 schema 收敛为 UUID `file_id`，
    从隐藏 `RunnableConfig` 读取 `langgraph_auth_user_id`。
  - [x] SubTask 4.2: 工具读取前再次验证数据库 owner、到期、受管根、普通文件、
    非符号链接、大小和 SHA-256；失败不输出路径、内容或主体。
  - [x] SubTask 4.3: FastAPI AgentService 直接调用图时注入服务端 actor ID，并更新
    Agent 工具策略版本和系统提示。
  - [x] SubTask 4.4: 增加路径/穿越/非 UUID、缺失主体、伪造主体、跨用户、符号链接、
    非普通文件、大小/哈希漂移和输出截断测试。
  - [x] SubTask 4.5: 验证生成的工具 schema 不暴露 config、owner、路径或 storage key。

- [x] Task 5: 收敛前端为同一受管上传事实源。
  - [x] SubTask 5.1: 新增固定 REST Origin 的文件客户端，复用第一方 JWT、请求 ID、
    401 登录失效语义和严格响应解析。
  - [x] SubTask 5.2: 选择、拖放和粘贴复用同一上传函数；强制 5 个/5 MiB/10 MiB
    客户端预检，但不把客户端检查当作授权。
  - [x] SubTask 5.3: 增加附件图标按钮、上传中/失败/移除状态与安全 metadata 预览，
    移除草稿附件时调用删除 API。
  - [x] SubTask 5.4: 向 LangGraph message 只写受管 `file_id` 文本引用；删除
    `fileToBase64` 和新图片/PDF 上传，历史 Base64 block 仅保留只读渲染。
  - [x] SubTask 5.5: 增加发布契约，禁止 `FileReader.readAsDataURL`、新 Base64 上传、
    任意路径工具参数及缺失文件 API/配额/卷。

- [x] Task 6: 建立恶意输入、容器与全量发布实证。
  - [x] SubTask 6.1: 扩展确定性测试，覆盖无效 UTF-8、NUL、伪造 MIME、双扩展、
    JSON 失败、CSV 公式、超大/超量/总量、重复和部分失败。
  - [x] SubTask 6.2: 扩展 Container Smoke：双用户上传/列表/分析/删除，验证跨用户
    与管理员拒绝、恶意格式/超限拒绝、thread payload 无 Base64。
  - [x] SubTask 6.3: 验证 FastAPI 与 LangGraph 使用同一受管卷，空库/head/legacy
    三场景达到唯一 migration head 且 canary 不变。
  - [x] SubTask 6.4: 运行 Python 3.12 全量 pytest、isort、发布契约、Alembic、
    Compose 和 `git diff --check`。
  - [x] SubTask 6.5: 使用 Node 22/pnpm 10.5.1 运行 typecheck、零警告 lint、
    format:check、build，清理 `.next`、`out`、`*.tsbuildinfo`。
  - [x] SubTask 6.6: 更新 README、AGENTS、项目分析、Roadmap、CHANGELOG：关闭
    `AUD-002`/`AUD-005`，记录 DEC-004、BREAKING 格式变化及剩余风险。
  - [x] SubTask 6.7: 独立执行 `checklist.md` 25 项；失败项先新增修复任务并复验。

  本地证据：Python 3.12.9 全量 **295 passed**，迁移定向 **8 passed**；isort、
  发布契约、Alembic 唯一 head `b6f4e8c2a9d1`、Compose 与 `git diff --check`
  通过。Node 22.22.2/pnpm 10.5.1 四门禁通过；Google Fonts 构建依赖已移除。
  五服务空库双用户、head 重启、legacy 升级及无凭据 Chromium 附件交互通过，
  资源与临时配置已清理。安全复核无可利用发现。

- [x] Task 7: 创建原子提交、推送并完成 Hosted 闭环。
  - [x] SubTask 7.1: 复核暂存范围、凭据、受管样本和生成物，只包含本轮必要改动。
  - [x] SubTask 7.2: 创建 `isolate-file-ingestion` 原子实现提交；远端前进时安全整合
    并重跑受影响门禁。
  - [x] SubTask 7.3: 推送 `main`，确认本地、origin 和 GitHub 完整 SHA 一致且工作区
    干净。
  - [x] SubTask 7.4: 通过 GitHub API 确认 implementation SHA 的 Backend、Frontend、
    Release Contracts、Container Smoke 全部成功。
  - [x] SubTask 7.5: 同步最终证据和 25/25 状态，推送验收记录，并等待最终 HEAD 的
    Hosted 四 Job 成功。

  Hosted 证据：implementation SHA
  `9fe0c40bd66a01db427fe37169a0ec0f65f24f85` 的 Release Readiness run
  `32008059164` 为 `completed/success`；Backend、Frontend、Release Contracts、
  Container Smoke 均为 `success`。Container Smoke 的空库双用户、head 重启、
  legacy 升级和 cleanup 均为 `success`。

# Task Dependencies

- Task 2、Task 3 依赖 Task 1；Task 3.1 可与 Task 2 的模型/迁移按文件边界并行。
- Task 4 依赖 Task 2 的 owner metadata 与存储不变量。
- Task 5 依赖 Task 3 的文件 API。
- Task 6 依赖 Task 2、Task 3、Task 4、Task 5。
- Task 7 依赖 Task 6 和清单前 24 项；第 25 项由 Task 7 的远端闭环完成。
