"""LightGBM模型 - 生成个股买入信号"""

import os
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from config import (
    LGB_PARAMS, N_ESTIMATORS, EARLY_STOPPING_ROUNDS,
    TRAIN_SPLIT_RATIO, MIN_SIGNAL_PROB, MODELS_DIR,
)


class LightGBMBuySignal:
    """LightGBM买入信号模型"""

    def __init__(self, model_path=None):
        self.model = None
        self.feature_cols = None
        self.threshold = MIN_SIGNAL_PROB

    def train(self, df, feature_cols):
        """训练LightGBM模型"""
        self.feature_cols = feature_cols

        # 过滤缺失值
        data = df.dropna(subset=feature_cols + ["label"])

        X = data[feature_cols].values
        y = data["label"].values

        # 检查正负样本
        pos_count = y.sum()
        neg_count = len(y) - pos_count
        print(f"  样本分布 - 正样本(买入): {pos_count}, 负样本: {neg_count}")
        if pos_count < 10:
            print("  警告：正样本太少，模型可能不可靠")

        # 划分训练集和验证集
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=1 - TRAIN_SPLIT_RATIO,
            random_state=42, stratify=y
        )

        # 创建LightGBM数据集
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        # 训练
        self.model = lgb.train(
            LGB_PARAMS,
            train_data,
            valid_sets=[train_data, val_data],
            num_boost_round=N_ESTIMATORS,
            callbacks=[
                lgb.early_stopping(early_stopping_rounds=EARLY_STOPPING_ROUNDS),
                lgb.log_evaluation(0),
            ],
        )

        # 验证
        y_pred = (self.model.predict(X_val) > self.threshold).astype(int)
        y_prob = self.model.predict(X_val)

        metrics = {
            "accuracy": float(accuracy_score(y_val, y_pred)),
            "precision": float(precision_score(y_val, y_pred, zero_division=0)),
            "recall": float(recall_score(y_val, y_pred, zero_division=0)),
            "auc": float(roc_auc_score(y_val, y_prob)),
        }
        print(f"  验证集指标: {metrics}")

        return metrics

    def predict(self, df):
        """预测买入概率"""
        if self.model is None or self.feature_cols is None:
            raise ValueError("模型尚未训练或加载")

        data = df[self.feature_cols].fillna(0)
        proba = self.model.predict(data.values)
        return proba

    def get_buy_signals(self, df, hmm_regime=None):
        """获取买入信号，可选基于HMM状态过滤"""
        proba = self.predict(df)

        signals = df[["date", "close", "volume"]].copy()
        signals["buy_prob"] = proba
        signals["signal"] = (proba >= self.threshold).astype(int)

        # 如果提供了HMM状态，合并
        if hmm_regime is not None:
            signals["hmm_regime"] = hmm_regime

        # 只在最后一个交易日产生信号
        last_signal = signals.iloc[-1:].copy()
        last_signal["signal_date"] = pd.Timestamp.today().strftime("%Y-%m-%d")

        return last_signal

    def predict_batch(self, stock_data_dict, feature_cols, hmm_state=None):
        """批量预测多个股票的买入信号"""
        results = []
        for symbol, df in stock_data_dict.items():
            df_with_features = df.copy()
            if hmm_state is not None:
                df_with_features["hmm_state"] = hmm_state

            # 确保特征列存在
            missing = [c for c in feature_cols if c not in df_with_features.columns]
            if missing:
                continue

            proba = self.predict(df_with_features)
            last_proba = proba[-1]

            row = df_with_features.iloc[-1]
            results.append({
                "symbol": symbol,
                "date": row.get("date", pd.Timestamp.today()),
                "close": row.get("close", 0),
                "buy_prob": round(float(last_proba), 4),
                "signal": 1 if last_proba >= self.threshold else 0,
                "pct_change": row.get("pct_change", 0),
                "volume": row.get("volume", 0),
                "turnover": row.get("turnover", 0),
            })

        return pd.DataFrame(results)

    def get_feature_importance(self, top_n=20):
        """获取特征重要性"""
        if self.model is None or self.feature_cols is None:
            return pd.DataFrame()
        importance = self.model.feature_importance(importance_type="gain")
        feat_imp = pd.DataFrame({
            "feature": self.feature_cols,
            "importance": importance,
        }).sort_values("importance", ascending=False)
        return feat_imp.head(top_n)

    def save(self, path=None):
        """保存模型"""
        path = path or os.path.join(MODELS_DIR, "lgb_model.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if self.model:
            self.model.save_model(path)
            # 保存特征列名和阈值
            meta_path = path.replace(".txt", "_meta.pkl")
            joblib.dump({
                "feature_cols": self.feature_cols,
                "threshold": self.threshold,
            }, meta_path)

    def load(self, path=None):
        """加载模型"""
        path = path or os.path.join(MODELS_DIR, "lgb_model.txt")
        if os.path.exists(path):
            self.model = lgb.Booster(model_file=path)
            meta_path = path.replace(".txt", "_meta.pkl")
            if os.path.exists(meta_path):
                meta = joblib.load(meta_path)
                self.feature_cols = meta.get("feature_cols")
                self.threshold = meta.get("threshold", MIN_SIGNAL_PROB)
