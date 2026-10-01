# Phase 0 Repository Audit

日期：2026-10-01（Asia/Shanghai）
仓库：zhaozhigang903-design/macd-boll-app
基线提交：81e06c2981e440693abf9b21a6ba43c343b92190
规则版本：EV1.1-WEEKLY-NATIVE-2026-09-30
类型：静态代码及文档审计；不代表线上运行验证或投资绩效认证。

## 结论
系统已具备多源行情、原生周K、基本面当前快照、持仓、后台扫描、交易模拟、组合研究、滚动及前向验证。适合渐进迁移。最主要缺口是历史时点财务数据、Alpha/Timing分离及独立任务执行。不能将它描述为只有MACD/BOLL的空壳，也不能将当前基本面叠加排名视为已验证Quantamental Alpha。

## 连接与范围
GitHub连接已成功读取账号及目标仓库，账号具备push/admin权限。Codex项目列表包含ChatGPT项目“MACD”和本地Git项目“每日选股”（C:\\Users\\17515\\Documents\\每日选股）。当前聊天工作目录是ChatGPT项目镜像，不是已验证的目标仓库工作副本；尚未核实“每日选股”的remote。没有创建新聊天或修改项目配置。

仓库递归树共13个文件：.gitignore、.streamlit/config.toml、README.md、WINDOWS.md、app.py、engine.py、ifind_http.py、requirements.txt、shared_store.py、cos_backup.py、start_windows.bat、windows_config.example.bat。app.py约8849行，功能集中。未发现AGENTS.md、docs、测试目录、CI工作流、render.yaml或依赖锁文件。

已取得主要Python模块及启动/配置文档并检查核心调用链。没有启动应用、联网调用行情、检查真实SQLite/PostgreSQL/COS数据、访问Render部署或进行性能测量。本地读取程序因磁盘空间不足启动失败；sources/参考材料未读取也未修改。以下“已实现”仅说明代码存在；参数、凭证和线上运行状态未确认。

## 架构与功能盘点
|项目|代码事实|迁移判断|
|---|---|---|
|前端|Streamlit八个页签：分析、选股、持仓、回测、历史、方法、设置、研究；自定义CSS/HTML|保留中文交互；不是React前端。[app.py:7169](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L7169)|
|后端|同进程Python函数负责UI、数据、策略和持久化；无独立FastAPI服务|先抽纯逻辑，框架替换不是Phase 0任务。[app.py:1](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L1)|
|主数据库|本地SQLite，busy_timeout=30秒；运行目录可配置|不直接改为PostgreSQL唯一主库。[app.py:46](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L46)|
|共享数据库|psycopg连接PostgreSQL，按TABLES推拉核心表|连接存在不等于线上已配置；需明确同步冲突权威。[shared_store.py:11](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/shared_store.py#L11)|
|iFind|HTTP token缓存/刷新、历史D/W、批量、基本名称、问财、通用财务接口|已有适配器可复用；财务通用接口不等于历史财务库。[ifind_http.py:206](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/ifind_http.py#L206)、[ifind_http.py:390](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/ifind_http.py#L390)|
|AKShare|A股东财/腾讯/新浪回退，港股东财/新浪|保留多源归一化，补来源与单位契约。[app.py:1823](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L1823)、[app.py:1942](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L1942)|
|Baostock|A股行情、周K、指数和历史股票池；会话锁与线程深度控制|不是港股兜底；配置iFind时部分路径不建立BS会话。[app.py:1867](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L1867)|
|行情流程|代码标准化→缓存边界→补历史/尾部→多源下载→清洗→SQLite→指标|已有增量与失败回退；需复权版本和实际来源。[app.py:2147](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L2147)|
|日K|OHLC/成交量校验、数值转换、日期排序去重|保留清洗；补交易日缺口、单位、时点和复权变化检查。[app.py:1669](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L1669)|
|周K|原生周K优先，日K聚合交叉验证，但多个路径允许聚合兜底/初筛|与宪法“聚合仅校验”不一致，必须显式决策。[app.py:2588](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L2588)、[app.py:3312](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L3312)、[app.py:4558](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4558)|
|缓存|SQLite行情、截图、EV、财务快照；st.cache_data证券池；EV部分路径14天复用|保留缓存，增加数据版本/质量和失效策略。[app.py:1495](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L1495)、[app.py:4070](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4070)、[app.py:4451](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4451)|
|后台任务|daemon线程+SQLite任务状态/游标；修复残留running|无Redis/Celery独立队列；进程停止线程消失。[app.py:5011](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5011)、[app.py:5224](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5224)|
|定时扫描|页面脚本执行时检查北京时间run_after_hour，默认18点|不是已证实的外部调度；无UI脚本执行时能否触发未验证。[app.py:5272](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5272)、[app.py:7148](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L7148)|
|手动扫描|按job_type区分，暂停定时任务并于结束后恢复|优先级机制已存在，但不是完全独立资源。[app.py:5030](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5030)|
|技术评分|截图score_engine、数值numeric_score、独立engine.py各有评分逻辑|冻结旧输出为legacy Timing；避免三个实现继续漂移。[app.py:984](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L984)、[app.py:2689](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L2689)、[engine.py:94](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/engine.py#L94)|
|基本面|问财当前A股快照；ROE、现金流、增长、PE/PB/股息、杠杆按固定阈值打分|有初步实现，无行业分位标准化/历史财务版本；港股此路径返回空。[app.py:4369](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4369)、[app.py:4451](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4451)|
|综合评分|技术25%、买点12%、周线13%、RS10%、市场8%、基本面20%、EV12%|不是独立Alpha；基本面内部权重质量35/成长30/估值20/健康15。[app.py:4536](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4536)|
|回测|次日成交、风险位/技术退出、费用滑点、EV、bootstrap、净化滚动、压力成本|不是没有回测；尚不能证明因子组合有效。[app.py:3680](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L3680)、[app.py:3820](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L3820)、[app.py:5323](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5323)|
|组合研究|研究证券池历史区间、交易过滤、逐日组合现金/净值/仓位|有基础组合模拟；相关性、行业风险和精确执行时序尚待补。[app.py:5793](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5793)、[app.py:6177](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L6177)|
|策略实验|训练/验证/测试分段、测试揭示、候选策略、forward signals|保留审计轨迹，再验证所有调用点无泄漏。[app.py:6638](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L6638)、[app.py:6822](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L6822)|
|备份|腾讯COS SQLite快照，完整性校验和核心恢复|备份只说明代码能力；未做恢复演练。[cos_backup.py:81](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/cos_backup.py#L81)|

## 数据库结构
SQLite共20个CREATE TABLE声明：analyses、extraction_cache、market_daily_cache、market_cache_meta、positions、position_snapshots、forward_signals、ev_cache、research_runs、research_members、research_membership、research_stock_results、research_trades、strategy_experiments、strategy_experiment_trades、strategy_candidates、factor_snapshot_cache、screener_jobs、screener_job_results、screener_settings。DDL始于[app.py:516](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L516)。

market_daily_cache同表保存不同frequency语义的数据，用adjustflag标签区分日/周与来源类别。factor_snapshot_cache保存trade_date+universe+source的JSON，不含逐财报公告/修订记录。任务表含job_type/status/cursor，但无跨进程worker租约和唯一每日调度键。

PostgreSQL同步11表：positions、position_snapshots、forward_signals、research_runs、research_members、research_membership、research_stock_results、research_trades、strategy_experiments、strategy_experiment_trades、strategy_candidates。analyses、任务、行情和因子缓存不属于这个TABLES集合。LIGHT_TABLES与HEAVY_TABLES分开；默认先push再pull，对可变表按文本updated_at比较。参见[shared_store.py:14](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/shared_store.py#L14)及sync_tables；删除传播、时钟偏差和并发冲突需验证。

## 优先发现与证据
### P0：财务历史时点缺失
当前快照明确只用于今天排名，不进入历史EV，这是正确的隔离（[app.py:4451](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4451)）。但没有报告期+公告时间+修订版本数据库，现有技术EV不能验证新Alpha排序。行业标准化和ROIC/现金流质量完整公式尚缺；固定阈值与目标宪法冲突。

### P0：周K可用时间需要证明
build_score_series使用trade_date向后合并周K（[app.py:3312](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L3312)）；confirmed_native_weekly按周五判定完成，而非供应商published_at。若供应商用周初标签表示含全周数据，会把未来信息合并到周初；这是需样本验证的条件性风险，不是已证实供应商行为。节假日提前收周亦需市场日历。

### P0：综合分与Alpha/Timing边界
midlong_composite_score混合技术、市场、基本面及历史EV。screen_codes在基本面排名前先进行技术/聚合周K过滤（[app.py:4558](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L4558)），所以高质量低Timing公司可能根本不进入候选。应增加独立Alpha候选视图和择时附加层，而非直接改旧策略。

### P1：任务执行与恢复竞态
手动任务将定时状态置paused_manual，worker在批次边界检查，已经进行的API调用不会即时停止。两者共享SQLite、会话和进程。暂停后恢复可与尚未退出的worker交错；现有线程登记可限制同进程重复启动，但跨进程无租约。秒级job_id、查询后插入的调度逻辑也需要幂等验证。当前没有证据证明独立任务不会互相阻塞。

### P1：增量复权与来源可追溯
market_cache_flag根据ifind_configured决定标签（[app.py:1987](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L1987)），实际下载却可能回退AKShare/Baostock，缓存标签不一定代表成功供应商。仅尾部补齐前复权价格（[app.py:2147](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L2147)）在复权基准变化时可能拼接不同尺度，需要公司行动/因子版本及重算窗口。

### P1：组合回测时序与末期持仓
research_daily_portfolio先以当天收盘更新在持持仓，再分配当天entry_date的新仓（[app.py:6229](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L6229)）；若交易为当天开盘，仓位可能依赖尚未知的收盘净值，需修复前验证。simulate_structural_trades忽略未退出最后一笔，run_backtest只用完成交易重建净值（[app.py:3680](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L3680)、[app.py:5323](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5323)），因此末期未平仓的绩效/暴露可能遗漏。新组合引擎必须显式计入。

### P1：证券池历史覆盖
A股有按月历史股票池，值得保留；港股标记current_only，无历史主板快照（[app.py:5842](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/app.py#L5842)），存在幸存者偏差。A股fallback_current也需清楚标记，不能当严格历史结果。

### P2：维护、依赖与备份范围
app.py集中约8849行，重复评分与指标实现，主app没有导入engine.py（静态导入检查），engine.py不能直接当活跃核心。requirements全部为下限范围，未锁定环境；无仓库CI/测试。COS _safe_snapshot仅清空EXCLUDED_TABLES中的行情/EV/截图数据，而factor_snapshot_cache不在排除集，因子快照仍随备份保留，与“纯核心数据”描述存在差异（[cos_backup.py:29](https://github.com/zhaozhigang903-design/macd-boll-app/blob/81e06c2981e440693abf9b21a6ba43c343b92190/cos_backup.py#L29)）。

## 性能推断（未测量）
已有分阶段粗筛、iFind批量预取、EV缓存和双请求并发，可保留。潜在瓶颈是逐股DataFrame循环和重复历史评分/模拟、频繁SQLite连接与写入、多源重试等待、Baostock锁、双向同步全表加载。不能承诺5000只<5分钟；须区分冷缓存/热缓存、A/H市场、供应商配额，记录阶段耗时、失败率、内存、锁等待及缓存命中。

## 保留/重构/新增/延期
保留：行情适配、代码归一化、清洗、原生周K路径、缓存、旧UI、持仓与共享表、研究和forward框架、成本及滚动验证。
重构：职责隔离、真实provider/frequency、缓存版本、任务幂等与资源隔离、交易时序、策略参数版本。
新增：时点财务与证券主数据、因子处理契约、独立Alpha排名、可执行市场约束、组合暴露/相关性风险。
延期：框架整体替换、机器学习、另类数据、自动参数优化和AI扩展。

## Phase 0完成边界
仓库静态审计及迁移文档完成；本地checkout/线上连接、运行回归、数据供应商样本与正式策略基线未完成。后续开发必须以迁移计划中的门槛为准。
