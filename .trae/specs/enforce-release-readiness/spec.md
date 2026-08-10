# 发布就绪治理 Spec

## Why

项目已完成可运行闭环和多用户认证隔离，但远端合并后重新出现了前端构建门禁绕过、格式检查失败和 Lint 警告；仓库也尚无 CI、Roadmap 或下一轮 Iteration Plan。继续扩展业务功能前，需要先建立可自动执行、不可静默绕过的发布质量基线，防止已验收能力在合并后再次回退。

## What Changes

- 恢复可信的前端质量门禁：移除 Next.js 的 TypeScript/ESLint 构建绕过，修复全部格式与 Lint 警告，并让警告导致门禁失败。
- 收敛后端项目自身产生的弃用警告，保持 Python 3.12、SQLAlchemy 与时区处理契约清晰。
- 增加 GitHub Actions CI，在推送和合并请求上自动执行后端、前端、配置与仓库卫生检查。
- 增加配置漂移检查，防止已移除的登录变量、质量绕过开关、真实凭据或错误的 Compose 地址重新进入仓库。
- 更新项目分析、Roadmap、环境示例、README 和变更记录，使文档反映已完成能力及后续优先级。
- 在 Docker 可用时重建镜像并完成五服务健康检查和认证隔离冒烟，形成可追溯的发布证据。

## Impact

- Affected specs: `establish-runnable-baseline`、`secure-user-sessions`
- Affected code:
  - `agent_chatui/next.config.mjs`
  - `agent_chatui/eslint.config.js`
  - `agent_chatui/package.json`
  - 当前产生 Lint 警告的前端组件与 Provider
  - `data_agent/models/`、`data_agent/services/session_service.py`
  - `.github/workflows/`
  - `.env.example`、`README.md`
  - `.trae/documents/project_analysis.md`、新增 Roadmap/变更记录

## ADDED Requirements

### Requirement: 自动化持续集成

系统 SHALL 在推送到主分支和创建合并请求时自动执行发布质量门禁。

#### Scenario: 后端门禁成功

- **WHEN** CI 检出仓库并安装 Python 3.12 依赖
- **THEN** `pytest`、`isort --check-only` 和后端配置契约检查全部通过

#### Scenario: 前端门禁成功

- **WHEN** CI 使用受支持的 Node.js LTS 与锁定的 pnpm 版本安装依赖
- **THEN** 类型检查、Lint、格式检查和生产构建全部通过

#### Scenario: 失败阻止合并

- **WHEN** 任一测试、类型、Lint、格式、构建、配置或仓库卫生检查失败
- **THEN** CI 返回非零状态，且失败步骤与文件可定位

### Requirement: 配置漂移防护

系统 SHALL 自动检查关键运行与安全配置，避免已修复问题重新出现。

#### Scenario: 禁止质量门禁绕过

- **WHEN** 检查 Next.js 配置
- **THEN** 不存在 `ignoreBuildErrors` 或 `ignoreDuringBuilds`

#### Scenario: 禁止过时登录配置

- **WHEN** 检查源码、Compose、环境示例和 README
- **THEN** 不再引用 `NEXT_PUBLIC_LOGIN_API_URL`

#### Scenario: 配置与凭据卫生

- **WHEN** 检查环境示例、Compose 和版本控制差异
- **THEN** `.env.example` 仅含非生产占位值，容器内部地址使用服务名，且无有效 API Key、JWT、密码或 Bearer Token 被提交

### Requirement: 发布路线与证据

项目 SHALL 维护与当前实现一致的项目分析、Roadmap 和变更记录。

#### Scenario: 路线图可执行

- **WHEN** 开发者查看 Roadmap
- **THEN** 可以区分已完成能力、当前发布治理迭代和后续业务候选，并看到依赖关系与验收门槛

#### Scenario: 发布证据可追溯

- **WHEN** 一轮迭代完成
- **THEN** 文档记录质量门禁结果、容器健康状态、冒烟范围、已知风险和未处理技术债

## MODIFIED Requirements

### Requirement: 前端生产构建

前端生产构建 SHALL 在 TypeScript 或 ESLint 存在错误时失败，不得依赖 `ignoreBuildErrors` 或 `ignoreDuringBuilds` 跳过检查；Lint 门禁 SHALL 以零警告完成。

### Requirement: 后端时间与 ORM 兼容性

后端 SHALL 使用 SQLAlchemy 2.x 推荐的声明式基类导入，并使用明确的 UTC 时间语义，消除项目代码直接触发的已知弃用警告，同时保持现有数据库字段和 API 响应兼容。

### Requirement: 发布前容器验证

发布候选 SHALL 从当前源码重建前后端镜像，确保 MySQL、Redis、FastAPI、LangGraph 和前端五服务健康，并复验注册、登录、`/me`、无 Token 401、跨用户会话 404 和 CORS 白名单行为。

## REMOVED Requirements

### Requirement: `NEXT_PUBLIC_LOGIN_API_URL` 环境变量

**Reason**: 第一方认证已统一使用 `NEXT_PUBLIC_REST_API_URL` 调用 FastAPI，授权码登录入口已被移除；继续保留该变量会制造配置漂移。

**Migration**: 删除 `.env.example`、Compose、README、前端构建参数和源码中的残留引用；现有部署改用 `NEXT_PUBLIC_REST_API_URL`。
