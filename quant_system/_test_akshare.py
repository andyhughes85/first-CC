"""测试 akshare 不同接口"""
import sys, os
sys.path.insert(0, r'D:\first CC\quant_system')
import akshare as ak

# 尝试1: 指数历史（新接口）
print("尝试1: index_zh_a_hist")
try:
    df = ak.index_zh_a_hist(symbol="000300", period="daily",
                            start_date="20240101", end_date="20240522")
    if df is not None and not df.empty:
        print(f"  OK: {len(df)} 条")
        print(f"  列: {list(df.columns)}")
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")

# 尝试2: stock_zh_a_hist（个股）
print("\n尝试2: stock_zh_a_hist 000001")
try:
    df = ak.stock_zh_a_hist(symbol="000001", period="daily",
                            start_date="20240101", end_date="20240522", adjust="qfq")
    if df is not None and not df.empty:
        print(f"  OK: {len(df)} 条")
        print(f"  列: {list(df.columns)}")
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")

# 尝试3: 股票列表
print("\n尝试3: stock_info_a_code_name")
try:
    df = ak.stock_info_a_code_name()
    if df is not None and not df.empty:
        print(f"  OK: {len(df)} 只股票")
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")

# 尝试4: 实时行情
print("\n尝试4: stock_zh_a_spot_em")
try:
    df = ak.stock_zh_a_spot_em()
    if df is not None and not df.empty:
        print(f"  OK: {len(df)} 条")
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")
