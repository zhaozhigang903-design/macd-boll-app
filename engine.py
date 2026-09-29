import math
import re
import pandas as pd

MID_SCORE = {"up":20, "flat":10, "down":0, "unknown":8}
PRICE_SCORE = {"above":15, "near":8, "below":0, "unknown":6}
ZERO_SCORE = {"above":15, "near":8, "below":0, "unknown":6}
DIF_SCORE = {"up":10, "flat":5, "down":0, "unknown":4}
BAR_SCORE = {
    "red_expanding":15, "red_shrinking":10, "green_shrinking":7,
    "green_expanding":0, "unclear":6, "unknown":6
}
CROSS_SCORE = {"golden":10, "adhesion":5, "death":0, "unknown":4}
VOLUME_SCORE = {
    "breakout_up_volume":10, "contract_pullback":8, "normal":5,
    "contract_rebound":4, "decline_volume":0, "unavailable":4, "unknown":4
}
DIV_SCORE = {"none":5, "bottom":4, "top":0, "uncertain":3, "unknown":3}

ACTION_CN = {
    "BUILD_CANDIDATE":"建仓候选",
    "ADD_CANDIDATE":"加仓候选",
    "HOLD":"持有",
    "WATCH":"观察",
    "REDUCE":"减仓",
    "AVOID":"回避",
}

CN = {
    "up":"向上","flat":"走平","down":"向下","unknown":"未知",
    "above":"中轨上","near":"中轨附近","below":"中轨下",
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
    "above":"零轴上","near":"零轴附近","below":"零轴下",
}

def normalize_tf(x, visible_default=False):
    x = x.copy() if isinstance(x, dict) else {}
    defaults = {
        "visible": visible_default, "image_quality":0, "price":"", "boll_mid":"",
        "boll_upper":"", "boll_lower":"", "mid_direction":"unknown",
        "price_vs_mid":"unknown", "price_vs_band":"unknown", "dif":"", "dea":"",
        "macd_bar":"", "dif_direction":"unknown", "zero_zone":"unknown",
        "cross":"unknown", "bar_momentum":"unknown", "volume_state":"unknown",
        "divergence":"unknown", "support_1":"", "resistance_1":"",
        "invalidation_price":"", "notes":""
    }
    for k,v in defaults.items():
        x.setdefault(k,v)
    return x

def timeframe_score(x):
    if not x.get("visible"):
        return None
    return float(
        MID_SCORE.get(x.get("mid_direction"),8) +
        PRICE_SCORE.get(x.get("price_vs_mid"),6) +
        ZERO_SCORE.get(x.get("zero_zone"),6) +
        DIF_SCORE.get(x.get("dif_direction"),4) +
        BAR_SCORE.get(x.get("bar_momentum"),6) +
        CROSS_SCORE.get(x.get("cross"),4) +
        VOLUME_SCORE.get(x.get("volume_state"),4) +
        DIV_SCORE.get(x.get("divergence"),3)
    )

def completeness(x):
    keys = ["mid_direction","price_vs_mid","zero_zone","dif_direction","bar_momentum","cross","volume_state"]
    known = sum(1 for k in keys if x.get(k) not in ("unknown","",None))
    return known / len(keys)

def confidence_score(daily, weekly):
    dq = max(0,min(100,int(daily.get("image_quality",0) or 0)))
    dc = completeness(daily)*100
    dconf = 0.55*dq + 0.45*dc
    if weekly.get("visible"):
        wq = max(0,min(100,int(weekly.get("image_quality",0) or 0)))
        wc = completeness(weekly)*100
        wconf = 0.55*wq + 0.45*wc
        return int(round(0.45*dconf + 0.55*wconf))
    return int(min(72, round(dconf)))

def technical_score(daily, weekly):
    ds = timeframe_score(daily)
    ws = timeframe_score(weekly)
    if ds is None:
        return 0.0, 0.0, None
    total = 0.45*ds + 0.55*ws if ws is not None else ds
    # exhaustion penalty: avoid scoring an overextended/negative-divergence chart too highly
    if daily.get("price_vs_band") == "above_upper":
        total -= 4
    if daily.get("divergence") == "top":
        total -= 6
    if weekly.get("visible") and weekly.get("divergence") == "top":
        total -= 8
    return round(max(0,min(100,total)),1), round(ds,1), (round(ws,1) if ws is not None else None)

def rating(score):
    if score >= 85: return "S"
    if score >= 72: return "A"
    if score >= 52: return "B"
    return "C"

def stage(daily, weekly):
    if weekly.get("visible"):
        wm, dm = weekly.get("mid_direction"), daily.get("mid_direction")
        wp, dp = weekly.get("price_vs_mid"), daily.get("price_vs_mid")
        if wm=="up" and wp=="above" and dm=="up" and dp=="above":
            return "多头趋势延续"
        if wm=="up" and wp in ("above","near") and dp in ("near","below"):
            return "上升趋势中的回撤/再确认"
        if wm in ("flat","down") and daily.get("cross")=="golden":
            return "趋势修复"
        if wm=="down" and dm=="down" and dp=="below":
            return "空头趋势"
        return "多周期过渡/震荡"
    if daily.get("mid_direction")=="up" and daily.get("price_vs_mid")=="above":
        return "日线多头，待周线确认"
    if daily.get("cross")=="golden" and daily.get("zero_zone")=="below":
        return "日线反弹/修复"
    if daily.get("mid_direction")=="down" and daily.get("price_vs_mid")=="below":
        return "日线弱势"
    return "日线过渡/震荡"

def is_held(position_level):
    return position_level != "未持仓"

def decision(score, daily_score, weekly_score, confidence, daily, weekly,
             position_level, fundamental, valuation, thesis, market_regime):
    held = is_held(position_level)
    reasons = []
    overextended = daily.get("price_vs_band") in ("above_upper","upper_zone")
    weekly_ready = weekly.get("visible")

    if thesis == "破坏":
        return ("REDUCE" if held else "AVOID",
                ["投资逻辑已标记为破坏，属于高优先级否决条件。"])

    if confidence < 60:
        return "WATCH", ["证据质量不足；低置信度下不应放大仓位。"]

    if weekly_ready and weekly_score is not None and weekly_score < 45:
        reasons.append("周线结构偏弱，中长线环境不支持主动扩张仓位。")
        if held and score < 55:
            return "REDUCE", reasons
        return "WATCH", reasons

    if fundamental == "恶化":
        reasons.append("基本面趋势被标记为恶化，技术信号不能覆盖基本面风险。")
        if held and score < 70:
            return "REDUCE", reasons
        return "WATCH", reasons

    if not weekly_ready:
        reasons.append("缺少周线确认，中长线结论自动降级。")
        if held:
            return ("HOLD" if score >= 66 else "WATCH"), reasons
        return "WATCH", reasons

    if market_regime == "弱势" and score < 88:
        reasons.append("市场环境偏弱，主动进攻信号降一级处理。")
        if held:
            return ("HOLD" if score >= 68 else "WATCH"), reasons
        return "WATCH", reasons

    if overextended and score >= 72:
        reasons.append("价格位于上轨附近/上轨外，趋势可能强但追价赔率下降。")
        return ("HOLD" if held else "WATCH"), reasons

    if valuation == "偏高" and score < 88:
        reasons.append("估值偏高，技术强势不等于中长线赔率足够。")
        return ("HOLD" if held else "WATCH"), reasons

    if score >= 82 and (weekly_score or 0) >= 72 and daily_score >= 72:
        if held:
            if position_level == "重仓(>20%)":
                return "HOLD", ["趋势与动能共振，但当前已是重仓，优先控制集中度。"]
            return "ADD_CANDIDATE", ["周线环境、日线趋势与动能形成共振。"]
        return "BUILD_CANDIDATE", ["周线环境、日线趋势与动能形成共振。"]

    if score >= 68:
        return ("HOLD" if held else "WATCH"), ["趋势尚可，但没有达到高质量新增仓位门槛。"]

    if score >= 50:
        return "WATCH", ["处于修复/震荡区，等待方向确认。"]

    if held:
        return "REDUCE", ["趋势与动能评分偏弱，风险收益比恶化。"]
    return "AVOID", ["趋势与动能评分偏弱。"]

def parse_num(v):
    if v is None: return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",",""))
    if not m: return None
    try: return float(m.group())
    except: return None

def risk_position_reference(daily, risk_budget_pct, max_single_pct):
    price = parse_num(daily.get("price"))
    inv = parse_num(daily.get("invalidation_price"))
    if not price or not inv or inv <= 0 or inv >= price:
        return None
    stop_pct = (price-inv)/price
    if stop_pct <= 0:
        return None
    raw = (risk_budget_pct/100)/stop_pct*100
    cap = min(raw, max_single_pct)
    return {
        "price":price,
        "invalidation":inv,
        "stop_pct":stop_pct*100,
        "raw_pct":raw,
        "cap_pct":cap,
    }

def evidence_rows(daily, weekly):
    rows = [
        ["日线","BOLL中轨",daily.get("mid_direction"),daily.get("boll_mid","")],
        ["日线","价格位置",daily.get("price_vs_mid"),daily.get("price","")],
        ["日线","MACD零轴",daily.get("zero_zone"),daily.get("cross")],
        ["日线","DIF方向",daily.get("dif_direction"),daily.get("dif","")],
        ["日线","柱体",daily.get("bar_momentum"),daily.get("macd_bar","")],
        ["日线","成交量",daily.get("volume_state"),""],
        ["日线","背离",daily.get("divergence"),""],
    ]
    if weekly.get("visible"):
        rows += [
            ["周线","BOLL中轨",weekly.get("mid_direction"),weekly.get("boll_mid","")],
            ["周线","价格位置",weekly.get("price_vs_mid"),weekly.get("price","")],
            ["周线","MACD零轴",weekly.get("zero_zone"),weekly.get("cross")],
            ["周线","DIF方向",weekly.get("dif_direction"),weekly.get("dif","")],
            ["周线","柱体",weekly.get("bar_momentum"),weekly.get("macd_bar","")],
            ["周线","成交量",weekly.get("volume_state"),""],
            ["周线","背离",weekly.get("divergence"),""],
        ]
    return rows

def _strategy_curve(df, fee_bps=10, boll_n=20, fast=12, slow=26, signal=9):
    cols = {c.lower():c for c in df.columns}
    if "close" not in cols:
        raise ValueError("CSV 至少需要 Close 列。")
    date_col = cols.get("date") or cols.get("datetime")
    x = df.copy()
    if date_col:
        x[date_col] = pd.to_datetime(x[date_col], errors="coerce")
        x = x.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
    close = pd.to_numeric(x[cols["close"]], errors="coerce")
    x = x.loc[close.notna()].copy()
    close = pd.to_numeric(x[cols["close"]], errors="coerce")
    if len(close) < max(boll_n,slow,signal)+5:
        raise ValueError("数据太少，至少需要约60个交易日。")

    mid = close.rolling(boll_n).mean()
    mid_up = mid.diff() > 0
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    dif = ema_f - ema_s
    dea = dif.ewm(span=signal, adjust=False).mean()

    entry = (close > mid) & mid_up & (dif > dea) & (dif > 0)
    exit_sig = (close < mid) | (dif < dea)

    state = 0
    pos = []
    for en, ex in zip(entry.fillna(False), exit_sig.fillna(False)):
        if state == 0 and en:
            state = 1
        elif state == 1 and ex:
            state = 0
        pos.append(state)
    pos = pd.Series(pos, index=x.index, dtype=float)

    ret = close.pct_change().fillna(0)
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * (fee_bps/10000)
    strat = pos.shift(1).fillna(0)*ret - cost
    equity = (1+strat).cumprod()
    bench = (1+ret).cumprod()

    changes = pos.diff().fillna(pos)
    entries = list(x.index[changes==1])
    exits = list(x.index[changes==-1])
    trades = []
    for en in entries:
        exs = [e for e in exits if e > en]
        ex = exs[0] if exs else x.index[-1]
        trades.append(close.loc[ex]/close.loc[en]-1)

    return x, close, pos, strat, equity, bench, trades

def backtest(df, fee_bps=10, boll_n=20, fast=12, slow=26, signal=9):
    x, close, pos, strat, equity, bench, trades = _strategy_curve(df, fee_bps, boll_n, fast, slow, signal)
    total = equity.iloc[-1]-1
    dd = equity/equity.cummax()-1
    mdd = dd.min()
    if isinstance(x.index, pd.DatetimeIndex) and len(x)>1:
        years = max((x.index[-1]-x.index[0]).days/365.25, 1/365.25)
        cagr = equity.iloc[-1]**(1/years)-1
    else:
        cagr = float("nan")
    win = sum(t>0 for t in trades)/len(trades) if trades else float("nan")
    avg_trade = sum(trades)/len(trades) if trades else float("nan")
    gains = sum(t for t in trades if t>0)
    losses = abs(sum(t for t in trades if t<0))
    profit_factor = gains/losses if losses>0 else float("nan")

    split = int(len(x)*0.70)
    oos = None
    if len(x) >= 120 and split < len(x)-20:
        eq0 = equity.iloc[split-1]
        oos_eq = equity.iloc[split:]/eq0
        oos_dd = oos_eq/oos_eq.cummax()-1
        oos = {
            "return":oos_eq.iloc[-1]-1,
            "max_drawdown":oos_dd.min(),
            "start":x.index[split],
            "end":x.index[-1],
        }

    curve = pd.DataFrame({"策略净值":equity,"买入持有":bench})
    return {
        "total_return":total,
        "cagr":cagr,
        "max_drawdown":mdd,
        "trades":len(trades),
        "win_rate":win,
        "avg_trade":avg_trade,
        "profit_factor":profit_factor,
        "oos":oos,
        "curve":curve,
    }
