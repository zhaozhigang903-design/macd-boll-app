import os
import sqlite3
from datetime import datetime

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None


SHARED_DATABASE_URL = (os.getenv("SHARED_DATABASE_URL") or "").strip()

TABLES = {
    "positions": {
        "cols": [
            "code","name","entry_date","entry_price","shares","initial_stop","entry_score",
            "peak_score","last_score","last_price","last_market_score","last_action","note",
            "active","created_at","updated_at"
        ],
        "keys": ["code"],
        "ts": "updated_at",
        "ddl": """
        CREATE TABLE IF NOT EXISTS positions(
          code TEXT PRIMARY KEY,
          name TEXT,
          entry_date TEXT NOT NULL,
          entry_price DOUBLE PRECISION NOT NULL,
          shares DOUBLE PRECISION NOT NULL DEFAULT 0,
          initial_stop DOUBLE PRECISION,
          entry_score DOUBLE PRECISION,
          peak_score DOUBLE PRECISION,
          last_score DOUBLE PRECISION,
          last_price DOUBLE PRECISION,
          last_market_score DOUBLE PRECISION,
          last_action TEXT,
          note TEXT,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    },
    "position_snapshots": {
        "cols": [
            "code","snapshot_date","price","technical_score","trend_score","momentum_score",
            "weekly_score","confirm_score","market_score","pnl_pct","action","reason","created_at"
        ],
        "keys": ["code","snapshot_date"],
        "ts": None,
        "ddl": """
        CREATE TABLE IF NOT EXISTS position_snapshots(
          id BIGSERIAL PRIMARY KEY,
          code TEXT NOT NULL,
          snapshot_date TEXT NOT NULL,
          price DOUBLE PRECISION,
          technical_score DOUBLE PRECISION,
          trend_score DOUBLE PRECISION,
          momentum_score DOUBLE PRECISION,
          weekly_score DOUBLE PRECISION,
          confirm_score DOUBLE PRECISION,
          market_score DOUBLE PRECISION,
          pnl_pct DOUBLE PRECISION,
          action TEXT,
          reason TEXT,
          created_at TEXT NOT NULL,
          UNIQUE(code,snapshot_date)
        )
        """
    },
    "forward_signals": {
        "cols": [
            "code","name","market","signal_date","price","tier","technical_score","buy_score",
            "weekly_score","rr","market_score","rs_score","ev_r","ev_lcb_r","stress_ev_r",
            "ev_samples","risk_price","rule_version","status","realized_r","exit_date",
            "created_at","updated_at"
        ],
        "keys": ["code","signal_date"],
        "ts": "updated_at",
        "ddl": """
        CREATE TABLE IF NOT EXISTS forward_signals(
          id BIGSERIAL PRIMARY KEY,
          code TEXT NOT NULL,
          name TEXT,
          market TEXT,
          signal_date TEXT NOT NULL,
          price DOUBLE PRECISION,
          tier TEXT,
          technical_score DOUBLE PRECISION,
          buy_score DOUBLE PRECISION,
          weekly_score DOUBLE PRECISION,
          rr DOUBLE PRECISION,
          market_score DOUBLE PRECISION,
          rs_score DOUBLE PRECISION,
          ev_r DOUBLE PRECISION,
          ev_lcb_r DOUBLE PRECISION,
          stress_ev_r DOUBLE PRECISION,
          ev_samples INTEGER,
          risk_price DOUBLE PRECISION,
          rule_version TEXT,
          status TEXT NOT NULL DEFAULT 'tracking',
          realized_r DOUBLE PRECISION,
          exit_date TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(code,signal_date)
        )
        """
    },
    "research_runs": {
        "cols": [
            "run_id","created_at","updated_at","universe","years","status","cursor","total",
            "rule_version","benchmark_name","note"
        ],
        "keys": ["run_id"],
        "ts": "updated_at",
        "ddl": """
        CREATE TABLE IF NOT EXISTS research_runs(
          run_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          universe TEXT NOT NULL,
          years INTEGER NOT NULL,
          status TEXT NOT NULL,
          cursor INTEGER NOT NULL DEFAULT 0,
          total INTEGER NOT NULL DEFAULT 0,
          rule_version TEXT NOT NULL,
          benchmark_name TEXT,
          note TEXT
        )
        """
    },
    "research_members": {
        "cols": ["run_id","seq","code","name","market"],
        "keys": ["run_id","seq"],
        "ts": None,
        "ddl": """
        CREATE TABLE IF NOT EXISTS research_members(
          run_id TEXT NOT NULL,
          seq INTEGER NOT NULL,
          code TEXT NOT NULL,
          name TEXT,
          market TEXT,
          PRIMARY KEY(run_id,seq)
        )
        """
    },
    "research_membership": {
        "cols": ["run_id","period_start","period_end","code","name","market"],
        "keys": ["run_id","period_start","code"],
        "ts": None,
        "ddl": """
        CREATE TABLE IF NOT EXISTS research_membership(
          run_id TEXT NOT NULL,
          period_start TEXT NOT NULL,
          period_end TEXT NOT NULL,
          code TEXT NOT NULL,
          name TEXT,
          market TEXT,
          PRIMARY KEY(run_id,period_start,code)
        )
        """
    },
    "research_stock_results": {
        "cols": [
            "run_id","code","name","market","trade_count","ev_r","conservative_ev_r","win_rate",
            "avg_win_r","avg_loss_r","profit_factor","oos_ev_r","oos_stability","updated_at"
        ],
        "keys": ["run_id","code"],
        "ts": "updated_at",
        "ddl": """
        CREATE TABLE IF NOT EXISTS research_stock_results(
          run_id TEXT NOT NULL,
          code TEXT NOT NULL,
          name TEXT,
          market TEXT,
          trade_count INTEGER,
          ev_r DOUBLE PRECISION,
          conservative_ev_r DOUBLE PRECISION,
          win_rate DOUBLE PRECISION,
          avg_win_r DOUBLE PRECISION,
          avg_loss_r DOUBLE PRECISION,
          profit_factor DOUBLE PRECISION,
          oos_ev_r DOUBLE PRECISION,
          oos_stability TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(run_id,code)
        )
        """
    },
    "research_trades": {
        "cols": [
            "run_id","code","name","market","signal_date","entry_date","exit_date","return_pct",
            "r_multiple","entry_price","exit_price","stop_price","initial_risk_pct","holding_days",
            "technical_score","buy_score","weekly_score","rr","market_score","rs_score",
            "opportunity_score","exit_reason"
        ],
        "keys": ["run_id","code","signal_date"],
        "ts": None,
        "ddl": """
        CREATE TABLE IF NOT EXISTS research_trades(
          run_id TEXT NOT NULL,
          code TEXT NOT NULL,
          name TEXT,
          market TEXT,
          signal_date TEXT NOT NULL,
          entry_date TEXT,
          exit_date TEXT,
          return_pct DOUBLE PRECISION,
          r_multiple DOUBLE PRECISION,
          entry_price DOUBLE PRECISION,
          exit_price DOUBLE PRECISION,
          stop_price DOUBLE PRECISION,
          initial_risk_pct DOUBLE PRECISION,
          holding_days INTEGER,
          technical_score DOUBLE PRECISION,
          buy_score DOUBLE PRECISION,
          weekly_score DOUBLE PRECISION,
          rr DOUBLE PRECISION,
          market_score DOUBLE PRECISION,
          rs_score DOUBLE PRECISION,
          opportunity_score DOUBLE PRECISION,
          exit_reason TEXT,
          PRIMARY KEY(run_id,code,signal_date)
        )
        """
    },
    "strategy_experiments": {
        "cols": [
            "experiment_id","research_run_id","module","created_at","updated_at","status","cursor",
            "total","train_end","validation_end","test_revealed","config_json","rule_version","note"
        ],
        "keys": ["experiment_id"],
        "ts": "updated_at",
        "ddl": """
        CREATE TABLE IF NOT EXISTS strategy_experiments(
          experiment_id TEXT PRIMARY KEY,
          research_run_id TEXT NOT NULL,
          module TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          status TEXT NOT NULL,
          cursor INTEGER NOT NULL DEFAULT 0,
          total INTEGER NOT NULL DEFAULT 0,
          train_end TEXT NOT NULL,
          validation_end TEXT NOT NULL,
          test_revealed INTEGER NOT NULL DEFAULT 0,
          config_json TEXT NOT NULL,
          rule_version TEXT NOT NULL,
          note TEXT
        )
        """
    },
    "strategy_experiment_trades": {
        "cols": [
            "experiment_id","config_id","code","signal_date","entry_date","exit_date","r_multiple",
            "return_pct","holding_days","opportunity_score","initial_risk_pct"
        ],
        "keys": ["experiment_id","config_id","code","signal_date"],
        "ts": None,
        "ddl": """
        CREATE TABLE IF NOT EXISTS strategy_experiment_trades(
          experiment_id TEXT NOT NULL,
          config_id TEXT NOT NULL,
          code TEXT NOT NULL,
          signal_date TEXT NOT NULL,
          entry_date TEXT,
          exit_date TEXT,
          r_multiple DOUBLE PRECISION,
          return_pct DOUBLE PRECISION,
          holding_days INTEGER,
          opportunity_score DOUBLE PRECISION,
          initial_risk_pct DOUBLE PRECISION,
          PRIMARY KEY(experiment_id,config_id,code,signal_date)
        )
        """
    },
    "strategy_candidates": {
        "cols": [
            "candidate_id","experiment_id","created_at","module","config_id","config_json","status","note"
        ],
        "keys": ["candidate_id"],
        "ts": None,
        "ddl": """
        CREATE TABLE IF NOT EXISTS strategy_candidates(
          candidate_id TEXT PRIMARY KEY,
          experiment_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          module TEXT NOT NULL,
          config_id TEXT NOT NULL,
          config_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'candidate',
          note TEXT
        )
        """
    }
}

LIGHT_TABLES = [
    "positions","position_snapshots","forward_signals",
    "research_runs","strategy_experiments","strategy_candidates"
]
HEAVY_TABLES = [
    "research_members","research_membership","research_stock_results",
    "research_trades","strategy_experiment_trades"
]


def enabled():
    return bool(SHARED_DATABASE_URL and psycopg is not None)


def status():
    if not SHARED_DATABASE_URL:
        return {"enabled": False, "reason": "未配置 SHARED_DATABASE_URL"}
    if psycopg is None:
        return {"enabled": False, "reason": "未安装 psycopg"}
    try:
        with psycopg.connect(SHARED_DATABASE_URL, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"enabled": True, "reason": "PostgreSQL 已连接"}
    except Exception as e:
        return {"enabled": False, "reason": f"共享数据库连接失败：{e}"}


def init_schema():
    if not enabled():
        return False
    with psycopg.connect(SHARED_DATABASE_URL, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            for spec in TABLES.values():
                cur.execute(spec["ddl"])
        conn.commit()
    return True


def _where_clause(filter_sql):
    if not filter_sql:
        return ""
    return " WHERE " + filter_sql


def _sqlite_rows(local_db_path, table, filter_sql=None, params=()):
    spec = TABLES[table]
    cols = spec["cols"]
    conn = sqlite3.connect(local_db_path)
    conn.row_factory = sqlite3.Row
    sql = f'SELECT {",".join(cols)} FROM {table}' + _where_clause(filter_sql)
    rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
    conn.close()
    return rows


def push_table(local_db_path, table, filter_sql=None, params=()):
    if not enabled() or table not in TABLES:
        return 0
    spec = TABLES[table]
    rows = _sqlite_rows(local_db_path, table, filter_sql, params)
    if not rows:
        return 0

    cols = spec["cols"]
    keys = spec["keys"]
    ts = spec.get("ts")
    nonkeys = [c for c in cols if c not in keys]
    placeholders = ",".join(["%s"] * len(cols))
    conflict = ",".join(keys)
    update_sql = ",".join([f"{c}=EXCLUDED.{c}" for c in nonkeys])

    sql = (
        f'INSERT INTO {table} ({",".join(cols)}) VALUES ({placeholders}) '
        f'ON CONFLICT ({conflict}) DO UPDATE SET {update_sql}'
    )
    if ts:
        sql += (
            f" WHERE {table}.{ts} IS NULL "
            f"OR EXCLUDED.{ts} >= {table}.{ts}"
        )

    values = [tuple(row.get(c) for c in cols) for row in rows]
    with psycopg.connect(SHARED_DATABASE_URL, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, values)
        conn.commit()
    return len(values)


def _remote_rows(table, filter_sql=None, params=()):
    spec = TABLES[table]
    cols = spec["cols"]
    sql = f'SELECT {",".join(cols)} FROM {table}'
    if filter_sql:
        # Caller uses SQLite-style ? placeholders; translate only positional markers.
        sql += " WHERE " + filter_sql.replace("?", "%s")
    with psycopg.connect(SHARED_DATABASE_URL, connect_timeout=8, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]


def pull_table(local_db_path, table, filter_sql=None, params=()):
    if not enabled() or table not in TABLES:
        return 0
    spec = TABLES[table]
    rows = _remote_rows(table, filter_sql, params)
    if not rows:
        return 0

    cols = spec["cols"]
    keys = spec["keys"]
    ts = spec.get("ts")
    nonkeys = [c for c in cols if c not in keys]
    placeholders = ",".join(["?"] * len(cols))
    conflict = ",".join(keys)
    update_sql = ",".join([f"{c}=excluded.{c}" for c in nonkeys])
    upsert_sql = (
        f'INSERT INTO {table} ({",".join(cols)}) VALUES ({placeholders}) '
        f'ON CONFLICT ({conflict}) DO UPDATE SET {update_sql}'
    )

    conn = sqlite3.connect(local_db_path)
    written = 0
    try:
        for row in rows:
            if ts:
                key_where = " AND ".join([f"{k}=?" for k in keys])
                local = conn.execute(
                    f"SELECT {ts} FROM {table} WHERE {key_where}",
                    tuple(row[k] for k in keys)
                ).fetchone()
                if local and local[0] and row.get(ts):
                    if str(local[0]) > str(row[ts]):
                        continue
            conn.execute(upsert_sql, tuple(row.get(c) for c in cols))
            written += 1
        conn.commit()
    finally:
        conn.close()
    return written


def sync_tables(local_db_path, tables=None, mode="both", filters=None):
    if not enabled():
        return {"enabled": False, "pushed": 0, "pulled": 0}
    init_schema()
    tables = tables or LIGHT_TABLES
    filters = filters or {}
    pushed = 0
    pulled = 0
    errors = []
    for table in tables:
        try:
            f = filters.get(table) or (None, ())
            filter_sql, params = f
            if mode in ("push","both"):
                pushed += push_table(local_db_path, table, filter_sql, params)
            if mode in ("pull","both"):
                pulled += pull_table(local_db_path, table, filter_sql, params)
        except Exception as e:
            errors.append(f"{table}: {e}")
    return {
        "enabled": True,
        "pushed": pushed,
        "pulled": pulled,
        "errors": errors
    }


def sync_light(local_db_path):
    return sync_tables(local_db_path, LIGHT_TABLES, mode="both")


def sync_research_run(local_db_path, run_id, mode="both"):
    tables = [
        "research_runs","research_members","research_membership",
        "research_stock_results","research_trades"
    ]
    filters = {
        t: ("run_id=?", (run_id,))
        for t in tables
    }
    return sync_tables(local_db_path, tables, mode=mode, filters=filters)


def sync_experiment(local_db_path, experiment_id, research_run_id=None, mode="both"):
    tables = ["strategy_experiments","strategy_experiment_trades","strategy_candidates"]
    filters = {
        "strategy_experiments": ("experiment_id=?", (experiment_id,)),
        "strategy_experiment_trades": ("experiment_id=?", (experiment_id,)),
        "strategy_candidates": ("experiment_id=?", (experiment_id,))
    }
    out = sync_tables(local_db_path, tables, mode=mode, filters=filters)
    if research_run_id:
        r = sync_research_run(local_db_path, research_run_id, mode=mode)
        out["pushed"] += r.get("pushed",0)
        out["pulled"] += r.get("pulled",0)
        out.setdefault("errors",[]).extend(r.get("errors",[]))
    return out
