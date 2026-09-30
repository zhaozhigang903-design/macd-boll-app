import base64
import html
import hashlib
import json
import os
import re
import sqlite3
import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import baostock as bs
import akshare as ak
from openai import OpenAI
from ifind_http import (
    configured as ifind_configured,
    status as ifind_status,
    history_one as ifind_history_one,
    history_many as ifind_history_many,
    basic_names as ifind_basic_names,
)
from shared_store import (
    enabled as shared_db_enabled,
    status as shared_db_status,
    sync_light as shared_sync_light,
    sync_research_run as shared_sync_research_run,
    sync_experiment as shared_sync_experiment,
)
from cos_backup import (
    configured as cos_backup_configured,
    status as cos_backup_status,
    backup_now as cos_backup_now,
    list_backups as cos_list_backups,
    restore_core as cos_restore_core,
    maybe_daily_backup as cos_maybe_daily_backup,
)

APP_DIR = Path(__file__).resolve().parent
RUNTIME_MODE = os.getenv(
    "MACD_RUNTIME_MODE",
    "windows" if os.name=="nt" else ("cloud" if os.getenv("RENDER") else "local")
).strip().lower()

if os.name=="nt":
    _default_data_dir = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "MACD-BOLL"
else:
    _default_data_dir = APP_DIR
DATA_DIR = Path(os.getenv("MACD_DATA_DIR", str(_default_data_dir))).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("MACD_LOCAL_DB_PATH", str(DATA_DIR / "analysis_history.db"))).expanduser()

RULE_VERSION = "EV1.1-WEEKLY-NATIVE-2026-09-30"
_SCREENER_THREADS = {}
_SCREENER_THREADS_LOCK = threading.Lock()
_BAOSTOCK_SESSION_LOCK = threading.RLock()
_BAOSTOCK_SESSION_OWNER = threading.local()
_ANALYSIS_EV_THREADS = {}
_ANALYSIS_EV_LOCK = threading.Lock()

st.set_page_config(
    page_title="中长线技术决策引擎",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
:root{
 --blue:#2563eb;
 --blue2:#0ea5e9;
 --violet:#7c3aed;
 --teal:#0f766e;
 --green:#16a34a;
 --amber:#d97706;
 --red:#dc2626;
 --panel:rgba(59,130,246,.055);
 --border:rgba(148,163,184,.26);
 --muted:rgba(148,163,184,.82);
}
.block-container{
 max-width:1080px;
 padding-top:calc(env(safe-area-inset-top, 0px) + 3.4rem);
 padding-bottom:4rem;
 padding-left:.7rem;
 padding-right:.7rem
}
h1{font-size:1.58rem!important;margin-bottom:.2rem!important}
h2,h3{
 font-weight:760!important;
 letter-spacing:.01em;
}
h2{
 font-size:1.22rem!important;
 border-left:4px solid var(--blue);
 padding-left:.55rem!important;
 margin-top:.65rem!important;
}
h3{
 font-size:1.03rem!important;
 color:var(--blue2)!important;
}
div[data-testid="stMetric"]{
 border:1px solid var(--border);
 border-radius:13px;
 padding:9px 10px;
 background:rgba(59,130,246,.035);
 box-shadow:0 2px 10px rgba(15,23,42,.04)
}
div[data-testid="stMetricLabel"]{opacity:.68}
div[data-testid="stMetricValue"]{font-weight:760}

/* 顶部菜单：当前页高亮，其他页弱化 */
div[data-testid="stTabs"] button[role="tab"]{
 border-radius:10px 10px 0 0!important;
 padding:.5rem .65rem!important;
 font-weight:650!important;
 opacity:.72;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"]{
 color:#fff!important;
 background:linear-gradient(135deg,var(--blue),var(--blue2))!important;
 opacity:1;
}
div[data-testid="stTabs"] div[data-baseweb="tab-highlight"]{
 background-color:transparent!important;
}

/* 输入区更有层次 */
div[data-testid="stFileUploader"], div[data-testid="stTextInput"],
div[data-testid="stSelectbox"], div[data-testid="stTextArea"]{
 border-radius:12px;
}
div[data-testid="stExpander"]{
 border:1px solid var(--border)!important;
 border-radius:13px!important;
 overflow:hidden;
}
.stButton>button[kind="primary"]{
 border:none!important;
 background:linear-gradient(135deg,var(--blue),var(--blue2))!important;
 color:white!important;
 font-weight:760!important;
 box-shadow:0 5px 16px rgba(37,99,235,.22)!important;
}
.stButton>button:not([kind="primary"]){
 border-color:var(--border)!important;
}

/* 驾驶舱 */
.cockpit{
 border:1px solid rgba(37,99,235,.25);
 border-radius:18px;
 padding:14px;
 margin:4px 0 14px;
 background:
  linear-gradient(135deg,rgba(37,99,235,.10),rgba(14,165,233,.035) 48%,rgba(124,58,237,.035));
 box-shadow:0 8px 26px rgba(15,23,42,.07)
}
.cockpit-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.cockpit-kicker{font-size:.76rem;color:var(--blue2);font-weight:650;margin-bottom:4px}
.symbol-highlight{font-size:1.34rem;font-weight:850;line-height:1.15;color:var(--blue2);margin:1px 0 3px}
.symbol-code{font-size:.78rem;opacity:.68;margin-bottom:5px}
.cockpit-state{font-size:1.33rem;font-weight:800;line-height:1.18}
.cockpit-stage{font-size:.92rem;opacity:.76;margin-top:5px}
.cockpit-score{
 min-width:70px;text-align:center;
 border:1px solid rgba(37,99,235,.28);
 background:rgba(37,99,235,.10);
 border-radius:14px;padding:8px 7px
}
.cockpit-score b{font-size:1.45rem;color:var(--blue2)}
.cockpit-score span{display:block;font-size:.70rem;opacity:.62}
.state-chip{
 display:inline-block;
 padding:4px 9px;
 border-radius:999px;
 font-size:.76rem;
 font-weight:800;
 margin-bottom:5px;
 border:1px solid transparent;
}
.state-buy{color:#86efac;background:rgba(22,163,74,.14);border-color:rgba(22,163,74,.32)}
.state-hold{color:#7dd3fc;background:rgba(14,165,233,.14);border-color:rgba(14,165,233,.30)}
.state-watch{color:#fde68a;background:rgba(217,119,6,.14);border-color:rgba(217,119,6,.30)}
.state-reduce,.state-avoid{color:#fca5a5;background:rgba(220,38,38,.14);border-color:rgba(220,38,38,.30)}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:11px}
.kpi{
 border:1px solid var(--border);
 border-radius:12px;padding:8px;text-align:center;
 background:rgba(15,23,42,.035)
}
.kpi b{display:block;font-size:1.02rem}
.kpi span{font-size:.70rem;opacity:.62}
.kpi-trend{border-top:3px solid var(--blue)}
.kpi-momentum{border-top:3px solid var(--violet)}
.kpi-weekly{border-top:3px solid var(--teal)}
.kpi-volume{border-top:3px solid var(--amber)}
.cockpit-note{
 margin-top:10px;padding:10px 11px;border-radius:11px;
 background:rgba(37,99,235,.07);
 border-left:3px solid var(--blue2);
 font-size:.90rem;line-height:1.48
}
.level-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:8px}
.level{
 border:1px solid var(--border);
 border-radius:11px;padding:8px 10px;font-size:.84rem;
 background:rgba(15,23,42,.025)
}
.level span{display:block;font-size:.68rem;opacity:.62;margin-bottom:2px}
.level-support{border-left:3px solid var(--green)}
.level-resist{border-left:3px solid var(--red)}
.trigger-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:8px}
.trigger{border-radius:11px;padding:8px 10px;font-size:.82rem;line-height:1.35}
.trigger-up{
 border:1px solid rgba(22,163,74,.28);
 background:rgba(22,163,74,.07)
}
.trigger-down{
 border:1px solid rgba(220,38,38,.28);
 background:rgba(220,38,38,.07)
}
.compactline{font-size:.92rem;line-height:1.45;margin:.3rem 0}

@media(max-width:700px){
 .block-container{
   padding-left:.5rem;
   padding-right:.5rem;
   padding-top:calc(env(safe-area-inset-top, 0px) + 3.7rem)
 }
 h1{font-size:1.38rem!important}
 h2{font-size:1.10rem!important}
 .stTextInput input,.stTextArea textarea{font-size:16px!important}
 button[kind="primary"]{min-height:50px;font-size:1.03rem}
 div[data-testid="stMetric"]{padding:7px 8px}
 div[data-testid="stTabs"] button[role="tab"]{padding:.42rem .46rem!important;font-size:.86rem!important}
 .cockpit{padding:11px}
 .cockpit-state{font-size:1.16rem}
 .cockpit-score{min-width:61px;padding:7px 5px}
 .kpi-grid{grid-template-columns:repeat(4,1fr);gap:5px}
 .kpi{padding:6px 3px}
 .kpi b{font-size:.92rem}
 .kpi span{font-size:.64rem}
 .level,.trigger{padding:7px 8px;font-size:.78rem}
}
</style>
""", unsafe_allow_html=True)

HOLDINGS_SCREENSHOT_PROMPT = """
你是一个严谨的A股/港股持仓列表读取器。请从用户上传的券商/行情App持仓截图中提取持仓，不要猜测看不清的数据。

只输出合法JSON：
{
  "positions":[
    {
      "symbol":"股票代码；A股6位，港股5位；若可见则填写，否则空字符串",
      "name":"股票名称，若可见则填写；否则空字符串",
      "entry_price": null,
      "shares": null,
      "entry_date":"",
      "initial_stop": null,
      "note":""
    }
  ],
  "unclear":""
}

规则：
- entry_price 只填截图明确显示的“成本价/持仓成本/买入均价”，不要把现价误当成本价。
- shares 只填明确显示的“持仓数量/持股数/可用数量”中的持仓数量；若不确定填null。
- 截图通常不显示买入日期和技术失效价，没显示就留空/null，禁止猜测。
- 若一张图有多只股票，逐只输出。
- 同一股票若在多张图重复出现，只保留一条，优先采用信息更完整的一条。
- 不要输出现金、基金、债券、美股；这里处理沪深A股和港股。
- 看不清就留空/null，不要编造。
"""

def extract_holdings_from_images(files):
    api_key = os.getenv("DEEPSEEK_API_KEY","").strip()
    if not api_key:
        raise RuntimeError("服务器未配置持仓截图识别接口。")
    if not files:
        return pd.DataFrame()

    content = [{"type":"text","text":HOLDINGS_SCREENSHOT_PROMPT}]
    for f in files:
        blob = f.getvalue()
        mime = getattr(f,"type",None) or "image/png"
        content.append({
            "type":"image_url",
            "image_url":{"url":data_url_bytes(blob,mime)}
        })

    client = OpenAI(api_key=api_key,base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model="deepseek-flash",
        messages=[{"role":"user","content":content}],
        response_format={"type":"json_object"},
        temperature=0
    )
    raw = resp.choices[0].message.content
    obj = parse_json(raw)
    if not obj or not isinstance(obj.get("positions"),list):
        raise RuntimeError("持仓截图识别结果格式异常。")

    rows = []
    seen = set()
    for x in obj["positions"]:
        symbol = str(x.get("symbol") or "").strip()
        name = str(x.get("name") or "").strip()
        if symbol.isdigit() and 1 <= len(symbol) <= 5:
            symbol = symbol.zfill(5)
        key = symbol or name
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append({
            "删除":False,
            "代码或名称":symbol or name,
            "名称":name,
            "买入均价":x.get("entry_price"),
            "持股数量":x.get("shares"),
            "买入日期":x.get("entry_date") or "",
            "技术失效价":x.get("initial_stop"),
            "备注":x.get("note") or ""
        })
    return pd.DataFrame(rows)

BATCH_SYMBOL_SCREENSHOT_PROMPT = """
你是一个严谨的A股/港股股票列表读取器。用户会上传自选股、持仓、行情列表、选股结果等截图。
你的任务只提取截图中明确出现的股票代码和股票名称，不做技术分析，不猜测看不清的数据。

只输出合法JSON：
{
  "stocks":[
    {
      "symbol":"A股6位代码或港股5位代码；明确可见才填写，否则空字符串",
      "name":"股票名称；明确可见才填写，否则空字符串",
      "market":"A股或港股；不确定留空"
    }
  ],
  "unclear":"无法确认的内容简述"
}

规则：
- 同一股票在多张截图重复出现，只保留一条。
- A股代码保留6位；港股代码统一补足5位，例如0700输出00700。
- 不要输出指数、现金、基金、债券、美股。
- 如果只有名称没有代码，也可以保留名称，后续系统会用名称解析。
- 如果只有代码没有名称，也可以保留代码。
- 看不清就留空，不要编造。
"""

def extract_batch_symbols_from_images(files):
    api_key=os.getenv("DEEPSEEK_API_KEY","").strip()
    if not api_key:
        raise RuntimeError("服务器未配置截图识别接口。")
    if not files:
        return pd.DataFrame(columns=["分析","代码或名称","名称","市场"])

    content=[{"type":"text","text":BATCH_SYMBOL_SCREENSHOT_PROMPT}]
    for f in files:
        blob=f.getvalue()
        mime=getattr(f,"type",None) or "image/png"
        content.append({
            "type":"image_url",
            "image_url":{"url":data_url_bytes(blob,mime)}
        })

    client=OpenAI(api_key=api_key,base_url="https://api.deepseek.com")
    resp=client.chat.completions.create(
        model="deepseek-flash",
        messages=[{"role":"user","content":content}],
        response_format={"type":"json_object"},
        temperature=0
    )
    obj=parse_json(resp.choices[0].message.content)
    if not obj or not isinstance(obj.get("stocks"),list):
        raise RuntimeError("截图股票识别结果格式异常。")

    rows=[]
    seen=set()
    for x in obj["stocks"]:
        symbol=str(x.get("symbol") or "").strip()
        name=str(x.get("name") or "").strip()
        market=str(x.get("market") or "").strip()
        digits=re.sub(r"\D","",symbol)
        if market=="港股" and digits:
            symbol=digits.zfill(5)[-5:]
        elif market=="A股" and len(digits)==6:
            symbol=digits
        elif digits and 1<=len(digits)<=5:
            symbol=digits.zfill(5)[-5:]
        elif len(digits)==6:
            symbol=digits
        key=(symbol or name).upper()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append({
            "分析":True,
            "代码或名称":symbol or name,
            "名称":name,
            "市场":market
        })
    return pd.DataFrame(rows)

EXTRACT_PROMPT = """
你是一个严谨的股票/ETF技术图表读取器。任务不是自由发挥，而是从用户上传的日K/周K截图中提取可验证事实，并做简短技术解释。
核心体系：BOLL + MACD + 成交量；ATR仅在清晰可见时读取。
禁止猜测看不清的数字。看不清就写“未知”。

分析优先级：
1. BOLL中轨方向
2. 价格相对BOLL中轨的位置
3. MACD零轴位置
4. DIF方向
5. MACD柱体变化
6. 金叉/死叉所处区域
7. 成交量确认
8. 周线是否确认日线方向

定义：
- 零轴下金叉：优先视为反弹/修复，不等于趋势反转。
- 零轴上二次金叉+BOLL中轨向上：趋势延续质量高。
- 零轴附近粘合：交叉信号降级。
- 红柱缩短=多头动能减速，不等于立刻转空。
- 绿柱缩短=空头动能减速，不等于立刻转多。
- 背离是风险/机会提示，不单独构成交易确认。
- 盘中截图必须标记 is_intraday=true。
- 成交量只依据截图中的VOL柱与MA5/MA10判断；不要求MA20。
- “异常放量”只表示明显偏离近期均量，不能自动判定利多或利空，必须结合价格位置与趋势解释。
- 不要根据股票名称补充截图外行情。
- 同一张截图在相同规则下必须尽量给出相同的分类结果；只依据图中可见事实分类。
- 持仓、成本、历史评分、用户倾向不得影响BOLL/MACD/量能事实识别。

必须只输出合法 json，不要Markdown，不要额外文字。JSON格式：
{
  "symbol_name": "未知",
  "symbol_code": "未知",
  "data_quality": 0,
  "missing_or_unclear": "",
  "is_intraday": false,
  "daily": {
    "price": "未知",
    "boll_mid": "未知",
    "boll_upper": "未知",
    "boll_lower": "未知",
    "boll_mid_direction": "向上/走平/向下/未知",
    "price_vs_mid": "中轨上/中轨附近/中轨下/未知",
    "boll_band_state": "扩张/平稳/收敛/未知",
    "macd_zero_zone": "零轴上/零轴附近/零轴下/未知",
    "dif_direction": "向上/走平/向下/未知",
    "cross": "金叉/死叉/粘合/未知",
    "bar_momentum": "红柱放大/红柱缩短/绿柱缩短/绿柱放大/不明确/未知",
    "volume_state": "明显放量/温和放量/普通/缩量/异常放量/不可见/未知",
    "vol_vs_ma5": "高于MA5/接近MA5/低于MA5/不可见/未知",
    "vol_vs_ma10": "高于MA10/接近MA10/低于MA10/不可见/未知",
    "volume_trend": "递增/递减/震荡/不明确/未知",
    "divergence": "顶背离/底背离/无明显背离/无法判断",
    "atr": "未知"
  },
  "weekly": {
    "available": false,
    "boll_mid_direction": "未知",
    "price_vs_mid": "未知",
    "macd_zero_zone": "未知",
    "dif_direction": "未知",
    "cross": "未知",
    "bar_momentum": "未知",
    "volume_state": "未知",
    "vol_vs_ma5": "未知",
    "vol_vs_ma10": "未知",
    "volume_trend": "未知"
  },
  "key_support": "未知",
  "key_resistance": "未知",
  "essence": "",
  "boll_analysis": "",
  "macd_analysis": "",
  "weekly_analysis": "",
  "resonance": "",
  "comparison_hint": ""
}
要求：
- symbol_name / symbol_code：若截图顶部清晰显示股票名称或代码则读取；看不清写“未知”，禁止猜测。
- data_quality 是0-100整数，衡量截图是否足够清晰、周期/指标是否可判断。
- 输出必须适合手机阅读：essence不超过60个汉字，其余解释字段尽量不超过45个汉字。
- 宁可写未知，也不要编造。
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS analyses(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      symbol TEXT,
      market TEXT,
      horizon TEXT,
      position_state TEXT,
      rating TEXT,
      state TEXT,
      stage TEXT,
      score REAL,
      trend_score REAL,
      momentum_score REAL,
      weekly_score REAL,
      confirm_score REAL,
      confidence INTEGER,
      price TEXT,
      boll_mid TEXT,
      key_support TEXT,
      key_resistance TEXT,
      model_mode TEXT,
      weekly_used INTEGER,
      raw_result TEXT
    )
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(analyses)").fetchall()}
    required = {
        "horizon":"TEXT", "position_state":"TEXT", "score":"REAL", "trend_score":"REAL",
        "momentum_score":"REAL", "weekly_score":"REAL", "confirm_score":"REAL",
        "data_quality":"INTEGER", "key_support":"TEXT", "key_resistance":"TEXT",
        "model_mode":"TEXT", "weekly_used":"INTEGER"
    }
    for name, typ in required.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE analyses ADD COLUMN {name} {typ}")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS extraction_cache(
      signature TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      payload TEXT NOT NULL,
      raw_result TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS market_daily_cache(
      code TEXT NOT NULL,
      trade_date TEXT NOT NULL,
      open REAL,
      high REAL,
      low REAL,
      close REAL,
      vol REAL,
      amount REAL,
      pctChg REAL,
      turn REAL,
      tradestatus TEXT,
      isST TEXT,
      adjustflag TEXT NOT NULL DEFAULT '2',
      fetched_at TEXT NOT NULL,
      PRIMARY KEY(code, trade_date, adjustflag)
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_market_daily_cache_code_date
    ON market_daily_cache(code, trade_date)
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS market_cache_meta(
      code TEXT PRIMARY KEY,
      last_checked TEXT,
      updated_at TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS positions(
      code TEXT PRIMARY KEY,
      name TEXT,
      entry_date TEXT NOT NULL,
      entry_price REAL NOT NULL,
      shares REAL NOT NULL DEFAULT 0,
      initial_stop REAL,
      entry_score REAL,
      peak_score REAL,
      last_score REAL,
      last_price REAL,
      last_market_score REAL,
      last_action TEXT,
      note TEXT,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS position_snapshots(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL,
      snapshot_date TEXT NOT NULL,
      price REAL,
      technical_score REAL,
      trend_score REAL,
      momentum_score REAL,
      weekly_score REAL,
      confirm_score REAL,
      market_score REAL,
      pnl_pct REAL,
      action TEXT,
      reason TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(code, snapshot_date)
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_position_snapshots_code_date
    ON position_snapshots(code, snapshot_date)
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS forward_signals(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL,
      name TEXT,
      market TEXT,
      signal_date TEXT NOT NULL,
      price REAL,
      tier TEXT,
      technical_score REAL,
      buy_score REAL,
      weekly_score REAL,
      rr REAL,
      market_score REAL,
      rs_score REAL,
      ev_r REAL,
      ev_lcb_r REAL,
      stress_ev_r REAL,
      ev_samples INTEGER,
      risk_price REAL,
      rule_version TEXT,
      status TEXT NOT NULL DEFAULT 'tracking',
      realized_r REAL,
      exit_date TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(code, signal_date)
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_forward_signals_status_date
    ON forward_signals(status, signal_date)
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ev_cache(
      code TEXT NOT NULL,
      stock_date TEXT NOT NULL,
      benchmark_date TEXT NOT NULL,
      rule_version TEXT NOT NULL,
      payload TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(code,stock_date,benchmark_date,rule_version)
    )
    """)
    conn.execute("""
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
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS research_members(
      run_id TEXT NOT NULL,
      seq INTEGER NOT NULL,
      code TEXT NOT NULL,
      name TEXT,
      market TEXT,
      PRIMARY KEY(run_id,seq)
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_research_members_run_code
    ON research_members(run_id,code)
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS research_membership(
      run_id TEXT NOT NULL,
      period_start TEXT NOT NULL,
      period_end TEXT NOT NULL,
      code TEXT NOT NULL,
      name TEXT,
      market TEXT,
      PRIMARY KEY(run_id,period_start,code)
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_research_membership_run_code_date
    ON research_membership(run_id,code,period_start,period_end)
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS research_stock_results(
      run_id TEXT NOT NULL,
      code TEXT NOT NULL,
      name TEXT,
      market TEXT,
      trade_count INTEGER,
      ev_r REAL,
      conservative_ev_r REAL,
      win_rate REAL,
      avg_win_r REAL,
      avg_loss_r REAL,
      profit_factor REAL,
      oos_ev_r REAL,
      oos_stability TEXT,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(run_id,code)
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS research_trades(
      run_id TEXT NOT NULL,
      code TEXT NOT NULL,
      name TEXT,
      market TEXT,
      signal_date TEXT,
      entry_date TEXT,
      exit_date TEXT,
      return_pct REAL,
      r_multiple REAL,
      entry_price REAL,
      exit_price REAL,
      stop_price REAL,
      initial_risk_pct REAL,
      holding_days INTEGER,
      technical_score REAL,
      buy_score REAL,
      weekly_score REAL,
      rr REAL,
      market_score REAL,
      rs_score REAL,
      opportunity_score REAL,
      exit_reason TEXT
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_research_trades_run_date
    ON research_trades(run_id,signal_date)
    """)
    conn.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_research_trades_unique
    ON research_trades(run_id,code,signal_date)
    """)
    rtcols={r[1] for r in conn.execute("PRAGMA table_info(research_trades)").fetchall()}
    for cname,ctype in {
        "entry_price":"REAL","exit_price":"REAL","stop_price":"REAL","initial_risk_pct":"REAL"
    }.items():
        if cname not in rtcols:
            conn.execute(f"ALTER TABLE research_trades ADD COLUMN {cname} {ctype}")
    conn.execute("""
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
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS strategy_experiment_trades(
      experiment_id TEXT NOT NULL,
      config_id TEXT NOT NULL,
      code TEXT NOT NULL,
      signal_date TEXT NOT NULL,
      entry_date TEXT,
      exit_date TEXT,
      r_multiple REAL,
      return_pct REAL,
      holding_days INTEGER,
      opportunity_score REAL,
      initial_risk_pct REAL,
      PRIMARY KEY(experiment_id,config_id,code,signal_date)
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_strategy_experiment_trades_exp_cfg_date
    ON strategy_experiment_trades(experiment_id,config_id,signal_date)
    """)
    conn.execute("""
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
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS screener_jobs(
      job_id TEXT PRIMARY KEY,
      job_type TEXT NOT NULL DEFAULT 'manual',
      trade_date TEXT NOT NULL,
      universe TEXT NOT NULL,
      exclude_st INTEGER NOT NULL DEFAULT 1,
      batch_size INTEGER NOT NULL DEFAULT 100,
      status TEXT NOT NULL,
      cursor INTEGER NOT NULL DEFAULT 0,
      total INTEGER NOT NULL DEFAULT 0,
      market_score REAL,
      market_regime TEXT,
      benchmark_name TEXT,
      error TEXT,
      stats_json TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_screener_jobs_trade_date
    ON screener_jobs(trade_date,universe,status)
    """)
    sjcols={r[1] for r in conn.execute("PRAGMA table_info(screener_jobs)").fetchall()}
    if "job_type" not in sjcols:
        conn.execute("ALTER TABLE screener_jobs ADD COLUMN job_type TEXT NOT NULL DEFAULT 'manual'")
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_screener_jobs_type_status
    ON screener_jobs(job_type,status,created_at)
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS screener_job_results(
      job_id TEXT NOT NULL,
      code TEXT NOT NULL,
      payload TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(job_id,code)
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS screener_settings(
      id INTEGER PRIMARY KEY CHECK(id=1),
      auto_daily INTEGER NOT NULL DEFAULT 1,
      universe TEXT NOT NULL DEFAULT '中证500',
      exclude_st INTEGER NOT NULL DEFAULT 1,
      batch_size INTEGER NOT NULL DEFAULT 100,
      run_after_hour INTEGER NOT NULL DEFAULT 18,
      updated_at TEXT NOT NULL
    )
    """)
    conn.execute(
        """INSERT OR IGNORE INTO screener_settings(
           id,auto_daily,universe,exclude_st,batch_size,run_after_hour,updated_at
        ) VALUES(1,1,'中证500',1,100,18,?)""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
    )
    fcols={r[1] for r in conn.execute("PRAGMA table_info(forward_signals)").fetchall()}
    if "rule_version" not in fcols:
        conn.execute("ALTER TABLE forward_signals ADD COLUMN rule_version TEXT")
    conn.commit()
    conn.close()

def data_url_bytes(blob, mime="image/png"):
    return f"data:{mime};base64,{base64.b64encode(blob).decode('utf-8')}"

def reset_uploads():
    for k in [
        "daily_bytes","daily_mime","daily_name",
        "weekly_bytes","weekly_mime","weekly_name"
    ]:
        st.session_state.pop(k, None)
    st.session_state["upload_nonce"] = st.session_state.get("upload_nonce", 0) + 1

def image_signature(daily_bytes, weekly_bytes=None):
    h = hashlib.sha256()
    h.update(b"TECH_EXTRACT_V3|")
    h.update(daily_bytes or b"")
    h.update(b"|WEEKLY|")
    h.update(weekly_bytes or b"")
    return h.hexdigest()

def get_cached_extraction(signature):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT payload, raw_result FROM extraction_cache WHERE signature=?",
        (signature,)
    ).fetchone()
    conn.close()
    if not row:
        return None, None
    try:
        return json.loads(row[0]), row[1]
    except Exception:
        return None, None

def save_cached_extraction(signature, payload, raw_result):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT OR REPLACE INTO extraction_cache(signature,created_at,payload,raw_result)
           VALUES(?,?,?,?)""",
        (
            signature,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(payload, ensure_ascii=False, separators=(",",":")),
            raw_result
        )
    )
    conn.commit()
    conn.close()

def parse_json(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    return None

def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def cat(v):
    return str(v or "").strip()

def score_engine(x, weekly_uploaded):
    d = x.get("daily", {}) or {}
    w = x.get("weekly", {}) or {}

    # 1) 日线趋势 0-100
    trend = 0
    trend += {"向上":45, "走平":24, "向下":5}.get(cat(d.get("boll_mid_direction")), 15)
    trend += {"中轨上":35, "中轨附近":20, "中轨下":4}.get(cat(d.get("price_vs_mid")), 12)
    trend += {"扩张":20, "平稳":13, "收敛":8}.get(cat(d.get("boll_band_state")), 10)
    trend = clamp(trend)

    # 2) 日线动能 0-100
    momentum = 0
    momentum += {"零轴上":35, "零轴附近":21, "零轴下":5}.get(cat(d.get("macd_zero_zone")), 14)
    momentum += {"向上":25, "走平":13, "向下":3}.get(cat(d.get("dif_direction")), 10)
    momentum += {"金叉":17, "粘合":9, "死叉":2}.get(cat(d.get("cross")), 7)
    momentum += {
        "红柱放大":23, "红柱缩短":15, "绿柱缩短":12,
        "绿柱放大":1, "不明确":8
    }.get(cat(d.get("bar_momentum")), 7)
    momentum = clamp(momentum)

    # 3) 周线过滤器 0-100
    weekly = None
    if weekly_uploaded and bool(w.get("available")):
        weekly = 0
        weekly += {"向上":40, "走平":22, "向下":4}.get(cat(w.get("boll_mid_direction")), 12)
        weekly += {"中轨上":30, "中轨附近":18, "中轨下":3}.get(cat(w.get("price_vs_mid")), 10)
        weekly += {"零轴上":20, "零轴附近":12, "零轴下":2}.get(cat(w.get("macd_zero_zone")), 7)
        weekly += {"向上":10, "走平":5, "向下":1}.get(cat(w.get("dif_direction")), 4)
        weekly = clamp(weekly)

    # 4) 确认因子 0-100：成交量用 MA5/MA10 + 柱体趋势，不依赖 MA20
    confirm = 45
    vol = cat(d.get("volume_state"))
    if vol == "明显放量":
        confirm += 14
    elif vol == "温和放量":
        confirm += 9
    elif vol == "普通":
        confirm += 3
    elif vol == "缩量":
        confirm -= 6
    elif vol == "异常放量":
        # 异常量本身不是方向信号，留给价格位置/趋势解释
        confirm += 0

    v5 = cat(d.get("vol_vs_ma5"))
    v10 = cat(d.get("vol_vs_ma10"))
    if v5 == "高于MA5" and v10 == "高于MA10":
        confirm += 12
    elif v5 == "低于MA5" and v10 == "低于MA10":
        confirm -= 8
    elif "高于" in v5 or "高于" in v10:
        confirm += 5

    vtrend = cat(d.get("volume_trend"))
    if vtrend == "递增":
        confirm += 7
    elif vtrend == "递减":
        confirm -= 4

    div = cat(d.get("divergence"))
    if div == "底背离":
        confirm += 15
    elif div == "顶背离":
        confirm -= 22
    elif div == "无明显背离":
        confirm += 4
    confirm = clamp(confirm)

    if weekly is None:
        overall = 0.50*trend + 0.35*momentum + 0.15*confirm
    else:
        overall = 0.38*trend + 0.30*momentum + 0.22*weekly + 0.10*confirm

    # 硬性弱势组合额外惩罚，避免均值掩盖风险
    hard_bear = (
        cat(d.get("boll_mid_direction")) == "向下"
        and cat(d.get("price_vs_mid")) == "中轨下"
        and cat(d.get("macd_zero_zone")) == "零轴下"
        and cat(d.get("cross")) == "死叉"
    )
    if hard_bear:
        overall = min(overall, 34)

    # 明显强势组合加分但封顶
    strong_bull = (
        cat(d.get("boll_mid_direction")) == "向上"
        and cat(d.get("price_vs_mid")) == "中轨上"
        and cat(d.get("macd_zero_zone")) == "零轴上"
        and cat(d.get("dif_direction")) == "向上"
    )
    if strong_bull:
        overall = min(100, overall + 5)

    return round(overall,1), round(trend,1), round(momentum,1), (round(weekly,1) if weekly is not None else None), round(confirm,1), hard_bear, strong_bull

def grade(score, weekly_ok, quality):
    if quality < 65:
        return "N/A"
    if score >= 86 and weekly_ok:
        return "S"
    if score >= 78:
        return "A+"
    if score >= 70:
        return "A"
    if score >= 62:
        return "B+"
    if score >= 50:
        return "B"
    if score >= 40:
        return "C+"
    return "C"

def stage_from(score, d, weekly_ok):
    if score >= 86 and weekly_ok:
        return "主升/强趋势延续"
    if score >= 70:
        return "趋势确认/转强"
    if score >= 55:
        return "修复/中轨争夺"
    if score >= 40:
        return "弱势震荡/等待确认"
    return "空头趋势/防守"

def state_from(score, rating, quality, intraday, weekly_ok, position_state, fundamentals_ok, hard_bear):
    holding = position_state != "未持有"
    if quality < 65:
        return "观察", "截图质量不足，先复核数据"
    if hard_bear or score < 35:
        return ("减仓" if holding else "回避"), "趋势与动能处于明显弱势"
    if holding and score < 48:
        return "减仓", "中长线结构转弱，优先控制风险"
    if score >= 78 and weekly_ok and not intraday:
        if fundamentals_ok:
            return "买入候选", "技术面进入高质量候选区"
        return "观察", "技术面较强，但中长线仍需基本面/估值独立验证"
    if holding and score >= 58:
        return "持有", "趋势尚未破坏，等待升级或降级条件"
    return "观察", "证据尚不足，等待关键确认"

def confidence_from(x, weekly_uploaded):
    q = int(x.get("data_quality", 0) or 0)
    if bool(x.get("is_intraday")):
        q -= 10
    if not weekly_uploaded:
        q -= 8
    if cat((x.get("daily") or {}).get("boll_mid_direction")) == "未知":
        q -= 12
    if cat((x.get("daily") or {}).get("macd_zero_zone")) == "未知":
        q -= 12
    return int(clamp(q))

def signal_color(score):
    if score >= 78: return "🟢"
    if score >= 60: return "🔵"
    if score >= 45: return "🟡"
    return "🔴"

def previous(symbol):
    if not symbol:
        return None
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM analyses WHERE symbol=? ORDER BY id DESC LIMIT 1",
        conn, params=(symbol,)
    )
    conn.close()
    return None if df.empty else df.iloc[0].to_dict()

def save_result(meta, x, metrics, raw):
    score, trend, momentum, weekly, confirm, _, _ = metrics
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analyses(
      created_at,symbol,market,horizon,position_state,rating,state,stage,
      score,trend_score,momentum_score,weekly_score,confirm_score,confidence,
      price,boll_mid,data_quality,key_support,key_resistance,model_mode,weekly_used,raw_result
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      meta["symbol"], meta["market"], meta["horizon"], meta["position_state"],
      meta["rating"], meta["state"], meta["stage"], score, trend, momentum,
      weekly, confirm, meta["confidence"],
      str((x.get("daily") or {}).get("price","未知")),
      str((x.get("daily") or {}).get("boll_mid","未知")),
      int(x.get("data_quality",0) or 0),
      x.get("key_support","未知"), x.get("key_resistance","未知"),
      meta["mode"], 1 if meta["weekly_used"] else 0, raw
    ))
    conn.commit()
    conn.close()

def _safe(v):
    return html.escape(str(v if v not in (None, "") else "—"))

def render_cockpit(report):
    if not report:
        st.info("暂无分析结果。输入A股或港股代码/名称后生成决策，结果会固定显示在这里。")
        return

    score = report.get("score", 0)
    weekly = report.get("weekly_score")
    weekly_txt = "—" if weekly is None else f"{weekly:.0f}"
    symbol = report.get("symbol") or "当前标的"
    parts = [x.strip() for x in str(symbol).split("/",1)]
    symbol_name = parts[0] if parts else str(symbol)
    symbol_code = parts[1] if len(parts)>1 else ""
    updated = report.get("updated_at","")
    essence = report.get("essence") or report.get("state_reason","")
    delta = report.get("delta")
    compare_text = ""
    if delta is not None:
        arrow = "↑" if delta > 3 else ("↓" if delta < -3 else "→")
        compare_text = f" · 较上次 {arrow}{delta:+.1f}"

    state = str(report.get("state") or "")
    state_class = (
        "state-buy" if state == "买入候选"
        else "state-hold" if state == "持有"
        else "state-watch" if state == "观察"
        else "state-reduce" if state == "减仓"
        else "state-avoid"
    )

    st.markdown(
        f"""
<div class="cockpit">
  <div class="cockpit-head">
    <div>
      <div class="cockpit-kicker">最新决策 · {_safe(updated)}</div>
      <div class="symbol-highlight">{_safe(symbol_name)}</div>
      <div class="symbol-code">{_safe(symbol_code)}</div>
      <span class="state-chip {state_class}">{_safe(state)}</span>
      <div class="cockpit-state">{signal_color(score)} {_safe(report.get("rating"))} · {_safe(report.get("stage"))}</div>
      <div class="cockpit-stage">{_safe(compare_text) if compare_text else "当前结构"}</div>
    </div>
    <div class="cockpit-score"><b>{score:.0f}</b><span>技术分 /100</span></div>
  </div>
  <div class="kpi-grid">
    <div class="kpi kpi-trend"><b>{report.get("trend",0):.0f}/100</b><span>趋势分</span></div>
    <div class="kpi kpi-momentum"><b>{report.get("momentum",0):.0f}/100</b><span>动能分</span></div>
    <div class="kpi kpi-weekly"><b>{weekly_txt}{"" if weekly_txt=="—" else "/100"}</b><span>周线分</span></div>
    <div class="kpi kpi-volume"><b>{report.get("confirm",0):.0f}/100</b><span>量能分</span></div>
  </div>
  <div class="cockpit-note">{_safe(essence)}</div>
  <div class="level-grid">
    <div class="level level-support"><span>关键支撑</span><b>{_safe(report.get("support"))}</b></div>
    <div class="level level-resist"><span>关键压力</span><b>{_safe(report.get("resistance"))}</b></div>
  </div>
  <div class="trigger-grid">
    <div class="trigger trigger-up">⬆️ <b>升级</b><br>{_safe(report.get("upgrade"))}</div>
    <div class="trigger trigger-down">⬇️ <b>降级</b><br>{_safe(report.get("downgrade"))}</div>
  </div>
</div>
        """,
        unsafe_allow_html=True
    )

    if report.get("opportunity_score") is not None:
        st.markdown("**交易机会层**")
        o1,o2 = st.columns(2)
        o1.metric("机会分", f"{report.get('opportunity_score',0):.0f}/100", report.get("opportunity_label",""))
        o2.metric("买点分", f"{report.get('buy_score',0):.0f}/100")
        o3,o4 = st.columns(2)
        rr_v = report.get("rr")
        o3.metric("盈亏比", f"{rr_v:.2f}:1" if rr_v is not None and pd.notna(rr_v) else "—")
        o4.metric("大盘环境", f"{report.get('market_score',0):.0f}/100", report.get("market_regime",""))
        ex20 = report.get("excess20")
        ex60 = report.get("excess60")
        rs_line = f"相对强度 {report.get('rs_score',50):.0f}/100"
        if ex20 is not None and pd.notna(ex20):
            rs_line += f" · 20日超额 {ex20:.1%}"
        if ex60 is not None and pd.notna(ex60):
            rs_line += f" · 60日超额 {ex60:.1%}"
        st.caption(rs_line)
        ev = report.get("ev") or {}
        e1,e2,e3 = st.columns(3)
        evr = ev.get("EV_R")
        lcb = ev.get("保守EV_R")
        stress = ev.get("压力EV_R")
        e1.metric("历史净EV", f"{evr:+.2f}R" if pd.notna(evr) else "—")
        e2.metric("保守EV", f"{lcb:+.2f}R" if pd.notna(lcb) else "—")
        e3.metric("2倍成本EV", f"{stress:+.2f}R" if pd.notna(stress) else "—")
        win = ev.get("胜率")
        pf = ev.get("盈亏因子")
        pf_txt = f"{pf:.2f}" if pd.notna(pf) and np.isfinite(pf) else ("∞" if pf==np.inf else "—")
        wf = ev.get("walk_forward") or {}
        line = f"真实交易样本 {ev.get('样本',0)}"
        if pd.notna(win):
            line += f" · 胜率 {win:.0%}"
        line += f" · EV可信度 {ev.get('可信度','不足')} · 盈亏因子 {pf_txt}"
        st.caption(line)
        st.caption(
            f"OOS：{wf.get('稳定性','样本不足')} · "
            f"正EV折数 {wf.get('正EV折数',0)}/{wf.get('折数',0)}"
        )

    wcheck=report.get("weekly_crosscheck") or {}
    if report.get("weekly_source"):
        agg_score=report.get("weekly_aggregate_score")
        agg_txt=f"{agg_score:.0f}/100" if agg_score is not None and pd.notna(agg_score) else "—"
        level=str(wcheck.get("level","不可校验"))
        source=str(report.get("weekly_source","—"))
        if level=="高":
            st.success(f"周线数据：{source}为主 · 日K聚合 {agg_txt} · 一致性高")
        elif level=="中":
            st.info(f"周线数据：{source}为主 · 日K聚合 {agg_txt} · 一致性中")
        elif level=="低":
            st.warning(f"周线数据：{source}为主 · 日K聚合 {agg_txt} · 一致性低，注意数据口径分歧")
        else:
            st.caption(f"周线数据：{source}为主 · 聚合周K暂不可校验")

    op=report.get("operation_strategy") or {}
    if op:
        st.markdown("### 🎯 具体操作策略")
        oa,ob=st.columns([1,2])
        oa.metric("当前动作",op.get("action","—"))
        ob.info(op.get("position_plan",""))
        st.markdown(f"**买入/确认触发**：{op.get('entry_trigger','—')}")
        st.markdown(f"**加仓条件**：{op.get('add_trigger','—')}")
        st.markdown(f"**减仓条件**：{op.get('reduce_trigger','—')}")
        st.markdown(f"**退出条件**：{op.get('exit_trigger','—')}")
        oc,od=st.columns(2)
        oc.caption(f"风险位：{op.get('risk_line','—')}")
        od.caption(f"压力/目标观察区：{op.get('target_zone','—')}")
        st.caption("执行依据："+str(op.get("evidence","")))

    with st.expander("详细技术证据"):
        d = report.get("daily",{}) or {}
        rows = [
            ["中轨", d.get("boll_mid_direction","未知")],
            ["价格位置", d.get("price_vs_mid","未知")],
            ["MACD零轴", d.get("macd_zero_zone","未知")],
            ["DIF", d.get("dif_direction","未知")],
            ["交叉", d.get("cross","未知")],
            ["柱体", d.get("bar_momentum","未知")],
            ["成交量", d.get("volume_state","未知")],
            ["量能趋势", d.get("volume_trend","未知")],
            ["背离", d.get("divergence","未知")],
        ]
        st.dataframe(pd.DataFrame(rows, columns=["证据","状态"]), use_container_width=True, hide_index=True)
        if report.get("boll_analysis"):
            st.caption("BOLL：" + report.get("boll_analysis",""))
        if report.get("macd_analysis"):
            st.caption("MACD：" + report.get("macd_analysis",""))
        if report.get("weekly_analysis"):
            st.caption("周线：" + report.get("weekly_analysis",""))
        if report.get("resonance"):
            st.caption("共振：" + report.get("resonance",""))

    if report.get("data_source"):
        st.caption(
            f"数据源：{report.get('data_source')} · {report.get('adjustment','')} · "
            f"最新交易日：{report.get('latest_date','—')} · 收盘：{report.get('latest_close','—')}"
        )
    st.caption("总技术分 = 趋势38% + 动能30% + 周线22% + 量能10%；周线为中长线必选周期。各分项满分100。")
    st.caption(f"数据完整度 {report.get('confidence',0)}% · 同一代码使用同一数据源和公式；技术分不是上涨概率。")


def _rs_to_df(rs):
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)

def normalize_code(code):
    s = str(code or "").strip().lower()
    if not s:
        return ""
    if s.startswith(("sh.","sz.","hk.")):
        if s.startswith("hk."):
            raw = re.sub(r"\D","",s.split(".",1)[1])
            return "hk." + raw.zfill(5)[-5:]
        return s

    hk_hint = s.endswith(".hk") or s.startswith("hk") or "港股" in s
    digits = re.sub(r"\D","",s)
    if not digits:
        return s
    if hk_hint or (1 <= len(digits) <= 5):
        return "hk." + digits.zfill(5)[-5:]
    if len(digits) == 6:
        if digits.startswith(("5","6","9")):
            return "sh." + digits
        return "sz." + digits
    return s

def market_of_code(code):
    return "港股" if normalize_code(code).startswith("hk.") else "A股"

def benchmark_label_for_code(code):
    return "恒生指数" if market_of_code(code) == "港股" else "沪深300"

def data_source_for_code(code):
    if ifind_configured():
        return "iFinD→AKShare→BaoStock"
    return "AKShare" if market_of_code(code) == "港股" else "AKShare→BaoStock"

def extract_a_share_code(*values):
    for value in values:
        s = str(value or "")
        m = re.search(r"(?<!\d)(\d{6})(?!\d)", s)
        if m:
            code = m.group(1)
            if code.startswith(("0","3","6","8","4")):
                return code
    return ""

def display_code(code):
    s = str(code or "")
    return s.split(".")[-1].upper() if "." in s else s.upper()

def bs_login(retries=3,strict=False):
    # BaoStock会话不支持同一进程多线程并发。若上游把Render IP临时列入黑名单，
    # 默认不再让整个App失败，而是释放锁并交给AKShare容灾。
    depth=int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)
    if depth>0:
        _BAOSTOCK_SESSION_OWNER.depth=depth+1
        return True

    acquired=_BAOSTOCK_SESSION_LOCK.acquire(timeout=30)
    if not acquired:
        if strict:
            raise RuntimeError("BaoStock当前正被后台任务占用，请稍后重试。")
        return False

    last_msg=""
    try:
        for attempt in range(1,int(retries)+1):
            try:
                lg=bs.login()
                if getattr(lg,"error_code","-1")=="0":
                    _BAOSTOCK_SESSION_OWNER.depth=1
                    _BAOSTOCK_SESSION_OWNER.last_error=""
                    return True
                last_msg=str(getattr(lg,"error_msg","未知错误"))
            except Exception as ex:
                last_msg=str(ex)
            if attempt<int(retries):
                time.sleep(1.2*attempt)
        _BAOSTOCK_SESSION_OWNER.last_error=last_msg
        if strict:
            raise RuntimeError("BaoStock登录失败："+last_msg)
        _BAOSTOCK_SESSION_LOCK.release()
        return False
    except Exception:
        try:
            _BAOSTOCK_SESSION_LOCK.release()
        except Exception:
            pass
        raise

def bs_logout_safe():
    depth=int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)
    if depth<=0:
        return
    if depth>1:
        _BAOSTOCK_SESSION_OWNER.depth=depth-1
        return
    try:
        bs.logout()
    except Exception:
        pass
    finally:
        _BAOSTOCK_SESSION_OWNER.depth=0
        try:
            _BAOSTOCK_SESSION_LOCK.release()
        except Exception:
            pass

def _normalize_hk_name(v):
    s = str(v or "").strip()
    s = re.sub(r"\s+","",s)
    s = s.replace("－","-").replace("—","-")
    # 港股名称常见股份类别/第二上市后缀；匹配时忽略后缀，但展示仍保留原名
    s = re.sub(r"(?i)-(SW|S|W|R|B)$","",s)
    return s.upper()

def _hk_spot_to_universe(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["code","code_name","latest","amount"])
    code_col = "代码" if "代码" in df.columns else None
    name_col = (
        "名称" if "名称" in df.columns
        else ("中文名称" if "中文名称" in df.columns else None)
    )
    if code_col is None or name_col is None:
        return pd.DataFrame(columns=["code","code_name","latest","amount"])

    raw_code = df[code_col].astype(str).str.extract(r"(\d+)")[0].fillna("")
    out = pd.DataFrame(index=df.index)
    out["code"] = "hk." + raw_code.str.zfill(5).str[-5:]
    out["code_name"] = df[name_col].astype(str).str.strip()
    out["latest"] = pd.to_numeric(df["最新价"],errors="coerce") if "最新价" in df.columns else np.nan
    out["amount"] = pd.to_numeric(df["成交额"],errors="coerce") if "成交额" in df.columns else np.nan
    out = out[
        out["code"].str.match(r"^hk\.\d{5}$") &
        out["code_name"].ne("") &
        out["code_name"].str.lower().ne("nan")
    ]
    return out.drop_duplicates("code").reset_index(drop=True)

@st.cache_data(ttl=1800, show_spinner=False)
def hk_universe_snapshot():
    frames = []
    errors = []

    # 多数据源并行兜底思路：东财主板 -> 东财全港股 -> 新浪全港股 -> 东财知名港股
    getters = [
        ("东财主板", lambda: ak.stock_hk_main_board_spot_em()),
        ("东财全港股", lambda: ak.stock_hk_spot_em()),
        ("新浪全港股", lambda: ak.stock_hk_spot()),
        ("东财知名港股", lambda: ak.stock_hk_famous_spot_em()),
    ]
    for label,getter in getters:
        try:
            x = _hk_spot_to_universe(getter())
            if not x.empty:
                frames.append(x)
                # 主板或全港股任一拿到大表后即可满足名称查询；继续尝试会拖慢页面
                if len(x) > 500:
                    break
        except Exception as ex:
            errors.append(f"{label}:{ex}")

    if not frames:
        return pd.DataFrame(columns=["code","code_name","latest","amount"])

    out = pd.concat(frames,ignore_index=True)
    # 信息更完整的行优先
    out["_info"] = out["latest"].notna().astype(int) + out["amount"].notna().astype(int)
    out = out.sort_values("_info",ascending=False).drop_duplicates("code",keep="first").drop(columns="_info")
    return out.reset_index(drop=True)

def _a_name_matches(s):
    rows=[]
    if int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)>0:
        try:
            rs=bs.query_stock_basic(code_name=s)
            if getattr(rs,"error_code","0")=="0":
                df=_rs_to_df(rs)
                if not df.empty and "code" in df.columns:
                    name_col="code_name" if "code_name" in df.columns else ("name" if "name" in df.columns else None)
                    for _,row in df.iterrows():
                        name=str(row[name_col]).strip() if name_col else ""
                        if name:
                            rows.append((str(row["code"]),name))
        except Exception:
            pass
    if rows:
        return rows
    try:
        pool=_ak_all_a_universe()
        exact=pool[pool["code_name"].astype(str).str.strip()==str(s).strip()]
        for _,row in exact.iterrows():
            rows.append((str(row["code"]),str(row["code_name"])))
    except Exception:
        pass
    return rows

def resolve_symbol_input(value):
    s = str(value or "").strip()
    if not s:
        raise ValueError("请输入股票代码或名称。")

    # 明确代码：5位按港股，6位按A股；00700.HK / HK00700 也支持。
    norm = normalize_code(s)
    if norm.startswith(("sh.","sz.")) and re.fullmatch(r"(sh|sz)\.\d{6}",norm):
        return norm, stock_basic_name(norm)
    if norm.startswith("hk.") and re.fullmatch(r"hk\.\d{5}",norm):
        return norm, stock_basic_name(norm)

    hk_hint = s.upper().endswith(".HK") or s.upper().startswith("HK") or "港股" in s
    clean_name = re.sub(r"(?i)\.HK$","",s).replace("港股","").strip()

    matches = []
    if not hk_hint:
        for code,name in _a_name_matches(clean_name):
            if name == clean_name:
                matches.append((code,name,"A股"))

    try:
        hk = hk_universe_snapshot()
        if not hk.empty:
            target_hk_name = _normalize_hk_name(clean_name)
            exact = hk[hk["code_name"].map(_normalize_hk_name) == target_hk_name]
            for _,row in exact.iterrows():
                matches.append((str(row["code"]),str(row["code_name"]),"港股"))
    except Exception:
        hk = pd.DataFrame()

    if len(matches) == 1:
        return matches[0][0],matches[0][1]
    if len(matches) > 1:
        choices = "、".join([f"{x[1]}({display_code(x[0])},{x[2]})" for x in matches[:6]])
        raise ValueError(f"名称对应多个市场，请输入代码或加.HK。匹配到：{choices}")

    # 唯一模糊匹配
    candidates = []
    if not hk_hint:
        try:
            apool = fetch_universe("全A股（沪深）")
            aa = apool[apool["code_name"].astype(str).str.contains(re.escape(clean_name),na=False)]
            for _,row in aa.head(8).iterrows():
                candidates.append((str(row["code"]),str(row["code_name"]),"A股"))
        except Exception:
            pass
    try:
        if "hk" not in locals() or hk.empty:
            hk = hk_universe_snapshot()
        target_hk_name = _normalize_hk_name(clean_name)
        hk_names = hk["code_name"].map(_normalize_hk_name)
        hh = hk[hk_names.str.contains(re.escape(target_hk_name),na=False)]
        for _,row in hh.head(8).iterrows():
            candidates.append((str(row["code"]),str(row["code_name"]),"港股"))
    except Exception:
        pass

    # 去重
    uniq = {}
    for x in candidates:
        uniq[x[0]] = x
    candidates = list(uniq.values())
    if len(candidates) == 1:
        return candidates[0][0],candidates[0][1]
    if len(candidates) > 1:
        choices = "、".join([f"{x[1]}({display_code(x[0])},{x[2]})" for x in candidates[:6]])
        raise ValueError(f"名称不唯一，请输入更完整名称或代码。匹配到：{choices}")
    raise ValueError(f"未找到股票：{s}。港股名称查询依赖港股股票池接口；若上游暂时不可用，可先输入港股代码，例如腾讯控股输入 0700 或 00700。")

def stock_basic_name(code):
    code=normalize_code(code)

    # 精确代码优先走iFinD基础数据，只请求一个名称，避免为了取名称下载整个A/H股票池。
    if ifind_configured():
        try:
            names=ifind_basic_names([code])
            name=names.get(code)
            if name:
                return str(name).strip()
        except Exception:
            pass

    if code.startswith("hk."):
        try:
            hk=hk_universe_snapshot()
            hit=hk[hk["code"]==code]
            if not hit.empty:
                return str(hit.iloc[0]["code_name"]).strip()
        except Exception:
            pass
        return display_code(code)

    if int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)>0:
        try:
            rs=bs.query_stock_basic(code=code)
            if getattr(rs,"error_code","0")=="0":
                df=_rs_to_df(rs)
                if not df.empty:
                    for col in ["code_name","name"]:
                        if col in df.columns and str(df.iloc[0][col]).strip():
                            return str(df.iloc[0][col]).strip()
        except Exception:
            pass

    # AKShare全市场名称表是慢路径，仅在iFinD/BaoStock都不可用时才调用。
    try:
        pool=_ak_all_a_universe()
        hit=pool[pool["code"]==code]
        if not hit.empty:
            return str(hit.iloc[0]["code_name"]).strip()
    except Exception:
        pass
    return display_code(code)


def sanitize_daily(df):
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    d=df.copy()
    if "trade_date" in d.columns:
        d["trade_date"]=pd.to_datetime(d["trade_date"],errors="coerce")
    for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
        if col in d.columns:
            d[col]=pd.to_numeric(d[col],errors="coerce")
    required=[x for x in ["trade_date","open","high","low","close","vol"] if x in d.columns]
    if required:
        d=d.dropna(subset=required)
    if all(x in d.columns for x in ["open","high","low","close","vol"]):
        valid=(
            (d["open"]>0)&(d["close"]>0)&
            (d["high"]>=d["low"])&
            (d["high"]>=d[["open","close"]].max(axis=1))&
            (d["low"]<=d[["open","close"]].min(axis=1))&
            (d["vol"]>=0)
        )
        d=d[valid]
    if "trade_date" in d.columns:
        d=d.sort_values("trade_date").drop_duplicates("trade_date",keep="last")
    return d.reset_index(drop=True)

def _read_daily_cache(code, start_date, end_date, adjustflag="2"):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """SELECT trade_date,code,open,high,low,close,vol,amount,pctChg,turn,tradestatus,isST
           FROM market_daily_cache
           WHERE code=? AND adjustflag=? AND trade_date BETWEEN ? AND ?
           ORDER BY trade_date""",
        conn,
        params=(code,adjustflag,start_date,end_date)
    )
    conn.close()
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return sanitize_daily(df)

def _cache_bounds(code, adjustflag="2"):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT MIN(trade_date),MAX(trade_date) FROM market_daily_cache WHERE code=? AND adjustflag=?",
        (code,adjustflag)
    ).fetchone()
    meta = conn.execute(
        "SELECT last_checked FROM market_cache_meta WHERE code=?",
        (code,)
    ).fetchone()
    conn.close()
    return (row[0] if row else None, row[1] if row else None, meta[0] if meta else None)

def _save_daily_cache(df, code, adjustflag="2"):
    if df is None or df.empty:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for _,r in df.iterrows():
        rows.append((
            code,
            pd.Timestamp(r["trade_date"]).strftime("%Y-%m-%d"),
            float(r["open"]) if pd.notna(r.get("open")) else None,
            float(r["high"]) if pd.notna(r.get("high")) else None,
            float(r["low"]) if pd.notna(r.get("low")) else None,
            float(r["close"]) if pd.notna(r.get("close")) else None,
            float(r["vol"]) if pd.notna(r.get("vol")) else None,
            float(r["amount"]) if pd.notna(r.get("amount")) else None,
            float(r["pctChg"]) if pd.notna(r.get("pctChg")) else None,
            float(r["turn"]) if pd.notna(r.get("turn")) else None,
            str(r.get("tradestatus","")),
            str(r.get("isST","")),
            adjustflag,
            now
        ))
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        """INSERT OR REPLACE INTO market_daily_cache(
           code,trade_date,open,high,low,close,vol,amount,pctChg,turn,
           tradestatus,isST,adjustflag,fetched_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    conn.commit()
    conn.close()

def _mark_cache_checked(code):
    now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO market_cache_meta(code,last_checked,updated_at)
           VALUES(?,?,?)
           ON CONFLICT(code) DO UPDATE SET
             last_checked=excluded.last_checked,
             updated_at=excluded.updated_at""",
        (code,now,now)
    )
    conn.commit()
    conn.close()

def _should_refresh_cache(last_checked,cache_max):
    now=datetime.utcnow()
    today=now.strftime("%Y-%m-%d")
    if not last_checked:
        return True
    raw=str(last_checked)
    checked_date=raw[:10]
    if checked_date<today:
        return True
    if cache_max and str(cache_max)>=today:
        return False
    # 亚洲市场收盘后若当天曾过早检查，至少间隔2小时再重试一次。
    try:
        checked=pd.Timestamp(raw)
        age=(pd.Timestamp(now)-checked).total_seconds()/3600
    except Exception:
        age=0
    return now.hour>=8 and age>=2


def _normalize_a_history(raw,code):
    if raw is None or raw.empty:
        return pd.DataFrame()
    df=raw.copy()
    rename={
        "日期":"trade_date","date":"trade_date",
        "开盘":"open","open":"open",
        "最高":"high","high":"high",
        "最低":"low","low":"low",
        "收盘":"close","close":"close",
        "成交量":"vol","volume":"vol",
        "成交额":"amount","amount":"amount",
        "涨跌幅":"pctChg","换手率":"turn","turnover":"turn"
    }
    df=df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
    needed=["trade_date","open","high","low","close","vol"]
    if any(x not in df.columns for x in needed):
        return pd.DataFrame()
    for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
        if col not in df.columns:
            df[col]=np.nan
        df[col]=pd.to_numeric(df[col],errors="coerce")
    df["trade_date"]=pd.to_datetime(df["trade_date"],errors="coerce")
    df["code"]=code
    df["tradestatus"]="1"
    df["isST"]=""
    df=df.dropna(subset=["trade_date","close"])
    cols=["trade_date","code","open","high","low","close","vol","amount","pctChg","turn","tradestatus","isST"]
    return sanitize_daily(df[cols]).sort_values("trade_date").reset_index(drop=True)

def _download_a_daily_ak(code,start,end):
    symbol=display_code(code)
    market_symbol=("sh"+symbol if code.startswith("sh.") else "sz"+symbol)
    s=str(start).replace("-","")
    e=str(end).replace("-","")
    errors=[]

    getters=[
        ("东财A股历史",lambda: ak.stock_zh_a_hist(
            symbol=symbol,period="daily",start_date=s,end_date=e,
            adjust="qfq",timeout=12
        )),
        ("腾讯A股历史",lambda: ak.stock_zh_a_hist_tx(
            symbol=market_symbol,start_date=s,end_date=e,
            adjust="qfq",timeout=12
        )),
        ("新浪A股历史",lambda: ak.stock_zh_a_daily(
            symbol=market_symbol,start_date=start,end_date=end,adjust="qfq"
        ))
    ]

    for label,getter in getters:
        last=None
        for attempt in range(1,4):
            try:
                raw=getter()
                df=_normalize_a_history(raw,code)
                if not df.empty:
                    mask=(
                        (df["trade_date"]>=pd.Timestamp(start))&
                        (df["trade_date"]<=pd.Timestamp(end))
                    )
                    out=df.loc[mask].reset_index(drop=True)
                    if not out.empty:
                        return out
                last=RuntimeError("返回空数据")
            except Exception as ex:
                last=ex
            if attempt<3:
                time.sleep(0.8*attempt)
        errors.append(f"{label}:{last}")

    raise RuntimeError("AKShare A股历史行情失败："+"；".join(errors[-3:]))

def _download_a_daily(code,start,end):
    if start>end:
        return pd.DataFrame()
    errors=[]

    if ifind_configured():
        try:
            df=ifind_history_one(code,start,end,interval="D",cps=2)
            df=sanitize_daily(df)
            if not df.empty:
                return df
        except Exception as ex:
            errors.append(f"iFinD:{ex}")

    try:
        df=_download_a_daily_ak(code,start,end)
        if df is not None and not df.empty:
            return df
    except Exception as ex:
        errors.append(f"AKShare:{ex}")

    if int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)>0:
        try:
            fields="date,code,open,high,low,close,volume,amount,pctChg,turn,tradestatus,isST"
            rs=bs.query_history_k_data_plus(
                code,fields,start_date=start,end_date=end,frequency="d",adjustflag="2"
            )
            if getattr(rs,"error_code","0")!="0":
                raise RuntimeError(getattr(rs,"error_msg","BaoStock返回错误"))
            df=_rs_to_df(rs)
            if not df.empty:
                df=df.rename(columns={"date":"trade_date","volume":"vol"})
                for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
                    if col in df.columns:
                        df[col]=pd.to_numeric(df[col],errors="coerce")
                df["trade_date"]=pd.to_datetime(df["trade_date"],errors="coerce")
                if "tradestatus" in df.columns:
                    df=df[df["tradestatus"].astype(str)=="1"]
                df=sanitize_daily(df)
                if not df.empty:
                    return df.sort_values("trade_date").reset_index(drop=True)
        except Exception as ex:
            errors.append(f"BaoStock:{ex}")

    raise RuntimeError("A股历史行情多源失败："+"；".join(errors[-3:]))

def _normalize_hk_history(raw,code):
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    rename = {
        "日期":"trade_date","date":"trade_date",
        "开盘":"open","open":"open",
        "最高":"high","high":"high",
        "最低":"low","low":"low",
        "收盘":"close","close":"close",
        "成交量":"vol","volume":"vol",
        "成交额":"amount","amount":"amount",
        "涨跌幅":"pctChg","换手率":"turn"
    }
    df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
    needed = ["trade_date","open","high","low","close","vol"]
    if any(x not in df.columns for x in needed):
        return pd.DataFrame()
    for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col],errors="coerce")
    df["trade_date"] = pd.to_datetime(df["trade_date"],errors="coerce")
    df["code"] = code
    df["tradestatus"] = "1"
    df["isST"] = ""
    df = df.dropna(subset=["trade_date","close"])
    return df[["trade_date","code","open","high","low","close","vol","amount","pctChg","turn","tradestatus","isST"]].sort_values("trade_date").reset_index(drop=True)

def _download_hk_daily(code,start,end):
    if start>end:
        return pd.DataFrame()
    errors=[]

    if ifind_configured():
        try:
            df=ifind_history_one(code,start,end,interval="D",cps=2)
            df=sanitize_daily(df)
            if not df.empty:
                return df
        except Exception as ex:
            errors.append(f"iFinD:{ex}")

    symbol=display_code(code).zfill(5)
    s0=start.replace("-","")
    e0=end.replace("-","")
    try:
        raw=ak.stock_hk_hist(
            symbol=symbol,period="daily",start_date=s0,end_date=e0,adjust="qfq"
        )
        df=_normalize_hk_history(raw,code)
        if not df.empty:
            return df
    except Exception as ex:
        errors.append(f"东财港股:{ex}")
    try:
        raw=ak.stock_hk_daily(symbol=symbol,adjust="qfq")
        df=_normalize_hk_history(raw,code)
        if not df.empty:
            mask=(
                (df["trade_date"]>=pd.Timestamp(start))&
                (df["trade_date"]<=pd.Timestamp(end))
            )
            out=df.loc[mask].reset_index(drop=True)
            if not out.empty:
                return out
    except Exception as ex:
        errors.append(f"新浪港股:{ex}")
    raise RuntimeError("港股历史行情多源失败："+"；".join(errors[-3:]))

def _download_daily(code,start,end):
    code = normalize_code(code)
    return _download_hk_daily(code,start,end) if code.startswith("hk.") else _download_a_daily(code,start,end)

def market_cache_flag(code,kind="daily"):
    code=normalize_code(code)
    if kind=="index":
        return "ifind_idx_v1" if ifind_configured() else "3"
    if kind=="weekly":
        if ifind_configured():
            return "ifind_hk_w_qfq_v1" if code.startswith("hk.") else "ifind_a_w_qfq_v1"
        return "hk_w_qfq" if code.startswith("hk.") else "w2"
    if ifind_configured():
        return "ifind_hk_qfq_v1" if code.startswith("hk.") else "ifind_a_qfq_v1"
    return "hk_qfq" if code.startswith("hk.") else "2"

def prefetch_ifind_daily(codes,years=1):
    if not ifind_configured():
        return {"requested":0,"saved":0,"errors":[]}
    clean=[normalize_code(x) for x in codes if normalize_code(x)]
    if not clean:
        return {"requested":0,"saved":0,"errors":[]}
    end=datetime.now().strftime("%Y-%m-%d")
    start=(pd.Timestamp.today()-pd.Timedelta(days=365*years+180)).strftime("%Y-%m-%d")
    need=[]
    for code in clean:
        flag=market_cache_flag(code,"daily")
        cmin,cmax,last_checked=_cache_bounds(code,flag)
        if not cmin or not cmax or cmin>start or _should_refresh_cache(last_checked,cmax):
            need.append(code)
    if not need:
        return {"requested":0,"saved":0,"errors":[]}
    saved=0
    errors=[]
    for pos in range(0,len(need),20):
        batch=need[pos:pos+20]
        try:
            got=ifind_history_many(batch,start,end,interval="D",cps=2)
            for code,df in got.items():
                if df is not None and not df.empty:
                    flag=market_cache_flag(code,"daily")
                    _save_daily_cache(df,code,flag)
                    _mark_cache_checked(code)
                    saved+=1
        except Exception as ex:
            errors.append(str(ex))
    return {"requested":len(need),"saved":saved,"errors":errors}

def prefetch_ifind_weekly(codes,years=3):
    if not ifind_configured():
        return {"requested":0,"saved":0,"errors":[]}
    clean=[normalize_code(x) for x in codes if normalize_code(x)]
    clean=list(dict.fromkeys(clean))
    if not clean:
        return {"requested":0,"saved":0,"errors":[]}
    end=datetime.now().strftime("%Y-%m-%d")
    start=(pd.Timestamp.today()-pd.Timedelta(days=365*int(years)+240)).strftime("%Y-%m-%d")
    need=[]
    current_week_start=(
        pd.Timestamp.today().normalize()-pd.Timedelta(days=pd.Timestamp.today().weekday())
    ).strftime("%Y-%m-%d")
    for code in clean:
        flag=market_cache_flag(code,"weekly")
        cmin,cmax,_=_cache_bounds(code,flag)
        if not cmin or not cmax or cmin>start or str(cmax)<current_week_start:
            need.append(code)
    if not need:
        return {"requested":0,"saved":0,"errors":[]}

    saved=0
    errors=[]
    for pos in range(0,len(need),20):
        batch=need[pos:pos+20]
        try:
            got=ifind_history_many(batch,start,end,interval="W",cps=2)
            for code,df in got.items():
                if df is None or df.empty:
                    continue
                _save_daily_cache(df,code,market_cache_flag(code,"weekly"))
                saved+=1
        except Exception as ex:
            errors.append(str(ex))
    return {"requested":len(need),"saved":saved,"errors":errors}


def prefetch_ifind_analysis_bundle(code,daily_years=2,weekly_years=3):
    """Warm stock daily + A-share benchmark daily + native weekly in at most two parallel iFinD calls."""
    if not ifind_configured():
        return {"daily_saved":0,"weekly_saved":0,"errors":[]}

    code=normalize_code(code)
    end=datetime.now().strftime("%Y-%m-%d")
    dstart=(pd.Timestamp.today()-pd.Timedelta(days=365*int(daily_years)+180)).strftime("%Y-%m-%d")
    wstart=(pd.Timestamp.today()-pd.Timedelta(days=365*int(weekly_years)+240)).strftime("%Y-%m-%d")
    errors=[]
    daily_saved=0
    weekly_saved=0

    need_daily=[]
    stock_flag=market_cache_flag(code,"daily")
    smin,smax,slast=_cache_bounds(code,stock_flag)
    if not smin or not smax or smin>dstart or _should_refresh_cache(slast,smax):
        need_daily.append((code,"daily"))

    if market_of_code(code)=="A股":
        bench="sh.000300"
        bflag=market_cache_flag(bench,"index")
        bmin,bmax,blast=_cache_bounds(bench,bflag)
        if not bmin or not bmax or bmin>dstart or _should_refresh_cache(blast,bmax):
            need_daily.append((bench,"index"))

    wflag=market_cache_flag(code,"weekly")
    wmin,wmax,_=_cache_bounds(code,wflag)
    current_week_start=(
        pd.Timestamp.today().normalize()-pd.Timedelta(days=pd.Timestamp.today().weekday())
    ).strftime("%Y-%m-%d")
    need_weekly=(not wmin or not wmax or wmin>wstart or str(wmax)<current_week_start)

    def _daily_job():
        if not need_daily:
            return {}
        codes=[x[0] for x in need_daily]
        return ifind_history_many(codes,dstart,end,interval="D",cps=2)

    def _weekly_job():
        if not need_weekly:
            return pd.DataFrame()
        return ifind_history_one(code,wstart,end,interval="W",cps=2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fd=pool.submit(_daily_job)
        fw=pool.submit(_weekly_job)
        try:
            got=fd.result()
            for dcode,kind in need_daily:
                df=got.get(dcode)
                if df is None or df.empty:
                    continue
                flag=market_cache_flag(dcode,"index" if kind=="index" else "daily")
                _save_daily_cache(df,dcode,flag)
                _mark_cache_checked(dcode)
                daily_saved+=1
        except Exception as ex:
            errors.append(f"日K预取:{ex}")
        try:
            wdf=fw.result()
            if wdf is not None and not wdf.empty:
                _save_daily_cache(wdf,code,wflag)
                weekly_saved=1
        except Exception as ex:
            errors.append(f"周K预取:{ex}")

    return {"daily_saved":daily_saved,"weekly_saved":weekly_saved,"errors":errors}


def fetch_stock_daily(code,years=3):
    code=normalize_code(code)
    end=datetime.now().strftime("%Y-%m-%d")
    start=(pd.Timestamp.today()-pd.Timedelta(days=365*years+180)).strftime("%Y-%m-%d")
    cache_flag=market_cache_flag(code,"daily")
    cache_min,cache_max,last_checked=_cache_bounds(code,cache_flag)

    def _cached():
        return _read_daily_cache(code,start,end,cache_flag)

    if not cache_min or not cache_max:
        try:
            fresh=_download_daily(code,start,end)
            _save_daily_cache(fresh,code,cache_flag)
            _mark_cache_checked(code)
        except Exception:
            cached=_cached()
            if len(cached)>=60:
                return cached
            raise
    else:
        if start<cache_min:
            pre_end=(pd.Timestamp(cache_min)-pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                older=_download_daily(code,start,pre_end)
                _save_daily_cache(older,code,cache_flag)
            except Exception:
                # 历史头部补齐失败时，已有缓存足够则继续，不阻塞当前分析。
                cached=_cached()
                if len(cached)<60:
                    raise

        if _should_refresh_cache(last_checked,cache_max):
            next_start=(pd.Timestamp(cache_max)+pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                newer=_download_daily(code,next_start,end)
                _save_daily_cache(newer,code,cache_flag)
                _mark_cache_checked(code)
            except Exception:
                # 上游临时断开时优先使用已有缓存，避免整个分析失败。
                cached=_cached()
                if len(cached)>=60:
                    return cached
                raise

    return _cached()

def _download_index_daily_ak(code,start,end):
    symbol=display_code(code)
    s=str(start).replace("-","")
    e=str(end).replace("-","")
    errors=[]
    getters=[
        ("东财指数历史",lambda: ak.index_zh_a_hist(
            symbol=symbol,period="daily",start_date=s,end_date=e
        )),
        ("新浪指数历史",lambda: ak.stock_zh_index_daily(
            symbol=("sh"+symbol if code.startswith("sh.") else "sz"+symbol)
        ))
    ]
    for label,getter in getters:
        try:
            raw=getter()
            if raw is None or raw.empty:
                continue
            df=raw.copy().rename(columns={
                "日期":"trade_date","date":"trade_date",
                "开盘":"open","open":"open","最高":"high","high":"high",
                "最低":"low","low":"low","收盘":"close","close":"close",
                "成交量":"vol","volume":"vol","成交额":"amount","amount":"amount",
                "涨跌幅":"pctChg"
            })
            for col in ["open","high","low","close","vol","amount","pctChg"]:
                if col not in df.columns:
                    df[col]=np.nan
                df[col]=pd.to_numeric(df[col],errors="coerce")
            df["trade_date"]=pd.to_datetime(df["trade_date"],errors="coerce")
            df["code"]=code
            df["turn"]=np.nan
            df["tradestatus"]="1"
            df["isST"]=""
            df=df.dropna(subset=["trade_date","close"])
            mask=(df["trade_date"]>=pd.Timestamp(start))&(df["trade_date"]<=pd.Timestamp(end))
            out=df.loc[mask,["trade_date","code","open","high","low","close","vol","amount","pctChg","turn","tradestatus","isST"]]
            out=sanitize_daily(out)
            if not out.empty:
                return out.reset_index(drop=True)
        except Exception as ex:
            errors.append(f"{label}:{ex}")
    raise RuntimeError("AKShare指数历史失败："+"；".join(errors[-2:]))

def _download_index_daily(code,start,end):
    if start>end:
        return pd.DataFrame()
    errors=[]

    if ifind_configured():
        try:
            df=ifind_history_one(code,start,end,interval="D",cps=1)
            df=sanitize_daily(df)
            if not df.empty:
                return df
        except Exception as ex:
            errors.append(f"iFinD指数:{ex}")

    try:
        df=_download_index_daily_ak(code,start,end)
        if df is not None and not df.empty:
            return df
    except Exception as ex:
        errors.append(f"AKShare指数:{ex}")

    if int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)>0:
        try:
            fields="date,code,open,high,low,close,preclose,volume,amount,pctChg"
            rs=bs.query_history_k_data_plus(
                code,fields,start_date=start,end_date=end,frequency="d",adjustflag="3"
            )
            if getattr(rs,"error_code","0")!="0":
                raise RuntimeError(getattr(rs,"error_msg","BaoStock返回错误"))
            df=_rs_to_df(rs)
            if not df.empty:
                df=df.rename(columns={"date":"trade_date","volume":"vol"})
                for col in ["open","high","low","close","vol","amount","pctChg"]:
                    if col in df.columns:
                        df[col]=pd.to_numeric(df[col],errors="coerce")
                df["trade_date"]=pd.to_datetime(df["trade_date"],errors="coerce")
                df["turn"]=np.nan
                df["tradestatus"]="1"; df["isST"]=""
                df=sanitize_daily(df)
                if not df.empty:
                    return df.sort_values("trade_date").reset_index(drop=True)
        except Exception as ex:
            errors.append(f"BaoStock指数:{ex}")

    raise RuntimeError("指数历史多源失败："+"；".join(errors[-3:]))

def fetch_benchmark_daily(years=5,code="sh.000300"):
    end=datetime.now().strftime("%Y-%m-%d")
    start=(pd.Timestamp.today()-pd.Timedelta(days=365*years+180)).strftime("%Y-%m-%d")
    flag=market_cache_flag(code,"index")
    cache_min,cache_max,last_checked=_cache_bounds(code,flag)

    def _cached():
        return _read_daily_cache(code,start,end,flag)

    if not cache_min or not cache_max:
        try:
            fresh=_download_index_daily(code,start,end)
            _save_daily_cache(fresh,code,flag)
            _mark_cache_checked(code)
        except Exception:
            cached=_cached()
            if len(cached)>=60:
                return cached
            raise
    else:
        if start<cache_min:
            pre_end=(pd.Timestamp(cache_min)-pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                older=_download_index_daily(code,start,pre_end)
                _save_daily_cache(older,code,flag)
            except Exception:
                cached=_cached()
                if len(cached)<60:
                    raise

        if _should_refresh_cache(last_checked,cache_max):
            next_start=(pd.Timestamp(cache_max)+pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                newer=_download_index_daily(code,next_start,end)
                _save_daily_cache(newer,code,flag)
                _mark_cache_checked(code)
            except Exception:
                cached=_cached()
                if len(cached)>=60:
                    return cached
                raise

    return _cached()

def _download_hk_benchmark(start,end):
    last_error = None
    try:
        raw = ak.stock_hk_index_daily_sina(symbol="HSI")
        if raw is not None and not raw.empty:
            df = raw.copy().rename(columns={"date":"trade_date","volume":"vol"})
            for col in ["open","high","low","close","vol"]:
                df[col] = pd.to_numeric(df[col],errors="coerce")
            df["trade_date"] = pd.to_datetime(df["trade_date"],errors="coerce")
            df["code"] = "hkidx.HSI"
            df["amount"] = np.nan
            df["pctChg"] = df["close"].pct_change()*100
            df["turn"] = np.nan
            df["tradestatus"] = "1"
            df["isST"] = ""
            mask = (
                (df["trade_date"]>=pd.Timestamp(start)) &
                (df["trade_date"]<=pd.Timestamp(end))
            )
            out = df.loc[mask,["trade_date","code","open","high","low","close","vol","amount","pctChg","turn","tradestatus","isST"]]
            if not out.empty:
                return out.reset_index(drop=True)
    except Exception as ex:
        last_error = ex

    # 备用：港股通历史接口中带恒生指数收盘值。仅用于市场环境，不参与个股ATR。
    try:
        raw = ak.stock_hsgt_hist_em(symbol="港股通沪")
        if raw is not None and not raw.empty and "恒生指数" in raw.columns:
            df = pd.DataFrame()
            df["trade_date"] = pd.to_datetime(raw["日期"],errors="coerce")
            close = pd.to_numeric(raw["恒生指数"],errors="coerce")
            df["open"] = close
            df["high"] = close
            df["low"] = close
            df["close"] = close
            df["vol"] = 0.0
            df["amount"] = np.nan
            df["pctChg"] = close.pct_change()*100
            df["turn"] = np.nan
            df["tradestatus"] = "1"
            df["isST"] = ""
            df["code"] = "hkidx.HSI"
            mask = (
                (df["trade_date"]>=pd.Timestamp(start)) &
                (df["trade_date"]<=pd.Timestamp(end))
            )
            out = df.loc[mask,["trade_date","code","open","high","low","close","vol","amount","pctChg","turn","tradestatus","isST"]].dropna(subset=["trade_date","close"])
            if not out.empty:
                return out.reset_index(drop=True)
    except Exception as ex:
        last_error = ex
    raise RuntimeError(f"恒生指数历史行情获取失败：{last_error}")

def fetch_hk_benchmark_daily(years=5):
    key = "hkidx.HSI"
    flag = "index"
    end = datetime.now().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today()-pd.Timedelta(days=365*years+180)).strftime("%Y-%m-%d")
    cache_min,cache_max,last_checked = _cache_bounds(key,flag)
    today = datetime.now().strftime("%Y-%m-%d")
    if not cache_min or not cache_max:
        fresh = _download_hk_benchmark(start,end)
        _save_daily_cache(fresh,key,flag)
        _mark_cache_checked(key)
    else:
        if start < cache_min:
            pre_end = (pd.Timestamp(cache_min)-pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            older = _download_hk_benchmark(start,pre_end)
            _save_daily_cache(older,key,flag)
        if _should_refresh_cache(last_checked,cache_max):
            next_start = (pd.Timestamp(cache_max)+pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            newer = _download_hk_benchmark(next_start,end)
            _save_daily_cache(newer,key,flag)
            _mark_cache_checked(key)
    return _read_daily_cache(key,start,end,flag)

def fetch_benchmark_for_code(code,years=5):
    return fetch_hk_benchmark_daily(years) if market_of_code(code)=="港股" else fetch_benchmark_daily(years)

def market_cache_stats():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """SELECT COUNT(*),COUNT(DISTINCT code),MIN(trade_date),MAX(trade_date)
           FROM market_daily_cache"""
    ).fetchone()
    size = conn.execute(
        "SELECT page_count*page_size FROM pragma_page_count(), pragma_page_size()"
    ).fetchone()[0]
    conn.close()
    return {
        "rows":int(row[0] or 0),
        "stocks":int(row[1] or 0),
        "min_date":row[2] or "—",
        "max_date":row[3] or "—",
        "db_mb":round(float(size or 0)/1024/1024,1)
    }

def clear_market_cache():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM market_daily_cache")
    conn.execute("DELETE FROM market_cache_meta")
    conn.commit()
    conn.close()

def add_indicators(df):
    if df is None or df.empty:
        return pd.DataFrame()
    d=df.copy().sort_values("trade_date").reset_index(drop=True)
    close=d["close"]
    d["ret1"]=close.pct_change()
    d["boll_mid"]=close.rolling(20).mean()
    std=close.rolling(20).std(ddof=0)
    d["boll_up"]=d["boll_mid"]+2*std
    d["boll_low"]=d["boll_mid"]-2*std
    d["ma60"]=close.rolling(60).mean()

    ema12=close.ewm(span=12,adjust=False).mean()
    ema26=close.ewm(span=26,adjust=False).mean()
    d["dif"]=ema12-ema26
    d["dea"]=d["dif"].ewm(span=9,adjust=False).mean()
    d["macd"]=2*(d["dif"]-d["dea"])

    d["vol_ma5"]=d["vol"].rolling(5).mean()
    d["vol_ma10"]=d["vol"].rolling(10).mean()
    if "amount" in d.columns:
        d["amount_ma20"]=d["amount"].rolling(20).mean()
        d["amount_median20"]=d["amount"].rolling(20).median()
    else:
        d["amount_ma20"]=np.nan
        d["amount_median20"]=np.nan

    d["boll_slope"]=d["boll_mid"]-d["boll_mid"].shift(3)
    d["dif_slope"]=d["dif"]-d["dif"].shift(3)
    d["high20"]=d["high"].rolling(20).max()
    d["low20"]=d["low"].rolling(20).min()
    d["high20_prev"]=d["high"].shift(1).rolling(20).max()
    d["high60_prev"]=d["high"].shift(1).rolling(60).max()
    d["low10_prev"]=d["low"].shift(1).rolling(10).min()
    d["low20_prev"]=d["low"].shift(1).rolling(20).min()

    prev_close=close.shift(1)
    tr=pd.concat([
        d["high"]-d["low"],
        (d["high"]-prev_close).abs(),
        (d["low"]-prev_close).abs()
    ],axis=1).max(axis=1)
    d["atr14"]=tr.rolling(14).mean()
    d["ret20"]=close/close.shift(20)-1
    d["ret60"]=close/close.shift(60)-1
    return d

def _download_a_weekly_ak(code,start,end):
    symbol=display_code(code)
    s=str(start).replace("-","")
    e=str(end).replace("-","")
    errors=[]
    getters=[
        ("东财A股周K",lambda: ak.stock_zh_a_hist(
            symbol=symbol,period="weekly",start_date=s,end_date=e,adjust="qfq"
        )),
        ("新浪A股周K",lambda: ak.stock_zh_a_daily(
            symbol=("sh"+symbol if code.startswith("sh.") else "sz"+symbol),
            start_date=start,end_date=end,adjust="qfq"
        ))
    ]
    for label,getter in getters:
        try:
            raw=getter()
            if label.startswith("新浪") and raw is not None and not raw.empty:
                # 新浪接口通常给日K；作为最后兜底时本地聚合为周K。
                daily=_normalize_a_history(raw,code)
                if not daily.empty:
                    return weekly_from_daily(daily,completed_only=True,with_indicators=False)
            df=_normalize_a_history(raw,code)
            if not df.empty:
                mask=(df["trade_date"]>=pd.Timestamp(start))&(df["trade_date"]<=pd.Timestamp(end))
                out=df.loc[mask].reset_index(drop=True)
                if not out.empty:
                    return out
        except Exception as ex:
            errors.append(f"{label}:{ex}")
    raise RuntimeError("AKShare A股周K失败："+"；".join(errors[-2:]))

def _download_a_weekly(code,start,end):
    if start>end:
        return pd.DataFrame()
    errors=[]

    if ifind_configured():
        try:
            df=ifind_history_one(code,start,end,interval="W",cps=2)
            df=sanitize_daily(df)
            if not df.empty:
                return df
        except Exception as ex:
            errors.append(f"iFinD原生周K:{ex}")

    try:
        df=_download_a_weekly_ak(code,start,end)
        if df is not None and not df.empty:
            return df
    except Exception as ex:
        errors.append(f"AKShare周K:{ex}")

    if int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)>0:
        try:
            fields="date,code,open,high,low,close,volume,amount,pctChg,turn"
            rs=bs.query_history_k_data_plus(
                code,fields,start_date=start,end_date=end,frequency="w",adjustflag="2"
            )
            if getattr(rs,"error_code","0")!="0":
                raise RuntimeError(getattr(rs,"error_msg","BaoStock返回错误"))
            df=_rs_to_df(rs)
            if not df.empty:
                df=df.rename(columns={"date":"trade_date","volume":"vol"})
                for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
                    if col in df.columns:
                        df[col]=pd.to_numeric(df[col],errors="coerce")
                df["trade_date"]=pd.to_datetime(df["trade_date"],errors="coerce")
                df["tradestatus"]="1"; df["isST"]=""
                df=sanitize_daily(df)
                if not df.empty:
                    return df.sort_values("trade_date").reset_index(drop=True)
        except Exception as ex:
            errors.append(f"BaoStock周K:{ex}")

    raise RuntimeError("A股原生周K多源失败："+"；".join(errors[-3:]))

def _download_hk_weekly(code,start,end):
    errors=[]
    if ifind_configured():
        try:
            df=ifind_history_one(code,start,end,interval="W",cps=2)
            df=sanitize_daily(df)
            if not df.empty:
                return df
        except Exception as ex:
            errors.append(f"iFinD原生周K:{ex}")

    symbol=display_code(code).zfill(5)
    s0=str(start).replace("-","")
    e0=str(end).replace("-","")
    try:
        raw=ak.stock_hk_hist(
            symbol=symbol,period="weekly",start_date=s0,end_date=e0,adjust="qfq"
        )
        df=_normalize_hk_history(raw,code)
        if not df.empty:
            return df.reset_index(drop=True)
    except Exception as ex:
        errors.append(f"东财港股周K:{ex}")
    try:
        daily=_download_hk_daily(code,start,end)
        if not daily.empty:
            return weekly_from_daily(daily,completed_only=True,with_indicators=False)
    except Exception as ex:
        errors.append(f"港股日K聚合兜底:{ex}")
    raise RuntimeError("港股周K获取失败："+"；".join(errors[-3:]))

def fetch_stock_weekly(code,years=5):
    code=normalize_code(code)
    end=datetime.now().strftime("%Y-%m-%d")
    start=(pd.Timestamp.today()-pd.Timedelta(days=365*years+240)).strftime("%Y-%m-%d")
    flag=market_cache_flag(code,"weekly")
    cache_min,cache_max,last_checked=_cache_bounds(code,flag)

    if not cache_min or not cache_max:
        fresh=_download_hk_weekly(code,start,end) if code.startswith("hk.") else _download_a_weekly(code,start,end)
        _save_daily_cache(fresh,code,flag)
    else:
        if start<cache_min:
            pre_end=(pd.Timestamp(cache_min)-pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            older=_download_hk_weekly(code,start,pre_end) if code.startswith("hk.") else _download_a_weekly(code,start,pre_end)
            _save_daily_cache(older,code,flag)
        # 周K不需要盘中反复刷新；若缓存最后周早于当前周，则尝试补齐。
        current_week_start=(pd.Timestamp.today().normalize()-pd.Timedelta(days=pd.Timestamp.today().weekday())).strftime("%Y-%m-%d")
        if str(cache_max)<current_week_start:
            next_start=(pd.Timestamp(cache_max)+pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            newer=_download_hk_weekly(code,next_start,end) if code.startswith("hk.") else _download_a_weekly(code,next_start,end)
            _save_daily_cache(newer,code,flag)

    out=_read_daily_cache(code,start,end,flag)
    return add_indicators(out) if out is not None and not out.empty else pd.DataFrame()

def weekly_consistency(native_weekly,aggregated_weekly):
    if native_weekly is None or native_weekly.empty or aggregated_weekly is None or aggregated_weekly.empty:
        return {
            "level":"不可校验","score_gap":np.nan,"close_gap_pct":np.nan,
            "direction_match":False,"native_score":np.nan,"aggregate_score":np.nan
        }
    nw=native_weekly.copy().sort_values("trade_date")
    aw=aggregated_weekly.copy().sort_values("trade_date")
    # 仅比较双方都已经出现的最近完成周，避免日期标签差异造成错配。
    merged=pd.merge_asof(
        nw[["trade_date","close","boll_slope","dif","dea"]].sort_values("trade_date"),
        aw[["trade_date","close","boll_slope","dif","dea"]].sort_values("trade_date"),
        on="trade_date",direction="nearest",tolerance=pd.Timedelta(days=4),
        suffixes=("_native","_agg")
    ).dropna(subset=["close_agg"])
    if merged.empty:
        return {
            "level":"不可校验","score_gap":np.nan,"close_gap_pct":np.nan,
            "direction_match":False,"native_score":np.nan,"aggregate_score":np.nan
        }
    r=merged.iloc[-1]
    nrow={
        "boll_slope":r["boll_slope_native"],"close":r["close_native"],
        "boll_mid":nw.iloc[-1].get("boll_mid",np.nan),
        "dif":r["dif_native"],"dea":r["dea_native"]
    }
    arow={
        "boll_slope":r["boll_slope_agg"],"close":r["close_agg"],
        "boll_mid":aw.iloc[-1].get("boll_mid",np.nan),
        "dif":r["dif_agg"],"dea":r["dea_agg"]
    }
    # 周线子分只依赖周线结构；用一个中性的日线占位，仅取numeric_score返回的weekly分。
    dummy={"boll_slope":0,"close":1,"boll_mid":1,"boll_up":1.1,"boll_low":0.9,
           "dif":0,"dea":0,"macd":0,"dif_slope":0,"vol":1,"vol_ma5":1,"vol_ma10":1,"ret1":0}
    ns=numeric_score(dummy,nrow)[3]
    ag=numeric_score(dummy,arow)[3]
    close_gap=abs(float(r["close_native"])-float(r["close_agg"]))/max(abs(float(r["close_native"])),1e-9)
    dir_match=(
        np.sign(float(r["boll_slope_native"]) if pd.notna(r["boll_slope_native"]) else 0)==
        np.sign(float(r["boll_slope_agg"]) if pd.notna(r["boll_slope_agg"]) else 0)
    )
    gap=abs(float(ns)-float(ag)) if pd.notna(ns) and pd.notna(ag) else np.nan
    if pd.notna(gap) and gap<=5 and close_gap<=0.005 and dir_match:
        level="高"
    elif pd.notna(gap) and gap<=10 and close_gap<=0.015:
        level="中"
    else:
        level="低"
    return {
        "level":level,"score_gap":gap,"close_gap_pct":close_gap,
        "direction_match":bool(dir_match),"native_score":ns,"aggregate_score":ag
    }

def weekly_from_daily(df,completed_only=True,with_indicators=True):
    if df is None or df.empty:
        return pd.DataFrame()
    src=df.copy().sort_values("trade_date").reset_index(drop=True)
    src["trade_date"]=pd.to_datetime(src["trade_date"],errors="coerce")
    src=src.dropna(subset=["trade_date","close"])
    if src.empty:
        return pd.DataFrame()
    latest_daily=pd.Timestamp(src["trade_date"].max()).normalize()
    src["_week"]=src["trade_date"].dt.to_period("W-FRI")
    agg={"trade_date":"max","open":"first","high":"max","low":"min","close":"last","vol":"sum"}
    if "amount" in src.columns:
        agg["amount"]="sum"
    w=src.groupby("_week",as_index=False).agg(agg).dropna(subset=["close"])
    if completed_only and not w.empty:
        # 常规情况下只有周五收盘后才把本周视为确认周；历史周天然保留。
        latest_period=latest_daily.to_period("W-FRI")
        current_mask=w["_week"]==latest_period
        if current_mask.any() and latest_daily.weekday()!=4:
            w=w[~current_mask]
    w=w.drop(columns=["_week"],errors="ignore").reset_index(drop=True)
    return add_indicators(w) if with_indicators else sanitize_daily(w)

def numeric_score(latest_d,latest_w=None):
    trend=0
    slope=latest_d.get("boll_slope",np.nan)
    if pd.isna(slope): trend+=15
    elif slope>0: trend+=45
    elif abs(slope)<=max(abs(latest_d.get("boll_mid",0))*0.001,1e-9): trend+=24
    else: trend+=5

    close=latest_d.get("close",np.nan)
    mid=latest_d.get("boll_mid",np.nan)
    if pd.notna(close) and pd.notna(mid):
        if close>mid*1.005: trend+=35
        elif close<mid*0.995: trend+=4
        else: trend+=20
    else:
        trend+=12
    up,low=latest_d.get("boll_up",np.nan),latest_d.get("boll_low",np.nan)
    band=((up-low)/mid) if pd.notna(up) and pd.notna(low) and pd.notna(mid) and mid else np.nan
    trend+=20 if pd.notna(band) and band>0.12 else (8 if pd.notna(band) and band<0.05 else 13)
    trend=clamp(trend)

    momentum=0
    dif,dea,macd=latest_d.get("dif",np.nan),latest_d.get("dea",np.nan),latest_d.get("macd",np.nan)
    if pd.notna(dif) and pd.notna(dea):
        if dif>0 and dea>0: momentum+=35
        elif abs(dif)<max(abs(close)*0.002 if pd.notna(close) else 0.01,0.01): momentum+=21
        else: momentum+=5
        ds=latest_d.get("dif_slope",np.nan)
        momentum+=25 if pd.notna(ds) and ds>0 else (13 if pd.isna(ds) or abs(ds)<1e-9 else 3)
        momentum+=17 if dif>dea else 2
        prev_macd=latest_d.get("macd_prev",np.nan)
        if pd.notna(macd):
            if macd>0 and (pd.isna(prev_macd) or macd>=prev_macd): momentum+=23
            elif macd>0: momentum+=15
            elif pd.notna(prev_macd) and macd>prev_macd: momentum+=12
            else: momentum+=1
    else:
        momentum=38
    momentum=clamp(momentum)

    vol=latest_d.get("vol",np.nan)
    v5,v10=latest_d.get("vol_ma5",np.nan),latest_d.get("vol_ma10",np.nan)
    ret1=latest_d.get("ret1",np.nan)
    confirm=50
    if pd.notna(vol) and pd.notna(v5) and pd.notna(v10) and max(v5,v10)>0:
        ratio=vol/max(v5,v10)
        rising=pd.notna(ret1) and ret1>0
        if rising:
            if ratio>=1.60: confirm=92
            elif ratio>=1.20: confirm=82
            elif ratio>=0.95: confirm=68
            elif ratio>=0.70: confirm=54
            else: confirm=42
        else:
            if ratio>=1.60: confirm=24
            elif ratio>=1.20: confirm=34
            elif ratio>=0.95: confirm=45
            elif ratio>=0.70: confirm=52
            else: confirm=58
    confirm=clamp(confirm)

    weekly=None
    if latest_w is not None:
        weekly=0
        ws=latest_w.get("boll_slope",np.nan)
        weekly+=40 if pd.notna(ws) and ws>0 else (22 if pd.isna(ws) or abs(ws)<1e-9 else 4)
        wc,wm=latest_w.get("close",np.nan),latest_w.get("boll_mid",np.nan)
        weekly+=30 if pd.notna(wc) and pd.notna(wm) and wc>wm else (18 if pd.notna(wc) and pd.notna(wm) and wc>=wm*0.99 else 3)
        wd,we=latest_w.get("dif",np.nan),latest_w.get("dea",np.nan)
        weekly+=20 if pd.notna(wd) and pd.notna(we) and wd>0 and we>0 else (12 if pd.notna(wd) and abs(wd)<0.05 else 2)
        weekly+=10 if pd.notna(wd) and pd.notna(we) and wd>we else 1
        weekly=clamp(weekly)

    overall=(0.50*trend+0.35*momentum+0.15*confirm) if weekly is None else (0.38*trend+0.30*momentum+0.22*weekly+0.10*confirm)
    return round(overall,1),round(trend,1),round(momentum,1),(round(weekly,1) if weekly is not None else None),round(confirm,1)

def build_operation_strategy(
    code,position_state,fundamentals_ok,technical,buy_score,weekly,rr,
    market_score,rs_score,opp,tier,ev,close,mid,risk_price,target_price,atr
):
    holding=position_state!="未持有"
    p=automatic_entry_policy(market_score)
    ev_mean=ev.get("EV_R",np.nan)
    ev_lcb=ev.get("保守EV_R",np.nan)
    ev_stress=ev.get("压力EV_R",np.nan)
    wf=ev.get("walk_forward") or {}
    oos=wf.get("OOS_EV_R",np.nan)

    ev_strong=(
        pd.notna(ev_mean) and ev_mean>0 and
        pd.notna(ev_lcb) and ev_lcb>0 and
        pd.notna(ev_stress) and ev_stress>0
    )
    weekly_ok=pd.notna(weekly) and weekly>=p["周线"]

    if holding:
        if technical<45 or (pd.notna(weekly) and weekly<45):
            action="退出/大幅减仓"
            position_plan="优先把风险降到轻仓或清仓；不在技术失效状态下补仓。"
        elif technical<55 or market_score<25:
            action="减仓"
            position_plan="降低一档仓位；剩余仓位只用于观察是否重新站回强势结构。"
        elif technical<65:
            action="谨慎持有"
            position_plan="维持现有核心仓，不主动加仓；等待技术分重新回到65以上。"
        elif tier=="优先机会" and ev_strong and weekly_ok:
            action="持有，可等确认后加仓"
            position_plan="已有仓位以持有为主；若回踩确认且未追高，可小幅加仓，单次新增风险建议不超过组合NAV的0.5%。"
        else:
            action="持有观察"
            position_plan="维持仓位，不追涨；只有买点、周线和EV重新共振时才考虑加仓。"
    else:
        if tier=="优先机会" and ev_strong and fundamentals_ok:
            action="分批建仓"
            position_plan="先试仓约目标仓位的1/3～1/2；确认后再加，不一次满仓。单笔风险预算建议≤组合NAV的0.5%。"
        elif tier=="优先机会" and not fundamentals_ok:
            action="等待基本面/估值确认"
            position_plan="技术与EV已通过，但在基本面/估值确认前不执行中长期建仓。"
        elif tier=="候选观察":
            action="观察，等待触发"
            position_plan="暂不追价；满足下方买入触发后再考虑轻仓试单。"
        else:
            action="不买/继续等待"
            position_plan="当前结构或EV证据不足，不因短期上涨放宽门槛。"

    entry_parts=[]
    if pd.notna(mid):
        entry_parts.append(f"收盘保持/重新站稳BOLL中轨 {mid:.2f}")
    entry_parts.append(f"技术分≥{p['技术']}、买点分≥{p['买点']}")
    entry_parts.append(f"确认周线≥{p['周线']}、相对强度≥{p['相对强度']}")
    entry_parts.append(f"结构RR≥{p['盈亏比']:.2f}")
    if pd.notna(atr) and atr>0 and pd.notna(close):
        entry_parts.append(f"次日开盘相对信号收盘跳空不超过约 {1.5*atr:.2f}（1.5ATR）")
    if not holding:
        entry_parts.append("历史EV、保守EV、2倍成本EV均为正时优先执行")

    if holding:
        add_parts=[
            f"技术分维持≥{max(65,p['技术'])}",
            f"买点分重新≥{p['买点']}且不明显追高",
            f"周线≥{p['周线']}，市场环境不处于逆风区"
        ]
        if pd.notna(ev_lcb):
            add_parts.append("保守EV继续>0")
    else:
        add_parts=["首仓后只有结构继续强化且风险位上移，才进行第二次加仓"]

    reduce_parts=[
        "技术分跌破55进入谨慎/减仓区",
        "技术分较阶段峰值回落≥15且当前分<65",
        "确认周线跌破45",
        "市场环境<25且技术分<60"
    ]
    exit_parts=["技术分<45或周线<45"]
    if pd.notna(risk_price):
        exit_parts.insert(0,f"价格触及/跌破初始风险位 {risk_price:.2f}，按风险位优先执行")
    if pd.notna(mid):
        exit_parts.append(f"持续运行于中轨 {mid:.2f} 下方且动能没有修复")

    target_txt=(
        f"{target_price:.2f} 附近作为参考压力区；不是固定止盈，强趋势可继续持有。"
        if pd.notna(target_price) else "暂无可靠固定压力位，使用技术退出而不是机械止盈。"
    )
    risk_txt=(
        f"{risk_price:.2f}" if pd.notna(risk_price)
        else "当前无法形成可靠结构风险位，暂不扩大仓位"
    )
    oos_txt=f"{oos:+.2f}R" if pd.notna(oos) else "样本不足"
    weekly_txt=f"{weekly:.0f}" if pd.notna(weekly) else "—"
    rr_txt=f"{rr:.2f}" if pd.notna(rr) else "—"

    return {
        "action":action,
        "position_plan":position_plan,
        "entry_trigger":"；".join(entry_parts),
        "add_trigger":"；".join(add_parts),
        "reduce_trigger":"；".join(reduce_parts),
        "exit_trigger":"；".join(exit_parts),
        "risk_line":risk_txt,
        "target_zone":target_txt,
        "evidence":(
            f"技术{technical:.0f} / 买点{buy_score:.0f} / 周线{weekly_txt} / "
            f"RR {rr_txt} / 市场{market_score:.0f} / RS{rs_score:.0f} / "
            f"机会{opp:.0f} / OOS EV {oos_txt}"
        )
    }

def deterministic_report(
    code,name,df,position_state,fundamentals_ok,benchmark_df=None,
    compute_ev=True,native_weekly_df=None,ev_override=None
):
    di=add_indicators(df)
    agg_w=weekly_from_daily(df,completed_only=True)
    try:
        if native_weekly_df is not None:
            native_w=native_weekly_df.copy()
        else:
            native_w=fetch_stock_weekly(code,years=3 if not compute_ev else 5)
        native_w=confirmed_native_weekly(native_w,di["trade_date"].max()) if not native_w.empty else native_w
    except Exception:
        native_w=pd.DataFrame()
    wi=native_w if native_w is not None and not native_w.empty else agg_w
    weekly_source="原生周K" if native_w is not None and not native_w.empty else "日K聚合兜底"
    weekly_check=weekly_consistency(native_w,agg_w)

    if len(di)<60:
        raise RuntimeError("历史数据不足，无法计算指标")
    if wi is None or len(wi)<20:
        raise RuntimeError("确认周线历史不足，无法生成中长线决策")

    drow=di.iloc[-1].to_dict()
    drow["macd_prev"]=di.iloc[-2]["macd"] if len(di)>1 else np.nan
    wrow=wi.iloc[-1].to_dict()
    score,trend,momentum,weekly,confirm=numeric_score(drow,wrow)
    weekly_ok=weekly is not None and weekly>=60
    rating=grade(score,weekly_ok,100)
    stage=stage_from(score,{},weekly_ok)

    buy_score,rr,risk_price,target_price=entry_quality(drow)
    benchmark_df=benchmark_df if benchmark_df is not None else pd.DataFrame()
    mkt_score,mkt_regime=market_environment(benchmark_df) if not benchmark_df.empty else (50,"未知")
    rs_score,ex20,ex60=relative_strength(df,benchmark_df) if not benchmark_df.empty else (50,np.nan,np.nan)
    opp=opportunity_score(score,buy_score,rr,None,mkt_score,rs_score)
    liq_ok,amount20,liq_threshold=liquidity_rule(code,drow)

    ev={
        "样本":0,"胜率":np.nan,"EV_R":np.nan,"保守EV_R":np.nan,"压力EV_R":np.nan,
        "中位R":np.nan,"平均盈利R":np.nan,"平均亏损R":np.nan,"盈亏因子":np.nan,
        "平均持有":np.nan,"最大不利R":np.nan,"可信度":"未计算",
        "walk_forward":{"折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,"稳定性":"未计算"}
    }
    tier="候选观察"
    ev_reason="持仓管理模式不重复计算历史EV"
    ev_pending=False
    if ev_override is not None:
        ev=ev_override
        tier,ev_reason,_=ev_opportunity_decision(
            score,buy_score,weekly,rr,mkt_score,rs_score,opp,ev,liq_ok
        )
    elif compute_ev:
        ev,_,_=realized_trade_ev(
            df,benchmark_df,code,use_cache=True,weekly_df=native_w
        )
        tier,ev_reason,_=ev_opportunity_decision(
            score,buy_score,weekly,rr,mkt_score,rs_score,opp,ev,liq_ok
        )
    else:
        p=automatic_entry_policy(mkt_score)
        structure_watch=(
            score>=p["技术"]-4 and buy_score>=p["买点"]-4 and
            pd.notna(weekly) and weekly>=p["周线"]-4 and
            pd.notna(rr) and rr>=max(0.8,p["盈亏比"]-0.2) and
            rs_score>=p["相对强度"]-5 and opp>=p["机会"]-4 and liq_ok
        )
        if structure_watch:
            tier="候选观察"
            ev_reason="当前结构达到观察门槛；历史EV正在后台更新"
            ev_pending=True
        else:
            tier="不通过"
            ev_reason="当前结构未达到自动观察门槛；本次不阻塞等待5年EV"

    hard_bear=(
        pd.notna(drow.get("boll_slope")) and drow.get("boll_slope")<0 and
        pd.notna(drow.get("boll_mid")) and drow.get("close")<drow.get("boll_mid") and
        pd.notna(drow.get("dif")) and drow.get("dif")<0 and
        pd.notna(drow.get("dea")) and drow.get("dif")<drow.get("dea")
    )
    state,reason=state_from(score,rating,100,False,weekly_ok,position_state,fundamentals_ok,hard_bear)
    holding=position_state!="未持有"

    if not holding:
        if tier=="优先机会" and fundamentals_ok:
            state,reason="买入候选",ev_reason
        elif tier=="优先机会":
            state,reason="观察","技术与EV通过，但基本面/估值尚未独立确认"
        elif tier=="候选观察":
            state,reason="观察",ev_reason
        elif hard_bear:
            state,reason="回避","趋势与动能处于明显弱势"
        else:
            state,reason="观察",ev_reason

    mid=drow.get("boll_mid",np.nan)
    support_txt=(
        f"{risk_price:.2f}（初始风险参考） / {mid:.2f}（中轨）"
        if pd.notna(risk_price) and pd.notna(mid)
        else (f"{mid:.2f}（中轨）" if pd.notna(mid) else "未知")
    )
    resistance_txt=f"{target_price:.2f}（参考压力，不作为固定止盈）" if pd.notna(target_price) else "未知"

    boll_dir="向上" if drow.get("boll_slope",0)>0 else ("向下" if drow.get("boll_slope",0)<0 else "走平")
    pos_txt="中轨上" if pd.notna(mid) and drow.get("close")>mid else "中轨下"
    zero="零轴上" if drow.get("dif",0)>0 and drow.get("dea",0)>0 else "零轴下/附近"
    cross="金叉" if drow.get("dif",0)>drow.get("dea",0) else "死叉"
    rr_txt=f"{rr:.2f}" if pd.notna(rr) else "—"
    ev_txt=(
        f"{ev.get('EV_R'):+.2f}R" if pd.notna(ev.get("EV_R"))
        else ("后台更新中" if ev_pending else "未计算")
    )
    essence=f"{tier} · 历史净EV {ev_txt} · 技术{score:.0f} · 买点{buy_score} · RR {rr_txt} · {mkt_regime}{mkt_score}/100"

    up=[]; down=[]
    if (compute_ev or ev_override is not None) and tier!="优先机会":
        up.append("等待保守EV与压力EV转正")
    elif ev_pending:
        up.append("等待后台EV完成后再确认是否升级")
    if buy_score<65:
        up.append("买点质量继续改善")
    if pd.notna(risk_price):
        down.append(f"跌破风险位{risk_price:.2f}")
    if mkt_score<35:
        down.append("市场处于逆风区")
    if pd.notna(mid):
        down.append(f"持续运行于中轨{mid:.2f}下方")

    operation_strategy=build_operation_strategy(
        code,position_state,fundamentals_ok,score,buy_score,weekly,rr,
        mkt_score,rs_score,opp,tier,ev,
        float(drow.get("close")) if pd.notna(drow.get("close")) else np.nan,
        mid,risk_price,target_price,drow.get("atr14",np.nan)
    )

    return {
        "updated_at":datetime.now().strftime("%m-%d %H:%M"),
        "symbol":f"{name} / {display_code(code)}",
        "state":state,"rating":rating,"stage":stage,"state_reason":reason,
        "score":score,"trend":trend,"momentum":momentum,"weekly_score":weekly,
        "confirm":confirm,"confidence":100,"essence":essence,
        "support":support_txt,"resistance":resistance_txt,
        "upgrade":"；".join(up[:2]) if up else "维持当前结构",
        "downgrade":"；".join(down[:2]),"delta":None,"intraday":False,
        "opportunity_score":opp,"opportunity_label":tier,
        "buy_score":buy_score,"rr":rr,
        "market_score":mkt_score,"market_regime":mkt_regime,
        "rs_score":rs_score,"excess20":ex20,"excess60":ex60,
        "ev":ev,"ev_pending":ev_pending,"liquidity_ok":liq_ok,"amount20":amount20,
        "risk_price":risk_price,"target_price":target_price,
        "weekly_source":weekly_source,
        "weekly_crosscheck":weekly_check,
        "weekly_aggregate_score":weekly_check.get("aggregate_score",np.nan),
        "operation_strategy":operation_strategy,
        "daily":{
            "boll_mid_direction":boll_dir,"price_vs_mid":pos_txt,
            "macd_zero_zone":zero,"dif_direction":"向上" if drow.get("dif_slope",0)>0 else "向下",
            "cross":cross,
            "bar_momentum":"红柱" if drow.get("macd",0)>0 else "绿柱",
            "volume_state":f"量能分 {confirm:.0f}/100",
            "volume_trend":"—","divergence":"未做自动背离判定"
        },
        "boll_analysis":f"中轨{boll_dir}，收盘{drow.get('close',np.nan):.2f}，中轨{mid:.2f}。" if pd.notna(mid) else "",
        "macd_analysis":f"DIF {drow.get('dif',np.nan):.3f}，DEA {drow.get('dea',np.nan):.3f}，{cross}。",
        "weekly_analysis":(
            f"{weekly_source}主评分 {weekly:.0f}/100；"
            f"日K聚合校验 {weekly_check.get('aggregate_score',np.nan):.0f}/100；"
            f"一致性 {weekly_check.get('level','不可校验')}。"
            if pd.notna(weekly_check.get("aggregate_score",np.nan))
            else f"{weekly_source}主评分 {weekly:.0f}/100；聚合周K暂不可校验。"
        ),
        "resonance":f"相对强度{rs_score}/100；{benchmark_label_for_code(code)}环境{mkt_regime}{mkt_score}/100。",
        "data_source":data_source_for_code(code),"market":market_of_code(code),
        "benchmark":benchmark_label_for_code(code),"adjustment":"前复权",
        "latest_date":di.iloc[-1]["trade_date"].strftime("%Y-%m-%d"),
        "latest_close":float(di.iloc[-1]["close"]),"_df":di
    }

def persist_analysis_report(report,code,horizon,position_state):
    if not report:
        return
    rdf=report.get("_df")
    price=""
    boll_mid=""
    if isinstance(rdf,pd.DataFrame) and not rdf.empty:
        price=str(rdf.iloc[-1].get("close",""))
        boll_mid=str(rdf.iloc[-1].get("boll_mid",""))
    xsave={
        "data_quality":100,
        "daily":{"price":price,"boll_mid":boll_mid},
        "key_support":report.get("support",""),
        "key_resistance":report.get("resistance",""),
    }
    meta={
        "symbol":report.get("symbol",""),
        "market":market_of_code(code),
        "horizon":horizon,
        "position_state":position_state,
        "rating":report.get("rating",""),
        "state":report.get("state",""),
        "stage":report.get("stage",""),
        "confidence":100,
        "mode":f"{data_source_for_code(code)}自动数据",
        "weekly_used":True
    }
    metrics=(
        report.get("score"),report.get("trend"),report.get("momentum"),
        report.get("weekly_score"),report.get("confirm"),False,False
    )
    save_result(
        meta,xsave,metrics,
        json.dumps(
            {
                "source":data_source_for_code(code),
                "market":market_of_code(code),
                "operation_strategy":report.get("operation_strategy",{})
            },
            ensure_ascii=False
        )
    )

def latest_trade_date():
    end=pd.Timestamp.today().strftime("%Y-%m-%d")
    start=(pd.Timestamp.today()-pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    if int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)>0:
        try:
            rs=bs.query_trade_dates(start_date=start,end_date=end)
            if getattr(rs,"error_code","0")=="0":
                df=_rs_to_df(rs)
                if not df.empty:
                    if "is_trading_day" in df.columns:
                        df=df[df["is_trading_day"].astype(str)=="1"]
                    if not df.empty and "calendar_date" in df.columns:
                        return str(df["calendar_date"].max())
        except Exception:
            pass
    # 容灾时无需依赖BaoStock交易日历；行情接口会自然过滤非交易日。
    return end

def _retry_df_call(label,fn,retries=3,delay=1.2):
    last=None
    for attempt in range(1,int(retries)+1):
        try:
            out=fn()
            if out is not None and not out.empty:
                return out
            last=RuntimeError(f"{label}返回空数据")
        except Exception as e:
            last=e
        if attempt<int(retries):
            time.sleep(float(delay)*attempt)
    raise RuntimeError(f"{label}连续{retries}次失败：{last}")

def _normalize_a_universe(raw):
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["code","code_name"])
    df=raw.copy()
    code_candidates=[
        "code","代码","证券代码","成分券代码","品种代码","股票代码"
    ]
    name_candidates=[
        "code_name","name","名称","证券简称","成分券名称","品种名称","股票简称"
    ]
    code_col=next((x for x in code_candidates if x in df.columns),None)
    name_col=next((x for x in name_candidates if x in df.columns),None)
    if not code_col:
        return pd.DataFrame(columns=["code","code_name"])
    codes=df[code_col].astype(str).str.extract(r"(\d{6})",expand=False)
    out=pd.DataFrame({"raw_code":codes})
    out["code_name"]=df[name_col].astype(str).str.strip() if name_col else codes
    out=out[out["raw_code"].notna()].copy()
    out["code"]=out["raw_code"].map(
        lambda x: ("sh."+x) if str(x).startswith(("5","6","9")) else ("sz."+x)
    )
    out=out[out["raw_code"].astype(str).str.startswith(("0","3","6"))]
    return out[["code","code_name"]].drop_duplicates("code").reset_index(drop=True)

def _ak_all_a_universe():
    errors=[]
    getters=[
        ("A股代码表",lambda: ak.stock_info_a_code_name()),
        ("A股实时表",lambda: ak.stock_zh_a_spot_em())
    ]
    for label,getter in getters:
        try:
            out=_normalize_a_universe(getter())
            if not out.empty:
                return out
        except Exception as ex:
            errors.append(f"{label}:{ex}")
    raise RuntimeError("AKShare全A股票池失败："+"；".join(errors[-2:]))

def _ak_index_universe(index_code):
    errors=[]
    getters=[]
    if hasattr(ak,"index_stock_cons"):
        getters.append(("指数成分",lambda: ak.index_stock_cons(symbol=index_code)))
    if hasattr(ak,"index_stock_cons_csindex"):
        getters.append(("中证指数成分",lambda: ak.index_stock_cons_csindex(symbol=index_code)))
    if hasattr(ak,"index_stock_cons_weight_csindex"):
        getters.append(("中证指数权重",lambda: ak.index_stock_cons_weight_csindex(symbol=index_code)))
    for label,getter in getters:
        try:
            out=_normalize_a_universe(getter())
            if not out.empty:
                return out
        except Exception as ex:
            errors.append(f"{label}:{ex}")
    raise RuntimeError(f"AKShare指数{index_code}成分失败："+"；".join(errors[-3:]))

def fetch_universe(kind):
    if kind=="港股主板":
        hk=_retry_df_call("港股主板股票池",lambda: hk_universe_snapshot().copy(),retries=3)
        if not all(x in hk.columns for x in ["code","code_name"]):
            raise RuntimeError("港股股票池字段异常")
        return hk[["code","code_name"]].drop_duplicates("code").reset_index(drop=True)

    bs_error=None
    if int(getattr(_BAOSTOCK_SESSION_OWNER,"depth",0) or 0)>0:
        try:
            if kind=="沪深300":
                rs=bs.query_hs300_stocks()
            elif kind=="中证500":
                rs=bs.query_zz500_stocks()
            elif kind=="上证50":
                rs=bs.query_sz50_stocks()
            else:
                rs=bs.query_all_stock(day=latest_trade_date())
            if getattr(rs,"error_code","0")!="0":
                raise RuntimeError(getattr(rs,"error_msg","BaoStock返回错误"))
            df=_rs_to_df(rs)
            if not df.empty:
                out=_normalize_a_universe(df)
                if kind=="全A股（沪深）" and "tradeStatus" in df.columns:
                    active_codes=set(
                        df.loc[df["tradeStatus"].astype(str)=="1","code"].astype(str)
                    )
                    out=out[out["code"].isin(active_codes)]
                if not out.empty:
                    return out.reset_index(drop=True)
        except Exception as ex:
            bs_error=ex

    try:
        if kind=="沪深300":
            return _ak_index_universe("000300")
        if kind=="中证500":
            return _ak_index_universe("000905")
        if kind=="上证50":
            return _ak_index_universe("000016")
        return _ak_all_a_universe()
    except Exception as ak_ex:
        raise RuntimeError(
            f"{kind}股票池双源失败；BaoStock={bs_error or getattr(_BAOSTOCK_SESSION_OWNER,'last_error','未登录')}；AKShare={ak_ex}"
        )

def market_score_from_row(r):
    close = r.get("close",np.nan)
    mid = r.get("boll_mid",np.nan)
    ma60 = r.get("ma60",np.nan)
    slope = r.get("boll_slope",np.nan)
    dif = r.get("dif",np.nan)
    dea = r.get("dea",np.nan)
    ret20 = r.get("ret20",np.nan)
    ret60 = r.get("ret60",np.nan)

    s = 0
    s += 25 if pd.notna(close) and pd.notna(mid) and close > mid else 5
    s += 20 if pd.notna(slope) and slope > 0 else 5
    s += 20 if pd.notna(dif) and pd.notna(dea) and dif > 0 and dif > dea else (10 if pd.notna(dif) and pd.notna(dea) and dif > dea else 3)
    s += 20 if pd.notna(close) and pd.notna(ma60) and close > ma60 else 5
    s += 10 if pd.notna(ret20) and ret20 > 0 else 2
    s += 5 if pd.notna(ret60) and ret60 > 0 else 1
    return int(clamp(s))

def market_regime(score):
    if score >= 70:
        return "顺风"
    if score >= 50:
        return "中性"
    if score >= 35:
        return "偏弱"
    return "逆风"

def market_score_series(benchmark_df):
    b = add_indicators(benchmark_df)
    if b.empty:
        return pd.DataFrame()
    b["market_score"] = [market_score_from_row(r.to_dict()) for _,r in b.iterrows()]
    b["market_regime"] = b["market_score"].map(market_regime)
    return b

def market_environment(benchmark_df):
    b = market_score_series(benchmark_df)
    if b.empty:
        return 50, "未知"
    score = int(b.iloc[-1]["market_score"])
    return score, market_regime(score)

def relative_strength(stock_df, benchmark_df):
    s = add_indicators(stock_df)
    b = add_indicators(benchmark_df)
    if s.empty or b.empty:
        return 50, np.nan, np.nan
    sr = s.iloc[-1]
    br = b.iloc[-1]
    ex20 = (sr.get("ret20") - br.get("ret20")) if pd.notna(sr.get("ret20")) and pd.notna(br.get("ret20")) else np.nan
    ex60 = (sr.get("ret60") - br.get("ret60")) if pd.notna(sr.get("ret60")) and pd.notna(br.get("ret60")) else np.nan
    score = 50
    if pd.notna(ex20):
        score += 120*ex20
    if pd.notna(ex60):
        score += 60*ex60
    return int(clamp(score)), ex20, ex60

def confirmed_native_weekly(weekly_df,latest_daily):
    if weekly_df is None or weekly_df.empty:
        return pd.DataFrame()
    w=weekly_df.copy().sort_values("trade_date").reset_index(drop=True)
    w["trade_date"]=pd.to_datetime(w["trade_date"],errors="coerce")
    w=w.dropna(subset=["trade_date","close"])
    if w.empty:
        return w
    latest_daily=pd.Timestamp(latest_daily).normalize()
    latest_period=latest_daily.to_period("W-FRI")
    row_periods=w["trade_date"].dt.to_period("W-FRI")
    # 周一至周四若数据源返回了本周临时周K，仍视为未确认并剔除。
    if latest_daily.weekday()!=4:
        w=w[row_periods<latest_period]
    else:
        w=w[row_periods<=latest_period]
    return w.reset_index(drop=True)

def build_score_series(df,weekly_df=None,code=None):
    d=add_indicators(df)
    if d.empty:
        return pd.DataFrame()

    code=normalize_code(code or (str(d.iloc[-1].get("code","")) if "code" in d.columns else ""))
    agg_w=weekly_from_daily(df,completed_only=True)

    native_w=weekly_df
    if native_w is None:
        try:
            native_w=fetch_stock_weekly(code,years=max(3,int(np.ceil(len(d)/240))+1)) if code else pd.DataFrame()
        except Exception:
            native_w=pd.DataFrame()
    if native_w is not None and not native_w.empty:
        native_w=confirmed_native_weekly(native_w,d["trade_date"].max())

    # 原生周K为主；只有原生周K不可用时才回退到日K聚合周K。
    w=native_w if native_w is not None and not native_w.empty else agg_w
    if w is None or w.empty:
        return pd.DataFrame()
    if "boll_mid" not in w.columns:
        w=add_indicators(w)

    w2=w[["trade_date","boll_mid","boll_slope","close","dif","dea"]].copy()
    w2.columns=["w_date","w_boll_mid","w_boll_slope","w_close","w_dif","w_dea"]
    m=pd.merge_asof(
        d.sort_values("trade_date"),w2.sort_values("w_date"),
        left_on="trade_date",right_on="w_date",direction="backward"
    )

    # 聚合周K只用于交叉验证，不参与主评分。
    if agg_w is not None and not agg_w.empty:
        aw=agg_w[["trade_date","boll_mid","boll_slope","close","dif","dea"]].copy()
        aw.columns=["wa_date","wa_boll_mid","wa_boll_slope","wa_close","wa_dif","wa_dea"]
        m=pd.merge_asof(
            m.sort_values("trade_date"),aw.sort_values("wa_date"),
            left_on="trade_date",right_on="wa_date",direction="backward"
        )
    else:
        for col in ["wa_date","wa_boll_mid","wa_boll_slope","wa_close","wa_dif","wa_dea"]:
            m[col]=np.nan

    scores=[]; weekly_scores=[]; weekly_agg_scores=[]; weekly_gaps=[]
    buy_scores=[]; rr_list=[]; stops=[]; targets=[]
    for i,row in m.iterrows():
        r=row.to_dict()
        r["macd_prev"]=m.iloc[i-1]["macd"] if i>0 else np.nan
        wr=None
        if pd.notna(row.get("w_date")):
            wr={
                "boll_slope":row.get("w_boll_slope"),"close":row.get("w_close"),
                "boll_mid":row.get("w_boll_mid"),"dif":row.get("w_dif"),"dea":row.get("w_dea")
            }
        war=None
        if pd.notna(row.get("wa_date")):
            war={
                "boll_slope":row.get("wa_boll_slope"),"close":row.get("wa_close"),
                "boll_mid":row.get("wa_boll_mid"),"dif":row.get("wa_dif"),"dea":row.get("wa_dea")
            }

        metric=numeric_score(r,wr)
        agg_metric=numeric_score(r,war) if war is not None else (None,None,None,None,None)
        bp,rr,stop,target=entry_quality(r)
        ws=metric[3] if metric[3] is not None else np.nan
        was=agg_metric[3] if agg_metric[3] is not None else np.nan
        scores.append(metric[0])
        weekly_scores.append(ws)
        weekly_agg_scores.append(was)
        weekly_gaps.append(abs(float(ws)-float(was)) if pd.notna(ws) and pd.notna(was) else np.nan)
        buy_scores.append(bp); rr_list.append(rr); stops.append(stop); targets.append(target)

    m["score"]=scores
    m["weekly_score"]=weekly_scores
    m["weekly_agg_score"]=weekly_agg_scores
    m["weekly_score_gap"]=weekly_gaps
    m["weekly_source"]="原生周K" if native_w is not None and not native_w.empty else "日K聚合兜底"
    m["buy_score"]=buy_scores
    m["rr"]=rr_list
    m["stop_ref"]=stops
    m["target_ref"]=targets
    return m

def entry_quality(r):
    close = r.get("close",np.nan)
    mid = r.get("boll_mid",np.nan)
    upper = r.get("boll_up",np.nan)
    low10 = r.get("low10_prev",np.nan)
    low20 = r.get("low20_prev",np.nan)
    high20 = r.get("high20_prev",np.nan)
    high60 = r.get("high60_prev",np.nan)
    atr = r.get("atr14",np.nan)
    slope = r.get("boll_slope",np.nan)
    dif = r.get("dif",np.nan)
    dea = r.get("dea",np.nan)
    vol = r.get("vol",np.nan)
    v5 = r.get("vol_ma5",np.nan)
    v10 = r.get("vol_ma10",np.nan)

    if pd.isna(close) or close <= 0:
        return 0, np.nan, np.nan, np.nan

    score = 0
    dist_mid = np.nan

    # 价格位置：中轨附近到中轨上方3.5%优先；明显追高主动降分
    if pd.notna(mid) and mid > 0:
        dist_mid = close/mid - 1
        if 0 <= dist_mid <= 0.035:
            score += 30
        elif -0.02 <= dist_mid < 0:
            score += 22
        elif 0.035 < dist_mid <= 0.07:
            score += 18
        elif 0.07 < dist_mid <= 0.10:
            score += 10
        else:
            score += 4
    else:
        score += 10

    # 趋势
    if pd.notna(slope) and slope > 0:
        score += 20
    elif pd.notna(slope) and slope < 0:
        score += 4
    else:
        score += 10

    # 动能
    if pd.notna(dif) and pd.notna(dea):
        if dif > 0 and dea > 0 and dif > dea:
            score += 20
        elif dif > dea:
            score += 13
        else:
            score += 4
    else:
        score += 8

    # 量能
    if pd.notna(vol) and pd.notna(v5) and pd.notna(v10) and v5 > 0 and v10 > 0:
        ratio = vol/max(v5,v10)
        if 1.0 <= ratio <= 1.6:
            score += 15
        elif 0.75 <= ratio < 1.0:
            score += 11
        elif 1.6 < ratio <= 2.0:
            score += 9
        elif ratio > 2.0:
            score += 5
        else:
            score += 7
    else:
        score += 7

    # 结构位置：突破前高可以，但紧贴上轨且乖离过大时不追
    structure = 15
    overextended = False
    if pd.notna(upper) and upper > 0 and close >= upper*0.99:
        structure -= 6
        overextended = True
    if pd.notna(dist_mid) and dist_mid > 0.08:
        structure -= 6
        overextended = True
    if pd.notna(atr) and atr > 0 and pd.notna(mid) and close-mid > 2.2*atr:
        structure -= 5
        overextended = True
    score += max(0,structure)

    # 风险位：优先用短期结构低点/中轨下方ATR缓冲；目标用最近压力，突破无压力时用2ATR作统一波动目标
    support_candidates = []
    for x in [low10, low20]:
        if pd.notna(x) and x < close:
            support_candidates.append(float(x))
    if pd.notna(mid) and pd.notna(atr) and mid-0.5*atr < close:
        support_candidates.append(float(mid-0.5*atr))
    elif pd.notna(mid) and mid < close:
        support_candidates.append(float(mid))
    stop = max(support_candidates) if support_candidates else np.nan

    targets = []
    for x in [high20, high60, upper]:
        if pd.notna(x) and x > close*1.005:
            targets.append(float(x))
    target = min(targets) if targets else (float(close+2*atr) if pd.notna(atr) and atr>0 else np.nan)

    rr = np.nan
    if pd.notna(stop) and pd.notna(target) and close > stop and target > close:
        rr = (target-close)/(close-stop)

    score = int(clamp(score))
    if overextended:
        score = min(score,72)
    return score, (round(float(rr),2) if pd.notna(rr) else np.nan), stop, target

def historical_edge(df, current_score, current_buy_score, benchmark_df=None, current_market_score=None):
    m = build_score_series(df)
    horizons = (20,40,60)
    empty = {h:{"样本":0,"胜率":np.nan,"平均收益":np.nan,"中位收益":np.nan} for h in horizons}
    if m.empty or len(m) < 160:
        return empty

    if benchmark_df is not None and not benchmark_df.empty:
        bm = market_score_series(benchmark_df)[["trade_date","market_score"]].sort_values("trade_date")
        m = pd.merge_asof(
            m.sort_values("trade_date"), bm,
            on="trade_date", direction="backward"
        )

    lo, hi = max(0,current_score-6), min(100,current_score+6)
    base = m[
        (m["score"]>=lo) & (m["score"]<=hi) &
        (m["buy_score"]>=max(48,current_buy_score-12))
    ].copy()

    # 大盘环境相近时优先采用；样本不足则自动退回不加大盘约束
    if current_market_score is not None and "market_score" in base.columns:
        similar_market = base[(base["market_score"]-current_market_score).abs() <= 20]
        if len(similar_market) >= 5:
            base = similar_market

    out = {}
    for horizon in horizons:
        temp = base.copy()
        temp["fwd"] = m["close"].shift(-horizon)/m["close"] - 1
        temp = temp[temp["fwd"].notna()]
        picked, last_pos = [], -9999
        for idx in temp.index:
            pos = m.index.get_loc(idx)
            if pos-last_pos >= horizon:
                picked.append(idx)
                last_pos = pos
        s = temp.loc[picked,"fwd"] if picked else pd.Series(dtype=float)
        if s.empty:
            out[horizon] = empty[horizon]
        else:
            out[horizon] = {
                "样本":int(len(s)),
                "胜率":float((s>0).mean()),
                "平均收益":float(s.mean()),
                "中位收益":float(s.median())
            }
    return out

def opportunity_score(technical,buy_score,rr,hist=None,market_score=50,rs_score=50):
    # 机会分只描述“当前结构”，不再混入历史结果，避免重复计分与循环解释。
    rr_score=30 if pd.isna(rr) else clamp(rr/2.5*100)
    score=(
        0.30*technical+
        0.30*buy_score+
        0.15*rr_score+
        0.15*market_score+
        0.10*rs_score
    )
    if market_score<35:
        score-=6
    if buy_score<55:
        score=min(score,64)
    if pd.notna(rr) and rr<1.0:
        score=min(score,60)
    return round(float(clamp(score)),1)

def opportunity_label(opp,buy_score,rr,market_score,hist=None):
    if market_score<35:
        return "逆风观察"
    if buy_score<60:
        return "等待买点"
    if pd.notna(rr) and rr<1.2:
        return "盈亏比不足"
    if opp>=72:
        return "结构较强"
    if opp>=64:
        return "结构可观察"
    return "一般观察"

def automatic_entry_policy(market_score):
    # 固定的市场自适应结构门槛；不会因为“今天选不到股票”临时放宽。
    if market_score>=70:
        return {"技术":56,"买点":56,"周线":48,"盈亏比":1.00,"相对强度":43,"机会":63}
    if market_score>=50:
        return {"技术":58,"买点":58,"周线":50,"盈亏比":1.10,"相对强度":45,"机会":65}
    if market_score>=35:
        return {"技术":62,"买点":60,"周线":52,"盈亏比":1.25,"相对强度":48,"机会":68}
    return {"技术":66,"买点":63,"周线":55,"盈亏比":1.40,"相对强度":52,"机会":71}

def liquidity_rule(code,row):
    amount20=row.get("amount_median20",np.nan)
    threshold=20_000_000 if market_of_code(code)=="港股" else 50_000_000
    if pd.isna(amount20):
        return False,np.nan,threshold
    return bool(float(amount20)>=threshold),float(amount20),threshold

def trade_cost_profile(code):
    # 单边bps：费用 + 滑点。压力测试会整体乘2。
    if market_of_code(code)=="港股":
        return 15.0,8.0
    return 8.0,5.0

def prepare_strategy_frame(df,benchmark_df,code=None,weekly_df=None,benchmark_features=None):
    code=normalize_code(code or (str(df.iloc[-1].get("code","")) if df is not None and not df.empty and "code" in df.columns else ""))
    m=build_score_series(df,weekly_df=weekly_df,code=code)
    if m.empty:
        return m

    bm=benchmark_features if benchmark_features is not None else market_score_series(benchmark_df)
    if bm is not None and not bm.empty:
        bm2=bm[["trade_date","ret20","ret60","market_score"]].copy()
        bm2.columns=["trade_date","bm_ret20","bm_ret60","market_score"]
        m=pd.merge_asof(
            m.sort_values("trade_date"),bm2.sort_values("trade_date"),
            on="trade_date",direction="backward"
        )
    else:
        m["market_score"]=50.0
        m["bm_ret20"]=np.nan
        m["bm_ret60"]=np.nan

    # 向量化计算RS与机会分，避免5年历史逐行iterrows。
    ex20=pd.to_numeric(m.get("ret20"),errors="coerce")-pd.to_numeric(m.get("bm_ret20"),errors="coerce")
    ex60=pd.to_numeric(m.get("ret60"),errors="coerce")-pd.to_numeric(m.get("bm_ret60"),errors="coerce")
    rs=np.full(len(m),50.0,dtype=float)
    rs+=np.where(ex20.notna(),120.0*ex20.fillna(0).to_numpy(dtype=float),0.0)
    rs+=np.where(ex60.notna(),60.0*ex60.fillna(0).to_numpy(dtype=float),0.0)
    rs=np.clip(rs,0,100)
    m["rs_score"]=np.round(rs,1)

    technical=pd.to_numeric(m.get("score"),errors="coerce").fillna(0).to_numpy(dtype=float)
    buy=pd.to_numeric(m.get("buy_score"),errors="coerce").fillna(0).to_numpy(dtype=float)
    rr=pd.to_numeric(m.get("rr"),errors="coerce")
    market=pd.to_numeric(m.get("market_score"),errors="coerce").fillna(50).to_numpy(dtype=float)
    rr_score=np.where(rr.notna(),np.clip(rr.fillna(0).to_numpy(dtype=float)/2.5*100,0,100),30.0)
    opp=0.30*technical+0.30*buy+0.15*rr_score+0.15*market+0.10*rs
    opp=np.where(market<35,opp-6,opp)
    opp=np.where(buy<55,np.minimum(opp,64),opp)
    rr_arr=rr.to_numpy(dtype=float)
    opp=np.where(np.isfinite(rr_arr)&(rr_arr<1.0),np.minimum(opp,60),opp)
    m["opportunity_score"]=np.round(np.clip(opp,0,100),1)
    return m

def structural_entry_ok(row,code,relax=0):
    market_score=float(row.get("market_score",50) or 50)
    p=automatic_entry_policy(market_score)
    liq_ok,_,_=liquidity_rule(code,row)
    if not liq_ok:
        return False
    rr=row.get("rr",np.nan)
    weekly=row.get("weekly_score",np.nan)
    return bool(
        row.get("score",0)>=p["技术"]-relax and
        row.get("buy_score",0)>=p["买点"]-relax and
        pd.notna(weekly) and weekly>=p["周线"]-relax and
        pd.notna(rr) and rr>=max(0.75,p["盈亏比"]-0.05*relax) and
        row.get("rs_score",50)>=p["相对强度"]-relax and
        row.get("opportunity_score",0)>=p["机会"]-relax
    )

def holding_exit_condition(row,peak_score):
    score=float(row.get("score",0) or 0)
    weekly=row.get("weekly_score",np.nan)
    market_score=float(row.get("market_score",50) or 50)
    return bool(
        score<45 or
        (peak_score-score>=15 and score<65) or
        (pd.notna(weekly) and float(weekly)<45) or
        (market_score<25 and score<60)
    )

def simulate_structural_trades(df,benchmark_df,code,cost_mult=1.0,benchmark_features=None,weekly_df=None):
    m=prepare_strategy_frame(
        df,benchmark_df,code=code,weekly_df=weekly_df,
        benchmark_features=benchmark_features
    )
    if m.empty or len(m)<180:
        return pd.DataFrame(),m

    fee_bps,slip_bps=trade_cost_profile(code)
    friction=(fee_bps+slip_bps)*cost_mult/10000.0
    trades=[]
    i=120
    n=len(m)

    while i<n-1:
        signal=m.iloc[i]
        if not structural_entry_ok(signal,code,relax=0):
            i+=1
            continue

        entry_i=i+1
        entry_row=m.iloc[entry_i]
        raw_entry=float(entry_row["open"]) if pd.notna(entry_row.get("open")) and entry_row.get("open")>0 else float(entry_row["close"])
        signal_close=float(signal["close"])
        stop=signal.get("stop_ref",np.nan)
        atr=signal.get("atr14",np.nan)

        if pd.isna(stop) or raw_entry<=float(stop):
            i+=1
            continue
        if pd.notna(atr) and atr>0 and abs(raw_entry-signal_close)>1.5*float(atr):
            i+=1
            continue

        entry_fill=raw_entry*(1+friction)
        initial_risk=entry_fill-float(stop)
        if initial_risk<=0:
            i+=1
            continue

        peak_score=float(signal.get("score",0) or 0)
        exit_i=None
        raw_exit=None
        exit_reason=None
        j=entry_i

        while j<n:
            row=m.iloc[j]
            peak_score=max(peak_score,float(row.get("score",0) or 0))
            day_open=float(row["open"]) if pd.notna(row.get("open")) and row.get("open")>0 else float(row["close"])
            day_low=float(row["low"]) if pd.notna(row.get("low")) else day_open

            if day_low<=float(stop):
                raw_exit=day_open if day_open<float(stop) else float(stop)
                exit_i=j
                exit_reason="风险位"
                break

            if j<n-1 and holding_exit_condition(row,peak_score):
                nxt=m.iloc[j+1]
                raw_exit=float(nxt["open"]) if pd.notna(nxt.get("open")) and nxt.get("open")>0 else float(nxt["close"])
                exit_i=j+1
                exit_reason="技术退出"
                break
            j+=1

        # 尚未退出的最后一笔不用于历史EV。
        if exit_i is None:
            break

        exit_fill=raw_exit*(1-friction)
        ret=exit_fill/entry_fill-1
        r_mult=(exit_fill-entry_fill)/initial_risk
        path=m.iloc[entry_i:exit_i+1]
        min_low=float(path["low"].min()) if not path.empty else raw_entry
        mae_r=(min_low-entry_fill)/initial_risk

        trades.append({
            "signal_date":pd.Timestamp(signal["trade_date"]),
            "entry_date":pd.Timestamp(entry_row["trade_date"]),
            "exit_date":pd.Timestamp(m.iloc[exit_i]["trade_date"]),
            "signal_index":i,"entry_index":entry_i,"exit_index":exit_i,
            "raw_entry":raw_entry,"raw_exit":raw_exit,"path_min_low":min_low,
            "entry":entry_fill,"exit":exit_fill,"stop":float(stop),
            "risk":initial_risk,"return":ret,"R":r_mult,"MAE_R":mae_r,
            "holding_days":int(exit_i-entry_i+1),"exit_reason":exit_reason,
            "technical":float(signal.get("score",0)),
            "buy_score":float(signal.get("buy_score",0)),
            "weekly":float(signal.get("weekly_score",np.nan)),
            "rr":float(signal.get("rr",np.nan)),
            "market_score":float(signal.get("market_score",50)),
            "rs_score":float(signal.get("rs_score",50)),
            "opportunity":float(signal.get("opportunity_score",0))
        })
        i=exit_i+1

    return pd.DataFrame(trades),m

def summarize_ev(trades):
    empty={
        "样本":0,"胜率":np.nan,"EV_R":np.nan,"保守EV_R":np.nan,"中位R":np.nan,
        "平均盈利R":np.nan,"平均亏损R":np.nan,"盈亏因子":np.nan,"平均持有":np.nan,
        "最大不利R":np.nan,"可信度":"不足"
    }
    if trades is None or trades.empty or "R" not in trades.columns:
        return empty

    s=pd.to_numeric(trades["R"],errors="coerce").dropna()
    if s.empty:
        return empty

    n=len(s)
    wins=s[s>0]
    losses=s[s<0]
    avg=float(s.mean())
    se=float(s.std(ddof=1)/np.sqrt(n)) if n>=2 else np.nan
    lcb=avg-1.28*se if pd.notna(se) else np.nan
    pf=float(wins.sum()/abs(losses.sum())) if len(losses) and abs(losses.sum())>1e-12 else (np.inf if len(wins) else np.nan)

    confidence=(
        "高" if n>=20 and pd.notna(lcb) and lcb>0 else
        "中高" if n>=12 and pd.notna(lcb) and lcb>0 else
        "中" if n>=8 else
        "低" if n>=5 else "不足"
    )

    return {
        "样本":int(n),
        "胜率":float((s>0).mean()),
        "EV_R":avg,
        "保守EV_R":float(lcb) if pd.notna(lcb) else np.nan,
        "中位R":float(s.median()),
        "平均盈利R":float(wins.mean()) if len(wins) else np.nan,
        "平均亏损R":float(losses.mean()) if len(losses) else np.nan,
        "盈亏因子":pf,
        "平均持有":float(pd.to_numeric(trades["holding_days"],errors="coerce").mean()) if "holding_days" in trades else np.nan,
        "最大不利R":float(pd.to_numeric(trades["MAE_R"],errors="coerce").min()) if "MAE_R" in trades else np.nan,
        "可信度":confidence
    }

def purged_walk_forward_validation(trades,purge_days=30,embargo_days=10):
    if trades is None or trades.empty or len(trades)<10:
        return {
            "折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,
            "稳定性":"样本不足","purge_days":purge_days,"embargo_days":embargo_days
        }

    t=trades.copy()
    t["signal_date"]=pd.to_datetime(t["signal_date"],errors="coerce")
    t["exit_date"]=pd.to_datetime(t.get("exit_date"),errors="coerce")
    t=t.dropna(subset=["signal_date"]).sort_values("signal_date").reset_index(drop=True)
    n=len(t)
    if n<10:
        return {
            "折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,
            "稳定性":"样本不足","purge_days":purge_days,"embargo_days":embargo_days
        }

    train_min=max(6,int(n*0.45))
    remain=n-train_min
    if remain<4:
        return {
            "折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,
            "稳定性":"样本不足","purge_days":purge_days,"embargo_days":embargo_days
        }

    folds=min(4,max(2,remain//4))
    fold_size=max(1,remain//folds)
    tests=[]
    positive=0
    used=0
    gap=pd.Timedelta(days=int(purge_days)+int(embargo_days))

    for k in range(folds):
        start_i=train_min+k*fold_size
        end_i=n if k==folds-1 else min(n,start_i+fold_size)
        if start_i>=end_i:
            continue

        test=t.iloc[start_i:end_i].copy()
        test_start=pd.Timestamp(test["signal_date"].min())
        cutoff=test_start-gap

        if "exit_date" in t.columns and t["exit_date"].notna().any():
            train=t[(t.index<start_i) & (t["exit_date"]<cutoff)].copy()
        else:
            train=t[(t.index<start_i) & (t["signal_date"]<cutoff)].copy()

        if len(train)<5 or test.empty:
            continue

        train_ev=summarize_ev(train)
        test_ev=summarize_ev(test)
        if pd.notna(train_ev.get("EV_R")) and train_ev["EV_R"]>0:
            tests.append(test)
            used+=1
            if pd.notna(test_ev.get("EV_R")) and test_ev["EV_R"]>0:
                positive+=1

    if not tests:
        return {
            "折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,
            "稳定性":"训练段EV非正或净化后样本不足",
            "purge_days":purge_days,"embargo_days":embargo_days
        }

    oos=pd.concat(tests,ignore_index=True)
    oe=summarize_ev(oos)
    stability=(
        "稳定" if used>=2 and positive==used and pd.notna(oe.get("EV_R")) and oe["EV_R"]>0
        else ("一般" if positive>=max(1,(used+1)//2) else "不稳定")
    )
    return {
        "折数":used,"正EV折数":positive,
        "OOS_EV_R":oe.get("EV_R"),"OOS胜率":oe.get("胜率"),
        "稳定性":stability,"purge_days":purge_days,"embargo_days":embargo_days
    }

def walk_forward_validation(trades):
    # 保留旧函数名，内部升级为Purged Walk-Forward + Embargo。
    return purged_walk_forward_validation(trades,purge_days=30,embargo_days=10)

def bootstrap_ev_interval(trades,n_boot=600):
    if trades is None or trades.empty or len(trades)<8:
        return {
            "样本":0,"P(EV>0)":np.nan,"EV_P05":np.nan,
            "EV_P50":np.nan,"EV_P95":np.nan
        }

    t=trades.copy()
    t["R"]=pd.to_numeric(t["R"] if "R" in t.columns else t.get("r_multiple"),errors="coerce")
    t["signal_date"]=pd.to_datetime(t["signal_date"],errors="coerce")
    t=t.dropna(subset=["R","signal_date"])
    if len(t)<8:
        return {
            "样本":int(len(t)),"P(EV>0)":np.nan,"EV_P05":np.nan,
            "EV_P50":np.nan,"EV_P95":np.nan
        }

    # 月度块Bootstrap：保留同一月份内横截面相关性，比逐笔独立重采样更保守。
    t["month"]=t["signal_date"].dt.to_period("M").astype(str)
    g=t.groupby("month")["R"].agg(["sum","count"]).reset_index(drop=True)
    if len(g)<4:
        arr=t["R"].to_numpy(dtype=float)
        rng=np.random.default_rng(42)
        means=np.array([
            float(np.mean(rng.choice(arr,size=len(arr),replace=True)))
            for _ in range(int(n_boot))
        ])
    else:
        sums=g["sum"].to_numpy(dtype=float)
        counts=g["count"].to_numpy(dtype=float)
        rng=np.random.default_rng(42)
        means=[]
        m=len(g)
        for _ in range(int(n_boot)):
            idx=rng.integers(0,m,size=m)
            denom=float(counts[idx].sum())
            means.append(float(sums[idx].sum()/denom) if denom>0 else np.nan)
        means=np.asarray(means,dtype=float)

    means=means[np.isfinite(means)]
    if len(means)==0:
        return {
            "样本":int(len(t)),"P(EV>0)":np.nan,"EV_P05":np.nan,
            "EV_P50":np.nan,"EV_P95":np.nan
        }
    return {
        "样本":int(len(t)),
        "P(EV>0)":float((means>0).mean()),
        "EV_P05":float(np.quantile(means,0.05)),
        "EV_P50":float(np.quantile(means,0.50)),
        "EV_P95":float(np.quantile(means,0.95))
    }

def attach_walkforward_pred_ev(trades,min_history=20,embargo_days=10):
    if trades is None or trades.empty:
        return pd.DataFrame()
    t=trades.copy()
    t["signal_date"]=pd.to_datetime(t["signal_date"],errors="coerce")
    t["exit_date"]=pd.to_datetime(t["exit_date"],errors="coerce")
    rcol="R" if "R" in t.columns else "r_multiple"
    t["_R"]=pd.to_numeric(t[rcol],errors="coerce")
    t["_opp"]=pd.to_numeric(
        t["opportunity"] if "opportunity" in t.columns else t.get("opportunity_score"),
        errors="coerce"
    ).fillna(50)
    t=t.dropna(subset=["signal_date","_R"]).sort_values("signal_date").reset_index(drop=True)
    if t.empty:
        return t

    t["_band"]=(t["_opp"]//10*10).clip(0,90).astype(int)
    completed=t.dropna(subset=["exit_date"]).sort_values("exit_date").reset_index()
    ptr=0
    global_r=[]
    subgroup={}
    preds=[]
    hist_ns=[]
    cutoff_delta=pd.Timedelta(days=int(embargo_days))

    for _,row in t.iterrows():
        cutoff=row["signal_date"]-cutoff_delta
        while ptr<len(completed) and completed.iloc[ptr]["exit_date"]<cutoff:
            cr=completed.iloc[ptr]
            rv=float(cr["_R"])
            global_r.append(rv)
            key=(str(cr.get("market","")),int(cr["_band"]))
            subgroup.setdefault(key,[]).append(rv)
            ptr+=1

        n=len(global_r)
        hist_ns.append(n)
        if n<int(min_history):
            preds.append(np.nan)
            continue

        global_mean=float(np.mean(global_r))
        key=(str(row.get("market","")),int(row["_band"]))
        sub=subgroup.get(key,[])
        # 经验贝叶斯式收缩：局部样本少时向全局均值收缩。
        k=12.0
        pred=(
            (len(sub)*float(np.mean(sub))+k*global_mean)/(len(sub)+k)
            if len(sub)>0 else global_mean
        )
        preds.append(float(pred))

    t["pred_ev_r"]=preds
    t["pred_ev_history_n"]=hist_ns
    return t

def ev_calibration_table(trades):
    t=attach_walkforward_pred_ev(trades,min_history=20,embargo_days=10)
    if t.empty or t["pred_ev_r"].notna().sum()<15:
        return pd.DataFrame()

    v=t.dropna(subset=["pred_ev_r","_R"]).copy()
    try:
        q=min(5,max(2,int(len(v)//12)))
        v["EV分组"]=pd.qcut(v["pred_ev_r"],q=q,duplicates="drop")
    except Exception:
        return pd.DataFrame()

    rows=[]
    for grp,g in v.groupby("EV分组",observed=True):
        pred=float(g["pred_ev_r"].mean())
        actual=float(g["_R"].mean())
        rows.append({
            "预测EV区间":str(grp),
            "样本":int(len(g)),
            "平均预测EV(R)":pred,
            "实际EV(R)":actual,
            "实际胜率":float((g["_R"]>0).mean()),
            "校准误差(R)":actual-pred
        })
    return pd.DataFrame(rows)

def reprice_trades_for_cost(trades,code,cost_mult=2.0):
    if trades is None or trades.empty:
        return pd.DataFrame()
    fee_bps,slip_bps=trade_cost_profile(code)
    friction=(fee_bps+slip_bps)*cost_mult/10000.0
    out=trades.copy()
    raw_entry=pd.to_numeric(out["raw_entry"],errors="coerce")
    raw_exit=pd.to_numeric(out["raw_exit"],errors="coerce")
    stop=pd.to_numeric(out["stop"],errors="coerce")
    min_low=pd.to_numeric(out["path_min_low"],errors="coerce")
    entry=raw_entry*(1+friction)
    exitp=raw_exit*(1-friction)
    risk=entry-stop
    valid=risk>0
    out["entry"]=entry
    out["exit"]=exitp
    out["risk"]=risk
    out["return"]=exitp/entry-1
    out["R"]=np.where(valid,(exitp-entry)/risk,np.nan)
    out["MAE_R"]=np.where(valid,(min_low-entry)/risk,np.nan)
    return out

def _ev_json_safe(v):
    if isinstance(v,dict):
        return {k:_ev_json_safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):
        return [_ev_json_safe(x) for x in v]
    if isinstance(v,np.generic):
        v=v.item()
    if isinstance(v,float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v

def _ev_cache_key(df,benchmark_df,code):
    if df is None or df.empty:
        return None
    stock_date=pd.Timestamp(df["trade_date"].max()).strftime("%Y-%m-%d")
    benchmark_date=(
        pd.Timestamp(benchmark_df["trade_date"].max()).strftime("%Y-%m-%d")
        if benchmark_df is not None and not benchmark_df.empty else "none"
    )
    return normalize_code(code),stock_date,benchmark_date,RULE_VERSION

def get_cached_ev(df,benchmark_df,code):
    key=_ev_cache_key(df,benchmark_df,code)
    if key is None:
        return None
    conn=sqlite3.connect(DB_PATH)
    row=conn.execute(
        """SELECT payload FROM ev_cache
           WHERE code=? AND stock_date=? AND benchmark_date=? AND rule_version=?""",
        key
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None

def get_recent_cached_ev(code,max_age_days=7):
    code=normalize_code(code)
    cutoff=(datetime.now()-pd.Timedelta(days=int(max_age_days))).strftime("%Y-%m-%d %H:%M:%S")
    conn=sqlite3.connect(DB_PATH)
    row=conn.execute(
        """SELECT payload,updated_at,stock_date,benchmark_date
           FROM ev_cache
           WHERE code=? AND rule_version=? AND updated_at>=?
           ORDER BY updated_at DESC LIMIT 1""",
        (code,RULE_VERSION,cutoff)
    ).fetchone()
    conn.close()
    if not row:
        return None,None
    try:
        payload=json.loads(row[0])
        age=max(0.0,(pd.Timestamp.now()-pd.Timestamp(row[1])).total_seconds()/86400.0)
        payload["_cache_stock_date"]=row[2]
        payload["_cache_benchmark_date"]=row[3]
        return payload,age
    except Exception:
        return None,None

def save_cached_ev(df,benchmark_df,code,ev):
    key=_ev_cache_key(df,benchmark_df,code)
    if key is None:
        return
    payload=json.dumps(_ev_json_safe(ev),ensure_ascii=False,separators=(",",":"))
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT OR REPLACE INTO ev_cache(
           code,stock_date,benchmark_date,rule_version,payload,updated_at
        ) VALUES(?,?,?,?,?,?)""",
        (*key,payload,datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def realized_trade_ev(df,benchmark_df,code,use_cache=True,benchmark_features=None,weekly_df=None):
    if use_cache:
        cached=get_cached_ev(df,benchmark_df,code)
        if cached is not None:
            return cached,pd.DataFrame(),True

    trades,_=simulate_structural_trades(
        df,benchmark_df,code,cost_mult=1.0,
        benchmark_features=benchmark_features,weekly_df=weekly_df
    )
    stress=reprice_trades_for_cost(trades,code,cost_mult=2.0)
    base=summarize_ev(trades)
    stress_s=summarize_ev(stress)
    base["压力EV_R"]=stress_s.get("EV_R",np.nan)
    base["walk_forward"]=walk_forward_validation(trades)

    if use_cache:
        save_cached_ev(df,benchmark_df,code,base)
    return base,trades,False

def _analysis_ev_worker(code):
    code=normalize_code(code)
    try:
        cached,_=get_recent_cached_ev(code,max_age_days=7)
        if cached is not None:
            return
        if ifind_configured():
            try:
                prefetch_ifind_analysis_bundle(code,daily_years=5,weekly_years=5)
            except Exception:
                pass

        bs_open=False
        if not ifind_configured():
            try:
                bs_open=bool(bs_login(retries=1,strict=False))
            except Exception:
                bs_open=False

        df=fetch_stock_daily(code,years=5)
        benchmark=fetch_benchmark_for_code(code,years=5)
        try:
            weekly=fetch_stock_weekly(code,years=5)
        except Exception:
            weekly=None
        bench_features=market_score_series(benchmark) if benchmark is not None and not benchmark.empty else None
        realized_trade_ev(
            df,benchmark,code,use_cache=True,
            benchmark_features=bench_features,weekly_df=weekly
        )
    except Exception as ex:
        print("ANALYSIS_EV_BACKGROUND_ERROR",code,ex)
    finally:
        try:
            if 'bs_open' in locals() and bs_open:
                bs_logout_safe()
        except Exception:
            pass
        with _ANALYSIS_EV_LOCK:
            _ANALYSIS_EV_THREADS.pop(code,None)

def start_analysis_ev_background(code):
    code=normalize_code(code)
    if not code:
        return False
    cached,_=get_recent_cached_ev(code,max_age_days=7)
    if cached is not None:
        return False
    with _ANALYSIS_EV_LOCK:
        t=_ANALYSIS_EV_THREADS.get(code)
        if t is not None and t.is_alive():
            return True
        t=threading.Thread(
            target=_analysis_ev_worker,args=(code,),
            daemon=True,name=f"analysis-ev-{display_code(code)}"
        )
        _ANALYSIS_EV_THREADS[code]=t
        t.start()
    return True

def analysis_ev_running(code):
    code=normalize_code(code)
    with _ANALYSIS_EV_LOCK:
        t=_ANALYSIS_EV_THREADS.get(code)
        return bool(t is not None and t.is_alive())

def ev_opportunity_decision(technical,buy_score,weekly,rr,market_score,rs_score,opp,ev,liq_ok):
    p=automatic_entry_policy(market_score)
    if not liq_ok:
        return "不通过","20日中位成交额不足流动性门槛",p

    base_pass=(
        technical>=p["技术"] and buy_score>=p["买点"] and
        pd.notna(weekly) and weekly>=p["周线"] and
        pd.notna(rr) and rr>=p["盈亏比"] and
        rs_score>=p["相对强度"] and opp>=p["机会"]
    )
    watch_pass=(
        technical>=p["技术"]-4 and buy_score>=p["买点"]-4 and
        pd.notna(weekly) and weekly>=p["周线"]-4 and
        pd.notna(rr) and rr>=max(0.8,p["盈亏比"]-0.2) and
        rs_score>=p["相对强度"]-5 and opp>=p["机会"]-4
    )

    n=int(ev.get("样本",0) or 0)
    mean_ev=ev.get("EV_R",np.nan)
    lcb=ev.get("保守EV_R",np.nan)
    stress=ev.get("压力EV_R",np.nan)
    wf=ev.get("walk_forward") or {}
    oos_ev=wf.get("OOS_EV_R",np.nan)

    if base_pass and n>=8 and pd.notna(mean_ev) and mean_ev>0 and pd.notna(lcb) and lcb>0 and pd.notna(stress) and stress>0:
        if wf.get("折数",0)>=1 and pd.notna(oos_ev) and oos_ev<=0:
            return "候选观察","历史EV为正，但时间外验证尚未确认",p
        return "优先机会","真实交易EV、保守EV和2倍成本压力EV均为正",p

    if watch_pass:
        if n>=5 and pd.notna(mean_ev) and mean_ev>0 and (pd.isna(stress) or stress>-0.05):
            return "候选观察","历史真实交易EV为正，但样本/置信下界尚不足",p
        if n<5 and technical>=p["技术"]+3 and buy_score>=p["买点"]+3 and pd.notna(rr) and rr>=p["盈亏比"]+0.2:
            return "候选观察","当前结构强，但真实交易EV样本不足",p

    if n>=5 and pd.notna(mean_ev) and mean_ev<=0:
        return "不通过","历史真实交易EV≤0",p
    return "不通过","结构或EV证据不足",p

def save_forward_candidates(df):
    if df is None or df.empty:
        return
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn=sqlite3.connect(DB_PATH)
    for _,r in df.iterrows():
        try:
            code=normalize_code(str(r.get("代码","")).strip())
            signal_date=str(r.get("信号日") or pd.Timestamp.today().strftime("%Y-%m-%d"))
            conn.execute("""
                INSERT INTO forward_signals(
                  code,name,market,signal_date,price,tier,technical_score,buy_score,weekly_score,
                  rr,market_score,rs_score,ev_r,ev_lcb_r,stress_ev_r,ev_samples,risk_price,
                  rule_version,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code,signal_date) DO UPDATE SET
                  tier=excluded.tier,technical_score=excluded.technical_score,
                  buy_score=excluded.buy_score,weekly_score=excluded.weekly_score,
                  rr=excluded.rr,market_score=excluded.market_score,rs_score=excluded.rs_score,
                  ev_r=excluded.ev_r,ev_lcb_r=excluded.ev_lcb_r,
                  stress_ev_r=excluded.stress_ev_r,ev_samples=excluded.ev_samples,
                  risk_price=excluded.risk_price,updated_at=excluded.updated_at
            """,(
                code,str(r.get("名称","")),str(r.get("市场","")),signal_date,
                float(r.get("收盘")) if pd.notna(r.get("收盘")) else None,
                str(r.get("机会状态","")),
                float(r.get("技术分/100")) if pd.notna(r.get("技术分/100")) else None,
                float(r.get("买点分/100")) if pd.notna(r.get("买点分/100")) else None,
                float(r.get("周线/100")) if pd.notna(r.get("周线/100")) else None,
                float(r.get("盈亏比")) if pd.notna(r.get("盈亏比")) else None,
                float(r.get("_market_score")) if pd.notna(r.get("_market_score")) else None,
                float(r.get("相对强度/100")) if pd.notna(r.get("相对强度/100")) else None,
                float(r.get("历史净EV(R)")) if pd.notna(r.get("历史净EV(R)")) else None,
                float(r.get("保守EV(R)")) if pd.notna(r.get("保守EV(R)")) else None,
                float(r.get("2倍成本EV(R)")) if pd.notna(r.get("2倍成本EV(R)")) else None,
                int(r.get("EV样本",0) or 0),
                float(r.get("风险位")) if pd.notna(r.get("风险位")) else None,
                RULE_VERSION,"tracking",now,now
            ))
        except Exception:
            continue
    conn.commit()
    conn.close()
    sync_shared_light_safe(force=True)

def screen_codes(codes,name_map=None,benchmark_df=None,progress_callback=None):
    rows=[]
    name_map=name_map or {}
    benchmark_df=benchmark_df if benchmark_df is not None else pd.DataFrame()
    benchmark_features=market_score_series(benchmark_df) if not benchmark_df.empty else pd.DataFrame()
    if benchmark_features is not None and not benchmark_features.empty:
        mkt_score=int(benchmark_features.iloc[-1]["market_score"])
        mkt_regime=market_regime(mkt_score)
    else:
        mkt_score,mkt_regime=(50,"未知")
    policy=automatic_entry_policy(mkt_score)
    stats={
        "扫描":0,"快速初筛通过":0,"优先机会":0,"候选观察":0,
        "EV阶段":0,"EV缓存命中":0,"流动性不足":0,"周线低一致性":0,"数据异常":0
    }
    total_codes=len(codes)

    if ifind_configured() and total_codes:
        try:
            pf=prefetch_ifind_daily(codes,years=1)
            stats["iFinD批量预取"]=int(pf.get("saved",0) or 0)
            stats["iFinD预取异常"]=len(pf.get("errors",[]) or [])
        except Exception:
            stats["iFinD批量预取"]=0
            stats["iFinD预取异常"]=1

    def tick(i,code,name,stage):
        if progress_callback is not None:
            try:
                progress_callback(i,total_codes,code,name,stage,len(rows),stats.copy())
            except Exception:
                pass

    for i,code in enumerate(codes,start=1):
        name=name_map.get(code) or display_code(code)
        try:
            tick(i-1,code,name,"读取行情")
            d=fetch_stock_daily(code,years=1)
            stats["扫描"]+=1
            if len(d)<150:
                tick(i,code,name,"历史不足，跳过")
                continue

            name=name_map.get(code) or display_code(code)
            di=add_indicators(d)
            agg_w=weekly_from_daily(d,completed_only=True)
            if agg_w is None or agg_w.empty:
                tick(i,code,name,"聚合周线不足，跳过")
                continue

            lr=di.iloc[-1].to_dict()
            lr["macd_prev"]=di.iloc[-2]["macd"] if len(di)>1 else np.nan
            agg_wr=agg_w.iloc[-1].to_dict()
            agg_technical,agg_trend,agg_momentum,agg_weekly,agg_confirm=numeric_score(lr,agg_wr)
            buy_score,rr,stop,target=entry_quality(lr)
            liq_ok,amount20,liq_threshold=liquidity_rule(code,lr)
            if not liq_ok:
                stats["流动性不足"]+=1
                tick(i,code,name,"流动性不足")
                continue

            rs_score,ex20,ex60=relative_strength(d,benchmark_df) if not benchmark_df.empty else (50,np.nan,np.nan)
            agg_opp=opportunity_score(agg_technical,buy_score,rr,None,mkt_score,rs_score)

            # 第一层只用已在内存中的日K+聚合周K做“宽松预筛”。
            # 原生周K仍是最终周线依据，但只为有可能入选的股票请求，避免全市场逐只额外网络请求。
            coarse_pass=(
                agg_weekly is not None and pd.notna(rr) and
                agg_technical>=policy["技术"]-5 and
                buy_score>=policy["买点"]-4 and
                agg_weekly>=policy["周线"]-6 and
                rr>=max(0.75,policy["盈亏比"]-0.25) and
                rs_score>=policy["相对强度"]-6 and
                agg_opp>=policy["机会"]-5
            )
            if not coarse_pass:
                tick(i,code,name,"快速预筛未通过")
                continue

            try:
                native_w=fetch_stock_weekly(code,years=2)
                native_w=confirmed_native_weekly(native_w,di["trade_date"].max()) if not native_w.empty else native_w
            except Exception:
                native_w=pd.DataFrame()

            wi=native_w if native_w is not None and not native_w.empty else agg_w
            weekly_source="原生周K" if native_w is not None and not native_w.empty else "日K聚合兜底"
            weekly_check=weekly_consistency(native_w,agg_w)
            if weekly_check.get("level")=="低":
                stats["周线低一致性"]+=1

            wr=wi.iloc[-1].to_dict()
            technical,trend,momentum,weekly,confirm=numeric_score(lr,wr)
            opp=opportunity_score(technical,buy_score,rr,None,mkt_score,rs_score)

            # 第二层使用“原生周K为主”的最终结构门槛。
            quick_pass=(
                weekly is not None and pd.notna(rr) and
                technical>=policy["技术"]-4 and
                buy_score>=policy["买点"]-4 and
                weekly>=policy["周线"]-4 and
                rr>=max(0.80,policy["盈亏比"]-0.20) and
                rs_score>=policy["相对强度"]-5 and
                opp>=policy["机会"]-4
            )
            if not quick_pass:
                tick(i,code,name,"原生周K确认后未通过")
                continue

            stats["快速初筛通过"]+=1
            stats["EV阶段"]+=1
            tick(i-1,code,name,"计算5年真实交易EV")

            # EV是慢变量：日常选股优先复用最近7天同规则EV。
            # 当前技术结构仍使用当天数据；只有EV缓存缺失/过期才重跑5年历史。
            ev,ev_cache_age=get_recent_cached_ev(code,max_age_days=7)
            if ev is not None:
                trades=pd.DataFrame()
                cache_hit=True
                stats["EV缓存命中"]+=1
            else:
                hist_df=fetch_stock_daily(code,years=5)
                ev,trades,cache_hit=realized_trade_ev(
                    hist_df,benchmark_df,code,use_cache=True,
                    benchmark_features=benchmark_features
                )
                ev_cache_age=0.0
                if cache_hit:
                    stats["EV缓存命中"]+=1
            tier,reason,policy_used=ev_opportunity_decision(
                technical,buy_score,weekly,rr,mkt_score,rs_score,opp,ev,liq_ok
            )
            if tier=="不通过":
                tick(i,code,name,f"未通过：{reason}")
                continue

            stats[tier]+=1
            wf=ev.get("walk_forward") or {}
            pf=ev.get("盈亏因子")
            rows.append({
                "市场":market_of_code(code),"代码":display_code(code),"名称":name,
                "机会状态":tier,"判定说明":reason,
                "历史净EV(R)":round(float(ev["EV_R"]),2) if pd.notna(ev.get("EV_R")) else np.nan,
                "保守EV(R)":round(float(ev["保守EV_R"]),2) if pd.notna(ev.get("保守EV_R")) else np.nan,
                "2倍成本EV(R)":round(float(ev["压力EV_R"]),2) if pd.notna(ev.get("压力EV_R")) else np.nan,
                "EV可信度":ev.get("可信度","不足"),"EV样本":ev.get("样本",0),
                "EV缓存年龄(天)":round(float(ev_cache_age),1) if ev_cache_age is not None else np.nan,
                "交易胜率":f"{ev.get('胜率'):.0%}" if pd.notna(ev.get("胜率")) else "—",
                "平均盈利R":round(float(ev["平均盈利R"]),2) if pd.notna(ev.get("平均盈利R")) else np.nan,
                "平均亏损R":round(float(ev["平均亏损R"]),2) if pd.notna(ev.get("平均亏损R")) else np.nan,
                "盈亏因子":round(float(pf),2) if pd.notna(pf) and np.isfinite(pf) else ("∞" if pf==np.inf else np.nan),
                "OOS EV(R)":round(float(wf.get("OOS_EV_R")),2) if pd.notna(wf.get("OOS_EV_R")) else np.nan,
                "OOS稳定性":wf.get("稳定性","样本不足"),
                "机会分/100":opp,"技术分/100":technical,"买点分/100":buy_score,
                "周线/100":weekly,
                "聚合周线/100":(
                    round(float(weekly_check.get("aggregate_score")),1)
                    if pd.notna(weekly_check.get("aggregate_score",np.nan)) else np.nan
                ),
                "周线一致性":weekly_check.get("level","不可校验"),
                "周线来源":weekly_source,
                "盈亏比":rr,
                "大盘":f"{mkt_regime} {mkt_score}/100","_market_score":mkt_score,
                "相对强度/100":rs_score,
                "20日超额":f"{ex20:.1%}" if pd.notna(ex20) else "—",
                "60日超额":f"{ex60:.1%}" if pd.notna(ex60) else "—",
                "20日中位成交额":round(float(amount20)/1e6,1) if pd.notna(amount20) else np.nan,
                "趋势/100":trend,"动能/100":momentum,"量能/100":confirm,
                "收盘":round(float(lr["close"]),2),
                "风险位":round(float(stop),2) if pd.notna(stop) else np.nan,
                "参考压力":round(float(target),2) if pd.notna(target) else np.nan,
                "信号日":pd.Timestamp(di.iloc[-1]["trade_date"]).strftime("%Y-%m-%d"),
                "系统规则":(
                    f"技≥{policy_used['技术']} / 买≥{policy_used['买点']} / "
                    f"周≥{policy_used['周线']} / RR≥{policy_used['盈亏比']:.2f} / "
                    f"RS≥{policy_used['相对强度']} / 机会≥{policy_used['机会']}"
                )
            })
            tick(i,code,name,f"发现{tier}")
        except Exception:
            stats["数据异常"]+=1
            tick(i,code,name,"数据异常，跳过")
            continue

    if not rows:
        return pd.DataFrame(),stats

    out=pd.DataFrame(rows)
    tier_order={"优先机会":0,"候选观察":1}
    out["_tier"]=out["机会状态"].map(tier_order).fillna(9)
    out["_evsort"]=pd.to_numeric(out["保守EV(R)"],errors="coerce").fillna(-999)
    out=out.sort_values(
        ["_tier","_evsort","历史净EV(R)","技术分/100"],
        ascending=[True,False,False,False]
    ).drop(columns=["_tier","_evsort"]).reset_index(drop=True)
    save_forward_candidates(out)
    return out,stats

def _scan_json_value(v):
    if isinstance(v,np.generic):
        v=v.item()
    if isinstance(v,(pd.Timestamp,datetime)):
        return pd.Timestamp(v).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v,float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v

def _save_screener_rows(job_id,df):
    if df is None or df.empty:
        return
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn=sqlite3.connect(DB_PATH)
    rows=[]
    for _,r in df.iterrows():
        payload={k:_scan_json_value(v) for k,v in r.to_dict().items()}
        code=str(payload.get("代码") or "")
        if not code:
            continue
        rows.append((job_id,code,json.dumps(payload,ensure_ascii=False),now))
    if rows:
        conn.executemany(
            """INSERT INTO screener_job_results(job_id,code,payload,updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(job_id,code) DO UPDATE SET
                 payload=excluded.payload,updated_at=excluded.updated_at""",
            rows
        )
    conn.commit(); conn.close()

def load_screener_job(job_id=None):
    conn=sqlite3.connect(DB_PATH)
    if job_id:
        df=pd.read_sql_query(
            "SELECT * FROM screener_jobs WHERE job_id=?",
            conn,params=(job_id,)
        )
    else:
        df=pd.read_sql_query(
            "SELECT * FROM screener_jobs ORDER BY created_at DESC LIMIT 1",
            conn
        )
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None

def load_screener_job_results(job_id):
    if not job_id:
        return pd.DataFrame()
    conn=sqlite3.connect(DB_PATH)
    rows=conn.execute(
        "SELECT payload FROM screener_job_results WHERE job_id=?",
        (job_id,)
    ).fetchall()
    conn.close()
    data=[]
    for (payload,) in rows:
        try:
            data.append(json.loads(payload))
        except Exception:
            pass
    if not data:
        return pd.DataFrame()
    out=pd.DataFrame(data)
    if "机会状态" in out.columns:
        order={"优先机会":0,"候选观察":1}
        out["_tier"]=out["机会状态"].map(order).fillna(9)
        out["_evsort"]=pd.to_numeric(out.get("保守EV(R)"),errors="coerce").fillna(-999)
        sort_cols=[x for x in ["_tier","_evsort","历史净EV(R)","技术分/100"] if x in out.columns]
        asc=[True,False,False,False][:len(sort_cols)]
        out=out.sort_values(sort_cols,ascending=asc).drop(columns=["_tier","_evsort"],errors="ignore")
    return out.reset_index(drop=True)

def create_screener_job(
    universe="中证500",exclude_st=True,batch_size=100,
    trade_date=None,job_type="manual"
):
    trade_date=trade_date or datetime.now().strftime("%Y-%m-%d")
    job_type="scheduled" if str(job_type)=="scheduled" else "manual"
    prefix="AUTO" if job_type=="scheduled" else "MAN"
    job_id=f"{prefix}_SCAN_"+datetime.now().strftime("%Y%m%d_%H%M%S")
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO screener_jobs(
           job_id,job_type,trade_date,universe,exclude_st,batch_size,status,cursor,total,
           created_at,updated_at
        ) VALUES(?,?,?,?,?,?,'queued',0,0,?,?)""",
        (
            job_id,job_type,trade_date,universe,1 if exclude_st else 0,
            int(batch_size),now,now
        )
    )
    conn.commit(); conn.close()
    return job_id

def latest_screener_job(job_type=None):
    conn=sqlite3.connect(DB_PATH)
    if job_type:
        df=pd.read_sql_query(
            """SELECT * FROM screener_jobs
               WHERE job_type=?
               ORDER BY created_at DESC LIMIT 1""",
            conn,params=(job_type,)
        )
    else:
        df=pd.read_sql_query(
            """SELECT * FROM screener_jobs
               ORDER BY created_at DESC LIMIT 1""",
            conn
        )
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None

def active_screener_job(job_type=None):
    conn=sqlite3.connect(DB_PATH)
    if job_type:
        row=conn.execute(
            """SELECT job_id,status FROM screener_jobs
               WHERE job_type=? AND status IN ('queued','running')
               ORDER BY created_at DESC LIMIT 1""",
            (job_type,)
        ).fetchone()
    else:
        row=conn.execute(
            """SELECT job_id,status,job_type FROM screener_jobs
               WHERE status IN ('queued','running')
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
    conn.close()
    return row

def repair_stale_screener_jobs():
    # Streamlit/Render进程重启后，数据库可能仍写着running，但线程已经不存在。
    # 这种任务改成paused，避免“明明完成/已中断却永远挡住下一次扫描”。
    conn=sqlite3.connect(DB_PATH)
    rows=conn.execute(
        """SELECT job_id FROM screener_jobs
           WHERE status='running'"""
    ).fetchall()
    conn.close()
    for (job_id,) in rows:
        with _SCREENER_THREADS_LOCK:
            t=_SCREENER_THREADS.get(str(job_id))
            alive=bool(t is not None and t.is_alive())
        if not alive:
            _update_screener_job(
                str(job_id),status="paused",
                error="服务重启或后台线程已结束，任务已保留断点。"
            )

def pause_scheduled_for_manual():
    conn=sqlite3.connect(DB_PATH)
    rows=conn.execute(
        """SELECT job_id FROM screener_jobs
           WHERE job_type='scheduled' AND status IN ('queued','running')"""
    ).fetchall()
    conn.close()
    for (job_id,) in rows:
        _update_screener_job(str(job_id),status="paused_manual",error=None)

def resume_scheduled_after_manual():
    if active_screener_job("manual"):
        return None
    conn=sqlite3.connect(DB_PATH)
    row=conn.execute(
        """SELECT job_id FROM screener_jobs
           WHERE job_type='scheduled' AND status='paused_manual'
           ORDER BY created_at DESC LIMIT 1"""
    ).fetchone()
    conn.close()
    if not row:
        return None
    job_id=str(row[0])
    _update_screener_job(job_id,status="queued",error=None)
    start_screener_job_background(job_id)
    return job_id

def _update_screener_job(job_id,**kwargs):
    if not kwargs:
        return
    kwargs["updated_at"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols=list(kwargs.keys())
    sql="UPDATE screener_jobs SET "+",".join([f"{x}=?" for x in cols])+" WHERE job_id=?"
    vals=[kwargs[x] for x in cols]+[job_id]
    conn=sqlite3.connect(DB_PATH)
    conn.execute(sql,vals)
    conn.commit(); conn.close()

def _background_screener_worker(job_id):
    job=load_screener_job(job_id)
    if not job:
        return
    job_type=str(job.get("job_type") or "manual")
    try:
        _update_screener_job(job_id,status="running",error=None)
        universe=str(job["universe"])
        exclude_st=bool(int(job.get("exclude_st",1) or 0))
        outer_batch=min(50,max(20,int(job.get("batch_size",50) or 50)))
        micro_batch=10

        use_bs_session=not ifind_configured()
        if use_bs_session:
            bs_login()
        try:
            if universe=="港股主板":
                benchmark_df=_retry_df_call(
                    "恒生指数",lambda: fetch_hk_benchmark_daily(years=5),retries=3
                )
                benchmark_name="恒生指数"
            else:
                benchmark_df=_retry_df_call(
                    "沪深300指数",lambda: fetch_benchmark_daily(years=5),retries=3
                )
                benchmark_name="沪深300"
            mkt_score,mkt_regime=market_environment(benchmark_df)
            pool=fetch_universe(universe)
        finally:
            if use_bs_session:
                bs_logout_safe()

        if exclude_st and universe!="港股主板" and not pool.empty:
            pool=pool[
                ~pool["code_name"].astype(str).str.upper().str.contains(
                    r"(^ST|\*ST)",regex=True,na=False
                )
            ]
        pool=pool.drop_duplicates("code").reset_index(drop=True)
        total=len(pool)
        cursor=min(int(job.get("cursor",0) or 0),total)
        _update_screener_job(
            job_id,total=total,market_score=float(mkt_score),
            market_regime=str(mkt_regime),benchmark_name=benchmark_name
        )

        agg_stats={
            "扫描":0,"快速初筛通过":0,"优先机会":0,"候选观察":0,
            "EV阶段":0,"EV缓存命中":0,"流动性不足":0,
            "周线低一致性":0,"数据异常":0
        }
        old_stats=job.get("stats_json")
        if old_stats:
            try:
                agg_stats.update(json.loads(old_stats))
            except Exception:
                pass

        while cursor<total:
            current=load_screener_job(job_id)
            if not current or str(current.get("status"))=="paused_manual":
                return
            outer_end=min(cursor+outer_batch,total)
            if use_bs_session:
                bs_login()
            try:
                while cursor<outer_end:
                    current=load_screener_job(job_id)
                    if not current or str(current.get("status"))=="paused_manual":
                        return
                    end=min(cursor+micro_batch,outer_end)
                    batch=pool.iloc[cursor:end]
                    codes=batch["code"].tolist()
                    names=dict(zip(batch["code"],batch["code_name"]))

                    last_err=None
                    batch_result=None
                    batch_stats=None
                    for attempt in range(2):
                        try:
                            batch_result,batch_stats=screen_codes(
                                codes,names,benchmark_df=benchmark_df,
                                progress_callback=None
                            )
                            last_err=None
                            break
                        except Exception as ex:
                            last_err=ex
                            time.sleep(1.5*(attempt+1))
                    if last_err is not None:
                        raise RuntimeError(f"扫描 {cursor}-{end} 批次失败：{last_err}")

                    _save_screener_rows(job_id,batch_result)
                    for k,v in (batch_stats or {}).items():
                        agg_stats[k]=int(agg_stats.get(k,0) or 0)+int(v or 0)

                    cursor=end
                    _update_screener_job(
                        job_id,cursor=cursor,
                        stats_json=json.dumps(agg_stats,ensure_ascii=False),
                        status=("completed" if cursor>=total else "running")
                    )
            finally:
                if use_bs_session:
                    bs_logout_safe()

            time.sleep(0.25)

        _update_screener_job(job_id,status="completed",cursor=total,error=None)
    except Exception as ex:
        err=f"{type(ex).__name__}: {ex}"
        print("BACKGROUND_SCREENER_ERROR",job_id,err)
        print(traceback.format_exc())
        _update_screener_job(job_id,status="paused",error=err)
    finally:
        bs_logout_safe()
        with _SCREENER_THREADS_LOCK:
            _SCREENER_THREADS.pop(job_id,None)
        if job_type=="manual":
            resume_scheduled_after_manual()

def start_screener_job_background(job_id):
    if not job_id:
        return False
    with _SCREENER_THREADS_LOCK:
        t=_SCREENER_THREADS.get(job_id)
        if t is not None and t.is_alive():
            return True
        t=threading.Thread(
            target=_background_screener_worker,args=(job_id,),
            daemon=True,name=f"screener-{job_id}"
        )
        _SCREENER_THREADS[job_id]=t
        t.start()
    return True

def get_screener_settings():
    conn=sqlite3.connect(DB_PATH)
    row=conn.execute(
        """SELECT auto_daily,universe,exclude_st,batch_size,run_after_hour
           FROM screener_settings WHERE id=1"""
    ).fetchone()
    conn.close()
    if not row:
        return {"auto_daily":1,"universe":"中证500","exclude_st":1,"batch_size":100,"run_after_hour":18}
    return {
        "auto_daily":int(row[0]),"universe":str(row[1]),
        "exclude_st":int(row[2]),"batch_size":int(row[3]),
        "run_after_hour":int(row[4])
    }

def save_screener_settings(auto_daily,universe,exclude_st,batch_size,run_after_hour):
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO screener_settings(
           id,auto_daily,universe,exclude_st,batch_size,run_after_hour,updated_at
        ) VALUES(1,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          auto_daily=excluded.auto_daily,universe=excluded.universe,
          exclude_st=excluded.exclude_st,batch_size=excluded.batch_size,
          run_after_hour=excluded.run_after_hour,updated_at=excluded.updated_at""",
        (
            1 if auto_daily else 0,str(universe),1 if exclude_st else 0,
            int(batch_size),int(run_after_hour),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit(); conn.close()

def maybe_resume_or_start_daily_screener():
    repair_stale_screener_jobs()
    settings=get_screener_settings()

    # 手动任务优先。每日任务与手动任务逻辑完全分开，手动任务运行时每日任务暂停。
    if active_screener_job("manual"):
        return None

    conn=sqlite3.connect(DB_PATH)
    scheduled=pd.read_sql_query(
        """SELECT * FROM screener_jobs
           WHERE job_type='scheduled'
             AND status IN ('running','queued','paused','paused_manual')
           ORDER BY created_at DESC LIMIT 1""",
        conn
    )
    conn.close()
    if not scheduled.empty:
        job=scheduled.iloc[0].to_dict()
        job_id=str(job["job_id"])
        if str(job.get("status")) in ("paused","paused_manual"):
            _update_screener_job(job_id,status="queued",error=None)
        start_screener_job_background(job_id)
        return job_id

    if not int(settings.get("auto_daily",0)):
        return None

    now=pd.Timestamp.now(tz="Asia/Shanghai")
    if int(now.hour)<int(settings.get("run_after_hour",18)):
        return None

    today=now.strftime("%Y-%m-%d")
    conn=sqlite3.connect(DB_PATH)
    row=conn.execute(
        """SELECT job_id,status FROM screener_jobs
           WHERE job_type='scheduled' AND trade_date=? AND universe=?
           ORDER BY created_at DESC LIMIT 1""",
        (today,settings["universe"])
    ).fetchone()
    conn.close()
    if row:
        return str(row[0])

    job_id=create_screener_job(
        settings["universe"],bool(settings["exclude_st"]),
        settings["batch_size"],trade_date=today,job_type="scheduled"
    )
    start_screener_job_background(job_id)
    return job_id

def run_backtest(df,benchmark_df,code=None,fee_bps=None):
    code=normalize_code(code or (str(df.iloc[-1].get("code","")) if df is not None and not df.empty else ""))
    if not code:
        code="sh.000001"

    trades,m=simulate_structural_trades(df,benchmark_df,code,cost_mult=1.0)
    stress=reprice_trades_for_cost(trades,code,cost_mult=2.0)
    if m.empty:
        return pd.DataFrame(),{}

    equity=np.ones(len(m),dtype=float)
    capital=1.0
    cursor=0

    if trades is not None and not trades.empty:
        for _,t in trades.iterrows():
            ei=int(t["entry_index"])
            xi=int(t["exit_index"])
            if ei>=len(m) or xi>=len(m):
                continue
            equity[cursor:ei]=capital
            entry=float(t["entry"])
            for k in range(ei,xi+1):
                px=float(m.iloc[k]["close"])
                equity[k]=capital*(px/entry)
            capital*=1+float(t["return"])
            equity[xi]=capital
            cursor=xi+1

    equity[cursor:]=capital
    m=m.copy()
    m["净值"]=equity
    first_open=float(m.iloc[0]["open"]) if pd.notna(m.iloc[0]["open"]) and m.iloc[0]["open"]>0 else float(m.iloc[0]["close"])
    m["买入持有"]=m["close"]/first_open

    eq=pd.Series(equity)
    total=float(eq.iloc[-1]-1)
    n_years=max((m["trade_date"].iloc[-1]-m["trade_date"].iloc[0]).days/365.25,0.01)
    annual=float(eq.iloc[-1]**(1/n_years)-1) if eq.iloc[-1]>0 else -1.0
    dd=float((eq/eq.cummax()-1).min())

    ev=summarize_ev(trades)
    stress_ev=summarize_ev(stress)
    wf=walk_forward_validation(trades)
    metrics={
        "累计收益":total,"年化收益":annual,"最大回撤":dd,
        "交易次数":ev["样本"],"买入持有":float(m["买入持有"].iloc[-1]-1),
        "交易胜率":ev["胜率"],
        "单笔均收益":float(trades["return"].mean()) if trades is not None and not trades.empty else np.nan,
        "盈亏因子":ev["盈亏因子"],"平均持有天数":ev["平均持有"],
        "持仓暴露":float(pd.to_numeric(trades["holding_days"],errors="coerce").sum()/max(len(m),1)) if trades is not None and not trades.empty else 0.0,
        "EV_R":ev["EV_R"],"保守EV_R":ev["保守EV_R"],"压力EV_R":stress_ev["EV_R"],
        "EV可信度":ev["可信度"],"OOS_EV_R":wf["OOS_EV_R"],"OOS胜率":wf["OOS胜率"],
        "OOS稳定性":wf["稳定性"],"OOS折数":wf["折数"],"OOS正EV折数":wf["正EV折数"]
    }
    return m,metrics

def position_action(
    current_score, entry_score, peak_score, weekly_score,
    market_score, close, initial_stop=None
):
    current_score = float(current_score or 0)
    entry_score = float(entry_score) if entry_score is not None and pd.notna(entry_score) else current_score
    peak_score = float(peak_score) if peak_score is not None and pd.notna(peak_score) else max(entry_score,current_score)
    weekly_score = float(weekly_score) if weekly_score is not None and pd.notna(weekly_score) else 50.0
    market_score = float(market_score) if market_score is not None and pd.notna(market_score) else 50.0

    drop_from_peak = peak_score-current_score
    drop_from_entry = entry_score-current_score

    if initial_stop is not None and pd.notna(initial_stop) and float(initial_stop) > 0 and close <= float(initial_stop):
        return "退出候选", "已跌破录入的技术失效价"

    if current_score < 45:
        return "退出候选", "技术分低于45，趋势与动能已明显弱化"

    if current_score < 55:
        action, reason = "减仓候选", "技术分进入45–54防守区"
    elif current_score < 65:
        action, reason = "谨慎持有", "技术分处于55–64观察区"
    elif current_score < 78:
        action, reason = "持有", "技术分处于65–77健康区"
    else:
        action, reason = "强势持有", "技术分≥78，结构仍处强势区"

    # 分数从高点快速回落，比绝对分更早反映趋势退化
    if drop_from_peak >= 15 or drop_from_entry >= 12:
        if action == "强势持有":
            action = "持有"
        elif action == "持有":
            action = "谨慎持有"
        elif action == "谨慎持有":
            action = "减仓候选"
        reason += f"；技术分较峰值回落{drop_from_peak:.0f}分"

    # 周线弱化与大盘逆风只做一级降档，不机械一票否决
    if weekly_score < 45:
        if action == "强势持有":
            action = "持有"
        elif action == "持有":
            action = "谨慎持有"
        elif action == "谨慎持有":
            action = "减仓候选"
        reason += "；周线已转弱"

    if market_score < 35 and current_score < 68:
        if action == "持有":
            action = "谨慎持有"
        elif action == "谨慎持有":
            action = "减仓候选"
        reason += "；大盘处于逆风区"

    return action, reason

def add_screener_rows_to_positions(df):
    if df is None or df.empty:
        return 0,[]
    ok = 0
    errors = []
    now_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    for idx,row in df.iterrows():
        try:
            raw = str(row.get("代码","")).strip()
            if not raw:
                continue
            code,name = resolve_symbol_input(raw)
            price = pd.to_numeric(row.get("收盘"),errors="coerce")
            if pd.isna(price) or float(price)<=0:
                raise ValueError("候选缺少有效收盘价")
            note = "由选股模块一键加入；成本暂用筛选收盘价，请按实际成交修改"
            upsert_position(code,name,now_date,float(price),0,None,note)
            tech = pd.to_numeric(row.get("技术分/100"),errors="coerce")
            mkt_text = str(row.get("大盘",""))
            mm = re.search(r"(\d+(?:\.\d+)?)/100",mkt_text)
            mkt = float(mm.group(1)) if mm else None
            if pd.notna(tech):
                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    """UPDATE positions SET
                       entry_score=COALESCE(entry_score,?),
                       peak_score=CASE
                         WHEN peak_score IS NULL THEN ?
                         WHEN peak_score < ? THEN ?
                         ELSE peak_score END,
                       last_score=?,last_price=?,last_market_score=COALESCE(?,last_market_score),
                       updated_at=?
                       WHERE code=?""",
                    (
                        float(tech),float(tech),float(tech),float(tech),
                        float(tech),float(price),mkt,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),code
                    )
                )
                conn.commit(); conn.close()
            ok += 1
        except Exception as e:
            errors.append(f"第{idx+1}行：{e}")
    return ok,errors

def editable_positions_frame():
    df = load_positions(True)
    if df.empty:
        return pd.DataFrame(columns=[
            "删除","市场","代码","名称","买入均价","持股数量","买入日期","技术失效价","备注",
            "技术分/100","峰值技术分","现价","管理状态"
        ])
    out = pd.DataFrame({
        "删除":False,
        "市场":df["code"].map(market_of_code),
        "代码":df["code"].map(display_code),
        "名称":df["name"],
        "买入均价":df["entry_price"],
        "持股数量":df["shares"],
        "买入日期":df["entry_date"],
        "技术失效价":df["initial_stop"],
        "备注":df["note"],
        "技术分/100":df["last_score"],
        "峰值技术分":df["peak_score"],
        "现价":df["last_price"],
        "管理状态":df["last_action"]
    })
    return out

def save_edited_positions(df):
    if df is None or df.empty:
        return 0,0,[]
    saved = deleted = 0
    errors = []
    for idx,row in df.iterrows():
        try:
            code = normalize_code(str(row.get("代码","")).strip())
            if not code:
                continue
            if bool(row.get("删除",False)):
                close_position(code)
                deleted += 1
                continue
            name = str(row.get("名称") or "").strip() or stock_basic_name(code)
            price = pd.to_numeric(row.get("买入均价"),errors="coerce")
            shares = pd.to_numeric(row.get("持股数量"),errors="coerce")
            if pd.isna(price) or float(price)<=0:
                raise ValueError("买入均价必须>0")
            shares = 0 if pd.isna(shares) else float(shares)
            entry_date = str(row.get("买入日期") or "").strip() or pd.Timestamp.today().strftime("%Y-%m-%d")
            stop = pd.to_numeric(row.get("技术失效价"),errors="coerce")
            stop = float(stop) if pd.notna(stop) and float(stop)>0 else None
            note = str(row.get("备注") or "")
            upsert_position(code,name,entry_date,float(price),shares,stop,note)
            saved += 1
        except Exception as e:
            errors.append(f"第{idx+1}行：{e}")
    return saved,deleted,errors

def upsert_position(code, name, entry_date, entry_price, shares, initial_stop=None, note=""):
    code = normalize_code(code)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    old = conn.execute(
        "SELECT entry_score,peak_score,last_score,last_price,last_market_score,last_action,created_at FROM positions WHERE code=?",
        (code,)
    ).fetchone()
    created_at = old[6] if old else now
    conn.execute("""
        INSERT INTO positions(
          code,name,entry_date,entry_price,shares,initial_stop,
          entry_score,peak_score,last_score,last_price,last_market_score,last_action,
          note,active,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(code) DO UPDATE SET
          name=excluded.name,
          entry_date=excluded.entry_date,
          entry_price=excluded.entry_price,
          shares=excluded.shares,
          initial_stop=excluded.initial_stop,
          note=excluded.note,
          active=1,
          updated_at=excluded.updated_at
    """,(
        code,name,entry_date,float(entry_price),float(shares),
        (float(initial_stop) if initial_stop is not None and initial_stop>0 else None),
        (old[0] if old else None),(old[1] if old else None),(old[2] if old else None),
        (old[3] if old else None),(old[4] if old else None),(old[5] if old else None),
        note,1,created_at,now
    ))
    conn.commit()
    conn.close()
    sync_shared_light_safe(force=True)

def close_position(code):
    code = normalize_code(code)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE positions SET active=0,updated_at=? WHERE code=?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),code)
    )
    conn.commit()
    conn.close()
    sync_shared_light_safe(force=True)

def load_positions(active_only=True):
    conn = sqlite3.connect(DB_PATH)
    q = "SELECT * FROM positions"
    if active_only:
        q += " WHERE active=1"
    q += " ORDER BY updated_at DESC"
    df = pd.read_sql_query(q,conn)
    conn.close()
    return df

def import_positions_dataframe(df):
    if df is None or df.empty:
        return 0,["文件为空"]

    aliases = {
        "symbol":["代码","股票代码","code","symbol","股票","名称","股票名称"],
        "price":["买入均价","成本","成本价","entry_price","price"],
        "shares":["持股数量","数量","持股","shares","qty"],
        "date":["买入日期","日期","entry_date","date"],
        "stop":["技术失效价","失效价","止损价","initial_stop","stop"],
        "note":["备注","note","memo"]
    }
    cols = {str(x).strip():x for x in df.columns}

    def pick(keys):
        for k in keys:
            if k in cols:
                return cols[k]
        return None

    symbol_col = pick(aliases["symbol"])
    price_col = pick(aliases["price"])
    shares_col = pick(aliases["shares"])
    date_col = pick(aliases["date"])
    stop_col = pick(aliases["stop"])
    note_col = pick(aliases["note"])

    if symbol_col is None or price_col is None:
        return 0,["至少需要“代码/名称”和“买入均价/成本”两列"]

    ok = 0
    errors = []
    for idx,row in df.iterrows():
        try:
            raw_symbol = str(row.get(symbol_col,"")).strip()
            if not raw_symbol or raw_symbol.lower()=="nan":
                continue
            code,name = resolve_symbol_input(raw_symbol)
            price = pd.to_numeric(row.get(price_col),errors="coerce")
            if pd.isna(price) or float(price)<=0:
                raise ValueError("买入均价无效")
            shares = pd.to_numeric(row.get(shares_col),errors="coerce") if shares_col else 0
            shares = 0 if pd.isna(shares) else float(shares)

            entry_date = pd.Timestamp.today().strftime("%Y-%m-%d")
            if date_col and pd.notna(row.get(date_col)):
                try:
                    entry_date = pd.to_datetime(row.get(date_col)).strftime("%Y-%m-%d")
                except Exception:
                    pass

            stop = None
            if stop_col:
                v = pd.to_numeric(row.get(stop_col),errors="coerce")
                if pd.notna(v) and float(v)>0:
                    stop = float(v)
            note = ""
            if note_col and pd.notna(row.get(note_col)):
                note = str(row.get(note_col))

            upsert_position(code,name,entry_date,float(price),shares,stop,note)
            ok += 1
        except Exception as e:
            errors.append(f"第{idx+2}行：{e}")
    return ok,errors

def position_history(code, limit=120):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """SELECT snapshot_date,price,technical_score,trend_score,momentum_score,
                  weekly_score,confirm_score,market_score,pnl_pct,action,reason
           FROM position_snapshots
           WHERE code=? ORDER BY snapshot_date DESC LIMIT ?""",
        conn,params=(normalize_code(code),limit)
    )
    conn.close()
    return df

def refresh_positions():
    pos = load_positions(True)
    if pos.empty:
        return pd.DataFrame()

    benchmarks = {}
    rows = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _,p in pos.iterrows():
        code = p["code"]
        try:
            market = market_of_code(code)
            if market not in benchmarks:
                benchmarks[market] = fetch_benchmark_for_code(code,years=3)
            benchmark_df = benchmarks[market]
            mkt_score,mkt_regime = market_environment(benchmark_df)
            df = fetch_stock_daily(code,years=3)
            if df.empty:
                continue
            name = p["name"] or stock_basic_name(code)
            report = deterministic_report(
                code,name,df,"中等25–50%",True,benchmark_df,compute_ev=False
            )
            current = float(report["score"])
            current_price = float(report["latest_close"])
            entry_score = p["entry_score"]
            if entry_score is None or pd.isna(entry_score):
                entry_score = current
            peak_score = p["peak_score"]
            if peak_score is None or pd.isna(peak_score):
                peak_score = max(float(entry_score),current)
            peak_score = max(float(peak_score),current)

            pnl_pct = (
                current_price/float(p["entry_price"])-1
                if float(p["entry_price"])>0 else np.nan
            )
            action,reason = position_action(
                current,float(entry_score),peak_score,
                report.get("weekly_score"),mkt_score,current_price,p.get("initial_stop")
            )

            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                UPDATE positions SET
                  name=?,entry_score=?,peak_score=?,last_score=?,last_price=?,
                  last_market_score=?,last_action=?,updated_at=?
                WHERE code=?
            """,(name,float(entry_score),float(peak_score),current,current_price,
                 float(mkt_score),action,now,code))
            conn.execute("""
                INSERT INTO position_snapshots(
                  code,snapshot_date,price,technical_score,trend_score,momentum_score,
                  weekly_score,confirm_score,market_score,pnl_pct,action,reason,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code,snapshot_date) DO UPDATE SET
                  price=excluded.price,
                  technical_score=excluded.technical_score,
                  trend_score=excluded.trend_score,
                  momentum_score=excluded.momentum_score,
                  weekly_score=excluded.weekly_score,
                  confirm_score=excluded.confirm_score,
                  market_score=excluded.market_score,
                  pnl_pct=excluded.pnl_pct,
                  action=excluded.action,
                  reason=excluded.reason,
                  created_at=excluded.created_at
            """,(
                code,report["latest_date"],current_price,current,
                report.get("trend"),report.get("momentum"),report.get("weekly_score"),
                report.get("confirm"),float(mkt_score),
                (float(pnl_pct) if pd.notna(pnl_pct) else None),
                action,reason,now
            ))
            conn.commit()
            conn.close()

            rows.append({
                "市场":market_of_code(code),
                "代码":display_code(code),
                "名称":name,
                "管理状态":action,
                "技术分/100":current,
                "入场技术分":round(float(entry_score),1),
                "峰值技术分":round(float(peak_score),1),
                "较峰值":round(current-float(peak_score),1),
                "周线/100":report.get("weekly_score"),
                "大盘":f"{benchmark_label_for_code(code)} {mkt_regime} {mkt_score}/100",
                "成本":round(float(p["entry_price"]),2),
                "现价":round(current_price,2),
                "收益率":pnl_pct,
                "持股":float(p["shares"]),
                "市值":round(current_price*float(p["shares"]),2),
                "失效价":p.get("initial_stop"),
                "原因":reason
            })
        except Exception as e:
            rows.append({
                "代码":display_code(code),"名称":p["name"] or display_code(code),
                "管理状态":"数据异常","原因":str(e)
            })

    if not rows:
        return pd.DataFrame()
    order = {"退出候选":0,"减仓候选":1,"谨慎持有":2,"持有":3,"强势持有":4,"数据异常":5}
    out = pd.DataFrame(rows)
    out["_ord"] = out["管理状态"].map(order).fillna(9)
    return out.sort_values(["_ord","技术分/100"],ascending=[True,True],na_position="last").drop(columns="_ord").reset_index(drop=True)

def recent_analyses(limit=12):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """SELECT created_at,symbol,market,horizon,position_state,state,rating,
                  score,trend_score,momentum_score,weekly_score,confirm_score,model_mode
           FROM analyses
           WHERE model_mode LIKE '%自动数据'
           ORDER BY id DESC LIMIT ?""",
        conn, params=(limit,)
    )
    conn.close()
    return df

def _research_month_end_trade_dates(years):
    end=pd.Timestamp.today().normalize()
    start=(end-pd.DateOffset(years=int(years))-pd.DateOffset(months=1)).normalize()
    rs=bs.query_trade_dates(
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d")
    )
    df=_rs_to_df(rs)
    if df.empty:
        return [end.strftime("%Y-%m-%d")]
    df=df[df["is_trading_day"].astype(str)=="1"].copy()
    df["calendar_date"]=pd.to_datetime(df["calendar_date"],errors="coerce")
    df=df.dropna(subset=["calendar_date"])
    dates=(
        df.groupby(df["calendar_date"].dt.to_period("M"))["calendar_date"]
          .max().sort_values().tolist()
    )
    return [pd.Timestamp(x).strftime("%Y-%m-%d") for x in dates]

def _fetch_universe_at_date(kind,day):
    if kind=="港股主板":
        hk=hk_universe_snapshot()
        return hk[["code","code_name"]].drop_duplicates("code").reset_index(drop=True)

    if kind=="沪深300":
        rs=bs.query_hs300_stocks(date=day)
        df=_rs_to_df(rs)
    elif kind=="中证500":
        rs=bs.query_zz500_stocks(date=day)
        df=_rs_to_df(rs)
    elif kind=="上证50":
        rs=bs.query_sz50_stocks(date=day)
        df=_rs_to_df(rs)
    else:
        rs=bs.query_all_stock(day=day)
        df=_rs_to_df(rs)
        if not df.empty:
            code_col="code" if "code" in df.columns else df.columns[0]
            df=df[df[code_col].astype(str).str.match(r"^(sh\.6|sz\.[03])")]

    if df.empty:
        return pd.DataFrame(columns=["code","code_name"])
    code_col="code" if "code" in df.columns else df.columns[0]
    name_col="code_name" if "code_name" in df.columns else ("codeName" if "codeName" in df.columns else None)
    out=pd.DataFrame({"code":df[code_col].astype(str)})
    out["code_name"]=df[name_col].astype(str) if name_col else out["code"]
    out=out[~out["code_name"].astype(str).str.upper().str.contains(r"(^ST|\*ST)",regex=True,na=False)]
    return out.drop_duplicates("code").reset_index(drop=True)

def _build_historical_membership(universe,years):
    market="港股" if universe=="港股主板" else "A股"
    end=pd.Timestamp.today().normalize()

    if market=="港股":
        # 公开免费数据源目前没有稳定的港股历史主板成分快照。
        pool=_fetch_universe_at_date(universe,end.strftime("%Y-%m-%d"))
        start=(end-pd.DateOffset(years=int(years))).normalize()
        rows=[
            {
                "period_start":start.strftime("%Y-%m-%d"),
                "period_end":end.strftime("%Y-%m-%d"),
                "code":str(r["code"]),"name":str(r["code_name"]),"market":"港股"
            }
            for _,r in pool.iterrows()
        ]
        return pd.DataFrame(rows),pool,"current_only"

    snap_dates=_research_month_end_trade_dates(years)
    if len(snap_dates)<2:
        pool=_fetch_universe_at_date(universe,end.strftime("%Y-%m-%d"))
        start=(end-pd.DateOffset(years=int(years))).normalize()
        rows=[
            {
                "period_start":start.strftime("%Y-%m-%d"),
                "period_end":end.strftime("%Y-%m-%d"),
                "code":str(r["code"]),"name":str(r["code_name"]),"market":"A股"
            }
            for _,r in pool.iterrows()
        ]
        return pd.DataFrame(rows),pool,"fallback_current"

    membership=[]
    union={}
    for idx,snap in enumerate(snap_dates):
        pool=_fetch_universe_at_date(universe,snap)
        if pool.empty:
            continue
        snap_ts=pd.Timestamp(snap)
        period_start=(snap_ts+pd.Timedelta(days=1)).normalize()
        next_snap=pd.Timestamp(snap_dates[idx+1]) if idx+1<len(snap_dates) else end
        period_end=next_snap.normalize()
        for _,r in pool.iterrows():
            code=str(r["code"]); name=str(r["code_name"])
            union[code]=name
            membership.append({
                "period_start":period_start.strftime("%Y-%m-%d"),
                "period_end":period_end.strftime("%Y-%m-%d"),
                "code":code,"name":name,"market":"A股"
            })

    mem=pd.DataFrame(membership)
    union_df=pd.DataFrame(
        [{"code":code,"code_name":name} for code,name in union.items()]
    ).drop_duplicates("code")
    return mem,union_df,"historical_monthly"

def create_research_run(universe,years):
    membership,pool,membership_mode=_build_historical_membership(universe,years)
    if pool is None or pool.empty:
        raise RuntimeError("研究股票池为空，无法创建任务。")

    pool=pool.drop_duplicates("code").reset_index(drop=True)
    run_id=datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+str(abs(hash((universe,int(years),RULE_VERSION)))%10000).zfill(4)
    market="港股" if universe=="港股主板" else "A股"
    benchmark_name="恒生指数" if market=="港股" else "沪深300"
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    note=(
        "历史股票池：按月使用BaoStock历史成分/历史在市股票，显著降低幸存者偏差。"
        if membership_mode=="historical_monthly"
        else "港股免费数据源暂使用当前主板股票池回溯，仍存在幸存者偏差。"
    )

    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO research_runs(
           run_id,created_at,updated_at,universe,years,status,cursor,total,rule_version,benchmark_name,note
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,now,now,universe,int(years),"running",0,len(pool),
            RULE_VERSION,benchmark_name,note
        )
    )
    members=[
        (run_id,int(i),str(r["code"]),str(r["code_name"]),market)
        for i,r in pool.iterrows()
    ]
    conn.executemany(
        """INSERT INTO research_members(run_id,seq,code,name,market)
           VALUES(?,?,?,?,?)""",members
    )
    if membership is not None and not membership.empty:
        mrows=[
            (
                run_id,str(r["period_start"]),str(r["period_end"]),
                str(r["code"]),str(r["name"]),str(r["market"])
            )
            for _,r in membership.iterrows()
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO research_membership(
               run_id,period_start,period_end,code,name,market
            ) VALUES(?,?,?,?,?,?)""",mrows
        )
    conn.commit(); conn.close()
    sync_shared_research_safe(run_id,mode="push")
    return run_id,len(pool)

def load_research_runs(limit=30):
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        """SELECT * FROM research_runs
           ORDER BY created_at DESC LIMIT ?""",
        conn,params=(int(limit),)
    )
    conn.close()
    return df

def get_research_run(run_id):
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        "SELECT * FROM research_runs WHERE run_id=?",
        conn,params=(run_id,)
    )
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None

def _research_membership_periods(run_id,code):
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        """SELECT period_start,period_end FROM research_membership
           WHERE run_id=? AND code=?
           ORDER BY period_start""",
        conn,params=(run_id,code)
    )
    conn.close()
    if not df.empty:
        df["period_start"]=pd.to_datetime(df["period_start"],errors="coerce")
        df["period_end"]=pd.to_datetime(df["period_end"],errors="coerce")
    return df

def filter_research_trades_by_membership(run_id,code,trades):
    if trades is None or trades.empty:
        return pd.DataFrame() if trades is None else trades
    periods=_research_membership_periods(run_id,code)
    if periods.empty:
        return trades
    signal_dates=pd.to_datetime(trades["signal_date"],errors="coerce")
    keep=pd.Series(False,index=trades.index)
    for _,p in periods.iterrows():
        if pd.isna(p["period_start"]) or pd.isna(p["period_end"]):
            continue
        keep=keep | ((signal_dates>=p["period_start"]) & (signal_dates<=p["period_end"]))
    return trades.loc[keep].reset_index(drop=True)

def save_research_stock_result(run_id,code,name,market,trades,ev,wf):
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pf=ev.get("盈亏因子")
    pf_db=float(pf) if pd.notna(pf) and np.isfinite(pf) else None
    conn=sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM research_trades WHERE run_id=? AND code=?",(run_id,code))
    conn.execute(
        """INSERT OR REPLACE INTO research_stock_results(
           run_id,code,name,market,trade_count,ev_r,conservative_ev_r,win_rate,
           avg_win_r,avg_loss_r,profit_factor,oos_ev_r,oos_stability,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,code,name,market,int(ev.get("样本",0) or 0),
            float(ev["EV_R"]) if pd.notna(ev.get("EV_R")) else None,
            float(ev["保守EV_R"]) if pd.notna(ev.get("保守EV_R")) else None,
            float(ev["胜率"]) if pd.notna(ev.get("胜率")) else None,
            float(ev["平均盈利R"]) if pd.notna(ev.get("平均盈利R")) else None,
            float(ev["平均亏损R"]) if pd.notna(ev.get("平均亏损R")) else None,
            pf_db,
            float(wf["OOS_EV_R"]) if pd.notna(wf.get("OOS_EV_R")) else None,
            str(wf.get("稳定性","样本不足")),now
        )
    )
    if trades is not None and not trades.empty:
        rows=[]
        for _,t in trades.iterrows():
            entry=float(t["entry"]) if pd.notna(t.get("entry")) else None
            stop=float(t["stop"]) if pd.notna(t.get("stop")) else None
            risk_pct=((entry-stop)/entry) if entry and stop is not None and entry>stop else None
            rows.append((
                run_id,code,name,market,
                pd.Timestamp(t["signal_date"]).strftime("%Y-%m-%d"),
                pd.Timestamp(t["entry_date"]).strftime("%Y-%m-%d"),
                pd.Timestamp(t["exit_date"]).strftime("%Y-%m-%d"),
                float(t["return"]) if pd.notna(t.get("return")) else None,
                float(t["R"]) if pd.notna(t.get("R")) else None,
                entry,
                float(t["exit"]) if pd.notna(t.get("exit")) else None,
                stop,risk_pct,
                int(t.get("holding_days",0) or 0),
                float(t["technical"]) if pd.notna(t.get("technical")) else None,
                float(t["buy_score"]) if pd.notna(t.get("buy_score")) else None,
                float(t["weekly"]) if pd.notna(t.get("weekly")) else None,
                float(t["rr"]) if pd.notna(t.get("rr")) else None,
                float(t["market_score"]) if pd.notna(t.get("market_score")) else None,
                float(t["rs_score"]) if pd.notna(t.get("rs_score")) else None,
                float(t["opportunity"]) if pd.notna(t.get("opportunity")) else None,
                str(t.get("exit_reason",""))
            ))
        conn.executemany(
            """INSERT INTO research_trades(
               run_id,code,name,market,signal_date,entry_date,exit_date,return_pct,r_multiple,
               entry_price,exit_price,stop_price,initial_risk_pct,
               holding_days,technical_score,buy_score,weekly_score,rr,market_score,rs_score,
               opportunity_score,exit_reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",rows
        )
    conn.commit(); conn.close()

def run_research_batch(run_id,batch_size=20,progress_callback=None):
    run=get_research_run(run_id)
    if not run:
        raise RuntimeError("研究任务不存在。")
    if run.get("status")=="completed":
        return {"processed":0,"errors":[],"done":True}

    cursor=int(run.get("cursor",0) or 0)
    total=int(run.get("total",0) or 0)
    end=min(cursor+int(batch_size),total)
    conn=sqlite3.connect(DB_PATH)
    members=pd.read_sql_query(
        """SELECT * FROM research_members
           WHERE run_id=? AND seq>=? AND seq<?
           ORDER BY seq""",
        conn,params=(run_id,cursor,end)
    )
    conn.close()
    if members.empty:
        return {"processed":0,"errors":[],"done":cursor>=total}

    years=int(run.get("years",5) or 5)
    universe=str(run.get("universe"))
    benchmark=fetch_hk_benchmark_daily(years=years) if universe=="港股主板" else fetch_benchmark_daily(years=years)
    errors=[]
    processed=0

    for _,member in members.iterrows():
        seq=int(member["seq"])
        code=str(member["code"])
        name=str(member["name"])
        market=str(member["market"])
        if progress_callback:
            try:
                progress_callback(seq-cursor,len(members),seq,total,code,name,"读取历史行情")
            except Exception:
                pass
        try:
            df=fetch_stock_daily(code,years=years)
            if len(df)<180:
                raise RuntimeError("有效历史少于180个交易日")
            if progress_callback:
                try:
                    progress_callback(seq-cursor,len(members),seq,total,code,name,"执行固定规则交易回放")
                except Exception:
                    pass
            trades,_=simulate_structural_trades(df,benchmark,code,cost_mult=1.0)
            trades=filter_research_trades_by_membership(run_id,code,trades)
            ev=summarize_ev(trades)
            wf=purged_walk_forward_validation(trades,purge_days=30,embargo_days=10)
            save_research_stock_result(run_id,code,name,market,trades,ev,wf)
        except Exception as e:
            errors.append(f"{display_code(code)} {name}: {e}")
        finally:
            processed+=1
            new_cursor=seq+1
            status="completed" if new_cursor>=total else "running"
            conn=sqlite3.connect(DB_PATH)
            conn.execute(
                """UPDATE research_runs
                   SET cursor=?,status=?,updated_at=?
                   WHERE run_id=?""",
                (
                    new_cursor,status,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),run_id
                )
            )
            conn.commit(); conn.close()
            if progress_callback:
                try:
                    progress_callback(seq-cursor+1,len(members),new_cursor,total,code,name,"完成")
                except Exception:
                    pass

    sync_shared_research_safe(run_id,mode="push")
    return {"processed":processed,"errors":errors,"done":end>=total}

def _cached_close_series(code,start_date,end_date):
    code=normalize_code(code)
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        """SELECT trade_date,close FROM market_daily_cache
           WHERE code=? AND trade_date>=? AND trade_date<=?
           ORDER BY trade_date""",
        conn,
        params=(
            code,pd.Timestamp(start_date).strftime("%Y-%m-%d"),
            pd.Timestamp(end_date).strftime("%Y-%m-%d")
        )
    )
    conn.close()
    if df.empty:
        return {}
    df["trade_date"]=pd.to_datetime(df["trade_date"],errors="coerce")
    df["close"]=pd.to_numeric(df["close"],errors="coerce")
    df=df.dropna(subset=["trade_date","close"])
    return {
        pd.Timestamp(d).normalize():float(px)
        for d,px in zip(df["trade_date"],df["close"])
    }

def _research_calendar(run,start_date,end_date):
    code="hkidx.HSI" if str(run.get("universe"))=="港股主板" else "sh.000300"
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        """SELECT DISTINCT trade_date FROM market_daily_cache
           WHERE code=? AND trade_date>=? AND trade_date<=?
           ORDER BY trade_date""",
        conn,
        params=(
            code,pd.Timestamp(start_date).strftime("%Y-%m-%d"),
            pd.Timestamp(end_date).strftime("%Y-%m-%d")
        )
    )
    conn.close()
    if not df.empty:
        dates=pd.to_datetime(df["trade_date"],errors="coerce").dropna().dt.normalize().tolist()
        if dates:
            return dates
    return list(pd.bdate_range(start_date,end_date).normalize())

def research_daily_portfolio(run_id,trades,max_slots=10,risk_budget=0.005,max_weight=0.10):
    if trades is None or trades.empty:
        return {
            "交易数":0,"累计收益":np.nan,"年化收益":np.nan,"最大回撤":np.nan,
            "Sharpe":np.nan,"Sortino":np.nan,"Calmar":np.nan,"换手率":np.nan,
            "采用率":np.nan,"平均仓位":np.nan
        },pd.DataFrame(),pd.DataFrame()

    run=get_research_run(run_id)
    t=attach_walkforward_pred_ev(trades,min_history=20,embargo_days=10)
    if t.empty:
        return {
            "交易数":0,"累计收益":np.nan,"年化收益":np.nan,"最大回撤":np.nan,
            "Sharpe":np.nan,"Sortino":np.nan,"Calmar":np.nan,"换手率":np.nan,
            "采用率":np.nan,"平均仓位":np.nan
        },pd.DataFrame(),pd.DataFrame()

    for col in ["entry_date","exit_date","signal_date"]:
        t[col]=pd.to_datetime(t[col],errors="coerce").dt.normalize()
    for col in ["entry_price","exit_price","stop_price","initial_risk_pct","opportunity_score"]:
        t[col]=pd.to_numeric(t[col],errors="coerce")
    t=t.dropna(subset=["entry_date","exit_date","entry_price","exit_price","initial_risk_pct","pred_ev_r"])
    t=t[(t["initial_risk_pct"]>0) & (t["pred_ev_r"]>0)].copy()
    if t.empty:
        return {
            "交易数":0,"累计收益":0.0,"年化收益":0.0,"最大回撤":0.0,
            "Sharpe":np.nan,"Sortino":np.nan,"Calmar":np.nan,"换手率":0.0,
            "采用率":0.0,"平均仓位":0.0
        },pd.DataFrame(),pd.DataFrame()

    t=t.sort_values(
        ["entry_date","pred_ev_r","opportunity_score"],
        ascending=[True,False,False]
    ).reset_index(drop=True)
    start=t["entry_date"].min()
    end=t["exit_date"].max()
    calendar=_research_calendar(run,start,end)
    entries={d:g.copy() for d,g in t.groupby("entry_date")}
    exits={}
    # accepted trades will be placed here after sizing.
    accepted=[]
    active={}
    cash=1.0
    turnover=0.0
    curve=[]
    last_nav=1.0

    for day in calendar:
        day=pd.Timestamp(day).normalize()

        # Mark active holdings with latest available close.
        for code,pos in list(active.items()):
            px=pos["prices"].get(day)
            if px is not None and np.isfinite(px):
                pos["last_close"]=float(px)

        # Exit at modeled execution price before allocating new risk.
        due=[code for code,pos in active.items() if pos["exit_date"]<=day]
        for code in due:
            pos=active.pop(code)
            proceeds=pos["shares"]*pos["exit_price"]
            cash+=proceeds
            turnover+=abs(proceeds)

        nav=cash+sum(pos["shares"]*pos["last_close"] for pos in active.values())
        nav=max(nav,1e-9)

        todays=entries.get(day)
        if todays is not None and not todays.empty:
            for _,row in todays.iterrows():
                code=str(row["code"])
                if code in active or len(active)>=int(max_slots):
                    continue
                risk_pct=float(row["initial_risk_pct"])
                if not np.isfinite(risk_pct) or risk_pct<=0:
                    continue

                # Fixed NAV risk budget + stop-distance sizing.
                # Smaller stop distance => larger notional, but max 10% NAV and available cash.
                target_weight=min(float(max_weight),float(risk_budget)/risk_pct)
                target_weight=max(0.0,target_weight)
                notional=min(cash,nav*target_weight)
                if notional<nav*0.005:
                    continue

                entry_price=float(row["entry_price"])
                if entry_price<=0:
                    continue
                shares=notional/entry_price
                prices=_cached_close_series(code,row["entry_date"],row["exit_date"])
                last_close=prices.get(day,entry_price)
                cash-=notional
                turnover+=abs(notional)

                pos={
                    "code":code,"shares":shares,"entry_date":day,
                    "exit_date":pd.Timestamp(row["exit_date"]).normalize(),
                    "entry_price":entry_price,"exit_price":float(row["exit_price"]),
                    "stop_price":float(row["stop_price"]) if pd.notna(row["stop_price"]) else np.nan,
                    "risk_pct":risk_pct,"weight":target_weight,
                    "pred_ev_r":float(row["pred_ev_r"]),
                    "last_close":float(last_close),"prices":prices
                }
                active[code]=pos
                accepted_row=row.to_dict()
                accepted_row["position_weight"]=target_weight
                accepted_row["risk_budget_nav"]=min(float(risk_budget),target_weight*risk_pct)
                accepted.append(accepted_row)

                nav=cash+sum(p["shares"]*p["last_close"] for p in active.values())
                nav=max(nav,1e-9)

        nav=cash+sum(pos["shares"]*pos["last_close"] for pos in active.values())
        exposure=(nav-cash)/nav if nav>0 else 0.0
        curve.append({
            "date":day,"equity":nav,"cash":cash,
            "exposure":exposure,"positions":len(active)
        })
        last_nav=nav

    curve_df=pd.DataFrame(curve)
    accepted_df=pd.DataFrame(accepted)
    if curve_df.empty:
        return {
            "交易数":0,"累计收益":np.nan,"年化收益":np.nan,"最大回撤":np.nan,
            "Sharpe":np.nan,"Sortino":np.nan,"Calmar":np.nan,"换手率":np.nan,
            "采用率":0.0,"平均仓位":np.nan
        },curve_df,accepted_df

    eq=pd.to_numeric(curve_df["equity"],errors="coerce").ffill().fillna(1.0)
    daily_ret=eq.pct_change().fillna(0.0)
    total=float(eq.iloc[-1]-1)
    years=max((pd.Timestamp(curve_df["date"].iloc[-1])-pd.Timestamp(curve_df["date"].iloc[0])).days/365.25,0.01)
    annual=float(eq.iloc[-1]**(1/years)-1) if eq.iloc[-1]>0 else -1.0
    dd=eq/eq.cummax()-1
    max_dd=float(dd.min())
    std=float(daily_ret.std(ddof=1))
    sharpe=float(daily_ret.mean()/std*np.sqrt(252)) if std>1e-12 else np.nan
    downside=daily_ret[daily_ret<0]
    dstd=float(downside.std(ddof=1)) if len(downside)>=2 else np.nan
    sortino=float(daily_ret.mean()/dstd*np.sqrt(252)) if pd.notna(dstd) and dstd>1e-12 else np.nan
    calmar=float(annual/abs(max_dd)) if max_dd<0 else np.nan
    avg_nav=float(eq.mean()) if len(eq) else 1.0
    turnover_ratio=float(turnover/max(avg_nav,1e-9))
    avg_exposure=float(pd.to_numeric(curve_df["exposure"],errors="coerce").mean())
    adoption=float(len(accepted_df)/len(t)) if len(t) else np.nan

    return {
        "交易数":int(len(accepted_df)),
        "累计收益":total,"年化收益":annual,"最大回撤":max_dd,
        "Sharpe":sharpe,"Sortino":sortino,"Calmar":calmar,
        "换手率":turnover_ratio,"采用率":adoption,"平均仓位":avg_exposure,
        "单笔风险预算":float(risk_budget),"单股上限":float(max_weight),"最大持仓数":int(max_slots)
    },curve_df,accepted_df

def research_summary(run_id):
    run=get_research_run(run_id)
    if not run:
        return None,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame()

    conn=sqlite3.connect(DB_PATH)
    stocks=pd.read_sql_query(
        "SELECT * FROM research_stock_results WHERE run_id=? ORDER BY ev_r DESC",
        conn,params=(run_id,)
    )
    trades=pd.read_sql_query(
        "SELECT * FROM research_trades WHERE run_id=? ORDER BY signal_date,code",
        conn,params=(run_id,)
    )
    conn.close()

    if trades.empty:
        summary={
            "股票数":int(len(stocks)),"交易数":0,"EV_R":np.nan,"保守EV_R":np.nan,
            "胜率":np.nan,"平均盈利R":np.nan,"平均亏损R":np.nan,"真实盈亏比":np.nan,
            "盈亏因子":np.nan,"OOS_EV_R":np.nan,"OOS稳定性":"样本不足",
            "Bootstrap_P正EV":np.nan,"Bootstrap_P05":np.nan,"Bootstrap_P50":np.nan,"Bootstrap_P95":np.nan
        }
        return summary,stocks,trades,pd.DataFrame(),pd.DataFrame()

    temp=pd.DataFrame({
        "R":pd.to_numeric(trades["r_multiple"],errors="coerce"),
        "holding_days":pd.to_numeric(trades["holding_days"],errors="coerce"),
        "signal_date":pd.to_datetime(trades["signal_date"],errors="coerce"),
        "exit_date":pd.to_datetime(trades["exit_date"],errors="coerce"),
        "market":trades["market"],
        "opportunity_score":pd.to_numeric(trades["opportunity_score"],errors="coerce")
    }).dropna(subset=["R","signal_date"])

    ev=summarize_ev(temp)
    wf=purged_walk_forward_validation(temp,purge_days=30,embargo_days=10)
    boot=bootstrap_ev_interval(temp,n_boot=600)
    calibration=ev_calibration_table(trades)

    avg_win=ev.get("平均盈利R")
    avg_loss=ev.get("平均亏损R")
    wl=(
        float(avg_win/abs(avg_loss))
        if pd.notna(avg_win) and pd.notna(avg_loss) and abs(avg_loss)>1e-12
        else np.nan
    )
    pf=ev.get("盈亏因子")
    summary={
        "股票数":int(len(stocks)),"交易数":int(ev.get("样本",0) or 0),
        "EV_R":ev.get("EV_R"),"保守EV_R":ev.get("保守EV_R"),
        "胜率":ev.get("胜率"),"平均盈利R":avg_win,"平均亏损R":avg_loss,
        "真实盈亏比":wl,"盈亏因子":pf,
        "OOS_EV_R":wf.get("OOS_EV_R"),"OOS稳定性":wf.get("稳定性"),
        "Purged折数":wf.get("折数",0),"Purged正EV折数":wf.get("正EV折数",0),
        "Bootstrap_P正EV":boot.get("P(EV>0)"),
        "Bootstrap_P05":boot.get("EV_P05"),
        "Bootstrap_P50":boot.get("EV_P50"),
        "Bootstrap_P95":boot.get("EV_P95")
    }

    port,curve,accepted=research_daily_portfolio(
        run_id,trades,max_slots=10,risk_budget=0.005,max_weight=0.10
    )
    summary.update({
        "组合累计收益":port.get("累计收益"),"组合年化收益":port.get("年化收益"),
        "组合最大回撤":port.get("最大回撤"),"组合交易数":port.get("交易数"),
        "组合采用率":port.get("采用率"),"组合Sharpe":port.get("Sharpe"),
        "组合Sortino":port.get("Sortino"),"组合Calmar":port.get("Calmar"),
        "组合换手率":port.get("换手率"),"组合平均仓位":port.get("平均仓位")
    })
    return summary,stocks,trades,curve,calibration

def delete_research_run(run_id):
    conn=sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM research_trades WHERE run_id=?",(run_id,))
    conn.execute("DELETE FROM research_stock_results WHERE run_id=?",(run_id,))
    conn.execute("DELETE FROM research_members WHERE run_id=?",(run_id,))
    conn.execute("DELETE FROM research_membership WHERE run_id=?",(run_id,))
    conn.execute("DELETE FROM research_runs WHERE run_id=?",(run_id,))
    conn.commit(); conn.close()

def strategy_default_params():
    return {
        "select_delta":0.0,
        "buy_delta":0.0,
        "rr_delta":0.0,
        "max_gap_atr":1.5,
        "ignore_weekly":False,
        "ignore_rs":False,
        "ignore_opp":False,
        "ignore_rr":False,
        "fixed_market_policy":False,
        "exit_score":45.0,
        "peak_drop":15.0,
        "peak_guard_score":65.0,
        "weekly_exit":45.0,
        "market_exit_threshold":25.0,
        "market_exit_score":60.0
    }

def strategy_variant_configs(module):
    base=strategy_default_params()
    def cfg(cid,label,order,**kw):
        p=base.copy(); p.update(kw)
        return {"config_id":cid,"label":label,"order":order,"params":p}

    if module=="选股门槛":
        return [
            cfg("S-6","宽松 -6",0,select_delta=-6),
            cfg("S-3","稍宽 -3",1,select_delta=-3),
            cfg("BASE","EV1.0 基准",2),
            cfg("S+3","稍严 +3",3,select_delta=3),
            cfg("S+6","严格 +6",4,select_delta=6)
        ]
    if module=="买入质量":
        return [
            cfg("B-4","宽松买点",0,buy_delta=-4,rr_delta=-0.20,max_gap_atr=1.8),
            cfg("B-2","稍宽买点",1,buy_delta=-2,rr_delta=-0.10,max_gap_atr=1.65),
            cfg("BASE","EV1.0 基准",2),
            cfg("B+2","稍严买点",3,buy_delta=2,rr_delta=0.10,max_gap_atr=1.35),
            cfg("B+4","严格买点",4,buy_delta=4,rr_delta=0.20,max_gap_atr=1.15)
        ]
    if module=="持仓退出":
        return [
            cfg("E_FAST","快速退出",0,exit_score=48,peak_drop=12,weekly_exit=48),
            cfg("E_QFAST","稍快退出",1,exit_score=46,peak_drop=14,weekly_exit=46),
            cfg("BASE","EV1.0 基准",2),
            cfg("E_SLOW","稍慢退出",3,exit_score=43,peak_drop=17,weekly_exit=43),
            cfg("E_TREND","趋势延长",4,exit_score=40,peak_drop=20,weekly_exit=40)
        ]
    if module=="因子消融":
        return [
            cfg("BASE","完整EV1.0",0),
            cfg("NO_WEEK","去掉周线门槛",1,ignore_weekly=True),
            cfg("NO_RS","去掉相对强度门槛",2,ignore_rs=True),
            cfg("NO_OPP","去掉机会分门槛",3,ignore_opp=True),
            cfg("NO_RR","去掉RR门槛",4,ignore_rr=True),
            cfg("FIX_MKT","去掉市场自适应门槛",5,fixed_market_policy=True)
        ]
    raise ValueError("不支持的优化模块")

def strategy_variant_entry_ok(row,code,params):
    actual_market=float(row.get("market_score",50) or 50)
    policy_market=50.0 if params.get("fixed_market_policy") else actual_market
    p=automatic_entry_policy(policy_market)
    d=float(params.get("select_delta",0) or 0)
    buy_delta=float(params.get("buy_delta",0) or 0)
    rr_delta=float(params.get("rr_delta",0) or 0)
    liq_ok,_,_=liquidity_rule(code,row)
    if not liq_ok:
        return False

    rr=row.get("rr",np.nan)
    weekly=row.get("weekly_score",np.nan)
    tech_ok=float(row.get("score",0) or 0)>=float(p["技术"])+d
    buy_ok=float(row.get("buy_score",0) or 0)>=float(p["买点"])+buy_delta
    week_ok=True if params.get("ignore_weekly") else (
        pd.notna(weekly) and float(weekly)>=float(p["周线"])+d
    )
    rr_ok=True if params.get("ignore_rr") else (
        pd.notna(rr) and float(rr)>=max(0.5,float(p["盈亏比"])+rr_delta)
    )
    rs_ok=True if params.get("ignore_rs") else (
        float(row.get("rs_score",50) or 50)>=float(p["相对强度"])+d
    )
    opp_ok=True if params.get("ignore_opp") else (
        float(row.get("opportunity_score",0) or 0)>=float(p["机会"])+d
    )
    return bool(tech_ok and buy_ok and week_ok and rr_ok and rs_ok and opp_ok)

def strategy_variant_exit_ok(row,peak_score,params):
    score=float(row.get("score",0) or 0)
    weekly=row.get("weekly_score",np.nan)
    market_score=float(row.get("market_score",50) or 50)
    return bool(
        score<float(params.get("exit_score",45)) or
        (
            peak_score-score>=float(params.get("peak_drop",15)) and
            score<float(params.get("peak_guard_score",65))
        ) or
        (
            pd.notna(weekly) and
            float(weekly)<float(params.get("weekly_exit",45))
        ) or
        (
            market_score<float(params.get("market_exit_threshold",25)) and
            score<float(params.get("market_exit_score",60))
        )
    )

def simulate_strategy_variant(prepared_frame,code,params,cost_mult=1.0):
    m=prepared_frame
    if m is None or m.empty or len(m)<180:
        return pd.DataFrame()

    fee_bps,slip_bps=trade_cost_profile(code)
    friction=(fee_bps+slip_bps)*float(cost_mult)/10000.0
    trades=[]
    i=120
    n=len(m)

    while i<n-1:
        signal=m.iloc[i]
        if not strategy_variant_entry_ok(signal,code,params):
            i+=1
            continue

        entry_i=i+1
        entry_row=m.iloc[entry_i]
        raw_entry=(
            float(entry_row["open"])
            if pd.notna(entry_row.get("open")) and entry_row.get("open")>0
            else float(entry_row["close"])
        )
        signal_close=float(signal["close"])
        stop=signal.get("stop_ref",np.nan)
        atr=signal.get("atr14",np.nan)

        if pd.isna(stop) or raw_entry<=float(stop):
            i+=1
            continue

        gap_limit=float(params.get("max_gap_atr",1.5))
        if pd.notna(atr) and atr>0 and abs(raw_entry-signal_close)>gap_limit*float(atr):
            i+=1
            continue

        entry_fill=raw_entry*(1+friction)
        initial_risk=entry_fill-float(stop)
        if initial_risk<=0:
            i+=1
            continue

        peak_score=float(signal.get("score",0) or 0)
        exit_i=None
        raw_exit=None
        exit_reason=None
        j=entry_i

        while j<n:
            row=m.iloc[j]
            peak_score=max(peak_score,float(row.get("score",0) or 0))
            day_open=(
                float(row["open"])
                if pd.notna(row.get("open")) and row.get("open")>0
                else float(row["close"])
            )
            day_low=float(row["low"]) if pd.notna(row.get("low")) else day_open

            if day_low<=float(stop):
                raw_exit=day_open if day_open<float(stop) else float(stop)
                exit_i=j
                exit_reason="风险位"
                break

            if j<n-1 and strategy_variant_exit_ok(row,peak_score,params):
                nxt=m.iloc[j+1]
                raw_exit=(
                    float(nxt["open"])
                    if pd.notna(nxt.get("open")) and nxt.get("open")>0
                    else float(nxt["close"])
                )
                exit_i=j+1
                exit_reason="技术退出"
                break
            j+=1

        if exit_i is None:
            break

        exit_fill=raw_exit*(1-friction)
        ret=exit_fill/entry_fill-1
        r_mult=(exit_fill-entry_fill)/initial_risk
        trades.append({
            "signal_date":pd.Timestamp(signal["trade_date"]),
            "entry_date":pd.Timestamp(entry_row["trade_date"]),
            "exit_date":pd.Timestamp(m.iloc[exit_i]["trade_date"]),
            "return":ret,"R":r_mult,
            "holding_days":int(exit_i-entry_i+1),
            "opportunity":float(signal.get("opportunity_score",0) or 0),
            "risk_pct":float(initial_risk/entry_fill) if entry_fill>0 else np.nan,
            "exit_reason":exit_reason
        })
        i=exit_i+1

    return pd.DataFrame(trades)

def _strategy_experiment_period(run_id):
    conn=sqlite3.connect(DB_PATH)
    row=conn.execute(
        """SELECT MIN(period_start),MAX(period_end)
           FROM research_membership WHERE run_id=?""",
        (run_id,)
    ).fetchone()
    conn.close()
    if row and row[0] and row[1]:
        start=pd.Timestamp(row[0]); end=pd.Timestamp(row[1])
    else:
        run=get_research_run(run_id)
        end=pd.Timestamp.today().normalize()
        start=end-pd.DateOffset(years=int(run.get("years",5) or 5))
    span=max((end-start).days,10)
    train_end=start+pd.Timedelta(days=int(span*0.60))
    validation_end=start+pd.Timedelta(days=int(span*0.80))
    return start.normalize(),train_end.normalize(),validation_end.normalize(),end.normalize()

def create_strategy_experiment(research_run_id,module):
    run=get_research_run(research_run_id)
    if not run:
        raise RuntimeError("请先创建研究任务。")
    configs=strategy_variant_configs(module)
    _,train_end,val_end,_=_strategy_experiment_period(research_run_id)
    exp_id="EXP_"+datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+str(abs(hash((research_run_id,module)))%10000).zfill(4)
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO strategy_experiments(
           experiment_id,research_run_id,module,created_at,updated_at,status,cursor,total,
           train_end,validation_end,test_revealed,config_json,rule_version,note
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            exp_id,research_run_id,module,now,now,"running",0,int(run.get("total",0) or 0),
            train_end.strftime("%Y-%m-%d"),val_end.strftime("%Y-%m-%d"),0,
            json.dumps(configs,ensure_ascii=False),RULE_VERSION,
            "60%训练 + 20%验证 + 20%最终测试；实验排序只使用训练/验证区间。"
        )
    )
    conn.commit(); conn.close()
    sync_shared_experiment_safe(exp_id,research_run_id=research_run_id,mode="push")
    return exp_id

def load_strategy_experiments(research_run_id=None,limit=30):
    conn=sqlite3.connect(DB_PATH)
    if research_run_id:
        df=pd.read_sql_query(
            """SELECT * FROM strategy_experiments
               WHERE research_run_id=?
               ORDER BY created_at DESC LIMIT ?""",
            conn,params=(research_run_id,int(limit))
        )
    else:
        df=pd.read_sql_query(
            """SELECT * FROM strategy_experiments
               ORDER BY created_at DESC LIMIT ?""",
            conn,params=(int(limit),)
        )
    conn.close()
    return df

def get_strategy_experiment(experiment_id):
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        "SELECT * FROM strategy_experiments WHERE experiment_id=?",
        conn,params=(experiment_id,)
    )
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None

def _save_strategy_experiment_trades(experiment_id,config_id,code,trades):
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """DELETE FROM strategy_experiment_trades
           WHERE experiment_id=? AND config_id=? AND code=?""",
        (experiment_id,config_id,code)
    )
    if trades is not None and not trades.empty:
        rows=[]
        for _,t in trades.iterrows():
            rows.append((
                experiment_id,config_id,code,
                pd.Timestamp(t["signal_date"]).strftime("%Y-%m-%d"),
                pd.Timestamp(t["entry_date"]).strftime("%Y-%m-%d"),
                pd.Timestamp(t["exit_date"]).strftime("%Y-%m-%d"),
                float(t["R"]) if pd.notna(t.get("R")) else None,
                float(t["return"]) if pd.notna(t.get("return")) else None,
                int(t.get("holding_days",0) or 0),
                float(t["opportunity"]) if pd.notna(t.get("opportunity")) else None,
                float(t["risk_pct"]) if pd.notna(t.get("risk_pct")) else None
            ))
        conn.executemany(
            """INSERT OR REPLACE INTO strategy_experiment_trades(
               experiment_id,config_id,code,signal_date,entry_date,exit_date,
               r_multiple,return_pct,holding_days,opportunity_score,initial_risk_pct
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",rows
        )
    conn.commit(); conn.close()

def run_strategy_experiment_batch(experiment_id,batch_size=5,progress_callback=None):
    exp=get_strategy_experiment(experiment_id)
    if not exp:
        raise RuntimeError("策略实验不存在。")
    if exp.get("status")=="completed":
        return {"processed":0,"errors":[],"done":True}

    run=get_research_run(exp["research_run_id"])
    configs=json.loads(exp["config_json"])
    cursor=int(exp.get("cursor",0) or 0)
    total=int(exp.get("total",0) or 0)
    end=min(cursor+int(batch_size),total)

    conn=sqlite3.connect(DB_PATH)
    members=pd.read_sql_query(
        """SELECT * FROM research_members
           WHERE run_id=? AND seq>=? AND seq<?
           ORDER BY seq""",
        conn,params=(exp["research_run_id"],cursor,end)
    )
    conn.close()
    if members.empty:
        return {"processed":0,"errors":[],"done":cursor>=total}

    years=int(run.get("years",5) or 5)
    universe=str(run.get("universe"))
    benchmark=(
        fetch_hk_benchmark_daily(years=years)
        if universe=="港股主板"
        else fetch_benchmark_daily(years=years)
    )
    errors=[]
    processed=0

    for _,member in members.iterrows():
        seq=int(member["seq"]); code=str(member["code"]); name=str(member["name"])
        try:
            if progress_callback:
                progress_callback(seq-cursor,len(members),seq,total,code,name,"准备共享指标")
            df=fetch_stock_daily(code,years=years)
            if len(df)<180:
                raise RuntimeError("有效历史少于180个交易日")
            prepared=prepare_strategy_frame(df,benchmark,code=code)
            if prepared.empty:
                raise RuntimeError("策略指标无法构建")

            for ci,cfg in enumerate(configs,start=1):
                if progress_callback:
                    progress_callback(
                        seq-cursor,len(members),seq,total,code,name,
                        f"{cfg['label']} ({ci}/{len(configs)})"
                    )
                trades=simulate_strategy_variant(
                    prepared,code,cfg["params"],cost_mult=1.0
                )
                trades=filter_research_trades_by_membership(
                    exp["research_run_id"],code,trades
                )
                _save_strategy_experiment_trades(
                    experiment_id,cfg["config_id"],code,trades
                )
        except Exception as e:
            errors.append(f"{display_code(code)} {name}: {e}")
        finally:
            processed+=1
            new_cursor=seq+1
            status="completed" if new_cursor>=total else "running"
            conn=sqlite3.connect(DB_PATH)
            conn.execute(
                """UPDATE strategy_experiments
                   SET cursor=?,status=?,updated_at=? WHERE experiment_id=?""",
                (
                    new_cursor,status,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    experiment_id
                )
            )
            conn.commit(); conn.close()

    sync_shared_experiment_safe(
        experiment_id,research_run_id=exp["research_run_id"],mode="push"
    )
    return {"processed":processed,"errors":errors,"done":end>=total}

def _experiment_segment_metrics(df):
    if df is None or df.empty:
        return {
            "n":0,"ev":np.nan,"lcb":np.nan,"win":np.nan,
            "pf":np.nan,"avg_win":np.nan,"avg_loss":np.nan
        }
    temp=pd.DataFrame({
        "R":pd.to_numeric(df["r_multiple"],errors="coerce"),
        "holding_days":pd.to_numeric(df["holding_days"],errors="coerce"),
        "signal_date":pd.to_datetime(df["signal_date"],errors="coerce")
    }).dropna(subset=["R","signal_date"])
    ev=summarize_ev(temp)
    return {
        "n":int(ev.get("样本",0) or 0),
        "ev":ev.get("EV_R"),"lcb":ev.get("保守EV_R"),
        "win":ev.get("胜率"),"pf":ev.get("盈亏因子"),
        "avg_win":ev.get("平均盈利R"),"avg_loss":ev.get("平均亏损R")
    }

def strategy_experiment_summary(experiment_id,include_test=None):
    exp=get_strategy_experiment(experiment_id)
    if not exp:
        return pd.DataFrame(),None
    configs=json.loads(exp["config_json"])
    if include_test is None:
        include_test=bool(int(exp.get("test_revealed",0) or 0))
    train_end=pd.Timestamp(exp["train_end"])
    val_end=pd.Timestamp(exp["validation_end"])

    conn=sqlite3.connect(DB_PATH)
    trades=pd.read_sql_query(
        """SELECT * FROM strategy_experiment_trades
           WHERE experiment_id=?""",
        conn,params=(experiment_id,)
    )
    conn.close()
    if trades.empty:
        return pd.DataFrame(),None
    trades["signal_date"]=pd.to_datetime(trades["signal_date"],errors="coerce")

    rows=[]
    for cfg in configs:
        cid=cfg["config_id"]
        g=trades[trades["config_id"]==cid].copy()
        train=g[g["signal_date"]<=train_end]
        val=g[(g["signal_date"]>train_end)&(g["signal_date"]<=val_end)]
        test=g[g["signal_date"]>val_end]
        tr=_experiment_segment_metrics(train)
        va=_experiment_segment_metrics(val)
        te=_experiment_segment_metrics(test) if include_test else None

        pf=va["pf"]
        pf_term=np.log(max(float(pf),0.25)) if pd.notna(pf) and np.isfinite(pf) and pf>0 else -1.0
        sample_term=min(1.0,va["n"]/30.0)
        robust=(
            0.55*(va["ev"] if pd.notna(va["ev"]) else -2.0)+
            0.25*min(
                tr["ev"] if pd.notna(tr["ev"]) else -2.0,
                va["ev"] if pd.notna(va["ev"]) else -2.0
            )+
            0.10*pf_term+
            0.10*sample_term
        )
        row={
            "config_id":cid,"方案":cfg["label"],"顺序":int(cfg.get("order",0)),
            "训练样本":tr["n"],"训练EV(R)":tr["ev"],
            "验证样本":va["n"],"验证EV(R)":va["ev"],"验证保守EV(R)":va["lcb"],
            "验证胜率":va["win"],"验证PF":va["pf"],
            "稳健分":float(robust),"参数":json.dumps(cfg["params"],ensure_ascii=False)
        }
        if include_test and te is not None:
            row.update({
                "最终测试样本":te["n"],"最终测试EV(R)":te["ev"],
                "最终测试保守EV(R)":te["lcb"],"最终测试胜率":te["win"],
                "最终测试PF":te["pf"]
            })
        rows.append(row)

    out=pd.DataFrame(rows).sort_values("顺序").reset_index(drop=True)
    if out.empty:
        return out,None

    out["邻域验证EV"]=np.nan
    out["稳定区域"]=False
    if exp["module"]!="因子消融" and len(out)>=3:
        vals=pd.to_numeric(out["验证EV(R)"],errors="coerce")
        trains=pd.to_numeric(out["训练EV(R)"],errors="coerce")
        for i in range(len(out)):
            lo=max(0,i-1); hi=min(len(out),i+2)
            neigh=vals.iloc[lo:hi].dropna()
            neigh_train=trains.iloc[lo:hi].dropna()
            if len(neigh)>=2:
                out.loc[i,"邻域验证EV"]=float(neigh.mean())
                out.loc[i,"稳定区域"]=bool(
                    (neigh>0).all() and
                    len(neigh_train)>=2 and (neigh_train>0).all()
                )

    if "BASE" in out["config_id"].values:
        base_val=float(
            pd.to_numeric(
                out.loc[out["config_id"]=="BASE","验证EV(R)"],errors="coerce"
            ).iloc[0]
        )
        out["相对基准EV"]=pd.to_numeric(out["验证EV(R)"],errors="coerce")-base_val
    else:
        out["相对基准EV"]=np.nan

    eligible=out[
        (pd.to_numeric(out["训练EV(R)"],errors="coerce")>0)&
        (pd.to_numeric(out["验证EV(R)"],errors="coerce")>0)&
        (out["验证样本"]>=5)
    ].copy()
    if exp["module"]!="因子消融":
        stable=eligible[eligible["稳定区域"]==True]
        if not stable.empty:
            eligible=stable
    candidate=(
        eligible.sort_values(["稳健分","验证保守EV(R)"],ascending=False).iloc[0].to_dict()
        if not eligible.empty else None
    )
    return out,candidate

def reveal_strategy_test(experiment_id):
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """UPDATE strategy_experiments
           SET test_revealed=1,updated_at=? WHERE experiment_id=?""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),experiment_id)
    )
    conn.commit(); conn.close()
    exp=get_strategy_experiment(experiment_id)
    sync_shared_experiment_safe(
        experiment_id,
        research_run_id=(exp.get("research_run_id") if exp else None),
        mode="push"
    )

def save_strategy_candidate(experiment_id,config_id):
    exp=get_strategy_experiment(experiment_id)
    if not exp:
        raise RuntimeError("实验不存在")
    configs=json.loads(exp["config_json"])
    cfg=next((x for x in configs if x["config_id"]==config_id),None)
    if not cfg:
        raise RuntimeError("找不到该参数方案")
    cid="CAND_"+datetime.now().strftime("%Y%m%d_%H%M%S")
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO strategy_candidates(
           candidate_id,experiment_id,created_at,module,config_id,config_json,status,note
        ) VALUES(?,?,?,?,?,?,?,?)""",
        (
            cid,experiment_id,datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            exp["module"],config_id,json.dumps(cfg,ensure_ascii=False),
            "candidate","仅保存为候选版本；不会自动替换EV1.0实盘规则。"
        )
    )
    conn.commit(); conn.close()
    sync_shared_experiment_safe(
        experiment_id,
        research_run_id=exp.get("research_run_id"),
        mode="push"
    )
    return cid

def load_strategy_candidates(limit=30):
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        """SELECT * FROM strategy_candidates
           ORDER BY created_at DESC LIMIT ?""",
        conn,params=(int(limit),)
    )
    conn.close()
    return df

def load_forward_signals(limit=300):
    conn=sqlite3.connect(DB_PATH)
    df=pd.read_sql_query(
        """SELECT * FROM forward_signals
           ORDER BY signal_date DESC,id DESC LIMIT ?""",
        conn,params=(limit,)
    )
    conn.close()
    return df

def _evaluate_forward_signal_row(sig):
    code=normalize_code(sig["code"])
    signal_date=pd.Timestamp(sig["signal_date"])
    df=fetch_stock_daily(code,years=5)
    benchmark=fetch_benchmark_for_code(code,years=5)
    m=prepare_strategy_frame(df,benchmark,code=code)
    if m.empty:
        return "tracking",np.nan,None

    dates=pd.to_datetime(m["trade_date"])
    hits=np.where(dates.dt.normalize()==signal_date.normalize())[0]
    if len(hits)==0:
        hits=np.where(dates>=signal_date)[0]
    if len(hits)==0:
        return "tracking",np.nan,None
    signal_i=int(hits[0])
    if signal_i>=len(m)-1:
        return "tracking",np.nan,None

    entry_i=signal_i+1
    entry_row=m.iloc[entry_i]
    raw_entry=float(entry_row["open"]) if pd.notna(entry_row.get("open")) and entry_row.get("open")>0 else float(entry_row["close"])
    stop=sig.get("risk_price",np.nan)
    if pd.isna(stop) or raw_entry<=float(stop):
        return "cancelled",np.nan,pd.Timestamp(entry_row["trade_date"]).strftime("%Y-%m-%d")

    fee_bps,slip_bps=trade_cost_profile(code)
    friction=(fee_bps+slip_bps)/10000.0
    entry_fill=raw_entry*(1+friction)
    initial_risk=entry_fill-float(stop)
    if initial_risk<=0:
        return "cancelled",np.nan,pd.Timestamp(entry_row["trade_date"]).strftime("%Y-%m-%d")

    peak=float(sig.get("technical_score",m.iloc[signal_i].get("score",0)) or 0)
    last_r=np.nan
    for j in range(entry_i,len(m)):
        row=m.iloc[j]
        peak=max(peak,float(row.get("score",0) or 0))
        day_open=float(row["open"]) if pd.notna(row.get("open")) and row.get("open")>0 else float(row["close"])
        day_low=float(row["low"]) if pd.notna(row.get("low")) else day_open

        if day_low<=float(stop):
            raw_exit=day_open if day_open<float(stop) else float(stop)
            exit_fill=raw_exit*(1-friction)
            r=(exit_fill-entry_fill)/initial_risk
            return "closed",float(r),pd.Timestamp(row["trade_date"]).strftime("%Y-%m-%d")

        if j<len(m)-1 and holding_exit_condition(row,peak):
            nxt=m.iloc[j+1]
            raw_exit=float(nxt["open"]) if pd.notna(nxt.get("open")) and nxt.get("open")>0 else float(nxt["close"])
            exit_fill=raw_exit*(1-friction)
            r=(exit_fill-entry_fill)/initial_risk
            return "closed",float(r),pd.Timestamp(nxt["trade_date"]).strftime("%Y-%m-%d")

        current_exit=float(row["close"])*(1-friction)
        last_r=(current_exit-entry_fill)/initial_risk

    return "tracking",float(last_r) if pd.notna(last_r) else np.nan,None

def refresh_forward_tests(max_items=25):
    conn=sqlite3.connect(DB_PATH)
    pending=pd.read_sql_query(
        """SELECT * FROM forward_signals
           WHERE status='tracking'
           ORDER BY signal_date ASC LIMIT ?""",
        conn,params=(int(max_items),)
    )
    conn.close()
    if pending.empty:
        return 0,0,[]

    updated=closed=0
    errors=[]
    for _,sig in pending.iterrows():
        try:
            status,r_value,exit_date=_evaluate_forward_signal_row(sig)
            conn=sqlite3.connect(DB_PATH)
            conn.execute(
                """UPDATE forward_signals SET
                   status=?,realized_r=?,exit_date=?,updated_at=?
                   WHERE id=?""",
                (
                    status,
                    float(r_value) if pd.notna(r_value) else None,
                    exit_date,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    int(sig["id"])
                )
            )
            conn.commit(); conn.close()
            updated+=1
            if status=="closed":
                closed+=1
        except Exception as e:
            errors.append(f"{sig.get('name') or sig.get('code')}: {e}")
    sync_shared_light_safe(force=True)
    return updated,closed,errors

def forward_test_summary():
    df=load_forward_signals(1000)
    if df.empty:
        return {"总信号":0,"已完成":0,"跟踪中":0,"EV_R":np.nan,"胜率":np.nan},df
    closed=df[df["status"]=="closed"].copy()
    vals=pd.to_numeric(closed["realized_r"],errors="coerce").dropna()
    return {
        "总信号":int(len(df)),
        "已完成":int(len(closed)),
        "跟踪中":int((df["status"]=="tracking").sum()),
        "EV_R":float(vals.mean()) if len(vals) else np.nan,
        "胜率":float((vals>0).mean()) if len(vals) else np.nan
    },df

def history(limit=300):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM analyses ORDER BY id DESC LIMIT ?", conn, params=(limit,))
    conn.close()
    return df

init_db()

def sync_shared_light_safe(force=False):
    if not shared_db_enabled():
        return {"enabled":False,"pushed":0,"pulled":0,"errors":[]}
    now_ts=time.time()
    last=float(st.session_state.get("_shared_sync_ts",0) or 0)
    if not force and now_ts-last<60:
        return st.session_state.get("_shared_sync_result",{"enabled":True,"pushed":0,"pulled":0,"errors":[]})
    try:
        result=shared_sync_light(DB_PATH)
        st.session_state["_shared_sync_ts"]=now_ts
        st.session_state["_shared_sync_result"]=result
        return result
    except Exception as e:
        result={"enabled":True,"pushed":0,"pulled":0,"errors":[str(e)]}
        st.session_state["_shared_sync_result"]=result
        return result

def sync_shared_research_safe(run_id,mode="both"):
    if not shared_db_enabled() or not run_id:
        return {"enabled":False,"pushed":0,"pulled":0,"errors":[]}
    try:
        return shared_sync_research_run(DB_PATH,run_id,mode=mode)
    except Exception as e:
        return {"enabled":True,"pushed":0,"pulled":0,"errors":[str(e)]}

def sync_shared_experiment_safe(experiment_id,research_run_id=None,mode="both"):
    if not shared_db_enabled() or not experiment_id:
        return {"enabled":False,"pushed":0,"pulled":0,"errors":[]}
    try:
        return shared_sync_experiment(
            DB_PATH,experiment_id,research_run_id=research_run_id,mode=mode
        )
    except Exception as e:
        return {"enabled":True,"pushed":0,"pulled":0,"errors":[str(e)]}

# 轻量共享状态自动双向同步；行情K线/EV缓存始终留在每台机器本地。
_shared_boot=sync_shared_light_safe(force=False)

# 选股在独立后台线程运行；页面刷新、切换页签或做其它分析不会终止任务。
_background_scan_job=maybe_resume_or_start_daily_screener()

# COS只备份不可重建的核心业务数据。每个浏览器会话最多触发一次检查，
# 真正是否需要上传由COS端“今日是否已有备份”决定。
if cos_backup_configured() and not st.session_state.get("_cos_daily_backup_started"):
    st.session_state["_cos_daily_backup_started"]=True
    def _cos_daily_backup_worker():
        try:
            cos_maybe_daily_backup(DB_PATH,RUNTIME_MODE,keep=30)
        except Exception as ex:
            print("COS_DAILY_BACKUP_ERROR",ex)
    threading.Thread(
        target=_cos_daily_backup_worker,daemon=True,name="cos-daily-backup"
    ).start()

st.markdown("<div style='height:.15rem'></div>", unsafe_allow_html=True)
st.title("📈 日线 × 周线 中长线决策引擎")
_runtime_label="Windows计算端" if RUNTIME_MODE=="windows" else ("云端访问端" if RUNTIME_MODE=="cloud" else "本地运行")
_shared_label="共享数据已连接" if shared_db_enabled() else "本地数据模式"
st.caption(f"数据驱动版 · {_runtime_label} · {_shared_label} · 机会发现 → 买点评估 → 持仓管理 → 回测验证。")

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["📊 分析", "🔎 选股", "💼 持仓", "🧪 回测", "📚 历史", "🧠 方法", "⚙️ 设置", "🧬 研究"])

with tab7:
    st.subheader("数据设置")
    st.info(f"当前策略规则版本：{RULE_VERSION}。为避免过拟合，EV核心规则进入观察期后不因短期盈亏或候选数量随意调整。")

    st.subheader("数据架构")
    a1,a2,a3=st.columns(3)
    a1.metric("当前运行端","Windows计算端" if RUNTIME_MODE=="windows" else ("云端访问端" if RUNTIME_MODE=="cloud" else "本地运行"))
    a2.metric("核心数据库","SQLite")
    a3.metric("云端备份","腾讯云COS" if cos_backup_configured() else "待配置")

    st.success("当前采用低成本方案：SQLite作为主数据库；行情/EV缓存留在本机；不可重建的核心业务数据每天备份到腾讯云COS。")
    st.caption("PostgreSQL能力继续保留，但现在不是必需项。等以后需要多人/多节点实时双向写入时再启用。")

    st.markdown("**☁️ 腾讯云 COS 核心数据备份**")
    cos_state=cos_backup_status()
    if cos_backup_configured() and cos_state.get("enabled"):
        st.success("✅ "+cos_state.get("reason","腾讯云COS已连接"))
        cb1,cb2=st.columns(2)
        if cb1.button("☁️ 立即备份核心数据",use_container_width=True,key="cos_backup_now_btn"):
            try:
                out=cos_backup_now(DB_PATH,RUNTIME_MODE,keep=30)
                st.success(
                    f"备份完成：{out.get('key','')} · "
                    f"{out.get('size',0)/1024/1024:.2f} MB · "
                    f"自动清理旧备份 {out.get('pruned',0)} 个"
                )
            except Exception as e:
                st.error(f"COS备份失败：{e}")

        if cb2.button("🔄 刷新COS备份列表",use_container_width=True,key="cos_refresh_list_btn"):
            st.session_state.pop("_cos_backup_list",None)

        try:
            if "_cos_backup_list" not in st.session_state:
                st.session_state["_cos_backup_list"]=cos_list_backups(max_keys=60)
            cos_rows=st.session_state.get("_cos_backup_list") or []
        except Exception as e:
            cos_rows=[]
            st.warning(f"读取COS备份列表失败：{e}")

        if cos_rows:
            backup_labels={
                r["key"]:f"{r.get('last_modified','')} · {r.get('device','')} · {r.get('size',0)/1024/1024:.2f} MB"
                for r in cos_rows
            }
            restore_key=st.selectbox(
                "选择一个云端备份",
                [r["key"] for r in cos_rows],
                format_func=lambda x:backup_labels.get(x,x),
                key="cos_restore_key"
            )
            confirm_restore=st.checkbox(
                "我确认用所选备份覆盖当前核心业务数据",
                value=False,key="cos_restore_confirm"
            )
            if st.button(
                "♻️ 恢复所选核心数据",
                use_container_width=True,
                disabled=not confirm_restore,
                key="cos_restore_btn"
            ):
                try:
                    restored=cos_restore_core(DB_PATH,restore_key)
                    st.success(
                        "恢复完成："+
                        " · ".join([f"{k}:{v}" for k,v in restored.items()])
                    )
                    st.session_state.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"COS恢复失败：{e}")
        else:
            st.caption("COS中暂未发现备份。点击“立即备份核心数据”生成第一份。")
    else:
        st.warning("COS备份代码已经启用，但还没有配置腾讯云COS密钥/桶信息，所以目前不会上传云端。")
        st.caption(
            "Render环境变量需要配置：TENCENT_COS_SECRET_ID、TENCENT_COS_SECRET_KEY、"
            "TENCENT_COS_REGION、TENCENT_COS_BUCKET。配置后系统每天自动备份1次，并保留最近30份。"
        )

    if shared_db_enabled():
        with st.expander("高级：PostgreSQL共享数据库（当前不建议启用）"):
            st.caption("只有将来需要Windows与云端同时实时写入同一数据库时才需要。")
            ss1,ss2=st.columns(2)
            if ss1.button("☁️ 立即同步PostgreSQL",use_container_width=True):
                out=sync_shared_light_safe(force=True)
                if out.get("errors"):
                    st.warning("同步完成，但存在异常："+"；".join(out["errors"][:5]))
                else:
                    st.success(f"同步完成：上传 {out.get('pushed',0)} 行 · 下载 {out.get('pulled',0)} 行。")
            if ss2.button("🔌 测试PostgreSQL",use_container_width=True):
                chk=shared_db_status()
                if chk.get("enabled"):
                    st.success(chk.get("reason","PostgreSQL 已连接"))
                else:
                    st.error(chk.get("reason","共享数据库未连接"))

    st.markdown("**📡 行情数据源优先级**")
    if ifind_configured():
        ifs=ifind_status(test_data=False)
        if ifs.get("ok"):
            st.success("✅ iFinD HTTP API 已配置：A股/港股日K与原生周K优先使用 iFinD；A股基准指数也优先使用 iFinD。")
        else:
            st.warning("iFinD 已配置但当前鉴权异常："+str(ifs.get("message","未知错误")))
    else:
        st.warning("尚未配置 iFinD Refresh Token；系统当前会继续使用 AKShare / BaoStock 容灾。")
        st.caption("在 Render 环境变量中添加 IFIND_REFRESH_TOKEN；不要把 token 写进GitHub或聊天记录。")

    if st.button("🔌 测试 iFinD 行情接口",use_container_width=True,key="ifind_test_btn"):
        chk=ifind_status(test_data=True)
        if chk.get("ok"):
            st.success(chk.get("message","iFinD连接成功"))
        else:
            st.error(chk.get("message","iFinD连接失败"))

    st.info("当前优先级：iFinD → AKShare → BaoStock。iFinD不可用时自动降级；BaoStock只作为最后兜底，避免再次因黑名单阻塞系统。")
    st.info("周线口径：原生周K为主；日K聚合周K做交叉验证。一致性低时会在分析/选股结果中提示。")
    st.caption("港股市场环境仍以恒生指数为基准；A股以沪深300为基准。首次启用iFinD会建立独立缓存，之后主要做增量更新。")

    st.subheader("本地行情缓存")
    cs = market_cache_stats()
    c1,c2,c3 = st.columns(3)
    c1.metric("已缓存标的",f"{cs['stocks']:,}")
    c2.metric("日线记录",f"{cs['rows']:,}")
    c3.metric("数据库大小",f"{cs['db_mb']:.1f} MB")
    st.caption(f"缓存区间：{cs['min_date']} ～ {cs['max_date']}。首次下载历史，以后主要补最新交易日。")
    if st.button("🗑️ 清空行情缓存",use_container_width=True):
        clear_market_cache()
        st.success("行情缓存已清空。")
        st.rerun()
    if RUNTIME_MODE=="cloud":
        st.warning("云端行情/EV缓存仍位于Render本机，重新部署时可能清空；这是设计行为，因为行情可以重新下载。核心业务数据在启用共享PostgreSQL后不会依赖这份缓存。")
    else:
        st.caption(f"本地数据库：{DB_PATH}。Windows行情缓存长期保存在本机，用于加速全市场扫描与回测。")
    st.markdown("**核心数据备份**")
    backup_pos=load_positions(False)
    backup_ft=load_forward_signals(5000)
    bkp1,bkp2=st.columns(2)
    bkp1.download_button(
        "⬇️ 导出全部持仓",
        backup_pos.to_csv(index=False).encode("utf-8-sig"),
        "positions_backup.csv","text/csv",use_container_width=True
    )
    bkp2.download_button(
        "⬇️ 导出Forward Test",
        backup_ft.to_csv(index=False).encode("utf-8-sig"),
        "forward_test_backup.csv","text/csv",use_container_width=True
    )
    st.caption("持仓截图识别使用已配置的DeepSeek视觉接口；截图只提取持仓字段，不参与技术评分。")
    st.markdown("iPhone：Safari打开网址 → 分享 → **添加到主屏幕**。Windows：使用仓库中的 **start_windows.bat** 启动同一套系统。")

with tab6:
    st.subheader("这套系统怎么做决策")
    st.markdown("""
**核心框架：四层证据，而不是指标堆砌。每一项都是100分制。**

1. **趋势分（满分100）**：BOLL中轨方向、价格相对中轨、带宽状态。  
2. **动能分（满分100）**：MACD零轴、DIF方向、金叉/死叉、柱体加减速。  
3. **周线分（满分100）**：周线是中长线体系的必选过滤器，所有分析、选股、回测都必须有周线。  
4. **量能分（满分100）**：成交量与背离，只做确认，不抢主导权。成交量读取 **VOL柱 + MA5 + MA10**。  

**总技术分也是100分制：**
- 有周线：趋势38% + 动能30% + 周线22% + 量能10%
- 中长线模式必须有确认周线，不再提供“无周线”评分。  

**选股目标：寻找交易机会，不是寻找最高技术分。**

- **技术分**：这只股票的趋势/动能是否值得关注。
- **买点分**：当前价格位置是否适合介入，越追高分数越低。
- **盈亏比**：以中轨/20日低点作为风险参考，以20日高点/BOLL上轨作为压力参考。
- **机会分**：只描述当前结构，权重为技术30% + 买点30% + 结构盈亏比15% + 市场15% + 相对强度10%；不再把历史结果重复塞进机会分。
- **真实交易EV**：历史信号按同一套“次日入场 → 初始风险位 → 技术分/周线/市场退出”逐笔模拟，以R倍数衡量。
- **自动门槛**：用户不手调技术分/买点分/盈亏比。门槛只随市场环境按预设规则变化，不会因为当天没有候选就临时放宽。
- **市场环境**：A股以沪深300、港股以恒生指数的BOLL、MACD、MA60及20/60日收益评估“顺风/中性/偏弱/逆风”。
- **相对强度**：A股相对沪深300、港股相对恒生指数比较20/60日表现，避免只买“随市场被动上涨”的股票。
- **历史EV**：不再用“20/40/60日后是否上涨”冒充策略胜率。历史信号按同一套入场、风险位和技术退出规则逐笔模拟，统一换算为R倍数。
- **保守EV**：历史平均R减去统计误差形成保守下界；只有点估计为正不够。
- **成本压力测试**：同时计算2倍交易成本/滑点下的EV，检验优势是否脆弱。
- **OOS验证**：固定规则按时间顺序滚动验证，不用测试段反向调参数。
- **周线**：原生周K作为主依据，日K聚合周K做交叉验证；硬性决策只使用已确认周线，未完成的当周K不参与选股阈值。
- **流动性**：A股默认20日中位成交额≥5000万元，港股≥2000万元。
- **回测**：收盘形成信号，下一交易日执行；止损考虑跳空，不假设一定能按风险位成交。
- **持仓管理**：买入后“买点分”的意义下降，核心转为技术分及其变化。≥78强势持有、65–77持有、55–64谨慎持有、45–54减仓候选、<45退出候选；技术分较峰值快速回落、周线转弱或大盘逆风会降档。

**量化研究层**
- **历史股票池**：A股研究按月读取当时的沪深300/中证500成分或当时在市股票，信号必须处于历史成员区间，降低幸存者偏差；港股当前仍受免费历史股票池数据限制。
- **Purged Walk-Forward**：训练与测试之间设置净化期和Embargo，降低重叠持仓造成的信息泄漏。
- **Bootstrap EV**：采用月度块重采样估计EV分布与 P(EV>0)，不只看一个均值。
- **EV校准**：每笔交易的预测EV只使用当时已经结束的历史交易，检查预测EV的排序能力。
- **日级组合回测**：每日按真实收盘盯市，计算CAGR、最大回撤、Sharpe、Sortino、Calmar和换手。
- **风险预算仓位**：默认每笔承担0.5% NAV风险，按技术失效距离反推仓位，单票上限10%、最多10仓。
- **策略优化实验室**：每次只允许研究一个模块（选股门槛 / 买入质量 / 持仓退出 / 因子消融），固定60%训练、20%验证、20%最终测试。
- **参数平台优先**：不选择单一历史最高点；要求相邻参数在训练与验证区间共同保持正EV，寻找稳定区域。
- **最终测试锁定**：参数筛选只使用训练+验证数据；最后20%默认不可见，实验完成并停止调参后才解锁。
- **候选版本机制**：实验结果只能保存为候选，不会自动替换EV1.0。正式升级必须再经过最终测试与Forward Test。

**规则版本与冻结原则**
- 当前版本：**EV1.0**。Forward Test会记录规则版本；后续若改变核心入场/退出逻辑，应升级版本而不是覆盖历史结果。
- 不因为某天“没有候选”就降低阈值，也不因为连续几笔亏损就临时改规则。

**关键原则**
- 零轴下金叉 = 先看修复，不把反弹当反转。
- BOLL中轨向下时，买入类信号天然降级。
- 日线强、周线弱 = 先观察，不把局部反弹当中长线主升。
- 技术面只负责“什么时候风险收益更好”，不替代基本面和估值判断。
""")
    st.warning("技术分/机会分只是结构描述，不再当作盈利概率。系统核心改为真实交易净EV(R)、保守EV、成本压力EV与OOS稳定性；样本不足时只能观察。")

with tab1:
    st.subheader("股票分析")
    st.caption("单股与批量分析共用同一套EV1.0规则。批量模式可从自选股/持仓/行情截图中识别多只A股或港股，并逐只生成具体操作策略。")

    single_tab,batch_tab=st.tabs(["📌 单股分析","🧺 批量分析"])

    with single_tab:
        a1,a2=st.columns([1.35,1])
        with a1:
            auto_code=st.text_input(
                "股票代码或名称",
                placeholder="例如 600519 / 贵州茅台 / 0700 / 腾讯控股",
                key="auto_code"
            )
        with a2:
            auto_horizon=st.selectbox(
                "持有周期",["2–8周","2–6个月","6–18个月"],index=1,key="auto_horizon"
            )

        a3,a4=st.columns(2)
        with a3:
            auto_position=st.selectbox(
                "当前仓位",["未持有","轻仓≤25%","中等25–50%","重仓>50%"],
                key="auto_position"
            )
        with a4:
            auto_fund=st.checkbox("基本面/估值已验证",value=False,key="auto_fund")

        act1,act2=st.columns([2,1])
        run_analysis=act1.button(
            "⚡ 生成 / 替换当前分析",
            type="primary",use_container_width=True,key="run_single_analysis"
        )
        clear_analysis=act2.button(
            "🧹 清空当前结果",use_container_width=True,key="clear_single_analysis"
        )

        if clear_analysis:
            st.session_state.pop("last_report",None)
            st.rerun()

        if run_analysis:
            if not auto_code.strip():
                st.error("请输入A股或港股代码/名称。")
            else:
                with st.spinner("正在快速读取当前结构；历史EV如未缓存会转后台更新..."):
                    t0=time.perf_counter()
                    bs_open=False
                    try:
                        if not ifind_configured():
                            bs_open=bool(bs_login(retries=1,strict=False))
                        code,name=resolve_symbol_input(auto_code)

                        if ifind_configured():
                            prefetch_ifind_analysis_bundle(
                                code,daily_years=2,weekly_years=3
                            )

                        df_auto=fetch_stock_daily(code,years=2)
                        benchmark_df=fetch_benchmark_for_code(code,years=2)
                        try:
                            native_weekly=fetch_stock_weekly(code,years=3)
                        except Exception:
                            native_weekly=None

                        ev_cached,ev_age=get_recent_cached_ev(code,max_age_days=7)
                        report=deterministic_report(
                            code,name,df_auto,auto_position,auto_fund,benchmark_df,
                            compute_ev=False,
                            native_weekly_df=native_weekly,
                            ev_override=ev_cached
                        )
                        report["ev_cache_age_days"]=ev_age
                        if ev_cached is None and report.get("opportunity_label")!="不通过":
                            started=start_analysis_ev_background(code)
                            report["ev_pending"]=bool(started or analysis_ev_running(code))

                        report["analysis_seconds"]=round(time.perf_counter()-t0,2)
                        prev=previous(report["symbol"])
                        if prev and prev.get("score") is not None:
                            try:
                                report["delta"]=report["score"]-float(prev.get("score"))
                            except Exception:
                                pass
                        persist_analysis_report(
                            report,code,auto_horizon,auto_position
                        )
                        report.pop("_df",None)
                        st.session_state["last_report"]=report
                        st.rerun()
                    except Exception as e:
                        st.error(f"自动分析失败：{e}")
                    finally:
                        try:
                            if bs_open:
                                bs_logout_safe()
                        except Exception:
                            pass

        st.divider()
        st.subheader("当前分析结果")
        render_cockpit(st.session_state.get("last_report"))

    with batch_tab:
        st.markdown("#### 1. 导入股票")
        st.caption("可上传券商/行情App的自选股、持仓、排行或选股截图。截图只用于识别股票代码/名称，技术分析仍使用实时行情数据。")
        batch_images=st.file_uploader(
            "上传股票列表截图",
            type=["png","jpg","jpeg","webp"],
            accept_multiple_files=True,
            key="batch_symbol_images"
        )
        bi1,bi2=st.columns([1.3,1])
        recognize_batch=bi1.button(
            "📷 识别截图中的股票",
            type="primary",use_container_width=True,key="recognize_batch_symbols"
        )
        bi2.caption("支持多张截图；识别后可人工删除、修改或补充。")

        if recognize_batch:
            if not batch_images:
                st.warning("请先上传至少一张截图。")
            else:
                with st.spinner("正在识别截图中的A股/港股..."):
                    try:
                        recognized=extract_batch_symbols_from_images(batch_images)
                        if recognized.empty:
                            st.warning("没有识别到可用股票，请换更清晰的截图或手工粘贴代码。")
                        else:
                            st.session_state["batch_symbols_df"]=recognized
                            st.success(f"已识别 {len(recognized)} 只股票。")
                    except Exception as e:
                        st.error(f"截图识别失败：{e}")

        manual_symbols=st.text_area(
            "也可以直接粘贴股票代码/名称",
            placeholder="每行一个，或用逗号分隔，例如：\n600519\n腾讯控股\n300750",
            height=105,key="batch_manual_symbols"
        )
        if st.button("➕ 加入手工股票",use_container_width=True,key="add_manual_batch_symbols"):
            tokens=[
                x.strip() for x in re.split(r"[\n,，;；]+",manual_symbols or "")
                if x.strip()
            ]
            if tokens:
                old=st.session_state.get(
                    "batch_symbols_df",
                    pd.DataFrame(columns=["分析","代码或名称","名称","市场"])
                )
                add=pd.DataFrame([
                    {"分析":True,"代码或名称":x,"名称":"","市场":""}
                    for x in tokens
                ])
                merged=pd.concat([old,add],ignore_index=True)
                merged["_key"]=merged["代码或名称"].astype(str).str.strip().str.upper()
                merged=merged[merged["_key"].ne("")].drop_duplicates("_key").drop(columns="_key")
                st.session_state["batch_symbols_df"]=merged.reset_index(drop=True)

        symbols_df=st.session_state.get(
            "batch_symbols_df",
            pd.DataFrame(columns=["分析","代码或名称","名称","市场"])
        )
        if not symbols_df.empty:
            edited_symbols=st.data_editor(
                symbols_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="batch_symbols_editor",
                column_config={
                    "分析":st.column_config.CheckboxColumn("分析",default=True),
                    "代码或名称":st.column_config.TextColumn("代码或名称",required=True),
                    "名称":st.column_config.TextColumn("识别名称"),
                    "市场":st.column_config.TextColumn("市场")
                }
            )
            st.session_state["batch_symbols_df"]=edited_symbols

            st.markdown("#### 2. 批量分析设置")
            bc1,bc2,bc3,bc4=st.columns(4)
            with bc1:
                batch_horizon=st.selectbox(
                    "持有周期",["2–8周","2–6个月","6–18个月"],index=1,
                    key="batch_horizon"
                )
            with bc2:
                batch_position=st.selectbox(
                    "统一当前仓位",
                    ["未持有","轻仓≤25%","中等25–50%","重仓>50%"],
                    key="batch_position"
                )
            with bc3:
                batch_fund=st.checkbox(
                    "基本面/估值均已验证",value=False,key="batch_fund"
                )
            with bc4:
                batch_limit=st.selectbox(
                    "本次最多分析",[10,20,30],index=1,key="batch_analysis_limit"
                )

            ba1,ba2=st.columns([2,1])
            run_batch=ba1.button(
                "⚡ 批量生成分析 + 操作策略",
                type="primary",use_container_width=True,key="run_batch_analysis"
            )
            clear_batch=ba2.button(
                "🧹 清空批量结果",use_container_width=True,key="clear_batch_results"
            )
            if clear_batch:
                st.session_state.pop("batch_reports",None)
                st.rerun()

            if run_batch:
                selected=edited_symbols[
                    edited_symbols["分析"].fillna(False).astype(bool)
                ].copy()
                selected=selected[
                    selected["代码或名称"].astype(str).str.strip().ne("")
                ].head(int(batch_limit))
                if selected.empty:
                    st.warning("请至少勾选一只股票。")
                else:
                    progress=st.progress(0.0,text="准备批量分析...")
                    status=st.empty()
                    reports=[]
                    errors=[]
                    resolved=[]
                    benchmark_cache={}
                    bs_open=False
                    t0=time.perf_counter()
                    try:
                        if not ifind_configured():
                            bs_open=bool(bs_login(retries=1,strict=False))

                        # 先解析代码，再一次性预取日K和原生周K，避免逐只发网络请求。
                        for _,row in selected.iterrows():
                            raw=str(row.get("代码或名称","")).strip()
                            try:
                                code,name=resolve_symbol_input(raw)
                                resolved.append((raw,code,name))
                            except Exception as ex:
                                errors.append(f"{raw}: {ex}")

                        if ifind_configured() and resolved:
                            codes=[x[1] for x in resolved]
                            status.caption(f"正在批量预取 {len(codes)} 只股票日K/周K…")
                            prefetch_ifind_daily(codes,years=2)
                            prefetch_ifind_weekly(codes,years=3)

                        total_resolved=len(resolved)
                        for idx,(raw,code,name) in enumerate(resolved,start=1):
                            status.caption(f"正在分析 {idx}/{total_resolved}：{name} {display_code(code)}")
                            try:
                                market=market_of_code(code)
                                if market not in benchmark_cache:
                                    benchmark_cache[market]=fetch_benchmark_for_code(code,years=2)
                                df_auto=fetch_stock_daily(code,years=2)
                                try:
                                    native_weekly=fetch_stock_weekly(code,years=3)
                                except Exception:
                                    native_weekly=None

                                ev_cached,ev_age=get_recent_cached_ev(code,max_age_days=7)
                                report=deterministic_report(
                                    code,name,df_auto,batch_position,batch_fund,
                                    benchmark_cache[market],
                                    compute_ev=False,
                                    native_weekly_df=native_weekly,
                                    ev_override=ev_cached
                                )
                                report["ev_cache_age_days"]=ev_age
                                if ev_cached is None and report.get("opportunity_label")!="不通过":
                                    started=start_analysis_ev_background(code)
                                    report["ev_pending"]=bool(started or analysis_ev_running(code))

                                prev=previous(report["symbol"])
                                if prev and prev.get("score") is not None:
                                    try:
                                        report["delta"]=report["score"]-float(prev.get("score"))
                                    except Exception:
                                        pass
                                persist_analysis_report(
                                    report,code,batch_horizon,batch_position
                                )
                                report.pop("_df",None)
                                reports.append(report)
                            except Exception as ex:
                                errors.append(f"{raw}: {ex}")
                            progress.progress(
                                idx/max(total_resolved,1),
                                text=f"批量分析 {idx}/{total_resolved} · 成功 {len(reports)} · 失败 {len(errors)}"
                            )
                    finally:
                        try:
                            if bs_open:
                                bs_logout_safe()
                        except Exception:
                            pass

                    elapsed=round(time.perf_counter()-t0,1)
                    for r in reports:
                        r["batch_elapsed_seconds"]=elapsed
                    st.session_state["batch_reports"]=reports
                    st.session_state["batch_analysis_errors"]=errors
                    if reports:
                        st.success(f"完成 {len(reports)} 只股票快速分析，用时约 {elapsed:.1f} 秒。未缓存的5年EV已转后台计算。")
                    if errors:
                        st.warning("部分股票失败："+"；".join(errors[:6]))
                    st.rerun()
        else:
            edited_symbols=pd.DataFrame()
            st.info("请先上传截图识别股票，或直接粘贴股票代码/名称。")

        reports=st.session_state.get("batch_reports") or []
        if reports:
            st.divider()
            st.markdown("#### 3. 批量决策总览")
            summary_rows=[]
            for r in reports:
                ev=r.get("ev") or {}
                op=r.get("operation_strategy") or {}
                summary_rows.append({
                    "股票":r.get("symbol",""),
                    "当前动作":op.get("action","—"),
                    "技术分":r.get("score"),
                    "买点分":r.get("buy_score"),
                    "周线":r.get("weekly_score"),
                    "RR":r.get("rr"),
                    "净EV(R)":ev.get("EV_R"),
                    "保守EV(R)":ev.get("保守EV_R"),
                    "机会":r.get("opportunity_label"),
                    "市场":f"{r.get('market_regime','')} {r.get('market_score',0):.0f}",
                    "现价":r.get("latest_close"),
                    "风险位":r.get("risk_price"),
                    "压力位":r.get("target_price")
                })
            summary_df=pd.DataFrame(summary_rows)
            st.dataframe(
                summary_df,use_container_width=True,hide_index=True,
                column_config={
                    "技术分":st.column_config.NumberColumn(format="%.0f"),
                    "买点分":st.column_config.NumberColumn(format="%.0f"),
                    "周线":st.column_config.NumberColumn(format="%.0f"),
                    "RR":st.column_config.NumberColumn(format="%.2f"),
                    "净EV(R)":st.column_config.NumberColumn(format="%+.2f"),
                    "保守EV(R)":st.column_config.NumberColumn(format="%+.2f"),
                    "现价":st.column_config.NumberColumn(format="%.2f"),
                    "风险位":st.column_config.NumberColumn(format="%.2f"),
                    "压力位":st.column_config.NumberColumn(format="%.2f")
                }
            )

            st.markdown("#### 4. 每只股票具体策略")
            for r in reports:
                op=r.get("operation_strategy") or {}
                title=f"{op.get('action','—')}｜{r.get('symbol','')}"
                with st.expander(title,expanded=False):
                    render_cockpit(r)

    st.divider()
    st.subheader("最近分析")
    recent=recent_analyses(20)
    if recent.empty:
        st.caption("暂无历史分析。")
    else:
        recent_show=recent.rename(columns={
            "created_at":"时间","symbol":"股票","market":"市场","horizon":"周期",
            "position_state":"仓位","state":"状态","rating":"评级",
            "score":"技术分","trend_score":"趋势","momentum_score":"动能",
            "weekly_score":"周线","confirm_score":"量能"
        })
        show_cols=[
            "时间","股票","市场","状态","技术分","趋势","动能","周线","量能","周期","仓位"
        ]
        st.dataframe(
            recent_show[[x for x in show_cols if x in recent_show.columns]],
            use_container_width=True,hide_index=True
        )
        st.caption("单股与批量分析都会进入最近分析记录。")

with tab2:
    st.subheader("自动选股")
    st.caption("现在分成两条完全独立的任务线：**临时手动扫描** 和 **每日定时扫描**。两类任务各自保存进度、结果和历史，不再互相占用“当天任务名额”。手动扫描优先，运行时会暂挂每日任务；手动完成后每日任务自动续跑。")

    repair_stale_screener_jobs()
    settings=get_screener_settings()

    def _render_screener_panel(job,panel_key,title):
        st.markdown(f"### {title}")
        if not job:
            st.caption("暂无任务。")
            return

        job_id=str(job["job_id"])
        status=str(job.get("status",""))
        cursor=int(job.get("cursor",0) or 0)
        total=int(job.get("total",0) or 0)
        pct=(cursor/total) if total else 0.0
        status_label={
            "queued":"排队中",
            "running":"后台运行中",
            "paused":"断点暂停",
            "paused_manual":"被临时手动任务暂挂",
            "completed":"已完成"
        }.get(status,status)

        j1,j2,j3,j4=st.columns(4)
        j1.metric("状态",status_label)
        j2.metric("进度",f"{cursor:,}/{total:,}" if total else f"{cursor:,}/—")
        j3.metric("股票池",str(job.get("universe","")))
        j4.metric("交易日",str(job.get("trade_date","")))
        st.progress(
            min(max(pct,0.0),1.0),
            text=f"{title}进度 {pct:.1%}" if total else "正在准备股票池…"
        )

        if job.get("market_score") is not None:
            p=automatic_entry_policy(float(job["market_score"]))
            st.info(
                f"{job.get('benchmark_name','大盘')}：{job.get('market_regime','')} "
                f"{float(job['market_score']):.0f}/100；本轮门槛："
                f"技≥{p['技术']} / 买≥{p['买点']} / 周≥{p['周线']} / "
                f"RR≥{p['盈亏比']:.2f} / RS≥{p['相对强度']} / 机会≥{p['机会']}。"
            )

        stats={}
        try:
            stats=json.loads(job.get("stats_json") or "{}")
        except Exception:
            stats={}
        if stats:
            st.caption(
                f"累计扫描 {stats.get('扫描',0)} · 结构初筛 {stats.get('快速初筛通过',0)} · "
                f"EV计算 {stats.get('EV阶段',0)} · EV缓存 {stats.get('EV缓存命中',0)} · "
                f"优先 {stats.get('优先机会',0)} · 观察 {stats.get('候选观察',0)} · "
                f"数据异常 {stats.get('数据异常',0)}"
            )

        if job.get("error"):
            st.warning(f"最近异常：{job['error']}")

        if status=="paused":
            if st.button(
                "▶️ 从断点续跑",
                use_container_width=True,
                key=f"resume_{panel_key}_{job_id}"
            ):
                if str(job.get("job_type"))=="manual":
                    pause_scheduled_for_manual()
                elif active_screener_job("manual"):
                    st.warning("当前有临时手动任务运行，每日任务会继续保持暂停。")
                    st.stop()
                _update_screener_job(job_id,status="queued",error=None)
                start_screener_job_background(job_id)
                st.rerun()
        elif status=="paused_manual":
            st.info("⏸️ 每日任务已为临时手动扫描让路；手动任务结束后会自动继续。")
        elif status=="running":
            st.success("✅ 后台运行中。可以切换到分析、持仓或研究页面。")
        elif status=="completed":
            st.success("✅ 本轮扫描已完成。完成的任务不会阻止你发起下一次扫描。")

        result=load_screener_job_results(job_id)
        if isinstance(result,pd.DataFrame) and not result.empty:
            n_priority=int((result["机会状态"]=="优先机会").sum()) if "机会状态" in result.columns else 0
            n_watch=int((result["机会状态"]=="候选观察").sum()) if "机会状态" in result.columns else 0
            st.markdown(f"#### 候选结果 · {len(result)}只（优先 {n_priority} / 观察 {n_watch}）")
            pick=result.head(150).drop(columns=["_market_score"],errors="ignore").copy()
            pick.insert(0,"加入持仓",False)
            edited_pick=st.data_editor(
                pick,use_container_width=True,hide_index=True,
                disabled=[x for x in pick.columns if x!="加入持仓"],
                column_config={
                    "加入持仓":st.column_config.CheckboxColumn("加入持仓")
                },
                key=f"screen_pick_editor_{panel_key}_{job_id}"
            )
            ab1,ab2=st.columns(2)
            add_selected=ab1.button(
                "➕ 加入勾选持仓",
                type="primary",use_container_width=True,
                key=f"add_selected_{panel_key}_{job_id}"
            )
            add_priority=ab2.button(
                "➕ 全部优先机会加入持仓",
                use_container_width=True,
                key=f"add_priority_{panel_key}_{job_id}"
            )
            if add_selected or add_priority:
                chosen=(
                    result[result["机会状态"]=="优先机会"].copy()
                    if add_priority
                    else edited_pick[edited_pick["加入持仓"]==True].drop(columns=["加入持仓"],errors="ignore")
                )
                if chosen.empty:
                    st.warning("没有可加入的股票。")
                else:
                    try:
                        bs_login()
                        ok,errs=add_screener_rows_to_positions(chosen)
                        if ok:
                            st.success(f"已加入/更新 {ok} 只持仓。")
                        if errs:
                            st.warning("部分失败："+"；".join(errs[:8]))
                    except Exception as e:
                        st.error(f"加入持仓失败：{e}")
                    finally:
                        try: bs_logout_safe()
                        except Exception: pass

            st.download_button(
                "⬇️ 导出本轮候选",
                result.drop(columns=["_market_score"],errors="ignore").to_csv(index=False).encode("utf-8-sig"),
                f"screen_candidates_{job_id}.csv","text/csv",
                use_container_width=True,key=f"download_{panel_key}_{job_id}"
            )
        elif cursor>0:
            st.caption("当前已扫描部分暂无满足EV1.0条件的候选。")

    manual_tab,daily_tab=st.tabs(["⚡ 临时手动扫描","🕒 每日定时扫描"])

    with manual_tab:
        st.markdown("#### 临时手动扫描")
        st.caption("这是你随时主动发起的扫描，与每日自动任务完全分开。即使今天的每日任务已经完成，也可以继续发起任意次数的临时扫描。")
        m1,m2,m3=st.columns(3)
        with m1:
            manual_universe=st.selectbox(
                "手动股票池",
                ["全A股（沪深）","沪深300","中证500","上证50","港股主板"],
                index=3,key="manual_scan_universe"
            )
        with m2:
            manual_batch=st.selectbox(
                "后台批次",[20,50,100],
                index=1,key="manual_scan_batch"
            )
        with m3:
            manual_exclude_st=st.checkbox(
                "排除ST/*ST",value=True,key="manual_scan_exclude_st"
            )

        mm1,mm2=st.columns([1.5,1])
        start_manual=mm1.button(
            "🚀 发起新的临时扫描",
            type="primary",use_container_width=True,
            key="start_manual_scan"
        )
        mm2.caption("手动任务优先；如果每日任务正在跑，会先把每日任务暂停在当前断点。")

        if start_manual:
            active_manual=active_screener_job("manual")
            if active_manual:
                st.warning(f"已有临时手动任务 {active_manual[0]} 正在运行。")
            else:
                try:
                    pause_scheduled_for_manual()
                    jid=create_screener_job(
                        manual_universe,manual_exclude_st,manual_batch,
                        trade_date=pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d"),
                        job_type="manual"
                    )
                    start_screener_job_background(jid)
                    st.session_state["active_manual_screener_job"]=jid
                    st.success("新的临时扫描已启动。")
                    st.rerun()
                except Exception as e:
                    st.error(f"启动临时扫描失败：{e}")

        manual_job=latest_screener_job("manual")
        _render_screener_panel(manual_job,"manual","临时手动任务")

    with daily_tab:
        st.markdown("#### 每日定时扫描设置")
        st.caption("每日任务只负责固定日常扫描；它不会因为你今天做过临时扫描而跳过，也不会阻止你继续手动发起新的扫描。")
        d1,d2,d3=st.columns(3)
        daily_universes=["全A股（沪深）","沪深300","中证500","上证50","港股主板"]
        with d1:
            daily_universe=st.selectbox(
                "每日股票池",daily_universes,
                index=(daily_universes.index(settings["universe"]) if settings["universe"] in daily_universes else 2),
                key="daily_scan_universe"
            )
        with d2:
            daily_batch=st.selectbox(
                "每日后台批次",[20,50,100],
                index=([20,50,100].index(settings["batch_size"]) if settings["batch_size"] in [20,50,100] else 1),
                key="daily_scan_batch"
            )
        with d3:
            daily_exclude_st=st.checkbox(
                "每日排除ST/*ST",
                value=bool(settings["exclude_st"]),
                key="daily_scan_exclude_st"
            )

        da1,da2=st.columns(2)
        with da1:
            auto_daily=st.checkbox(
                "每天自动运行一次",
                value=bool(settings["auto_daily"]),
                key="daily_auto_enabled"
            )
        with da2:
            hours=[16,17,18,19,20,21]
            run_hour=st.selectbox(
                "北京时间几点后启动",hours,
                index=(hours.index(settings["run_after_hour"]) if settings["run_after_hour"] in hours else 2),
                key="daily_run_hour"
            )

        ds1,ds2,ds3=st.columns([1.2,1.2,1])
        save_auto=ds1.button(
            "💾 保存每日设置",
            use_container_width=True,key="save_daily_scan_settings"
        )
        run_daily_now=ds2.button(
            "▶️ 立即运行/续跑每日任务",
            use_container_width=True,key="run_daily_now"
        )
        refresh_daily=ds3.button(
            "🔄 刷新状态",
            use_container_width=True,key="refresh_daily_status"
        )

        if save_auto:
            save_screener_settings(
                auto_daily,daily_universe,daily_exclude_st,daily_batch,run_hour
            )
            st.success("每日扫描设置已保存。")
            st.rerun()

        if run_daily_now:
            if active_screener_job("manual"):
                st.warning("当前有临时手动任务运行。每日任务会在手动任务完成后自动继续。")
            else:
                daily_job=latest_screener_job("scheduled")
                today=pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d")
                if (
                    daily_job
                    and str(daily_job.get("trade_date"))==today
                    and str(daily_job.get("status")) in ("queued","running","paused","paused_manual")
                ):
                    jid=str(daily_job["job_id"])
                    _update_screener_job(jid,status="queued",error=None)
                elif (
                    daily_job
                    and str(daily_job.get("trade_date"))==today
                    and str(daily_job.get("status"))=="completed"
                ):
                    st.info("今天的每日定时任务已经完成。若要再扫一次，请到“临时手动扫描”发起，不会受此限制。")
                    jid=None
                else:
                    jid=create_screener_job(
                        daily_universe,daily_exclude_st,daily_batch,
                        trade_date=today,job_type="scheduled"
                    )
                if jid:
                    start_screener_job_background(jid)
                    st.success("每日任务已启动/续跑。")
                    st.rerun()

        scheduled_job=latest_screener_job("scheduled")
        _render_screener_panel(scheduled_job,"scheduled","每日定时任务")

    st.caption(
        "任务隔离规则：每日任务和临时任务分别建档、分别保存结果。临时任务优先，最多只会暂挂每日任务，不会覆盖或复用它。"
        "完成的任务永远不会阻止下一次临时扫描。"
    )

with tab3:
    st.subheader("持仓管理")
    st.caption("最简流程：选股页一键加入，或直接上传券商持仓截图。识别后可批量校对；日常只需要修改、删除和更新技术分。")

    st.markdown("**管理分区**：≥78 强势持有｜65–77 持有｜55–64 谨慎持有｜45–54 减仓候选｜<45 退出候选。技术分从峰值快速回落、周线转弱或大盘逆风会进一步降档。")

    with st.expander("📸 上传持仓截图",expanded=True):
        st.caption("支持一张或多张持仓列表截图。系统只读取股票名称/代码、持仓成本、持股数量；看不清的字段不会猜。识别后先在表格里校对，再保存。")
        hold_imgs = st.file_uploader(
            "上传持仓截图",
            type=["png","jpg","jpeg","webp"],
            accept_multiple_files=True,
            key="holding_screenshots"
        )
        if hold_imgs and st.button("🔍 识别持仓截图",type="primary",use_container_width=True):
            with st.spinner("正在识别持仓列表..."):
                try:
                    parsed = extract_holdings_from_images(hold_imgs)
                    if parsed.empty:
                        st.warning("没有识别到有效A股/港股持仓。")
                    else:
                        st.session_state["holding_import_preview"] = parsed
                except Exception as e:
                    st.error(f"截图识别失败：{e}")

        preview = st.session_state.get("holding_import_preview")
        if isinstance(preview,pd.DataFrame) and not preview.empty:
            st.markdown("**识别结果 — 请先校对**")
            preview_edit = st.data_editor(
                preview,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "删除":st.column_config.CheckboxColumn("删除"),
                    "买入均价":st.column_config.NumberColumn("买入均价",format="%.3f"),
                    "持股数量":st.column_config.NumberColumn("持股数量",format="%.0f"),
                    "技术失效价":st.column_config.NumberColumn("技术失效价",format="%.3f")
                },
                key="holding_import_editor"
            )
            if st.button("💾 保存识别后的持仓",type="primary",use_container_width=True):
                work = preview_edit[preview_edit["删除"]!=True].copy()
                if work.empty:
                    st.warning("没有可保存的持仓。")
                else:
                    try:
                        bs_login()
                        # 转成统一导入字段
                        imp = work.rename(columns={"代码或名称":"股票"})
                        ok,errs = import_positions_dataframe(imp)
                        if ok:
                            st.success(f"成功保存 {ok} 只持仓。")
                            st.session_state.pop("holding_import_preview",None)
                            st.session_state.pop("holding_view",None)
                        if errs:
                            st.warning("部分未保存："+"；".join(errs[:8]))
                    except Exception as e:
                        st.error(f"保存失败：{e}")
                    finally:
                        try: bs_logout_safe()
                        except Exception: pass

    st.divider()
    h1,h2 = st.columns(2)
    refresh_holdings = h1.button("🔄 更新全部技术分",type="primary",use_container_width=True)
    h2.caption("持仓表可直接修改成本、数量、日期、失效价和备注；勾选“删除”后保存即可移除。")

    if refresh_holdings:
        with st.spinner("正在更新全部持仓的最新技术分和管理状态..."):
            try:
                bs_login()
                holding_view = refresh_positions()
                st.session_state["holding_view"] = holding_view
            except Exception as e:
                st.error(f"持仓更新失败：{e}")
            finally:
                try: bs_logout_safe()
                except Exception: pass

    edit_df = editable_positions_frame()
    if not edit_df.empty:
        st.markdown("### 当前持仓")
        position_editor = st.data_editor(
            edit_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "删除":st.column_config.CheckboxColumn("删除"),
                "买入均价":st.column_config.NumberColumn("买入均价",format="%.3f"),
                "持股数量":st.column_config.NumberColumn("持股数量",format="%.0f"),
                "技术失效价":st.column_config.NumberColumn("技术失效价",format="%.3f"),
                "技术分/100":st.column_config.NumberColumn("技术分/100",format="%.1f"),
                "峰值技术分":st.column_config.NumberColumn("峰值技术分",format="%.1f"),
                "现价":st.column_config.NumberColumn("现价",format="%.3f")
            },
            disabled=["市场","代码","名称","技术分/100","峰值技术分","现价","管理状态"],
            key="positions_editor"
        )
        if st.button("💾 保存修改 / 删除勾选",type="primary",use_container_width=True):
            try:
                bs_login()
                saved,deleted,errs = save_edited_positions(position_editor)
                msg = []
                if saved: msg.append(f"修改/保存 {saved} 只")
                if deleted: msg.append(f"删除 {deleted} 只")
                if msg: st.success("；".join(msg))
                if errs: st.warning("部分处理失败："+"；".join(errs[:8]))
                st.session_state.pop("holding_view",None)
                st.rerun()
            except Exception as e:
                st.error(f"保存持仓修改失败：{e}")
            finally:
                try: bs_logout_safe()
                except Exception: pass

        active_now = load_positions(True)

        if not active_now.empty:
            pv=active_now.copy()
            pv["shares_n"]=pd.to_numeric(pv["shares"],errors="coerce").fillna(0)
            pv["last_price_n"]=pd.to_numeric(pv["last_price"],errors="coerce")
            pv["market_value"]=pv["shares_n"]*pv["last_price_n"]
            total_mv=float(pv["market_value"].fillna(0).sum())
            top_weight=(float(pv["market_value"].max())/total_mv) if total_mv>0 else np.nan
            a_mv=float(pv.loc[~pv["code"].astype(str).str.startswith("hk."),"market_value"].fillna(0).sum())
            hk_mv=float(pv.loc[pv["code"].astype(str).str.startswith("hk."),"market_value"].fillna(0).sum())

            stop_n=pd.to_numeric(pv["initial_stop"],errors="coerce")
            known=(stop_n.notna() & pv["last_price_n"].notna() & (pv["last_price_n"]>stop_n) & (pv["shares_n"]>0))
            risk_cash=((pv.loc[known,"last_price_n"]-stop_n[known])*pv.loc[known,"shares_n"]).sum()
            unknown_stop=int((~stop_n.notna() & (pv["shares_n"]>0)).sum())
            defense=int(pv["last_action"].isin(["退出候选","减仓候选"]).sum())

            st.markdown("### 组合风险概览")
            p1,p2,p3,p4=st.columns(4)
            p1.metric("持仓市值",f"{total_mv:,.0f}" if total_mv>0 else "—")
            p2.metric("最大单票占比",f"{top_weight:.0%}" if pd.notna(top_weight) else "—")
            p3.metric("已知技术风险",f"{float(risk_cash):,.0f}" if risk_cash>0 else "—")
            p4.metric("减仓/退出候选",str(defense))
            if total_mv>0:
                st.caption(
                    f"A股市值占比 {a_mv/total_mv:.0%} · 港股市值占比 {hk_mv/total_mv:.0%} · "
                    f"{unknown_stop} 只持仓尚未设置技术失效价。"
                )
            st.caption("“已知技术风险”=现价到技术失效价的距离×持股数量，仅用于组合风险预算，不代表最大实际亏损；跳空可能扩大损失。")

        codes_available = [
            (r["code"],f"{display_code(r['code'])} · {r['name']}")
            for _,r in active_now.iterrows()
        ]
        if codes_available:
            label_to_code = {label:code for code,label in codes_available}
            selected_hist = st.selectbox("查看持仓技术分历史",[x[1] for x in codes_available],key="pos_hist")
            ph = position_history(label_to_code[selected_hist])
            if not ph.empty:
                chart = ph.sort_values("snapshot_date").set_index("snapshot_date")
                cols = [x for x in ["technical_score","weekly_score","market_score"] if x in chart.columns]
                st.line_chart(chart[cols],height=250)
                st.dataframe(ph.head(30),use_container_width=True,hide_index=True)
            else:
                st.caption("点击“更新全部技术分”后开始累计每日持仓快照。")
    else:
        st.info("暂无持仓。可以从选股页一键加入，或者直接上传券商持仓截图。")

with tab4:
    st.subheader("自动策略回测")
    st.caption("固定规则回测 + 真实交易R倍数 + 时间外(OOS)验证。用户不能为了回测结果手调阈值；重点看净EV、保守EV、2倍成本EV和OOS稳定性。")
    bt_code = st.text_input("股票代码或名称",placeholder="例如 600519 / 贵州茅台 / 00700 / 腾讯控股",key="bt_code")

    st.info("固定口径：5年历史；A股单边成本按万分之8，港股按万分之15保守估算；入场门槛根据当时市场环境自动变化，退出使用同一持仓管理规则。")

    if st.button("🧪 一键自动回测",type="primary",use_container_width=True):
        if not bt_code.strip():
            st.error("请输入股票代码或名称。")
        else:
            with st.spinner("正在执行自动策略回测..."):
                try:
                    bs_login()
                    code,name = resolve_symbol_input(bt_code)
                    df_bt = fetch_stock_daily(code,years=5)
                    benchmark_bt = fetch_benchmark_for_code(code,years=5)
                    fee_bps = 15 if market_of_code(code)=="港股" else 8
                    curve,m = run_backtest(df_bt,benchmark_bt,code=code,fee_bps=fee_bps)
                    st.session_state["bt_curve"] = curve
                    st.session_state["bt_metrics"] = m
                    st.session_state["bt_symbol"] = f"{name} / {display_code(code)}"
                except Exception as e:
                    st.error(f"回测失败：{e}")
                finally:
                    try: bs_logout_safe()
                    except Exception: pass

    m = st.session_state.get("bt_metrics")
    curve = st.session_state.get("bt_curve")
    if isinstance(m,dict) and m:
        st.markdown(f"### {st.session_state.get('bt_symbol','回测结果')}")
        a,b,c1,c2 = st.columns(4)
        a.metric("累计收益",f"{m['累计收益']:.1%}")
        b.metric("年化收益",f"{m['年化收益']:.1%}")
        c1.metric("最大回撤",f"{m['最大回撤']:.1%}")
        c2.metric("交易次数",str(m["交易次数"]))

        d1,d2,d3,d4 = st.columns(4)
        d1.metric("交易胜率",f"{m['交易胜率']:.1%}" if pd.notna(m["交易胜率"]) else "—")
        d2.metric("单笔均收益",f"{m['单笔均收益']:.1%}" if pd.notna(m["单笔均收益"]) else "—")
        pf = m["盈亏因子"]
        d3.metric("盈亏因子",f"{pf:.2f}" if pd.notna(pf) and np.isfinite(pf) else ("∞" if pf==np.inf else "—"))
        d4.metric("持仓暴露",f"{m['持仓暴露']:.1%}")

        st.caption(
            f"同期买入持有：{m['买入持有']:.1%}"
            +(f" · 平均持有 {m['平均持有天数']:.0f} 天" if pd.notna(m["平均持有天数"]) else "")
        )
        e1,e2,e3,e4 = st.columns(4)
        e1.metric("净EV",f"{m['EV_R']:+.2f}R" if pd.notna(m.get("EV_R")) else "—")
        e2.metric("保守EV",f"{m['保守EV_R']:+.2f}R" if pd.notna(m.get("保守EV_R")) else "—")
        e3.metric("2倍成本EV",f"{m['压力EV_R']:+.2f}R" if pd.notna(m.get("压力EV_R")) else "—")
        e4.metric("OOS EV",f"{m['OOS_EV_R']:+.2f}R" if pd.notna(m.get("OOS_EV_R")) else "—")
        st.caption(
            f"EV可信度：{m.get('EV可信度','不足')} · OOS稳定性：{m.get('OOS稳定性','样本不足')} · "
            f"OOS正EV折数 {m.get('OOS正EV折数',0)}/{m.get('OOS折数',0)}"
        )
        if isinstance(curve,pd.DataFrame) and not curve.empty:
            st.line_chart(curve.set_index("trade_date")[["净值","买入持有"]],height=280)
            with st.expander("查看最近自动信号"):
                cols = [x for x in [
                    "trade_date","close","score","weekly_score","buy_score","rr",
                    "market_score","rs_score","tech_req","buy_req","week_req","rr_req","action","position"
                ] if x in curve.columns]
                st.dataframe(curve[cols].tail(100),use_container_width=True,hide_index=True)
        st.warning("回测用于检验历史期望，不保证未来收益；5年单股样本仍可能有限，重点看盈亏因子、回撤、交易次数和稳定性，而不是只看累计收益。")

    st.divider()
    st.subheader("Forward Test · 实盘前向验证")
    st.caption("选股模块出现“优先机会/候选观察”时会自动记录当时信号。这里按之后真实行情和同一退出规则更新结果，避免只看回测。")
    ft1,ft2=st.columns(2)
    refresh_ft=ft1.button("🔄 更新前向验证",use_container_width=True)
    ft2.caption("每次最多更新25条跟踪中信号，避免一次请求过多行情。")
    if refresh_ft:
        with st.spinner("正在用后续真实行情更新Forward Test..."):
            try:
                bs_login()
                ucnt,ccnt,ferrs=refresh_forward_tests(25)
                st.success(f"已更新 {ucnt} 条，其中完成交易 {ccnt} 条。")
                if ferrs:
                    st.warning("部分更新失败："+"；".join(ferrs[:5]))
            except Exception as e:
                st.error(f"Forward Test更新失败：{e}")
            finally:
                try: bs_logout_safe()
                except Exception: pass

    fsum,fdf=forward_test_summary()
    q1,q2,q3,q4=st.columns(4)
    q1.metric("累计信号",str(fsum["总信号"]))
    q2.metric("已完成",str(fsum["已完成"]))
    q3.metric("实盘样本EV",f"{fsum['EV_R']:+.2f}R" if pd.notna(fsum["EV_R"]) else "—")
    q4.metric("实盘样本胜率",f"{fsum['胜率']:.0%}" if pd.notna(fsum["胜率"]) else "—")
    if isinstance(fdf,pd.DataFrame) and not fdf.empty:
        fs=fdf.head(80).copy()
        cols=[x for x in [
            "signal_date","market","code","name","tier","ev_r","ev_lcb_r",
            "stress_ev_r","ev_samples","status","realized_r","exit_date"
        ] if x in fs.columns]
        st.dataframe(fs[cols],use_container_width=True,hide_index=True)

with tab8:
    st.subheader("组合级量化研究")
    st.caption("EV1.0研究层：历史股票池、Purged OOS、Bootstrap EV、EV校准、日级组合净值和风险预算仓位。任务分批运行并可断点继续。")

    r1,r2,r3=st.columns(3)
    with r1:
        research_universe=st.selectbox(
            "研究股票池",
            ["沪深300","中证500","全A股（沪深）","港股主板"],
            index=0,key="research_universe"
        )
    with r2:
        research_years=st.selectbox("历史长度",[3,5,10],index=1,key="research_years")
    with r3:
        research_batch=st.selectbox("每批计算",[10,20,30],index=1,key="research_batch")

    st.info(
        "A股研究任务会按月调用BaoStock历史成分/历史在市股票，历史信号只有在当时属于股票池时才保留。"
        "港股免费数据源暂没有同等级历史主板成分，因此港股仍使用当前股票池回溯并单独标注偏差。"
    )

    runs=load_research_runs(30)
    rb1,rb2=st.columns([1.25,1])
    create_research=rb1.button("🧬 新建研究任务",type="primary",use_container_width=True)
    rb2.caption("建议：先跑沪深300 5年，再跑中证500 5年；规则不因结果好坏临时修改。")

    if create_research:
        with st.spinner("正在构建历史股票池并创建研究任务..."):
            try:
                bs_login()
                rid,total_count=create_research_run(research_universe,research_years)
                st.session_state["research_run_id"]=rid
                st.success(f"研究任务已创建：历史并集 {total_count} 只股票。")
                st.rerun()
            except Exception as e:
                st.error(f"创建研究任务失败：{e}")
            finally:
                try: bs_logout_safe()
                except Exception: pass

    runs=load_research_runs(30)
    if runs.empty:
        st.info("暂无研究任务。建议先创建“沪深300 · 5年”。")
    else:
        options=[]; labels={}
        for _,rr in runs.iterrows():
            rid=str(rr["run_id"])
            label=(
                f"{rr['universe']} · {int(rr['years'])}年 · "
                f"{int(rr['cursor'])}/{int(rr['total'])} · {rr['status']} · {rid}"
            )
            options.append(rid); labels[rid]=label

        preferred=st.session_state.get("research_run_id")
        default_index=options.index(preferred) if preferred in options else 0
        selected_run=st.selectbox(
            "研究任务",options,index=default_index,
            format_func=lambda x:labels.get(x,x),key="research_run_select"
        )
        st.session_state["research_run_id"]=selected_run
        if shared_db_enabled():
            _rkey=f"_shared_research_pull::{selected_run}"
            if not st.session_state.get(_rkey):
                _rsync=sync_shared_research_safe(selected_run,mode="pull")
                if not _rsync.get("errors"):
                    st.session_state[_rkey]=True
        run=get_research_run(selected_run)

        if run.get("note"):
            if str(run.get("universe"))=="港股主板":
                st.warning(str(run["note"]))
            else:
                st.success(str(run["note"]))

        done=int(run.get("cursor",0) or 0)
        total=int(run.get("total",0) or 0)
        pct=done/total if total else 0
        st.progress(min(pct,1.0),text=f"研究进度 {done:,}/{total:,}（{pct:.1%}）")

        rc1,rc2=st.columns([1.25,1])
        run_batch_btn=rc1.button(
            "▶️ 继续计算下一批",
            type="primary",use_container_width=True,
            disabled=(run.get("status")=="completed")
        )
        rc2.caption(f"每次处理 {research_batch} 只；每只股票会按历史成员区间过滤交易。")

        if run_batch_btn:
            prog=st.progress(0.0,text="准备研究批次...")
            status_box=st.empty()
            with st.spinner("正在执行多股票历史交易回放..."):
                try:
                    bs_login()
                    def _research_progress(local_done,local_total,overall_done,overall_total,code,name,stage):
                        p=local_done/local_total if local_total else 0
                        prog.progress(
                            min(p,1.0),
                            text=f"本批 {local_done}/{local_total} · 总进度 {overall_done}/{overall_total}"
                        )
                        status_box.caption(f"当前：{display_code(code)} {name} · {stage}")

                    batch_out=run_research_batch(
                        selected_run,batch_size=int(research_batch),
                        progress_callback=_research_progress
                    )
                    if batch_out.get("errors"):
                        st.warning(
                            f"本批完成，但有 {len(batch_out['errors'])} 只数据不足/异常。"
                            +"；".join(batch_out["errors"][:4])
                        )
                    else:
                        st.success(f"本批完成 {batch_out.get('processed',0)} 只。")
                    st.session_state.pop(f"research_summary_bundle::{selected_run}",None)
                    st.rerun()
                except Exception as e:
                    st.error(f"研究批次失败：{e}")
                finally:
                    try: bs_logout_safe()
                    except Exception: pass

        summary_key=f"research_summary_bundle::{selected_run}"
        sr1,sr2=st.columns([1.2,1])
        refresh_summary=sr1.button("📊 刷新研究汇总",use_container_width=True)
        sr2.caption("组合日级净值、Bootstrap和EV校准计算量较大，只在你点击时刷新，避免拖慢整个App。")
        if refresh_summary:
            with st.spinner("正在计算系统级EV、Bootstrap、Purged OOS与日级组合净值..."):
                try:
                    st.session_state[summary_key]=research_summary(selected_run)
                except Exception as e:
                    st.error(f"研究汇总计算失败：{e}")

        bundle=st.session_state.get(summary_key)
        if bundle is None:
            st.info("研究批次结果已保存。点击“刷新研究汇总”计算当前系统级结果。")
            summary=stock_results=research_trades=portfolio_curve=calibration=None
        else:
            summary,stock_results,research_trades,portfolio_curve,calibration=bundle

        if summary is not None:
            st.markdown("### ① 系统级Edge")
            s1,s2,s3,s4=st.columns(4)
            s1.metric("已完成股票",str(summary.get("股票数",0)))
            s2.metric("历史交易数",str(summary.get("交易数",0)))
            s3.metric("系统净EV",f"{summary['EV_R']:+.2f}R" if pd.notna(summary.get("EV_R")) else "—")
            s4.metric("保守EV",f"{summary['保守EV_R']:+.2f}R" if pd.notna(summary.get("保守EV_R")) else "—")

            s5,s6,s7,s8=st.columns(4)
            s5.metric("交易胜率",f"{summary['胜率']:.1%}" if pd.notna(summary.get("胜率")) else "—")
            s6.metric("真实盈亏比",f"{summary['真实盈亏比']:.2f}" if pd.notna(summary.get("真实盈亏比")) else "—")
            pf=summary.get("盈亏因子")
            s7.metric("Profit Factor",f"{pf:.2f}" if pd.notna(pf) and np.isfinite(pf) else ("∞" if pf==np.inf else "—"))
            s8.metric("Purged OOS EV",f"{summary['OOS_EV_R']:+.2f}R" if pd.notna(summary.get("OOS_EV_R")) else "—")
            st.caption(
                f"Purged Walk-Forward：正EV折数 {summary.get('Purged正EV折数',0)}/{summary.get('Purged折数',0)} · "
                f"稳定性 {summary.get('OOS稳定性','样本不足')} · 训练/测试之间设置30日净化+10日禁入间隔。"
            )

            st.markdown("### ② Bootstrap EV可信区间")
            b1,b2,b3,b4=st.columns(4)
            b1.metric("P(EV>0)",f"{summary['Bootstrap_P正EV']:.1%}" if pd.notna(summary.get("Bootstrap_P正EV")) else "—")
            b2.metric("EV 5%分位",f"{summary['Bootstrap_P05']:+.2f}R" if pd.notna(summary.get("Bootstrap_P05")) else "—")
            b3.metric("EV中位数",f"{summary['Bootstrap_P50']:+.2f}R" if pd.notna(summary.get("Bootstrap_P50")) else "—")
            b4.metric("EV 95%分位",f"{summary['Bootstrap_P95']:+.2f}R" if pd.notna(summary.get("Bootstrap_P95")) else "—")
            st.caption("采用月度块Bootstrap，尽量保留同一月份股票之间的相关性；比逐笔独立重采样更保守。")

            if isinstance(calibration,pd.DataFrame) and not calibration.empty:
                st.markdown("### ③ EV校准")
                cal=calibration.copy()
                st.dataframe(cal,use_container_width=True,hide_index=True)
                chart_df=cal[["平均预测EV(R)","实际EV(R)"]].copy()
                chart_df.index=[f"组{i+1}" for i in range(len(chart_df))]
                st.line_chart(chart_df,height=230)
                st.caption("预测EV只使用当时已经结束的历史交易，并向大样本均值收缩。理想状态是预测EV越高，实际EV也随之上升。")
            else:
                st.caption("EV校准：至少需要约15笔具有历史预测EV的交易后才显示。")

            st.markdown("### ④ 日级组合回测 · 风险预算仓位")
            p1,p2,p3,p4=st.columns(4)
            p1.metric("累计收益",f"{summary['组合累计收益']:.1%}" if pd.notna(summary.get("组合累计收益")) else "—")
            p2.metric("年化收益",f"{summary['组合年化收益']:.1%}" if pd.notna(summary.get("组合年化收益")) else "—")
            p3.metric("最大回撤",f"{summary['组合最大回撤']:.1%}" if pd.notna(summary.get("组合最大回撤")) else "—")
            p4.metric("采用交易",str(summary.get("组合交易数",0)))

            q1,q2,q3,q4=st.columns(4)
            q1.metric("Sharpe",f"{summary['组合Sharpe']:.2f}" if pd.notna(summary.get("组合Sharpe")) else "—")
            q2.metric("Sortino",f"{summary['组合Sortino']:.2f}" if pd.notna(summary.get("组合Sortino")) else "—")
            q3.metric("Calmar",f"{summary['组合Calmar']:.2f}" if pd.notna(summary.get("组合Calmar")) else "—")
            q4.metric("平均资金利用",f"{summary['组合平均仓位']:.1%}" if pd.notna(summary.get("组合平均仓位")) else "—")
            st.caption(
                "组合按日盯市；最多10仓。每笔默认风险预算=组合NAV的0.5%，"
                "仓位由“风险预算 ÷ 入场到技术失效价的风险距离”决定，单票市值上限10%。"
                "同日候选优先按仅使用过去已完成交易估计的预测EV排序。"
            )
            if pd.notna(summary.get("组合换手率")):
                st.caption(
                    f"累计换手约 {summary['组合换手率']:.1f}× · "
                    f"候选采用率 {summary.get('组合采用率',np.nan):.1%}"
                    if pd.notna(summary.get("组合采用率"))
                    else f"累计换手约 {summary['组合换手率']:.1f}×"
                )
            if isinstance(portfolio_curve,pd.DataFrame) and not portfolio_curve.empty:
                st.line_chart(
                    portfolio_curve.set_index("date")[[x for x in ["equity","exposure"] if x in portfolio_curve.columns]],
                    height=260
                )

            if summary.get("交易数",0)>=30:
                strong=(
                    pd.notna(summary.get("EV_R")) and summary["EV_R"]>0 and
                    pd.notna(summary.get("保守EV_R")) and summary["保守EV_R"]>0 and
                    pd.notna(summary.get("OOS_EV_R")) and summary["OOS_EV_R"]>0 and
                    pd.notna(summary.get("Bootstrap_P正EV")) and summary["Bootstrap_P正EV"]>=0.90
                )
                if strong:
                    st.success("当前样本同时通过：净EV>0、保守EV>0、Purged OOS EV>0、Bootstrap正EV概率≥90%。继续扩大年份和股票池验证。")
                else:
                    st.warning("当前样本尚未同时通过全部稳健性条件。不要根据局部结果重新调参。")

            if isinstance(stock_results,pd.DataFrame) and not stock_results.empty:
                with st.expander("查看单股研究结果"):
                    view=stock_results.copy().rename(columns={
                        "code":"代码","name":"名称","trade_count":"交易数",
                        "ev_r":"EV(R)","conservative_ev_r":"保守EV(R)",
                        "win_rate":"胜率","avg_win_r":"平均盈利R","avg_loss_r":"平均亏损R",
                        "profit_factor":"PF","oos_ev_r":"OOS EV(R)","oos_stability":"OOS稳定性"
                    })
                    cols=[x for x in [
                        "代码","名称","交易数","EV(R)","保守EV(R)","胜率",
                        "平均盈利R","平均亏损R","PF","OOS EV(R)","OOS稳定性"
                    ] if x in view.columns]
                    st.dataframe(view[cols].head(300),use_container_width=True,hide_index=True)

            if isinstance(research_trades,pd.DataFrame) and not research_trades.empty:
                dl1,dl2=st.columns(2)
                dl1.download_button(
                    "⬇️ 导出全部研究交易",
                    research_trades.to_csv(index=False).encode("utf-8-sig"),
                    f"research_trades_{selected_run}.csv","text/csv",use_container_width=True
                )
                dl2.download_button(
                    "⬇️ 导出单股汇总",
                    stock_results.to_csv(index=False).encode("utf-8-sig"),
                    f"research_stocks_{selected_run}.csv","text/csv",use_container_width=True
                )

        st.divider()
        st.subheader("🧪 策略优化实验室")
        st.caption(
            "回测不只看收益，而是用于优化“选股 → 买入 → 持仓/退出”。"
            "每次只改一个模块，固定60%训练、20%验证、20%最终测试；最终测试默认锁定。"
        )

        lab1,lab2=st.columns(2)
        with lab1:
            experiment_module=st.selectbox(
                "本次只研究一个模块",
                ["选股门槛","买入质量","持仓退出","因子消融"],
                key="strategy_experiment_module"
            )
        with lab2:
            experiment_batch=st.selectbox(
                "实验每批股票数",[3,5,10],index=1,
                key="strategy_experiment_batch"
            )

        st.info(
            "程序会自动跑有限、可解释的参数变体，但不会把“历史最优参数”直接改成实盘规则。"
            "候选方案只按训练+验证数据产生；最终20%测试集在实验完成前保持锁定。"
        )

        eb1,eb2=st.columns([1.2,1])
        create_exp=eb1.button(
            "➕ 新建单模块实验",
            use_container_width=True,key="create_strategy_experiment"
        )
        eb2.caption("优先找参数稳定平台，而不是找某个历史最高点。")

        if create_exp:
            try:
                exp_id=create_strategy_experiment(selected_run,experiment_module)
                st.session_state["strategy_experiment_id"]=exp_id
                st.success(f"已创建：{experiment_module}实验。")
                st.rerun()
            except Exception as e:
                st.error(f"创建策略实验失败：{e}")

        experiments=load_strategy_experiments(selected_run,30)
        if experiments.empty:
            st.caption("这个研究任务还没有策略优化实验。")
        else:
            exp_options=[]; exp_labels={}
            for _,er in experiments.iterrows():
                eid=str(er["experiment_id"])
                exp_options.append(eid)
                exp_labels[eid]=(
                    f"{er['module']} · {int(er['cursor'])}/{int(er['total'])} · "
                    f"{er['status']} · {eid}"
                )

            pref_exp=st.session_state.get("strategy_experiment_id")
            exp_index=exp_options.index(pref_exp) if pref_exp in exp_options else 0
            selected_exp=st.selectbox(
                "选择实验",exp_options,index=exp_index,
                format_func=lambda x:exp_labels.get(x,x),
                key="strategy_experiment_select"
            )
            st.session_state["strategy_experiment_id"]=selected_exp
            exp=get_strategy_experiment(selected_exp)
            if shared_db_enabled() and exp:
                _ekey=f"_shared_experiment_pull::{selected_exp}"
                if not st.session_state.get(_ekey):
                    _esync=sync_shared_experiment_safe(
                        selected_exp,
                        research_run_id=exp.get("research_run_id"),
                        mode="pull"
                    )
                    if not _esync.get("errors"):
                        st.session_state[_ekey]=True
                    exp=get_strategy_experiment(selected_exp)

            edone=int(exp.get("cursor",0) or 0)
            etotal=int(exp.get("total",0) or 0)
            epct=edone/etotal if etotal else 0
            st.progress(
                min(epct,1.0),
                text=f"实验进度 {edone:,}/{etotal:,}（{epct:.1%}）"
            )
            st.caption(
                f"训练截止 {exp['train_end']} · 验证截止 {exp['validation_end']} · "
                f"最终测试：{'已解锁' if int(exp.get('test_revealed',0) or 0) else '🔒 锁定'}"
            )

            ex1,ex2=st.columns([1.25,1])
            run_exp=ex1.button(
                "▶️ 继续实验下一批",
                type="primary",use_container_width=True,
                disabled=(exp.get("status")=="completed"),
                key="run_strategy_experiment_batch"
            )
            ex2.caption(
                f"每只股票共享一次指标计算，再运行多个参数方案；本批 {experiment_batch} 只。"
            )

            if run_exp:
                eprog=st.progress(0.0,text="准备策略实验...")
                estat=st.empty()
                with st.spinner("正在执行参数敏感性/消融回放..."):
                    try:
                        bs_login()
                        def _exp_progress(local_done,local_total,overall_done,overall_total,code,name,stage):
                            pp=local_done/local_total if local_total else 0
                            eprog.progress(
                                min(pp,1.0),
                                text=(
                                    f"本批 {local_done}/{local_total} · "
                                    f"总进度 {overall_done}/{overall_total}"
                                )
                            )
                            estat.caption(
                                f"当前：{display_code(code)} {name} · {stage}"
                            )

                        exp_out=run_strategy_experiment_batch(
                            selected_exp,batch_size=int(experiment_batch),
                            progress_callback=_exp_progress
                        )
                        if exp_out.get("errors"):
                            st.warning(
                                f"本批完成，有 {len(exp_out['errors'])} 只异常："
                                +"；".join(exp_out["errors"][:4])
                            )
                        else:
                            st.success(
                                f"本批实验完成 {exp_out.get('processed',0)} 只。"
                            )
                        st.rerun()
                    except Exception as e:
                        st.error(f"策略实验运行失败：{e}")
                    finally:
                        try: bs_logout_safe()
                        except Exception: pass

            exp_table,candidate=strategy_experiment_summary(selected_exp)
            if not exp_table.empty:
                st.markdown("#### 训练 + 验证结果")
                show=exp_table.copy()
                for col in [
                    "训练EV(R)","验证EV(R)","验证保守EV(R)",
                    "验证胜率","验证PF","稳健分","邻域验证EV","相对基准EV"
                ]:
                    if col in show.columns:
                        show[col]=pd.to_numeric(show[col],errors="coerce")
                cols=[
                    "方案","训练样本","训练EV(R)","验证样本","验证EV(R)",
                    "验证保守EV(R)","验证胜率","验证PF",
                    "邻域验证EV","稳定区域","相对基准EV","稳健分"
                ]
                if int(exp.get("test_revealed",0) or 0):
                    cols += [
                        "最终测试样本","最终测试EV(R)",
                        "最终测试保守EV(R)","最终测试胜率","最终测试PF"
                    ]
                st.dataframe(
                    show[[x for x in cols if x in show.columns]],
                    use_container_width=True,hide_index=True
                )

                if exp["module"]!="因子消融":
                    stable_rows=show[show["稳定区域"]==True] if "稳定区域" in show.columns else pd.DataFrame()
                    if not stable_rows.empty:
                        st.success(
                            "发现参数稳定区域："
                            +" / ".join(stable_rows["方案"].astype(str).tolist())
                            +"。优先关注整个区域，而不是单一最高值。"
                        )
                    else:
                        st.warning(
                            "目前没有形成连续正EV的参数平台。即使某个参数单点很好，也不应据此升级实盘规则。"
                        )
                else:
                    st.caption(
                        "消融实验看“去掉某因子后验证EV如何变化”。相对基准EV明显为负，说明该因子更可能贡献有效Edge；"
                        "明显为正则说明该门槛可能冗余或有害。"
                    )

                if candidate:
                    st.markdown("#### 研究候选")
                    st.info(
                        f"训练+验证阶段候选：**{candidate['方案']}** · "
                        f"验证EV {candidate.get('验证EV(R)',np.nan):+.2f}R · "
                        f"验证保守EV {candidate.get('验证保守EV(R)',np.nan):+.2f}R。"
                        "这不是实盘升级结论。"
                    )
                    save_cand=st.button(
                        "💾 保存为候选版本（不应用实盘）",
                        use_container_width=True,key="save_strategy_candidate_btn"
                    )
                    if save_cand:
                        try:
                            cid=save_strategy_candidate(
                                selected_exp,candidate["config_id"]
                            )
                            st.success(f"已保存候选版本 {cid}；EV1.0实盘规则未改变。")
                        except Exception as e:
                            st.error(f"保存候选失败：{e}")
                else:
                    st.caption(
                        "当前训练/验证数据没有产生同时满足正EV和最小样本要求的候选方案。"
                    )

                if exp.get("status")=="completed" and not int(exp.get("test_revealed",0) or 0):
                    st.warning(
                        "最终20%测试集仍锁定。只有在你决定“停止调参、接受当前候选”后再解锁。"
                        "一旦看过最终测试，不应再用同一测试区间继续改参数。"
                    )
                    reveal=st.button(
                        "🔓 锁定参数后，解锁最终测试",
                        use_container_width=True,key="reveal_strategy_final_test"
                    )
                    if reveal:
                        reveal_strategy_test(selected_exp)
                        st.rerun()

                if int(exp.get("test_revealed",0) or 0):
                    st.warning(
                        "该实验最终测试已经看过。后续如果继续修改逻辑，应创建新的策略版本和新的未见测试区间，"
                        "不要反复用这20%数据挑参数。"
                    )

            candidates=load_strategy_candidates(20)
            if not candidates.empty:
                relevant=candidates[
                    candidates["experiment_id"].isin(
                        experiments["experiment_id"].astype(str).tolist()
                    )
                ].copy()
                if not relevant.empty:
                    with st.expander("候选策略版本库"):
                        cv=relevant[[
                            "created_at","module","config_id","status","note"
                        ]].rename(columns={
                            "created_at":"保存时间","module":"模块",
                            "config_id":"方案","status":"状态","note":"说明"
                        })
                        st.dataframe(cv,use_container_width=True,hide_index=True)

        st.caption(
            "优化闭环：基准EV1.0 → 单模块实验 → 训练/验证筛选 → 参数稳定区 → 锁定方案 → "
            "最终测试 → 保存候选版本 → Forward Test。程序不会自动把回测冠军替换为实盘规则。"
        )

with tab5:
    st.subheader("历史记录与信号演化")
    df = history()
    if df.empty:
        st.info("暂无历史记录。")
    else:
        symbols = [s for s in df["symbol"].dropna().astype(str).unique().tolist() if s]
        chosen = st.selectbox("筛选标的", ["全部"] + symbols)
        view = df if chosen == "全部" else df[df["symbol"] == chosen]
        cols = [c for c in [
            "created_at","symbol","rating","state","stage","score",
            "trend_score","momentum_score","weekly_score","confirm_score",
            "confidence","price","boll_mid","key_support","key_resistance"
        ] if c in view.columns]
        st.dataframe(view[cols], use_container_width=True, hide_index=True)
        if chosen != "全部" and len(view) >= 2:
            chart = view.sort_values("created_at").set_index("created_at")
            st.line_chart(chart[["score","trend_score","momentum_score"]], height=250)
            st.caption("曲线用于看技术状态是否持续升级，不代表未来收益。")
        st.download_button(
            "⬇️ 导出历史记录",
            view.to_csv(index=False).encode("utf-8-sig"),
            "mid_long_history.csv",
            "text/csv",
            use_container_width=True
        )

st.divider()
st.caption("中长线技术决策辅助工具。分析、选股、回测统一使用同一行情数据和指标公式；技术分不是未来收益保证。")
