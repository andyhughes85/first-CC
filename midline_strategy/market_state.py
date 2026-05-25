"""市场状态判断模块 — 趋势 + ATR波动率 + 成交额热度"""

import pandas as pd
import numpy as np
from config import MARKET_MA_SHORT, MARKET_MA_LONG, ATR_PERIOD, VOL_MA_PERIOD


def add_index_indicators(df):
    """为指数数据添加技术指标（SMA）"""
    df = df.sort_values("date").reset_index(drop=True)
    df["ma_s"] = df["close"].rolling(MARKET_MA_SHORT).mean()
    df["ma_l"] = df["close"].rolling(MARKET_MA_LONG).mean()

    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )
    df["atr"] = df["tr"].rolling(ATR_PERIOD).mean()
    df["atr_pct"] = df["atr"] / df["close"]
    df["amt_ma20"] = df["amount"].rolling(VOL_MA_PERIOD).mean()
    return df


def judge_market_state(index_df):
    """
    判断市场状态（V3 原始分类器：成交额分位判断活跃度，不依赖MA20斜率）

    Returns:
        dict: {
            "state": 'bull' | 'oscillation' | 'bear' | 'wait',
            "pos_limit": float,
            "index_close": float,
            "index_pct": float,
            "atr_rank": float,
            "amt_rank": float,
            "trend_detail": str,
        }
    """
    if len(index_df) < MARKET_MA_LONG:
        return {
            "state": "wait",
            "pos_limit": 0.0,
            "index_close": 0,
            "index_pct": 0,
            "atr_rank": 0,
            "amt_rank": 0,
            "trend_detail": "数据不足",
        }

    row = index_df.iloc[-1]
    prev = index_df.iloc[-2] if len(index_df) >= 2 else row
    trend = row["ma_s"] > row["ma_l"]

    lookback = min(len(index_df), 244)
    atr_series = index_df["atr_pct"].iloc[-lookback:]
    atr_rank = float(atr_series.rank(pct=True).iloc[-1])
    high_vol = atr_rank > 0.70

    amt_series = index_df["amt_ma20"].iloc[-lookback:]
    amt_rank = float(amt_series.rank(pct=True).iloc[-1])
    is_active = amt_rank > 0.60

    index_close = float(row["close"])
    index_pct = float((row["close"] - prev["close"]) / prev["close"])

    trend_detail = (
        f"MA20({row['ma_s']:.0f}){'↑' if trend else '↓'}MA60({row['ma_l']:.0f}), "
        f"波动率分位{atr_rank:.0%}, 成交额分位{amt_rank:.0%}"
    )

    # 牛市：趋势向上 + 成交额活跃 + 非高波
    if trend and is_active and not high_vol:
        state, pos_limit = "bull", 0.8
    # 熊市：趋势向下 + 高波
    elif not trend and high_vol:
        state, pos_limit = "bear", 0.2
    else:
        state, pos_limit = "oscillation", 0.4

    return {
        "state": state,
        "pos_limit": pos_limit,
        "index_close": index_close,
        "index_pct": index_pct,
        "atr_rank": atr_rank,
        "amt_rank": amt_rank,
        "trend_detail": trend_detail,
    }
