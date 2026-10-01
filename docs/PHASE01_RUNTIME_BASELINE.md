# Phase 0.1 运行基线报告

日期：2026-10-01（北京时间）
状态：本次可执行的本地运行及只读云端盘点已完成；完整生产验收仍有未验证项。
应用代码、策略参数、原有业务数据库、Render配置和main均未修改。

## 核心结论
现有应用可以在独立Windows环境启动，页面及样本业务链路能运行。真实A股/港股日K、原生周K和A股基准通过现有函数成功取得。当前应先确认数据时间与供应商口径、线上备份及正式模型范围，再实施迁移，不能把运行通过当作策略有效性证明。

## D盘目录
- 本次根目录：D:\Quantamental-Phase01
- 代码副本：macd-boll-app
- 独立运行环境：runtime
- 样本数据库：sandbox-data
- 临时下载目录：temp
- 核验脚本：checks（在仓库之外）
- 证据、版本清单和日志：evidence
- Phase 0文档仍位于D:\Quantamental-Phase0
任务下载、缓存、报告和数据库都放在D盘。独立运行环境以已有Codex Python 3.12.14为基础，其基础解释器位于C盘；未迁移系统或Codex本身。

## 代码连接与基线
正确现有副本：D:\GitHub\macd-boll-app，remote为https://github.com/zhaozhigang903-design/macd-boll-app.git，HEAD为81e06c2981e440693abf9b21a6ba43c343b92190，受管理文件无改动。
新核验副本：D:\Quantamental-Phase01\macd-boll-app，分支migration/quantamental-v1，HEAD为a4822d299879da79c5fa4def2506be2ab02a9293（相对主线仅添加Phase 0文档）。未修改仓库受管理文件。
Codex中的“每日选股”目录虽然有.git，但没有remote，不是当前应使用的项目连接。没有替换该项目或创建新聊天。

## 环境结果
机器PATH没有python/py启动命令，因此直接双击旧start_windows.bat会遇到“Python was not found”；本次使用D盘独立运行环境解决核验启动。
仓库requirements.txt全部为版本下限，安装得到Streamlit 1.64.0、pandas 3.0.6、NumPy 2.5.3、AKShare 1.19.1、Baostock 0.9.4、OpenAI 3.22.1、psycopg 3.3.6、COS SDK 1.9.44、requests 2.34.2。
pip check无依赖冲突。完整依赖快照见evidence/environment-freeze.txt。本环境是本次解析结果，不代表Render正在使用相同版本，也没有修改仓库依赖声明。
初次安装过程结束时尚未完成；重试成功。安装日志保留在D盘。
运行核验采用隔离配置，禁用生产数据库、iFind和COS凭证；本机未发现windows_config.bat、实际业务数据库或这些连接的进程环境变量。不能推断云端也没有凭证。

## 本地功能结果
|核验|结果|证据与限制|
|---|---|---|
|Python源码语法|通过|5个应用模块均能编译；未生成仓库pyc|
|SQLite初始化|通过|20张表、integrity_check正常，journal_mode=WAL|
|行情缓存及清洗|通过|A/H各1000行样本读写一致；两个非法OHLC样本被删除|
|个股分析|通过|A/H样本产生报告并保存；无真实投资结论|
|回测|通过|A/H各1000行净值；7/4笔已平仓样本交易；成交晚于信号的检查为entry_date>signal_date|
|持仓生命周期|通过|新建、刷新、关闭及历史保留|
|扫描|通过（有限范围）|两证券粗筛路径，零数据异常；候选为空，未覆盖扫描中EV候选输出完整分支|
|手动任务|通过（有限范围）|样本任务completed，cursor/total为2/2|
|定时任务暂停/完成|通过（有限范围）|paused_manual后顺序恢复并completed；不是并发、抢占或无人值守18点触发证明|
|研究任务|通过|两证券批次完成，保存11笔交易并生成汇总；该样本没有正历史EV，组合采用为空|
|有持仓组合路径|通过|另用40笔明确人工构造的正EV成交，采用20笔、388行日级净值；现金非负、仓位不超100%、持仓数约束满足|
|本地快照恢复|通过|隔离库快照恢复15类核心表，恢复后SQLite完整性正常；COS配置和下载仅在核验进程中用本地替身，未访问COS|
|页面及空输入|通过|Streamlit AppTest运行完整app，八个主页签及嵌套页签可读，零页面异常，空代码输入有提示|
|本机服务启动|通过|127.0.0.1:18501健康接口200/ok；核验进程已关闭|
共13项最终功能检查通过，另有本机服务器健康通过。原始offline-results.json保留初次UI核验错误：网络隔离误拦Windows测试框架的loopback连接，不是应用失败；单独允许本机loopback后UI检查通过，见ui-results.json。最终汇总见baseline-results.json。
函数核验以AST读取原文件函数，不执行页面顶层自动同步/调度；仅在核验进程中替换数据获取为标记清楚的样本，策略、交易和数据库函数未改。页面核验运行原始完整应用。不是所有按钮的真实数据端到端或视觉验收。
更正Phase 0静态描述：该基线的init_db已经设置WAL；db_connect的busy_timeout与WAL共同存在。

## 真实行情连接与应用获取结果
直接连接探测：
- AKShare A股日K成功424条。
- Baostock A股日K成功424条，说明本机此次连接并未遇到云端旧日志中的黑名单。
- AKShare港股东财直连探测失败，错误为代理连接中断。

随后调用未修改的应用行情函数，包括现有多源备用路径：
|路径|行数|最后数据日期|结果|
|---|---:|---|---|
|A股日K：sh.600519|605|2026-09-30|通过|
|A股原生周K：sh.600519|187|2026-09-24|通过|
|港股日K：hk.00700|613|2026-09-30|通过|
|港股原生周K：hk.00700|190|2026-09-25|通过|
|沪深300日K|605|2026-09-30|通过|
以上运行禁用iFind，仅核验现有免费源路径，数据存入live-market.db。港股应用获取成功说明备用逻辑/再次请求可取得数据，但代码缺少真实provider记录，不能凭缓存标签确定是哪一个供应商成功。

需核对：两个供应商返回的同日历史前复权价格不完全相同，例如2025-01-02收盘AKShare为1408.42，Baostock为1401.789744，最新日期收盘相同。这是实际数据口径差异，不应直接混拼；原因与复权版本需查供应商规范。A股周K最近标签为09-24，港股为09-25，不能仅凭取得非空数据宣称周标签/完成周对齐正确。
iFind鉴权与历史财务未验证；没有使用用户付费凭证。

## Render只读盘点
已使用用户确认的“志刚's workspace”。
服务macd-boll-app：
- 地址：https://macd-boll-app.onrender.com
- 状态：not_suspended；最近部署live。
- 已部署提交：81e06c2981e440693abf9b21a6ba43c343b92190，与审计代码一致。
- 2026-09-30 22:09:50北京时间完成最新部署。
- 自动部署：main分支提交；PR预览关闭。迁移分支文档提交不会触发该服务自动部署。
- 类型：free Python web service，Singapore，单实例，使用Streamlit启动。
部署成功不等于所有功能运行健康；未在生产页面触发扫描或同步。

数据库macd-boll-db：
- PostgreSQL 16，free，available，未暂停。
- 到期：2026-10-29 20:05北京时间。
- 外部IP允许列表为空，工具无法连接；只读表清单查询被网络规则阻止。没有放开防火墙。
- 未确认应用是否使用此实例、表结构/数据、中央同步或恢复质量。available只说明平台实例状态。

日志：
- 最新部署之前存在解压错误、BaoStock黑名单、AKShare502导致指数和扫描失败的日志。
- 针对最新部署后错误的查询返回Render日志后端503/502，未能验证当前错误情况。
- 未对线上数据库或服务进行任何写操作，也未变更实例套餐、环境变量或部署。

## 尚未验收与处理顺序
1. 在到期前确定生产持久化方案并完成真实数据备份恢复核验；本次本地样本恢复不能替代线上COS或PostgreSQL恢复。
2. 明确iFind的授权覆盖、历史财务公告/修订版本、真实provider及复权/原生周标签；免费源本地可用不能保证云端出口长期可靠。
3. 取得当前部署后日志，并做安全的线上只读状态检查；确认实际数据库与COS连接范围。
4. 为扫描增加成功候选路径、长周期缓存失效、重启/同时点击和资源竞争核验；本次顺序样本不是并发验收。
5. 确认正式四设计草案、Alpha权重及第一版范围，再授权TASK-001数据契约与旧接口适配。
现阶段可以继续规范确认与针对性数据验证；还不具备“全部生产基线已验收”的证据。不直接改投资公式或启动整个Quantamental重构。

## 证据文件
repository-inventory.json：分支、提交、连接、源文件SHA256。
runtime-versions.json、environment-freeze.txt：环境版本。
offline-results.json、ui-results.json、portfolio-results.json、baseline-results.json：检查结果。
live-provider-results.json、live-workflow-results.json及*-sample.csv：真实行情返回。
server-health.json、server-start.log：启动核验。
render-readonly-inventory.json：线上部署与受限数据库盘点。
上述文件位于D:\Quantamental-Phase01\evidence。
