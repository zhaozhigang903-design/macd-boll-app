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

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analysis_history.db"

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
        st.info("暂无分析结果。输入A股代码后生成决策，结果会固定显示在这里。")
        return

    score = report.get("score", 0)
    weekly = report.get("weekly_score")
    weekly_txt = "—" if weekly is None else f"{weekly:.0f}"
    symbol = report.get("symbol") or "当前标的"
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
      <div class="cockpit-kicker">最新决策 · {_safe(symbol)} · {_safe(updated)}</div>
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

    if report.get("intraday"):
        st.warning("盘中截图：信号尚未定型，已降低置信度。")
    if report.get("confidence",0) < 65:
        st.error("截图清晰度不足，本次只作观察，不据此执行。")

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
    if weekly is None:
        st.caption("总技术分 = 趋势50% + 动能35% + 量能15%；各分项满分100。")
    else:
        st.caption("总技术分 = 趋势38% + 动能30% + 周线22% + 量能10%；各分项满分100。")
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
    if s.startswith(("sh.","sz.")):
        return s
    digits = re.sub(r"\D","",s)
    if len(digits) != 6:
        return s
    if digits.startswith(("5","6","9")):
        return "sh." + digits
    return "sz." + digits

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

def stock_basic_name(code):
    rs = bs.query_stock_basic(code=code)
    df = _rs_to_df(rs)
    if df.empty:
        return display_code(code)
    for col in ["code_name","name"]:
        if col in df.columns and str(df.iloc[0][col]).strip():
            return str(df.iloc[0][col]).strip()
    return display_code(code)

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
    return df

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
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO market_cache_meta(code,last_checked,updated_at)
           VALUES(?,?,?)
           ON CONFLICT(code) DO UPDATE SET
             last_checked=excluded.last_checked,
             updated_at=excluded.updated_at""",
        (code,today,now)
    )
    conn.commit()
    conn.close()

def _download_daily(code, start, end):
    if start > end:
        return pd.DataFrame()
    fields = "date,code,open,high,low,close,volume,amount,pctChg,turn,tradestatus,isST"
    rs = bs.query_history_k_data_plus(
        code, fields, start_date=start, end_date=end, frequency="d", adjustflag="2"
    )
    df = _rs_to_df(rs)
    if df.empty:
        return df
    df = df.rename(columns={"date":"trade_date","volume":"vol"})
    for col in ["open","high","low","close","vol","amount","pctChg","turn"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    if "tradestatus" in df.columns:
        df = df[df["tradestatus"].astype(str) == "1"]
    return df.sort_values("trade_date").reset_index(drop=True)

def fetch_stock_daily(code, years=3):
    code = normalize_code(code)
    end = datetime.now().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today() - pd.Timedelta(days=365*years+180)).strftime("%Y-%m-%d")
    cache_min, cache_max, last_checked = _cache_bounds(code, "2")
    today = datetime.now().strftime("%Y-%m-%d")

    # 首次读取：下载完整所需区间。
    if not cache_min or not cache_max:
        fresh = _download_daily(code, start, end)
        _save_daily_cache(fresh, code, "2")
        _mark_cache_checked(code)
    else:
        # 如果请求区间比缓存更早，只补前段。
        if start < cache_min:
            pre_end = (pd.Timestamp(cache_min) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            older = _download_daily(code, start, pre_end)
            _save_daily_cache(older, code, "2")

        # 每只股票每天最多检查一次最新行情，避免重复请求BaoStock。
        if last_checked != today:
            next_start = (pd.Timestamp(cache_max) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            newer = _download_daily(code, next_start, end)
            _save_daily_cache(newer, code, "2")
            _mark_cache_checked(code)

    return _read_daily_cache(code, start, end, "2")

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
    d = df.copy().sort_values("trade_date").reset_index(drop=True)
    close = d["close"]
    d["boll_mid"] = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    d["boll_up"] = d["boll_mid"] + 2*std
    d["boll_low"] = d["boll_mid"] - 2*std
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    d["dif"] = ema12 - ema26
    d["dea"] = d["dif"].ewm(span=9, adjust=False).mean()
    d["macd"] = 2*(d["dif"]-d["dea"])
    d["vol_ma5"] = d["vol"].rolling(5).mean()
    d["vol_ma10"] = d["vol"].rolling(10).mean()
    d["boll_slope"] = d["boll_mid"] - d["boll_mid"].shift(3)
    d["dif_slope"] = d["dif"] - d["dif"].shift(3)
    d["high20"] = d["high"].rolling(20).max()
    d["low20"] = d["low"].rolling(20).min()
    return d

def weekly_from_daily(df):
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy().set_index("trade_date")
    agg = {
        "open":"first","high":"max","low":"min","close":"last","vol":"sum"
    }
    if "amount" in d.columns:
        agg["amount"] = "sum"
    w = d.resample("W-FRI").agg(agg).dropna(subset=["close"]).reset_index()
    return add_indicators(w)

def numeric_score(latest_d, latest_w=None):
    trend = 0
    slope = latest_d.get("boll_slope", np.nan)
    if pd.isna(slope): trend += 15
    elif slope > 0: trend += 45
    elif abs(slope) <= max(abs(latest_d.get("boll_mid",0))*0.001, 1e-9): trend += 24
    else: trend += 5

    close = latest_d.get("close", np.nan)
    mid = latest_d.get("boll_mid", np.nan)
    if pd.notna(close) and pd.notna(mid):
        if close > mid*1.005: trend += 35
        elif close < mid*0.995: trend += 4
        else: trend += 20
    else: trend += 12

    up, low = latest_d.get("boll_up",np.nan), latest_d.get("boll_low",np.nan)
    band = ((up-low)/mid) if pd.notna(up) and pd.notna(low) and pd.notna(mid) and mid else np.nan
    trend += 20 if pd.notna(band) and band > 0.12 else (8 if pd.notna(band) and band < 0.05 else 13)
    trend = clamp(trend)

    momentum = 0
    dif, dea, macd = latest_d.get("dif",np.nan), latest_d.get("dea",np.nan), latest_d.get("macd",np.nan)
    if pd.notna(dif) and pd.notna(dea):
        if dif > 0 and dea > 0: momentum += 35
        elif abs(dif) < max(abs(close)*0.002 if pd.notna(close) else 0.01,0.01): momentum += 21
        else: momentum += 5
        ds = latest_d.get("dif_slope",np.nan)
        momentum += 25 if pd.notna(ds) and ds > 0 else (13 if pd.isna(ds) or abs(ds) < 1e-9 else 3)
        momentum += 17 if dif > dea else 2
        prev_macd = latest_d.get("macd_prev", np.nan)
        if pd.notna(macd):
            if macd > 0 and (pd.isna(prev_macd) or macd >= prev_macd): momentum += 23
            elif macd > 0: momentum += 15
            elif pd.notna(prev_macd) and macd > prev_macd: momentum += 12
            else: momentum += 1
    else:
        momentum = 38
    momentum = clamp(momentum)

    confirm = 45
    vol = latest_d.get("vol",np.nan)
    v5, v10 = latest_d.get("vol_ma5",np.nan), latest_d.get("vol_ma10",np.nan)
    if pd.notna(vol) and pd.notna(v5) and pd.notna(v10):
        if vol > v5*1.35 and vol > v10*1.35: confirm += 20
        elif vol > v5 and vol > v10: confirm += 12
        elif vol < v5 and vol < v10: confirm -= 8
        else: confirm += 5
    confirm = clamp(confirm)

    weekly = None
    if latest_w is not None:
        weekly = 0
        ws = latest_w.get("boll_slope",np.nan)
        weekly += 40 if pd.notna(ws) and ws > 0 else (22 if pd.isna(ws) or abs(ws)<1e-9 else 4)
        wc, wm = latest_w.get("close",np.nan), latest_w.get("boll_mid",np.nan)
        weekly += 30 if pd.notna(wc) and pd.notna(wm) and wc > wm else (18 if pd.notna(wc) and pd.notna(wm) and wc >= wm*0.99 else 3)
        wd, we = latest_w.get("dif",np.nan), latest_w.get("dea",np.nan)
        weekly += 20 if pd.notna(wd) and pd.notna(we) and wd > 0 and we > 0 else (12 if pd.notna(wd) and abs(wd)<0.05 else 2)
        weekly += 10 if pd.notna(wd) and pd.notna(we) and wd > we else 1
        weekly = clamp(weekly)

    overall = (0.50*trend + 0.35*momentum + 0.15*confirm) if weekly is None else (0.38*trend + 0.30*momentum + 0.22*weekly + 0.10*confirm)
    return round(overall,1), round(trend,1), round(momentum,1), (round(weekly,1) if weekly is not None else None), round(confirm,1)

def deterministic_report(code, name, df, position_state, fundamentals_ok):
    di = add_indicators(df)
    wi = weekly_from_daily(df)
    if len(di) < 60:
        raise RuntimeError("历史数据不足，无法计算指标")
    drow = di.iloc[-1].to_dict()
    drow["macd_prev"] = di.iloc[-2]["macd"] if len(di)>1 else np.nan
    wrow = wi.iloc[-1].to_dict() if len(wi) >= 20 else None
    score, trend, momentum, weekly, confirm = numeric_score(drow, wrow)
    weekly_ok = weekly is not None and weekly >= 60
    rating = grade(score, weekly_ok, 100)
    stage = stage_from(score, {}, weekly_ok)

    hard_bear = (
        pd.notna(drow.get("boll_slope")) and drow.get("boll_slope") < 0
        and pd.notna(drow.get("boll_mid")) and drow.get("close") < drow.get("boll_mid")
        and pd.notna(drow.get("dif")) and drow.get("dif") < 0
        and pd.notna(drow.get("dea")) and drow.get("dif") < drow.get("dea")
    )
    state, reason = state_from(score, rating, 100, False, weekly_ok, position_state, fundamentals_ok, hard_bear)

    mid = drow.get("boll_mid",np.nan)
    support = drow.get("low20",np.nan)
    resistance = drow.get("high20",np.nan)
    if pd.notna(mid) and pd.notna(support):
        support_txt = f"{support:.2f}（20日低点）/ {mid:.2f}（中轨）"
    else:
        support_txt = "未知"
    resistance_txt = f"{resistance:.2f}（20日高点）" if pd.notna(resistance) else "未知"

    boll_dir = "向上" if drow.get("boll_slope",0) > 0 else ("向下" if drow.get("boll_slope",0) < 0 else "走平")
    pos = "中轨上" if pd.notna(mid) and drow.get("close") > mid else "中轨下"
    zero = "零轴上" if drow.get("dif",0) > 0 and drow.get("dea",0) > 0 else "零轴下/附近"
    cross = "金叉" if drow.get("dif",0) > drow.get("dea",0) else "死叉"

    essence = f"日线中轨{boll_dir}、价格位于{pos}；MACD处于{zero}并呈{cross}。"
    if weekly is not None:
        essence += f" 周线分{weekly:.0f}/100。"

    up = []
    down = []
    if boll_dir != "向上": up.append("日线中轨转向上")
    if pos != "中轨上" and pd.notna(mid): up.append(f"收盘站稳中轨{mid:.2f}")
    if zero != "零轴上": up.append("MACD回到零轴上")
    if weekly is not None and weekly < 60: up.append("周线分升至60以上")
    down.append(f"失守20日低点{support:.2f}" if pd.notna(support) else "关键支撑失守")
    if pd.notna(mid): down.append(f"持续运行于中轨{mid:.2f}下方")

    return {
        "updated_at": datetime.now().strftime("%m-%d %H:%M"),
        "symbol": f"{name} / {display_code(code)}",
        "state":state, "rating":rating, "stage":stage, "state_reason":reason,
        "score":score, "trend":trend, "momentum":momentum, "weekly_score":weekly,
        "confirm":confirm, "confidence":100, "essence":essence,
        "support":support_txt, "resistance":resistance_txt,
        "upgrade":"；".join(up[:2]) if up else "维持强势并继续确认",
        "downgrade":"；".join(down[:2]), "delta":None, "intraday":False,
        "daily":{
            "boll_mid_direction":boll_dir, "price_vs_mid":pos,
            "macd_zero_zone":zero, "dif_direction":"向上" if drow.get("dif_slope",0)>0 else "向下",
            "cross":cross,
            "bar_momentum":"红柱" if drow.get("macd",0)>0 else "绿柱",
            "volume_state":"高于MA5/MA10" if pd.notna(drow.get("vol_ma5")) and drow.get("vol")>drow.get("vol_ma5") and drow.get("vol")>drow.get("vol_ma10") else "普通/缩量",
            "volume_trend":"—","divergence":"未做自动背离判定"
        },
        "boll_analysis":f"中轨{boll_dir}，收盘{drow.get('close',np.nan):.2f}，中轨{mid:.2f}。" if pd.notna(mid) else "",
        "macd_analysis":f"DIF {drow.get('dif',np.nan):.3f}，DEA {drow.get('dea',np.nan):.3f}，{cross}。",
        "weekly_analysis":f"周线技术分 {weekly:.0f}/100。" if weekly is not None else "",
        "resonance":"数据计算模式：全部指标由OHLCV直接计算，不依赖图片识别。",
        "data_source":"BaoStock",
        "adjustment":"前复权",
        "latest_date":di.iloc[-1]["trade_date"].strftime("%Y-%m-%d"),
        "latest_close":float(di.iloc[-1]["close"]),
        "_df":di
    }

def latest_trade_date():
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    start = (pd.Timestamp.today() - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    rs = bs.query_trade_dates(start_date=start, end_date=end)
    df = _rs_to_df(rs)
    if df.empty:
        return end
    if "is_trading_day" in df.columns:
        df = df[df["is_trading_day"].astype(str) == "1"]
    if df.empty:
        return end
    return str(df["calendar_date"].max())

def fetch_universe(kind):
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
                df = df[df["tradeStatus"].astype(str) == "1"]

    if df.empty:
        return pd.DataFrame(columns=["code","code_name"])
    code_col = "code" if "code" in df.columns else df.columns[0]
    name_col = "code_name" if "code_name" in df.columns else ("codeName" if "codeName" in df.columns else None)
    out = pd.DataFrame({"code":df[code_col].astype(str)})
    out["code_name"] = df[name_col].astype(str) if name_col else out["code"]
    return out.drop_duplicates("code").reset_index(drop=True)

def build_score_series(df):
    d = add_indicators(df)
    w = weekly_from_daily(df)
    if d.empty or w.empty:
        return pd.DataFrame()
    w2 = w[["trade_date","boll_mid","boll_slope","close","dif","dea"]].copy()
    w2.columns = ["w_date","w_boll_mid","w_boll_slope","w_close","w_dif","w_dea"]
    m = pd.merge_asof(
        d.sort_values("trade_date"),
        w2.sort_values("w_date"),
        left_on="trade_date", right_on="w_date", direction="backward"
    )
    scores = []
    buy_scores = []
    rr_list = []
    for i,row in m.iterrows():
        r = row.to_dict()
        r["macd_prev"] = m.iloc[i-1]["macd"] if i>0 else np.nan
        wr = None
        if pd.notna(row.get("w_date")):
            wr = {
                "boll_slope":row.get("w_boll_slope"), "close":row.get("w_close"),
                "boll_mid":row.get("w_boll_mid"), "dif":row.get("w_dif"), "dea":row.get("w_dea")
            }
        score = numeric_score(r,wr)[0]
        bp, rr, _, _ = entry_quality(r)
        scores.append(score)
        buy_scores.append(bp)
        rr_list.append(rr)
    m["score"] = scores
    m["buy_score"] = buy_scores
    m["rr"] = rr_list
    return m

def entry_quality(r):
    close = r.get("close",np.nan)
    mid = r.get("boll_mid",np.nan)
    upper = r.get("boll_up",np.nan)
    low20 = r.get("low20",np.nan)
    high20 = r.get("high20",np.nan)
    slope = r.get("boll_slope",np.nan)
    dif = r.get("dif",np.nan)
    dea = r.get("dea",np.nan)
    vol = r.get("vol",np.nan)
    v5 = r.get("vol_ma5",np.nan)
    v10 = r.get("vol_ma10",np.nan)

    if pd.isna(close) or close <= 0:
        return 0, np.nan, np.nan, np.nan

    score = 0

    # 位置：中轨上方但不过度乖离最理想
    if pd.notna(mid) and mid > 0:
        dist_mid = close/mid - 1
        if 0 <= dist_mid <= 0.035:
            score += 35
        elif -0.02 <= dist_mid < 0:
            score += 24
        elif 0.035 < dist_mid <= 0.07:
            score += 20
        elif dist_mid > 0.10:
            score += 5
        else:
            score += 12
    else:
        score += 12

    # 趋势：只奖励向上趋势
    if pd.notna(slope) and slope > 0:
        score += 25
    elif pd.notna(slope) and slope < 0:
        score += 4
    else:
        score += 12

    # 动能：零轴上金叉最好；零轴下反弹不追高
    if pd.notna(dif) and pd.notna(dea):
        if dif > 0 and dea > 0 and dif > dea:
            score += 22
        elif dif > dea:
            score += 14
        else:
            score += 5
    else:
        score += 8

    # 量能：温和高于均量优于极端放量或明显缩量
    if pd.notna(vol) and pd.notna(v5) and pd.notna(v10) and v5 > 0 and v10 > 0:
        ratio = vol/max(v5,v10)
        if 1.0 <= ratio <= 1.6:
            score += 18
        elif 0.75 <= ratio < 1.0:
            score += 12
        elif ratio > 2.0:
            score += 7
        else:
            score += 9
    else:
        score += 8

    # 过度靠近上轨/20日高点时降分，避免“强但追高”
    overextended = False
    if pd.notna(upper) and upper > 0 and close >= upper*0.985:
        score -= 12
        overextended = True
    if pd.notna(high20) and high20 > 0 and close >= high20*0.985:
        score -= 8
        overextended = True

    # 风险收益：用最近可见支撑与20日高点/上轨构造，不人为保证目标价
    supports = [x for x in [mid,low20] if pd.notna(x) and x < close]
    stop = max(supports) if supports else np.nan
    targets = [x for x in [high20,upper] if pd.notna(x) and x > close]
    target = min(targets) if targets else np.nan
    rr = np.nan
    if pd.notna(stop) and pd.notna(target) and close > stop:
        rr = (target-close)/(close-stop)

    score = int(clamp(score))
    if overextended and score > 75:
        score = 75
    return score, (round(float(rr),2) if pd.notna(rr) else np.nan), stop, target

def historical_edge(df, current_score, current_buy_score, horizon=20):
    m = build_score_series(df)
    if m.empty or len(m) < horizon + 80:
        return {"样本":0,"胜率":np.nan,"平均收益":np.nan,"中位收益":np.nan}

    m["fwd"] = m["close"].shift(-horizon)/m["close"] - 1
    lo = max(0,current_score-5)
    hi = min(100,current_score+5)

    # 相似信号：技术分接近 + 买点分不低于当前附近；每20天只取一个，减少同一波行情重复计数
    cand = m[
        (m["score"]>=lo) & (m["score"]<=hi) &
        (m["buy_score"]>=max(50,current_buy_score-10)) &
        m["fwd"].notna()
    ].copy()
    if cand.empty:
        return {"样本":0,"胜率":np.nan,"平均收益":np.nan,"中位收益":np.nan}

    picked = []
    last_i = -999
    for idx in cand.index:
        pos = m.index.get_loc(idx)
        if pos-last_i >= horizon:
            picked.append(idx)
            last_i = pos
    s = cand.loc[picked,"fwd"] if picked else pd.Series(dtype=float)
    if s.empty:
        return {"样本":0,"胜率":np.nan,"平均收益":np.nan,"中位收益":np.nan}
    return {
        "样本":int(len(s)),
        "胜率":float((s>0).mean()),
        "平均收益":float(s.mean()),
        "中位收益":float(s.median())
    }

def opportunity_score(technical, buy_score, rr, hist):
    # 机会分只做排序：技术40% + 买点35% + 盈亏比15% + 历史样本10%
    rr_score = 35
    if pd.notna(rr):
        rr_score = clamp(rr/3.0*100)
    hist_score = 50
    if hist.get("样本",0) >= 5 and pd.notna(hist.get("胜率")):
        hist_score = clamp(hist["胜率"]*100)
    score = 0.40*technical + 0.35*buy_score + 0.15*rr_score + 0.10*hist_score
    return round(float(score),1)

def screen_codes(codes, name_map=None, min_score=62, min_buy_score=60, min_rr=1.2):
    rows = []
    name_map = name_map or {}
    for code in codes:
        try:
            # 第一阶段：用缓存/1年数据快速判断当前技术结构
            d = fetch_stock_daily(code, years=1)
            if len(d) < 150:
                continue
            name = name_map.get(code) or stock_basic_name(code)
            di = add_indicators(d)
            wi = weekly_from_daily(d)
            lr = di.iloc[-1].to_dict()
            lr["macd_prev"] = di.iloc[-2]["macd"] if len(di)>1 else np.nan
            wr = wi.iloc[-1].to_dict() if not wi.empty else None
            technical, trend, momentum, weekly, confirm = numeric_score(lr, wr)
            buy_score, rr, stop, target = entry_quality(lr)

            if technical < min_score or buy_score < min_buy_score:
                continue
            if pd.notna(rr) and rr < min_rr:
                continue
            if weekly is not None and weekly < 50:
                continue

            # 第二阶段：只对初筛通过者补3年历史，统计相似信号20日表现
            hist_df = fetch_stock_daily(code, years=3)
            hist = historical_edge(hist_df, technical, buy_score, horizon=20)
            opp = opportunity_score(technical,buy_score,rr,hist)

            rows.append({
                "代码":display_code(code), "名称":name,
                "机会分/100":opp,
                "技术分/100":technical,
                "买点分/100":buy_score,
                "盈亏比":rr if pd.notna(rr) else np.nan,
                "20日胜率":hist["胜率"],
                "样本":hist["样本"],
                "20日均收益":hist["平均收益"],
                "趋势/100":trend, "动能/100":momentum,
                "周线/100":weekly, "量能/100":confirm,
                "收盘":round(float(lr["close"]),2),
                "风险位":round(float(stop),2) if pd.notna(stop) else np.nan,
                "参考压力":round(float(target),2) if pd.notna(target) else np.nan
            })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["机会分/100","买点分/100","技术分/100"], ascending=False
    ).reset_index(drop=True)

def run_backtest(df, entry_score=78, exit_score=48, fee_bps=8):
    d = add_indicators(df)
    w = weekly_from_daily(df)
    if len(d) < 100 or len(w) < 20:
        return pd.DataFrame(), {}
    w2 = w[["trade_date","boll_mid","boll_slope","close","dif","dea"]].copy()
    w2.columns = ["w_date","w_boll_mid","w_boll_slope","w_close","w_dif","w_dea"]
    m = pd.merge_asof(d.sort_values("trade_date"), w2.sort_values("w_date"), left_on="trade_date", right_on="w_date", direction="backward")
    scores = []
    for i,row in m.iterrows():
        r = row.to_dict()
        r["macd_prev"] = m.iloc[i-1]["macd"] if i>0 else np.nan
        wr = None
        if pd.notna(row.get("w_date")):
            wr = {"boll_slope":row.get("w_boll_slope"),"close":row.get("w_close"),"boll_mid":row.get("w_boll_mid"),"dif":row.get("w_dif"),"dea":row.get("w_dea")}
        scores.append(numeric_score(r,wr)[0])
    m["score"] = scores
    m["signal"] = 0
    in_pos = False
    for i in range(len(m)):
        s = m.iloc[i]["score"]
        if not in_pos and s >= entry_score:
            m.at[m.index[i],"signal"] = 1
            in_pos = True
        elif in_pos and s <= exit_score:
            m.at[m.index[i],"signal"] = -1
            in_pos = False
    m["position"] = m["signal"].replace(0,np.nan).replace(-1,0).ffill().fillna(0).shift(1).fillna(0)
    m["ret"] = m["close"].pct_change().fillna(0)
    turnover = m["position"].diff().abs().fillna(m["position"])
    fee = fee_bps/10000
    m["strategy_ret"] = m["position"]*m["ret"] - turnover*fee
    m["净值"] = (1+m["strategy_ret"]).cumprod()
    m["买入持有"] = (1+m["ret"]).cumprod()
    eq = m["净值"]
    total = eq.iloc[-1]-1
    n_years = max((m["trade_date"].iloc[-1]-m["trade_date"].iloc[0]).days/365.25,0.01)
    annual = eq.iloc[-1]**(1/n_years)-1
    dd = (eq/eq.cummax()-1).min()
    metrics = {
        "累计收益":total, "年化收益":annual, "最大回撤":dd,
        "交易次数":int((m["signal"]==1).sum()), "买入持有":m["买入持有"].iloc[-1]-1
    }
    return m, metrics

def history(limit=300):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM analyses ORDER BY id DESC LIMIT ?", conn, params=(limit,))
    conn.close()
    return df

init_db()

st.markdown("<div style='height:.15rem'></div>", unsafe_allow_html=True)
st.title("📈 日线 × 周线 中长线决策引擎")
st.caption("数据驱动版 · 自动获取日K → 聚合周K → 统一计算BOLL/MACD/VOL → 规则评分。")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📷 分析", "🔎 选股", "🧪 回测", "📚 历史", "🧠 方法", "⚙️ 设置"])

with tab6:
    st.subheader("数据设置")
    st.success("A股行情使用 BaoStock，无需 Token 或会员。")
    st.info("统一使用前复权日线数据；周线由同一套日线聚合，分析、选股、回测使用相同数据口径和相同公式。")
    st.caption("BaoStock采用自身复权算法，因此历史价格可能与同花顺/通达信存在细微差异；App内部始终保持同一数据源和同一复权口径。")

    st.subheader("本地行情缓存")
    cs = market_cache_stats()
    c1,c2,c3 = st.columns(3)
    c1.metric("已缓存股票", f"{cs['stocks']:,}")
    c2.metric("日线记录", f"{cs['rows']:,}")
    c3.metric("数据库大小", f"{cs['db_mb']:.1f} MB")
    st.caption(f"缓存区间：{cs['min_date']} ～ {cs['max_date']}。首次下载完整历史，以后同一股票每天只补最新数据。")
    if st.button("🗑️ 清空行情缓存", use_container_width=True):
        clear_market_cache()
        st.success("行情缓存已清空。")
        st.rerun()
    st.warning("当前缓存位于Render本机SQLite：日常重复扫描会明显加速，但服务重新部署/重建实例时可能被清空。")
    st.markdown("iPhone：Safari打开网址 → 分享 → **添加到主屏幕**。")

with tab5:
    st.subheader("这套系统怎么做决策")
    st.markdown("""
**核心框架：四层证据，而不是指标堆砌。每一项都是100分制。**

1. **趋势分（满分100）**：BOLL中轨方向、价格相对中轨、带宽状态。  
2. **动能分（满分100）**：MACD零轴、DIF方向、金叉/死叉、柱体加减速。  
3. **周线分（满分100）**：周线确认日线；没有周线时不显示该项。  
4. **量能分（满分100）**：成交量与背离，只做确认，不抢主导权。成交量读取 **VOL柱 + MA5 + MA10**。  

**总技术分也是100分制：**
- 有周线：趋势38% + 动能30% + 周线22% + 量能10%
- 无周线：趋势50% + 动能35% + 量能15%  

**选股目标：寻找交易机会，不是寻找最高技术分。**

- **技术分**：这只股票的趋势/动能是否值得关注。
- **买点分**：当前价格位置是否适合介入，越追高分数越低。
- **盈亏比**：以中轨/20日低点作为风险参考，以20日高点/BOLL上轨作为压力参考。
- **历史胜率**：该股票过去出现相似技术分和买点分时，未来20日获得正收益的比例。
- **机会分**：技术40% + 买点35% + 盈亏比15% + 历史胜率10%，用于候选排序，不代表上涨概率。

**关键原则**
- 零轴下金叉 = 先看修复，不把反弹当反转。
- BOLL中轨向下时，买入类信号天然降级。
- 日线强、周线弱 = 先观察，不把局部反弹当中长线主升。
- 技术面只负责“什么时候风险收益更好”，不替代基本面和估值判断。
""")
    st.warning("评分是“技术证据质量分”，不是上涨概率，也不是收益率预测。真正的收益来自正期望：胜率 × 盈亏比 × 仓位纪律 × 足够样本。")

with tab1:
    st.subheader("决策驾驶舱")
    render_cockpit(st.session_state.get("last_report"))
    st.divider()

    st.subheader("① 自动数据分析")
    st.caption("输入A股代码即可。系统自动获取日K、聚合周K，并计算BOLL/MACD/VOL；无需上传截图。")
    a1,a2 = st.columns([1.2,1])
    with a1:
        auto_code = st.text_input("A股代码", placeholder="例如 600519 / 000001 / 300750", key="auto_code")
    with a2:
        auto_horizon = st.selectbox("持有周期", ["2–8周","2–6个月","6–18个月"], index=1, key="auto_horizon")
    a3,a4 = st.columns(2)
    with a3:
        auto_position = st.selectbox("当前仓位", ["未持有","轻仓≤25%","中等25–50%","重仓>50%"], key="auto_position")
    with a4:
        auto_fund = st.checkbox("基本面/估值已验证", value=False, key="auto_fund")

    if st.button("⚡ 自动生成决策", type="primary", use_container_width=True):
        if not auto_code.strip():
            st.error("请输入A股代码。")
        else:
            with st.spinner("正在获取行情并计算日线/周线指标..."):
                try:
                    bs_login()
                    code = normalize_code(auto_code)
                    df_auto = fetch_stock_daily(code, years=3)
                    name = stock_basic_name(code)
                    report = deterministic_report(code, name, df_auto, auto_position, auto_fund)
                    prev = previous(report["symbol"])
                    if prev and prev.get("score") is not None:
                        try: report["delta"] = report["score"] - float(prev.get("score"))
                        except Exception: pass
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
                        "symbol":report["symbol"],"market":"A股","horizon":auto_horizon,
                        "position_state":auto_position,"rating":report["rating"],"state":report["state"],
                        "stage":report["stage"],"confidence":100,"mode":"BaoStock自动数据",
                        "weekly_used":True
                    }
                    metrics = (report["score"],report["trend"],report["momentum"],report["weekly_score"],report["confirm"],False,False)
                    save_result(meta,xsave,metrics,json.dumps({"source":"BaoStock"},ensure_ascii=False))
                    report.pop("_df",None)
                    st.rerun()
                except Exception as e:
                    st.error(f"自动分析失败：{e}")
                finally:
                    try: bs.logout()
                    except Exception: pass

    st.divider()
    st.caption("当前仅保留数据驱动模式：日K直接获取，周K由同一套日K聚合生成，避免截图识别误差。")

    with st.expander("仓位风险计算器"):
        rc1, rc2 = st.columns(2)
        with rc1:
            capital = st.number_input("账户资金", min_value=0.0, value=100000.0, step=10000.0, key="risk_capital")
            risk_pct = st.number_input("单次最大风险 %", min_value=0.1, max_value=5.0, value=0.8, step=0.1, key="risk_pct")
        with rc2:
            entry = st.number_input("计划入场价", min_value=0.0, value=0.0, step=0.1, key="risk_entry")
            stop = st.number_input("技术失效价", min_value=0.0, value=0.0, step=0.1, key="risk_stop")
        if entry > 0 and stop > 0 and entry > stop:
            risk_cash = capital * risk_pct / 100
            shares = int(risk_cash / (entry-stop))
            position_value = shares * entry
            pct = (position_value/capital*100) if capital else 0
            st.info(f"风险预算 {risk_cash:,.0f}；理论上限约 {shares:,} 股；约占资金 {pct:.1f}%")

with tab2:
    st.subheader("自动选股")
    st.caption("目标不是找最高分股票，而是找可执行的交易机会：技术结构 + 当前买点 + 盈亏比 + 历史相似信号。首次扫描会建立缓存，全市场可分批扫描到100%。")

    universe = st.selectbox("选股范围", ["全A股（沪深）","沪深300","中证500","上证50"], index=0)
    f1,f2,f3 = st.columns(3)
    with f1:
        batch_size = st.selectbox("每批扫描", [100,200,300,500], index=2)
    with f2:
        min_score = st.slider("最低技术分", 50, 90, 62)
    with f3:
        min_buy_score = st.slider("最低买点分", 40, 90, 60)

    g1,g2 = st.columns(2)
    with g1:
        min_rr = st.selectbox("最低盈亏比", [0.8,1.0,1.2,1.5,2.0], index=2)
    with g2:
        exclude_st = st.checkbox("排除ST/*ST", value=True)

    s1,s2 = st.columns(2)
    start_scan = s1.button("🔎 开始/重新扫描", type="primary", use_container_width=True)
    continue_scan = s2.button("➡️ 扫描下一批", use_container_width=True)

    if start_scan:
        st.session_state["scan_cursor"] = 0
        st.session_state["scan_results"] = pd.DataFrame()
        st.session_state["scan_universe"] = universe
        st.session_state["scan_done"] = False

    if start_scan or continue_scan:
        with st.spinner("正在获取股票池并扫描本批次..."):
            try:
                bs_login()
                pool = fetch_universe(universe)
                if exclude_st and not pool.empty:
                    pool = pool[~pool["code_name"].str.upper().str.contains(r"(^ST|\*ST)", regex=True, na=False)]
                pool = pool.reset_index(drop=True)

                total = len(pool)
                cursor = int(st.session_state.get("scan_cursor",0))
                if st.session_state.get("scan_universe") != universe:
                    cursor = 0
                    st.session_state["scan_results"] = pd.DataFrame()
                    st.session_state["scan_universe"] = universe

                end_i = min(cursor + int(batch_size), total)
                batch = pool.iloc[cursor:end_i]
                codes = batch["code"].tolist()
                names = dict(zip(batch["code"], batch["code_name"]))
                batch_result = screen_codes(
                    codes, names,
                    min_score=min_score,
                    min_buy_score=min_buy_score,
                    min_rr=float(min_rr)
                )

                old_result = st.session_state.get("scan_results")
                if not isinstance(old_result,pd.DataFrame) or old_result.empty:
                    merged = batch_result.copy()
                elif batch_result.empty:
                    merged = old_result.copy()
                else:
                    merged = pd.concat([old_result,batch_result], ignore_index=True)
                    merged = merged.drop_duplicates("代码", keep="last")
                    merged = merged.sort_values(["机会分/100","买点分/100","技术分/100"], ascending=False).reset_index(drop=True)

                st.session_state["scan_results"] = merged
                st.session_state["scan_cursor"] = end_i
                st.session_state["scan_total"] = total
                st.session_state["scan_done"] = end_i >= total
            except Exception as e:
                st.error(f"选股失败：{e}")
            finally:
                try: bs.logout()
                except Exception: pass

    total = int(st.session_state.get("scan_total",0))
    cursor = int(st.session_state.get("scan_cursor",0))
    result = st.session_state.get("scan_results")

    if total > 0:
        pct = min(cursor/total,1.0)
        st.progress(pct, text=f"已扫描 {cursor:,} / {total:,} 只（{pct:.1%}）")
        if cursor < total:
            st.info(f"还有 {total-cursor:,} 只未扫描。点击“扫描下一批”继续，直到100%。")
        else:
            st.success("✅ 当前股票池已全部扫描完成。")

    if isinstance(result,pd.DataFrame):
        if result.empty:
            if cursor > 0:
                st.warning("已扫描部分暂未发现满足条件的标的。")
        else:
            st.success(f"当前累计筛出 {len(result)} 只候选")
            st.dataframe(result.head(100), use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ 导出当前候选",
                result.to_csv(index=False).encode("utf-8-sig"),
                "screen_candidates.csv",
                "text/csv",
                use_container_width=True
            )
            st.caption("候选表按“机会分”排序：技术结构只是第一层，还同时考虑当前买点、盈亏比和历史相似信号。胜率来自该股票历史相似信号的20日正收益比例；样本少时参考价值有限。")

with tab3:
    st.subheader("策略回测")
    st.caption("BaoStock历史日线 → 自动聚合周线 → 计算同一套技术分。信号收盘后形成，下一交易日生效。")
    bt_code = st.text_input("A股代码", placeholder="例如 600519", key="bt_code")
    b1,b2,b3 = st.columns(3)
    with b1:
        years = st.selectbox("回测年限",[2,3,5],index=1)
    with b2:
        entry_score = st.slider("入场分数",65,90,78)
    with b3:
        exit_score = st.slider("退出分数",30,65,48)
    fee_bps = st.number_input("单边交易成本（万分之一）", min_value=0.0, max_value=30.0, value=8.0, step=1.0)
    if st.button("🧪 开始回测", type="primary", use_container_width=True):
        if not bt_code.strip():
            st.error("请输入A股代码。")
        else:
            with st.spinner("正在下载历史行情并回测..."):
                try:
                    bs_login()
                    df_bt = fetch_stock_daily(bt_code.strip(), years=years)
                    curve, m = run_backtest(df_bt, entry_score, exit_score, fee_bps)
                    st.session_state["bt_curve"] = curve
                    st.session_state["bt_metrics"] = m
                except Exception as e:
                    st.error(f"回测失败：{e}")
                finally:
                    try: bs.logout()
                    except Exception: pass
    m = st.session_state.get("bt_metrics")
    curve = st.session_state.get("bt_curve")
    if isinstance(m,dict) and m:
        a,b,c1,c2 = st.columns(4)
        a.metric("累计收益", f"{m['累计收益']:.1%}")
        b.metric("年化收益", f"{m['年化收益']:.1%}")
        c1.metric("最大回撤", f"{m['最大回撤']:.1%}")
        c2.metric("交易次数", str(m["交易次数"]))
        st.caption(f"同期买入持有：{m['买入持有']:.1%}")
        if isinstance(curve,pd.DataFrame) and not curve.empty:
            st.line_chart(curve.set_index("trade_date")[["净值","买入持有"]], height=280)
            with st.expander("查看最近信号"):
                st.dataframe(curve[["trade_date","close","score","signal","position"]].tail(60), use_container_width=True, hide_index=True)
        st.warning("回测不代表未来收益；尚未完整模拟滑点、涨跌停、停牌、分红税等真实交易约束。")

with tab4:
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
