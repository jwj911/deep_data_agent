# 修复认证跳转并重验部署场景

用户已要求实施。起点为 `fix/agent-graph-copy @ 8e552f3` 的当前未提交工作树，
包含已验证的 `repair-async-lease-context`；前轮失败证据继续保留。

## 范围与合同

修复静态 Nginx 在宿主端口映射下生成登录跳转的问题。匿名入口、登录、退出、
无尾斜线地址和带查询的深链接必须保持浏览器 Origin、端口及对应路径/查询；
不得通过绕过身份验证或更换固定 API Origin 解决跳转。

使用当前源码的生产静态构建与独立五服务部署重验。运行前核对源码/镜像指纹，
使用合成用户、随机测试密钥、独立数据库/文件卷及受控模型传输；真实图、API
worker、MySQL 认证、Redis 租约及浏览器操作必须执行。成功判定包含最终 run
状态与租约释放，不能把 HTTP 200 或部分答案渲染当作成功。

验证覆盖双用户/管理员权限、文件共享与隔离、实际 wait/stream/取消/timeout、
Redis 故障恢复、空库迁移、head 重启和已知 legacy 升级。生产持久化恢复、
真实模型效果、父子合计预算及依赖现代化不由本轮局部验收自动放行。
不改前轮 tasks/checklist，不提交、推送、合并或操作现有业务容器。

## 最小复现

原缓存前端镜像的 Nginx 配置 SHA-256 与工作树一致；在独立只读容器中请求：

```text
GET http://127.0.0.1:11370/data_copilot/login
301 Location: http://127.0.0.1/data_copilot/login/
AssertionError: Authentication redirect lost the host port
```

临时容器已删除。首次附加 cap-drop 的执行器未取到端口映射，未采集启动日志；
仅去掉该限制后复现成功，未将其认定为产品缺陷。

回归入口为 `scripts/verify_static_frontend_http.py --base-url <HTTP origin>`，
直接断言真实 HTTP 跳转的 Origin、端口、路径/查询及静态页面 200。
实施与完整重验结果另记，不反写前轮失败或 Hosted 结果。
