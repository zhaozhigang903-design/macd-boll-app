import base64
import html
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import baostock as bs
import akshare as ak
from openai import OpenAI

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analysis_history.db"
RULE_VERSION = "EV1.0-2026-09-30"

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
    return "AKShare" if market_of_code(code) == "港股" else "BaoStock"

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

def bs_login():
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError("BaoStock登录失败：" + lg.error_msg)
    return lg

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
    rows = []
    try:
        rs = bs.query_stock_basic(code_name=s)
        df = _rs_to_df(rs)
        if not df.empty and "code" in df.columns:
            name_col = "code_name" if "code_name" in df.columns else ("name" if "name" in df.columns else None)
            for _,row in df.iterrows():
                name = str(row[name_col]).strip() if name_col else ""
                if name:
                    rows.append((str(row["code"]),name))
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
    code = normalize_code(code)
    if code.startswith("hk."):
        try:
            hk = hk_universe_snapshot()
            hit = hk[hk["code"] == code]
            if not hit.empty:
                return str(hit.iloc[0]["code_name"]).strip()
        except Exception:
            pass
        return display_code(code)

    rs = bs.query_stock_basic(code=code)
    df = _rs_to_df(rs)
    if df.empty:
        return display_code(code)
    for col in ["code_name","name"]:
        if col in df.columns and str(df.iloc[0][col]).strip():
            return str(df.iloc[0][col]).strip()
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


def _download_a_daily(code,start,end):
    if start > end:
        return pd.DataFrame()
    fields = "date,code,open,high,low,close,volume,amount,pctChg,turn,tradestatus,isST"
    rs = bs.query_history_k_data_plus(
        code,fields,start_date=start,end_date=end,frequency="d",adjustflag="2"
    )
    df = _rs_to_df(rs)
    if df.empty:
        return df
    df = df.rename(columns={"date":"trade_date","volume":"vol"})
    for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col],errors="coerce")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    if "tradestatus" in df.columns:
        df = df[df["tradestatus"].astype(str)=="1"]
    return df.sort_values("trade_date").reset_index(drop=True)

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
    if start > end:
        return pd.DataFrame()
    symbol = display_code(code).zfill(5)
    s = start.replace("-","")
    e = end.replace("-","")
    last_error = None
    try:
        raw = ak.stock_hk_hist(
            symbol=symbol,period="daily",start_date=s,end_date=e,adjust="qfq"
        )
        df = _normalize_hk_history(raw,code)
        if not df.empty:
            return df
    except Exception as ex:
        last_error = ex
    try:
        raw = ak.stock_hk_daily(symbol=symbol,adjust="qfq")
        df = _normalize_hk_history(raw,code)
        if not df.empty:
            mask = (
                (df["trade_date"] >= pd.Timestamp(start)) &
                (df["trade_date"] <= pd.Timestamp(end))
            )
            return df.loc[mask].reset_index(drop=True)
    except Exception as ex:
        last_error = ex
    raise RuntimeError(f"港股历史行情获取失败：{last_error}")

def _download_daily(code,start,end):
    code = normalize_code(code)
    return _download_hk_daily(code,start,end) if code.startswith("hk.") else _download_a_daily(code,start,end)

def fetch_stock_daily(code,years=3):
    code = normalize_code(code)
    end = datetime.now().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today()-pd.Timedelta(days=365*years+180)).strftime("%Y-%m-%d")
    cache_flag = "hk_qfq" if code.startswith("hk.") else "2"
    cache_min,cache_max,last_checked = _cache_bounds(code,cache_flag)
    today = datetime.now().strftime("%Y-%m-%d")

    if not cache_min or not cache_max:
        fresh = _download_daily(code,start,end)
        _save_daily_cache(fresh,code,cache_flag)
        _mark_cache_checked(code)
    else:
        if start < cache_min:
            pre_end = (pd.Timestamp(cache_min)-pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            older = _download_daily(code,start,pre_end)
            _save_daily_cache(older,code,cache_flag)
        if _should_refresh_cache(last_checked,cache_max):
            next_start = (pd.Timestamp(cache_max)+pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            newer = _download_daily(code,next_start,end)
            _save_daily_cache(newer,code,cache_flag)
            _mark_cache_checked(code)

    return _read_daily_cache(code,start,end,cache_flag)

def _download_index_daily(code,start,end):
    if start > end:
        return pd.DataFrame()
    fields = "date,code,open,high,low,close,preclose,volume,amount,pctChg"
    rs = bs.query_history_k_data_plus(
        code,fields,start_date=start,end_date=end,frequency="d",adjustflag="3"
    )
    df = _rs_to_df(rs)
    if df.empty:
        return df
    df = df.rename(columns={"date":"trade_date","volume":"vol"})
    for col in ["open","high","low","close","vol","amount","pctChg"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col],errors="coerce")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df.sort_values("trade_date").reset_index(drop=True)

def fetch_benchmark_daily(years=5,code="sh.000300"):
    end = datetime.now().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today()-pd.Timedelta(days=365*years+180)).strftime("%Y-%m-%d")
    cache_min,cache_max,last_checked = _cache_bounds(code,"3")
    today = datetime.now().strftime("%Y-%m-%d")
    if not cache_min or not cache_max:
        fresh = _download_index_daily(code,start,end)
        _save_daily_cache(fresh,code,"3")
        _mark_cache_checked(code)
    else:
        if start < cache_min:
            pre_end = (pd.Timestamp(cache_min)-pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            older = _download_index_daily(code,start,pre_end)
            _save_daily_cache(older,code,"3")
        if _should_refresh_cache(last_checked,cache_max):
            next_start = (pd.Timestamp(cache_max)+pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            newer = _download_index_daily(code,next_start,end)
            _save_daily_cache(newer,code,"3")
            _mark_cache_checked(code)
    return _read_daily_cache(code,start,end,"3")

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

def weekly_from_daily(df,completed_only=True):
    if df is None or df.empty:
        return pd.DataFrame()
    src=df.copy().sort_values("trade_date")
    latest_daily=pd.Timestamp(src["trade_date"].max()).normalize()
    d=src.set_index("trade_date")
    agg={"open":"first","high":"max","low":"min","close":"last","vol":"sum"}
    if "amount" in d.columns:
        agg["amount"]="sum"
    w=d.resample("W-FRI").agg(agg).dropna(subset=["close"]).reset_index()
    if completed_only and not w.empty:
        w=w[pd.to_datetime(w["trade_date"]).dt.normalize()<=latest_daily]
    return add_indicators(w.reset_index(drop=True))

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

def deterministic_report(code,name,df,position_state,fundamentals_ok,benchmark_df=None,compute_ev=True):
    di=add_indicators(df)
    wi=weekly_from_daily(df,completed_only=True)
    if len(di)<60:
        raise RuntimeError("历史数据不足，无法计算指标")
    if len(wi)<20:
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
    if compute_ev:
        ev,_,_=realized_trade_ev(df,benchmark_df,code,use_cache=True)
        tier,ev_reason,_=ev_opportunity_decision(
            score,buy_score,weekly,rr,mkt_score,rs_score,opp,ev,liq_ok
        )

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
    ev_txt=f"{ev.get('EV_R'):+.2f}R" if pd.notna(ev.get("EV_R")) else "样本不足"
    essence=f"{tier} · 历史净EV {ev_txt} · 技术{score:.0f} · 买点{buy_score} · RR {rr_txt} · {mkt_regime}{mkt_score}/100"

    up=[]; down=[]
    if compute_ev and tier!="优先机会":
        up.append("等待保守EV与压力EV转正")
    if buy_score<65:
        up.append("买点质量继续改善")
    if pd.notna(risk_price):
        down.append(f"跌破风险位{risk_price:.2f}")
    if mkt_score<35:
        down.append("市场处于逆风区")
    if pd.notna(mid):
        down.append(f"持续运行于中轨{mid:.2f}下方")

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
        "ev":ev,"liquidity_ok":liq_ok,"amount20":amount20,
        "risk_price":risk_price,"target_price":target_price,
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
        "weekly_analysis":f"已确认周线技术分 {weekly:.0f}/100；未完成本周K不用于硬性决策。",
        "resonance":f"相对强度{rs_score}/100；{benchmark_label_for_code(code)}环境{mkt_regime}{mkt_score}/100。",
        "data_source":data_source_for_code(code),"market":market_of_code(code),
        "benchmark":benchmark_label_for_code(code),"adjustment":"前复权",
        "latest_date":di.iloc[-1]["trade_date"].strftime("%Y-%m-%d"),
        "latest_close":float(di.iloc[-1]["close"]),"_df":di
    }

def latest_trade_date():
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today()-pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    rs = bs.query_trade_dates(start_date=start,end_date=end)
    df = _rs_to_df(rs)
    if df.empty:
        return end
    if "is_trading_day" in df.columns:
        df = df[df["is_trading_day"].astype(str)=="1"]
    if df.empty:
        return end
    return str(df["calendar_date"].max())

def fetch_universe(kind):
    if kind == "港股主板":
        hk = hk_universe_snapshot()
        return hk[["code","code_name"]].drop_duplicates("code").reset_index(drop=True)

    if kind == "沪深300":
        rs = bs.query_hs300_stocks()
        df = _rs_to_df(rs)
    elif kind == "中证500":
        rs = bs.query_zz500_stocks()
        df = _rs_to_df(rs)
    elif kind == "上证50":
        rs = bs.query_sz50_stocks()
        df = _rs_to_df(rs)
    else:
        day = latest_trade_date()
        rs = bs.query_all_stock(day=day)
        df = _rs_to_df(rs)
        if not df.empty:
            code_col = "code" if "code" in df.columns else df.columns[0]
            df = df[df[code_col].astype(str).str.match(r"^(sh\.6|sz\.[03])")]
            if "tradeStatus" in df.columns:
                df = df[df["tradeStatus"].astype(str)=="1"]

    if df.empty:
        return pd.DataFrame(columns=["code","code_name"])
    code_col = "code" if "code" in df.columns else df.columns[0]
    name_col = "code_name" if "code_name" in df.columns else ("codeName" if "codeName" in df.columns else None)
    out = pd.DataFrame({"code":df[code_col].astype(str)})
    out["code_name"] = df[name_col].astype(str) if name_col else out["code"]
    return out.drop_duplicates("code").reset_index(drop=True)

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

def build_score_series(df):
    d=add_indicators(df)
    w=weekly_from_daily(df,completed_only=True)
    if d.empty or w.empty:
        return pd.DataFrame()
    w2=w[["trade_date","boll_mid","boll_slope","close","dif","dea"]].copy()
    w2.columns=["w_date","w_boll_mid","w_boll_slope","w_close","w_dif","w_dea"]
    m=pd.merge_asof(
        d.sort_values("trade_date"),w2.sort_values("w_date"),
        left_on="trade_date",right_on="w_date",direction="backward"
    )
    scores=[]; weekly_scores=[]; buy_scores=[]; rr_list=[]; stops=[]; targets=[]
    for i,row in m.iterrows():
        r=row.to_dict()
        r["macd_prev"]=m.iloc[i-1]["macd"] if i>0 else np.nan
        wr=None
        if pd.notna(row.get("w_date")):
            wr={
                "boll_slope":row.get("w_boll_slope"),"close":row.get("w_close"),
                "boll_mid":row.get("w_boll_mid"),"dif":row.get("w_dif"),"dea":row.get("w_dea")
            }
        metric=numeric_score(r,wr)
        bp,rr,stop,target=entry_quality(r)
        scores.append(metric[0]); weekly_scores.append(metric[3] if metric[3] is not None else np.nan)
        buy_scores.append(bp); rr_list.append(rr); stops.append(stop); targets.append(target)
    m["score"]=scores
    m["weekly_score"]=weekly_scores
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

def prepare_strategy_frame(df,benchmark_df):
    m=build_score_series(df)
    if m.empty:
        return m
    bm=market_score_series(benchmark_df)
    if not bm.empty:
        bm2=bm[["trade_date","ret20","ret60","market_score"]].copy()
        bm2.columns=["trade_date","bm_ret20","bm_ret60","market_score"]
        m=pd.merge_asof(
            m.sort_values("trade_date"),bm2.sort_values("trade_date"),
            on="trade_date",direction="backward"
        )
    else:
        m["market_score"]=50
        m["bm_ret20"]=np.nan
        m["bm_ret60"]=np.nan

    rs_scores=[]
    opp_scores=[]
    for _,r in m.iterrows():
        ex20=r.get("ret20")-r.get("bm_ret20") if pd.notna(r.get("ret20")) and pd.notna(r.get("bm_ret20")) else np.nan
        ex60=r.get("ret60")-r.get("bm_ret60") if pd.notna(r.get("ret60")) and pd.notna(r.get("bm_ret60")) else np.nan
        rs=50
        if pd.notna(ex20):
            rs+=120*ex20
        if pd.notna(ex60):
            rs+=60*ex60
        rs=clamp(rs)
        rs_scores.append(rs)
        opp_scores.append(opportunity_score(
            r.get("score",0),r.get("buy_score",0),r.get("rr",np.nan),
            None,float(r.get("market_score",50) or 50),rs
        ))
    m["rs_score"]=rs_scores
    m["opportunity_score"]=opp_scores
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

def simulate_structural_trades(df,benchmark_df,code,cost_mult=1.0):
    m=prepare_strategy_frame(df,benchmark_df)
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

def walk_forward_validation(trades):
    if trades is None or trades.empty or len(trades)<8:
        return {"折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,"稳定性":"样本不足"}

    t=trades.sort_values("signal_date").reset_index(drop=True)
    n=len(t)
    train_min=max(5,int(n*0.45))
    remain=n-train_min
    if remain<3:
        return {"折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,"稳定性":"样本不足"}

    folds=min(3,max(1,remain//3))
    fold_size=max(1,remain//folds)
    tests=[]
    positive=0
    used=0

    for k in range(folds):
        start=train_min+k*fold_size
        end=n if k==folds-1 else min(n,start+fold_size)
        if start>=end:
            continue
        train=t.iloc[:start]
        test=t.iloc[start:end]
        train_ev=summarize_ev(train)
        test_ev=summarize_ev(test)

        # 只在过去训练段为正EV时观察下一段；测试段不反向调参。
        if pd.notna(train_ev["EV_R"]) and train_ev["EV_R"]>0:
            tests.append(test)
            used+=1
            if pd.notna(test_ev["EV_R"]) and test_ev["EV_R"]>0:
                positive+=1

    if not tests:
        return {"折数":0,"正EV折数":0,"OOS_EV_R":np.nan,"OOS胜率":np.nan,"稳定性":"历史训练段EV非正"}

    oos=pd.concat(tests,ignore_index=True)
    oe=summarize_ev(oos)
    stability=(
        "稳定" if used>=2 and positive==used and pd.notna(oe["EV_R"]) and oe["EV_R"]>0
        else ("一般" if positive>=max(1,used//2) else "不稳定")
    )
    return {
        "折数":used,"正EV折数":positive,
        "OOS_EV_R":oe["EV_R"],"OOS胜率":oe["胜率"],"稳定性":stability
    }

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

def realized_trade_ev(df,benchmark_df,code,use_cache=True):
    if use_cache:
        cached=get_cached_ev(df,benchmark_df,code)
        if cached is not None:
            return cached,pd.DataFrame(),True

    trades,_=simulate_structural_trades(df,benchmark_df,code,cost_mult=1.0)
    stress=reprice_trades_for_cost(trades,code,cost_mult=2.0)
    base=summarize_ev(trades)
    stress_s=summarize_ev(stress)
    base["压力EV_R"]=stress_s.get("EV_R",np.nan)
    base["walk_forward"]=walk_forward_validation(trades)

    if use_cache:
        save_cached_ev(df,benchmark_df,code,base)
    return base,trades,False

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

def screen_codes(codes,name_map=None,benchmark_df=None,progress_callback=None):
    rows=[]
    name_map=name_map or {}
    benchmark_df=benchmark_df if benchmark_df is not None else pd.DataFrame()
    mkt_score,mkt_regime=market_environment(benchmark_df) if not benchmark_df.empty else (50,"未知")
    policy=automatic_entry_policy(mkt_score)
    stats={
        "扫描":0,"快速初筛通过":0,"优先机会":0,"候选观察":0,
        "EV阶段":0,"EV缓存命中":0,"流动性不足":0,"数据异常":0
    }
    total_codes=len(codes)

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

            name=name_map.get(code) or stock_basic_name(code)
            di=add_indicators(d)
            wi=weekly_from_daily(d,completed_only=True)
            if wi.empty:
                tick(i,code,name,"确认周线不足，跳过")
                continue

            lr=di.iloc[-1].to_dict()
            lr["macd_prev"]=di.iloc[-2]["macd"] if len(di)>1 else np.nan
            wr=wi.iloc[-1].to_dict()
            technical,trend,momentum,weekly,confirm=numeric_score(lr,wr)
            buy_score,rr,stop,target=entry_quality(lr)
            liq_ok,amount20,liq_threshold=liquidity_rule(code,lr)
            if not liq_ok:
                stats["流动性不足"]+=1
                tick(i,code,name,"流动性不足")
                continue

            rs_score,ex20,ex60=relative_strength(d,benchmark_df) if not benchmark_df.empty else (50,np.nan,np.nan)
            opp=opportunity_score(technical,buy_score,rr,None,mkt_score,rs_score)

            # 与最终“候选观察”的结构门槛对齐，不会漏掉最终可能入选的股票；
            # 但可避免为结构上注定无法通过的股票计算5年EV。
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
                tick(i,code,name,"快速结构初筛未通过")
                continue

            stats["快速初筛通过"]+=1
            stats["EV阶段"]+=1
            tick(i-1,code,name,"计算5年真实交易EV")

            hist_df=fetch_stock_daily(code,years=5)
            ev,trades,cache_hit=realized_trade_ev(hist_df,benchmark_df,code,use_cache=True)
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
                "交易胜率":f"{ev.get('胜率'):.0%}" if pd.notna(ev.get("胜率")) else "—",
                "平均盈利R":round(float(ev["平均盈利R"]),2) if pd.notna(ev.get("平均盈利R")) else np.nan,
                "平均亏损R":round(float(ev["平均亏损R"]),2) if pd.notna(ev.get("平均亏损R")) else np.nan,
                "盈亏因子":round(float(pf),2) if pd.notna(pf) and np.isfinite(pf) else ("∞" if pf==np.inf else np.nan),
                "OOS EV(R)":round(float(wf.get("OOS_EV_R")),2) if pd.notna(wf.get("OOS_EV_R")) else np.nan,
                "OOS稳定性":wf.get("稳定性","样本不足"),
                "机会分/100":opp,"技术分/100":technical,"买点分/100":buy_score,
                "周线/100":weekly,"盈亏比":rr,
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

def close_position(code):
    code = normalize_code(code)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE positions SET active=0,updated_at=? WHERE code=?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),code)
    )
    conn.commit()
    conn.close()

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
    m=prepare_strategy_frame(df,benchmark)
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

st.markdown("<div style='height:.15rem'></div>", unsafe_allow_html=True)
st.title("📈 日线 × 周线 中长线决策引擎")
st.caption("数据驱动版 · 机会发现 → 买点评估 → 持仓管理 → 回测验证。")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 分析", "🔎 选股", "💼 持仓", "🧪 回测", "📚 历史", "🧠 方法", "⚙️ 设置"])

with tab7:
    st.subheader("数据设置")
    st.info(f"当前策略规则版本：{RULE_VERSION}。为避免过拟合，EV核心规则进入观察期后不因短期盈亏或候选数量随意调整。")
    st.success("A股：BaoStock；港股：AKShare。两者均无需在本App配置行情Token。")
    st.info("A股与港股统一使用前复权日线，并由日线聚合周线；分析、选股、持仓和回测使用同一指标逻辑。")
    st.caption("港股市场环境以恒生指数为基准；A股以沪深300为基准。AKShare接口来自公开数据源，接口稳定性可能受上游网站变化影响。")

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
    st.warning("当前缓存位于Render本机SQLite：重新部署/重建实例时可能被清空。持仓数据后续应迁移到持久数据库。")
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
    st.markdown("iPhone：Safari打开网址 → 分享 → **添加到主屏幕**。")

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
- **周线**：硬性决策只使用已确认周线；未完成的当周K不参与选股阈值。
- **流动性**：A股默认20日中位成交额≥5000万元，港股≥2000万元。
- **回测**：收盘形成信号，下一交易日执行；止损考虑跳空，不假设一定能按风险位成交。
- **持仓管理**：买入后“买点分”的意义下降，核心转为技术分及其变化。≥78强势持有、65–77持有、55–64谨慎持有、45–54减仓候选、<45退出候选；技术分较峰值快速回落、周线转弱或大盘逆风会降档。

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
    st.caption("一次只保留一个“当前分析结果”。分析下一只股票时会自动替换上一只；历史结果集中放在页面底部。")

    a1,a2 = st.columns([1.35,1])
    with a1:
        auto_code = st.text_input(
            "股票代码或名称",
            placeholder="例如 600519 / 贵州茅台 / 0700 / 腾讯控股",
            key="auto_code"
        )
    with a2:
        auto_horizon = st.selectbox(
            "持有周期",["2–8周","2–6个月","6–18个月"],index=1,key="auto_horizon"
        )

    a3,a4 = st.columns(2)
    with a3:
        auto_position = st.selectbox(
            "当前仓位",["未持有","轻仓≤25%","中等25–50%","重仓>50%"],key="auto_position"
        )
    with a4:
        auto_fund = st.checkbox("基本面/估值已验证",value=False,key="auto_fund")

    act1,act2 = st.columns([2,1])
    run_analysis = act1.button("⚡ 生成 / 替换当前分析",type="primary",use_container_width=True)
    clear_analysis = act2.button("🧹 清空当前结果",use_container_width=True)

    if clear_analysis:
        st.session_state.pop("last_report",None)
        st.rerun()

    if run_analysis:
        if not auto_code.strip():
            st.error("请输入A股或港股代码/名称。")
        else:
            with st.spinner("正在获取行情并计算日线/周线指标..."):
                try:
                    bs_login()
                    code,name = resolve_symbol_input(auto_code)
                    df_auto = fetch_stock_daily(code,years=5)
                    benchmark_df = fetch_benchmark_for_code(code,years=5)
                    report = deterministic_report(
                        code,name,df_auto,auto_position,auto_fund,benchmark_df
                    )
                    prev = previous(report["symbol"])
                    if prev and prev.get("score") is not None:
                        try:
                            report["delta"] = report["score"]-float(prev.get("score"))
                        except Exception:
                            pass

                    st.session_state["last_report"] = report
                    xsave = {
                        "data_quality":100,
                        "daily":{
                            "price":str(report["_df"].iloc[-1]["close"]),
                            "boll_mid":str(report["_df"].iloc[-1]["boll_mid"]),
                        },
                        "key_support":report["support"],
                        "key_resistance":report["resistance"],
                    }
                    meta = {
                        "symbol":report["symbol"],"market":market_of_code(code),
                        "horizon":auto_horizon,"position_state":auto_position,
                        "rating":report["rating"],"state":report["state"],
                        "stage":report["stage"],"confidence":100,
                        "mode":f"{data_source_for_code(code)}自动数据",
                        "weekly_used":True
                    }
                    metrics = (
                        report["score"],report["trend"],report["momentum"],
                        report["weekly_score"],report["confirm"],False,False
                    )
                    save_result(
                        meta,xsave,metrics,
                        json.dumps(
                            {"source":data_source_for_code(code),"market":market_of_code(code)},
                            ensure_ascii=False
                        )
                    )
                    report.pop("_df",None)
                    st.rerun()
                except Exception as e:
                    st.error(f"自动分析失败：{e}")
                finally:
                    try:
                        bs.logout()
                    except Exception:
                        pass

    st.divider()
    st.subheader("当前分析结果")
    render_cockpit(st.session_state.get("last_report"))

    st.divider()
    st.subheader("最近分析")
    recent = recent_analyses(12)
    if recent.empty:
        st.caption("暂无历史分析。")
    else:
        recent_show = recent.rename(columns={
            "created_at":"时间","symbol":"股票","market":"市场","horizon":"周期",
            "position_state":"仓位","state":"状态","rating":"评级",
            "score":"技术分","trend_score":"趋势","momentum_score":"动能",
            "weekly_score":"周线","confirm_score":"量能"
        })
        show_cols = [
            "时间","股票","市场","状态","技术分","趋势","动能","周线","量能","周期","仓位"
        ]
        st.dataframe(
            recent_show[[x for x in show_cols if x in recent_show.columns]],
            use_container_width=True,hide_index=True
        )
        st.caption("这里只显示最近12次数据驱动分析；清空“当前结果”不会删除这些历史记录。")

with tab2:
    st.subheader("自动选股")
    st.caption("已启用两阶段快速扫描：先做1年当前结构过滤，只有最终可能进入“优先/观察”的股票才计算5年EV；同一交易日EV自动缓存。提速不放宽正期望标准。")

    sopt1,sopt2,sopt3 = st.columns(3)
    with sopt1:
        universe = st.selectbox("选股范围",["全A股（沪深）","沪深300","中证500","上证50","港股主板"],index=0)
    with sopt2:
        batch_size = st.selectbox("每批扫描",[100,200,300,500],index=2)
    with sopt3:
        exclude_st = st.checkbox("排除ST/*ST",value=True)

    scan_market = st.session_state.get("scan_market")
    if scan_market and st.session_state.get("scan_universe") == universe:
        p = automatic_entry_policy(scan_market[0])
        bench_label = scan_market[2] if len(scan_market)>2 else "沪深300"
        st.info(
            f"当前{bench_label}：{scan_market[1]} {scan_market[0]}/100。系统基础门槛自动调整为："
            f"技术≥{p['技术']}、买点≥{p['买点']}、周线≥{p['周线']}、"
            f"盈亏比≥{p['盈亏比']:.2f}、相对强度≥{p['相对强度']}、机会≥{p['机会']}。"
            "结构通过后再计算5年真实交易EV；优先机会要求EV、保守EV和2倍成本压力EV为正。"
        )

    sb1,sb2 = st.columns(2)
    start_scan = sb1.button("🔎 开始/重新扫描",type="primary",use_container_width=True)
    continue_scan = sb2.button("➡️ 扫描下一批",use_container_width=True)

    if start_scan:
        st.session_state["scan_cursor"] = 0
        st.session_state["scan_results"] = pd.DataFrame()
        st.session_state["scan_universe"] = universe
        st.session_state["scan_done"] = False

    if start_scan or continue_scan:
        with st.spinner("正在按系统自动门槛扫描交易机会..."):
            try:
                bs_login()
                if universe == "港股主板":
                    benchmark_df = fetch_hk_benchmark_daily(years=5)
                    benchmark_name = "恒生指数"
                else:
                    benchmark_df = fetch_benchmark_daily(years=5)
                    benchmark_name = "沪深300"
                current_market_score,current_market_regime = market_environment(benchmark_df)
                st.session_state["scan_market"] = (current_market_score,current_market_regime,benchmark_name)

                pool = fetch_universe(universe)
                if exclude_st and universe != "港股主板" and not pool.empty:
                    pool = pool[~pool["code_name"].str.upper().str.contains(r"(^ST|\*ST)",regex=True,na=False)]
                pool = pool.reset_index(drop=True)

                total = len(pool)
                cursor = int(st.session_state.get("scan_cursor",0))
                if st.session_state.get("scan_universe") != universe:
                    cursor = 0
                    st.session_state["scan_results"] = pd.DataFrame()
                    st.session_state["scan_universe"] = universe

                end_i = min(cursor+int(batch_size),total)
                batch = pool.iloc[cursor:end_i]
                codes = batch["code"].tolist()
                names = dict(zip(batch["code"],batch["code_name"]))
                live_progress = st.progress(
                    min(cursor/total,1.0) if total else 0.0,
                    text=f"准备扫描：已完成 {cursor:,}/{total:,}"
                )
                live_status = st.empty()
                live_diag = st.empty()

                def _scan_progress(done,batch_total,code_now,name_now,stage,found,stats_now):
                    overall_done = min(cursor+done,total)
                    overall_pct = (overall_done/total) if total else 0.0
                    live_progress.progress(
                        min(overall_pct,1.0),
                        text=(
                            f"实时进度 {overall_done:,}/{total:,}（{overall_pct:.1%}） · "
                            f"本批 {done:,}/{batch_total:,} · 已发现 {found} 只"
                        )
                    )
                    live_status.caption(
                        f"当前：{display_code(code_now)} {name_now} · {stage}"
                    )
                    live_diag.caption(
                        f"结构初筛 {stats_now.get('快速初筛通过',0)} · "
                        f"EV计算 {stats_now.get('EV阶段',0)} · 缓存 {stats_now.get('EV缓存命中',0)} · "
                        f"优先 {stats_now.get('优先机会',0)} · 观察 {stats_now.get('候选观察',0)} · "
                        f"流动性不足 {stats_now.get('流动性不足',0)}"
                    )

                batch_result,batch_stats = screen_codes(
                    codes,names,benchmark_df=benchmark_df,
                    progress_callback=_scan_progress
                )
                st.session_state["scan_last_stats"] = batch_stats
                live_progress.progress(
                    (end_i/total) if total else 1.0,
                    text=f"本批完成：已扫描 {end_i:,}/{total:,}"
                )
                live_status.caption("本批扫描完成。")

                old_result = st.session_state.get("scan_results")
                if not isinstance(old_result,pd.DataFrame) or old_result.empty:
                    merged = batch_result.copy()
                elif batch_result.empty:
                    merged = old_result.copy()
                else:
                    merged = pd.concat([old_result,batch_result],ignore_index=True)
                    merged = merged.drop_duplicates("代码",keep="last")
                    tier_order={"优先机会":0,"候选观察":1}
                    merged["_tier"]=merged["机会状态"].map(tier_order).fillna(9)
                    merged["_evsort"]=pd.to_numeric(merged["保守EV(R)"],errors="coerce").fillna(-999)
                    merged = merged.sort_values(
                        ["_tier","_evsort","历史净EV(R)","技术分/100"],
                        ascending=[True,False,False,False]
                    ).drop(columns=["_tier","_evsort"]).reset_index(drop=True)

                st.session_state["scan_results"] = merged
                st.session_state["scan_cursor"] = end_i
                st.session_state["scan_total"] = total
                st.session_state["scan_done"] = end_i>=total
            except Exception as e:
                st.error(f"选股失败：{e}")
            finally:
                try: bs.logout()
                except Exception: pass

    scan_market = st.session_state.get("scan_market")
    if scan_market:
        p = automatic_entry_policy(scan_market[0])
        bench_label = scan_market[2] if len(scan_market)>2 else "沪深300"
        st.info(
            f"大盘环境（{bench_label}）：{scan_market[1]} · {scan_market[0]}/100；"
            f"本轮自动门槛：技≥{p['技术']} / 买≥{p['买点']} / 周≥{p['周线']} / "
            f"RR≥{p['盈亏比']:.2f} / RS≥{p['相对强度']} / 机会≥{p['机会']}。"
        )

    total = int(st.session_state.get("scan_total",0))
    cursor = int(st.session_state.get("scan_cursor",0))
    result = st.session_state.get("scan_results")

    if total>0:
        pct = min(cursor/total,1.0)
        st.progress(pct,text=f"已扫描 {cursor:,} / {total:,} 只（{pct:.1%}）")
        if cursor<total:
            st.info(f"还有 {total-cursor:,} 只未扫描。点击“扫描下一批”继续。")
        else:
            st.success("✅ 当前股票池已全部扫描完成。")

    if isinstance(result,pd.DataFrame):
        if result.empty:
            if cursor>0:
                st.warning("已扫描部分暂未发现“优先机会/候选观察”。这代表当前结构普遍较弱，不会为了凑数量强行选股。")
        else:
            n_priority = int((result["机会状态"]=="优先机会").sum()) if "机会状态" in result.columns else 0
            n_watch = int((result["机会状态"]=="候选观察").sum()) if "机会状态" in result.columns else 0
            st.success(f"当前累计 {len(result)} 只：优先机会 {n_priority} · 候选观察 {n_watch}")
            pick = result.head(100).drop(columns=["_market_score"],errors="ignore").copy()
            pick.insert(0,"加入持仓",False)
            edited_pick = st.data_editor(
                pick,
                use_container_width=True,
                hide_index=True,
                disabled=[x for x in pick.columns if x!="加入持仓"],
                column_config={
                    "加入持仓":st.column_config.CheckboxColumn("加入持仓",help="勾选后可批量加入持仓")
                },
                key="screen_pick_editor"
            )
            ab1,ab2 = st.columns(2)
            add_selected = ab1.button("➕ 加入勾选持仓",type="primary",use_container_width=True)
            add_all = ab2.button("➕ 全部候选加入持仓",use_container_width=True)

            if add_selected or add_all:
                chosen = pick if add_all else edited_pick[edited_pick["加入持仓"]==True].drop(columns=["加入持仓"],errors="ignore")
                if add_all:
                    chosen = chosen.drop(columns=["加入持仓"],errors="ignore")
                if chosen.empty:
                    st.warning("请先勾选要加入持仓的股票。")
                else:
                    try:
                        bs_login()
                        ok,errs = add_screener_rows_to_positions(chosen)
                        if ok:
                            st.success(f"已加入/更新 {ok} 只持仓。加入时暂用筛选收盘价作为成本，可在持仓页直接修改成实际成交价。")
                            st.session_state.pop("holding_view",None)
                        if errs:
                            st.warning("部分加入失败："+"；".join(errs[:8]))
                    except Exception as e:
                        st.error(f"加入持仓失败：{e}")
                    finally:
                        try: bs.logout()
                        except Exception: pass

            st.download_button(
                "⬇️ 导出当前候选",
                result.drop(columns=["_market_score"],errors="ignore").to_csv(index=False).encode("utf-8-sig"),
                "screen_candidates.csv","text/csv",use_container_width=True
            )
            stats_last = st.session_state.get("scan_last_stats") or {}
            if stats_last:
                st.caption(
                    f"本批诊断：扫描 {stats_last.get('扫描',0)} · "
                    f"快速初筛通过 {stats_last.get('快速初筛通过',0)} · "
                    f"进入EV阶段 {stats_last.get('EV阶段',0)} · "
                    f"EV缓存命中 {stats_last.get('EV缓存命中',0)} · "
                    f"流动性不足 {stats_last.get('流动性不足',0)} · "
                    f"数据异常 {stats_last.get('数据异常',0)}"
                )
            st.caption("排序核心已改为保守EV：优先机会要求真实交易EV、保守EV与2倍成本压力EV为正；候选观察表示EV点估计为正但样本或置信度不足。")

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
                        try: bs.logout()
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
                try: bs.logout()
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
                try: bs.logout()
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
                    try: bs.logout()
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
                try: bs.logout()
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
