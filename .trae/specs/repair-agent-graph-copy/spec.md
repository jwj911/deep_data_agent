# 修复 Agent 图复制后的运行失败

## 为什么

`REV-A01` 在本机 LangGraph 1.2.11 / API 0.7.28 / DeepAgents 0.7.5
组合中已复现。基础图复制用实例属性重建子类，后置注入的租约管理器被构造器
忽略，导致 `copy`、`with_config` 和 API `get_graph` 后运行失败。

## 变更内容

- 让资源图显式接收并保存服务端租约管理器，满足框架构造与复制合同。
- 保留 `CompiledStateGraph`、四种调用方式和 checkpoint/store 注入。
- 添加真实编译图、真实 Agent 工厂及已安装 API 装配路径的离线回归。
- 定向同步当前问题状态与验证记录；前轮审计原值和历史验收不反写。
- 本轮不升级依赖，不实施父子合计预算、缓存或其他 Roadmap 候选。

## 影响范围

- 代码：`data_agent/services/agent_service.py`。
- 测试：`tests/test_agent_graph_copy.py`，必要的已有图资源/租约用例。
- 文档：本规格、README、AGENTS、CHANGELOG、项目分析与 Roadmap。
- 关联规格：`bound-agent-resource-use`、`secure-agent-tenant-boundaries`。
- 用户已要求开始修复，本规格记录本次实施范围，不另设审批。

## 新增要求

### 要求：复制保持服务端依赖

资源图 SHALL 在原图、复制、绑定配置、API 注入存储及重复复制后保持原租约
管理器；不得通过丢失依赖、回退另一管理器或替换为普通 Runnable 绕过保护。

#### 场景：API 加载已注册图

- **当** 已安装 API 的 `get_graph` 复制图并注入 checkpoint/store
- **则** 四种调用可完成，注入生效、原图不被修改，每次调用只取得并释放一份租约。

### 要求：现有保护不变

身份来源、递归覆盖、deadline、模型/工具错误映射、取消及租约拒绝 SHALL
继续有效。仅持久化结构由框架复制；每次运行的主体和资源状态不能跨图串用。

#### 场景：异常和取消

- **当** 复制图无可信身份、租约忙碌或不可用、预算超限、超时或被取消
- **则** 保留对应拒绝与稳定错误，节点不会在保护拒绝后执行，已取得租约仅释放一次。

### 要求：验收证据分层

回归 SHALL 使用非敏感合成输入、离线模型、内存存储和租约替身；不读取
真实 `.env`、业务数据或调用模型/搜索。工程测试通过不代表 Linux 容器、
真实 HTTP、Hosted 或生产放行；缺口必须明确记录。

## 修改要求

资源图构造器 SHALL 显式接收租约管理器；工厂在构造时注入管理器，而不是构造
后增加属性。保持基础类的复制协议和既有调用保护逻辑。

## 移除要求

无。

## 实施与验证记录（2026-10-27）

- 分支 `main`，HEAD 保持 `3d4ac6dbb540d7f8a46430f3bc311c071d4ba438`；
  实施在未提交工作树。先前五份文档和现代化规格改动保留。
- 最小回归修复前：原图四例通过，copy/with_config 八例均报管理器缺失；
  第二轮实际安装 API get_graph 四面及 copy 正控复现同一 AttributeError。
- 修复后最小回归 16 项通过；扩展到真实工厂与保护路径后新增 149 项。
  相关测试一次 222 项通过，随后增加同步 deadline 和 falsey 管理器验证；
  最新全量后端 **601 项通过，51.64 秒**，其中新增复制回归 **149 项**。
- 执行器为 `.venv/Scripts/python.exe -I -B -`，stdin 中禁用 dotenv
  （`PYTHON_DOTENV_DISABLED=1` 并替换 `dotenv.load_dotenv`）、追踪、自动
  pytest 插件，设置空日志路径，调用
  `pytest.main(["-q", "-p", "no:cacheprovider", "--tb=short"])`。
  既有 conftest 使用 SQLite、假凭据与离线 Redis；工厂模型及存储均为替身/内存。
- `python -I -B -m isort --check-only data_agent tests scripts`、
  `python -I -B -S scripts/check_release_contracts.py` 和差异检查通过。
- 一轮扩展用例误读公开输出中的私有计数，原图与复制图均已运行成功；
  改为独立 callback 记录实际离线模型调用次数后相关回归通过。导入格式失败
  按项目 isort 风格手工修正；未以这两类测试问题扩大运行时改动。
- 本轮未启动真实服务、模型/搜索、浏览器或 Docker，未改依赖/部署配置，
  不将前轮前端/容器/Hosted 数字作为本轮运行证据；Linux/HTTP/Hosted/生产未验证。

## 后续部署补验

上述记录属于初次本机修复验收。随后真实 TCP HTTP 补验通过，新增全量后端
602 项通过；再经用户授权将四个代码文件提交为
`8e552f393aafd919fcf564f2b43c9856e6ff71f9` 并推送到 `fix/agent-graph-copy`。
PR #1 的 Hosted run `40507150345` 四 Job 全部成功，包括 Ubuntu 图复制/TCP
回归及 Linux 源码镜像容器冒烟。PR 合并测试树与修复 head 一致，尚未合并或
批准生产。随后本机 Engine 恢复，受限只读 Linux 容器中的当前源码复制/TCP
回归 150 项通过。再从该提交与原 Dockerfile 重建本机五服务，新镜像 150 项
回归、空库、Redis canary、head 重启和已知 legacy 迁移通过；实际工厂图的
wait/stream 在退出时发生 ContextVar reset 异常，取消后租约未及时释放。
浏览器可登录并渲染测试答案，但 run 为 error，匿名入口/退出跳转丢失宿主端口。
本机完整联调验收未通过，任务 6 与验收 18/19 保持未勾。时间、实际依赖、
Job ID、控制条件与范围见
[部署补验记录](validation.md)。
