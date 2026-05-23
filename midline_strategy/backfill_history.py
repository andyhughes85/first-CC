"""全市场A股历史日线批量回填 — 用于回测 (自动断点续传)"""

import json
import os
import time
import socket
import logging
import sqlite3
from datetime import datetime

import pandas as pd

from config import DB_PATH

socket.setdefaulttimeout(30)  # 防止 baostock API 挂死

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ==================== 配置 ====================
START_DATE = "2018-01-01"
END_DATE = "2025-12-31"
BATCH_SAVE = 50            # 每攒够N只写入一次DB
CHECKPOINT_FILE = "backfill_checkpoint.json"
RETRY_TIMES = 3            # 失败重试次数

# ==================== 工具函数 ====================


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_daily (
            code TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            PRIMARY KEY (code, date)
        )
    """)
    return conn


def get_all_codes():
    """从 stock_list 获取全市场股票代码"""
    conn = _get_conn()
    df = pd.read_sql("SELECT code FROM stock_list", conn)
    conn.close()
    codes = df["code"].tolist()
    log.info("股票列表: %d 只", len(codes))
    return codes


# ==================== 加载/保存检查点 ====================


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
            done = set(data.get("done_codes", []))
            log.info("读取检查点: 已完成 %d 只", len(done))
            return done
    return set()


def save_checkpoint(done_codes):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"done_codes": sorted(done_codes), "updated": datetime.now().isoformat()}, f)


# ==================== 拉取单只股票 ====================


def _fetch_one_stock(bs_session, code, start, end):
    """用已有 bs 会话查询单只股票，失败返回 None"""
    bs_code = f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"
    for attempt in range(1, RETRY_TIMES + 1):
        try:
            rs = bs_session.query_history_k_data_plus(
                bs_code, "date,open,high,low,close,volume,amount",
                start_date=start, end_date=end, frequency="d", adjustflag="2",
            )
            if rs.error_code != "0":
                # 会话过期: 重新登录后重试
                if "未登录" in (rs.error_msg or ""):
                    log.info("  ⚡ 会话过期，重新登录...")
                    bs_session.logout()
                    bs_session.login()
                    time.sleep(1)
                    continue  # 不消耗重试次数
                if attempt < RETRY_TIMES:
                    time.sleep(2)
                    continue
                log.warning("  ⚠ %s 失败%d次: %s", code, attempt, rs.error_msg)
                return None
            rows = []
            while rs.next():
                row = rs.get_row_data()
                if row and len(row) >= 7:
                    rows.append(row[:7])
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
            for col in ["open", "high", "low", "close", "volume", "amount"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["code"] = code
            df = df.dropna(subset=["close"])
            return df if not df.empty else None
        except Exception as e:
            if attempt < RETRY_TIMES:
                time.sleep(2)
                continue
            log.warning("  ⚠ %s 异常%d次: %s", code, attempt, e)
            return None
    return None


# ==================== 批量写入DB ====================


def _save_batch(rows):
    """批量写入，自动跳过格式异常的行"""
    if not rows:
        return
    # 逐行校验，确保每行8字段
    valid = [r for r in rows if isinstance(r, (list, tuple)) and len(r) == 8]
    bad = len(rows) - len(valid)
    if bad:
        log.warning("  ⚠ 跳过 %d 条格式异常的行 (首位: %s)", bad, rows[0] if rows else "N/A")
    if not valid:
        return
    conn = _get_conn()
    try:
        conn.executemany("""
            INSERT OR REPLACE INTO stock_daily (code, date, open, high, low, close, volume, amount)
            VALUES (?,?,?,?,?,?,?,?)
        """, valid)
        conn.commit()
    except Exception as e:
        log.error("  ❌ 批量写入失败: %s (首行: %s, len=%d)", e, valid[0], len(valid[0]) if valid else 0)
        # 退化为逐行写入，跳过坏行
        for i, r in enumerate(valid):
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO stock_daily (code, date, open, high, low, close, volume, amount)
                    VALUES (?,?,?,?,?,?,?,?)
                """, r)
            except Exception as e2:
                log.warning("  ⚠ 第%d行写入失败: %s → %s", i, r, e2)
        conn.commit()
    finally:
        conn.close()


# ==================== 主流程 ====================


def run_backfill():
    import baostock as bs

    log.info("=" * 50)
    log.info("历史数据回填开始")
    log.info("区间: %s ~ %s", START_DATE, END_DATE)
    log.info("=" * 50)

    all_codes = get_all_codes()
    done_codes = load_checkpoint()

    pending = [c for c in all_codes if c not in done_codes]
    total = len(pending)
    log.info("待处理: %d 只, 已完成: %d 只", total, len(done_codes))

    if not pending:
        log.info("全部完成，无需处理")
        return

    start_ts = time.time()
    batch_buffer = []
    success_count = 0
    fail_count = 0

    bs.login()
    log.info("baostock 登录成功")
    try:
        for idx, code in enumerate(pending, 1):
            df = _fetch_one_stock(bs, code, START_DATE, END_DATE)
            if df is not None:
                rows = [tuple(row) for row in df[["code", "date", "open", "high", "low", "close", "volume", "amount"]].itertuples(index=False)]
                batch_buffer.extend(rows)
                done_codes.add(code)
                success_count += 1
                elapsed = time.time() - start_ts
                rate = idx / elapsed * 3600 if elapsed > 0 else 0
                log.info("  [%d/%d] ✓ %s (%d 条, %.1f只/时)",
                         idx, total, code, len(df), rate)
            else:
                # 失败也算完成，避免反复重试
                done_codes.add(code)
                fail_count += 1
                log.warning("  [%d/%d] ⚠ %s 跳过", idx, total, code)

            # 批量写入 + 检查点
            if len(batch_buffer) >= BATCH_SAVE * 200 or success_count % BATCH_SAVE == 0:
                pass
            if len(batch_buffer) >= 5000 or success_count % BATCH_SAVE == 0:
                if batch_buffer:
                    _save_batch(batch_buffer)
                    log.info("  写入 %d 条到 DB", len(batch_buffer))
                    batch_buffer = []
                save_checkpoint(done_codes)
                log.info("  检查点: %d 只完成 (失败 %d)", success_count, fail_count)
                elapsed = time.time() - start_ts
                eta = elapsed / max(success_count, 1) * (total - idx) / 3600
                log.info("  已用 %.1f分, 预计剩余 %.1f小时", elapsed / 60, eta)

            time.sleep(0.3)  # 礼貌延迟

    finally:
        bs.logout()
        log.info("baostock 登出")

    # 最后一批写入
    if batch_buffer:
        _save_batch(batch_buffer)
        log.info("最终写入 %d 条到 DB", len(batch_buffer))
    save_checkpoint(done_codes)

    # 统计
    conn = _get_conn()
    total_rows = pd.read_sql(
        f"SELECT COUNT(*) as n FROM stock_daily WHERE date BETWEEN '{START_DATE}' AND '{END_DATE}'", conn
    )["n"][0]
    conn.close()

    total_time = (time.time() - start_ts) / 60
    log.info("=" * 50)
    log.info("回填完成! 成功 %d 只, 失败 %d 只", success_count, fail_count)
    log.info("用时 %.1f 分钟", total_time)
    log.info("%s~%s 区间共 %d 条日线数据", START_DATE, END_DATE, total_rows)
    log.info("=" * 50)


def check_data_status():
    conn = _get_conn()
    tables = [
        ("index_daily", "SELECT COUNT(*), MIN(date), MAX(date) FROM index_daily"),
        ("stock_daily", f"SELECT COUNT(*), MIN(date), MAX(date) FROM stock_daily WHERE date BETWEEN '{START_DATE}' AND '{END_DATE}'"),
    ]
    for name, sql in tables:
        try:
            cnt, dmin, dmax = conn.execute(sql).fetchone()
            print(f"{name}: {cnt} 条, {dmin} ~ {dmax}")
        except Exception:
            print(f"{name}: 无数据或不存在")
    conn.close()
    done = load_checkpoint()
    print(f"检查点: {len(done)} 只已完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        check_data_status()
    else:
        run_backfill()
