"""测试同花顺行业数据"""
import sys, os
sys.path.insert(0, r'D:\first CC\quant_system')
import akshare as ak

print("尝试1: stock_board_industry_name_ths")
try:
    df = ak.stock_board_industry_name_ths()
    if df is not None:
        print(f"  OK: {len(df)} 行业")
        print(f"  列: {list(df.columns)}")
        print(df.head(5))
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")

print("\n尝试2: stock_board_industry_info_ths")
try:
    df = ak.stock_board_industry_info_ths()
    if df is not None:
        print(f"  OK: {len(df)} 条")
        print(f"  列: {list(df.columns)}")
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")
