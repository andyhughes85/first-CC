"""LightGBM 股票打分模型"""

import os
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from config import (
    LGB_PARAMS, N_ESTIMATORS, EARLY_STOPPING_ROUNDS,
    TRAIN_SPLIT_RATIO, MODELS_DIR, FORWARD_DAYS, BUY_THRESHOLD,
)


class StockScorer:
    """LightGBM 股票评分模型"""

    def __init__(self):
        self.model = None
        self.feature_cols = None

    def _build_features(self, df):
        """构建个股特征"""
        df = df.copy()
        # 收益率
        for w in [1, 3, 5, 10, 20]:
            df[f"ret_{w}d"] = df["close"].pct_change(w)
        # 波动率
        df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
        for w in [5, 10, 20]:
            df[f"vol_{w}d"] = df["log_ret"].rolling(w).std()
        # 成交量
        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["vol_ma10"] = df["volume"].rolling(10).mean()
        df["vol_ratio"] = df["volume"] / df["vol_ma5"].replace(0, np.nan)
        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_g = gain.rolling(14).mean()
        avg_l = loss.rolling(14).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        df["rsi"] = df["rsi"].fillna(50)
        # MACD
        ema12 = df["close"].ewm(span=12).mean()
        ema26 = df["close"].ewm(span=26).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9).mean()
        df["macd_diff"] = df["macd"] - df["macd_signal"]
        # 布林带
        df["boll_ma"] = df["close"].rolling(20).mean()
        boll_std = df["close"].rolling(20).std()
        df["boll_pos"] = (df["close"] - df["boll_ma"]) / (2 * boll_std + 1e-10)
        # 均线距离
        for p in [5, 10, 20, 60]:
            ma = df["close"].rolling(p).mean()
            df[f"ma{p}_dist"] = (df["close"] - ma) / ma.replace(0, np.nan)
        # ATR
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        df["atr_ratio"] = tr.rolling(14).mean() / df["close"]
        # 标签
        future_ret = df["close"].shift(-FORWARD_DAYS) / df["close"] - 1
        df["label"] = (future_ret > BUY_THRESHOLD).astype(int)
        df.loc[df.index[-FORWARD_DAYS:], "label"] = np.nan

        return df

    @property
    def feature_cols_list(self):
        return [
            "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
            "vol_5d", "vol_10d", "vol_20d",
            "vol_ratio", "rsi", "macd", "macd_diff",
            "boll_pos", "ma5_dist", "ma10_dist", "ma20_dist", "atr_ratio",
        ]

    def train(self, stock_data_dict):
        """使用多只股票的历史数据训练模型"""
        self.feature_cols = self.feature_cols_list
        all_samples = []

        for sym, df in stock_data_dict.items():
            try:
                df_feat = self._build_features(df)
                available = [c for c in self.feature_cols if c in df_feat.columns]
                sample = df_feat.dropna(subset=available + ["label"])
                if len(sample) > 100:
                    sample["symbol"] = sym
                    all_samples.append(sample)
            except Exception as e:
                continue

        if not all_samples:
            print("[LGB] 无训练数据")
            return {}

        train_df = pd.concat(all_samples, ignore_index=True)
        X = train_df[self.feature_cols].values
        y = train_df["label"].values

        pos = y.sum()
        neg = len(y) - pos
        print(f"[LGB] 训练样本: {len(y)}  (正样本:{pos}, 负样本:{neg})")

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=1 - TRAIN_SPLIT_RATIO, random_state=42, stratify=y
        )

        lgb_train = lgb.Dataset(X_train, label=y_train)
        lgb_val = lgb.Dataset(X_val, label=y_val, reference=lgb_train)

        self.model = lgb.train(
            LGB_PARAMS, lgb_train,
            valid_sets=[lgb_val],
            num_boost_round=N_ESTIMATORS,
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS), lgb.log_evaluation(0)],
        )

        y_prob = self.model.predict(X_val)
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y_val, y_prob)
        print(f"[LGB] 验证集 AUC: {auc:.4f}")

        # 特征重要性
        imp = pd.DataFrame({
            "feature": self.feature_cols,
            "importance": self.model.feature_importance(importance_type="gain"),
        }).sort_values("importance", ascending=False)
        print("[LGB] 特征重要性 Top 5:")
        for _, row in imp.head(5).iterrows():
            print(f"       {row['feature']:15s}: {row['importance']:.1f}")

        return {"auc": auc}

    def score(self, df):
        """对个股最新数据打分（0-100）"""
        if self.model is None or self.feature_cols is None:
            return 50

        df_feat = self._build_features(df)
        available = [c for c in self.feature_cols if c in df_feat.columns]
        if not available:
            return 50

        last_row = df_feat[available].iloc[-1:].fillna(0)
        prob = float(self.model.predict(last_row.values)[0])
        return round(prob * 100, 1)

    def save(self):
        path = os.path.join(MODELS_DIR, "lgb_model.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.model.save_model(path)
        joblib.dump({"feature_cols": self.feature_cols},
                     path.replace(".txt", "_meta.pkl"))

    def load(self):
        path = os.path.join(MODELS_DIR, "lgb_model.txt")
        if os.path.exists(path):
            self.model = lgb.Booster(model_file=path)
            meta_path = path.replace(".txt", "_meta.pkl")
            if os.path.exists(meta_path):
                self.feature_cols = joblib.load(meta_path).get("feature_cols")
