import base64
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
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
.block-container{
 max-width:1080px;
 padding-top:calc(env(safe-area-inset-top, 0px) + 3.4rem);
 padding-bottom:4rem;
 padding-left:.7rem;
 padding-right:.7rem
}
h1{font-size:1.58rem!important;margin-bottom:.2rem!important}
h2{font-size:1.25rem!important}
div[data-testid="stMetric"]{border:1px solid rgba(128,128,128,.22);border-radius:12px;padding:9px 10px}
.decision{border:1px solid rgba(128,128,128,.28);border-radius:14px;padding:14px;margin:8px 0 12px}
.hero{border:1px solid rgba(128,128,128,.28);border-radius:16px;padding:15px;margin:8px 0 14px}
.muted{opacity:.72;font-size:.88rem}
@media(max-width:700px){
 .block-container{
   padding-left:.5rem;
   padding-right:.5rem;
   padding-top:calc(env(safe-area-inset-top, 0px) + 3.7rem)
 }
 h1{font-size:1.38rem!important}
 .stTextInput input,.stTextArea textarea{font-size:16px!important}
 button[kind="primary"]{min-height:50px;font-size:1.03rem}
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
- 不要根据股票名称补充截图外行情。

必须只输出合法 json，不要Markdown，不要额外文字。JSON格式：
{
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
    "volume_state": "放量/缩量/普通/不可见/未知",
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
    "bar_momentum": "未知"
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
- data_quality 是0-100整数，衡量截图是否足够清晰、周期/指标是否可判断。
- 所有解释字段简洁，单项尽量不超过100个汉字。
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
    conn.commit()
    conn.close()

def data_url(file):
    mime = getattr(file, "type", None) or "image/png"
    return f"data:{mime};base64,{base64.b64encode(file.getvalue()).decode('utf-8')}"

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

    # 4) 确认因子 0-100
    confirm = 45
    vol = cat(d.get("volume_state"))
    if vol == "放量": confirm += 25
    elif vol == "缩量": confirm -= 10
    elif vol == "普通": confirm += 5

    div = cat(d.get("divergence"))
    if div == "底背离": confirm += 18
    elif div == "顶背离": confirm -= 25
    elif div == "无明显背离": confirm += 5
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
        return "WATCH", "截图质量不足，先复核数据"
    if hard_bear or score < 35:
        return ("REDUCE" if holding else "AVOID"), "趋势与动能处于明显弱势"
    if holding and score < 48:
        return "REDUCE", "中长线结构转弱，优先控制风险"
    if score >= 78 and weekly_ok and not intraday:
        if fundamentals_ok:
            return "BUY CANDIDATE", "技术面进入高质量候选区"
        return "WATCH", "技术面较强，但中长线仍需基本面/估值独立验证"
    if holding and score >= 58:
        return "HOLD", "趋势尚未破坏，等待升级或降级条件"
    return "WATCH", "证据尚不足，等待关键确认"

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

def history(limit=300):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM analyses ORDER BY id DESC LIMIT ?", conn, params=(limit,))
    conn.close()
    return df

init_db()

st.markdown("<div style='height:.15rem'></div>", unsafe_allow_html=True)
st.title("📈 日线 × 周线 中长线决策引擎")
st.caption("DeepSeek 国内版 · 先读图 → 再规则评分 → 最后给行动条件。AI负责识别，规则负责决策。")

tab1, tab2, tab3, tab4 = st.tabs(["📷 分析", "📚 历史", "🧠 方法", "⚙️ 设置"])

with tab4:
    st.subheader("API 设置")
    env_key = os.getenv("DEEPSEEK_API_KEY", "")
    if env_key:
        st.success("服务器已配置 DeepSeek API Key，无需重复输入。")
    else:
        st.info("服务器尚未配置 Key。可在这里临时输入；仅保存在当前会话。")
    temp = st.text_input("DeepSeek API Key", type="password", key="temp_key")
    if temp:
        st.session_state["api_key"] = temp
        st.success("本次会话已启用临时 Key。")
    st.markdown("iPhone：Safari打开网址 → 分享 → **添加到主屏幕**。")
    st.info("中长线工具的核心不是预测下一根K线，而是：只在趋势、动能、周期一致时提高风险暴露，在结构破坏时降低风险。")

with tab3:
    st.subheader("这套系统怎么做决策")
    st.markdown("""
**核心框架：四层证据，而不是指标堆砌。**

1. **趋势层（40%左右）**：BOLL中轨方向、价格相对中轨、带宽状态。  
2. **动能层（30%左右）**：MACD零轴、DIF方向、金叉/死叉、柱体加减速。  
3. **周期层（约20%）**：周线确认日线。中长线若没有周线确认，强信号会被降级。  
4. **确认层（约10%）**：成交量与背离，只做加减分，不抢主导权。  

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
    st.subheader("① 上传图表")
    c1, c2 = st.columns(2)
    with c1:
        daily_img = st.file_uploader("日线截图（必填）", type=["png","jpg","jpeg","webp"], key="daily")
        if daily_img:
            st.image(daily_img, use_container_width=True)
    with c2:
        weekly_img = st.file_uploader("周线截图（推荐，中长线过滤器）", type=["png","jpg","jpeg","webp"], key="weekly")
        if weekly_img:
            st.image(weekly_img, use_container_width=True)

    st.subheader("② 决策上下文")
    symbol = st.text_input("股票/ETF名称或代码", placeholder="例如：腾讯控股 / 0700.HK")
    c3, c4 = st.columns(2)
    with c3:
        market = st.selectbox("市场", ["自动判断","A股","港股","美股","ETF/其他"])
        horizon = st.selectbox("持有周期", ["2–8周", "2–6个月", "6–18个月"], index=1)
    with c4:
        position_state = st.selectbox("当前仓位", ["未持有","轻仓≤25%","中等25–50%","重仓>50%"])
        cost = st.text_input("持仓成本（可选）", placeholder="例如：435")

    fundamentals_ok = st.checkbox("基本面与估值已独立验证通过（中长线强烈建议）", value=False)
    notes = st.text_area("补充说明（可选）", placeholder="例如：盘中截图；准备持有3个月；只考虑回调加仓……", height=80)

    st.subheader("③ 分析精度")
    mode = st.radio("模式", ["省钱模式","标准模式","精细模式"], index=1, horizontal=True)
    st.caption("标准模式适合绝大多数情况；省钱模式用于批量初筛；精细模式用于重要标的或图形复杂时。")

    if st.button("🚀 生成中长线决策", type="primary", use_container_width=True):
        key = os.getenv("DEEPSEEK_API_KEY","") or st.session_state.get("api_key","")
        if not daily_img:
            st.error("请先上传日线截图。")
            st.stop()
        if not key:
            st.error("请先在“设置”配置 DeepSeek API Key。")
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
            f"周线截图：{'有' if weekly_img else '无'}",
        ]
        if prev:
            prompt_lines += [
                "存在同标的历史记录，仅用于给comparison_hint提供方向性参考：",
                f"上次评分：{prev.get('score','')}",
                f"上次评级：{prev.get('rating','')}",
                f"上次阶段：{prev.get('stage','')}",
            ]

        detail = "low" if mode == "省钱模式" else "original"
        max_tokens = 2500 if mode == "省钱模式" else (4200 if mode == "标准模式" else 6000)

        content = [{"type":"text","text":"\n".join(prompt_lines)}]
        content.append({"type":"image_url","image_url":{"url":data_url(daily_img),"detail":detail}})
        if weekly_img:
            content.append({"type":"image_url","image_url":{"url":data_url(weekly_img),"detail":detail}})

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
                max_tokens=budget,
                messages=messages
            )

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

        metrics = score_engine(x, weekly_img is not None)
        score, trend, momentum, weekly_score, confirm, hard_bear, strong_bull = metrics
        weekly_ok = weekly_score is not None and weekly_score >= 60
        confidence = confidence_from(x, weekly_img is not None)
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
            "weekly_used":weekly_img is not None
        }
        save_result(meta, x, metrics, raw)

        st.subheader("④ 决策总览")
        st.markdown(
            f"<div class='hero'><b>{signal_color(score)} {state}</b><br>"
            f"<span style='font-size:1.25rem;font-weight:700'>技术质量分 {score:.1f}/100 · {rating}</span><br>"
            f"{stage}<br><span class='muted'>{state_reason}</span></div>",
            unsafe_allow_html=True
        )

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("趋势", f"{trend:.0f}")
        m2.metric("动能", f"{momentum:.0f}")
        m3.metric("周线", "未提供" if weekly_score is None else f"{weekly_score:.0f}")
        m4.metric("置信度", f"{confidence}%")

        if bool(x.get("is_intraday")):
            st.warning("这是盘中截图：日K与指标尚未定型，系统已自动降低置信度。")
        if confidence < 65:
            st.error(f"截图质量不足（{confidence}%）。缺失/模糊：{x.get('missing_or_unclear','未说明')}。不建议依据本次结果采取中长线动作。")

        st.markdown("### 核心判断")
        st.write(x.get("essence",""))
        st.markdown(f"**BOLL：** {x.get('boll_analysis','')}")
        st.markdown(f"**MACD：** {x.get('macd_analysis','')}")
        if weekly_img:
            st.markdown(f"**周线：** {x.get('weekly_analysis','')}")
        st.markdown(f"**共振/冲突：** {x.get('resonance','')}")

        st.markdown("### 技术证据表")
        d = x.get("daily",{}) or {}
        rows = [
            ["BOLL中轨", d.get("boll_mid_direction","未知"), "主趋势方向"],
            ["价格位置", d.get("price_vs_mid","未知"), f"现价 {d.get('price','未知')} / 中轨 {d.get('boll_mid','未知')}"],
            ["BOLL带宽", d.get("boll_band_state","未知"), "趋势扩张/收敛"],
            ["MACD零轴", d.get("macd_zero_zone","未知"), "环境强弱"],
            ["DIF方向", d.get("dif_direction","未知"), "趋势动能方向"],
            ["交叉", d.get("cross","未知"), "确认信号"],
            ["柱体", d.get("bar_momentum","未知"), "动能加减速"],
            ["成交量", d.get("volume_state","未知"), "参与度确认"],
            ["背离", d.get("divergence","未知"), "仅作风险提示"],
        ]
        st.dataframe(pd.DataFrame(rows, columns=["证据","当前状态","作用"]), use_container_width=True, hide_index=True)

        st.markdown("### 关键价位")
        k1,k2 = st.columns(2)
        k1.info(f"支撑：{x.get('key_support','未知')}")
        k2.warning(f"压力：{x.get('key_resistance','未知')}")

        st.markdown("### 升级 / 降级条件")
        daily_mid = d.get("boll_mid","未知")
        upgrade_parts = []
        downgrade_parts = []
        if d.get("boll_mid_direction") != "向上":
            upgrade_parts.append("BOLL中轨由走平/向下转为向上")
        if d.get("price_vs_mid") != "中轨上":
            upgrade_parts.append(f"价格有效站上中轨 {daily_mid}")
        if d.get("macd_zero_zone") != "零轴上":
            upgrade_parts.append("DIF/DEA向零轴上方迁移")
        if weekly_score is None:
            upgrade_parts.append("补充周线并获得同向确认")
        elif weekly_score < 60:
            upgrade_parts.append("周线由弱转强并确认日线")

        if d.get("price_vs_mid") != "中轨下":
            downgrade_parts.append(f"有效跌破/持续运行在中轨 {daily_mid} 下方")
        if d.get("bar_momentum") != "绿柱放大":
            downgrade_parts.append("MACD绿柱明显放大")
        downgrade_parts.append("周线同步转弱或关键支撑失守")

        st.success("升级：" + "；".join(upgrade_parts[:4]) if upgrade_parts else "升级：当前已处于较强共振区，重点观察趋势延续。")
        st.warning("降级：" + "；".join(downgrade_parts[:3]))

        if prev and prev.get("score") is not None:
            try:
                delta = score - float(prev.get("score"))
                arrow = "↑" if delta > 3 else ("↓" if delta < -3 else "→")
                st.markdown(f"### 与上次相比：{arrow} {delta:+.1f} 分")
                st.caption(f"上次 {prev.get('score')} / {prev.get('rating')} / {prev.get('stage')} → 本次 {score} / {rating} / {stage}")
            except Exception:
                pass

        with st.expander("🧮 风险预算 / 仓位计算器"):
            st.caption("这是风险控制计算，不是收益承诺。输入计划入场价与失效价，系统按最大可承受亏损反推仓位。")
            rc1, rc2 = st.columns(2)
            with rc1:
                capital = st.number_input("用于该账户的资金", min_value=0.0, value=100000.0, step=10000.0)
                risk_pct = st.number_input("单次最大风险 %", min_value=0.1, max_value=5.0, value=0.8, step=0.1)
            with rc2:
                entry = st.number_input("计划入场价", min_value=0.0, value=0.0, step=0.1)
                stop = st.number_input("技术失效价/止损参考", min_value=0.0, value=0.0, step=0.1)
            if entry > 0 and stop > 0 and entry > stop:
                risk_cash = capital * risk_pct / 100
                shares = int(risk_cash / (entry-stop))
                position_value = shares * entry
                pct = (position_value/capital*100) if capital else 0
                st.info(f"风险预算约 {risk_cash:,.0f}；理论最大股数约 {shares:,}；对应仓位约 {position_value:,.0f}（{pct:.1f}%）。")
            else:
                st.caption("入场价需要高于失效价，才能计算多头仓位。")

        st.markdown("### 执行纪律")
        if state == "BUY CANDIDATE":
            st.write("技术面达到中长线候选标准，但更适合分批进入而不是一次性满仓；后续只在升级条件兑现时提高暴露。")
        elif state == "HOLD":
            st.write("继续持有的前提是中轨/周线结构不被破坏；不要因为单日波动频繁交易。")
        elif state == "REDUCE":
            st.write("当前重点是降低组合回撤，而不是猜底；等待趋势重新修复后再提高仓位。")
        elif state == "AVOID":
            st.write("当前技术证据不足以支持中长线新增风险暴露，优先等待结构重建。")
        else:
            st.write("保持观察。等趋势、动能与周线形成更高质量共振，再考虑提高风险暴露。")

        st.caption("评分不是上涨概率。技术图表不能替代基本面、估值、行业和组合风险管理。")

with tab2:
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
            "⬇️ 导出历史 CSV",
            view.to_csv(index=False).encode("utf-8-sig"),
            "mid_long_history.csv",
            "text/csv",
            use_container_width=True
        )

st.divider()
st.caption("中长线技术决策辅助工具。先控制错误，再放大正确；截图识别和技术指标均可能失真，请以原始行情数据复核。")
