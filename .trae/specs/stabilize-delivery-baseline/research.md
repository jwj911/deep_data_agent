# 运行时选择依据

核查日期：2026-10-28。以下是官方资料核查，兼容性仍以实际回归为准。

- 官方安装包 `langgraph_api/cli.py` 的 `_support_level` 将同 major
  最新 minor 标为 active，落后一 minor 为 critical，两 minor 或以上为 EOL。
  本机 `0.7.28` 相对官方 PyPI 最新 `0.16.8` 为 EOL。
  来源：[官方仓库](https://github.com/langchain-ai/langgraph)
  与安装包源码；版本事实来自
  [PyPI API](https://pypi.org/pypi/langgraph-api/json)。
- `langgraph-api 0.16.8` 要求 Python >=3.11、cryptography >=50.0.0、
  langgraph-runtime-inmem >=0.36.0.dev0,<0.37.0.dev0，
  checkpoint >=3.0.1,<5、LangGraph >=0.4.10,<2。
  来源：[该版本权威元数据](https://pypi.org/pypi/langgraph-api/0.16.8/json)。
- `deepagents 0.7.32` 要求 LangChain >=1.4.7,<2 和 Core >=1.7.0,<2；
  LangChain 1.4.7 要求 LangGraph >=1.2.12,<1.3，选择 1.2.18。
  来源：[DeepAgents 元数据](https://pypi.org/pypi/deepagents/0.7.32/json)、
  [LangChain 元数据](https://pypi.org/pypi/langchain/1.4.7/json)、
  [LangGraph 元数据](https://pypi.org/pypi/langgraph/1.2.18/json)。
- cryptography 50.0.2 发布于 2026-09-30，满足新 API 要求；
  LangChain OpenAI 1.7.3 要求 OpenAI >=2.45.0，选择已发布稳定版 3.40.0。
  来源：[cryptography](https://pypi.org/pypi/cryptography/50.0.2/json)、
  [LangChain OpenAI](https://pypi.org/pypi/langchain-openai/1.7.3/json)、
  [OpenAI](https://pypi.org/pypi/openai/3.40.0/json)。
- 实际解析发现 grpcio-tools 1.81.1 要求 setuptools >=77.0.1，原固定
  75.8.0 与新 API 无解。候选改用 80.9.0，保留旧认证依赖的兼容边界。
  来源：[gRPC 工具元数据](https://pypi.org/pypi/grpcio-tools/1.81.1/json)、
  [setuptools 元数据](https://pypi.org/pypi/setuptools/80.9.0/json)。

维护策略是官方单源合同，包版本和依赖约束各来自其发布方，不能将元数据
之间的吻合称为跨运行时实证。候选锁必须通过完整本机、Linux 与 Hosted。
使用 `langgraph dev` 文件持久化仍属开发运行时；挂载和人工恢复演练不能
把它升级为具有生产 HA、持续备份或承诺 RPO 的部署。
