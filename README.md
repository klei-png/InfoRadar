# InfoRadar

一个持续运行的个性化信息监测系统（AI + 金融领域）。通过搜索引擎聚合多源信息，结合 LangGraph 和大语言模型（LLM）进行智能去重、分析与推荐，生成每日精选简报。

## 核心架构

- **数据采集**：基于 Tavily Search API，按配置的 Query 定时拉取。
- **数据处理**：L1 URL 规范化去重 + L2 标题 SimHash 相似度去重。
- **数据存储**：PostgreSQL（原生支持 `pgvector`，为后续语义聚类/召回预留）。
- **推荐引擎**：基于 **LangGraph** 构建的状态图，驱动 LLM 进行记忆感知、事件脉络梳理与个性化推荐。

## 目录结构

```text
InfoRadar/
├── config/
│   ├── sources.yaml            # 搜索 Query 配置（关注领域、频率、权重等）
│   └── search_providers.yaml   # 搜索引擎提供商配置
├── src/
│   ├── config/                 # 配置校验与解析（基于 Pydantic）
│   ├── collectors/             # 采集器实现（SearchCollector）
│   ├── search/                 # 搜索引擎适配层（支持 Tavily 等）
│   ├── pipeline/               # 数据处理流水线（去重等）
│   ├── db/                     # 数据库连接与读写（PostgreSQL）
│   ├── models/                 # 数据模型定义（Item / RawItem 等）
│   ├── agent/                  # LangGraph 智能体（核心推荐逻辑）
│   └── scripts/                # 测试与调试脚本
├── docker-compose.yml          # 本地开发数据库环境
├── .env.example                # 环境变量示例
└── pyproject.toml