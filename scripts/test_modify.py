"""测试修改后的代码"""
from data_fetcher import refresh_trading_pool, get_trading_pool
from config import SCHEDULE_TIME, SCHEDULE_RETRY_TIME

print("=== 测试1: refresh_trading_pool() 全市场A股 ===")
pool = refresh_trading_pool()
print(f"全市场股票数量: {len(pool)}")
print(pool.head().to_string())
print()

print("=== 测试2: get_trading_pool() 缓存读取 ===")
pool2 = get_trading_pool()
print(f"缓存读取数量: {len(pool2)}")
print()

print("=== 测试3: 定时配置 ===")
print(f"SCHEDULE_TIME = {SCHEDULE_TIME}")
print(f"SCHEDULE_RETRY_TIME = {SCHEDULE_RETRY_TIME}")
