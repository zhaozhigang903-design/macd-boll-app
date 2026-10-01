# Codex 开发交接入口

日期：2026-10-01。准备状态：首批Data Engine隔离开发的任务、接口和验收已整理；生产切换条件尚未满足。
本文件不授权现在开始写代码。当前用户要求完成准备工作，仍保留“不修改代码”的边界。之后用户明确说“开始开发”时，按本交接范围实施。

## 工作位置与基线

- 仓库：D:\Quantamental-Phase01\macd-boll-app
- 远程：https://github.com/zhaozhigang903-design/macd-boll-app
- 准备分支：migration/quantamental-v1
- 业务源码基线：81e06c2981e440693abf9b21a6ba43c343b92190
- 文档起始提交：a4822d299879da79c5fa4def2506be2ab02a9293
- 本地环境：D:\Quantamental-Phase01\runtime\Scripts\python.exe（3.12.14）
- 测试数据：D:\Quantamental-Phase01\sandbox-data
- 证据：D:\Quantamental-Phase01\evidence
- 本地检查程序：D:\Quantamental-Phase01\checks
- 所有新增文件、缓存、临时文件和虚拟环境放D盘。已有Python基础运行时在C盘，仅读取；不要为迁移准备擅自搬动系统运行时。
- 原有工作副本D:\GitHub\macd-boll-app保持原状。不要在没有remote的“每日选股”目录开发。

## 先读这些材料

AGENTS.md → docs/README.md → docs/CURRENT_SYSTEM_AUDIT.md → docs/PHASE01_RUNTIME_BASELINE.md → docs/DATA_CONTRACT_READINESS.md → docs/TASKS_DATA_ENGINE_V1.md → docs/ACCEPTANCE_MATRIX.md → docs/SCHEMA_AND_BACKUP_COVERAGE.md。

六份设计文档继续作为目标参考。四份原设计正文缺失与因子权重合计75%的问题均未解决，不能视为已批准完整投资策略。

## 第一批开发范围

只建立可测试的数据契约、单位转换和来源追溯，随后添加独立缓存与影子诊断。保持旧应用作为当前路径。
先做TASK-001，验收后再依次做TASK-002至004；每个任务一个小PR。不并行大拆app.py，不引入FastAPI/React或替换整体框架。

第一批不需要决定Alpha权重、重写回测或接通生产数据库。已知策略问题先记录，保持当前RULE_VERSION原样。
Data→Universe/Factor→Alpha职责顺序用于后续模块依赖；Timing、Risk保持独立，不以MACD替代Quality。

## 最小模块边界

推荐quantamental/data下分为contracts、validation、adapters、cache、diagnostics，具体文件粒度由实施者按可测试性确定：
- contracts：不可变请求、行情行、批次元数据、质量问题、失败原因；不依赖Streamlit。
- adapters：供应商请求与纯转换分开，可注入客户端、时间、日历；禁止导入app.py触发初始化/同步。
- cache：仅新独立数据库；不迁移或覆盖旧SQLite表。
- diagnostics：比对差异与来源，在影子结果中展示；不参与投资评分或下单。
- tests：离线夹具，先覆盖数据损坏、供应商回退、时点与单位边界，再验证旧路径没有被改变。

不创建空Factor/Portfolio骨架冒充实现；公共结果只开放已实现字段。

## 必须保留的行为

旧报告字段、MACD/BOLL公式、综合分、股票排序、持仓动作、成本和止损参数不变。
单位统一造成的新诊断结果不送入旧评分；如果将来接入旧评分会改变数值，必须单列策略影响与验收，不能称为行为等价。
legacy缓存无法证明真实供应商的记录标为legacy_unknown，不从ifind_configured推断provider。
原生周线缺失时，新契约返回native_weekly_unavailable；汇总只用于交叉核验。旧兜底暂存legacy路径并明确差距。

## 完成TASK-001后应交付

新增模块及离线测试、变更说明、固定夹具结果、无生产访问证据和小PR。写清哪些字段是观测值、哪些不可知。
审阅通过前不合并main、不更新Render配置、不触发部署、不恢复真实库。

## 后续阶段的阻塞条件

- 实际iFind鉴权与A/H历史日周线、财务公告/修订覆盖：未验收。
- Render实际SQLite路径、共享数据库连接关系、真实备份恢复：未验收。
- Alpha数学公式、标准化规则、权重和第一版组合能力：待确认。
这些不阻塞第一批纯离线模块开发，但阻塞依赖它们的功能验收和上线。不得声称整个Quantamental规范已最终批准。

## 交给后续Codex的任务文本

阅读本入口与所列材料，核对源码基线和当前用户授权。获得“开始开发”授权后，只执行TASK-001：新增独立数据契约及纯验证/单位转换模块，使用D盘隔离数据完成ACCEPTANCE_MATRIX的A01至A09、A16，保留旧应用路径。
不要修改Alpha权重、旧策略、生产数据或部署。任务完成后提交小PR，说明测试结果、未知字段和后续任务；不自动开始TASK-002或上线。
