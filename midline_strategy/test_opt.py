"""测试优化版 v3.1"""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

from data_fetcher import (
    get_trading_pool,
    fetch_sina_snapshot,
    update_stock_data_daily,
    fetch_daily_data,
)

# 1. 交易池
pool = get_trading_pool()
pool_codes = [c for c, _ in pool]
print(f"交易池: {len(pool)} 只")

# 2. 新浪快照
print("\n=== 新浪快照测试 ===")
snap = fetch_sina_snapshot()
print(f"全市场: {len(snap)} 只")
pool_snap = snap[snap["code"].isin(pool_codes)]
print(f"交易池: {len(pool_snap)} 只")
if not pool_snap.empty:
    print(pool_snap[["code", "name", "close", "volume"]].head(5).to_string())

# 3. 每日更新
print("\n=== 每日更新测试 ===")
stocks = update_stock_data_daily(pool_codes)
print(f"个股数据: {len(stocks)} 条, {stocks['code'].nunique()} 只")
if "industry" in stocks.columns:
    has_ind = stocks["industry"].str.len().gt(0).sum()
    print(f"含行业: {has_ind}/{len(stocks)}")
print(stocks.tail(3).to_string())

# 4. 完整流程
print("\n=== 完整流程 ===")
result = fetch_daily_data()
if result:
    print(f"指数: {len(result['index'])} 条, 最新: {result['index']['date'].max().strftime('%Y-%m-%d')}")
    print(f"个股: {len(result['stocks'])} 条")
