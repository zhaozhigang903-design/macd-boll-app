import base64
import json
import os
import hmac
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from openai import OpenAI

from engine import (
    ACTION_CN, backtest, confidence_score, decision, evidence_rows,
    normalize_tf, rating, risk_position_reference, score_breakdown,
    stage, technical_score, transition_conditions, validate_extraction
)

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "analysis_history.db"

st.set_page_config(
    page_title="中长线决策引擎",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if APP_PASSWORD:
    if not st.session_state.get("authenticated", False):
        st.title("🔐 中长线决策引擎")
        pwd = st.text_input("访问密码", type="password", placeholder="请输入访问密码")
        if st.button("进入", type="primary", width="stretch"):
            if hmac.compare_digest(pwd, APP_PASSWORD):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("密码错误")
        st.stop()

st.markdown("""
<style>
.block-container{
  max-width:1080px;
  padding-top:calc(env(safe-area-inset-top, 0px) + 3.2rem);
  padding-bottom:5rem;
  padding-left:.7rem;
  padding-right:.7rem
}
h1{font-size:1.55rem!important;margin-bottom:.15rem!important}
h2{font-size:1.28rem!important}
h3{font-size:1.08rem!important}
div[data-testid="stMetric"]{
  border:1px solid rgba(128,128,128,.22);
  border-radius:12px;
  padding:9px 10px
}
.decision-card{
  border:1px solid rgba(128,128,128,.25);
  border-radius:14px;
  padding:14px;
  margin:8px 0 12px
}
.small{opacity:.72;font-size:.88rem}
@media(max-width:700px){
  .block-container{
    padding-left:.5rem;
    padding-right:.5rem;
    padding-top:calc(env(safe-area-inset-top, 0px) + 3.6rem)
  }
  h1{font-size:1.32rem!important}
  .stTextInput input,.stTextArea textarea{font-size:16px!important}
  button[kind="primary"]{min-height:48px;font-size:1.02rem}
}
</style>
""", unsafe_allow_html=True)

EXTRACT_PROMPT = """
你是严谨的证券图表视觉解析器。用户可能上传日线截图和可选周线截图。
你的唯一任务是“从图片提取可验证事实”，最终评分和仓位决策由程序规则引擎完成。
禁止根据股票名称、记忆、新闻或截图之外的信息补充行情；看不清就写 unknown/空字符串。

只输出一个合法JSON对象，不要Markdown，不要额外文字：
{
  "daily":{
    "visible":true,
    "image_quality":0,
    "price":"",
    "boll_mid":"",
    "boll_upper":"",
    "boll_lower":"",
    "mid_direction":"up|flat|down|unknown",
    "price_vs_mid":"above|near|below|unknown",
    "price_vs_band":"above_upper|upper_zone|middle_zone|lower_zone|below_lower|unknown",
    "dif":"",
    "dea":"",
    "macd_bar":"",
    "dif_direction":"up|flat|down|unknown",
    "zero_zone":"above|near|below|unknown",
    "cross":"golden|death|adhesion|unknown",
    "bar_momentum":"red_expanding|red_shrinking|green_shrinking|green_expanding|unclear|unknown",
    "volume_state":"breakout_up_volume|decline_volume|contract_pullback|contract_rebound|normal|unavailable|unknown",
    "divergence":"top|bottom|none|uncertain|unknown",
    "support_1":"",
    "resistance_1":"",
    "invalidation_price":"",
    "notes":""
  },
  "weekly":{
    "visible":false,
    "image_quality":0,
    "price":"",
    "boll_mid":"",
    "boll_upper":"",
    "boll_lower":"",
    "mid_direction":"up|flat|down|unknown",
    "price_vs_mid":"above|near|below|unknown",
    "price_vs_band":"above_upper|upper_zone|middle_zone|lower_zone|below_lower|unknown",
    "dif":"",
    "dea":"",
    "macd_bar":"",
    "dif_direction":"up|flat|down|unknown",
    "zero_zone":"above|near|below|unknown",
    "cross":"golden|death|adhesion|unknown",
    "bar_momentum":"red_expanding|red_shrinking|green_shrinking|green_expanding|unclear|unknown",
    "volume_state":"breakout_up_volume|decline_volume|contract_pullback|contract_rebound|normal|unavailable|unknown",
    "divergence":"top|bottom|none|uncertain|unknown",
    "support_1":"",
    "resistance_1":"",
    "invalidation_price":"",
    "notes":""
  },
  "global":{
    "is_intraday_unclosed":false,
    "uncertainties":[],
    "data_quality_comment":""
  }
}

判读纪律：
1. BOLL中轨方向看斜率，不因一根K线改变方向。
2. MACD先看零轴，再看DIF方向，再看柱体，最后才看金叉死叉。
3. 零轴下金叉默认是反弹/修复；零轴附近粘合必须降级。
4. 红柱缩短只是多头动能减弱，绿柱缩短只是空头动能减弱，不等于反转确认。
5. 背离只有同级波峰/波谷清晰可比时才标top/bottom，否则uncertain。
6. 成交量看不清写unavailable。
7. invalidation_price只有截图存在明确结构失效位时填写；不要虚构止损位。
8. image_quality=0-100，综合清晰度、指标完整度、数值可读性。
9. 如果没有周线图，weekly.visible=false。
10. notes不超过100字，JSON必须完整闭合。
"""

DISPLAY = {
    "up":"向上","flat":"走平","down":"向下","unknown":"未知",
    "above":"上方","near":"附近","below":"下方",
    "above_upper":"上轨外","upper_zone":"上轨附近","middle_zone":"中部",
    "lower_zone":"下轨附近","below_lower":"下轨外",
    "golden":"金叉","death":"死叉","adhesion":"粘合",
    "red_expanding":"红柱放大","red_shrinking":"红柱缩短",
    "green_shrinking":"绿柱缩短","green_expanding":"绿柱放大",
    "unclear":"不明确",
    "breakout_up_volume":"放量上攻","decline_volume":"放量下跌",
    "contract_pullback":"缩量回调","contract_rebound":"缩量反弹",
    "normal":"普通","unavailable":"不可见",
    "top":"顶背离","bottom":"底背离","none":"无明确背离","uncertain":"不确定",
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS analyses_v3(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      symbol TEXT,
      market TEXT,
      score REAL,
      rating TEXT,
      action TEXT,
      stage TEXT,
      daily_score REAL,
      weekly_score REAL,
      confidence INTEGER,
      decision TEXT,
      analysis_json TEXT
    )
    """)
    conn.commit()
    conn.close()

def to_data_url(file):
    mime = getattr(file, "type", None) or "image/png"
    return f"data:{mime};base64,{base64.b64encode(file.getvalue()).decode('utf-8')}"

def parse_json(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\x60\x60\x60(?:json)?\s*(\{.*\})\s*\x60\x60\x60", text, re.S | re.I)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e+1])
        except Exception:
            pass
    return None

def save_record(symbol, market, score, rtg, action, stg, ds, ws, conf, dec, payload):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analyses_v3(
      created_at,symbol,market,score,rating,action,stage,daily_score,weekly_score,
      confidence,decision,analysis_json
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), symbol, market, score, rtg,
        action, stg, ds, ws, conf, dec, json.dumps(payload, ensure_ascii=False)
    ))
    conn.commit()
    conn.close()

def history(limit=300, symbol=None):
    conn = sqlite3.connect(DB_PATH)
    if symbol:
        df = pd.read_sql_query(
            "SELECT * FROM analyses_v3 WHERE symbol=? ORDER BY id DESC LIMIT ?",
            conn, params=(symbol,limit)
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM analyses_v3 ORDER BY id DESC LIMIT ?", conn, params=(limit,)
        )
    conn.close()
    return df

def previous_record(symbol):
    if not symbol:
        return None
    df = history(1, symbol)
    return None if df.empty else df.iloc[0].to_dict()

def label(v):
    return DISPLAY.get(v, v if v not in (None,"") else "未知")

def pct(v):
    if pd.isna(v):
        return "—"
    return f"{v:.1%}"

def fmt_num(v):
    return v if str(v).strip() else "—"

init_db()

st.title("📈 中长线决策引擎 V3")
st.caption("周线定环境 · 日线定时机 · DeepSeek只负责读图 · 规则引擎评分 · 风险预算控仓")
st.caption("评分是规则一致性分数，不是上涨概率；任何单次信号都必须服从仓位和失效位纪律。")

tab_decision, tab_history, tab_backtest, tab_system, tab_settings = st.tabs(
    ["🎯 决策","📚 历史","🧪 回测","🧠 系统","⚙️ 设置"]
)

with tab_settings:
    st.subheader("API 与运行状态")
    env_key = os.getenv("DEEPSEEK_API_KEY","")
    if env_key:
        st.success("DeepSeek API Key 已由 Render 环境变量配置，无需重复输入。")
    else:
        st.warning("服务器尚未配置 DeepSeek API Key。")
        temp = st.text_input("临时 DeepSeek API Key", type="password")
        if temp:
            st.session_state["api_key"] = temp
            st.success("本次会话已启用临时 Key。")
    st.info("历史记录目前使用本地 SQLite。Render 免费实例重新部署/重建时可能清空历史；正式长期复盘应迁移到持久化数据库。")
    if os.getenv("APP_PASSWORD",""):
        st.success("已启用访问密码保护，DeepSeek额度不会暴露给公开访客。")
    else:
        st.warning("当前未启用APP_PASSWORD。若网址公开，其他人可能消耗你的DeepSeek额度。")
    st.markdown("iPhone：Safari 打开网址 → 分享 → **添加到主屏幕**。")

with tab_system:
    st.subheader("这套系统解决什么")
    st.markdown("""
**核心原则：先判断“环境”，再决定“时机”，最后才谈仓位。**

1. **周线 = 中长线环境**：周线向上时，日线回调更可能是机会；周线向下时，日线金叉优先当修复。
2. **日线 = 执行时机**：BOLL中轨负责趋势与位置，MACD负责动能确认，成交量负责验证参与度。
3. **规则引擎 ≠ 大模型拍脑袋**：DeepSeek只负责读图，评分和行动门槛由固定规则计算。
4. **基本面/估值是硬约束**：中长线不能只靠技术图形；基本面恶化、逻辑破坏会否决主动加仓。
5. **仓位由风险预算决定**：不是“看多就重仓”，而是用失效位距离反推仓位上限。
""")
    st.subheader("评分框架")
    st.dataframe(pd.DataFrame([
        ["BOLL中轨方向",20,"趋势主方向"],
        ["价格相对中轨",15,"结构位置"],
        ["MACD零轴",15,"趋势环境"],
        ["DIF方向",10,"动能方向"],
        ["MACD柱体",15,"动能加减速"],
        ["金叉/死叉",10,"确认信号"],
        ["成交量",10,"参与度验证"],
        ["背离",5,"风险预警"],
    ], columns=["因子","满分","作用"]), hide_index=True, width="stretch")
    st.caption("有周线时总分 = 日线45% + 周线55%。缺少周线时置信度封顶，主动建仓/加仓结论会自动降级。")

with tab_decision:
    st.subheader("① 图表证据")
    daily_img = st.file_uploader(
        "日线截图（必填）",
        type=["png","jpg","jpeg","webp"],
        key="daily_img",
        help="建议包含至少2-3个月K线、BOLL、MACD、成交量。"
    )
    weekly_img = st.file_uploader(
        "周线截图（强烈建议）",
        type=["png","jpg","jpeg","webp"],
        key="weekly_img",
        help="中长线决策中，周线决定环境；缺少周线时系统会自动降低结论等级。"
    )
    if daily_img:
        with st.expander("查看日线截图"):
            st.image(daily_img, width="stretch")
    if weekly_img:
        with st.expander("查看周线截图"):
            st.image(weekly_img, width="stretch")

    st.subheader("② 标的与投资前提")
    symbol = st.text_input("股票/ETF名称或代码", placeholder="例如：腾讯控股 / 0700.HK")
    market = st.selectbox("市场", ["自动判断","A股","港股","美股","ETF/其他"])

    c1,c2 = st.columns(2)
    with c1:
        position_level = st.selectbox("当前仓位", ["未持仓","轻仓(<10%)","中仓(10-20%)","重仓(>20%)"])
        cost = st.text_input("持仓成本（可选）", placeholder="例如：435")
        fundamental = st.selectbox("基本面趋势", ["未知","改善","稳定","恶化"])
    with c2:
        valuation = st.selectbox("估值状态", ["未知","偏低","合理","偏高"])
        thesis = st.selectbox("投资逻辑", ["未知","完整","有疑点","破坏"])
        market_regime = st.selectbox("大盘/行业环境", ["未知","强势","震荡","弱势"])

    notes = st.text_area(
        "补充说明（可选）",
        placeholder="例如：计划持有1-3年；只考虑回撤加仓；这是盘中截图……",
        height=80
    )

    with st.expander("③ 风险预算"):
        risk_budget = st.slider("单次交易最大风险预算（占总资产）",0.20,1.50,0.50,0.05,format="%.2f%%")
        max_single = st.slider("单一标的最大仓位参考",5,30,15,1,format="%d%%")
        st.caption("仓位参考 = 风险预算 ÷ 现价到失效位距离，并受单一标的上限约束。")

    st.subheader("④ 分析精度")
    mode = st.radio("DeepSeek模式",["省钱模式","标准模式","精细模式"],index=1,horizontal=True)

    if st.button("🚀 生成中长线决策", type="primary", width="stretch"):
        key = os.getenv("DEEPSEEK_API_KEY","") or st.session_state.get("api_key","")
        if not daily_img:
            st.error("请至少上传日线截图。")
            st.stop()
        if not key:
            st.error("请先在设置中配置 DeepSeek API Key。")
            st.stop()

        if mode=="省钱模式":
            detail="low"; max_tokens=2600
        elif mode=="精细模式":
            detail="original"; max_tokens=5200
        else:
            detail="original"; max_tokens=3800

        user_context = f"""标的：{symbol.strip() or '未填写'}
市场：{market}
当前仓位：{position_level}
持仓成本：{cost or '未填写'}
补充说明：{notes or '无'}
下面依次提供日线截图，以及可选周线截图。只提取图表事实，不要替程序做最终评分。"""

        content = [
            {"type":"text","text":user_context},
            {"type":"text","text":"【日线截图】"},
            {"type":"image_url","image_url":{"url":to_data_url(daily_img),"detail":detail}},
        ]
        if weekly_img:
            content += [
                {"type":"text","text":"【周线截图】"},
                {"type":"image_url","image_url":{"url":to_data_url(weekly_img),"detail":detail}},
            ]

        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")

        def call_ds(tokens, retry=False):
            msg = content.copy()
            if retry:
                msg.append({"type":"text","text":"上一次JSON可能不完整。重新输出更短、更完整的合法JSON，确保括号全部闭合。"})
            return client.chat.completions.create(
                model="deepseek-flash",
                reasoning_effort="low",
                max_tokens=tokens,
                response_format={"type":"json_object"},
                messages=[
                    {"role":"system","content":EXTRACT_PROMPT},
                    {"role":"user","content":msg}
                ]
            )

        with st.spinner("正在读取日线/周线并运行规则引擎..."):
            try:
                resp = call_ds(max_tokens)
                raw = resp.choices[0].message.content or ""
                data = parse_json(raw)
                if getattr(resp.choices[0],"finish_reason",None)=="length" or not data:
                    resp = call_ds(6500, retry=True)
                    raw = resp.choices[0].message.content or ""
                    data = parse_json(raw)
            except Exception as e:
                st.error(f"DeepSeek调用失败：{e}")
                st.stop()

        if not data:
            st.error("模型连续返回了无法解析的结果。请重新上传更清晰的截图再试。")
            st.stop()

        daily = normalize_tf(data.get("daily"), True)
        weekly = normalize_tf(data.get("weekly"), False)
        if not weekly_img:
            weekly["visible"] = False

        score, dscore, wscore = technical_score(daily, weekly)
        conf = confidence_score(daily, weekly)
        extraction_issues, extraction_penalty = validate_extraction(daily, weekly)
        conf = max(0, conf - extraction_penalty)
        if data.get("global",{}).get("is_intraday_unclosed"):
            conf = max(0, conf - 10)
        rtg = rating(score)
        stg = stage(daily, weekly)

        action, reasons = decision(
            score, dscore, wscore, conf, daily, weekly,
            position_level, fundamental, valuation, thesis, market_regime
        )

        prev = previous_record(symbol.strip())
        compare_text = ""
        if prev:
            old = float(prev.get("score") or 0)
            delta = score-old
            direction = "升级" if delta>=5 else ("降级" if delta<=-5 else "基本持平")
            compare_text = f"{direction}：评分 {old:.0f} → {score:.0f}（{delta:+.0f}）"

        pos_ref = risk_position_reference(daily, risk_budget, max_single)
        upgrades, downgrades = transition_conditions(daily, weekly)

        if data.get("global",{}).get("is_intraday_unclosed"):
            st.warning("⚠️ 当前截图可能是盘中数据：收盘前BOLL和MACD信号仍可能变化。")

        st.subheader("决策仪表盘")
        a,b,c,d = st.columns(4)
        a.metric("技术评分",f"{score:.0f}/100")
        b.metric("评级",rtg)
        c.metric("行动",ACTION_CN.get(action,action))
        d.metric("证据置信度",f"{conf}%")

        st.markdown(f"<div class='decision-card'><b>阶段：</b>{stg}<br><b>核心结论：</b>{'；'.join(reasons)}</div>", unsafe_allow_html=True)

        if not weekly.get("visible"):
            st.warning("中长线系统缺少周线截图：当前结论只适合做日线观察，主动建仓/加仓会被自动降级。")
        if conf < 70:
            st.warning("证据置信度低于70%。建议上传更清晰、指标更完整的截图后再做仓位决策。")
        for issue in extraction_issues:
            st.warning("数据一致性检查：" + issue)
        if daily.get("image_quality",0) and int(daily.get("image_quality",0)) < 65:
            st.warning("日线截图质量偏低：关键数值可能识别错误，建议重新截图。")
        if weekly.get("visible") and int(weekly.get("image_quality",0) or 0) < 65:
            st.warning("周线截图质量偏低：中长线判断可靠性下降。")

        st.subheader("1. 多周期结构")
        r1,r2 = st.columns(2)
        with r1:
            st.markdown("### 日线")
            st.write(f"得分：**{dscore:.0f}/100**")
            st.write(f"BOLL中轨：**{label(daily.get('mid_direction'))}** ｜ 价格在中轨**{label(daily.get('price_vs_mid'))}**")
            st.write(f"MACD：零轴**{label(daily.get('zero_zone'))}** ｜ {label(daily.get('cross'))} ｜ {label(daily.get('bar_momentum'))}")
            st.write(f"成交量：{label(daily.get('volume_state'))} ｜ 背离：{label(daily.get('divergence'))}")
            if daily.get("notes"): st.caption(daily.get("notes"))
        with r2:
            st.markdown("### 周线")
            if weekly.get("visible"):
                st.write(f"得分：**{wscore:.0f}/100**")
                st.write(f"BOLL中轨：**{label(weekly.get('mid_direction'))}** ｜ 价格在中轨**{label(weekly.get('price_vs_mid'))}**")
                st.write(f"MACD：零轴**{label(weekly.get('zero_zone'))}** ｜ {label(weekly.get('cross'))} ｜ {label(weekly.get('bar_momentum'))}")
                st.write(f"成交量：{label(weekly.get('volume_state'))} ｜ 背离：{label(weekly.get('divergence'))}")
                if weekly.get("notes"): st.caption(weekly.get("notes"))
            else:
                st.info("未上传周线。")

        st.subheader("2. 评分透明度")
        bd = score_breakdown(daily) or {}
        bw = score_breakdown(weekly) if weekly.get("visible") else None
        score_rows = []
        for k,v in bd.items():
            score_rows.append([k,v,(bw or {}).get(k,"—")])
        st.dataframe(pd.DataFrame(score_rows,columns=["因子","日线得分","周线得分"]),hide_index=True,width="stretch")

        st.subheader("3. 关键位与执行条件")
        ucol,dcol = st.columns(2)
        with ucol:
            st.markdown("### 升级条件")
            if upgrades:
                for x in upgrades:
                    st.markdown(f"- {x}")
            else:
                st.write("当前已接近高质量趋势状态。")
        with dcol:
            st.markdown("### 降级/失效条件")
            if downgrades:
                for x in downgrades:
                    st.markdown(f"- {x}")
            else:
                st.write("截图中暂未形成清晰失效位。")

        st.markdown("### 关键价格")
        key_rows = [
            ["现价",fmt_num(daily.get("price"))],
            ["日线BOLL中轨",fmt_num(daily.get("boll_mid"))],
            ["日线支撑",fmt_num(daily.get("support_1"))],
            ["日线压力",fmt_num(daily.get("resistance_1"))],
            ["结构失效位",fmt_num(daily.get("invalidation_price"))],
        ]
        if weekly.get("visible"):
            key_rows += [
                ["周线BOLL中轨",fmt_num(weekly.get("boll_mid"))],
                ["周线支撑",fmt_num(weekly.get("support_1"))],
                ["周线压力",fmt_num(weekly.get("resistance_1"))],
            ]
        st.dataframe(pd.DataFrame(key_rows,columns=["关键位","数值"]),hide_index=True,width="stretch")

        try:
            current_price = float(str(daily.get("price","")).replace(",",""))
            holding_cost = float(str(cost).replace(",","")) if cost else None
            if holding_cost and holding_cost > 0:
                pnl = current_price/holding_cost - 1
                st.caption(f"相对持仓成本浮动：{pnl:+.1%}。系统不会因为盈亏本身改变趋势判断，避免成本锚定。")
        except Exception:
            pass

        if pos_ref:
            st.markdown("### 风险预算仓位参考")
            p1,p2,p3 = st.columns(3)
            p1.metric("失效距离",f"{pos_ref['stop_pct']:.1f}%")
            p2.metric("风险公式仓位",f"{pos_ref['raw_pct']:.1f}%")
            p3.metric("应用上限后",f"{pos_ref['cap_pct']:.1f}%")
            st.caption("这是基于你设置的单次风险预算和图上结构失效位计算的上限参考，不代表必须持有该仓位。")
        else:
            st.info("截图没有可靠的结构失效位，因此系统不强行计算仓位。")

        st.subheader("4. 中长线硬约束")
        constraints = pd.DataFrame([
            ["基本面趋势",fundamental,"恶化时禁止主动扩张仓位"],
            ["估值状态",valuation,"偏高时降低新增仓位优先级"],
            ["投资逻辑",thesis,"破坏时优先退出/回避"],
            ["大盘/行业",market_regime,"弱势环境提高进攻门槛"],
            ["当前仓位",position_level,"重仓时即便强势也优先控制集中度"],
        ],columns=["维度","当前输入","系统纪律"])
        st.dataframe(constraints,hide_index=True,width="stretch")

        if compare_text:
            st.subheader("5. 与上次相比")
            st.info(compare_text)

        decision_text = (
            f"{symbol or '该标的'}：技术评分{score:.0f}，评级{rtg}，阶段{stg}，"
            f"行动={ACTION_CN.get(action,action)}。"
        )
        payload = {
            "daily":daily,"weekly":weekly,"global":data.get("global",{}),
            "inputs":{
                "position":position_level,"cost":cost,"fundamental":fundamental,
                "valuation":valuation,"thesis":thesis,"market_regime":market_regime,
                "risk_budget_pct":risk_budget,"max_single_pct":max_single
            },
            "result":{
                "score":score,"daily_score":dscore,"weekly_score":wscore,
                "confidence":conf,"rating":rtg,"stage":stg,"action":action,
                "reasons":reasons,"compare":compare_text,"position_reference":pos_ref,
                "upgrade_conditions":upgrades,"downgrade_conditions":downgrades,
                "extraction_issues":extraction_issues
            }
        }
        save_record(symbol.strip(), market, score, rtg, action, stg, dscore, wscore, conf, decision_text, payload)

        report = f"""# {symbol or '标的'} 中长线决策报告
时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
市场：{market}

## 决策
- 技术评分：{score:.0f}/100
- 评级：{rtg}
- 阶段：{stg}
- 行动：{ACTION_CN.get(action,action)}
- 证据置信度：{conf}%
- 原因：{'；'.join(reasons)}

## 日线
- 中轨方向：{label(daily.get('mid_direction'))}
- 价格/中轨：{label(daily.get('price_vs_mid'))}
- 零轴：{label(daily.get('zero_zone'))}
- 交叉：{label(daily.get('cross'))}
- 柱体：{label(daily.get('bar_momentum'))}

## 周线
- 是否提供：{'是' if weekly.get('visible') else '否'}
- 中轨方向：{label(weekly.get('mid_direction')) if weekly.get('visible') else '—'}
- 价格/中轨：{label(weekly.get('price_vs_mid')) if weekly.get('visible') else '—'}

## 风险纪律
- 单次风险预算：{risk_budget:.2f}%
- 单一标的仓位上限：{max_single}%
- 基本面：{fundamental}
- 估值：{valuation}
- 投资逻辑：{thesis}
- 市场环境：{market_regime}

> 该报告是规则化技术与风险管理辅助，不代表收益保证。
"""
        st.download_button(
            "⬇️ 下载本次报告",
            report.encode("utf-8"),
            file_name=f"{symbol or 'analysis'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            width="stretch"
        )

with tab_history:
    st.subheader("历史复盘")
    df = history()
    if df.empty:
        st.info("暂无V3历史记录。")
    else:
        symbols = ["全部"] + [x for x in df["symbol"].dropna().astype(str).unique() if x]
        chosen = st.selectbox("筛选标的",symbols)
        view = df if chosen=="全部" else df[df["symbol"]==chosen]
        cols = ["created_at","symbol","score","rating","action","stage","daily_score","weekly_score","confidence","decision"]
        st.dataframe(view[cols],hide_index=True,width="stretch")
        if chosen!="全部" and len(view)>=2:
            chart = view.sort_values("created_at")[["created_at","score"]].copy()
            st.line_chart(chart.set_index("created_at")["score"],height=230)
            st.caption("评分曲线用于观察结构升级/降级，不是收益曲线。")
        st.download_button(
            "⬇️ 导出历史CSV",
            view.to_csv(index=False).encode("utf-8-sig"),
            "medium_term_history.csv",
            "text/csv",
            width="stretch"
        )

with tab_backtest:
    st.subheader("规则回测")
    st.caption("这里验证的是核心技术规则，而不是DeepSeek的主观判断。回测不能证明未来收益，但可以排除明显无效的规则。")
    csv_file = st.file_uploader(
        "上传日线CSV",
        type=["csv"],
        key="bt_csv",
        help="至少包含 Date 和 Close 列；Date不是必需，但有日期才能计算年化收益。"
    )
    p1,p2 = st.columns(2)
    with p1:
        fee = st.slider("单边交易成本（bp）",0,50,10,1)
        boll_n = st.slider("BOLL中轨周期",10,40,20,1)
        weekly_filter = st.checkbox("启用周线环境过滤", value=True)
    with p2:
        fast = st.number_input("MACD快线",5,20,12)
        slow = st.number_input("MACD慢线",15,50,26)
        sig = st.number_input("MACD信号线",5,20,9)

    st.caption("回测按收盘信号、下一根K线生效，避免使用未来数据。启用周线过滤时，CSV必须有Date/Datetime列。")

    if csv_file and st.button("运行回测",type="primary",width="stretch"):
        try:
            x = pd.read_csv(csv_file)
            bt = backtest(x,fee,boll_n,int(fast),int(slow),int(sig),weekly_filter)
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("策略总收益",pct(bt["total_return"]))
            m2.metric("买入持有",pct(bt["benchmark_return"]))
            m3.metric("最大回撤",pct(bt["max_drawdown"]))
            m4.metric("交易次数",bt["trades"])
            m5,m6,m7,m8 = st.columns(4)
            m5.metric("年化收益",pct(bt["cagr"]))
            m6.metric("胜率",pct(bt["win_rate"]))
            pf = bt["profit_factor"]
            m7.metric("Profit Factor", "—" if pd.isna(pf) else f"{pf:.2f}")
            mar = bt["mar"]
            m8.metric("MAR", "—" if pd.isna(mar) else f"{mar:.2f}")
            st.caption(f"策略持仓暴露时间：{bt['exposure']:.1%}")
            st.line_chart(bt["curve"],height=280)
            if bt["oos"]:
                st.info(
                    f"后30%样本检验：收益 {bt['oos']['return']:.1%}，"
                    f"最大回撤 {bt['oos']['max_drawdown']:.1%}。"
                )
            st.warning("不要针对单一标的反复调参数追求漂亮历史曲线；真正要看跨标的、跨周期、样本外稳定性，以及回撤是否可承受。")
        except Exception as e:
            st.error(f"回测失败：{e}")

st.divider()
st.caption("中长线决策辅助工具。目标是提高决策一致性与风险控制，不承诺收益；关键价格与基本面请用原始行情/财报复核。")
