# Deep Data Agent

Deep Data Agent 是一个前后端分离的 AI 数据探索项目。后端同时提供
FastAPI REST 服务和 LangGraph 图服务，前端使用 Next.js 静态导出，
MySQL 持久化 users/RBAC、既有 REST sessions/messages 与受管文件 metadata，
不是 Chat UI 主历史的存储；Redis 用于缓存、限流、Agent
并发租约与就绪保护。第一方注册、登录与角色由 FastAPI 提供；同一 JWT 同时保护
FastAPI Agent 入口与 LangGraph thread/run 所有权。前端、FastAPI、LangGraph、
Agent、工具与缓存使用请求 ID 和结构化脱敏事件形成轻量诊断链路。

## 服务与访问地址

| 服务 | 默认地址 | 用途 |
| --- | --- | --- |
| 前端 | `http://localhost:3000/data_copilot/` | 聊天界面 |
| LangGraph | `http://localhost:2024/info` | 线程与流式 Agent API |
| FastAPI | `http://localhost:8000/api/live` | REST API 与进程存活检查 |
| MySQL | `localhost:3306` | users/RBAC、REST sessions/messages 与受管文件 metadata 持久化 |
| Redis | `localhost:6379` | 缓存、限流、Agent 并发租约与就绪保护 |

## 完整文件统计（聊天与 API）

已上传的受管 CSV/JSON 可以在聊天或 API 中按列求和，计算覆盖完整文件，
不受文本预览 20,000 字符限制。唯一数值来源是后端 Decimal 统计服务，
`analyze_document` 仍只提供预览。

### 在聊天中求和

1. 登录后上传 CSV/JSON，在消息中明确目标文件和原始列名，例如：
   “对本次上传的 sales.csv 的 amount 列求和。”
2. `analyze_file_statistics` 只接受受管文件 UUID 和精确列名，指标固定为 `sum`；
   缺列名或多个附件选择有歧义时应先澄清，不默认选择首列或首文件。
   主体和当前角色由服务端取得，模型不能指定 owner、路径、表达式或资源限额。
3. 查看“完整文件统计 · 求和”卡片及来源，按需点击“校验来源并下载 JSON”。



## 环境准备

- Python 3.12
- Node.js 22.11 或更高的 22.x 版本
- pnpm 10.5.1
- Docker Desktop（运行完整容器栈时需要 Linux Engine）
- Docker 构建与运行前，建议确认系统盘至少有 10 GB 可用空间

## 恢复与生产门禁辅助脚本

恢复辅助脚本及公开合成评测集已纳入 `scripts/` 版本管理。工作区外层旧副本
仅属于历史交付；后续执行以下仓库入口，避免脚本与应用源码版本不一致。

| 入口 | 用途与证据边界 |
| --- | --- |
| `scripts/data_recovery.py` | 停写格式 1 三域快照及独立空目标恢复；1 GiB 总量、64 KiB 清单、每 tar 100,000 条目 |
| `scripts/verify_backup_transport.py` | 可信清单、完整快照集合、有界四文件下载及原子发布；不安装定时任务 |
| `scripts/verify_recovery_admission.py` | 真实本地 restic 的恢复拒绝、下载失败、目标保护及 Windows/Linux 原子发布回归 |
| `scripts/verify_production_support.py` | 离线模型参考与费用控制，以及真实本地加密/保留 dry-run/恢复负控 |
| `scripts/verify_production_runtime.py` | 只读前置盘点，不读取 `.env` 值，不启动生产运行时 |
| `scripts/verify_real_model.py` | 人工触发的有界提供方 pilot；缺进程 Key、准确价格及执行参数时不发送 |




## 本地配置

复制 `.env.example` 为 `.env`，再填写本地密钥：

```powershell
Copy-Item .env.example .env
```

`MOONSHOT_API_KEY` 是模型查询所需配置，`TAVILY_API_KEY` 仅在调用互联网
搜索工具时需要。示例文件中的占位值不会被当作有效密钥；真实 API Key、
JWT 密钥、密码和 Token 只能写入本地 `.env` 或部署环境，不能写入文档或提交。

Agent、模型与搜索的默认配置如下；8/12 是同一 run 的合计调用限额，
覆盖父子、摘要与重试（见“Agent 资源预算”）。模型与搜索上限只能收紧；Agent 配置必须为
正整数，并满足模型/搜索 timeout 不超过 run deadline、单用户并发不超过全局并发、
租约 TTL 大于 run deadline 等关系：

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| `MODEL_REQUEST_TIMEOUT_SECONDS` / `MODEL_MAX_RETRIES` / `MODEL_MAX_OUTPUT_TOKENS` | 45 秒 / 1 次 / 4,096 tokens | 单次模型请求预算 |
| `AGENT_QUERY_MAX_CHARS` / `AGENT_RESPONSE_MAX_CHARS` | 8,000 / 32,000 个字符 | FastAPI 输入与最终响应上限 |
| `AGENT_RUN_TIMEOUT_SECONDS` / `AGENT_RECURSION_LIMIT` | 60 秒 / 25 层 | run 总 deadline；父图与内联子图递归均受服务端约束 |
| `AGENT_MODEL_CALL_LIMIT` / `AGENT_TOOL_CALL_LIMIT` | 8 次 / 12 次 | 父子、摘要、SDK 重试共享实际请求与工具执行总账 |
| `AGENT_GLOBAL_CONCURRENCY_LIMIT` / `AGENT_USER_CONCURRENCY_LIMIT` | 4 / 1 | Redis 原子全局与用户租约上限 |
| `AGENT_CONCURRENCY_WAIT_SECONDS` / `AGENT_CONCURRENCY_LEASE_TTL_SECONDS` | 1 秒 / 75 秒 | 租约等待与异常回收边界 |
| `SEARCH_QUERY_MAX_CHARS` / `SEARCH_MAX_RESULTS` | 2,000 个字符 / 5 条 | 搜索输入与结果数上限 |
| `SEARCH_TIMEOUT_SECONDS` / `SEARCH_MAX_OUTPUT_BYTES` | 15 秒 / 65,536 字节（64 KiB） | 搜索调用与序列化输出上限 |
