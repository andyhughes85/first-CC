"""信号生成引擎 — V3 单通道（SMA，反转为主）"""

import pandas as pd
import numpy as np
from config import (
    VOL_RATIO_MIN,
    VOL_RATIO_MAX,
    MAX_DEVIATION,
    VOL_RATIO_MIN_BULL,
    VOL_RATIO_MIN_OSC,
    AMPLITUDE_5D_MIN,
)


def _calc_score(df):
    """统一评分公式"""
    return (
        (df["ma5"] / df["ma60"] - 1) * 100
        + df["volume_ratio"] * 0.5
        - abs(df["deviation"]) * 50
        + df["mom_20"] * 100
        + df["mom_60"] * 50
        + df["has_bdr"] * 10
        - df["has_fb"] * 10
        + df["has_w"] * 10
        + df["ma_distance"] * 100
        - df["max_dd_20"] * 50
    )


def generate_signals(df, hot_industries=None, market_state="oscillation"):
    if df.empty:
        return pd.DataFrame(), {}

    pool = df.copy()

    def calc_indicators(group):
        group = group.sort_values("date")
        group["ma5"] = group["close"].rolling(5, min_periods=5).mean()
        group["ma10"] = group["close"].rolling(10, min_periods=10).mean()
        group["ma20"] = group["close"].rolling(20, min_periods=20).mean()
        group["ma60"] = group["close"].rolling(60, min_periods=60).mean()
        group["vol_ma20"] = group["volume"].rolling(20, min_periods=20).mean()

        group["mom_20"] = group["close"] / group["close"].shift(20) - 1
        group["mom_60"] = group["close"] / group["close"].shift(60) - 1

        group["ema12"] = group["close"].ewm(span=12).mean()
        group["ema26"] = group["close"].ewm(span=26).mean()
        group["dif"] = group["ema12"] - group["ema26"]
        group["dea"] = group["dif"].ewm(span=9).mean()
        group["macd_bar"] = 2 * (group["dif"] - group["dea"])
        group["divergence_bull"] = (
            group["macd_bar"].rolling(3).mean()
            > group["macd_bar"].shift(3).rolling(3).mean()
        )

        group["neckline"] = group["low"].rolling(20).min().shift(1)
        group["low_60"] = group["low"].rolling(60).min()
        group["has_bdr"] = (
            (group["close"] > group["neckline"])
            & (group["low_60"] < group["neckline"] * 0.97)
        )

        group["resistance"] = group["high"].rolling(20).max().shift(2)
        group["broke_resistance"] = group["close"] > group["resistance"]
        group["back_below"] = group["close"] < group["resistance"]
        group["has_fb"] = (
            group["broke_resistance"].rolling(5).max().fillna(0).astype(bool)
            & group["back_below"]
        )

        group["low_40"] = group["low"].rolling(40).min()
        group["hi_20"] = group["high"].rolling(20).max().shift(1)
        group["has_w"] = (
            ((group["low_40"] / group["low_60"] - 1).abs() < 0.03)
            & (group["close"] > group["hi_20"])
        )

        group["ma_distance"] = (group["ma5"] - group["ma20"]) / group["ma20"]
        group["max_dd_20"] = group["close"] / group["close"].rolling(20).max() - 1
        # 5日振幅：过滤窄幅震荡的低质量信号
        group["amplitude_5d"] = (
            group["high"].rolling(5).max() / group["low"].rolling(5).min() - 1
        )
        return group

    pool = (pool.set_index("code")
            .groupby(level=0, group_keys=False)
            .apply(calc_indicators)
            .reset_index())

    required_cols = ["ma5", "ma10", "ma20", "ma60", "vol_ma20",
                     "mom_20", "mom_60", "divergence_bull",
                     "has_bdr", "has_w", "has_fb", "amplitude_5d"]
    pool = pool.dropna(subset=required_cols)

    # 只保留每只股票最新一天数据，避免历史过时价格产生信号
    pool = pool.sort_values("date").groupby("code", as_index=False).tail(1)

    base_pool = len(pool["code"].unique())
    vol_ratio = pool["volume"] / pool["vol_ma20"]
    deviation = (pool["close"] - pool["ma20"]) / pool["ma20"]

    mask_trend = (
        (pool["ma5"] > pool["ma10"])
        & (pool["ma10"] > pool["ma20"])
        & (pool["ma20"] > pool["ma60"])
        & (pool["close"] > pool["ma10"])
    )
    # 趋势评分（从硬过滤改为评分项，不做淘汰）
    trend_score = (
        (pool["ma5"] > pool["ma10"]).astype(int)
        + (pool["ma10"] > pool["ma20"]).astype(int)
        + (pool["ma20"] > pool["ma60"]).astype(int)
        + (pool["close"] > pool["ma10"]).astype(int)
    )  # 0~4分
    mask_dev = deviation < MAX_DEVIATION
    mask_yang = pool["close"] > pool["open"]
    mask_div = pool["divergence_bull"]
    mask_caisen = (pool["has_bdr"] | pool["has_w"]) & ~pool["has_fb"]
    mask_amplitude = pool["amplitude_5d"] >= AMPLITUDE_5D_MIN

    if market_state == "bull":
        mask_vol = (vol_ratio >= VOL_RATIO_MIN_BULL) & (vol_ratio <= VOL_RATIO_MAX)
        final_mask = mask_vol & mask_dev & mask_yang & mask_amplitude
    elif market_state == "bear":
        mask_vol_bear = vol_ratio > 2.5
        final_mask = mask_vol_bear & mask_dev & mask_yang & mask_div & mask_caisen & mask_amplitude
    else:
        mask_vol = (vol_ratio >= VOL_RATIO_MIN_OSC) & (vol_ratio <= VOL_RATIO_MAX)
        final_mask = mask_vol & mask_dev & mask_yang & mask_div & mask_amplitude

    signals = pool[final_mask].copy()
    if signals.empty:
        return pd.DataFrame(), {
            "base_pool": base_pool,
            "after_trend_mean": float(trend_score.mean()) if len(trend_score) > 0 else 0,
            "after_all": 0,
        }

    signals["volume_ratio"] = signals["volume"] / signals["vol_ma20"]
    signals["deviation"] = (signals["close"] - signals["ma20"]) / signals["ma20"]
    signals["reason"] = "反转信号"
    signals["trend_score"] = trend_score.values if hasattr(trend_score, "values") else trend_score
    signals["score"] = _calc_score(signals)

    industry_filter = 0
    if hot_industries and "industry" in signals.columns:
        before = len(signals)
        signals = signals[
            signals["industry"].isin(hot_industries) | signals["industry"].isna()
        ]
        industry_filter = before - len(signals)

    filter_stats = {
        "base_pool": base_pool,
        "after_trend_mean": float(trend_score.mean()) if len(trend_score) > 0 else 0,
        "after_all": len(signals),
        "industry_filter": industry_filter,
        "max_score": float(signals["score"].max()) if not signals.empty else 0,
    }

    cols = ["code", "name", "close", "volume_ratio", "deviation", "score", "reason"]
    if "industry" in signals.columns:
        cols.insert(-1, "industry")
    return signals[cols].sort_values("score", ascending=False), filter_stats
