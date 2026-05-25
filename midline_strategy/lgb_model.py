"""LightGBM 模型包装 — 中线策略筛选"""

import os
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from datetime import timedelta
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


class PurgedKFold:
    """Purged K-Fold Cross Validator (De Prado)

    防止时间泄漏：
    1. Purge: 移除训练集中标签窗口与验证集重叠的样本
    2. Embargo: 在训练/验证之间加入禁运缓冲期
    """

    def __init__(self, n_splits=5, embargo=5):
        self.n_splits = n_splits
        self.embargo = embargo

    def split(self, df, date_col="date", max_forward=15):
        """生成经过净化的训练/验证索引

        df: DataFrame，必须包含 date_col 列
        max_forward: 标签最大前视天数（如三柱法的 max_days）
        """
        sorted_df = df.sort_values(date_col).reset_index(drop=True)
        sorted_df["_date_rank"] = sorted_df[date_col].rank(method="dense")
        max_rank = sorted_df["_date_rank"].max()

        fold_edges = np.linspace(0, max_rank, self.n_splits + 1, dtype=int)

        for i in range(self.n_splits):
            val_start_rank = fold_edges[i]
            val_end_rank = fold_edges[i + 1] - 1
            if val_end_rank < val_start_rank:
                continue

            val_mask = (sorted_df["_date_rank"] >= val_start_rank) & \
                       (sorted_df["_date_rank"] <= val_end_rank)

            # Purge: 训练样本的标签窗口不得与验证集重叠
            # 一个信号在日期 T 发出，标签窗口为 [T, T + max_forward)
            # 须满足 T + max_forward + embargo < val_start
            purge_cutoff_rank = val_start_rank - max_forward - self.embargo
            train_mask = sorted_df["_date_rank"] <= purge_cutoff_rank

            train_idx = sorted_df.index[train_mask].values
            val_idx = sorted_df.index[val_mask].values

            if len(train_idx) < 10 or len(val_idx) < 10:
                continue

            yield train_idx, val_idx


class LightGBMModel:
    """中线策略 LightGBM 筛选模型"""

    def __init__(self, model_path=None):
        self.model = None
        self.feature_cols = None
        self.cv_metrics = None
        self.cv_summary = None

    def train(self, df, feature_cols):
        """普通训练（无净化交叉验证，保留向后兼容）"""
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

    def train_purged(self, df, feature_cols, date_col="date", max_forward=15,
                      n_splits=5, embargo=5):
        """Purged K-Fold 交叉验证训练（Meta-Labeling 推荐）

        df: DataFrame, 必须有 date_col 列和 label 列
        feature_cols: 特征列名列表
        max_forward: 标签最大前视天数
        n_splits: 折数
        embargo: 禁运期天数
        """
        self.feature_cols = feature_cols
        data = df.dropna(subset=feature_cols + ["label"]).copy()
        data = data.sort_values(date_col).reset_index(drop=True)

        X = data[feature_cols].values
        y = data["label"].values

        pos = y.sum()
        neg = len(y) - pos
        print(f"  样本分布: 正={pos} ({pos/len(y):.1%}), 负={neg}")

        pkf = PurgedKFold(n_splits=n_splits, embargo=embargo)

        cv_metrics = []
        models = []

        for fold, (train_idx, val_idx) in enumerate(pkf.split(data, date_col, max_forward)):
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            train_data = lgb.Dataset(X_train, label=y_train)
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

            fold_model = lgb.train(
                LGB_PARAMS, train_data,
                valid_sets=[train_data, val_data],
                num_boost_round=N_ESTIMATORS,
                callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS), lgb.log_evaluation(0)],
            )

            y_prob = fold_model.predict(X_val)
            y_pred = (y_prob > 0.5).astype(int)
            metrics = {
                "fold": fold,
                "n_train": len(y_train),
                "n_val": len(y_val),
                "pos_rate": float(y_val.mean()),
                "accuracy": float(accuracy_score(y_val, y_pred)),
                "precision": float(precision_score(y_val, y_pred, zero_division=0)),
                "recall": float(recall_score(y_val, y_pred, zero_division=0)),
                "auc": float(roc_auc_score(y_val, y_prob)),
            }
            cv_metrics.append(metrics)
            models.append(fold_model)
            print(f"  Fold {fold}: AUC={metrics['auc']:.4f} "
                  f"Prec={metrics['precision']:.3f} Rec={metrics['recall']:.3f} "
                  f"n_train={metrics['n_train']} n_val={metrics['n_val']}")

        if not cv_metrics:
            raise ValueError("PurgedKFold 未生成有效的训练/验证划分")

        # 选 AUC 最高的折的模型
        best_idx = int(np.argmax([m["auc"] for m in cv_metrics]))
        self.model = models[best_idx]
        self.cv_metrics = pd.DataFrame(cv_metrics)
        self.cv_summary = {
            "auc_mean": float(np.mean([m["auc"] for m in cv_metrics])),
            "auc_std": float(np.std([m["auc"] for m in cv_metrics])),
            "best_fold": int(best_idx),
            "n_folds": len(cv_metrics),
        }

        print(f"\n  CV Summary: AUC={self.cv_summary['auc_mean']:.4f} "
              f"±{self.cv_summary['auc_std']:.4f}")
        return self.cv_metrics

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
