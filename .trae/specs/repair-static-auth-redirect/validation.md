# 静态认证跳转修复与部署重验

2026-10-28，基于 `fix/agent-graph-copy @ 8e552f3` 的当前未提交工作树，
包含 `repair-async-lease-context`。前轮失败、历史 Hosted 和 A/B 原值不反写。
本机当前源码的生产静态构建、独立五服务与浏览器联调通过；生产持久业务仍
NO-GO。机器证据见 [本轮部署证据](local-five-service-evidence.json)。

## 根因与修复

原 Nginx 在容器内监听 80。静态目录补尾斜线时生成绝对 Location，
从 `http://127.0.0.1:11370/data_copilot/login` 跳到
`http://127.0.0.1/data_copilot/login/`，丢失宿主映射端口。

仅在前端 Nginx server 加入 `absolute_redirect off;`，令 Location 相对当前
Origin 解析。第一方 JWT、固定 API Origin 和客户端认证逻辑保持原合同。
新增 `scripts/verify_static_frontend_http.py`，直接检查 TCP HTTP 的 5 条跳转与
2 个静态 HTML 页面；同一原缓存镜像先红、只读挂载修复配置后绿。
CI Container Smoke 已加入该门禁，使用非 80 宿主端口。

## 部署与控制条件

从当前工作树复制隔离源码，排除真实 `.env`、Git、依赖、缓存、日志和构建输出。
使用原前后端 Dockerfile 和正式五服务 Compose，单独项目、镜像标签、数据库、
文件卷及 loopback 端口；公开 API 地址写入本次静态构建。

后端临时 Python 基底只指定清华 PyPI 地址，通过 named build context 供原
Dockerfile 使用；不修改产品依赖声明、原镜像标签或全局配置。前端使用
Node 22.23.2、pnpm 10.5.1 和 frozen lockfile。后端为 Python 3.12.13、
DeepAgents 0.7.32、LangGraph 1.2.18、API 0.7.28、Redis client 8.1.0；
完整安装版本在机器证据中。MySQL 8.4、Redis 7-alpine 为真实服务。
验证辅助脚本、源码快照、随机合成密钥、请求和日志仅位于工作区外临时目录。

模型使用部署网络内的合成 OpenAI HTTP/SSE 传输，不替换实际图、worker、
身份上下文或 Redis Lua。正常请求返回固定合成答案；取消/timeout 请求等待
客户端关闭。run、模型、搜索 timeout 均为 5 秒，lease TTL 75 秒，模型重试
保留默认 1 次。该验证证明传输与生命周期，不证明真实模型质量、搜索或收费。

首次测试配置误设 `MODEL_MAX_RETRIES=0`，两个 worker 按正式正整数合同拒绝
启动；恢复默认 1 后就绪。此为验证配置错误，不认定为产品缺陷。

## 已取得结果

| 检查 | 实际结果 |
| --- | --- |
| 当前源码生产镜像 | 原 Dockerfile 构建通过，镜像/源码指纹相符 |
| 前端 typecheck、零警告 lint、format:check、build | 全部通过 |
| 正式五服务 | 全部 healthy，公开端口仅绑定 loopback |
| 新生产 Nginx 的真实 HTTP 门禁 | 5 条相对跳转、2 个 HTML 200；Origin/端口/路径/查询保持 |
| 新后端镜像生命周期、复制、TCP HTTP 三文件回归 | 194 passed，17.24 秒 |
| 新后端镜像 pip check | 通过 |
| 真实 MySQL 双用户/管理员、受管文件共享和 owner 隔离 | 通过 |
| LangGraph wait/stream、checkpoint、身份/owner 负控 | 通过，正常 run 最终 success |
| 真实取消 | 最终 interrupted，取消后无 lease key |
| timeout | 稳定 agent_timeout，run 最终 error，无 lease key |
| FastAPI 实际工厂图 | 回答成功，返回后无 lease key |
| 浏览器匿名入口、登录、对话、无尾斜线深链接刷新 | 通过，固定答案来自服务端，threadId 与答案保持 |
| 浏览器错误密码、退出、退出后深链接、重新登录 | 通过，错误密码拒绝带诊断 ID，端口始终保持 |
| 浏览器对应服务端 run | 最终 success，checkpoint 答案相符，无 lease key |
| worker 日志与真实 Redis | LangGraph 5 acquire / 5 release；FastAPI 1 / 1；无 different Context reset 错误 |
| 两次 Redis 故障及恢复 | live 200；ready/query fail-closed；自动恢复；后端容器未重启 |
| 空库、head 重启、known legacy 升级 | 唯一 head b6f4e8c2a9d1；用户/会话/消息 canary 保持 |
| isort、发布契约、差异检查 | 通过 |

IDE 浏览器完成匿名入口、登录、发送及深链接刷新；实际退出 click 和随后
select 两次出现浏览器桥接 60 秒超时，未据此认定退出成功。切换本机浏览器，
通过真实表单/按钮完成错误密码、登录、退出、匿名深链接与再次登录；该临时
浏览器 tab 已关闭。IDE 桥接失联后未取得其原 tab 最终状态，不将工具超时记为
产品缺陷。两种浏览器使用同一生产构建与服务 Origin。

正常 wait/stream、浏览器及 REST 返回成功；取消和 timeout 分别按错误/中断合同
判定。各结束点验证 ZCARD 为 0 且无 `agent:lease:*` key，并从 worker 结构化事件
核对共 6 次取得/释放。Redis 的缓存与限流 key 不属于该计数，不声称整个 DB 无 key。

空库 owner/文件检查先由正式 smoke 模块完成，随后补入第五服务的健康、HTTP 与
迁移核验；重复场景不再次注册已有用户。head/legacy 使用该模块的原 canary 合同。
原 Compose 的 uvicorn/langgraph 命令保持，不注入 NumPy 启动预初始化。

## 验证入口与清理

HTTP 门禁可对任意已启动的前端 Origin 重复执行：

```powershell
python -I -B scripts/verify_static_frontend_http.py --base-url http://127.0.0.1:3000
```

五服务检查使用 `scripts/verify_container_smoke.py` 的 `verify --scenario empty`、
`redis-canary`、`seed-head`、`verify --scenario head`、`prepare-legacy` 和
`verify --scenario legacy`；指定独立 Compose/override/env/project 与对应 HTTP 地址。
模型、用户和卷必须使用本节说明的隔离条件，不能对业务数据库执行 legacy 准备。

验收后删除本轮独立容器、网络、卷、4 个镜像标签及按 ID 限定的构建缓存；确认
没有本轮残留容器、卷或新建 cache record。原五个容器保持运行，两个原缓存镜像
完整 ID 不变。工作区外辅助脚本、快照、合成密钥和原始日志已清理，仓库只保留
本轮规格、脱敏证据与授权改动。旧 tasks/checklist 保持原状，未提交、推送或合并。

## 放行边界

本轮工作树尚无 exact-SHA Hosted 证据。父子/summary/retry 合计预算、未知 schema
拒绝、身份/thread/file 一致恢复、API EOL 与依赖锁定、真实模型和业务效果仍需
各自验收。即使本机联调通过，生产或不可重建持久业务仍为 **NO-GO**。

## 后续新锁 Hosted 验收（2026-10-28）

上述为本机认证修复阶段的记录，保留原时点与条件。后续完整实施 SHA
`1910fdfa8653beb3233e48f0e5d29ac2d1e42514` 的
[run 40635353761](https://github.com/jwj911/deep_data_agent/actions/runs/40635353761)
四 Job 均 success。新锁源码镜像的五服务、真实静态认证跳转、Redis 恢复、
head 重启和 known legacy 升级通过；Chromium 通过匿名跳转保留端口、
注册登录、渲染答案且 run success、深链接刷新、退出清 Token、错误密码拒绝、
再次登录七项。受控 TCP/SSE 模型实际收到 1 次请求，结束后 0 lease key。

新锁完整后端 733 项、预算/MySQL 各 20 项及独立三域恢复另行通过；
详细证据与范围见[运行时记录](../stabilize-delivery-baseline/validation.md)。
工程门禁通过不等同生产运行时、自动异地备份或真实模型效果验收。
