# 隔离文件摄取 Spec

## Why

当前 `analyze_document` 默认注册并接受任意服务器路径，直接执行存在性检查和文本
读取；任何能够影响 Agent 工具调用的用户都可能读取容器配置、挂载文件或其他用户
文件。与此同时，前端只依据浏览器 MIME 选择文件，不限制数量或大小，并把图片/PDF
整体 Base64 写入 LangGraph thread，放大浏览器内存、请求体、线程存储和模型成本。

`secure-agent-tenant-boundaries` 已建立第一方主体和 thread/run owner，本轮必须把
该主体扩展到文件资源，关闭 `AUD-002` 与 `AUD-005`，再允许后续数据分析迭代消费
文件。

## Decisions

- `DEC-004`：选择**租户受管上传**，不继续支持任意服务器路径。MySQL 保存文件
  metadata 与 owner，本地受管目录/容器共享卷保存原始字节；Agent、前端和 API
  只使用随机 UUID `file_id`，不暴露或接受存储路径。
- 首期只允许严格 UTF-8 的 `.txt`、`.md`、`.csv`、`.json`。现有 JPEG、PNG、GIF、
  WebP 和 PDF Base64 上传是 **BREAKING** 移除项；在专用媒体/PDF 解析器、恶意
  样本和资源预算完成前保持拒绝。
- 默认限制为每批/每条消息最多 5 个文件、单文件 5 MiB、批次 10 MiB、每用户
  100 个文件与 100 MiB；所有限制由服务端强制，前端只做同值预检。
- 默认保留期为 7 天。上传、列表和分析会惰性清理当前用户的过期文件；用户可在
  到期前显式删除。当前本地卷没有备份，不扩大 `RR-001`。
- CSV 使用标准解析器检查结构，并拒绝去除前导空白后以 `=`, `+`, `-`, `@` 开头的
  单元格；JSON 必须能由标准 JSON 解析器完整解析。文本拒绝 NUL 和无效 UTF-8。
- LangGraph 将认证用户 ID 注入 `RunnableConfig.configurable` 的
  `langgraph_auth_user_id`。`analyze_document` 的模型可见参数只有 `file_id`；
  工具从隐藏配置恢复主体，再以 `file_id + user_id` 查询，管理员不绕过所有权。
- FastAPI `/api/query` 在直接调用本地图时注入同一服务端主体 ID，不能由请求体
  覆盖。缺失或非法主体时，工具在读取 metadata 或字节前默认拒绝。
- 文件名只用于当前用户 UI 和分析结果；日志、错误、审计和容器诊断不得输出文件名、
  内容、路径、主体原文、Token 或哈希。允许记录固定错误码、媒体类别、大小区间和
  请求 ID。

## What Changes

- 新增 `managed_files` 模型和线性 Alembic migration，记录 owner、随机 `file_id`、
  原始文件名、服务端媒体类型、大小、SHA-256、内部 storage key、创建和过期时间。
- 新增文件配置契约、受管存储服务、严格文件验证和过期清理；上传采用有界读取、
  随机内部文件名、原子替换和失败回收。
- 新增 `file.read_own`、`file.write_own`、`file.delete_own` 权限；FastAPI 文件
  路由与服务层执行双层默认拒绝。
- 新增认证文件 API：批量上传、列表、metadata、受控文本分析和删除。越权或过期
  统一返回资源不可见，不提供下载任意路径的接口。
- 用只接受 UUID `file_id` 的受管工具替换路径工具；读取时再次验证 owner、根目录、
  普通文件、非符号链接、大小和 SHA-256，输出按字符预算截断。
- 前端把选择、拖放和粘贴统一到同一上传函数；先上传 FastAPI，再向 LangGraph
  发送小型受管文件引用，不再生成或发送 Base64。
- 增加可见附件按钮、上传中状态、数量/大小/类型预检、失败恢复和删除未提交附件。
- 扩展发布契约与 Container Smoke，验证双用户上传/分析/删除隔离、恶意文件拒绝、
  FastAPI/LangGraph 共享卷和无 Base64 thread 写入。
- 同步 README、AGENTS、项目分析、Roadmap、CHANGELOG 与本规格；完成 25 项验收后
  创建原子实现提交，推送并等待目标 SHA 的四个 Hosted Job。

## Impact

- Affected specs:
  - `secure-agent-tenant-boundaries`
  - `secure-user-sessions`
  - `add-rbac-audit`
  - `add-versioned-migrations`
  - `add-request-rate-limiting`
  - `restore-runtime-release-gates`
  - `audit-project-roadmap`
- Affected code:
  - `data_agent/models/`
  - `data_agent/routes/`
  - `data_agent/services/`
  - `data_agent/tools/document_analysis.py`
  - `data_agent/tools/tool_manager.py`
  - `data_agent/config/`
  - `data_agent/agent_server.py`
  - `migrations/`
  - `agent_chatui/src/hooks/use-file-upload.tsx`
  - `agent_chatui/src/lib/`
  - `agent_chatui/src/components/thread/`
  - `.env.example`
  - `docker-config/docker-compose.yml`
  - `scripts/check_release_contracts.py`
  - `scripts/verify_container_smoke.py`
  - `tests/`
  - `README.md`、`AGENTS.md`
  - `.trae/documents/project_analysis.md`、`.trae/documents/roadmap.md`
  - `CHANGELOG.md`

## ADDED Requirements

### Requirement: 文件 metadata 与字节按 owner 受管

每个文件 SHALL 具有不可预测 UUID `file_id` 和不可变 `user_id` owner。数据库只
保存受控 metadata，原始字节 SHALL 写入配置的受管根目录；storage key 只能由
服务端生成且不得出现在 API、消息、日志或工具结果中。

#### Scenario: 成功上传

- **WHEN** 已认证用户上传满足格式与配额的文件
- **THEN** 服务端生成 owner 绑定的 `file_id`，原子写入随机 storage key，并返回
  不含路径和内容的 metadata

#### Scenario: 跨用户访问

- **WHEN** 用户 B 使用用户 A 的有效 `file_id` 读取 metadata、分析或删除
- **THEN** 路由与服务 owner 过滤返回 `404`，字节和 metadata 保持不变

#### Scenario: 管理员访问

- **WHEN** 管理员使用其他用户的 `file_id`
- **THEN** 管理员仍得到资源不可见语义，不绕过文件 owner

#### Scenario: 上传失败

- **WHEN** 验证、配额、文件系统或数据库任一步失败
- **THEN** 本批次不产生部分 metadata 或最终文件，临时文件被回收

### Requirement: 服务端强制格式、大小和配额

服务端 SHALL 在业务处理前限制文件上传请求体，并在逐文件验证中强制批次数、
单文件字节、批次字节、用户文件数和用户总字节。客户端声明的 MIME 不得作为唯一
依据。

#### Scenario: 支持的文本格式

- **WHEN** 扩展名、声明类型和内容共同符合 TXT/Markdown/CSV/JSON 契约
- **THEN** 服务端使用规范媒体类型保存，且内容可由严格 UTF-8 解码

#### Scenario: 伪造类型

- **WHEN** 扩展名、声明 MIME 或内容结构不一致
- **THEN** 服务端以稳定 `unsupported_file_type` 或 `invalid_file_content` 拒绝，
  不写入 metadata 或字节

#### Scenario: 超出限制

- **WHEN** 请求体、文件、批次或用户配额超过任一上限
- **THEN** 在有界读取内返回 `413` 或稳定配额错误，不继续解析或持久化

#### Scenario: CSV 公式

- **WHEN** CSV 任一单元格具有公式注入前缀
- **THEN** 整批 fail-closed，响应和日志不回显该单元格

### Requirement: Agent 只按隐藏主体分析 opaque file ID

`analyze_document` SHALL 只向模型暴露一个 UUID `file_id` 参数。工具必须从运行时
隐藏配置取得服务端认证主体，并在打开文件前执行数据库 owner 和文件系统不变量
校验。

#### Scenario: 有效 Agent 调用

- **WHEN** Agent 使用当前用户拥有且未过期的 `file_id`
- **THEN** 工具验证大小和 SHA-256 后返回有界文本与安全 metadata

#### Scenario: 路径输入

- **WHEN** 模型传入绝对路径、相对路径、穿越字符串或非 UUID
- **THEN** 参数验证或工具默认拒绝，且不会对该路径执行 `exists`, `stat`, `open`

#### Scenario: 伪造主体

- **WHEN** LangGraph 客户端在 config/context 中提交其他 `user_id`
- **THEN** LangGraph 服务端认证主体覆盖客户端值，工具只使用
  `langgraph_auth_user_id`

#### Scenario: 文件系统漂移

- **WHEN** storage key 越过根目录、目标是符号链接/非普通文件，或大小/哈希与
  metadata 不一致
- **THEN** 工具返回稳定拒绝，不输出路径、内容或底层异常

### Requirement: 前端只发送受管引用

浏览器 SHALL 先把文件发送到固定 FastAPI REST Origin，成功后只把 `file_id` 引用
写入 LangGraph message。选择、拖放和粘贴 SHALL 复用同一验证与上传函数。

#### Scenario: 上传并发送

- **WHEN** 用户选择允许文件并提交消息
- **THEN** FastAPI 收到 multipart 字节，LangGraph 只收到小型文本引用，不含
  Data URL 或 Base64 文件正文

#### Scenario: 客户端预检

- **WHEN** 文件类型、单文件大小、批次数或批次总大小超限
- **THEN** 前端在读取文件正文前显示错误并保持已有附件不变

#### Scenario: 删除未提交附件

- **WHEN** 用户从消息草稿移除已上传附件
- **THEN** 前端调用 owner 保护的删除 API，成功后才从草稿移除

#### Scenario: 上传失败

- **WHEN** REST API 返回 401、413、409 或验证错误
- **THEN** Token 过期沿用现有登录失效流程，其他错误保持草稿可恢复且不提交 thread

### Requirement: 保留、删除与观测保持有界

文件 SHALL 具有过期时间；列表、上传和分析 SHALL 惰性清理当前用户过期资源。
成功、拒绝和失败事件只能使用低基数安全字段。

#### Scenario: 到期资源

- **WHEN** 文件超过保留期后被列表或分析
- **THEN** metadata 与字节被回收，调用方获得资源不可见语义

#### Scenario: 显式删除

- **WHEN** owner 删除文件
- **THEN** metadata 与受管字节都被删除，重复删除返回资源不可见

#### Scenario: 诊断输出

- **WHEN** 上传、分析或删除成功/失败
- **THEN** 事件可由请求 ID 关联，但不包含文件名、内容、路径、file ID、哈希、
  主体原文或 Token

### Requirement: 容器与发布闭环验证文件边界

FastAPI 与 LangGraph SHALL 挂载同一受管文件卷。发布契约 SHALL 阻止任意路径工具、
前端 Base64 新上传和缺失文件配置/迁移/卷的变更。

#### Scenario: 双用户容器冒烟

- **WHEN** 用户 A/B 在空库五服务中分别上传脱敏文本样本
- **THEN** 各自可分析自己的文件，不能读/分析/删对方文件；恶意格式和超限样本
  拒绝，thread payload 不含 Base64，测试不调用模型或搜索

#### Scenario: 迁移兼容

- **WHEN** 空库、当前 head 和已知旧基线启动
- **THEN** `managed_files` 达到唯一 migration head，既有 canary 保持不变

#### Scenario: 远端交付

- **WHEN** 25 项验收完成并推送 `main`
- **THEN** Backend、Frontend、Release Contracts、Container Smoke 绑定目标 SHA
  且全部成功，本地与远端 SHA 一致、工作区干净

## MODIFIED Requirements

### Requirement: Agent 工具策略

默认工具集合仍包含 `analyze_document`，但其输入从服务器路径改为受管 `file_id`，
并要求运行时认证主体。缓存工具策略版本 SHALL 更新，避免旧路径语义结果复用。

### Requirement: 文件消息

新消息不再嵌入图片/PDF Base64。历史 thread 中已有 Base64 block 只保留兼容渲染，
不得重新上传、复制到新消息或解释为受管文件。

### Requirement: 数据主权边界

MySQL `managed_files` 是文件 metadata/owner 主数据，受管卷是原始字节主数据；
LangGraph thread 只保存引用。三者不做内容双写。

## REMOVED Requirements

### Requirement: 任意服务器路径分析

**Reason**: 路径没有租户所有权，允许读取容器可见的任意普通文件。

**Migration**: `analyze_document` 只接受服务端签发 UUID `file_id`；路径形式全部拒绝。

### Requirement: 浏览器 Base64 图片/PDF 上传

**Reason**: 客户端 MIME 不可信，且整体 Base64 造成无界内存、请求、thread 和模型
负载。

**Migration**: 新上传只支持受管文本格式。历史 block 可显示但不能作为新上传来源。

## Non-Goals

- 不支持 PDF、Office、压缩包、图片、音视频、OCR、病毒扫描或压缩内容解析。
- 不建设对象存储、跨实例共享、备份恢复、永久文档库、版本管理或跨租户共享。
- 不在本轮开放任意 Python、任意 SQL、自动数据分析、图表或报告导出。
- 不声称文本内容可信；文件内容只在用户明确发送并触发工具后进入模型上下文。
- 不解决 Agent 总超时、全局并发预算、Redis 自动恢复或生产托管边界。
