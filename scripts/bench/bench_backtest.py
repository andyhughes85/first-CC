"""benchmark backtest loading"""
import time, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'midline_strategy'))
from data_fetcher import load_cached
from market_state import add_index_indicators

t0 = time.time()
idx = load_cached("index_daily", start="2017-07-01", end="2025-12-31")
print(f"index loaded: {len(idx)} rows, {time.time()-t0:.1f}s")

t0 = time.time()
idx2 = add_index_indicators(idx)
print(f"index indicators: {time.time()-t0:.1f}s")

t0 = time.time()
stocks = load_cached("stock_daily", start="2017-07-01", end="2025-12-31")
print(f"stocks loaded: {len(stocks)} rows, {stocks['code'].nunique()} stocks, {time.time()-t0:.1f}s")

t0 = time.time()
stock_list = load_cached("stock_list")
print(f"stock_list loaded: {len(stock_list)} rows, {time.time()-t0:.1f}s")

# benchmark signal precomputation
import pandas as pd
import numpy as np
from config import STOCK_MA5, STOCK_MA10, STOCK_MA20, STOCK_MA60, VOL_RATIO_MIN, VOL_RATIO_MAX, MAX_DEVIATION

stocks["date"] = pd.to_datetime(stocks["date"])
stocks = stocks.sort_values(["code", "date"])

t0 = time.time()
def _calc(group):
    g = group.sort_values("date")
    g["ma5"] = g["close"].rolling(STOCK_MA5, min_periods=STOCK_MA5).mean()
    g["ma10"] = g["close"].rolling(STOCK_MA10, min_periods=STOCK_MA10).mean()
    g["ma20"] = g["close"].rolling(STOCK_MA20, min_periods=STOCK_MA20).mean()
    g["ma60"] = g["close"].rolling(STOCK_MA60, min_periods=STOCK_MA60).mean()
    g["vol_ma20"] = g["volume"].rolling(20, min_periods=20).mean()
    return g

df = (stocks.set_index("code")
      .groupby(level=0, group_keys=False)
      .apply(_calc)
      .reset_index())
print(f"signals precomputed: {len(df)} rows, {time.time()-t0:.1f}s")
