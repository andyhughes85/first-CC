"""LightGBM 训练脚本 — 支持主模型和元标注两种模式"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime

from data_fetcher import load_cached
from config import STOCK_MA5, STOCK_MA10, STOCK_MA20, STOCK_MA60, VOL_RATIO_MIN, VOL_RATIO_MAX, MAX_DEVIATION
from lgb_features import build_lgb_features, create_label, get_lgb_feature_cols, add_meta_label, triple_barrier_meta_label
from lgb_model import LightGBMModel, FORWARD_DAYS, BUY_THRESHOLD

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_SCRIPT_DIR, "models")
TRAIN_START = "2018-01-01"
TRAIN_END = "2024-12-31"


def load_training_data():
    print("加载训练数据...")
    stocks = load_cached("stock_daily", start=TRAIN_START, end=TRAIN_END)
    if stocks.empty:
        raise ValueError("个股数据为空")

    stock_list = load_cached("stock_list")
    if not stock_list.empty:
        stocks = stocks.merge(stock_list[["code", "name", "industry"]], on="code", how="left")

    stocks["date"] = pd.to_datetime(stocks["date"])
    stocks = stocks.sort_values(["code", "date"]).reset_index(drop=True)

    min_days = 500
    counts = stocks["code"].value_counts()
    valid = counts[counts >= min_days].index
    stocks = stocks[stocks["code"].isin(valid)]
    print(f"  有效股票: {len(valid)} 只 ({len(stocks)} 行)")
    return stocks


def compute_signals(stocks_df):
    """计算信号（与 backtest._precompute_signals 一致）"""
    df = stocks_df.copy()

    def _calc(group):
        g = group.sort_values("date")
        g["ma5"] = g["close"].rolling(STOCK_MA5, min_periods=STOCK_MA5).mean()
        g["ma10"] = g["close"].rolling(STOCK_MA10, min_periods=STOCK_MA10).mean()
        g["ma20"] = g["close"].rolling(STOCK_MA20, min_periods=STOCK_MA20).mean()
        g["ma60"] = g["close"].rolling(STOCK_MA60, min_periods=STOCK_MA60).mean()
        g["vol_ma20"] = g["volume"].rolling(20, min_periods=20).mean()
        prev_close = g["close"].shift(1)
        g["tr"] = np.maximum(
            g["high"] - g["low"],
            np.maximum(abs(g["high"] - prev_close), abs(g["low"] - prev_close))
        )
        g["atr"] = g["tr"].rolling(14, min_periods=14).mean()
        g["mom_20"] = g["close"] / g["close"].shift(20) - 1
        g["mom_60"] = g["close"] / g["close"].shift(60) - 1
        g["neckline"] = g["low"].rolling(20).min().shift(1)
        g["low_60"] = g["low"].rolling(60).min()
        g["has_bdr"] = ((g["close"] > g["neckline"]) & (g["low_60"] < g["neckline"] * 0.97))
        g["resistance"] = g["high"].rolling(20).max().shift(2)
        g["broke_resistance"] = g["close"] > g["resistance"]
        g["back_below"] = g["close"] < g["resistance"]
        g["has_fb"] = g["broke_resistance"].rolling(5).max().fillna(0).astype(bool) & g["back_below"]
        g["low_40"] = g["low"].rolling(40).min()
        g["hi_20"] = g["high"].rolling(20).max().shift(1)
        g["has_w"] = ((g["low_40"] / g["low_60"] - 1).abs() < 0.03) & (g["close"] > g["hi_20"])
        g["ma_distance"] = (g["ma5"] - g["ma20"]) / g["ma20"]
        g["max_dd_20"] = g["close"] / g["close"].rolling(20).max() - 1
        g["ema12"] = g["close"].ewm(span=12).mean()
        g["ema26"] = g["close"].ewm(span=26).mean()
        g["dif"] = g["ema12"] - g["ema26"]
        g["dea"] = g["dif"].ewm(span=9).mean()
        g["macd_bar"] = 2 * (g["dif"] - g["dea"])
        g["divergence_bull"] = (g["macd_bar"].rolling(3).mean() > g["macd_bar"].shift(3).rolling(3).mean())
        g["high_20"] = g["high"].rolling(20).max().shift(1)
        # LGB 特征
        g["ret_1d"] = g["close"].pct_change(1)
        g["ret_3d"] = g["close"].pct_change(3)
        g["ret_5d"] = g["close"].pct_change(5)
        g["ret_10d"] = g["close"].pct_change(10)
        g["ret_20d"] = g["close"].pct_change(20)
        g["log_ret"] = np.log(g["close"] / g["close"].shift(1))
        g["volatility_5d"] = g["log_ret"].rolling(5).std()
        g["volatility_10d"] = g["log_ret"].rolling(10).std()
        g["volatility_20d"] = g["log_ret"].rolling(20).std()
        g["volume_pct"] = g["volume"].pct_change(5)
        _d = g["close"].diff()
        _gain = _d.clip(lower=0); _loss = -_d.clip(upper=0)
        _ag = _gain.rolling(14).mean(); _al = _loss.rolling(14).mean()
        g["rsi"] = 100 - (100 / (1 + _ag / _al.replace(0, np.nan)))
        g["macd_cross"] = np.where(
            (g["dif"] > g["dea"]) & (g["dif"].shift(1) <= g["dea"].shift(1)), 1,
            np.where((g["dif"] < g["dea"]) & (g["dif"].shift(1) >= g["dea"].shift(1)), -1, 0))
        _bm = g["close"].rolling(20).mean(); _bs = g["close"].rolling(20).std()
        g["boll_position"] = (g["close"] - (_bm - 2 * _bs)) / (4 * _bs + 1e-10)
        g["boll_width"] = 4 * _bs / _bm.replace(0, np.nan)
        g["ma5_dist"] = (g["close"] - g["ma5"]) / g["ma5"].replace(0, np.nan)
        g["ma10_dist"] = (g["close"] - g["ma10"]) / g["ma10"].replace(0, np.nan)
        g["ma20_dist"] = g["ma_distance"].copy()
        g["ma5_10_cross"] = np.where(
            (g["ma5"] > g["ma10"]) & (g["ma5"].shift(1) <= g["ma10"].shift(1)), 1,
            np.where((g["ma5"] < g["ma10"]) & (g["ma5"].shift(1) >= g["ma10"].shift(1)), -1, 0))
        g["atr_ratio"] = g["atr"] / g["close"]
        g["day_range"] = (g["high"] - g["low"]) / g["close"]
        g["close_position"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-10)
        g["momentum"] = g["close"].pct_change(5)
        g["sup_res_dist"] = (g["close"] - g["low"].rolling(20).min()) / \
                            (g["high"].rolling(20).max() - g["low"].rolling(20).min() + 1e-10)
        g["macd_diff"] = g["dif"]; g["macd_dea"] = g["dea"]
        g["volume_ratio"] = g["volume"] / g["volume"].rolling(5).mean().replace(0, np.nan)
        return g

    df = (df.set_index("code").groupby(level=0, group_keys=False).apply(_calc).reset_index())
    df = df.dropna(subset=["ma5", "ma10", "ma20", "ma60", "vol_ma20", "atr", "mom_20", "mom_60",
                           "ma_distance", "max_dd_20"])

    mask_trend = (df["ma5"] > df["ma10"]) & (df["ma10"] > df["ma20"]) & (df["close"] > df["ma20"])
    mask_dev = (df["close"] - df["ma20"]) / df["ma20"] < MAX_DEVIATION
    mask_yang = df["close"] > df["open"]
    df["signal_base"] = mask_trend & mask_dev & mask_yang

    return df[df["signal_base"]].copy()


def train_primary():
    """主模型训练：全市场预测 forward_20d_return > 8%"""
    print("=" * 60)
    print("模式: 主模型（全市场二分类）")
    print(f"预测窗口: {FORWARD_DAYS}日 | 阈值: {BUY_THRESHOLD:.0%}")
    print("=" * 60)

    os.makedirs(MODEL_DIR, exist_ok=True)

    stocks = load_training_data()
    print("\n[2/3] 构建特征和标签...")
    train_df = build_training_dataset(stocks)
    print(f"  训练集: {len(train_df)} 行, {train_df['code'].nunique()} 只股票")
    print(f"  正样本率: {train_df['label'].mean():.2%}")

    print("\n[3/3] 训练 LightGBM...")
    feature_cols = get_lgb_feature_cols()
    model = LightGBMModel()
    metrics = model.train(train_df, feature_cols)

    importance = model.get_feature_importance(15)
    print("\n  特征重要性 Top 15:")
    for _, r in importance.iterrows():
        print(f"    {r['feature']:20s}: {r['importance']:.2f}")

    model_path = os.path.join(MODEL_DIR, "lgb_midline.txt")
    model.save(model_path)
    print(f"\n模型已保存: {model_path}")

    print("\n" + "=" * 60)
    print(f"AUC:       {metrics.get('auc', 0):.4f}")
    print(f"Precision: {metrics.get('precision', 0):.4f}")
    print(f"Recall:    {metrics.get('recall', 0):.4f}")
    print(f"Accuracy:  {metrics.get('accuracy', 0):.4f}")
    print("=" * 60)
    return True


def build_training_dataset(stocks, max_stocks=None):
    """对每只股票构建特征和标签"""
    feature_cols = get_lgb_feature_cols()
    all_rows = []

    codes = stocks["code"].unique()
    if max_stocks:
        codes = codes[:max_stocks]

    for i, code in enumerate(codes):
        if (i + 1) % 200 == 0:
            print(f"  特征构建: {i+1}/{len(codes)}")
        hist = stocks[stocks["code"] == code].sort_values("date").copy()
        if len(hist) < 80:
            continue
        try:
            df = build_lgb_features(hist)
            df = create_label(df, FORWARD_DAYS, BUY_THRESHOLD)
            df["code"] = code
            all_rows.append(df)
        except Exception as e:
            print(f"  跳过 {code}: {e}")

    if not all_rows:
        raise ValueError("无可用训练数据")
    train_df = pd.concat(all_rows, ignore_index=True)
    return train_df.dropna(subset=feature_cols + ["label"])


def train_meta():
    """元标注训练：仅在信号触发事件上训练，预测交易是否盈利"""
    print("=" * 60)
    print("模式: 元标注（信号事件二分类）")
    print("标签: forward_20d_return > 2%（交易是否盈利）")
    print("=" * 60)

    os.makedirs(MODEL_DIR, exist_ok=True)
    feature_cols = get_lgb_feature_cols()

    # 1. 加载数据
    print("\n[1/4] 加载训练数据...")
    stocks = load_training_data()

    # 2. 计算信号
    print("\n[2/4] 计算信号事件...")
    sig_df = compute_signals(stocks)
    print(f"  信号事件: {len(sig_df)} 条")

    # 3. 添加元标注标签
    print("\n[3/4] 添加元标注标签...")
    meta_df = add_meta_label(sig_df, stocks, forward_days=20, threshold=0.02)
    meta_df = meta_df.dropna(subset=feature_cols + ["meta_label"])
    print(f"  有效样本: {len(meta_df)} 条")
    print(f"  正样本率: {meta_df['meta_label'].mean():.2%}")

    # 4. 训练
    print("\n[4/4] 训练 LightGBM 元标注模型...")
    meta_df.rename(columns={"meta_label": "label"}, inplace=True)
    model = LightGBMModel()
    metrics = model.train(meta_df, feature_cols)

    importance = model.get_feature_importance(15)
    print("\n  特征重要性 Top 15:")
    for _, r in importance.iterrows():
        print(f"    {r['feature']:20s}: {r['importance']:.2f}")

    model_path = os.path.join(MODEL_DIR, "lgb_meta.txt")
    model.save(model_path)
    print(f"\n模型已保存: {model_path}")

    print("\n" + "=" * 60)
    print(f"AUC:       {metrics.get('auc', 0):.4f}")
    print(f"Precision: {metrics.get('precision', 0):.4f}")
    print(f"Recall:    {metrics.get('recall', 0):.4f}")
    print(f"Accuracy:  {metrics.get('accuracy', 0):.4f}")
    print("=" * 60)
    return True


def train_meta_triple_barrier():
    """三柱法元标注训练 — 使用 Purged K-Fold CV

    标签规则匹配实际交易止盈止损：
      - 上界 +10%（止盈）→ label=1
      - 下界 -7%（止损）→ label=0
      - 15日时间止损 → label=0
    验证方法：Purged K-Fold（防时间泄漏）
    """
    from config import TAKE_PROFIT, STOP_LOSS, TIME_STOP_DAYS

    upper_pct = TAKE_PROFIT          # 0.10
    lower_pct = abs(STOP_LOSS)       # 0.07
    max_days = TIME_STOP_DAYS        # 15

    print("=" * 60)
    print("模式: 三柱法元标注（Purged K-Fold CV）")
    print(f"上界: +{upper_pct:.0%} | 下界: -{lower_pct:.0%} | 垂直界: {max_days}日")
    print("=" * 60)

    os.makedirs(MODEL_DIR, exist_ok=True)
    feature_cols = get_lgb_feature_cols()

    # 1. 加载数据
    print("\n[1/4] 加载训练数据...")
    stocks = load_training_data()

    # 2. 计算信号事件（compute_signals 已包含所有 LGB 特征列）
    print("\n[2/4] 计算信号事件...")
    sig_df = compute_signals(stocks)
    print(f"  信号事件: {len(sig_df)} 条, {sig_df['code'].nunique()} 只股票")

    # 验证特征列是否齐全
    missing_cols = [c for c in feature_cols if c not in sig_df.columns]
    if missing_cols:
        raise ValueError(f"compute_signals 缺少特征: {missing_cols}")

    # 3. 三柱法打标签
    print("\n[3/4] 三柱法标注...")
    meta_df = triple_barrier_meta_label(
        sig_df, stocks, upper_pct=upper_pct, lower_pct=lower_pct, max_days=max_days
    )
    meta_df.rename(columns={"triple_barrier_label": "label"}, inplace=True)
    meta_df = meta_df.dropna(subset=feature_cols + ["label"])
    print(f"  有效样本: {len(meta_df)} 条")
    print(f"  正样本率: {meta_df['label'].mean():.2%}")
    print(f"  时间范围: {meta_df['date'].min()} ~ {meta_df['date'].max()}")

    # 4. Purged K-Fold 训练
    print("\n[4/4] Purged K-Fold 训练...")
    model = LightGBMModel()
    cv_metrics = model.train_purged(
        meta_df, feature_cols, date_col="date",
        max_forward=max_days, n_splits=5, embargo=5,
    )

    # 特征重要性
    importance = model.get_feature_importance(15)
    print("\n  特征重要性 Top 15:")
    for _, r in importance.iterrows():
        print(f"    {r['feature']:20s}: {r['importance']:.2f}")

    model_path = os.path.join(MODEL_DIR, "lgb_meta_triple.txt")
    model.save(model_path)
    print(f"\n模型已保存: {model_path}")

    print("\n" + "=" * 60)
    if model.cv_summary:
        print(f"CV AUC:     {model.cv_summary['auc_mean']:.4f} "
              f"±{model.cv_summary['auc_std']:.4f}")
        print(f"Best Fold:  {model.cv_summary['best_fold']}")
    print(f"N Folds:    {model.cv_summary['n_folds'] if model.cv_summary else 0}")
    print("=" * 60)
    return True


if __name__ == "__main__":
    mode = "primary"
    if "--meta" in sys.argv:
        mode = "meta"
    if "--triple" in sys.argv:
        mode = "triple"

    if mode == "triple":
        train_meta_triple_barrier()
    elif mode == "meta":
        train_meta()
    else:
        train_primary()
