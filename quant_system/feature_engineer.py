"""特征工程模块 - 为HMM和LightGBM构建特征"""

import pandas as pd
import numpy as np


def calc_returns(df, windows=[1, 3, 5, 10, 20]):
    """计算收益率特征"""
    for w in windows:
        df[f"ret_{w}d"] = df["close"].pct_change(w)
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    return df


def calc_volatility(df, windows=[5, 10, 20]):
    """计算波动率特征"""
    for w in windows:
        df[f"volatility_{w}d"] = df["log_ret"].rolling(w).std()
    return df


def calc_volume_features(df):
    """计算成交量特征"""
    df["volume_ma5"] = df["volume"].rolling(5).mean()
    df["volume_ma10"] = df["volume"].rolling(10).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma5"]  # 量比
    df["volume_pct"] = df["volume"].pct_change(5)
    return df


def calc_rsi(df, period=14):
    """计算RSI"""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)
    return df


def calc_macd(df, fast=12, slow=26, signal=9):
    """计算MACD"""
    ema_fast = df["close"].ewm(span=fast).mean()
    ema_slow = df["close"].ewm(span=slow).mean()
    df["macd_diff"] = ema_fast - ema_slow
    df["macd_dea"] = df["macd_diff"].ewm(span=signal).mean()
    df["macd_bar"] = 2 * (df["macd_diff"] - df["macd_dea"])
    # MACD金叉/死叉
    df["macd_cross"] = np.where(
        (df["macd_diff"] > df["macd_dea"]) &
        (df["macd_diff"].shift(1) <= df["macd_dea"].shift(1)), 1,
        np.where(
            (df["macd_diff"] < df["macd_dea"]) &
            (df["macd_diff"].shift(1) >= df["macd_dea"].shift(1)), -1, 0
        )
    )
    return df


def calc_bollinger(df, period=20, std=2):
    """计算布林带"""
    df["boll_ma"] = df["close"].rolling(period).mean()
    boll_std = df["close"].rolling(period).std()
    df["boll_upper"] = df["boll_ma"] + std * boll_std
    df["boll_lower"] = df["boll_ma"] - std * boll_std
    df["boll_position"] = (df["close"] - df["boll_lower"]) / (
        df["boll_upper"] - df["boll_lower"]
    ).replace(0, np.nan)
    df["boll_width"] = (df["boll_upper"] - df["boll_lower"]) / df["boll_ma"]
    return df


def calc_ma_features(df, windows=[5, 10, 20, 60]):
    """计算均线特征"""
    for w in windows:
        df[f"ma{w}"] = df["close"].rolling(w).mean()
    # 价格与均线距离
    for w in windows:
        df[f"ma{w}_dist"] = (df["close"] - df[f"ma{w}"]) / df[f"ma{w}"].replace(0, np.nan)
    # 均线交叉信号
    df["ma5_10_cross"] = np.where(
        (df["ma5"] > df["ma10"]) & (df["ma5"].shift(1) <= df["ma10"].shift(1)), 1,
        np.where(
            (df["ma5"] < df["ma10"]) & (df["ma5"].shift(1) >= df["ma10"].shift(1)), -1, 0
        )
    )
    return df


def calc_atr(df, period=14):
    """计算ATR (Average True Range)"""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(period).mean()
    df["atr_ratio"] = df["atr"] / df["close"]
    return df


def calc_price_features(df):
    """计算价格形态特征"""
    # 日内波动
    df["day_range"] = (df["high"] - df["low"]) / df["close"]
    # 收盘位置
    df["close_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"] + 1e-10)
    # 动量
    df["momentum"] = df["close"] / df["close"].shift(5) - 1
    return df


def calc_support_resistance(df, lookback=20):
    """计算支撑阻力位"""
    df["resistance"] = df["high"].rolling(lookback).max()
    df["support"] = df["low"].rolling(lookback).min()
    df["sup_res_dist"] = (df["close"] - df["support"]) / (
        df["resistance"] - df["support"] + 1e-10
    )
    return df


def build_hmm_features(df):
    """构建HMM输入特征（市场状态识别用）"""
    features = pd.DataFrame(index=df.index)
    # 对数收益率
    features["log_return"] = np.log(df["close"] / df["close"].shift(1))
    # 波动率
    features["volatility"] = df["log_ret"].rolling(10).std()
    # 成交量变化
    features["volume_change"] = df["volume"].pct_change(5)
    # 价格位置
    features["price_position"] = (
        df["close"] - df["close"].rolling(20).min()
    ) / (df["close"].rolling(20).max() - df["close"].rolling(20).min() + 1e-10)
    return features.fillna(0)


def build_lgb_features(df):
    """构建LightGBM输入特征"""
    df = df.copy()

    # 按顺序计算所有特征
    df = calc_returns(df)
    df = calc_volatility(df)
    df = calc_volume_features(df)
    df = calc_rsi(df)
    df = calc_macd(df)
    df = calc_bollinger(df)
    df = calc_ma_features(df)
    df = calc_atr(df)
    df = calc_price_features(df)
    df = calc_support_resistance(df)

    # 标签：未来N日收益率
    return df


def get_lgb_feature_cols():
    """LightGBM使用的特征列名"""
    return [
        "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
        "volatility_5d", "volatility_10d", "volatility_20d",
        "volume_ratio", "volume_pct",
        "rsi",
        "macd_diff", "macd_dea", "macd_bar", "macd_cross",
        "boll_position", "boll_width",
        "ma5_dist", "ma10_dist", "ma20_dist",
        "ma5_10_cross",
        "atr_ratio",
        "day_range", "close_position", "momentum",
        "sup_res_dist",
    ]


def create_label(df, forward_days=5, threshold=0.03):
    """创建买入标签：未来N日收益 > 阈值"""
    future_ret = df["close"].shift(-forward_days) / df["close"] - 1
    df["label"] = (future_ret > threshold).astype(int)
    # 最后N行没有未来数据，丢弃
    df.loc[df.index[-forward_days:], "label"] = np.nan
    return df
