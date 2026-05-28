import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'midline_strategy'))
"""鐢ㄧ紦瀛樻暟鎹繍琛岀瓥鐣ュ苟杈撳嚭淇″彿JSON"""
import json, sys, logging, pandas as pd
from datetime import datetime
from data_fetcher import load_cached, get_stock_list
from market_state import judge_market_state, add_index_indicators
from signal_engine import generate_signals
from pipeline import get_hot_industries

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

index_df = load_cached("index_daily")
if index_df.empty:
    print("NO_DATA")
    sys.exit(0)

index_df = add_index_indicators(index_df)
market_info = judge_market_state(index_df)
hot_industries = get_hot_industries()

stocks_df = load_cached("stock_daily", start=datetime.now().strftime("%Y-%m-%d"))
if stocks_df.empty:
    stocks_df = load_cached("stock_daily", start=None)

stock_list = get_stock_list()
stocks_df = stocks_df.merge(stock_list[["code", "name", "industry"]], on="code", how="left")

signals, filter_stats = generate_signals(stocks_df, hot_industries, market_info["state"])

if signals.empty:
    print("NO_SIGNALS")
    print(market_info["state"])
    print(market_info["pos_limit"])
    print(json.dumps(hot_industries, ensure_ascii=False))
    print(json.dumps(filter_stats))
else:
    print("SIGNALS")
    print(market_info["state"])
    print(market_info["pos_limit"])
    print(json.dumps(hot_industries, ensure_ascii=False))
    print(json.dumps(filter_stats))
    print(signals.to_json(orient="records", force_ascii=False))
