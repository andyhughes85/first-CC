"""benchmark market state precomputation"""
import time, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'midline_strategy'))
from data_fetcher import load_cached
from market_state import add_index_indicators, judge_market_state
import pandas as pd

idx = load_cached("index_daily", start="2017-07-01", end="2025-12-31")
idx = add_index_indicators(idx).sort_values("date").reset_index(drop=True)
idx["date"] = pd.to_datetime(idx["date"])
print(f"index: {len(idx)} rows")

t0 = time.time()
for i in range(len(idx)):
    lookback = min(i + 1, 500)
    tmp = idx.iloc[i + 1 - lookback: i + 1]
    if len(tmp) >= 60:
        _ = judge_market_state(tmp)
    if (i+1) % 200 == 0:
        print(f"  progress: {i+1}/{len(idx)}, {time.time()-t0:.1f}s")

print(f"market states: {len(idx)} iterations, {time.time()-t0:.1f}s")
