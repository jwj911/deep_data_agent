# Tasks

- [x] Task 1: 固化运行契约与依赖基线：整理 LangGraph、FastAPI、数据库、Redis 和前端公开地址的环境变量契约，补齐并去重 Python 依赖，确保示例配置不含真实凭据。
  - [x] SubTask 1.1: 明确 `NEXT_PUBLIC_API_URL` 表示浏览器可访问的 LangGraph 地址，并为 FastAPI、Redis 和高风险工具开关定义无歧义的配置项。
  - [x] SubTask 1.2: 补齐 SQLAlchemy、数据库驱动、Redis、JWT、密码哈希、表单解析、环境加载、测试和 `isort` 所需依赖。
  - [x] SubTask 1.3: 为缺失配置、Redis 降级和日志脱敏定义稳定行为。

- [x] Task 2: 拆分并修正后端服务入口：提供可加载的 `agent` 图与 FastAPI `app`，移动导入期副作用，默认关闭任意代码执行，并修正查询错误语义。
  - [x] SubTask 2.1: 将 Agent 图构建与 FastAPI 路由装配解耦，并更新 `langgraph.json` 的导出路径。
  - [x] SubTask 2.2: 将数据库初始化迁移到 FastAPI 生命周期，保证 LangGraph 图加载不依赖 MySQL。
  - [x] SubTask 2.3: 仅在显式配置时注册代码执行工具，并记录脱敏风险提示。
  - [x] SubTask 2.4: 让 Agent 异常向上抛出，由 API 映射为稳定的非 2xx 错误响应和可关联日志。

- [x] Task 3: 修复前端构建与连接一致性：补齐 `src/lib` 模块，统一有效连接配置，修正可选认证头与未配置登录入口时的行为。
  - [x] SubTask 3.1: 按当前 SDK 契约实现或恢复 `utils`、API Key、工具响应、Agent Inbox 与多模态辅助模块。
  - [x] SubTask 3.2: 让 Stream、Thread Client 和状态检查共享解析后的 LangGraph 地址、助手 ID 与请求头。
  - [x] SubTask 3.3: 省略空认证头，保留 API Key 与 JWT 各自的有效请求头，并移除未定义登录配置导致的构建错误。
  - [x] SubTask 3.4: 恢复 TypeScript 和 ESLint 构建门禁，修复所有暴露出的类型、Lint 与格式问题。

- [x] Task 4: 校正本地容器编排：从正确构建上下文生成后端与静态前端镜像，分别启动 FastAPI 和 LangGraph 服务，并为关键依赖增加健康检查。
  - [x] SubTask 4.1: 修正后端镜像对根目录依赖文件和 Python 包路径的访问。
  - [x] SubTask 4.2: 使用与静态导出模式一致的前端运行镜像，并在构建阶段注入浏览器可访问的 LangGraph 地址与助手 ID。
  - [x] SubTask 4.3: 修正 MySQL 驱动 URL、Redis 地址、端口、网络、持久卷和就绪依赖。
  - [x] SubTask 4.4: 运行 `docker compose config` 并构建全部项目镜像。

- [x] Task 5: 建立验证与运行文档：增加确定性后端测试，执行前后端质量门禁和容器冒烟检查，并更新项目说明。
  - [x] SubTask 5.1: 覆盖 FastAPI 健康检查、LangGraph 导出、缺失模型配置、Redis 降级、代码执行默认关闭和查询错误映射。
  - [x] SubTask 5.2: 执行后端测试与 `isort --check-only`。
  - [x] SubTask 5.3: 执行前端类型检查、Lint、格式检查和生产构建。
  - [x] SubTask 5.4: 启动 Compose 栈并验证前端静态入口、`/api/health`、LangGraph `/info` 及一次人工配置密钥后的聊天请求。
  - [x] SubTask 5.5: 更新 `README.md` 与 `.env.example`，记录本地开发、Docker 启动、访问地址、验证命令、可选认证和高风险工具开关。
  - [x] SubTask 5.6: 执行 `git diff --check` 并确认未覆盖或回滚任务开始前的用户改动。

- [x] Task 6: 修复静态验收发现的 Compose 地址透传问题：隔离主机与容器数据库/Redis 地址，并向前端构建传递可选登录 URL。
  - [x] SubTask 6.1: 确保复制 `.env.example` 后，容器内 FastAPI 与 LangGraph 使用 `mysql`、`redis` 服务名而非 `localhost`。
  - [x] SubTask 6.2: 将 `NEXT_PUBLIC_LOGIN_API_URL` 作为前端构建参数透传，并保持空值时本地聊天无需登录。
  - [x] SubTask 6.3: 重新执行 Compose 配置解析、Bake 目标解析、文档一致性和敏感信息检查。

- [x] Task 7: 修复运行验收发现的根环境文件加载问题：确保从仓库根启动 Compose 时，后端容器能够读取本地 `.env` 中的模型密钥且文档命令一致。
  - [x] SubTask 7.1: 为 FastAPI 与 LangGraph 显式加载根 `.env`，不得在渲染配置、日志或响应中输出密钥值。
  - [x] SubTask 7.2: 更新 Docker 命令示例并重新创建服务，验证 LangGraph 不再因缺少 `MOONSHOT_API_KEY` 重启。
  - [x] SubTask 7.3: 重新执行 Compose 配置、健康状态、端点与聊天冒烟检查。

- [x] Task 8: 使用有效的本地 Moonshot 凭据完成最终模型调用验收。
  - [x] SubTask 8.1: 在不提交、不输出密钥的前提下更新本地 `.env`，并重新创建 FastAPI 与 LangGraph 服务。
  - [x] SubTask 8.2: 从前端兼容的 LangGraph API 创建线程并提交消息，确认运行状态成功而非上游 401。
  - [x] SubTask 8.3: 复查服务健康状态与脱敏日志，完成 Task 5.4。

- [x] Task 9: 处置验收发现的历史硬编码凭据，确保版本控制差异不再暴露有效 Key。
  - [x] SubTask 9.1: 在服务提供方轮换或吊销已进入 Git 的 Moonshot 与 Tavily Key，并仅在本地 `.env` 保存新值。
  - [x] SubTask 9.2: 经用户明确批准后，以保留当前工作区改动的方式清理 Git 历史中的旧凭据，或记录不重写历史的风险接受决定。
  - [x] SubTask 9.3: 重新扫描日志、响应、规格文档、工作区差异和 Git 历史，确认无有效凭据泄露。

# Task Dependencies

- Task 2 depends on Task 1.
- Task 3 depends on Task 1 and may run in parallel with Task 2.
- Task 4 depends on Task 2 and Task 3.
- Task 5 depends on Task 2, Task 3, and Task 4.
- Task 6 depends on Task 4 and must complete before final checklist verification.
- Task 7 depends on Task 6 and must complete before Task 4/5 的运行验收。
- Task 8 depends on Task 7 and requires a valid locally configured Moonshot API Key.
- Task 9 depends on Task 8 and must complete before final security checklist approval.
