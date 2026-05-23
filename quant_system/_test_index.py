import sys, os
sys.path.insert(0, r'D:\first CC\quant_system')
from data_fetcher import get_index_hist
df = get_index_hist()
if not df.empty:
    print(f"沪深300 OK: {len(df)} 条")
    print(f"列名: {list(df.columns)}")
    last = df.iloc[-1]
    print(f"最新: {last['date'].date()} 收盘:{last['close']}")
else:
    print("失败")
