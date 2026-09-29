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
import tushare as ts
from openai import OpenAI

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
        st.info("暂无分析结果。上传日线/周线后生成决策，结果会固定显示在这里。")
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

    if weekly is None:
        st.caption("总技术分 = 趋势50% + 动能35% + 量能15%；各分项满分100。")
    else:
        st.caption("总技术分 = 趋势38% + 动能30% + 周线22% + 量能10%；各分项满分100。")
    st.caption(f"置信度 {report.get('confidence',0)}% · 同一组截图复用同一识别结果；技术分不是上涨概率。")


def get_tushare_token():
    return os.getenv("TUSHARE_TOKEN","") or st.session_state.get("tushare_token","")

def tushare_pro():
    token = get_tushare_token()
    if not token:
        return None
    return ts.pro_api(token)

def normalize_daily(df):
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("trade_date").reset_index(drop=True)
    for col in ["open","high","low","close","vol","amount"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out

def add_indicators(df):
    d = normalize_daily(df)
    if d.empty:
        return d
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
    return d

def weekly_from_daily(df):
    if df is None or df.empty:
        return pd.DataFrame()
    d = normalize_daily(df).set_index("trade_date")
    w = pd.DataFrame({
        "open": d["open"].resample("W-FRI").first(),
        "high": d["high"].resample("W-FRI").max(),
        "low": d["low"].resample("W-FRI").min(),
        "close": d["close"].resample("W-FRI").last(),
        "vol": d["vol"].resample("W-FRI").sum(),
        "amount": d["amount"].resample("W-FRI").sum() if "amount" in d.columns else np.nan,
    }).dropna(subset=["close"]).reset_index()
    w["trade_date"] = w["trade_date"].dt.normalize()
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
        if vol > v5 and vol > v10: confirm += 20
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

def fetch_stock_daily(pro, code, years=3):
    end = datetime.now().strftime("%Y%m%d")
    start = (pd.Timestamp.today() - pd.Timedelta(days=365*years+120)).strftime("%Y%m%d")
    df = pro.daily(ts_code=code, start_date=start, end_date=end)
    return normalize_daily(df)

def fetch_index_members(pro, index_code, limit_n):
    today = datetime.now().strftime("%Y%m%d")
    start = (pd.Timestamp.today() - pd.Timedelta(days=120)).strftime("%Y%m%d")
    w = pro.index_weight(index_code=index_code, start_date=start, end_date=today)
    if w is None or w.empty:
        return []
    latest = w["trade_date"].max()
    x = w[w["trade_date"]==latest].sort_values("weight", ascending=False)
    return x["con_code"].drop_duplicates().head(limit_n).tolist()

def stock_name_map(pro):
    try:
        b = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        return dict(zip(b["ts_code"], b["name"]))
    except Exception:
        return {}

def screen_codes(pro, codes, name_map):
    rows = []
    for i, code in enumerate(codes):
        try:
            d = fetch_stock_daily(pro, code, years=2)
            if len(d) < 150:
                continue
            di = add_indicators(d)
            wi = weekly_from_daily(d)
            if di.empty or wi.empty:
                continue
            lr = di.iloc[-1].to_dict()
            lr["macd_prev"] = di.iloc[-2]["macd"] if len(di)>1 else np.nan
            wr = wi.iloc[-1].to_dict()
            score, trend, momentum, weekly, confirm = numeric_score(lr, wr)
            if score >= 62 and (weekly is None or weekly >= 50):
                rows.append({
                    "代码":code, "名称":name_map.get(code,code),
                    "技术分/100":score, "趋势/100":trend, "动能/100":momentum,
                    "周线/100":weekly, "量能/100":confirm,
                    "收盘":round(float(lr["close"]),2),
                    "中轨":round(float(lr["boll_mid"]),2) if pd.notna(lr["boll_mid"]) else np.nan
                })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["技术分/100","周线/100"], ascending=False).reset_index(drop=True)

def run_backtest(df, entry_score=78, exit_score=48, fee_bps=8):
    d = add_indicators(df)
    w = weekly_from_daily(df)
    if len(d) < 100 or len(w) < 20:
        return pd.DataFrame(), {}
    w2 = w[["trade_date","boll_mid","boll_slope","close","dif","dea"]].copy()
    w2.columns = ["w_date","w_boll_mid","w_boll_slope","w_close","w_dif","w_dea"]
    m = pd.merge_asof(
        d.sort_values("trade_date"),
        w2.sort_values("w_date"),
        left_on="trade_date", right_on="w_date", direction="backward"
    )
    scores = []
    for i,row in m.iterrows():
        r = row.to_dict()
        r["macd_prev"] = m.iloc[i-1]["macd"] if i>0 else np.nan
        wr = None
        if pd.notna(row.get("w_date")):
            wr = {
                "boll_slope":row.get("w_boll_slope"), "close":row.get("w_close"),
                "boll_mid":row.get("w_boll_mid"), "dif":row.get("w_dif"), "dea":row.get("w_dea")
            }
        scores.append(numeric_score(r,wr)[0])
    m["score"] = scores
    m["signal"] = 0
    in_pos = False
    for i in range(len(m)):
        s = m.iloc[i]["score"]
        if not in_pos and s >= entry_score:
            m.iloc[i, m.columns.get_loc("signal")] = 1
            in_pos = True
        elif in_pos and s <= exit_score:
            m.iloc[i, m.columns.get_loc("signal")] = -1
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
    n_years = max((m["trade_date"].iloc[-1]-m["trade_date"].iloc[0]).days/365.25, 0.01)
    annual = eq.iloc[-1]**(1/n_years)-1
    dd = (eq/eq.cummax()-1).min()
    trades = int((m["signal"]==1).sum())
    bh = m["买入持有"].iloc[-1]-1
    metrics = {
        "累计收益": total, "年化收益": annual, "最大回撤": dd,
        "交易次数": trades, "买入持有": bh
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
st.caption("DeepSeek 国内版 · 先读图 → 再规则评分 → 最后给行动条件。AI负责识别，规则负责决策。")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📷 分析", "🔎 选股", "🧪 回测", "📚 历史", "🧠 方法", "⚙️ 设置"])

with tab6:
    st.subheader("接口设置")
    env_key = os.getenv("DEEPSEEK_API_KEY", "")
    if env_key:
        st.success("服务器已配置 DeepSeek 接口密钥，无需重复输入。")
    else:
        st.info("服务器尚未配置 Key。可在这里临时输入；仅保存在当前会话。")
    temp = st.text_input("DeepSeek 接口密钥", type="password", key="temp_key")
    if temp:
        st.session_state["api_key"] = temp
        st.success("本次会话已启用临时 Key。")

    st.markdown("**行情数据接口（选股/回测）**")
    tushare_env = os.getenv("TUSHARE_TOKEN","")
    if tushare_env:
        st.success("服务器已配置 Tushare Token。")
    else:
        ttemp = st.text_input("Tushare Token", type="password", key="tushare_temp")
        if ttemp:
            st.session_state["tushare_token"] = ttemp
            st.success("本次会话已启用 Tushare Token。")
    st.markdown("iPhone：Safari打开网址 → 分享 → **添加到主屏幕**。")
    st.info("中长线工具的核心不是预测下一根K线，而是：只在趋势、动能、周期一致时提高风险暴露，在结构破坏时降低风险。")

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

**关键原则**
- 零轴下金叉 = 先看修复，不把反弹当反转。
- BOLL中轨向下时，买入类信号天然降级。
- 日线强、周线弱 = 先观察，不把局部反弹当中长线主升。
- 盘中截图自动降置信度。
- 图片不清晰时不给强结论。
- 技术面只负责“什么时候风险收益更好”，不替代基本面和估值判断。
""")
    st.warning("评分是“技术证据质量分”，不是上涨概率，也不是收益率预测。真正的收益来自正期望：胜率 × 盈亏比 × 仓位纪律 × 足够样本。")

with tab1:
    st.subheader("决策驾驶舱")
    render_cockpit(st.session_state.get("last_report"))
    st.divider()

    st.subheader("① 上传图表")
    st.caption("模板：BOLL(20,2) + MACD(12,26,9) + VOL/MA5/MA10。")
    nonce = st.session_state.get("upload_nonce", 0)
    c1, c2 = st.columns(2)
    with c1:
        daily_upload = st.file_uploader(
            "日线（必填）",
            type=["png","jpg","jpeg","webp"],
            key=f"daily_{nonce}"
        )
        if daily_upload is not None:
            st.session_state["daily_bytes"] = daily_upload.getvalue()
            st.session_state["daily_mime"] = getattr(daily_upload, "type", None) or "image/png"
            st.session_state["daily_name"] = getattr(daily_upload, "name", "日线截图")
        if st.session_state.get("daily_bytes"):
            st.success("✅ 日线已载入")
            with st.expander("查看日线截图"):
                st.image(st.session_state["daily_bytes"], use_container_width=True)
    with c2:
        weekly_upload = st.file_uploader(
            "周线（推荐）",
            type=["png","jpg","jpeg","webp"],
            key=f"weekly_{nonce}"
        )
        if weekly_upload is not None:
            st.session_state["weekly_bytes"] = weekly_upload.getvalue()
            st.session_state["weekly_mime"] = getattr(weekly_upload, "type", None) or "image/png"
            st.session_state["weekly_name"] = getattr(weekly_upload, "name", "周线截图")
        if st.session_state.get("weekly_bytes"):
            st.success("✅ 周线已载入")
            with st.expander("查看周线截图"):
                st.image(st.session_state["weekly_bytes"], use_container_width=True)

    if st.button("🗑️ 清空已上传图片", use_container_width=True):
        reset_uploads()
        st.rerun()

    daily_ready = bool(st.session_state.get("daily_bytes"))
    weekly_ready = bool(st.session_state.get("weekly_bytes"))

    st.subheader("② 决策上下文")
    symbol = st.text_input("股票/ETF名称或代码（可留空自动识别）", placeholder="留空时从截图顶部自动识别")
    c3, c4 = st.columns(2)
    with c3:
        market = st.selectbox("市场", ["自动判断","A股","港股","美股","ETF/其他"])
        horizon = st.selectbox("持有周期", ["2–8周", "2–6个月", "6–18个月"], index=1)
    with c4:
        position_state = st.selectbox("当前仓位", ["未持有","轻仓≤25%","中等25–50%","重仓>50%"])
        cost = st.text_input("持仓成本（可选）", placeholder="例如：435")

    fundamentals_ok = st.checkbox("基本面与估值已独立验证通过（中长线强烈建议）", value=False)
    notes = st.text_area("补充说明（可选）", placeholder="例如：盘中截图；准备持有3个月；只考虑回调加仓……", height=80)

    st.subheader("③ 分析模式")
    mode = "稳定模式"
    st.info("稳定模式：始终按原图读取，并复用同一截图的已识别结果，避免重复分析时评分漂移。")

    if st.button("🚀 生成中长线决策", type="primary", use_container_width=True):
        key = os.getenv("DEEPSEEK_API_KEY","") or st.session_state.get("api_key","")
        if not daily_ready:
            st.error("请先上传日线截图。")
            st.stop()
        if not key:
            st.error("请先在“设置”配置 DeepSeek 接口密钥。")
            st.stop()

        prev = previous(symbol.strip())
        prompt_lines = [
            "请读取上传图表。第一张一定是日线；如果有第二张，则第二张是周线。",
            f"标的：{symbol.strip() or '未填写'}",
            f"市场：{market}",
            f"持有周期：{horizon}",
            f"当前仓位：{position_state}",
            f"持仓成本：{cost or '未填写'}",
            f"补充说明：{notes or '无'}",
            f"周线截图：{'有' if weekly_ready else '无'}",
        ]
        detail = "original"
        max_tokens = 4200

        content = [{"type":"text","text":"\n".join(prompt_lines)}]
        content.append({
            "type":"image_url",
            "image_url":{
                "url":data_url_bytes(
                    st.session_state["daily_bytes"],
                    st.session_state.get("daily_mime","image/png")
                ),
                "detail":detail
            }
        })
        if weekly_ready:
            content.append({
                "type":"image_url",
                "image_url":{
                    "url":data_url_bytes(
                        st.session_state["weekly_bytes"],
                        st.session_state.get("weekly_mime","image/png")
                    ),
                    "detail":detail
                }
            })

        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")

        def call_ds(budget, retry=False):
            extra = ""
            if retry:
                extra = "\n上次输出不完整。请只返回一个完整、简洁、合法的JSON对象，宁可少写也不要截断。"
            messages = [
                {"role":"system","content":EXTRACT_PROMPT},
                {"role":"user","content":[{"type":"text","text":"\n".join(prompt_lines)+extra}] + content[1:]}
            ]
            return client.chat.completions.create(
                model="deepseek-flash",
                response_format={"type":"json_object"},
                temperature=0,
                max_tokens=budget,
                messages=messages
            )

        sig = image_signature(
            st.session_state.get("daily_bytes", b""),
            st.session_state.get("weekly_bytes", b"") if weekly_ready else None
        )
        x, raw = get_cached_extraction(sig)
        cache_hit = x is not None

        if not cache_hit:
            with st.spinner("正在读取日线/周线并构建技术证据..."):
                try:
                    resp = call_ds(max_tokens)
                    raw = resp.choices[0].message.content or ""
                    x = parse_json(raw)
                    if not x or getattr(resp.choices[0], "finish_reason", None) == "length":
                        resp = call_ds(7000, True)
                        raw = resp.choices[0].message.content or ""
                        x = parse_json(raw)
                except Exception as e:
                    st.error(f"分析失败：{e}")
                    st.stop()

            if not x:
                st.error("DeepSeek 连续返回了不完整结构，请重新分析一次。")
                st.stop()
            save_cached_extraction(sig, x, raw)
        else:
            st.toast("已识别为同一组截图，直接复用稳定结果。")

        recognized_name = cat(x.get("symbol_name"))
        recognized_code = cat(x.get("symbol_code"))
        auto_symbol = ""
        if recognized_name not in ("","未知"):
            auto_symbol = recognized_name
        if recognized_code not in ("","未知"):
            auto_symbol = (auto_symbol + " / " + recognized_code).strip(" /")
        if not symbol.strip() and auto_symbol:
            symbol = auto_symbol

        metrics = score_engine(x, weekly_ready)
        score, trend, momentum, weekly_score, confirm, hard_bear, strong_bull = metrics
        weekly_ok = weekly_score is not None and weekly_score >= 60
        confidence = confidence_from(x, weekly_ready)
        rating = grade(score, weekly_ok, confidence)
        stage = stage_from(score, x.get("daily",{}), weekly_ok)
        state, state_reason = state_from(
            score, rating, confidence, bool(x.get("is_intraday")),
            weekly_ok, position_state, fundamentals_ok, hard_bear
        )

        meta = {
            "symbol":symbol.strip(), "market":market, "horizon":horizon,
            "position_state":position_state, "rating":rating, "state":state,
            "stage":stage, "confidence":confidence, "mode":mode,
            "weekly_used":weekly_ready
        }
        save_result(meta, x, metrics, raw)

        d = x.get("daily",{}) or {}
        daily_mid = d.get("boll_mid","未知")
        upgrade_parts = []
        downgrade_parts = []
        if d.get("boll_mid_direction") != "向上":
            upgrade_parts.append("中轨转向上")
        if d.get("price_vs_mid") != "中轨上":
            upgrade_parts.append(f"站稳中轨 {daily_mid}")
        if d.get("macd_zero_zone") != "零轴上":
            upgrade_parts.append("MACD回到零轴上")
        if weekly_score is None:
            upgrade_parts.append("补周线确认")
        elif weekly_score < 60:
            upgrade_parts.append("周线转强")

        if d.get("price_vs_mid") != "中轨下":
            downgrade_parts.append(f"失守中轨 {daily_mid}")
        if d.get("bar_momentum") != "绿柱放大":
            downgrade_parts.append("MACD绿柱放大")
        downgrade_parts.append("关键支撑失守")

        up_text = "；".join(upgrade_parts[:2]) if upgrade_parts else "维持强势并继续确认"
        down_text = "；".join(downgrade_parts[:2])

        delta = None
        if prev and prev.get("score") is not None:
            try:
                delta = score - float(prev.get("score"))
            except Exception:
                delta = None

        st.session_state["last_report"] = {
            "updated_at": datetime.now().strftime("%m-%d %H:%M"),
            "symbol": symbol.strip() or "当前标的",
            "state": state,
            "rating": rating,
            "stage": stage,
            "state_reason": state_reason,
            "score": score,
            "trend": trend,
            "momentum": momentum,
            "weekly_score": weekly_score,
            "confirm": confirm,
            "confidence": confidence,
            "essence": x.get("essence",""),
            "support": x.get("key_support","未知"),
            "resistance": x.get("key_resistance","未知"),
            "upgrade": up_text,
            "downgrade": down_text,
            "delta": delta,
            "intraday": bool(x.get("is_intraday")),
            "daily": d,
            "boll_analysis": x.get("boll_analysis",""),
            "macd_analysis": x.get("macd_analysis",""),
            "weekly_analysis": x.get("weekly_analysis","") if weekly_ready else "",
            "resonance": x.get("resonance",""),
        }
        st.rerun()

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
    st.caption("当前版本先支持A股。使用与个股分析一致的 BOLL + MACD + 周线 + 量能规则进行规则化筛选。")
    pro = tushare_pro()
    if pro is None:
        st.info("请先在“设置”里配置 Tushare Token。")
    else:
        universe = st.selectbox("选股范围", ["沪深300","中证500","中证1000"], index=0)
        count = st.select_slider("扫描数量", options=[20,50,100,200], value=50)
        index_code = {"沪深300":"000300.SH","中证500":"000905.SH","中证1000":"000852.SH"}[universe]
        if st.button("🔎 开始选股", type="primary", use_container_width=True):
            with st.spinner(f"正在扫描{universe}前{count}只成分股..."):
                try:
                    codes = fetch_index_members(pro,index_code,count)
                    names = stock_name_map(pro)
                    result = screen_codes(pro,codes,names)
                    st.session_state["screen_result"] = result
                except Exception as e:
                    st.error(f"选股失败：{e}")
        result = st.session_state.get("screen_result")
        if isinstance(result,pd.DataFrame):
            if result.empty:
                st.warning("本次没有筛到满足条件的标的。")
            else:
                st.success(f"筛出 {len(result)} 只候选")
                st.dataframe(result.head(30), use_container_width=True, hide_index=True)
                st.caption("总分是技术证据质量分，不是上涨概率。建议再进入“分析”页做截图/基本面复核。")

with tab3:
    st.subheader("策略回测")
    st.caption("按历史日线自动计算 BOLL/MACD/周线过滤，信号在收盘后形成，并从下一交易日开始计入持仓，避免未来函数。")
    pro = tushare_pro()
    if pro is None:
        st.info("请先在“设置”里配置 Tushare Token。")
    else:
        bt_code = st.text_input("A股代码", placeholder="例如 600519.SH", key="bt_code")
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
                        df_bt = fetch_stock_daily(pro, bt_code.strip().upper(), years=years)
                        curve, m = run_backtest(df_bt, entry_score, exit_score, fee_bps)
                        st.session_state["bt_curve"] = curve
                        st.session_state["bt_metrics"] = m
                    except Exception as e:
                        st.error(f"回测失败：{e}")
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
                show = curve.set_index("trade_date")[["净值","买入持有"]]
                st.line_chart(show, height=280)
                with st.expander("查看最近信号"):
                    st.dataframe(curve[["trade_date","close","score","signal","position"]].tail(60), use_container_width=True, hide_index=True)
            st.warning("回测只说明历史规则表现，不代表未来收益；结果仍需考虑滑点、停牌、涨跌停、分红复权和样本外验证。")

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
st.caption("中长线技术决策辅助工具。先控制错误，再放大正确；截图识别和技术指标均可能失真，请以原始行情数据复核。")
