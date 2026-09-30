import os
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0))
_SESSION.mount("http://", HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0))

BASE_URL = (os.getenv("IFIND_BASE_URL") or "https://quantapi.51ifind.com").rstrip("/")
REFRESH_TOKEN = (os.getenv("IFIND_REFRESH_TOKEN") or "").strip()
STATIC_ACCESS_TOKEN = (os.getenv("IFIND_ACCESS_TOKEN") or "").strip()

_TOKEN_LOCK = threading.RLock()
_ACCESS_TOKEN = ""
_ACCESS_TOKEN_AT = 0.0


def configured():
    return bool(REFRESH_TOKEN or STATIC_ACCESS_TOKEN)


def _to_ifind_code(app_code):
    s = str(app_code or "").strip().lower()
    if s.startswith("sh."):
        return s.split(".", 1)[1] + ".SH"
    if s.startswith("sz."):
        return s.split(".", 1)[1] + ".SZ"
    if s.startswith("hk."):
        return s.split(".", 1)[1].zfill(5) + ".HK"
    if s.upper().endswith((".SH", ".SZ", ".HK")):
        return s.upper()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 6:
        return digits + (".SH" if digits.startswith(("5", "6", "9")) else ".SZ")
    if 1 <= len(digits) <= 5:
        return digits.zfill(5) + ".HK"
    return s.upper()


def _to_app_code(ths_code):
    s = str(ths_code or "").strip().upper()
    if s.endswith(".SH"):
        return "sh." + s[:-3]
    if s.endswith(".SZ"):
        return "sz." + s[:-3]
    if s.endswith(".HK"):
        return "hk." + s[:-3].zfill(5)
    return s.lower()


def _get_access_token(force=False):
    global _ACCESS_TOKEN, _ACCESS_TOKEN_AT
    if STATIC_ACCESS_TOKEN:
        return STATIC_ACCESS_TOKEN
    if not REFRESH_TOKEN:
        raise RuntimeError("未配置 IFIND_REFRESH_TOKEN")

    with _TOKEN_LOCK:
        # 官方access token有效期7天；本地只缓存6天，提前刷新。
        if not force and _ACCESS_TOKEN and (time.time() - _ACCESS_TOKEN_AT) < 6 * 86400:
            return _ACCESS_TOKEN

        url = BASE_URL + "/api/v1/get_access_token"
        headers = {
            "Content-Type": "application/json",
            "refresh_token": REFRESH_TOKEN,
        }
        last = None
        for attempt in range(2):
            try:
                resp = _SESSION.post(url, headers=headers, timeout=12)
                resp.raise_for_status()
                obj = resp.json()
                token = ((obj.get("data") or {}).get("access_token") or "").strip()
                if not token:
                    raise RuntimeError(
                        f"iFind获取access token失败：{obj.get('errmsg') or obj.get('message') or obj}"
                    )
                _ACCESS_TOKEN = token
                _ACCESS_TOKEN_AT = time.time()
                return token
            except Exception as exc:
                last = exc
                if attempt < 1:
                    time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"iFind获取access token失败：{last}")


def _post(endpoint, payload, timeout=25, retries=2):
    url = BASE_URL + endpoint
    last = None
    for attempt in range(max(1, int(retries))):
        try:
            token = _get_access_token(force=False)
            headers = {
                "Content-Type": "application/json",
                "access_token": token,
                "ifindlang": "cn",
            }
            resp = _SESSION.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in (401, 403):
                _get_access_token(force=True)
                headers["access_token"] = _get_access_token(force=False)
                resp = _SESSION.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            obj = resp.json()
            err = obj.get("errorcode", obj.get("errorCode", 0))
            try:
                err_i = int(err or 0)
            except Exception:
                err_i = 0 if str(err).strip() in ("", "0", "None") else -1
            if err_i != 0:
                raise RuntimeError(
                    f"iFind接口错误 {err_i}：{obj.get('errmsg') or obj.get('message') or '未知错误'}"
                )
            return obj
        except Exception as exc:
            last = exc
            if attempt < max(1, int(retries)) - 1:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(str(last))


def _as_list(v, n=None):
    if isinstance(v, list):
        out = v
    elif isinstance(v, tuple):
        out = list(v)
    elif isinstance(v, np.ndarray):
        out = v.tolist()
    elif isinstance(v, pd.Series):
        out = v.tolist()
    elif v is None:
        out = []
    else:
        out = [v]
    if n is not None:
        if len(out) == 1 and n > 1:
            out = out * n
        elif len(out) < n:
            out = out + [None] * (n - len(out))
        elif len(out) > n:
            out = out[:n]
    return out


def _table_entries(obj):
    tables = obj.get("tables")
    if tables is None:
        data = obj.get("data")
        if isinstance(data, dict) and "tables" in data:
            tables = data.get("tables")
        elif isinstance(data, list):
            tables = data
    if isinstance(tables, dict):
        if "table" in tables or "thscode" in tables:
            tables = [tables]
        else:
            tables = list(tables.values())
    if not isinstance(tables, list):
        return []
    return [x for x in tables if isinstance(x, dict)]


def _history_frames(obj):
    result = {}
    for entry in _table_entries(obj):
        code = entry.get("thscode") or entry.get("code") or entry.get("THSCODE")
        table = entry.get("table") or entry.get("data") or {}
        times = entry.get("time") or entry.get("times") or []

        if isinstance(table, list):
            try:
                frame = pd.DataFrame(table)
            except Exception:
                continue
            if "time" not in frame.columns and times:
                frame["time"] = _as_list(times, len(frame))
        elif isinstance(table, dict):
            lengths = [len(v) for v in table.values() if isinstance(v, (list, tuple, np.ndarray, pd.Series))]
            lengths += [len(times)] if isinstance(times, (list, tuple, np.ndarray, pd.Series)) else []
            n = max(lengths) if lengths else 1
            cols = {k: _as_list(v, n) for k, v in table.items()}
            frame = pd.DataFrame(cols)
            if "time" not in frame.columns:
                frame["time"] = _as_list(times, n)
        else:
            continue

        if not code and "thscode" in frame.columns and not frame.empty:
            code = frame.iloc[0]["thscode"]
        if not code and "code" in frame.columns and not frame.empty:
            code = frame.iloc[0]["code"]
        if not code:
            continue
        result[str(code).upper()] = frame
    return result


def history_many(app_codes, start, end, interval="D", cps=2):
    if not configured():
        raise RuntimeError("iFind未配置")
    app_codes = [str(x) for x in app_codes if str(x).strip()]
    if not app_codes:
        return {}

    ths_codes = [_to_ifind_code(x) for x in app_codes]
    payload = {
        "codes": ",".join(ths_codes),
        "indicators": "open,high,low,close,volume,amount,changeRatio,turnoverRatio",
        "startdate": str(start),
        "enddate": str(end),
        "functionpara": {
            "Interval": str(interval).upper(),
            "CPS": int(cps),
            "Fill": "Omit",
            "Currency": "YSHB",
        },
    }
    timeout = 20 if len(app_codes) <= 3 else 30
    obj = _post("/api/v1/cmd_history_quotation", payload, timeout=timeout, retries=2)
    raw = _history_frames(obj)
    out = {}

    for app_code, ths_code in zip(app_codes, ths_codes):
        df = raw.get(ths_code.upper())
        if df is None or df.empty:
            continue
        d = df.copy()
        rename = {
            "time": "trade_date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "vol",
            "amount": "amount",
            "changeRatio": "pctChg",
            "turnoverRatio": "turn",
        }
        d = d.rename(columns={k: v for k, v in rename.items() if k in d.columns})
        if "trade_date" not in d.columns:
            continue
        for col in ["open", "high", "low", "close", "vol", "amount", "pctChg", "turn"]:
            if col not in d.columns:
                d[col] = np.nan
            d[col] = pd.to_numeric(d[col], errors="coerce")
        d["trade_date"] = pd.to_datetime(d["trade_date"], errors="coerce")
        d["code"] = str(app_code)
        d["tradestatus"] = "1"
        d["isST"] = ""
        cols = [
            "trade_date", "code", "open", "high", "low", "close", "vol",
            "amount", "pctChg", "turn", "tradestatus", "isST"
        ]
        d = d[cols].dropna(subset=["trade_date", "close"]).sort_values("trade_date")
        out[str(app_code)] = d.reset_index(drop=True)
    return out


def history_one(app_code, start, end, interval="D", cps=2):
    data = history_many([app_code], start, end, interval=interval, cps=cps)
    return data.get(str(app_code), pd.DataFrame())



def basic_names(app_codes):
    """Return {app_code: short_name} using iFinD basic-data service."""
    if not configured():
        return {}
    app_codes=[str(x) for x in app_codes if str(x).strip()]
    if not app_codes:
        return {}
    ths_codes=[_to_ifind_code(x) for x in app_codes]
    payload={
        "codes": ",".join(ths_codes),
        "indipara": [{"indicator":"ths_stock_short_name_stock"}],
    }
    obj=_post("/api/v1/basic_data_service",payload,timeout=12,retries=2)
    entries=_table_entries(obj)
    by_ths={}
    for entry in entries:
        code=str(entry.get("thscode") or entry.get("code") or entry.get("THSCODE") or "").upper()
        table=entry.get("table") or entry.get("data") or {}
        name=None
        if isinstance(table,dict):
            for key in ["ths_stock_short_name_stock","stock_short_name","name"]:
                if key in table:
                    vals=_as_list(table.get(key))
                    if vals:
                        name=vals[0]
                        break
            if name is None:
                for v in table.values():
                    vals=_as_list(v)
                    if vals and isinstance(vals[0],str):
                        name=vals[0]
                        break
        elif isinstance(table,list) and table:
            first=table[0]
            if isinstance(first,dict):
                name=first.get("ths_stock_short_name_stock") or first.get("name")
        if code and name is not None and str(name).strip():
            by_ths[code]=str(name).strip()
    out={}
    for app_code,ths_code in zip(app_codes,ths_codes):
        name=by_ths.get(ths_code.upper())
        if name:
            out[str(app_code)]=name
    return out



def _flatten_generic_response(obj):
    """Best-effort conversion of iFinD HTTP table/data responses to one DataFrame."""
    frames=[]
    for entry in _table_entries(obj):
        code=entry.get("thscode") or entry.get("code") or entry.get("THSCODE")
        table=entry.get("table") or entry.get("data") or {}
        if isinstance(table,dict):
            lengths=[
                len(v) for v in table.values()
                if isinstance(v,(list,tuple,np.ndarray,pd.Series))
            ]
            n=max(lengths) if lengths else 1
            frame=pd.DataFrame({k:_as_list(v,n) for k,v in table.items()})
        elif isinstance(table,list):
            try:
                frame=pd.DataFrame(table)
            except Exception:
                continue
        else:
            continue
        if code and "thscode" not in [str(x).lower() for x in frame.columns]:
            frame["thscode"]=str(code)
        if not frame.empty:
            frames.append(frame)

    if frames:
        return pd.concat(frames,ignore_index=True,sort=False)

    data=obj.get("data")
    if isinstance(data,list):
        try:
            return pd.json_normalize(data)
        except Exception:
            pass
    if isinstance(data,dict):
        # Some HTTP functions return {column:[...], ...}.
        try:
            lengths=[
                len(v) for v in data.values()
                if isinstance(v,(list,tuple,np.ndarray,pd.Series))
            ]
            n=max(lengths) if lengths else 1
            return pd.DataFrame({k:_as_list(v,n) for k,v in data.items()})
        except Exception:
            pass

    # WCQuery may expose thscode/indicators/data at top level.
    codes=obj.get("thscode")
    raw=obj.get("data")
    if codes is not None and raw is not None:
        try:
            frame=pd.DataFrame(raw)
            code_list=_as_list(codes,len(frame))
            if len(code_list)==len(frame):
                frame["thscode"]=code_list
            return frame
        except Exception:
            pass
    return pd.DataFrame()


def smart_stock_picking(query):
    """Run one iFinD/WenCai stock query and return a normalized DataFrame."""
    if not configured():
        raise RuntimeError("iFind未配置")
    payload={"searchstring":str(query),"searchtype":"stock"}
    obj=_post("/api/v1/smart_stock_picking",payload,timeout=35,retries=2)
    return _flatten_generic_response(obj)


def basic_data_many(app_codes, indicator_specs):
    """
    Generic iFinD basic-data request.
    indicator_specs: [{"indicator":"...", "indiparams":[...]}]
    """
    if not configured():
        raise RuntimeError("iFind未配置")
    app_codes=[str(x) for x in app_codes if str(x).strip()]
    if not app_codes:
        return pd.DataFrame()
    ths_codes=[_to_ifind_code(x) for x in app_codes]
    payload={"codes":",".join(ths_codes),"indipara":indicator_specs}
    obj=_post("/api/v1/basic_data_service",payload,timeout=25,retries=2)
    return _flatten_generic_response(obj)

def status(test_data=False):
    if not configured():
        return {"configured": False, "ok": False, "message": "未配置 IFIND_REFRESH_TOKEN"}
    try:
        _get_access_token(force=False)
        if test_data:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
            df = history_one("sh.600000", start, end, interval="D", cps=2)
            if df.empty:
                return {"configured": True, "ok": False, "message": "iFind鉴权成功，但测试行情为空"}
        return {"configured": True, "ok": True, "message": "iFind HTTP API 已连接"}
    except Exception as exc:
        return {"configured": True, "ok": False, "message": str(exc)}
