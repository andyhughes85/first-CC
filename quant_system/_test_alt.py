"""测试备选数据接口"""
import sys, os
sys.path.insert(0, r'D:\first CC\quant_system')
import akshare as ak

# 尝试Sina来源的指数数据
print("尝试: stock_zh_index_daily (sina)")
try:
    df = ak.stock_zh_index_daily(symbol="sh000300")
    if df is not None and not df.empty:
        print(f"  OK: {len(df)} 条")
        print(f"  列: {list(df.columns)}")
        print(df.tail(3))
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")

# 尝试用个股合成指数数据 (用510300 ETF代表沪深300)
print("\n尝试: 510300 ETF")
try:
    df = ak.stock_zh_a_hist(symbol="510300", period="daily",
                            start_date="20230101", adjust="qfq")
    if df is not None and not df.empty:
        print(f"  OK: {len(df)} 条")
        print(f"  列: {list(df.columns)}")
    else:
        print("  空数据")
except Exception as e:
    print(f"  失败: {e}")

# 检查还有哪些index函数可用
print("\n可用的index函数:")
index_funcs = [x for x in dir(ak) if 'index' in x.lower()]
for f in sorted(index_funcs):
    print(f"  - {f}")
