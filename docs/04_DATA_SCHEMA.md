# 数据结构迁移草案

状态：原 Data Schema 正文未取得；本文件仅设计建议，未创建或修改任何数据库。

## 当前事实
SQLite是本地运行主库。PostgreSQL通过shared_store.py同步部分核心业务表；行情与EV缓存保留本地。所有表清单见审计。

## 候选规范表
|表|建议键/版本|作用|
|---|---|---|
|security_master|security_id+有效期间|市场、证券代码沿革、币种、上市/退市、行业历史|
|daily_price|security_id+trade_date+provider+adjustment+version|原始行情、复权口径、获取/可用时间与质量|
|weekly_price|security_id+period_end+provider+adjustment+version|原生周K、周期起止、是否完成、published_at|
|fundamental_snapshot|security_id+report_period+announcement_at+revision|财务报告、公告时间、修订、单位和币种|
|universe_membership|universe_version+security_id+有效期间|当时可知证券池与退市样本|
|factor_scores|security_id+as_of+factor_version+data_version|因子覆盖、清洗/行业/标准化记录|
|strategy_versions|strategy_version|公式、参数、权重、审批和验证引用|
|job_runs|job_id|任务来源、状态、游标、租约、心跳和幂等键|

日线与周线必须区分frequency；provider必须为实际成功返回的来源，不得仅依据iFind是否配置标记。复权数据更新需有因子/版本与重算窗口。

## 迁移限制
不替换现有表。先做字段映射与只读适配，备份恢复演练后才能启用双写。PostgreSQL、SQLite及备份源各自有权威范围，需明确冲突和删除规则。全量回填、DDL、线上数据迁移不在Phase 0授权范围。
