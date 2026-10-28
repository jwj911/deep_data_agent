# 运行时与本轮发布门禁

2026-10-28；当前未提交工作树。本轮尚未取得精确 SHA 的 Hosted 结果。

独立 Windows Python 3.12 环境使用 `requirements.txt` 的跨平台精确版本及
SHA-256 锁安装。实际 134 个活动包全部匹配；首方 PyPI 元数据确认
`langgraph-api 0.16.8` 属当前 active minor。锁覆盖传递依赖，Docker 和
Hosted 安装均启用 `--require-hashes`。不把哈希锁解释为依赖无漏洞证明。

新锁首次完整回归为 684 通过 / 36 失败。35 项来自测试仍按旧
`get_graph` 签名调用；适配新必填 `store` 与 `access_context` 后，保持真实
API copy、存储注入及四调用面断言。另一项来自新版先删除保留身份字段，
不再按旧版返回 422；HTTP 回归改为发送伪造 configurable/context 并核验
实际模型主体、租约主体、owner 拒绝及最终清理，未替换生产 API 或授权逻辑。
定向 150 项通过，随后完整 **720 项通过，90.74 秒**。

合计预算实际 SDK/TCP **20 个控制例通过**；真实 MySQL 8.4 的结构识别与拒绝
**20 个控制例通过**。恢复前新增实际目标镜像的代码/安装版本校验；
该拒绝回归先红后绿，恢复与运行时锁集合 **33 项通过**。
随后完整 **721 项通过，130.25 秒**。另发现 Python `-O` 会关闭恢复
校验中的断言；实际负控先观测错误接受，再将全部清单/路径/哈希校验改为
显式拒绝。新增该项后的恢复/锁/发布契约集合 **193 项通过**，完整集合应为 722。

发布契约脚本与 Compose 静态解析通过。四个 Hosted Job 明确检出 PR
head SHA，Container Smoke 在构建前核验实际 HEAD 相同。

本机 Linux 镜像构建在系统盘越过 700 MiB 保护线后中止，没有取得新镜像
或本机五服务证据。构建日志显示 NumPy Linux wheel 下载仅 9.8/16.7 MB，
哈希检查拒绝；首方 PyPI 元数据给出的完整大小 16,727,283 bytes 与 SHA-256
`fbde6962867ee75b48b0ee29b2b9372ec5d617799dbaf38e82dc0596f2f7738a`
均可核验，官方哈希已在锁中。本轮不以不完整下载值替换锁，不绕过哈希。
仅按 ID 删除本轮新增 286.7 kB 缓存；保留原容器、镜像和缓存。
精确提交 Hosted 将承担 Linux 镜像和完整三域恢复的实际验收；
当前结果尚未取得，浏览器新锁联调也未执行。

本轮继续使用合成模型传输与隔离 canary，不调用真实模型/搜索，不证明业务
质量、费用或延迟。Compose 仍为 dev runtime；自动异地备份与恢复运营、
真实效果以及相应生产部署支持尚未取得，生产持久业务保持 **NO-GO**。

最终 Windows 新锁全量 **723 项通过，131.69 秒**；isort、release contracts
及 Compose 静态解析通过。预算 TCP 门禁增加独立服务及请求/取消标识；
受控异步并行场景预留 8、实际接收 7、取消 1，其余场景预留与接收相等。
真实 Redis/TCP 20 控制例通过，取得/释放各 20，最终 0 key。
首轮无诊断计数失败仍保留，确定性取消负控不用于追认其根因。

Hosted Container Smoke 新增实际 Chromium UI 门禁：通过受控 TCP/SSE
模型验证匿名跳转、注册登录、对话与 run success、深链接刷新、错误密码、
退出与再登录；随后恢复原配置并执行独立三域恢复。Playwright `1.64.1`
只安装到 runner 临时目录，不改变项目运行时依赖。上述 Hosted 步骤在本记录
提交时尚未执行；最终结果须由精确 head SHA 的四 Job 与步骤日志取得。

## Hosted 修复轮（2026-10-28）

上述未提交和待执行描述保留其记录时点。后续使用原生 `gh` 登录状态读取
API 和步骤日志，逐轮核对完整 `head_sha`，不提取 Git 凭据或临时 Token。

| 提交 / run | 实际结果 |
| --- | --- |
| `19413e1` / `40629314457` | Backend 723 项、预算 20 项、MySQL 20 项及 Frontend/Contracts 成功；Container Smoke 将真实匿名 401 误按 403 判断而失败 |
| `3d0b2ea` / `40632589192` | 严格 401、五服务、owner/文件、静态跳转和 Redis 通过；浏览器控制器在 runner 缺少 HTTPX 时启动失败 |
| `e665a4b` / `40633932174` | Backend 724 项及 Frontend/Contracts 成功；Chromium 七项通过；恢复端口解析拒绝 Docker 同端口双栈绑定 |
| `2f8e348` / `40634732017` | Backend 729 项通过，27.68 秒；135 个 Linux 活动包匹配且支持检查成功；预算/MySQL 各 20 项、Chromium 七项通过；恢复在内存 stdin 的 `fileno` 异常处失败 |

上述失败未放宽为成功响应或跳过恢复。401 回归先红后绿；HTTPX 延后到
预算客户端创建，控制器标准库启动回归先红后绿；恢复在 bootstrap 成功时
独立执行。端口修复保留不可达/歧义拒绝；内存输入修复以真实子进程复现，
磁盘与内存、捕获与文件输出四组合先 2 红 / 2 绿，修后恢复/锁/浏览器
**44 项通过**。各失败轮 Container Smoke 的清理步骤均为 success。

## 新锁完整 Hosted 验收通过

API 核验完整实施 SHA `1910fdfa8653beb3233e48f0e5d29ac2d1e42514` 与
[run 40635353761](https://github.com/jwj911/deep_data_agent/actions/runs/40635353761)
的 `head_sha` 相同；run 为 completed/success，四个 Job 全部 success：
Container Smoke `122640951730`、Backend `122640951876`、
Release Contracts `122640951943`、Frontend `122640951975`。

| 门禁 | 实际结果 |
| --- | --- |
| Linux 完整后端 | 733 项通过，31.03 秒 |
| 运行时哈希锁与支持 minor | 135 个活动包匹配；官方支持检查通过 |
| 真实 SDK/TCP + Redis 合计预算 | 20 控制例通过；20 acquire / 20 release，最终 0 lease key |
| MySQL 8.4 schema 控制 | 20 正负控制通过 |
| 前端类型、lint、格式与构建 | 全部通过 |
| 五服务、空库/owner/文件、静态认证与 Redis 恢复 | 全部通过 |
| Chromium 实际 UI | 七项通过；1 次受控 TCP/SSE 请求，结束后 0 lease key |
| 三域独立恢复 | 逐值比较通过；6 项损坏/缺失负控、非空目标拒绝通过；确认写入丢失 0 |
| 备份与恢复实测 | 快照 4.754 秒，恢复及验证 31.757 秒 |
| head 重启与已知 legacy 升级 | 均通过，canary 保持 |
| CI 自有资源清理 | 恢复目标 teardown 和最终清理步骤成功 |

实施 SHA 的 Windows 新锁全量重验 **733 项通过，101.15 秒**。此前同一
工作树一轮为 732 通过 / 1 失败，实际 HTTP 子进程导入 LangSmith 时报
`SyntaxError`。随后文件 SHA-256 与安装 RECORD 相同、独立语法解析通过，
该 HTTP 回归单独 **1 项通过，30.43 秒**；未修改依赖或源码即重跑全量通过。
首轮失败保留，根因未确定，不将重跑成功描述成已修复该导入异常。

三域覆盖 MySQL 身份/RBAC/REST/file metadata、LangGraph
thread/checkpoint/store、受管文件字节版本。恢复后的重新登录、state/history、
UUID 引用、虚拟 checkpoint 文件、store 值、owner/admin、删除/过期/篡改拒绝
均通过，详见[恢复记录](../prove-data-recovery/validation.md)。

本记录引用已成功的实施提交；最终文档提交自身的精确 SHA、四 Job 及
步骤回执另存工作区根的 `release-gate-evidence.json`，避免在同一提交中
预写自身 SHA 或未来成功。原 A/B、历史失败和旧 tasks/checklist 不反写。
这是新锁工程门禁通过；人工停写/合成 canary 的一次实测不建立生产 RPO/RTO
承诺、自动异地备份、生产 dev runtime 支持或真实效果，生产持久业务仍 NO-GO。
