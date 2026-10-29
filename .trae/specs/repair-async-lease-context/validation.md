# 异步身份上下文与租约释放修复验收

本轮在 `fix/agent-graph-copy @ 8e552f3` 的未提交工作树中实施。
前轮五服务的失败响应保留在
[原补验记录](../repair-agent-graph-copy/validation.md)，不反写为通过。

## 修复与控制条件

安装版 API 0.7.28 的 `wait_if_not_done` 为每次 `anext` 创建新 Task。
原图包装跨 `yield` 持有 `asyncio.timeout` 和租约 ContextVar Token，
退出时执行 Context 与创建时不同；subject reset 抛错后，lease reset 与 Redis
释放也被跳过。复制图保留 manager 的前轮修复不是本次根因。

`ResourceBoundedAgentGraph.astream` 现在由一个受控 Task 执行图、绑定身份、
管理 deadline，并在同 Task 显式关闭底层流。消费者通过容量为 1 的队列取流；
队列满时生产者等待，终止通知不阻塞释放。消费者关闭或取消时取消图任务并等待
其清理；重复取消不打断已开始的清理，正常清理异常仍传播。deadline 覆盖执行
及背压等待，不依赖最初取流的 Task 继续存活。

同步 `stream` 在私有 `copy_context()` 内执行每次迭代与关闭，保持主体绑定
作用域；支持顺序跨 Context/线程恢复，不引入后台线程。
`hold`/`hold_async` 使用嵌套 `finally`，保证两个 Token 的 reset 和一次
release 都被尝试。reset 异常继续传播；Redis 故障仍按原合同延迟到 TTL 回收，
不能把应用生命周期修复宣称为 Redis 不可用时的即时删除保证。

模型、工具预算映射、服务端身份清洗、原图/copy/with_config/API get_graph、
checkpoint/store 及同主体嵌套单租约合同保留。本轮未修改依赖声明或部署配置。

## 本机结果

环境为 Python 3.12.9、DeepAgents 0.7.5、LangGraph 1.2.11、
LangGraph API 0.7.28。使用离线模型、SQLite、Redis Lua 替身及隔离 inmem
运行时，禁用 dotenv、追踪、自动 pytest 插件、缓存 provider 和字节码。
未读取真实 `.env`，未调用真实模型、搜索或业务服务。
HTTP 验证沿用启动主线程预初始化 NumPy 的控制条件；未将该控制写入产品运行时。

| 检查 | 实际结果 |
| --- | --- |
| 修复前，真实 API 逐步取流与另一 Task 关闭 | 2 failed / 27 deselected，26.31 秒；Token different Context |
| 首次生命周期修复后的并发与复制回归 | 178 passed，23.17 秒 |
| 重复取消、清理异常传播的加严控制 | 首次 2 failed / 42 deselected，21.57 秒；随后修复 |
| 最终全量后端 | **619 passed，89.67 秒** |
| isort 全仓库检查 | 通过 |
| 发布契约脚本 | 通过 |
| 真实 TCP HTTP，真实工厂图和 ContextVar | wait/stream/state、owner/身份负控、取消、timeout 通过；4 acquire / 4 release |

新增 17 项生命周期回归，覆盖跨 Task 完整取流/提前关闭、异常/超时/取消、
有界背压、消费者暂停后的 timeout、双主体交错、嵌套单租约、同步跨 Context/
线程、两种 reset 异常、重复取消和清理异常传播。取消回归同时核验节点已清理、
租约归零且没有新增悬挂 Task。

`scripts/verify_agent_graph_http.py` 现在继承真实 `AgentLeaseManager` 的
上下文管理实现，仅替换可控的取得/存储。模型执行时核验可信主体与活动租约，
HTTP 请求上下文核验无身份泄漏；wait/stream/timeout 返回前检查释放，
取消的最终 run 必须为 `interrupted`。timeout 的 HTTP 200 必须含稳定
`agent_timeout` 错误，不把 200 当成功。可用 `--lease-redis-url` 指定独立、
无凭据的 loopback Redis，以运行真实 Lua 获取与释放。

本机全量命令（PowerShell，以项目根为工作目录）：

```powershell
"import os,sys; os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHON_DOTENV_DISABLED='1',LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',LOG_FILE_PATH=''); sys.path.insert(0,os.getcwd()); import dotenv; dotenv.load_dotenv=lambda *a,**k:False; import pytest; raise SystemExit(pytest.main(['-q','-p','no:cacheprovider']))" | .\.venv\Scripts\python.exe -I -B -
.\.venv\Scripts\python.exe -I -B -m isort --check-only data_agent tests scripts
.\.venv\Scripts\python.exe -I -B scripts/verify_agent_graph_http.py
```

## Linux 与独立 Redis

缓存镜像 Python 3.12.13 / DeepAgents 0.7.6 / LangGraph 1.2.11 /
API 0.7.28 下，另用只读当前源码和独立 Redis 完成直接图验证：
跨 Task 提前关闭、取消、deadline、节点异常，以及故意让原始 hold_async 在
另一 Task 退出的实际 Token different Context 错误，**5 例通过**。
五次取得/释放相符，每例结束 Redis DB 均为 0 个 key；最后一例仍抛 ValueError，
同时真实 Lua 释放成功。临时 Redis 已删除；原运行容器保持。
指纹与条件见 [直接 Redis 证据](direct-redis-evidence.json)。

2026-10-28 00:00–00:02 的精确部署依赖验证通过。临时镜像从原缓存基底派生，
按[前轮五服务证据](../repair-agent-graph-copy/local-five-service-evidence.json)
的 133 个安装版本逐项固定；实际核对零版本差异。环境为 Python 3.12.13、
DeepAgents **0.7.32**、LangGraph **1.2.18**、API **0.7.28**、
Redis Python client 8.1.0。镜像另保留缓存基底的 greenlet 3.5.5 与
tqdm 4.70.0，完整 135 项安装列表见 [Linux 证据](linux-evidence.json)。
这些版本属于前轮部署环境；本轮没有修改产品依赖声明。

| Linux 检查 | 实际结果 |
| --- | --- |
| 并发生命周期、图复制、真实 TCP HTTP 三文件回归 | **194 passed，17.00 秒** |
| 独立 Redis 下的真实 API 工厂图 HTTP | wait/stream/state、身份/owner 负控、取消、timeout 通过 |
| 真实 Lua 租约 | **4 acquire / 4 release**；每个结束点无活动租约，最终 Redis DB 为 **0 个 key** |
| 源码与只读快照 | 六个源码/测试/脚本 SHA-256 相符；验收后再次核对仍一致 |
| 原运行资源 | 原五个容器保持运行，原缓存镜像 ID 保持 |

回归命令的目标为 `tests/test_agent_concurrency.py`、
`tests/test_agent_graph_copy.py`、`tests/test_agent_graph_http.py`，沿用上文
pytest 隔离条件。随后独立执行
`python -I -B scripts/verify_agent_graph_http.py --lease-redis-url redis://127.0.0.1:6379/0`。
运行容器使用只读源码/根文件系统、临时 `/tmp`、CPU/内存/PID 限额及禁用
capabilities；网络只共享独立 Redis 的 loopback namespace，不发布端口。
Redis 无外网、无持久化。HTTP 仍使用离线模型、隔离 SQLite/inmem 和主线程
NumPy 预初始化；外部连接尝试为 0，不代表完整产品 Compose 或真实模型验证。

首轮构建曾因 Docker 客户端超时后遗留子进程的输出管道而中断，实际未运行
容器测试；[中断证据](interrupted-build-evidence.json)保留。改用临时文件捕获
输出、直接调用 buildx、有界等待及超时终止所属进程树后，本次构建与验证通过。
临时容器、镜像、源码快照及执行器已删除；缓存按本轮确定的 ID 清理，
回收 470.3 MB，共享的 13.68 kB COPY 记录保留，未清理旧基底或其他构建缓存。

## 当前验收边界

本轮不提交、推送或合并，未取得本次工作树的 Hosted 证据。
没有重跑完整五服务或浏览器验收；静态认证跳转丢失宿主端口仍未修复，
前轮任务 6、验收 18/19 保持未通过。父子合计预算与生产恢复门禁保持，
生产仍 **NO-GO**。
