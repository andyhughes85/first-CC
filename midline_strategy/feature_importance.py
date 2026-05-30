"""
特征重要性分析 — 加载已训练模型，输出重要性排序 + 可视化

用法:
    python feature_importance.py                          # 默认分析 lgb_meta_triple.txt
    python feature_importance.py --model lgb_midline.txt  # 指定模型文件
"""

import os
import sys
import json
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime

from lgb_model import LightGBMModel
from lgb_features import get_lgb_feature_cols

_EXPERIMENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "experiments")
os.makedirs(_EXPERIMENTS_DIR, exist_ok=True)


def analyze(model_path: str, save: bool = True):
    """加载模型，分析特征重要性，输出报告"""
    # 加载模型
    model = LightGBMModel()
    model.load(model_path)
    feat = get_lgb_feature_cols()
    print("=" * 50)
    print("特征重要性分析")
    print("模型:", model_path)
    print("特征总数:", len(feat))
    print("=" * 50)

    # 获取重要性
    all_imp = model.model.feature_importance(importance_type="gain")
    df = []
    for f, imp in zip(feat, all_imp):
        df.append({"feature": f, "importance": imp})
    df = sorted(df, key=lambda x: x["importance"], reverse=True)

    total_imp = sum(d["importance"] for d in df)
    cum = 0

    print()
    print("{:<4s} {:<20s} {:>10s} {:>10s} {:>10s}".format(
        "排名", "特征", "重要性", "占比", "累计占比"
    ))
    print("-" * 58)
    for i, d in enumerate(df, 1):
        pct = d["importance"] / total_imp * 100 if total_imp > 0 else 0
        cum += pct
        print("{:<4d} {:<20s} {:>10.2f} {:>9.2f}% {:>9.2f}%".format(
            i, d["feature"], d["importance"], pct, cum
        ))

    # 标记可删除特征
    print()
    print("-" * 50)
    print("可删除特征（无区分度）:")
    zero_imp = [d for d in df if d["importance"] < 10]
    if zero_imp:
        for d in zero_imp:
            print("  [REMOVE] {}: {:.2f}".format(d["feature"], d["importance"]))
    else:
        print("  无")

    low_imp = [d for d in df if 10 <= d["importance"] < 100]
    if low_imp:
        print()
        print("低重要性特征（建议观察）:")
        for d in low_imp:
            print("  [LOW] {}: {:.2f}".format(d["feature"], d["importance"]))

    # 可视化
    if save:
        _plot(df, model_path)


def _plot(df, model_path):
    """保存特征重要性条形图"""
    top_n = min(25, len(df))
    top = df[:top_n]

    fig, ax = plt.subplots(figsize=(10, 8))
    features = [d["feature"] for d in top][::-1]
    values = [d["importance"] for d in top][::-1]

    colors = ["#2196F3" if v > 100 else "#FF9800" if v > 10 else "#F44336" for v in values]
    ax.barh(range(len(features)), values, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(features)))
    ax.set_yticklabels(features, fontsize=9)
    ax.set_xlabel("Importance (Gain)", fontsize=10)
    ax.set_title("Feature Importance - " + os.path.basename(model_path), fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # 超出图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#2196F3", label="High (>100)"),
        Patch(facecolor="#FF9800", label="Medium (10-100)"),
        Patch(facecolor="#F44336", label="Low (<10)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

    model_name = os.path.splitext(os.path.basename(model_path))[0]
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "feature_importance_{}_{}.png".format(model_name, now)
    filepath = os.path.join(_EXPERIMENTS_DIR, filename)
    plt.tight_layout()
    plt.savefig(filepath, dpi=150)
    print()
    print("图表已保存:", filepath)

    # 保存 JSON 数据
    json_data = {
        "model": model_path,
        "timestamp": now,
        "total_features": len(df),
        "features": [
            {"name": d["feature"], "importance": round(d["importance"], 2)}
            for d in df
        ],
        "remove_count": sum(1 for d in df if d["importance"] < 10),
    }
    json_path = filepath.replace(".png", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print("数据已保存:", json_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/lgb_meta_triple.txt")
    args = parser.parse_args()
    analyze(args.model)
