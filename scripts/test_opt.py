import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'midline_strategy'))
"""娴嬭瘯浼樺寲鐗?v3.1"""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

from data_fetcher import (
    get_trading_pool,
    fetch_sina_snapshot,
    update_stock_data_daily,
    fetch_daily_data,
)

# 1. 浜ゆ槗姹?
pool = get_trading_pool()
pool_codes = [c for c, _ in pool]
print(f"浜ゆ槗姹? {len(pool)} 鍙?)

# 2. 鏂版氮蹇収
print("\n=== 鏂版氮蹇収娴嬭瘯 ===")
snap = fetch_sina_snapshot()
print(f"鍏ㄥ競鍦? {len(snap)} 鍙?)
pool_snap = snap[snap["code"].isin(pool_codes)]
print(f"浜ゆ槗姹? {len(pool_snap)} 鍙?)
if not pool_snap.empty:
    print(pool_snap[["code", "name", "close", "volume"]].head(5).to_string())

# 3. 姣忔棩鏇存柊
print("\n=== 姣忔棩鏇存柊娴嬭瘯 ===")
stocks = update_stock_data_daily(pool_codes)
print(f"涓偂鏁版嵁: {len(stocks)} 鏉? {stocks['code'].nunique()} 鍙?)
if "industry" in stocks.columns:
    has_ind = stocks["industry"].str.len().gt(0).sum()
    print(f"鍚涓? {has_ind}/{len(stocks)}")
print(stocks.tail(3).to_string())

# 4. 瀹屾暣娴佺▼
print("\n=== 瀹屾暣娴佺▼ ===")
result = fetch_daily_data()
if result:
    print(f"鎸囨暟: {len(result['index'])} 鏉? 鏈€鏂? {result['index']['date'].max().strftime('%Y-%m-%d')}")
    print(f"涓偂: {len(result['stocks'])} 鏉?)
