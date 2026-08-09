# Deep Data Agent — 项目指南

> 本文件面向 AI 编码助手。阅读前请默认对项目一无所知；以下内容全部基于仓库实际文件，不做假设。

## 1. 项目概述

Deep Data Agent（中文名：人工智能数据探索）是一个前后端分离的 AI 数据探索/智能问答系统。

- **后端** (`data_agent/`)：基于 Python + FastAPI + LangChain/DeepAgents 构建，对外提供 REST API，并可通过 LangGraph 协议暴露图服务。
- **前端** (`agent_chatui/`)：基于 Next.js + React + Tailwind CSS 构建的聊天界面，源自 LangChain 官方 `agent-chat-ui` 模板。
- **基础设施** (`docker-config/`)：使用 Docker Compose 编排 MySQL、Redis、后端与前端服务。

当前项目处于早期阶段：后端已实现搜索、文档分析、代码执行三种工具以及用户/会话持久化；前端聊天界面集成 LangGraph SDK，但存在若干缺失文件与未对齐的接口。

## 2. 仓库位置

本项目的实际根目录为：

```text
D:\Code\deep_data_agent\deep_data_agent
```

外层 `D:\Code\deep_data_agent` 仅包含上述一个子目录，无实际代码。所有命令请在 `deep_data_agent/` 目录内执行。

## 3. 技术栈

### 3.1 后端

| 技术 | 用途 |
|------|------|
| Python 3.12 | 运行时 |
| FastAPI | Web 框架 |
| Uvicorn | ASGI 服务器 |
| SQLAlchemy | ORM |
| MySQL | 持久化数据库 |
| Redis | 缓存 |
| LangChain / `langchain_openai` | LLM 调用抽象 |
| `deepagents` | Agent 创建与编排（`create_deep_agent`） |
| Moonshot Kimi (`kimi-k2-turbo-preview`) | 默认大模型 |
| Tavily | 互联网搜索 |
| python-jose / passlib | JWT 认证与密码哈希 |
| python-dotenv | 环境变量加载 |
| pandas / tabulate | 数据处理与展示 |

### 3.2 前端

| 技术 | 用途 |
|------|------|
| Next.js 15.2.3 | React 框架 |
| React 19.0.0 | UI 库 |
| TypeScript ~5.7.2 | 类型系统 |
| Tailwind CSS 4.0.13 | 原子化 CSS |
| shadcn/ui (New York) | 组件库 |
| `@langchain/langgraph-sdk` | 与 LangGraph 后端通信 |
| `@antv/g2` / `@antv/ava` | 图表与自动可视化 |
| `react-markdown` / `react-syntax-highlighter` | Markdown 与代码高亮 |
| pnpm 10.5.1 | 包管理器 |

### 3.3 部署/运维

| 技术 | 用途 |
|------|------|
| Docker / Docker Compose | 容器化部署 |
| PM2 | 本地/服务器进程管理（`start.sh`） |
| Nginx | 静态前端部署（`agent_chatui/start.sh`） |

## 4. 项目结构

```text
deep_data_agent/
├── .env                      # 环境变量（本地，已忽略，需手动创建）
├── .env.example              # 环境变量示例
├── .gitignore
├── README.md                 # 仅一行中文标题
├── langgraph.json            # LangGraph CLI 配置
├── requirements.txt          # Python 依赖
├── setup.py                  # 极简 setuptools 配置
├── start.sh                  # PM2 启动 LangGraph 开发服务器
├── agent_chatui/             # 前端（Next.js）
│   ├── package.json
│   ├── next.config.mjs
│   ├── tsconfig.json
│   ├── eslint.config.js
│   ├── prettier.config.js
│   ├── tailwind.config.js
│   ├── components.json       # shadcn/ui 配置
│   ├── Dockerfile
│   ├── start.sh              # Nginx 静态部署脚本
│   └── src/                  # 源码
│       ├── app/              # Next.js App Router
│       ├── components/       # 组件（thread、ui、icons）
│       ├── config/index.ts   # 全局常量
│       ├── hooks/            # 自定义 Hooks
│       └── providers/        # React Context / LangGraph Client
├── data_agent/               # 后端（Python）
│   ├── agent_server.py       # FastAPI 入口
│   ├── Dockerfile
│   ├── config/               # 配置、数据库、日志
│   ├── models/               # SQLAlchemy 模型
│   ├── routes/               # FastAPI 路由
│   ├── services/             # 业务逻辑服务
│   └── tools/                # Agent 工具实现
└── docker-config/
    └── docker-compose.yml    # 全栈 Docker Compose 编排
```

## 5. 关键配置文件

### 5.1 后端

- **`requirements.txt`**：Python 依赖清单。注意 `pandas` 重复出现，`setuptools==75.8.0` 被固定，`langgraph-cli[inmem]` 用于本地 LangGraph 开发。
- **`setup.py`**：极简包配置，仅声明 `name='data_agent'`、`version='0.1'`。
- **`langgraph.json`**：LangGraph CLI 使用，指定 graph 名 `agent` 对应 `./data_agent/agent_server.py:agent`。注意当前 `agent_server.py` 导出的是 `app`（FastAPI 实例），而非 `agent`。
- **`.env.example`**：
  - `MOONSHOT_API_KEY`
  - `TAVILY_API_KEY`
  - `DATABASE_URL`（默认 MySQL）
  - `HOST`、`PORT`、`LOG_LEVEL`

### 5.2 前端

- **`package.json`**：脚本、依赖、packageManager 固定为 `pnpm@10.5.1`。
- **`next.config.mjs`**：
  - `output: 'export'`：静态导出
  - `basePath: '/data_copilot'`
  - `images.unoptimized: true`
  - `eslint.ignoreDuringBuilds: true`
  - `typescript.ignoreBuildErrors: true`
- **`tsconfig.json`**：路径别名 `@/*` -> `./src/*`。
- **`eslint.config.js`**：基于 `typescript-eslint`、`@eslint/js`、React Hooks/Refresh 规则。
- **`prettier.config.js`**：单属性换行、Tailwind 排序插件。
- **`components.json`**：shadcn/ui 配置，`rsc: false`。

### 5.3 部署

- **`docker-config/docker-compose.yml`**：编排 `mysql`、`redis`、`backend`、`frontend`。
- **`data_agent/Dockerfile`**：Python 3.12 slim，安装依赖后执行 `python agent_server.py`。
- **`agent_chatui/Dockerfile`**：Node 18 Alpine，pnpm 安装、build、start。

## 6. 构建与运行命令

### 6.1 本地开发

#### 后端

```bash
# 1. 创建并激活虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/macOS，然后填写密钥

# 4. 启动 MySQL / Redis（可选，也可使用 Docker Compose）
cd docker-config
docker compose up -d mysql redis

# 5. 启动后端开发服务器
python data_agent/agent_server.py
```

默认监听 `0.0.0.0:8000`。

#### 使用 LangGraph CLI 启动（与 `start.sh` 一致）

```bash
# 需要安装 langgraph-cli[inmem]
langgraph dev --allow-blocking --no-browser
```

或按项目脚本使用 PM2：

```bash
pm2 delete langgraph-app
pm2 start "langgraph dev --allow-blocking --no-browser" --name "langgraph-app"
```

#### 前端

```bash
cd agent_chatui

# 使用 pnpm（项目固定）
pnpm install
pnpm dev
```

开发服务器默认在 `http://localhost:3000`。

### 6.2 生产构建

#### 前端静态导出

```bash
cd agent_chatui
pnpm install
pnpm build
```

产物在 `agent_chatui/out/` 目录，随后可用 Nginx 部署（参考 `agent_chatui/start.sh`）。

#### 全栈 Docker Compose

```bash
cd docker-config
# 确保外层 .env 已配置 MOONSHOT_API_KEY / TAVILY_API_KEY
docker compose up --build -d
```

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- MySQL：`localhost:3306`
- Redis：`localhost:6379`

## 7. 代码组织

### 7.1 后端模块

| 目录 | 职责 |
|------|------|
| `data_agent/config/` | 配置 (`config.py`)、SQLAlchemy 引擎与会话 (`database.py`)、日志 (`logger.py`) |
| `data_agent/models/` | SQLAlchemy 模型：`User`、`Session`、`Message`，以及实验性的 `KimiChat` |
| `data_agent/routes/` | FastAPI 路由：`auth.py`（注册/登录）、`session.py`（会话/消息 CRUD） |
| `data_agent/services/` | 业务逻辑：`AgentService`、`AuthService`（函数集合）、`SessionService`、`CacheService` |
| `data_agent/tools/` | Agent 可调用的工具：`internet_search`、`analyze_document`、`execute_python_code` |

### 7.2 后端核心流程

1. `agent_server.py` 初始化时调用 `init_db()`，由 SQLAlchemy 自动建表。
2. 全局 `AgentService` 启动时通过 `deepagents.create_deep_agent` 创建 Agent，绑定工具与 Moonshot Kimi 模型。
3. 用户调用 `POST /api/query` 时，`AgentService.invoke()` 先检查 Redis 缓存，再调用 Agent，最后缓存结果 24 小时。
4. 认证与会话路由提供独立的 REST API，但目前会话路由使用硬编码 `user_id = 1`。

### 7.3 前端模块

- `app/page.tsx`：主聊天页，集成 `ThreadProvider`、`StreamProvider`、`ArtifactProvider`。
- `app/login/page.tsx`：授权码登录回调页。
- `providers/Stream.tsx`：封装 `useStream`，管理 LangGraph 连接与初始化表单。
- `providers/Thread.tsx`：线程列表管理。
- `providers/client.ts`：创建 LangGraph SDK Client。
- `components/thread/`：聊天线程、消息渲染、Artifact、Agent Inbox、历史记录。
- `components/ui/`：shadcn/ui 基础组件与 AntV 图表封装。

## 8. 开发规范

### 8.1 代码风格

- **后端**：Python，使用 4 空格缩进，函数/类均使用双引号或单引号均可（当前混用）。
- **前端**：TypeScript + React，函数组件优先，Tailwind 类名通过 `cn()` 工具合并。
- **格式化**：前端使用 Prettier（`pnpm format` / `pnpm format:check`）；后端无统一格式化配置。
- **Lint**：前端 `pnpm lint` / `pnpm lint:fix`；Next.js 构建时 ESLint 与 TypeScript 错误均被忽略（见 `next.config.mjs`）。

### 8.2 命名约定

- 后端服务类：`XxxService`，并创建全局单例 `global_xxx_service`。
- 后端路由文件：`auth.py`、`session.py`，通过 `APIRouter` 组织。
- 前端组件：PascalCase；Hooks：`useXxx`；工具函数：`camelCase`。

### 8.3 环境变量

- 后端通过 `python-dotenv` 从 `.env` 加载。
- 前端仅识别以 `NEXT_PUBLIC_` 开头的变量；当前模板支持 `NEXT_PUBLIC_API_URL` 与 `NEXT_PUBLIC_ASSISTANT_ID`。
- **注意**：仓库中的 `.env` 文件包含密钥，已被 `.gitignore` 忽略，请勿提交。

## 9. 测试策略

当前仓库中**未找到任何测试文件或测试配置**：

- 无 `pytest.ini` / `pyproject.toml` 中的 pytest 配置
- 无 `tests/` 目录
- 无前端 Jest/Vitest/Playwright 配置

建议后续补充：

- 后端：pytest + `TestClient` 覆盖 API 路由与工具函数。
- 前端：至少保留 TypeScript 类型检查与 ESLint；可引入 Vitest 做单元测试。

## 10. 部署流程

### 10.1 Docker Compose（推荐）

```bash
cd docker-config
docker compose up --build -d
```

Compose 文件定义了 `mysql`、`redis`、`backend`、`frontend` 四个服务，共享 `deep_data_network` 桥接网络。

### 10.2 PM2 + LangGraph CLI

```bash
# 在项目根目录
./start.sh
```

等价于：

```bash
pm2 delete langgraph-app
pm2 start "langgraph dev --allow-blocking --no-browser" --name "langgraph-app"
```

### 10.3 前端静态部署

```bash
cd agent_chatui
pnpm install
pnpm build
./start.sh
```

`start.sh` 将 `out/` 复制到 `/usr/share/nginx/html/agent_chat_ui` 并重启 Nginx。**该脚本依赖 sudo 与 Nginx，且包含硬编码路径**。

## 11. 安全注意事项

> 当前代码存在多项安全隐患，修改前请务必了解。

1. **JWT 密钥硬编码**
   - `data_agent/services/auth_service.py` 中 `SECRET_KEY = "your-secret-key-here"` 为硬编码字符串，生产环境必须替换为强随机密钥并通过环境变量注入。

2. **CORS 过于宽松**
   - `agent_server.py` 中 `allow_origins=["*"]`，生产环境应限制为具体域名。

3. **任意代码执行**
   - `data_agent/tools/code_execution.py` 使用 `subprocess.run([sys.executable, temp_file_path])` 执行传入的 Python 代码，且无沙箱。该工具一旦被 Agent 调用，可能导致 RCE。

4. **缓存键使用 MD5**
   - `agent_service.py` 与 `search.py` 使用 `hashlib.md5` 生成缓存键。虽然仅用于缓存去重，但建议敏感场景使用 SHA-256。

5. **前端缺少关键工具文件**
   - 多个组件引用以下不存在的文件：
     - `@/lib/utils`
     - `@/lib/api-key`
     - `@/lib/ensure-tool-responses`
     - `@/lib/agent-inbox-interrupt`
   - 这将导致前端构建/运行失败，需要先补齐或删除相关引用。

6. **配置与接口不一致**
   - `agent_chatui/src/config/index.ts` 只导出 `AGENT_API_URL`，但 `app/page.tsx` 同时引用了未导出的 `LOGIN_API_URL`。
   - `langgraph.json` 声明 graph 为 `./data_agent/agent_server.py:agent`，但 `agent_server.py` 当前导出的是 FastAPI `app` 实例。

7. **会话路由未真正鉴权**
   - `session.py` 中 `user_id = 1` 为硬编码，未从 JWT 中解析用户身份。

8. **API 密钥管理**
   - Moonshot 与 Tavily 密钥通过环境变量读取，符合基本要求；确保 `.env` 不被提交，并在生产环境使用密钥管理服务。

## 12. 已知问题与注意事项

- **前端构建会失败**：由于缺少 `@/lib/*` 工具文件以及 `LOGIN_API_URL` 未定义，直接 `pnpm build` 会报错。修复前建议先补齐 shadcn/ui 的 `lib/utils.ts` 与项目所需的 `lib/api-key.ts`、`lib/ensure-tool-responses.ts`、`lib/agent-inbox-interrupt.ts`。
- **虚拟环境路径损坏**：`.venv` 的 `pyvenv.cfg` 指向 `C:\Python314\python.exe`，该路径在当前环境中不存在。建议使用新的 Python 3.12 重新创建虚拟环境。
- **数据库与 Redis 依赖**：后端启动时会自动建表；Redis 在 `CacheService` 中按 `localhost:6379` 连接，连接失败时仅降级为不缓存，不会阻断启动。
- **`KimiChat` 模型未使用**：`data_agent/models/chat_models.py` 中定义了自定义 `KimiChat(BaseChatModel)`，但 `AgentService` 实际使用的是 `langchain_openai.ChatOpenAI`。
- **Docker Compose 中的前端环境变量**：`NEXT_PUBLIC_API_URL=http://backend01:8000` 在浏览器端不会生效（Next.js 仅在构建时嵌入该值），如需动态后端地址需调整架构。

## 13. 常用命令速查

```bash
# 后端
pip install -r requirements.txt
python data_agent/agent_server.py

# 后端（LangGraph CLI）
langgraph dev --allow-blocking --no-browser

# 前端
cd agent_chatui
pnpm install
pnpm dev
pnpm build
pnpm lint
pnpm lint:fix
pnpm format
pnpm format:check

# Docker
cd docker-config
docker compose up --build -d
```

## 14. 相关文档

- `README.md`：仅包含项目中文名“人工智能数据探索”。
- `.trae/documents/project_analysis.md`：中文项目分析报告，描述了当前状态、问题与改进方向，可作为背景参考。
