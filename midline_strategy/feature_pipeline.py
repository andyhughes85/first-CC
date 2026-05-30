"""特征工程管道 — 统一管理所有技术指标计算

设计原则：
1. 所有特征计算集中于此，回测/线上/LGB 训练共用
2. 每个指标是一个独立函数，用 registry 注册
3. 加入新特征只需加一个函数，无需改多处
4. 保持与 backtest.py 内联计算的独立（两个版本相互验证）
"""

import numpy as np
import pandas as pd

# 特征注册表
_FEATURE_REGISTRY = {}

def register(name):
    def decorator(func):
        _FEATURE_REGISTRY[name] = func
        return func
    return decorator

def get_feature_registry():
    return dict(_FEATURE_REGISTRY)

# ====================================================================
# 基础特征
# ====================================================================

@register("ma")
def calc_ma(df, periods=[5, 10, 20, 60]):
    g = df.copy()
    for p in periods:
        g[f"ma{p}"] = g["close"].rolling(p, min_periods=p).mean()
    return g

@register("volume_ma")
def calc_volume_ma(df, period=20):
    g = df.copy()
    g["vol_ma20"] = g["volume"].rolling(period, min_periods=period).mean()
    return g

@register("atr")
def calc_atr(df, period=14):
    g = df.copy()
    pc = g["close"].shift(1)
    g["tr"] = np.maximum(g["high"]-g["low"], np.maximum(abs(g["high"]-pc), abs(g["low"]-pc)))
    g["atr"] = g["tr"].rolling(period, min_periods=period).mean()
    return g

@register("momentum")
def calc_momentum(df, periods=[5, 20, 60]):
    g = df.copy()
    for p in periods:
        g[f"mom_{p}"] = g["close"] / g["close"].shift(p) - 1
    return g

# ====================================================================
# 形态特征（蔡森三法）
# ====================================================================

@register("caisen")
def calc_caisen(df):
    g = df.copy()
    g["neckline"] = g["low"].rolling(20).min().shift(1)
    g["low_60"] = g["low"].rolling(60).min()
    g["has_bdr"] = (g["close"] > g["neckline"]) & (g["low_60"] < g["neckline"] * 0.97)
    g["resistance"] = g["high"].rolling(20).max().shift(2)
    g["broke_resistance"] = g["close"] > g["resistance"]
    g["back_below"] = g["close"] < g["resistance"]
    g["has_fb"] = g["broke_resistance"].rolling(5).max().fillna(0).astype(bool) & g["back_below"]
    g["low_40"] = g["low"].rolling(40).min()
    g["hi_20"] = g["high"].rolling(20).max().shift(1)
    g["has_w"] = ((g["low_40"]/g["low_60"]-1).abs()<0.03) & (g["close"]>g["hi_20"])
    return g

# ====================================================================
# 技术指标
# ====================================================================

@register("macd")
def calc_macd(df):
    g = df.copy()
    g["ema12"] = g["close"].ewm(span=12).mean()
    g["ema26"] = g["close"].ewm(span=26).mean()
    g["dif"] = g["ema12"] - g["ema26"]
    g["dea"] = g["dif"].ewm(span=9).mean()
    g["macd_bar"] = 2 * (g["dif"] - g["dea"])
    g["macd_diff"] = g["dif"]
    g["macd_dea"] = g["dea"]
    g["divergence_bull"] = (g["macd_bar"].rolling(3).mean() > g["macd_bar"].shift(3).rolling(3).mean())
    return g

@register("rsi")
def calc_rsi(df, period=14):
    g = df.copy()
    d = g["close"].diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    ag = gain.rolling(period).mean()
    al = loss.rolling(period).mean()
    g["rsi"] = 100 - (100 / (1 + ag/al.replace(0,np.nan)))
    return g

@register("bollinger")
def calc_bollinger(df, period=20, n_std=2):
    g = df.copy()
    bm = g["close"].rolling(period).mean()
    bs = g["close"].rolling(period).std()
    g["boll_position"] = (g["close"] - (bm - n_std*bs)) / (4*bs + 1e-10)
    g["boll_width"] = 4*bs / bm.replace(0,np.nan)
    return g

@register("amplitude")
def calc_amplitude(df, period=5):
    g = df.copy()
    g["amplitude_5d"] = g["high"].rolling(period).max() / g["low"].rolling(period).min() - 1
    return g

# ====================================================================
# 量价特征
# ====================================================================

@register("price_pattern")
def calc_price_pattern(df):
    g = df.copy()
    g["ma_distance"] = (g["ma5"] - g["ma20"]) / g["ma20"]
    g["max_dd_20"] = g["close"] / g["close"].rolling(20).max() - 1
    g["high_20"] = g["high"].rolling(20).max().shift(1)
    g["close_position"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-10)
    g["day_range"] = (g["high"] - g["low"]) / g["close"]
    return g

# ====================================================================
# LightGBM 全量特征
# ====================================================================

@register("lgb_features")
def calc_lgb_features(df):
    g = df.copy()
    g["ret_1d"] = g["close"].pct_change(1)
    g["ret_3d"] = g["close"].pct_change(3)
    g["ret_5d"] = g["close"].pct_change(5)
    g["ret_10d"] = g["close"].pct_change(10)
    g["ret_20d"] = g["close"].pct_change(20)
    g["log_ret"] = np.log(g["close"] / g["close"].shift(1))
    g["volatility_5d"] = g["log_ret"].rolling(5).std()
    g["volatility_10d"] = g["log_ret"].rolling(10).std()
    g["volatility_20d"] = g["log_ret"].rolling(20).std()
    g["volume_ma5"] = g["volume"].rolling(5).mean()
    g["volume_ratio"] = g["volume"] / g["volume_ma5"].replace(0,np.nan)
    g["volume_pct"] = g["volume"].pct_change(5)
    for w in [5,10,20]:
        g[f"ma{w}_dist"] = (g["close"] - g[f"ma{w}"]) / g[f"ma{w}"].replace(0,np.nan)
    g["ma5_10_cross"] = np.where(
        (g["ma5"]>g["ma10"]) & (g["ma5"].shift(1)<=g["ma10"].shift(1)), 1,
        np.where((g["ma5"]<g["ma10"]) & (g["ma5"].shift(1)>=g["ma10"].shift(1)), -1, 0))
    g["macd_cross"] = np.where(
        (g["dif"]>g["dea"]) & (g["dif"].shift(1)<=g["dea"].shift(1)), 1,
        np.where((g["dif"]<g["dea"]) & (g["dif"].shift(1)>=g["dea"].shift(1)), -1, 0))
    g["atr_ratio"] = g["atr"] / g["close"]
    g["momentum"] = g["close"].pct_change(5)
    g["sup_res_dist"] = (g["close"] - g["low"].rolling(20).min()) / (g["high"].rolling(20).max() - g["low"].rolling(20).min() + 1e-10)
    return g

# ====================================================================
# 统一构建入口
# ====================================================================

def build_all_features(df, use_kama=False):
    """统一构建全部特征。保持 backtest.py 的内联版本作为对照。"""
    if df.empty:
        return df
    def _all(group):
        g = group.sort_values("date").copy()
        g = calc_ma(g)
        g = calc_volume_ma(g)
        g = calc_atr(g)
        g = calc_momentum(g)
        g = calc_caisen(g)
        g = calc_macd(g)
        g = calc_rsi(g)
        g = calc_bollinger(g)
        g = calc_amplitude(g)
        g = calc_price_pattern(g)
        g = calc_lgb_features(g)
        if use_kama:
            from kama import calc_kama
            from config import KAMA_STOCK_SHORT,KAMA_STOCK_MID,KAMA_STOCK_LONG,KAMA_STOCK_MAIN
            g["ma5"] = calc_kama(g["close"], KAMA_STOCK_SHORT)
            g["ma10"] = calc_kama(g["close"], KAMA_STOCK_MID)
            g["ma20"] = calc_kama(g["close"], KAMA_STOCK_LONG)
            g["ma60"] = calc_kama(g["close"], KAMA_STOCK_MAIN)
            g["ma_distance"] = (g["ma5"]-g["ma20"])/g["ma20"]
        return g
    return (df.set_index("code").groupby(level=0,group_keys=False).apply(_all).reset_index())

def get_lgb_feature_cols():
    return [
        "ret_1d","ret_3d","ret_5d","ret_10d","ret_20d",
        "volatility_5d","volatility_10d","volatility_20d",
        "volume_ratio","volume_pct","rsi",
        "macd_diff","macd_dea","macd_bar",
        "boll_position","boll_width",
        "ma5_dist","ma10_dist","ma20_dist",
        "atr_ratio",
        "day_range","close_position","momentum","sup_res_dist",
    ]

def create_label(df, forward_days=20, threshold=0.08):
    future_ret = df["close"].shift(-forward_days) / df["close"] - 1
    df["label"] = (future_ret > threshold).astype(int)
    df.loc[df.index[-forward_days:], "label"] = np.nan
    return df

# 兼容旧接口
def build_lgb_features(df):
    return build_all_features(df)
