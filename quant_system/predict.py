"""每日预测脚本 - 生成实时买入信号"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from config import WATCHLIST, MODELS_DIR
from signal_generator import SignalGenerator


def daily_predict(symbols=None, use_realtime=False):
    """每日预测入口"""
    symbols = symbols or WATCHLIST

    generator = SignalGenerator(watchlist=symbols)

    # 检查模型是否存在
    if not generator.check_trained():
        print("错误：模型未训练，请先运行 train.py")
        print(f"  python {os.path.join(os.path.dirname(__file__), 'train.py')}")
        return

    # 加载模型
    generator.load_models()
    print(f"模型加载成功")

    # 生成信号
    signals_df, regime = generator.generate_signals(
        symbols=symbols, use_realtime=use_realtime
    )

    # 打印报告
    generator.print_signal_report(signals_df, regime)

    return signals_df, regime


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A股买入信号生成")
    parser.add_argument("--symbols", nargs="+", help="指定股票代码列表")
    parser.add_argument("--realtime", action="store_true", help="使用实时行情")
    args = parser.parse_args()

    symbols = args.symbols or WATCHLIST
    daily_predict(symbols=symbols, use_realtime=args.realtime)
