# Tasks

- [x] Task 1: 建立请求关联与结构化事件基础：统一上下文、日志格式和 FastAPI
  中间件。
  - [x] SubTask 1.1: 增加请求 ID 生成、严格校验、上下文绑定和 LangGraph
    运行配置提取工具。
  - [x] SubTask 1.2: 将日志改为 UTC JSON Lines，使用固定事件字段白名单并覆盖
    消息、字段和异常脱敏。
  - [x] SubTask 1.3: 增加 FastAPI 请求中间件，回传 `X-Request-ID`，记录路由
    模板、状态码、结果和耗时，并对齐 CORS。
  - [x] SubTask 1.4: 让 `/api/query` 与 AgentService 复用请求上下文，不改变
    既有错误码和响应语义。

- [x] Task 2: 贯通前端、LangGraph、缓存、模型和工具事件。
  - [x] SubTask 2.1: 前端 REST 请求生成并发送 `X-Request-ID`，错误对象保留可
    展示的诊断 ID。
  - [x] SubTask 2.2: 每次 LangGraph 提交、重试和人工中断处理均通过
    `configurable` 与 `metadata` 传递请求 ID。
  - [x] SubTask 2.3: 缓存记录命中、未命中与降级事件，Agent 记录开始、完成、
    缓存命中、配置失败和模型失败事件。
  - [x] SubTask 2.4: 互联网搜索、文档分析和可选代码执行工具记录开始、完成与
    失败事件，不记录输入或输出正文。

- [x] Task 3: 建立有界日志保留与人工诊断导出。
  - [x] SubTask 3.1: 增加日志路径、轮转大小、备份数和服务名配置，Compose
    限制容器日志大小与文件数。
  - [x] SubTask 3.2: 实现 JSON Lines 解析、二次脱敏、请求 ID 过滤、倒序
    时间线和高频事件折叠。
  - [x] SubTask 3.3: 汇总 HTTP 请求数、错误率、平均/最大/P95 延迟、缓存降级
    与模型失败，并生成无外发副作用的告警信号。
  - [x] SubTask 3.4: 提供人工 CLI，支持标准输出或显式输出文件，错误信息不得
    回显无效输入内容。

- [x] Task 4: 完成回归测试、文档与发布验证。
  - [x] SubTask 4.1: 增加请求 ID、日志结构、脱敏、事件字段和 CORS 回归测试。
  - [x] SubTask 4.2: 增加诊断报告聚合、倒序、折叠、告警和无效输入测试。
  - [x] SubTask 4.3: 更新 `.env.example`、Compose、README、Roadmap、
    CHANGELOG 和发布契约说明。
  - [x] SubTask 4.4: 执行全量 pytest、isort、前端 typecheck/Lint/格式/构建、
    Compose 解析、发布契约与 `git diff --check`，清理生成物。

# Task Dependencies

- Task 1 是 Task 2 与 Task 3 的基础。
- Task 2.1 与 Task 2.2 可并行；Task 2.3 与 Task 2.4 依赖 Task 1 的事件 API。
- Task 3.1 可与 Task 2 并行；Task 3.2 至 Task 3.4 依赖 Task 1 的日志 schema。
- Task 4 依赖 Task 1、Task 2 和 Task 3。
