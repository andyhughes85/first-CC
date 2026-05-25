"""特征工程 — 为 LightGBM 构建技术面特征"""

import numpy as np
import pandas as pd


def build_lgb_features(df):
    """对单只股票的完整历史计算全部 LightGBM 特征（向量化）"""
    g = df.copy()

    # 收益率
    g["ret_1d"] = g["close"].pct_change(1)
    g["ret_3d"] = g["close"].pct_change(3)
    g["ret_5d"] = g["close"].pct_change(5)
    g["ret_10d"] = g["close"].pct_change(10)
    g["ret_20d"] = g["close"].pct_change(20)

    # 波动率
    g["log_ret"] = np.log(g["close"] / g["close"].shift(1))
    g["volatility_5d"] = g["log_ret"].rolling(5).std()
    g["volatility_10d"] = g["log_ret"].rolling(10).std()
    g["volatility_20d"] = g["log_ret"].rolling(20).std()

    # 成交量
    g["volume_ma5"] = g["volume"].rolling(5).mean()
    g["volume_ratio"] = g["volume"] / g["volume_ma5"].replace(0, np.nan)
    g["volume_pct"] = g["volume"].pct_change(5)

    # RSI
    delta = g["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    g["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = g["close"].ewm(span=12).mean()
    ema26 = g["close"].ewm(span=26).mean()
    g["macd_diff"] = ema12 - ema26
    g["macd_dea"] = g["macd_diff"].ewm(span=9).mean()
    g["macd_bar"] = 2 * (g["macd_diff"] - g["macd_dea"])
    g["macd_cross"] = np.where(
        (g["macd_diff"] > g["macd_dea"]) & (g["macd_diff"].shift(1) <= g["macd_dea"].shift(1)), 1,
        np.where((g["macd_diff"] < g["macd_dea"]) & (g["macd_diff"].shift(1) >= g["macd_dea"].shift(1)), -1, 0)
    )

    # 布林带
    boll_ma = g["close"].rolling(20).mean()
    boll_std = g["close"].rolling(20).std()
    g["boll_position"] = (g["close"] - (boll_ma - 2 * boll_std)) / (4 * boll_std + 1e-10)
    g["boll_width"] = 4 * boll_std / boll_ma.replace(0, np.nan)

    # 均线
    ma_windows = [5, 10, 20, 60]
    for w in ma_windows:
        g[f"ma{w}"] = g["close"].rolling(w).mean()
    for w in ma_windows:
        g[f"ma{w}_dist"] = (g["close"] - g[f"ma{w}"]) / g[f"ma{w}"].replace(0, np.nan)
    g["ma5_10_cross"] = np.where(
        (g["ma5"] > g["ma10"]) & (g["ma5"].shift(1) <= g["ma10"].shift(1)), 1,
        np.where((g["ma5"] < g["ma10"]) & (g["ma5"].shift(1) >= g["ma10"].shift(1)), -1, 0)
    )

    # ATR
    tr = pd.concat([
        g["high"] - g["low"],
        (g["high"] - g["close"].shift(1)).abs(),
        (g["low"] - g["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    g["atr"] = tr.rolling(14).mean()
    g["atr_ratio"] = g["atr"] / g["close"]

    # 价格形态
    g["day_range"] = (g["high"] - g["low"]) / g["close"]
    g["close_position"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-10)
    g["momentum"] = g["close"] / g["close"].shift(5) - 1

    # 支撑阻力
    g["sup_res_dist"] = (g["close"] - g["low"].rolling(20).min()) / \
                        (g["high"].rolling(20).max() - g["low"].rolling(20).min() + 1e-10)

    return g


def get_lgb_feature_cols():
    """LightGBM 输入特征列名"""
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


def create_label(df, forward_days=20, threshold=0.08):
    """创建标签: 未来 forward_days 日收益 > threshold 视为正样本"""
    future_ret = df["close"].shift(-forward_days) / df["close"] - 1
    df["label"] = (future_ret > threshold).astype(int)
    df.loc[df.index[-forward_days:], "label"] = np.nan
    return df


def add_meta_label(sig_df, stock_df, forward_days=20, threshold=0.02):
    """元标注标签: 对信号事件标注是否盈利（向量化版本）

    sig_df:  信号事件 DataFrame, 必须有 code 和 date 列
    stock_df: 全量股票日线数据, 必须有 code, date, close 列
    """
    # 每只股票计算 forward_days 后的收盘价
    tmp = stock_df[["code", "date", "close"]].copy()
    tmp["fwd_close"] = tmp.groupby("code")["close"].transform(lambda x: x.shift(-forward_days))
    tmp["forward_ret"] = tmp["fwd_close"] / tmp["close"] - 1

    sig = sig_df.merge(tmp[["code", "date", "forward_ret"]], on=["code", "date"], how="left")
    sig["meta_label"] = (sig["forward_ret"] > threshold).astype(int)
    sig["meta_label"] = sig["meta_label"].where(sig["forward_ret"].notna(), np.nan)
    return sig


def triple_barrier_meta_label(sig_df, stock_df, upper_pct=0.10, lower_pct=0.07, max_days=15):
    """三柱法元标注 — 匹配实际交易规则

    对每个信号事件模拟持仓，判断哪个障碍先触达：
      - 上界 (+upper_pct): 止盈 → label=1（盈利交易）
      - 下界 (-lower_pct): 止损 → label=0
      - 垂直界 (max_days 日): 时间止损 → label=0

    sig_df:   信号事件 DataFrame, 必须有 code, date, close 列
    stock_df: 全量日线数据, 必须有 code, date, high, low, close 列
    upper_pct: 止盈幅度（默认 0.10 = +10%）
    lower_pct: 止损幅度（默认 0.07 = -7%）
    max_days:  最长持仓天数（默认 15 日）
    """
    tmp = stock_df[["code", "date", "high", "low", "close"]].copy()
    sig = sig_df.copy()

    def _label_one_stock(ss, pp):
        pp = pp.sort_values("date").reset_index(drop=True)
        date_idx = pd.Series(pp.index, index=pp["date"])
        sig_indices = ss["date"].map(date_idx)

        labels = []
        for i, idx in enumerate(sig_indices):
            if pd.isna(idx):
                labels.append(np.nan)
                continue
            idx = int(idx)
            entry = ss.iloc[i]["close"]
            upper = entry * (1 + upper_pct)
            lower = entry * (1 - lower_pct)

            future = pp.iloc[idx + 1: idx + 1 + max_days]
            if len(future) == 0:
                labels.append(np.nan)
                continue

            hit_upper = (future["high"] >= upper)
            hit_lower = (future["low"] <= lower)

            if hit_upper.any() and not hit_lower.any():
                labels.append(1)
            elif hit_lower.any() and not hit_upper.any():
                labels.append(0)
            elif hit_upper.any() and hit_lower.any():
                first_up = hit_upper.idxmax()
                first_lo = hit_lower.idxmax()
                labels.append(1 if first_up <= first_lo else 0)
            else:
                labels.append(0)

        return labels

    result_parts = []
    for code, sigs in sig.groupby("code", sort=False):
        pp = tmp[tmp["code"] == code]
        if pp.empty:
            continue
        labels = _label_one_stock(sigs.reset_index(drop=True), pp)
        sigs_part = sigs.copy()
        sigs_part["triple_barrier_label"] = labels
        result_parts.append(sigs_part)

    if not result_parts:
        sig["triple_barrier_label"] = np.nan
        return sig

    final = pd.concat(result_parts, ignore_index=True)
    return final
