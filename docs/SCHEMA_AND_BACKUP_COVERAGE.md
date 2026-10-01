# 当前数据库字段与备份覆盖

基线：81e06c2981e440693abf9b21a6ba43c343b92190。来自D盘人工样本库的建表结果及静态代码；不是生产表查询。

|表|SQLite字段（名称/类型/主键序号）|PostgreSQL同步|COS快照保留数据|COS恢复核心表|
|---|---|---|---|---|
|analyses|id:INTEGER PK1; created_at:TEXT; symbol:TEXT; market:TEXT; horizon:TEXT; position_state:TEXT; rating:TEXT; state:TEXT; stage:TEXT; score:REAL; trend_score:REAL; momentum_score:REAL; weekly_score:REAL; confirm_score:REAL; confidence:INTEGER; price:TEXT; boll_mid:TEXT; key_support:TEXT; key_resistance:TEXT; model_mode:TEXT; weekly_used:INTEGER; raw_result:TEXT; data_quality:INTEGER|否|保留|是|
|ev_cache|code:TEXT PK1; stock_date:TEXT PK2; benchmark_date:TEXT PK3; rule_version:TEXT PK4; payload:TEXT; updated_at:TEXT|否|清空|否|
|extraction_cache|signature:TEXT PK1; created_at:TEXT; payload:TEXT; raw_result:TEXT|否|清空|否|
|factor_snapshot_cache|trade_date:TEXT PK1; universe:TEXT PK2; source:TEXT PK3; payload:TEXT; updated_at:TEXT|否|保留|否|
|forward_signals|id:INTEGER PK1; code:TEXT; name:TEXT; market:TEXT; signal_date:TEXT; price:REAL; tier:TEXT; technical_score:REAL; buy_score:REAL; weekly_score:REAL; rr:REAL; market_score:REAL; rs_score:REAL; ev_r:REAL; ev_lcb_r:REAL; stress_ev_r:REAL; ev_samples:INTEGER; risk_price:REAL; rule_version:TEXT; status:TEXT; realized_r:REAL; exit_date:TEXT; created_at:TEXT; updated_at:TEXT|是|保留|是|
|market_cache_meta|code:TEXT PK1; last_checked:TEXT; updated_at:TEXT|否|清空|否|
|market_daily_cache|code:TEXT PK1; trade_date:TEXT PK2; open:REAL; high:REAL; low:REAL; close:REAL; vol:REAL; amount:REAL; pctChg:REAL; turn:REAL; tradestatus:TEXT; isST:TEXT; adjustflag:TEXT PK3; fetched_at:TEXT|否|清空|否|
|position_snapshots|id:INTEGER PK1; code:TEXT; snapshot_date:TEXT; price:REAL; technical_score:REAL; trend_score:REAL; momentum_score:REAL; weekly_score:REAL; confirm_score:REAL; market_score:REAL; pnl_pct:REAL; action:TEXT; reason:TEXT; created_at:TEXT|是|保留|是|
|positions|code:TEXT PK1; name:TEXT; entry_date:TEXT; entry_price:REAL; shares:REAL; initial_stop:REAL; entry_score:REAL; peak_score:REAL; last_score:REAL; last_price:REAL; last_market_score:REAL; last_action:TEXT; note:TEXT; active:INTEGER; created_at:TEXT; updated_at:TEXT|是|保留|是|
|research_members|run_id:TEXT PK1; seq:INTEGER PK2; code:TEXT; name:TEXT; market:TEXT|是|保留|是|
|research_membership|run_id:TEXT PK1; period_start:TEXT PK2; period_end:TEXT; code:TEXT PK3; name:TEXT; market:TEXT|是|保留|是|
|research_runs|run_id:TEXT PK1; created_at:TEXT; updated_at:TEXT; universe:TEXT; years:INTEGER; status:TEXT; cursor:INTEGER; total:INTEGER; rule_version:TEXT; benchmark_name:TEXT; note:TEXT|是|保留|是|
|research_stock_results|run_id:TEXT PK1; code:TEXT PK2; name:TEXT; market:TEXT; trade_count:INTEGER; ev_r:REAL; conservative_ev_r:REAL; win_rate:REAL; avg_win_r:REAL; avg_loss_r:REAL; profit_factor:REAL; oos_ev_r:REAL; oos_stability:TEXT; updated_at:TEXT|是|保留|是|
|research_trades|run_id:TEXT; code:TEXT; name:TEXT; market:TEXT; signal_date:TEXT; entry_date:TEXT; exit_date:TEXT; return_pct:REAL; r_multiple:REAL; entry_price:REAL; exit_price:REAL; stop_price:REAL; initial_risk_pct:REAL; holding_days:INTEGER; technical_score:REAL; buy_score:REAL; weekly_score:REAL; rr:REAL; market_score:REAL; rs_score:REAL; opportunity_score:REAL; exit_reason:TEXT|是|保留|是|
|screener_job_results|job_id:TEXT PK1; code:TEXT PK2; payload:TEXT; updated_at:TEXT|否|保留|是|
|screener_jobs|job_id:TEXT PK1; job_type:TEXT; trade_date:TEXT; universe:TEXT; exclude_st:INTEGER; batch_size:INTEGER; status:TEXT; cursor:INTEGER; total:INTEGER; market_score:REAL; market_regime:TEXT; benchmark_name:TEXT; error:TEXT; stats_json:TEXT; created_at:TEXT; updated_at:TEXT|否|保留|是|
|screener_settings|id:INTEGER PK1; auto_daily:INTEGER; universe:TEXT; exclude_st:INTEGER; batch_size:INTEGER; run_after_hour:INTEGER; updated_at:TEXT|否|保留|是|
|strategy_candidates|candidate_id:TEXT PK1; experiment_id:TEXT; created_at:TEXT; module:TEXT; config_id:TEXT; config_json:TEXT; status:TEXT; note:TEXT|是|保留|是|
|strategy_experiment_trades|experiment_id:TEXT PK1; config_id:TEXT PK2; code:TEXT PK3; signal_date:TEXT PK4; entry_date:TEXT; exit_date:TEXT; r_multiple:REAL; return_pct:REAL; holding_days:INTEGER; opportunity_score:REAL; initial_risk_pct:REAL|是|保留|是|
|strategy_experiments|experiment_id:TEXT PK1; research_run_id:TEXT; module:TEXT; created_at:TEXT; updated_at:TEXT; status:TEXT; cursor:INTEGER; total:INTEGER; train_end:TEXT; validation_end:TEXT; test_revealed:INTEGER; config_json:TEXT; rule_version:TEXT; note:TEXT|是|保留|是|

factor_snapshot_cache在快照中保留，但不在restore_core列表内。不能假定全部快照表均会被核心恢复流程恢复。
共享库11表、COS核心恢复15表都不能称为SQLite20表全量恢复。每项丢弃或重建需要在生产备份方案中明确。
当前字段使用legacy日期/字符串，不代表已经具备财务PIT或供应商时点契约。
