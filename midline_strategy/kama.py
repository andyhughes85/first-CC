"""KAMA (Kaufman's Adaptive Moving Average) 自适应移动平均线"""

import numpy as np
import pandas as pd


def calc_kama(series, er_period=10, fast=2, slow=30):
    """
    计算 KAMA 自适应移动平均线

    Args:
        series: 价格序列（Series 或 array）
        er_period: 效率比回看周期
        fast: 快速 EMA 周期（默认 2）
        slow: 慢速 EMA 周期（默认 30）

    Returns:
        KAMA Series（前 er_period-1 个值为 NaN）
    """
    arr = np.asarray(series, dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)

    if n < er_period + 1:
        return pd.Series(out, index=getattr(series, "index", None))

    # 初始值：SMA
    out[er_period - 1] = np.mean(arr[:er_period])

    fastest = 2.0 / (fast + 1)
    slowest = 2.0 / (slow + 1)

    for i in range(er_period, n):
        direction = abs(arr[i] - arr[i - er_period])
        volatility = np.sum(np.abs(np.diff(arr[i - er_period : i + 1])))
        er = direction / volatility if volatility > 0 else 0
        sc = (er * (fastest - slowest) + slowest) ** 2
        out[i] = out[i - 1] + sc * (arr[i] - out[i - 1])

    return pd.Series(out, index=getattr(series, "index", None))


def add_kama_columns(df, price_col="close", periods=None):
    """
    为 DataFrame 添加多周期 KAMA 列

    Args:
        df: 包含价格列的 DataFrame
        price_col: 价格列名
        periods: ER 周期列表，如 [5, 10, 20, 30]
    """
    if periods is None:
        periods = [5, 10, 20, 30]
    price = df[price_col]
    for p in periods:
        df[f"kama_{p}"] = calc_kama(price, er_period=p)
    return df
