import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from qcloud_cos import CosConfig, CosS3Client
except Exception:
    CosConfig = None
    CosS3Client = None


CORE_TABLES = [
    "analyses",
    "positions",
    "position_snapshots",
    "forward_signals",
    "research_runs",
    "research_members",
    "research_membership",
    "research_stock_results",
    "research_trades",
    "strategy_experiments",
    "strategy_experiment_trades",
    "strategy_candidates",
    "screener_jobs",
    "screener_job_results",
    "screener_settings",
]

EXCLUDED_TABLES = {
    "market_daily_cache",
    "market_cache_meta",
    "ev_cache",
    "extraction_cache",
}

def _env(name, default=""):
    return (os.getenv(name, default) or "").strip()

def configured():
    return bool(
        CosConfig is not None and
        CosS3Client is not None and
        _env("TENCENT_COS_SECRET_ID") and
        _env("TENCENT_COS_SECRET_KEY") and
        _env("TENCENT_COS_REGION") and
        _env("TENCENT_COS_BUCKET")
    )

def _client():
    if not configured():
        raise RuntimeError("腾讯云COS尚未配置完整。")
    cfg=CosConfig(
        Region=_env("TENCENT_COS_REGION"),
        SecretId=_env("TENCENT_COS_SECRET_ID"),
        SecretKey=_env("TENCENT_COS_SECRET_KEY"),
        Scheme="https",
    )
    return CosS3Client(cfg)

def _prefix():
    p=_env("TENCENT_COS_PREFIX","macd-backups").strip("/")
    return p or "macd-backups"

def _device(runtime_mode):
    raw=(runtime_mode or "local").strip().lower()
    return "windows" if raw=="windows" else ("cloud" if raw=="cloud" else "local")

def status():
    if not configured():
        return {"enabled":False,"reason":"COS未配置"}
    try:
        client=_client()
        client.head_bucket(Bucket=_env("TENCENT_COS_BUCKET"))
        return {"enabled":True,"reason":"腾讯云COS已连接"}
    except Exception as e:
        return {"enabled":False,"reason":f"COS连接失败：{e}"}

def _safe_snapshot(src_db_path):
    src_path=Path(src_db_path)
    if not src_path.exists():
        raise RuntimeError(f"本地数据库不存在：{src_path}")

    fd,tmp=tempfile.mkstemp(prefix="macd_core_",suffix=".db")
    os.close(fd)
    try:
        src=sqlite3.connect(str(src_path))
        dst=sqlite3.connect(tmp)
        src.backup(dst)
        dst.commit()
        src.close()

        # 备份仅保留不可重建的核心业务数据；行情、EV和截图缓存不上传。
        dst.execute("PRAGMA journal_mode=DELETE")
        for table in EXCLUDED_TABLES:
            try:
                dst.execute(f'DELETE FROM "{table}"')
            except Exception:
                pass
        dst.commit()
        try:
            dst.execute("VACUUM")
        except Exception:
            pass
        row=dst.execute("PRAGMA integrity_check").fetchone()
        dst.close()
        if not row or str(row[0]).lower()!="ok":
            raise RuntimeError("备份快照完整性检查失败")
        return tmp
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise

def _key(runtime_mode, now=None):
    now=now or datetime.now(timezone.utc)
    stamp=now.strftime("%Y%m%dT%H%M%SZ")
    return f"{_prefix()}/{_device(runtime_mode)}/macd_core_{stamp}.db"

def list_backups(runtime_mode=None, max_keys=100):
    if not configured():
        return []
    client=_client()
    bucket=_env("TENCENT_COS_BUCKET")
    prefix=_prefix()+"/"
    if runtime_mode:
        prefix+=_device(runtime_mode)+"/"
    resp=client.list_objects(
        Bucket=bucket,
        Prefix=prefix,
        MaxKeys=max(1,min(int(max_keys),1000))
    )
    rows=[]
    for item in resp.get("Contents",[]) or []:
        key=str(item.get("Key",""))
        if not key.endswith(".db"):
            continue
        rows.append({
            "key":key,
            "size":int(item.get("Size",0) or 0),
            "last_modified":str(item.get("LastModified","")),
            "device":key.split("/")[-2] if "/" in key else "",
        })
    rows.sort(key=lambda x:x["key"],reverse=True)
    return rows

def prune_backups(runtime_mode, keep=30):
    if not configured():
        return 0
    client=_client()
    bucket=_env("TENCENT_COS_BUCKET")
    rows=list_backups(runtime_mode=runtime_mode,max_keys=500)
    removed=0
    for row in rows[int(keep):]:
        client.delete_object(Bucket=bucket,Key=row["key"])
        removed+=1
    return removed

def backup_now(db_path, runtime_mode, keep=30):
    if not configured():
        raise RuntimeError("请先配置腾讯云COS环境变量。")
    tmp=_safe_snapshot(db_path)
    key=_key(runtime_mode)
    try:
        client=_client()
        client.upload_file(
            Bucket=_env("TENCENT_COS_BUCKET"),
            LocalFilePath=tmp,
            Key=key,
            PartSize=10,
            MAXThread=3,
            EnableMD5=True,
        )
        size=os.path.getsize(tmp)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    removed=prune_backups(runtime_mode,keep=keep)
    return {"key":key,"size":size,"pruned":removed}

def _download_backup(key):
    fd,tmp=tempfile.mkstemp(prefix="macd_restore_",suffix=".db")
    os.close(fd)
    try:
        client=_client()
        client.download_file(
            Bucket=_env("TENCENT_COS_BUCKET"),
            Key=key,
            DestFilePath=tmp,
        )
        conn=sqlite3.connect(tmp)
        row=conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if not row or str(row[0]).lower()!="ok":
            raise RuntimeError("云端备份完整性检查失败")
        return tmp
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise

def _table_exists(conn, table):
    row=conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    return bool(row)

def _columns(conn, table):
    return [str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]

def restore_core(db_path, key):
    if not configured():
        raise RuntimeError("请先配置腾讯云COS环境变量。")
    tmp=_download_backup(key)
    src=None
    dst=None
    restored={}
    try:
        src=sqlite3.connect(tmp)
        dst=sqlite3.connect(str(db_path))
        dst.execute("BEGIN IMMEDIATE")
        for table in CORE_TABLES:
            if not _table_exists(src,table) or not _table_exists(dst,table):
                continue
            src_cols=_columns(src,table)
            dst_cols=_columns(dst,table)
            cols=[c for c in src_cols if c in dst_cols]
            if not cols:
                continue
            col_sql=",".join([f'"{c}"' for c in cols])
            rows=src.execute(f'SELECT {col_sql} FROM "{table}"').fetchall()
            dst.execute(f'DELETE FROM "{table}"')
            if rows:
                q=",".join(["?"]*len(cols))
                dst.executemany(
                    f'INSERT INTO "{table}" ({col_sql}) VALUES ({q})',
                    rows
                )
            restored[table]=len(rows)
        dst.commit()
        check=dst.execute("PRAGMA integrity_check").fetchone()
        if not check or str(check[0]).lower()!="ok":
            raise RuntimeError("恢复后数据库完整性检查失败")
        return restored
    except Exception:
        if dst is not None:
            try: dst.rollback()
            except Exception: pass
        raise
    finally:
        if src is not None:
            src.close()
        if dst is not None:
            dst.close()
        try:
            os.remove(tmp)
        except Exception:
            pass

def maybe_daily_backup(db_path, runtime_mode, keep=30):
    if not configured():
        return {"skipped":True,"reason":"COS未配置"}
    device=_device(runtime_mode)
    today=datetime.now(timezone.utc).strftime("%Y%m%d")
    rows=list_backups(runtime_mode=device,max_keys=5)
    for row in rows:
        name=row["key"].split("/")[-1]
        if name.startswith(f"macd_core_{today}"):
            return {"skipped":True,"reason":"今日已备份","key":row["key"]}
    out=backup_now(db_path,runtime_mode,keep=keep)
    out["skipped"]=False
    return out
