"""
批量回填 A 股历史日线数据 — 安全、可断点续传、低内存

流程:
  1. 从 trading_pool 读取股票池
  2. 逐一检查每只股票是否已有目标区间数据
  3. 缺失的用 baostock 拉取，积累 batch 条后批量写入 DB
  4. 每批写入后清内存，避免 OOM

用法:
  python backfill_history.py                               # 默认 2018~2025
  python backfill_history.py --start 2015-01-01 --end 2025-12-31
  python backfill_history.py --batch 50                    # 每 50 只写一次盘
  python backfill_history.py --force                       # 重新拉取（不跳过已有数据）
"""

import argparse
import logging
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

from data_fetcher import get_conn, save_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


def _baostock_fetch(code: str, start: str, end: str) -> pd.DataFrame | None:
    """用 baostock 拉取单只股票日线"""
    import baostock as bs

    bs.login()
    try:
        bs_code = f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag="2",
        )
        rows = []
        while (rs.error_code == "0") and rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return None

        df = pd.DataFrame(
            rows,
            columns=["date", "open", "high", "low", "close", "volume", "amount"],
        )
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df["code"] = code
        return df[["code", "date", "open", "high", "low", "close", "volume", "amount"]]
    finally:
        bs.logout()


def _get_stock_codes() -> list[str]:
    """从 trading_pool 获取股票代码列表"""
    conn = get_conn()
    try:
        df = pd.read_sql("SELECT code FROM trading_pool ORDER BY code", conn)
        return df["code"].tolist()
    finally:
        conn.close()


def _get_stock_range(conn: sqlite3.Connection, code: str, start: str, end: str):
    """查询某只股票在目标区间内已有的日期范围"""
    return conn.execute(
        """SELECT MIN(date), MAX(date), COUNT(*) FROM stock_daily
           WHERE code=? AND date>=? AND date<=?""",
        (code, start, end),
    ).fetchone()


def _estimate_days(start: str, end: str) -> int:
    """粗略估算区间内的交易日数"""
    days = (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days
    return int(days * 250 / 365) + 10


def backfill(start="2018-01-01", end="2025-12-31", batch_size=20, resume=True):
    codes = _get_stock_codes()
    total = len(codes)
    log.info("股票池: %d 只 | 区间: %s ~ %s", total, start, end)

    pending = []
    stats = {"skipped": 0, "fetched": 0, "failed": 0}
    conn = get_conn()

    for idx, code in enumerate(codes, 1):
        if resume:
            min_d, max_d, cnt = _get_stock_range(conn, code, start, end)
            if min_d and max_d and min_d <= start and max_d >= end:
                stats["skipped"] += 1
                if idx % 50 == 0:
                    log.info("[%d/%d] 跳过 %s (已有 %d 天)", idx, total, code, cnt)
                continue

        try:
            df = _baostock_fetch(code, start, end)
            if df is not None and not df.empty:
                pending.append(df)
                stats["fetched"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            stats["failed"] += 1
            log.error("[%d/%d] %s 失败: %s", idx, total, code, e)

        if len(pending) >= batch_size:
            _flush(conn, pending, start, end)
            pending.clear()
            log.info("[%d/%d] checkpoint — 已获取 %d, 跳过 %d, 失败 %d",
                     idx, total, stats["fetched"], stats["skipped"], stats["failed"])

    if pending:
        _flush(conn, pending, start, end)

    conn.close()
    log.info("=" * 50)
    log.info("回填完成! 获取 %d | 跳过 %d | 失败 %d",
             stats["fetched"], stats["skipped"], stats["failed"])
    _summary()


def _flush(conn, pending, start, end):
    df = pd.concat(pending, ignore_index=True)
    mask = (df["date"] >= start) & (df["date"] <= end)
    df = df[mask].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    n_before = pd.read_sql("SELECT COUNT(*) as n FROM stock_daily", conn)["n"][0]
    save_data(df, "stock_daily")
    n_after = pd.read_sql("SELECT COUNT(*) as n FROM stock_daily", conn)["n"][0]
    log.info("  写入 %d 条 (%d 只) → DB: %d → %d (+%d)",
             len(df), df["code"].nunique(), n_before, n_after, n_after - n_before)


def _summary():
    conn = get_conn()
    try:
        r = conn.execute("SELECT COUNT(*), COUNT(DISTINCT code), MIN(date), MAX(date) FROM stock_daily").fetchone()
        log.info("数据库: %d 条, %d 只股票, %s ~ %s", r[0], r[1], r[2], r[3])
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="回填 A 股历史日线数据")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--batch", type=int, default=20, help="每批股票数 (默认 20)")
    parser.add_argument("--force", action="store_true", help="强制重新拉取")
    args = parser.parse_args()

    log.info("启动回填: %s ~ %s | batch=%d | force=%s",
             args.start, args.end, args.batch, args.force)
    backfill(start=args.start, end=args.end, batch_size=args.batch, resume=not args.force)


if __name__ == "__main__":
    main()
