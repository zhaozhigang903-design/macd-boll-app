# Quantamental 文档导航

2026-10-01建立。Phase 0仅审计与迁移准备，应用代码、数据库和部署均未修改。

|文件|来源与状态|
|---|---|
|../AGENTS.md|从“转到Codex指南”的项目宪法代码块恢复；追加Phase 0边界，待正式基线审阅|
|01_STRATEGY_ARCHITECTURE.md|原稿正文未取得；根据已恢复材料整理的迁移草案|
|02_FACTOR_DICTIONARY.md|原稿正文未取得；候选因子与未决公式清单|
|03_BACKTEST_SPECIFICATION.md|原稿正文未取得；回测正确性与验证草案|
|04_DATA_SCHEMA.md|原稿正文未取得；候选schema，不是已实施DDL|
|05_PRD.md|恢复历史对话PRD回复，保留正文；待确认|
|06_DEVELOPMENT_ROADMAP.md|恢复历史对话路线图回复，保留正文；待确认|
|CURRENT_SYSTEM_AUDIT.md|基于固定提交的代码证据；静态审计|
|QUANTAMENTAL_MIGRATION_PLAN.md|本次建议顺序与开发门槛；尚未实现|
|OPEN_DECISIONS.md|待明确的规范冲突及证据缺口|

来源对话：chatgpt-conversation://6abdabb6-4c78-83e9-b890-0b0de359664b。
读取范围只包含项目宪法、PRD、路线图及接管指导；对话提到此前四文档已完成，但未取得其正文。本目录不宣称完整恢复原始设计包。示例股票评分、阈值、权重、仓位和性能目标不能直接用于生产。应用架构现状以审计为准，目标技术选型以确认后的设计为准。

阅读顺序：审计→迁移计划→决策表→宪法→六份设计文档。正式批准后需将草案状态改为确定版本，并解决跨文档冲突，历史对话只作出处。

## 2026-10-01 运行基线与开发交接补充

新增只读准备材料：
- PHASE01_RUNTIME_BASELINE.md：D盘运行基线及证据限制。
- DATA_CONTRACT_READINESS.md：真实行情差异与配置说明。
- DATA_CONTRACT_DRAFT.md：行情时点、单位、复权与来源草案。
- SCHEMA_AND_BACKUP_COVERAGE.md：当前20表字段、11表同步与15表核心恢复覆盖。
- CODEX_DEVELOPMENT_HANDOFF.md：后续Codex开发入口。
- TASKS_DATA_ENGINE_V1.md：四个顺序实施任务及禁止边界。
- ACCEPTANCE_MATRIX.md：逐项离线/联调验收，尚未实施。
- DEVELOPMENT_READINESS.md：隔离开发、因子实施与生产切换分开的门槛。
- PRODUCTION_DATA_PRESERVATION.md：真实数据保全与恢复方案。

首批纯数据模块可以在后续明确授权后开始D盘隔离开发。iFind真实权限、生产备份恢复、因子公式/权重尚未验收或确认，不将其宣称为全部已完成。
优先从CODEX_DEVELOPMENT_HANDOFF.md进入；旧路线图与决策表保留出处，最新状态以DEVELOPMENT_READINESS.md和各专项证据为准。