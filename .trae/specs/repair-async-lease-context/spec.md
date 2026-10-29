# 修复图流退出的身份上下文与租约释放

用户已要求实施本修复。起点为 `fix/agent-graph-copy @ 8e552f3`；
前轮未提交文档、规格及失败证据保留。

## 问题与范围

安装版 API 0.7.28 的 `wait_if_not_done` 对每次 `anext` 创建新任务。
资源图在异步生成器中持有租约与 `asyncio.timeout`，跨 `yield` 后继续执行于
另一个任务；身份 Token reset 因 Context 不同抛错，随后租约释放未执行。
本机五服务实际 wait/stream/取消失败记录见
[前轮补验](../repair-agent-graph-copy/validation.md)。

本轮只修图流的执行生命周期、身份上下文和释放保证；保留复制合同、授权、
服务端限额、deadline、错误映射与单租约。前端重定向、父子合计预算及依赖升级
为其他迭代。源码、回归与适用验证脚本可修改，治理文档只同步当前范围。

## 修复合同

- 图执行、可信身份绑定及 deadline 在稳定执行上下文中开始和结束；流消费者
  切换任务、提前关闭、取消或结束后，身份不能泄漏到消费者或其他用户。
- 流的缓冲有界。消费者结束时取消并等待图任务清理，不能留下脱离调用方的
  后台运行。deadline 覆盖真实执行及等待，不依赖首个取流任务继续存活。
- 已取得租约正常、异常、超时、提前关闭及取消均及时单次释放；身份上下文清理
  异常也须尝试释放，不能以吞掉 reset 错误或移除身份检查代替正确作用域。
- 嵌套调用复用同一可信主体的租约，其他主体仍拒绝；原图、copy、with_config
  和 API get_graph 的类型、存储及保护保持。
- HTTP 验证使用真实 API worker、实际工厂图与真实身份上下文；模型/存储的
  控制条件明确，单独取得隔离 Redis 的实际租约证据。HTTP 200 不代替成功
  payload、stream 无 error 或最终 run 状态。

## 修复前最小复现

`tests/test_agent_concurrency.py` 新增
`test_api_steps_release_real_lease_across_task_contexts`，直接使用安装版 API 的
逐步迭代函数、真实 AgentLeaseManager 和既有离线 Redis 脚本替身。
两例分别完整消费及从另一任务提前关闭，实际均失败：
`ValueError: Token ... was created in a different Context`。
本轮定向结果为 **2 failed，27 deselected，26.31 秒**。

执行器使用 `.venv/Scripts/python.exe -I -B -`，明确加入项目路径，禁用 dotenv、
追踪、自动 pytest 插件与缓存/字节码；未读取真实配置或调用生产服务。
前轮失败不反写为通过。

## 实施与验证

异步流改为单个受控生产任务，图、租约、deadline 与底层流关闭在同一 Task
执行；容量为 1 的队列保持背压，消费者结束时取消并等待生产任务清理。
重复取消不打断已开始的清理，清理异常继续传播。同步流在私有 Context 中
迭代与关闭；两种租约上下文分别尝试两个 reset 及一次 release。

新增 17 项回归，本机全量 **619 passed，89.67 秒**，真实工厂 TCP HTTP 的
身份、wait/stream、取消最终 `interrupted`、timeout 与单次释放通过。
前轮部署的精确依赖环境下，Linux **194 passed，17.00 秒**，独立 Redis 的
真实 HTTP **4 acquire / 4 release**，最终 DB 为 0 个 key。环境、源码指纹及结果见
[独立验收](validation.md)。本轮不提交、推送或合并；完整五服务、浏览器和
本轮工作树 Hosted 未重验，静态认证跳转及生产 NO-GO 边界保持。
