# 验收清单

- [x] 1. 修复前回归捕获确切的 `_agent_lease_manager` 缺失，原图正控成功。
- [x] 2. 构造与复制保持显式同一租约管理器，无隐式全局回退。
- [x] 3. 原图、copy、with_config 和实际 get_graph 四调用面完成。
- [x] 4. 真实 Agent 工厂与重复复制仍为 CompiledStateGraph。
- [x] 5. 注入 checkpoint/store 可实际读写、原图配置不变。
- [x] 6. 可信主体、请求 ID 与服务端递归保持，伪造身份不能进入节点。
- [x] 7. 租约忙碌/不可用在节点前拒绝，正常/异常调用仅释放一次。
- [x] 8. 原模型/工具预算错误与递归拒绝保持，未宣称修复父子合计预算。
- [x] 9. deadline、显式取消与提前关闭流后释放有效。
- [x] 10. 新增/相关/全量后端测试、isort、发布契约与 diff 检查有实际结果。
- [x] 11. 当前文档状态一致，历史原值不变，HTTP/Linux/容器/Hosted 缺口明确。
- [x] 12. 未调用真实服务、读取真实凭据、覆盖前轮改动或留下临时生成物。

以下为后续部署补验，不能由前述本机修复结果代替。

- [x] 13. 安装版 LangGraph API 的真实 TCP HTTP wait/stream/state 与取消通过，
  身份和 owner 负控有效；测试替身与 NumPy 初始化条件明确。
- [x] 14. Hosted Linux 的图复制/TCP 回归与当前源码镜像容器冒烟实际通过，
  Backend 和 Container Smoke 的验证范围明确，本机范围另有补验。
- [x] 15. 修复 exact SHA 的 Backend、Frontend、Release Contracts、Container Smoke
  Hosted Job 实际成功，未用未提交工作树或旧 run 代替。
- [x] 16. HTTP 补验测试和适用静态门禁通过，本轮临时资源清理完成。
- [x] 17. 本机 Engine 已恢复；受限 Linux 容器中当前源码的 150 项回归通过，
  四文件指纹一致，自有容器已清理，未冒充完整本机五服务重建。
- [ ] 18. 本机从修复 SHA 重建五服务，通过迁移、Redis 恢复和 HTTP 图执行；
  实际租约与取消可验证，独立资源已清理，测试模型和生产边界明确。
  构建/150 项回归/迁移/Redis canary 通过；实际图 ContextVar reset 失败，
  取消租约未及时释放，本项未通过。
- [ ] 19. 重建前端的浏览器登录与分析正控有实际页面证据，未宣称完整浏览器 E2E。
  显式登录和答案渲染已验证；run 为 error，匿名入口/退出跳转丢失端口，
  完整正控未通过。
