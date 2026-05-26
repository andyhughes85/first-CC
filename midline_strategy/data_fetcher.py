"""数据获取模块 v3.1 — 含行业 + 增量缓存 + 多源降级 + 交易池缓存"""

import time
import random
import logging
import sqlite3
import threading
import concurrent.futures
from datetime import datetime, timedelta

import pandas as pd
import akshare as ak

from config import DB_PATH, INDEX_CODE, START_DATE, POOL_MIN_AMOUNT
from utils import is_trade_day

# ==================== 全局限流 ====================
REQUEST_COUNTER = {"sina": 0, "baostock": 0, "em": 0}
DAILY_LIMIT = 2000
_REQUEST_LOCK = threading.Lock()


def rate_limited(source):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with _REQUEST_LOCK:
                if REQUEST_COUNTER.get(source, 0) >= DAILY_LIMIT:
                    logging.warning("%s 已达日限(%d)，跳过", source, DAILY_LIMIT)
                    return None
                REQUEST_COUNTER[source] += 1
            time.sleep(random.uniform(0.05, 0.15))
            result = func(*args, **kwargs)
            return result
        return wrapper
    return decorator


def retry_backoff(max_tries=3, base_delay=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_tries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_tries:
                        logging.error("%s 重试%d次失败", func.__name__, max_tries)
                        raise
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logging.warning("%s 第%d次失败，%.1fs重试", func.__name__, attempt, delay)
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


def reset_daily_counters():
    REQUEST_COUNTER.clear()
    REQUEST_COUNTER.update({"sina": 0, "baostock": 0, "em": 0})
    logging.info("日请求计数器已重置")


# ==================== 数据库 ====================

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS index_daily (
            date TEXT PRIMARY KEY,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_daily (
            code TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            PRIMARY KEY (code, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_list (
            code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trading_pool (
            code TEXT PRIMARY KEY,
            name TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_state_history (
            date TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            pos_limit REAL NOT NULL,
            index_close REAL,
            trend_detail TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    return conn


def load_cached(table, code=None, start=None, end=None):
    conn = get_conn()
    query = f"SELECT * FROM {table} WHERE 1=1"
    params = []
    if code:
        query += " AND code=?"
        params.append(code)
    if start:
        query += " AND date>=?"
        params.append(start)
    if end:
        query += " AND date<=?"
        params.append(end)
    if start or end or code:
        query += " ORDER BY date"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], format="mixed")
    return df


def _insert_or_ignore(table, conn, keys, data_iter):
    """INSERT OR IGNORE 避免 UNIQUE 约束冲突"""
    tbl = table.name if hasattr(table, "name") else table
    columns = ", ".join(keys)
    placeholders = ", ".join(["?" for _ in keys])
    sql = f"INSERT OR IGNORE INTO {tbl} ({columns}) VALUES ({placeholders})"
    data = list(data_iter)
    conn.executemany(sql, data)
    return len(data)


def save_data(df, table):
    if df is None or df.empty:
        return
    conn = get_conn()
    try:
        df.to_sql(table, conn, if_exists="append", index=False, method=_insert_or_ignore, chunksize=500)
        conn.commit()
    finally:
        conn.close()


def save_market_state(date, state, pos_limit, index_close, trend_detail):
    """持久化每日市场状态"""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO market_state_history
               (date, state, pos_limit, index_close, trend_detail)
               VALUES (?, ?, ?, ?, ?)""",
            (date, state, pos_limit, index_close, trend_detail),
        )
        conn.commit()
    finally:
        conn.close()


# ==================== 股票列表 & 行业分类 ====================

def update_stock_list():
    """从 Baostock 获取全市场股票列表 + 行业"""
    import baostock as bs
    bs.login()
    try:
        rs = bs.query_stock_basic()
        stocks = []
        while (rs.error_code == "0") and rs.next():
            stocks.append(rs.get_row_data())
        stock_df = pd.DataFrame(stocks, columns=rs.fields)
        stock_df = stock_df[(stock_df["type"] == "1") & (stock_df["status"] == "1")]
        stock_df["code"] = stock_df["code"].str.replace(r"^(sh|sz)\.", "", regex=True)
        code_name = dict(zip(stock_df["code"], stock_df["code_name"]))

        rs2 = bs.query_stock_industry()
        industries = []
        while (rs2.error_code == "0") and rs2.next():
            industries.append(rs2.get_row_data())
        ind_df = pd.DataFrame(industries, columns=rs2.fields)
        ind_df["code"] = ind_df["code"].str.replace(r"^(sh|sz)\.", "", regex=True)

        code_industry = {}
        for _, row in ind_df.iterrows():
            ind = row["industry"]
            if ind:
                code_industry[row["code"]] = ind

        rows = [{"code": c, "name": code_name[c], "industry": code_industry.get(c, "")}
                for c in code_name]
        result = pd.DataFrame(rows)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM stock_list")
        result.to_sql("stock_list", conn, if_exists="append", index=False, method="multi", chunksize=500)
        conn.commit()
        conn.close()
        logging.info("股票列表更新: %d 只 (含行业 %d 只)", len(result),
                     sum(1 for i in code_industry.values() if i))
        return result
    finally:
        bs.logout()


def get_stock_list():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM stock_list", conn)
    conn.close()
    if df.empty:
        df = update_stock_list()
    return df


# ==================== 交易池（沪深300，缓存到数据库）====================

def _clean_pool_df(df, code_col, name_col):
    """清洗交易池DataFrame：提取代码、去ST、去重，保留成交额用于后续过滤"""
    extra_cols = ['成交额'] if '成交额' in df.columns else []
    keep_cols = [code_col, name_col] + extra_cols
    result = df[keep_cols].copy()
    result.rename(columns={code_col: 'code', name_col: 'name'}, inplace=True)
    result['code'] = result['code'].str.extract(r'(\d{6})', expand=False)
    result.dropna(subset=['code'], inplace=True)
    result = result[~result['name'].str.contains('ST', na=False)]
    result.drop_duplicates(subset='code', inplace=True)
    return result


def _save_pool_df(spot_df):
    """将清洗后的交易池写入数据库"""
    conn = get_conn()
    conn.execute("DELETE FROM trading_pool")
    conn.commit()
    spot_df.to_sql('trading_pool', conn, if_exists='append', index=False)
    conn.close()
    logging.info("交易池更新完成，全市场股票数量: %d", len(spot_df))


def _filter_pool_by_amount(spot_df):
    """按成交额过滤交易池，剔除僵尸股/微盘股"""
    if POOL_MIN_AMOUNT <= 0 or '成交额' not in spot_df.columns:
        return spot_df[['code', 'name']]

    spot_df = spot_df.copy()
    spot_df['成交额'] = pd.to_numeric(spot_df['成交额'], errors='coerce').fillna(0)
    before = len(spot_df)
    spot_df = spot_df[spot_df['成交额'] >= POOL_MIN_AMOUNT]
    after = len(spot_df)
    logging.info("交易池成交额过滤(>=%.0f万): %d → %d (剔除 %d 只)",
                 POOL_MIN_AMOUNT / 1e4, before, after, before - after)
    return spot_df[['code', 'name']]


def refresh_trading_pool():
    """多数据源刷新交易池：新浪→东财→降级缓存"""
    logging.info("刷新全市场交易池...")

    # 尝试1：新浪实时快照（含成交额，可过滤僵尸股）
    try:
        spot_df = ak.stock_zh_a_spot()
        spot_df = _clean_pool_df(spot_df, '代码', '名称')
        spot_df = _filter_pool_by_amount(spot_df)
        _save_pool_df(spot_df)
        logging.info("新浪源刷新成功")
        return spot_df
    except Exception as e:
        logging.warning("新浪源失败: %s", e)

    # 尝试2：东财快照（备选，含总市值+成交额）
    try:
        spot_df = ak.stock_zh_a_spot_em()
        spot_df = _clean_pool_df(spot_df, '代码', '名称')
        spot_df = _filter_pool_by_amount(spot_df)
        _save_pool_df(spot_df)
        logging.info("东财源刷新成功")
        return spot_df
    except Exception as e:
        logging.warning("东财源也失败: %s", e)

    # 最终降级：使用缓存
    logging.warning("所有在线源失败，使用缓存交易池")
    return get_trading_pool()


def get_trading_pool():
    """从缓存获取交易池（返回DataFrame）"""
    conn = get_conn()
    df = pd.read_sql("SELECT code, name FROM trading_pool ORDER BY code", conn)
    conn.close()
    if df.empty:
        return refresh_trading_pool()
    return df


# ==================== 指数数据 ====================

@rate_limited("sina")
def _fetch_idx_sina():
    df = ak.stock_zh_index_daily(symbol=f"sh{INDEX_CODE}")
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["volume"] * df["close"] * 100
    return df[["date", "open", "high", "low", "close", "volume", "amount"]]


@retry_backoff(max_tries=2)
@rate_limited("baostock")
def _fetch_idx_baostock(start, end):
    import baostock as bs
    bs.login()
    try:
        rs = bs.query_history_k_data_plus(
            "sh.000300", "date,open,high,low,close,volume,amount",
            start_date=start, end_date=end, frequency="d", adjustflag="3",
        )
        rows = []
        while (rs.error_code == "0") and rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        if (df["amount"] == 0).all():
            df["amount"] = df["volume"] * df["close"]
        return df[["date", "open", "high", "low", "close", "volume", "amount"]]
    finally:
        bs.logout()


@retry_backoff(max_tries=2)
@rate_limited("em")
def _fetch_idx_em():
    """东财指数日线（稳定备源，拉全量后按需裁剪）"""
    df = ak.stock_zh_index_daily_em(symbol=f"sh{INDEX_CODE}")
    df["date"] = pd.to_datetime(df["date"])
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df[["date", "open", "high", "low", "close", "volume", "amount"]]


def fetch_index_incremental():
    today = datetime.now().strftime("%Y-%m-%d")
    cached = load_cached("index_daily")

    if not cached.empty:
        last_date = cached["date"].max().strftime("%Y-%m-%d")
        if last_date >= today:
            logging.info("指数数据已最新(%s)，直接使用缓存", last_date)
            return cached
        start = (datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        logging.info("指数增量拉取: %s ~ %s", start, today)
    else:
        start = datetime.strptime(START_DATE, "%Y%m%d").strftime("%Y-%m-%d")
        logging.info("首次拉取指数: %s ~ %s", start, today)

    for name, fn in [("新浪", _fetch_idx_sina), ("东财", _fetch_idx_em),
                      ("BaoStock", lambda: _fetch_idx_baostock(start, today))]:
        try:
            df = fn()
            if df is not None and not df.empty:
                df = df[(df["date"] >= start) & (df["date"] <= today)]
                if not df.empty:
                    logging.info("%s 成功获取 %d 条指数数据", name, len(df))
                    save_data(df.drop_duplicates(subset=["date"]).sort_values("date"), "index_daily")
                    return pd.concat([cached, df]).drop_duplicates(subset=["date"]).sort_values("date") if not cached.empty else df.sort_values("date")
        except Exception as e:
            logging.warning("%s 指数获取失败: %s", name, e)

    if not cached.empty:
        logging.warning("在线源都失败，使用缓存指数数据")
        return cached
    return None


# ==================== 个股数据 ====================

@rate_limited("sina")
def _fetch_stock_sina(code, start_str, end_str):
    def _code_sina(c):
        return f"sh{c}" if c.startswith(("6", "9")) else f"sz{c}"
    df = ak.stock_zh_a_daily(symbol=_code_sina(code),
                             start_date=start_str, end_date=end_str, adjust="qfq")
    if df is None or df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df["code"] = code
    return df[["code", "date", "open", "high", "low", "close", "volume", "amount"]]


@rate_limited("em")
def _fetch_stock_em(code, start_str, end_str):
    """东财个股日线（稳定备源）"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start_str.replace("-", ""),
                                end_date=end_str.replace("-", ""), adjust="qfq")
        if df is None or df.empty:
            return None
        df["date"] = pd.to_datetime(df["日期"])
        df["code"] = code
        df.rename(columns={"开盘": "open", "收盘": "close", "最高": "high",
                           "最低": "low", "成交量": "volume", "成交额": "amount"}, inplace=True)
        return df[["code", "date", "open", "high", "low", "close", "volume", "amount"]]
    except Exception:
        return None


@retry_backoff(max_tries=2)
@rate_limited("baostock")
def _fetch_stock_bs(code, start_str, end_str):
    import baostock as bs
    bs.login()
    try:
        bs_code = f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"
        rs = bs.query_history_k_data_plus(
            bs_code, "date,open,high,low,close,volume,amount",
            start_date=start_str, end_date=end_str, frequency="d", adjustflag="2",
        )
        rows = []
        while (rs.error_code == "0") and rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df["code"] = code
        return df[["code", "date", "open", "high", "low", "close", "volume", "amount"]]
    finally:
        bs.logout()


def download_stock_history(code, days=60):
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    df = _fetch_stock_sina(code, start_str, end_str)
    if df is None or df.empty:
        df = _fetch_stock_em(code, start_str, end_str)
    if df is None or df.empty:
        df = _fetch_stock_bs(code, start_str, end_str)
    if df is None or df.empty:
        return None
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df[df["date"] >= start_str]


# ==================== 单只股票当日行情 ====================

def download_one_stock_today_sina(code, today):
    """获取单只股票当日行情（轻量，不限流）"""
    try:
        symbol = f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"
        df = ak.stock_zh_a_daily(symbol=symbol, start_date=today, end_date=today, adjust="qfq")
        if df is not None and not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df["code"] = code
            return df[["code", "date", "open", "high", "low", "close", "volume", "amount"]]
    except Exception:
        pass
    return pd.DataFrame()


# ==================== 全市场并行快照 ====================

def fetch_daily_snapshot(max_workers=8):
    """并行获取全市场股票当日日线快照"""
    today = datetime.now().strftime('%Y-%m-%d')
    pool = refresh_trading_pool()
    codes = pool['code'].tolist()
    name_map = dict(zip(pool['code'], pool['name']))

    logging.info("并行获取全市场日线，共 %d 只，并发 %d", len(codes), max_workers)
    all_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(download_one_stock_today_sina, code, today): code
                          for code in codes}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_code)):
            if i % 500 == 0 and i > 0:
                logging.info("快照进度: %d/%d", i, len(codes))
            code = future_to_code[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    df['name'] = name_map.get(code, '')
                    all_data.append(df)
            except Exception as e:
                logging.debug("%s 异常: %s", code, e)
            time.sleep(random.uniform(0.01, 0.03))
    if all_data:
        result = pd.concat(all_data, ignore_index=True)
        logging.info("快照完成，获取 %d 只股票数据", len(result))
        return result
    return pd.DataFrame()


# ==================== 批量回填（仅首次）====================

def _backfill_pool(conn, pool_codes, days=60, workers=3):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    cur = conn.execute("SELECT max(date) FROM stock_daily")
    max_date = cur.fetchone()[0]
    if max_date:
        start = datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)
        if start > datetime.now():
            logging.info("个股历史已最新")
            return
    else:
        start = datetime.now() - timedelta(days=days)

    start_str = start.strftime("%Y-%m-%d")
    n_before = pd.read_sql("SELECT count(*) as n FROM stock_daily", conn)["n"][0]
    total = len(pool_codes)

    def fetch_one(code):
        try:
            df = download_stock_history(code, days)
            if df is not None and not df.empty:
                rows = df[df["date"] >= start_str]
                return rows if not rows.empty else None
        except Exception:
            return None

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, c): c for c in pool_codes}
        for i, f in enumerate(as_completed(futures)):
            if i % 50 == 0:
                logging.info("回填: %d/%d", i, total)
            r = f.result()
            if r is not None:
                results.append(r)

    if results:
        pd.concat(results, ignore_index=True).to_sql("stock_daily", conn, if_exists="append", index=False, method=_insert_or_ignore)
    n_after = pd.read_sql("SELECT count(*) as n FROM stock_daily", conn)["n"][0]
    logging.info("回填完成: %d -> %d条 (+%d)", n_before, n_after, n_after - n_before)


# ==================== 每日个股增量 ====================

def update_stock_data_daily(pool_codes, lookback_days=120, max_workers=5):
    """每日增量更新：检查缓存 → 并发补今日数据 → 合并行业"""
    today = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    conn = get_conn()
    cur = conn.execute("SELECT count(*) FROM stock_daily WHERE date=?", (today,))
    has_today = cur.fetchone()[0] > 0
    conn.close()

    if not has_today:
        saved = 0

        def _fetch_one(code):
            """Sina → 东财 → BaoStock 三源降级"""
            df = _fetch_stock_sina(code, today, today)
            if df is None or df.empty:
                df = _fetch_stock_em(code, today, today)
            if df is None or df.empty:
                df = _fetch_stock_bs(code, today, today)
            return df

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one, code): code for code in pool_codes}
            for future in concurrent.futures.as_completed(futures):
                code = futures[future]
                try:
                    df = future.result()
                    if df is not None and not df.empty:
                        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
                        save_data(df, "stock_daily")
                        saved += 1
                except Exception:
                    pass
        if saved > 0:
            logging.info("增量更新 %d 只股票今日数据（并发%d）", saved, max_workers)

    df_hist = load_cached("stock_daily", start=start_date, end=today)
    stock_list = get_stock_list()
    df_hist = df_hist.merge(stock_list[["code", "name", "industry"]], on="code", how="left")
    logging.info("个股数据: %d 条, %d 只", len(df_hist), df_hist["code"].nunique() if not df_hist.empty else 0)
    return df_hist


# ==================== 主流程 ====================

def fetch_daily_data():
    """获取当日数据"""
    if not is_trade_day():
        logging.info("非交易日，跳过")
        return None

    conn = get_conn()

    # ---- 指数 ----
    index_df = fetch_index_incremental()
    if index_df is None:
        logging.error("指数数据获取失败")
        conn.close()
        return None

    # ---- 交易池 ----
    get_stock_list()  # 确保 stock_list 表存在
    pool = get_trading_pool()
    if pool.empty:
        pool = refresh_trading_pool()
    if pool.empty:
        logging.error("交易池为空，退出")
        conn.close()
        return None

    pool_codes = pool['code'].tolist()

    # ---- 个股 ----
    cur = conn.execute("SELECT max(date) FROM stock_daily")
    latest = cur.fetchone()[0]
    conn.close()

    if latest is None:
        conn2 = get_conn()
        _backfill_pool(conn2, pool_codes, days=60)
        conn2.close()

    stocks_df = update_stock_data_daily(pool_codes)
    logging.info("数据加载完成: 指数%d条, 个股%d条(%d只)",
                 len(index_df), len(stocks_df), stocks_df["code"].nunique() if not stocks_df.empty else 0)
    return {"index": index_df, "stocks": stocks_df}
