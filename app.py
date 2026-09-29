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
    page_title="MACD+BOLL 日线决策",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container{
 max-width:1050px;
 padding-top:calc(env(safe-area-inset-top, 0px) + 3.2rem);
 padding-bottom:4rem;
 padding-left:.7rem;
 padding-right:.7rem
}
h1{font-size:1.55rem!important;margin-bottom:.2rem!important}
div[data-testid="stMetric"]{border:1px solid rgba(128,128,128,.22);border-radius:12px;padding:9px 10px}
.decision{border:1px solid rgba(128,128,128,.25);border-radius:14px;padding:14px;margin:8px 0 12px}
@media(max-width:700px){
 .block-container{
   padding-left:.5rem;
   padding-right:.5rem;
   padding-top:calc(env(safe-area-inset-top, 0px) + 3.5rem)
 }
 h1{font-size:1.35rem!important}
 .stTextInput input,.stTextArea textarea{font-size:16px!important}
 button[kind="primary"]{min-height:48px;font-size:1.02rem}
}
</style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """
你是一名严谨的日线技术分析助手。用户上传股票/ETF日K截图。
核心体系：BOLL + MACD；成交量和ATR仅在截图清晰可见时辅助。
禁止臆测看不清的数据。

优先级：
1 BOLL中轨方向
2 价格相对中轨位置
3 MACD零轴位置
4 DIF方向
5 柱体变化
6 金叉/死叉质量

规则：
- BOLL负责趋势/位置/支撑压力；MACD负责动能/确认。
- 零轴下金叉优先定义为反弹或修复，不直接定义趋势反转。
- 零轴上二次金叉+BOLL中轨向上属于高质量趋势延续。
- 零轴附近粘合时，金叉死叉降级处理。
- 背离只做预警，不单独构成买卖确认。
- 盘中截图必须提示“未收盘，信号可能变化”。

评级：
S=强多头共振；
A=趋势转换确认；
B=反弹/修复；
C=弱势/空头。
可用+/-。

五状态：
BUY=买入候选，仅A/S且趋势动能共振；
HOLD=持有，趋势未破坏；
WATCH=观察，修复/测试/震荡/冲突；
REDUCE=减仓，明显转弱；
AVOID=回避，趋势动能双弱。

必须只输出一个合法 JSON 对象，不要 Markdown 代码块，不要在 JSON 前后添加任何文字。字段严格为：
{
 "rating":"",
 "state":"",
 "stage":"",
 "one_line":"",
 "price":"",
 "boll_mid":"",
 "boll_upper":"",
 "boll_lower":"",
 "boll_mid_direction":"",
 "price_vs_mid":"",
 "dif":"",
 "dea":"",
 "macd_bar":"",
 "macd_zero_zone":"",
 "cross":"",
 "bar_momentum":"",
 "volume":"",
 "atr":"",
 "key_level":"",
 "upgrade_condition":"",
 "downgrade_condition":"",
 "confidence":0,
 "essence":"",
 "boll_analysis":"",
 "macd_analysis":"",
 "resonance":"",
 "comparison":"",
 "action_1":"",
 "action_2":"",
 "action_3":"",
 "risk_1":"",
 "risk_2":"",
 "risk_3":"",
 "decision_model":""
}
所有字符串必须简洁：普通字段尽量不超过80个汉字；essence不超过180字；comparison不超过120字；每个action/risk不超过80字。
必须确保JSON完整闭合，宁可少写也不要截断。confidence 为 0-100 的整数。
不要承诺收益，不使用“必涨/必跌/稳赚”。
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS analyses(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      symbol TEXT,
      market TEXT,
      rating TEXT,
      state TEXT,
      stage TEXT,
      one_line TEXT,
      price TEXT,
      boll_mid TEXT,
      boll_mid_direction TEXT,
      macd_zero_zone TEXT,
      cross_signal TEXT,
      bar_momentum TEXT,
      key_level TEXT,
      upgrade_condition TEXT,
      downgrade_condition TEXT,
      confidence INTEGER,
      raw_result TEXT
    )
    """)
    conn.commit()
    conn.close()

def to_data_url(file):
    mime = getattr(file, "type", None) or "image/png"
    return f"data:{mime};base64,{base64.b64encode(file.getvalue()).decode('utf-8')}"

def parse_result(text):
    text = (text or "").strip()
    # 1) DeepSeek JSON Output: expected path
    try:
        obj = json.loads(text)
        return obj, ""
    except Exception:
        pass

    # 2) Fallback: fenced JSON
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
    if m:
        try:
            return json.loads(m.group(1)), ""
        except Exception:
            pass

    # 3) Fallback: first balanced-looking JSON object
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1]), ""
        except Exception:
            pass
    return None, text

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

def save(symbol, market, p, raw):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analyses(
      created_at,symbol,market,rating,state,stage,one_line,price,boll_mid,
      boll_mid_direction,macd_zero_zone,cross_signal,bar_momentum,key_level,
      upgrade_condition,downgrade_condition,confidence,raw_result
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
      datetime.now().strftime("%Y-%m-%d %H:%M:%S"), symbol, market,
      p.get("rating",""), p.get("state",""), p.get("stage",""), p.get("one_line",""),
      str(p.get("price","")), str(p.get("boll_mid","")), p.get("boll_mid_direction",""),
      p.get("macd_zero_zone",""), p.get("cross",""), p.get("bar_momentum",""),
      p.get("key_level",""), p.get("upgrade_condition",""), p.get("downgrade_condition",""),
      int(p.get("confidence",0) or 0), raw
    ))
    conn.commit()
    conn.close()

def history(limit=100):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM analyses ORDER BY id DESC LIMIT ?", conn, params=(limit,))
    conn.close()
    return df

init_db()

st.markdown("<div style='height:.2rem'></div>", unsafe_allow_html=True)
st.title("📈 MACD + BOLL 日线决策 · DeepSeek版")
st.caption("DeepSeek国内版 · 上传截图 → 评级 → 五状态 → 关键位 → 升级/降级条件")

tab1, tab2, tab3 = st.tabs(["📷 分析", "📚 历史", "⚙️ 设置"])

with tab3:
    st.subheader("API 设置")
    env_key = os.getenv("DEEPSEEK_API_KEY", "")
    if env_key:
        st.success("服务器已配置 DeepSeek API Key。")
    else:
        st.info("服务器尚未配置 Key。可在这里临时输入；仅保存在当前浏览器会话。")
    temp = st.text_input("DeepSeek API Key", type="password", key="temp_key")
    if temp:
        st.session_state["api_key"] = temp
        st.success("本次会话已启用临时 Key。")
    st.markdown("iPhone：Safari打开网址 → 分享 → **添加到主屏幕**。")
    st.markdown("""
**DeepSeek 国内版**
- 省钱：低分辨率读取截图，适合日常复盘
- 标准：原图读取，适合大多数K线分析
- 精细：原图 + 更长输出，适合复杂图形

""")

with tab1:
    source = st.radio("图片来源", ["相册 / 文件", "相机"], horizontal=True, label_visibility="collapsed")
    uploaded = (
        st.file_uploader("选择K线截图", type=["png","jpg","jpeg","webp"])
        if source == "相册 / 文件"
        else st.camera_input("拍摄图表")
    )
    if uploaded:
        st.image(uploaded, use_container_width=True)

    symbol = st.text_input("股票/ETF名称或代码", placeholder="例如：腾讯控股 / 0700.HK")
    market = st.selectbox("市场", ["自动判断","A股","港股","美股","ETF/其他"])

    with st.expander("持仓信息（可选）"):
        position = st.text_input("当前仓位", placeholder="例如：25%")
        cost = st.text_input("持仓成本", placeholder="例如：435")
        notes = st.text_area("补充说明", placeholder="例如：中线持有；这是盘中截图……", height=90)

    st.markdown("### 💰 DeepSeek 分析模式")
    mode = st.radio(
        "选择分析模式",
        ["省钱模式", "标准模式", "精细模式"],
        index=1,
        help="三种模式都使用 DeepSeek Flash。省钱模式降低图片细节；标准模式使用原图；精细模式使用原图并允许更长输出。"
    )
    st.caption("默认推荐“标准模式”。日常大量复盘可用省钱模式，复杂图形再切精细模式。")
    compare = st.checkbox("自动和同标的上一次分析比较", value=True)

    if st.button("🚀 开始分析", type="primary", use_container_width=True):
        key = os.getenv("DEEPSEEK_API_KEY","") or st.session_state.get("api_key","")
        if not uploaded:
            st.error("请先上传截图。")
            st.stop()
        if not key:
            st.error("请到“设置”输入 DeepSeek API Key。")
            st.stop()

        prev = previous(symbol.strip()) if compare else None
        prompt = [
            "请分析上传的日K截图。",
            f"标的：{symbol.strip() or '未填写'}",
            f"市场：{market}",
            f"当前仓位：{position or '未填写'}",
            f"持仓成本：{cost or '未填写'}",
            f"补充说明：{notes or '无'}",
        ]
        if prev:
            prompt += [
                "",
                "同一标的上一次结果如下，请在正文增加“与上次相比”，判断升级/持平/降级：",
                f"上次时间：{prev.get('created_at','')}",
                f"上次评级：{prev.get('rating','')}",
                f"上次状态：{prev.get('state','')}",
                f"上次阶段：{prev.get('stage','')}",
                f"上次中轨方向：{prev.get('boll_mid_direction','')}",
                f"上次MACD区域：{prev.get('macd_zero_zone','')}",
            ]

        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
        image_url = to_data_url(uploaded)

        if mode == "省钱模式":
            image_detail = "low"
            max_tokens = 2600
        elif mode == "精细模式":
            image_detail = "original"
            max_tokens = 5000
        else:
            image_detail = "original"
            max_tokens = 3600

        full_prompt = "\n".join(prompt)
        model_used = f"DeepSeek Flash · {mode}"

        def deepseek_call(token_budget, retry_note=""):
            user_text = full_prompt
            if retry_note:
                user_text += "\n\n" + retry_note
            return client.chat.completions.create(
                model="deepseek-flash",
                max_tokens=token_budget,
                response_format={"type":"json_object"},
                messages=[
                    {"role":"system","content":SYSTEM_PROMPT},
                    {
                        "role":"user",
                        "content":[
                            {"type":"text","text":user_text},
                            {
                                "type":"image_url",
                                "image_url":{
                                    "url":image_url,
                                    "detail":image_detail
                                }
                            }
                        ]
                    }
                ]
            )

        with st.spinner("DeepSeek 正在读取截图并分析..."):
            try:
                resp = deepseek_call(max_tokens)
                raw = resp.choices[0].message.content or ""
                finish_reason = getattr(resp.choices[0], "finish_reason", None)
                parsed, body = parse_result(raw)

                # If output was truncated or malformed, retry once with a larger budget.
                if finish_reason == "length" or not parsed:
                    resp = deepseek_call(
                        6000,
                        "上一次输出可能被截断。请重新输出一个完整、简洁、合法的JSON对象；不要解释，不要Markdown，务必闭合所有引号和大括号。"
                    )
                    raw = resp.choices[0].message.content or ""
                    parsed, body = parse_result(raw)
            except Exception as e:
                st.error(f"分析失败：{e}")
                st.stop()
        if not parsed:
            st.warning("DeepSeek 连续两次返回了不完整JSON。本次不保存历史；请切到“省钱模式”或重新分析。")
            st.markdown(body)
        else:
            save(symbol.strip(), market, parsed, raw)
            st.caption(f"本次使用：{model_used}")
            c1,c2 = st.columns(2)
            c1.metric("评级", parsed.get("rating","未知"))
            c2.metric("状态", parsed.get("state","未知"))
            c3,c4 = st.columns(2)
            c3.metric("阶段", parsed.get("stage","未知"))
            c4.metric("置信度", f"{parsed.get('confidence',0)}%")

            st.markdown(f"<div class='decision'><b>一句话结论</b><br>{parsed.get('one_line','')}</div>", unsafe_allow_html=True)

            st.markdown("## 1. 本质分析")
            st.write(parsed.get("essence",""))
            st.markdown(f"**BOLL：** {parsed.get('boll_analysis','')}")
            st.markdown(f"**MACD：** {parsed.get('macd_analysis','')}")
            st.markdown(f"**共振/冲突：** {parsed.get('resonance','')}")
            if parsed.get("comparison"):
                st.markdown(f"**与上次相比：** {parsed.get('comparison','')}")

            st.markdown("## 2. 结构化决策")
            decision_df = pd.DataFrame([
                ["BOLL中轨", parsed.get("boll_mid_direction","未知"), parsed.get("boll_mid","未知")],
                ["价格位置", parsed.get("price_vs_mid","未知"), parsed.get("price","未知")],
                ["MACD零轴", parsed.get("macd_zero_zone","未知"), parsed.get("cross","未知")],
                ["柱体动能", parsed.get("bar_momentum","未知"), parsed.get("macd_bar","未知")],
            ], columns=["维度","当前状态","关键数据"])
            st.dataframe(decision_df, use_container_width=True, hide_index=True)

            st.markdown("## 3. 明确结论")
            st.info(f"评级 {parsed.get('rating','未知')} · 状态 {parsed.get('state','未知')} · 阶段：{parsed.get('stage','未知')}")
            st.markdown("**关键观察位**")
            st.info(parsed.get("key_level","未知"))
            st.markdown("**升级条件**")
            st.success(parsed.get("upgrade_condition","未知"))
            st.markdown("**降级条件**")
            st.warning(parsed.get("downgrade_condition","未知"))

            st.markdown("## 4. 可执行行动")
            st.markdown(f"1. {parsed.get('action_1','')}")
            st.markdown(f"2. {parsed.get('action_2','')}")
            st.markdown(f"3. {parsed.get('action_3','')}")

            st.markdown("### 风险提示 Top 3")
            st.markdown(f"- {parsed.get('risk_1','')}")
            st.markdown(f"- {parsed.get('risk_2','')}")
            st.markdown(f"- {parsed.get('risk_3','')}")
            st.markdown("### 一句话判断模型")
            st.write(parsed.get("decision_model",""))

with tab2:
    st.subheader("历史记录")
    df = history(200)
    if df.empty:
        st.info("暂无历史记录。")
    else:
        cols = ["created_at","symbol","market","rating","state","stage","price","boll_mid","boll_mid_direction","macd_zero_zone","cross_signal","bar_momentum","confidence"]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
        st.download_button("⬇️ 导出历史CSV", df.to_csv(index=False).encode("utf-8-sig"), "macd_boll_history.csv", "text/csv", use_container_width=True)

st.divider()
st.caption("技术分析辅助工具。盘中信号可能变化；截图识别受清晰度影响；关键数据请以行情软件原始数据复核。")
