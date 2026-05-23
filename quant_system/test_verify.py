"""快速验证脚本"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import get_index_hist
from market_state import MarketStateDetector
from industry_selector import IndustrySelector

print("=" * 50)
print("验证市场状态判断")
print("=" * 50)
df = get_index_hist()
if not df.empty:
    print(f"沪深300数据: {len(df)} 条记录")
    print(f"日期范围: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")
    detector = MarketStateDetector(use_hmm=True)
    df = detector.fit(df)
    regime = detector.get_current(df)
    print(f"\n当前市场状态: {regime['state_name']}")
    print(f"概率: {regime['probabilities']}")
    pos = detector.get_position_suggest(regime['state_label'])
    print(f"仓位建议: {pos['position']} ({pos['desc']})")
    detector.save()
    print("HMM模型已保存")
else:
    print("获取指数数据失败")

print("\n" + "=" * 50)
print("验证行业动量筛选")
print("=" * 50)
ind = IndustrySelector()
top = ind.update()
if top:
    print(f"\n强势行业 Top {len(top)}:")
    for x in top:
        print(f"  - {x}")
else:
    print("行业数据获取失败（可能需要网络连接）")

print("\n验证完成!")
