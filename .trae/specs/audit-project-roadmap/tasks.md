# Tasks

- [x] Task 1: 建立可重复审计基线：锁定当前主分支、工作区、规格状态和实际发布证据。
  - [x] SubTask 1.1: 记录审计日期、分支、完整 HEAD SHA、工作区状态，以及 `.trae/specs/` 中全部既有 change-id 的任务/清单完成度。
  - [x] SubTask 1.2: 使用 Python 3.12 虚拟环境执行后端 pytest、isort、发布契约、Alembic 单 head、Compose 解析和 `git diff --check`；执行前端 typecheck、lint、format:check、build，并清理生成物。
  - [x] SubTask 1.3: 查询目标 SHA 的 GitHub Actions 状态；无法取得 Hosted CI、Docker 五服务或真实外部服务证据时，明确记录为本轮证据缺口。

- [x] Task 2: 完成全仓库多维度审查：按真实调用链检查主应用、平台边界和遗留模块。
  - [x] SubTask 2.1: 审查 FastAPI、认证/RBAC、会话所有权、数据库迁移、Redis、限流、日志、诊断和管理员操作，形成后端/安全/数据候选问题。
  - [x] SubTask 2.2: 审查 LangGraph/Agent、模型与搜索调用、文件分析、代码执行、缓存键与资源边界，形成 AI/工具安全候选问题。
  - [x] SubTask 2.3: 审查 Next.js 前端、浏览器认证边界、流式线程、文件上传、图表路径和公开构建配置，形成前端/产品契约候选问题。
  - [x] SubTask 2.4: 审查 Docker Compose、GitHub Actions、Python/Node 依赖可重复性、发布契约、备份恢复和 `utils/` 遗留边界，形成平台/运维/依赖候选问题。
  - [x] SubTask 2.5: 合并重复发现，排除纯风格和无证据猜测，为剩余问题分配唯一 ID、P0-P3 严重度、最小新版本行号证据、影响、建议、依赖和验收条件。

- [x] Task 3: 独立复核审计发现：用两个验证者逐项确认存在性、证据和严重度。
  - [x] SubTask 3.1: 向两个独立验证者提供完整候选问题列表；每个验证者必须覆盖全部问题并返回存在性、建议严重度和理由。
  - [x] SubTask 3.2: 按 2/2、1/2、0/2 共识分别标记高、中、低置信度；排除低置信度误报，保留中置信度 caveat，并校正证据行号。
  - [x] SubTask 3.3: 形成按 P0→P3、阻塞关系和用户影响排序的最终问题表，以及不构成问题但需要人工决策的开放问题表。

- [x] Task 4: 刷新项目分析文档：把审计证据、当前架构、问题与剩余风险写入正式快照。
  - [x] SubTask 4.1: 重构 `.trae/documents/project_analysis.md` 为“范围与证据、当前架构、已验证能力、问题清单、开放决策、发布判断”，清理过时或冲突描述。
  - [x] SubTask 4.2: 增加展示浏览器、FastAPI、LangGraph、MySQL、Redis、模型和工具真实调用/认证边界的 Mermaid 流程图；强调节点同时设置填充色和文字色。
  - [x] SubTask 4.3: 写入最终 ID 化问题表，提供严重度、置信度、最小代码链接、影响、建议、依赖和验收条件；已实现能力与候选能力严格分开。

- [x] Task 5: 刷新 Roadmap：根据审计结论形成可直接转为正式 Spec 的迭代序列。
  - [x] SubTask 5.1: 保留已完成里程碑，按“近期阻塞项、中期业务能力、长期平台候选”重排后续 change-id；每轮写明目标、依赖、进入条件、范围、非目标、验收门槛和停止条件。
  - [x] SubTask 5.2: 为后续迭代增加 Mermaid 依赖流程图，标识串行阻塞、可并行工作和数据分析/报告能力的解锁路径，并使用高对比度填充色与文字色。
  - [x] SubTask 5.3: 将项目分析中的每个有效问题映射到一个 Roadmap 迭代、明确延期理由或风险接受决策，避免无归属问题和无法验收的大型候选。

- [x] Task 6: 同步治理记录并完成文档验收：确保项目现状、Roadmap 和变更记录一致。
  - [x] SubTask 6.1: 更新 `CHANGELOG.md`，记录审计范围、关键结论、Roadmap 调整和实际验证证据；仅在状态、命令或边界失真时定向更新 `README.md`、`AGENTS.md`。
  - [x] SubTask 6.2: 检查所有 Mermaid 语法、文档链接、审计 ID、状态日期、SHA、测试数字、迭代名称和依赖映射一致；确认未复制凭据、Token、业务数据或敏感日志原文。
  - [x] SubTask 6.3: 运行发布契约、`git diff --check` 和文档差异审查，确认本轮仅修改规格与治理文档，无运行时代码、测试、依赖或部署配置变化。

- [x] Task 7: 修复审计文档验收缺口并重新验证。
  - [x] SubTask 7.1: 补充当前工作区状态及 temp-file、chart、static-export、utils 门禁覆盖证据（对应 checklist #1、#8、#9、#11）。
  - [x] SubTask 7.2: 按 Spec P0-P3 定义重新分级并显式补充每项依赖，保存两个验证者对 21 个候选问题的 42 条验证矩阵，重排问题（对应 checklist #13、#15、#17、#19）。
  - [x] SubTask 7.3: 同步 Roadmap、`CHANGELOG.md`、`README.md`、`AGENTS.md` 的统计与名称，并重新运行全部 25 项验证。
  - [x] SubTask 7.4: 清理 `pnpm typecheck` 生成且被忽略的 `agent_chatui/tsconfig.tsbuildinfo`（前次验收实测存在），确认 `.next/`、`out/` 与 `*.tsbuildinfo` 均不存在后重新运行全部 25 项验收；最终验收 25/25 通过。

- [x] Task 8: 完成交付前独立复核与当前门禁复验。
  - [x] SubTask 8.1: 在 2026-08-16 对同一运行时代码基线重跑后端、前端、发布契约、Compose 解析和差异检查，并清理前端生成物。
  - [x] SubTask 8.2: 由两名新的独立验证者逐项复核 18 个最终问题；18/18 均取得 2/2 确认，严重度结论保持不变。
  - [x] SubTask 8.3: 收紧 `AUD-015`、`AUD-009` 和 `AUD-018` 的证据或反证边界，同步状态日期与变更记录，不改变问题数量和 Roadmap 映射。

# Task Dependencies

- Task 2 依赖 Task 1 的审计基线；SubTask 2.1-2.4 可并行执行。
- Task 3 依赖 Task 2 的完整候选问题清单；两个验证者必须并行且相互独立。
- Task 4 和 Task 5 依赖 Task 3 的最终问题清单，可分别编辑不同文档并行推进。
- Task 6 依赖 Task 4 和 Task 5。
- Task 7 依赖 Task 6 的文档草稿，或 Task 4-6 的当前成果。
- Task 8 依赖 Task 7 的 25/25 验收结果。
