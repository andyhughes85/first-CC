"""训练脚本 - 训练HMM和LightGBM模型"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime

from config import (
    WATCHLIST, INDEX_CODE, FORWARD_DAYS, BUY_THRESHOLD, MODELS_DIR,
)
from data_fetcher import get_index_data, get_batch_stock_data
from feature_engineer import (
    build_lgb_features, create_label, get_lgb_feature_cols,
)
from hmm_model import MarketRegimeHMM, add_hmm_feature_to_stock
from lgb_model import LightGBMBuySignal


def train():
    """完整训练流程"""
    print("=" * 60)
    print(f"HMM + LightGBM + CVaR 量化模型训练")
    print(f"训练时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    os.makedirs(MODELS_DIR, exist_ok=True)

    # 1. 获取指数数据 + 训练HMM
    print("\n[1/4] 获取指数数据并训练HMM...")
    index_data = get_index_data(INDEX_CODE)
    if index_data.empty:
        print("错误：无法获取指数数据")
        return False

    print(f"   指数数据: {len(index_data)} 条记录")
    hmm_model = MarketRegimeHMM()
    index_data = hmm_model.fit(index_data)

    # 打印状态统计
    state_counts = index_data["hmm_label"].value_counts()
    for state, count in state_counts.items():
        print(f"   HMM状态 {state}: {count} 天")

    hmm_model.save()
    print("   HMM模型已保存")

    # 2. 获取个股数据
    print(f"\n[2/4] 获取个股数据 ({len(WATCHLIST)} 只)...")
    stock_data = get_batch_stock_data(WATCHLIST)
    print(f"   成功获取: {len(stock_data)} 只")

    # 3. 构建特征 + 训练LightGBM
    print("\n[3/4] 构建特征并训练LightGBM...")
    feature_cols = get_lgb_feature_cols()
    all_training_data = []

    for sym, df in stock_data.items():
        try:
            df = build_lgb_features(df)
            df = create_label(df, FORWARD_DAYS, BUY_THRESHOLD)
            # 添加HMM状态
            df = add_hmm_feature_to_stock(df, index_data, hmm_model)
            df["symbol"] = sym
            all_training_data.append(df)
        except Exception as e:
            print(f"   处理 {sym} 失败: {e}")

    if not all_training_data:
        print("错误：无可用训练数据")
        return False

    train_df = pd.concat(all_training_data, ignore_index=True)
    print(f"   训练数据集: {len(train_df)} 行")

    # 确认HMM状态列可用
    if "hmm_state" in train_df.columns and "hmm_state" not in feature_cols:
        feature_cols_with_hmm = feature_cols + ["hmm_state"]
    else:
        feature_cols_with_hmm = feature_cols

    # 确保所有特征列存在
    available_features = [
        c for c in feature_cols_with_hmm if c in train_df.columns
    ]
    print(f"   特征数量: {len(available_features)}")
    missing = set(feature_cols_with_hmm) - set(available_features)
    if missing:
        print(f"   缺失特征: {missing}")

    # 训练LightGBM
    lgb_model = LightGBMBuySignal()
    metrics = lgb_model.train(train_df, available_features)

    # 特征重要性
    importance = lgb_model.get_feature_importance(10)
    print("\n   特征重要性 Top 10:")
    for _, row in importance.iterrows():
        print(f"     {row['feature']:20s}: {row['importance']:.2f}")

    lgb_model.save()
    print("\n   LightGBM模型已保存")

    # 4. 训练结果总结
    print("\n[4/4] 训练完成!")
    print("-" * 40)
    print(f"  AUC:       {metrics.get('auc', 0):.4f}")
    print(f"  Precision: {metrics.get('precision', 0):.4f}")
    print(f"  Recall:    {metrics.get('recall', 0):.4f}")
    print(f"  Accuracy:  {metrics.get('accuracy', 0):.4f}")
    print(f"  模型文件:")
    print(f"    HMM: {os.path.join(MODELS_DIR, 'hmm_model.pkl')}")
    print(f"    LGB: {os.path.join(MODELS_DIR, 'lgb_model.txt')}")
    print("=" * 60)

    return True


if __name__ == "__main__":
    train()
