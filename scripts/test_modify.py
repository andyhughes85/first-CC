import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'midline_strategy'))
"""娴嬭瘯淇敼鍚庣殑浠ｇ爜"""
from data_fetcher import refresh_trading_pool, get_trading_pool
from config import SCHEDULE_TIME, SCHEDULE_RETRY_TIME

print("=== 娴嬭瘯1: refresh_trading_pool() 鍏ㄥ競鍦篈鑲?===")
pool = refresh_trading_pool()
print(f"鍏ㄥ競鍦鸿偂绁ㄦ暟閲? {len(pool)}")
print(pool.head().to_string())
print()

print("=== 娴嬭瘯2: get_trading_pool() 缂撳瓨璇诲彇 ===")
pool2 = get_trading_pool()
print(f"缂撳瓨璇诲彇鏁伴噺: {len(pool2)}")
print()

print("=== 娴嬭瘯3: 瀹氭椂閰嶇疆 ===")
print(f"SCHEDULE_TIME = {SCHEDULE_TIME}")
print(f"SCHEDULE_RETRY_TIME = {SCHEDULE_RETRY_TIME}")
