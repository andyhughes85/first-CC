"""LightGBM 模型包装 — 中线策略筛选"""

import os
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

LGB_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
    "min_data_in_leaf": 50,
    "is_unbalance": True,
}
N_ESTIMATORS = 200
EARLY_STOPPING_ROUNDS = 50
TRAIN_SPLIT_RATIO = 0.8

# 中线的预测目标
FORWARD_DAYS = 20
BUY_THRESHOLD = 0.08


class LightGBMModel:
    """中线策略 LightGBM 筛选模型"""

    def __init__(self, model_path=None):
        self.model = None
        self.feature_cols = None

    def train(self, df, feature_cols):
        self.feature_cols = feature_cols
        data = df.dropna(subset=feature_cols + ["label"])
        X = data[feature_cols].values
        y = data["label"].values

        pos = y.sum()
        neg = len(y) - pos
        print(f"  样本分布: 正={pos} ({pos/len(y):.1%}), 负={neg}")
        if pos < 10:
            print("  警告: 正样本太少")

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=1 - TRAIN_SPLIT_RATIO, random_state=42, stratify=y
        )

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        self.model = lgb.train(
            LGB_PARAMS, train_data,
            valid_sets=[train_data, val_data],
            num_boost_round=N_ESTIMATORS,
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS), lgb.log_evaluation(0)],
        )

        y_prob = self.model.predict(X_val)
        y_pred = (y_prob > 0.5).astype(int)
        metrics = {
            "accuracy": float(accuracy_score(y_val, y_pred)),
            "precision": float(precision_score(y_val, y_pred, zero_division=0)),
            "recall": float(recall_score(y_val, y_pred, zero_division=0)),
            "auc": float(roc_auc_score(y_val, y_prob)),
        }
        print(f"  验证集: {metrics}")
        return metrics

    def predict(self, df):
        if self.model is None:
            raise ValueError("模型未加载")
        return self.model.predict(df[self.feature_cols].fillna(0).values)

    def get_feature_importance(self, top_n=20):
        if self.model is None or self.feature_cols is None:
            return pd.DataFrame()
        imp = self.model.feature_importance(importance_type="gain")
        return pd.DataFrame({"feature": self.feature_cols, "importance": imp})\
            .sort_values("importance", ascending=False).head(top_n)

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.model.save_model(path)
        joblib.dump({"feature_cols": self.feature_cols},
                     path.replace(".txt", "_meta.pkl"))

    def load(self, path):
        self.model = lgb.Booster(model_file=path)
        meta_path = path.replace(".txt", "_meta.pkl")
        if os.path.exists(meta_path):
            self.feature_cols = joblib.load(meta_path).get("feature_cols")
