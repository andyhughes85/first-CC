"""主入口 - A股中线波段买入信号系统"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
from datetime import datetime

from pipeline import DailyPipeline
from stock_scorer import StockScorer
from config import WATCHLIST  # 兼容旧版，实际是全A股扫描


def cmd_today(push=False):
    """运行今日信号"""
    pipeline = DailyPipeline()
    signals, regime = pipeline.run(push=push)
    return signals, regime


def cmd_realtime():
    """快速查看实时行情"""
    from data_fetcher import get_realtime_quote
    df = get_realtime_quote()
    if df.empty:
        print("无法获取实时行情")
        return
    print("\n实时行情（前20只）:")
    cols = [c for c in ["code", "name", "price", "pct", "turnover", "volume_ratio"]
            if c in df.columns]
    print(df[cols].head(20).to_string(index=False))


def cmd_train_lgb():
    """训练LightGBM模型"""
    from data_fetcher import get_all_a_stocks, get_batch_stock_data
    from config import TRAIN_START_DATE

    print("开始获取训练数据...")
    all_stocks = get_all_a_stocks()
    # 取前500只做训练
    train_stocks = [s for s in all_stocks if s.startswith(("0", "3", "6"))][:500]
    stock_data = get_batch_stock_data(train_stocks, start_date=TRAIN_START_DATE)

    print(f"\n开始训练LightGBM...")
    scorer = StockScorer()
    metrics = scorer.train(stock_data)
    if metrics:
        scorer.save()
        print(f"模型已保存到 {os.path.join('models', 'lgb_model.txt')}")
    else:
        print("训练失败")


def cmd_schedule():
    """设置定时任务"""
    print("设置每日定时任务...")
    print(f"  执行时间: 15:10 (盘后)")
    print(f"  使用Windows任务计划程序或 schedule 库")
    print()
    print("  创建 Windows 计划任务:")
    print(f'    schtasks /create /tn "A股买入信号" /tr "py {os.path.abspath("main.py")}" /sc daily /st 15:10')
    print()
    print("  或用 Python schedule 库:")
    print('    pip install schedule')
    print('    然后运行: py main.py --schedule')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A股中线波段买入信号系统")
    parser.add_argument("--today", action="store_true", help="运行今日信号")
    parser.add_argument("--push", action="store_true", help="推送信号到手机")
    parser.add_argument("--realtime", action="store_true", help="查看实时行情")
    parser.add_argument("--train", action="store_true", help="训练LightGBM模型")
    parser.add_argument("--schedule", action="store_true", help="设置定时任务")

    args = parser.parse_args()

    if args.train:
        cmd_train_lgb()
    elif args.realtime:
        cmd_realtime()
    elif args.schedule:
        cmd_schedule()
    elif args.push:
        cmd_today(push=True)
    else:
        cmd_today(push=False)
