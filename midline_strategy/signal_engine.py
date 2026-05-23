"""信号生成引擎 — 均线多头 + 放量 + 低偏离"""

import pandas as pd
import numpy as np
from config import (
    STOCK_MA5,
    STOCK_MA10,
    STOCK_MA20,
    STOCK_MA60,
    VOL_RATIO_MIN,
    VOL_RATIO_MAX,
    MAX_DEVIATION,
)


def generate_signals(df, hot_industries=None, market_state="oscillation"):
    """
    生成买入信号，返回 (signals_df, filter_stats)
    filter_stats: 过滤漏斗统计
    """
    if df.empty:
        return pd.DataFrame(), {}

    pool = df.copy()

    def calc_indicators(group):
        group = group.sort_values("date")
        group["ma5"] = group["close"].rolling(
            STOCK_MA5, min_periods=STOCK_MA5
        ).mean()
        group["ma10"] = group["close"].rolling(
            STOCK_MA10, min_periods=STOCK_MA10
        ).mean()
        group["ma20"] = group["close"].rolling(
            STOCK_MA20, min_periods=STOCK_MA20
        ).mean()
        group["ma60"] = group["close"].rolling(
            STOCK_MA60, min_periods=STOCK_MA60
        ).mean()
        group["vol_ma20"] = group["volume"].rolling(20, min_periods=20).mean()
        return group

    pool = (pool.set_index("code")
            .groupby(level=0, group_keys=False)
            .apply(calc_indicators)
            .reset_index())
    pool = pool.dropna(subset=["ma5", "ma10", "ma20", "ma60", "vol_ma20"])

    base_pool = len(pool["code"].unique())
    vol_ratio = pool["volume"] / pool["vol_ma20"]

    # 条件1：均线多头排列
    mask_trend = (
        (pool["ma5"] > pool["ma10"])
        & (pool["ma10"] > pool["ma20"])
        & (pool["ma20"] > pool["ma60"])
        & (pool["close"] > pool["ma10"])
    )
    trend_pool = len(pool[mask_trend]["code"].unique())

    # 条件2：放量（量比1.5~4.0）
    mask_vol = (vol_ratio >= VOL_RATIO_MIN) & (vol_ratio <= VOL_RATIO_MAX)
    vol_fail = len(pool[mask_trend & ~mask_vol]["code"].unique())

    # 条件3：不偏离20日线太远（< 8%）
    deviation = (pool["close"] - pool["ma20"]) / pool["ma20"]
    mask_dev = deviation < MAX_DEVIATION

    final_mask = mask_trend & mask_vol & mask_dev

    # 熊市额外收紧
    bear_filter = 0
    if market_state == "bear":
        bear_mask = vol_ratio > 2.5
        bear_filter = len(pool[final_mask & ~bear_mask]["code"].unique())
        final_mask = final_mask & bear_mask

    signals = pool[final_mask].copy()

    filter_stats = {
        "base_pool": base_pool,
        "after_trend": trend_pool,
        "vol_fail": vol_fail,
        "bear_filter": bear_filter,
    }

    if signals.empty:
        return pd.DataFrame(), filter_stats

    signals["volume_ratio"] = signals["volume"] / signals["vol_ma20"]
    signals["deviation"] = (
        signals["close"] - signals["ma20"]
    ) / signals["ma20"]
    signals["reason"] = "均线多头+放量突破"

    # 评分：综合均线强度 + 量比 + 偏离度
    signals["score"] = (
        (signals["ma5"] / signals["ma60"] - 1) * 100   # 均线斜率
        + signals["volume_ratio"] * 0.5                  # 量比加分
        - abs(signals["deviation"]) * 50                 # 偏离扣分
    )
    filter_stats["max_score"] = float(signals["score"].max())

    cols = ["code", "name", "close", "volume_ratio", "deviation", "score", "reason"]
    if "industry" in signals.columns:
        cols.insert(-1, "industry")
    return signals[cols].sort_values("score", ascending=False), filter_stats
