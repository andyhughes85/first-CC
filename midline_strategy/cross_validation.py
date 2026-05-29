"""Purged Walk-Forward 交叉验证 — 防止时间序列数据泄露

设计：
- 每次训练集和测试集之间有 purge 天隔离期
- 每折输出完整回测指标（年化、夏普、最大回撤、胜率、盈亏比）
- 最终输出各折均值 + 标准差，识别过拟合
"""

import pandas as pd
import numpy as np
import logging
from datetime import timedelta

log = logging.getLogger(__name__)


class PurgedWalkForward:
    """Purged Walk-Forward 时间序列交叉验证

    Parameters
    ----------
    n_train : int
        每个训练集的交易日数
    n_test : int
        每个测试集的交易日数
    n_purge : int
        训练集和测试集之间的间隔（天），防止数据泄露
    min_samples : int
        最少有效折数
    """
    def __init__(self, n_train=504, n_test=252, n_purge=60, min_samples=3):
        self.n_train = n_train
        self.n_test = n_test
        self.n_purge = n_purge
        self.min_samples = min_samples

    def split(self, dates):
        """生成 (train_indices, test_indices) 的迭代器

        Parameters
        ----------
        dates : array-like of datetime
            所有交易日（已排序）

        Yields
        ------
        (train_idx, test_idx) : 每个折的训练集和测试集索引
        """
        dates = sorted(pd.to_datetime(dates))
        n = len(dates)
        folds = []

        start = 0
        while start + self.n_train + self.n_purge + self.n_test <= n:
            train_end = start + self.n_train
            purge_end = train_end + self.n_purge
            test_end = purge_end + self.n_test

            train_idx = list(range(start, train_end))
            test_idx = list(range(purge_end, test_end))

            folds.append((train_idx, test_idx))
            # 步进 n_test，可以重叠（后续折从当前折的 test 中间开始）
            start += self.n_test // 2  # 50% 重叠，增加折数

        if len(folds) < self.min_samples:
            raise ValueError(
                f"数据不足：{n}个交易日, n_train={self.n_train}, "
                f"n_purge={self.n_purge}, n_test={self.n_test}, "
                f"只能生成{len(folds)}折，需要≥{self.min_samples}折"
            )

        return folds


def run_cv_backtest(bt_class, start_date, end_date, max_stocks=280,
                    n_train=504, n_test=252, n_purge=60, **bt_kwargs):
    """用 Purged Walk-Forward 跑回测

    Parameters
    ----------
    bt_class : Backtest class
    start_date, end_date : str
    max_stocks : int
    n_train, n_test, n_purge : int
        对应 PurgedWalkForward 参数
    **bt_kwargs : 传给 Backtest 的额外参数

    Returns
    -------
    results : list of dict, 每折的完整指标
    """
    # 先用全量初始化拿到交易日列表
    bt = bt_class(start_date=start_date, end_date=end_date,
                  max_stocks=max_stocks, **bt_kwargs)
    all_dates = bt.trade_dates

    cv = PurgedWalkForward(n_train=n_train, n_test=n_test,
                           n_purge=n_purge)
    folds = cv.split(all_dates)

    results = []
    for i, (train_idx, test_idx) in enumerate(folds):
        fold_start = all_dates[train_idx[0]]
        fold_mid = all_dates[train_idx[-1]]
        fold_end = all_dates[test_idx[-1]]

        print(f"\n{'='*50}")
        print(f"折 {i+1}/{len(folds)}")
        print(f"  训练: {all_dates[train_idx[0]].date()} ~ {all_dates[train_idx[-1]].date()}")
        print(f"  隔离: +{n_purge}天")
        print(f"  测试: {all_dates[test_idx[0]].date()} ~ {all_dates[test_idx[-1]].date()}")
        print(f"{'='*50}")

        # 该折的回测
        fold_bt = bt_class(
            start_date=all_dates[train_idx[0]].strftime("%Y-%m-%d"),
            end_date=all_dates[test_idx[-1]].strftime("%Y-%m-%d"),
            max_stocks=max_stocks, **bt_kwargs
        )
        # 只保留 test 期间的权益曲线计算指标
        fold_bt.trade_dates = [d for d in fold_bt.trade_dates if d in set(all_dates[test_idx])]

        # 用测试集的交易和权益计算指标
        fold_bt.run()

        # 收集折结果
        from backtest import _SCRIPT_DIR
        import json
        with open(f"{_SCRIPT_DIR}/backtest_summary.json") as f:
            summary = json.load(f)
        summary["fold"] = i + 1
        summary["train_start"] = all_dates[train_idx[0]].strftime("%Y-%m-%d")
        summary["train_end"] = all_dates[train_idx[-1]].strftime("%Y-%m-%d")
        summary["test_start"] = all_dates[test_idx[0]].strftime("%Y-%m-%d")
        summary["test_end"] = all_dates[test_idx[-1]].strftime("%Y-%m-%d")
        results.append(summary)

    # 汇总
    print(f"\n{'='*50}")
    print(f"Purged Walk-Forward 结果汇总 ({len(results)}折)")
    print(f"{'='*50}")

    metrics = {
        "annual_return": "年化收益率",
        "sharpe": "夏普比率",
        "max_drawdown": "最大回撤",
        "win_rate": "胜率",
        "profit_ratio": "盈亏比",
        "excess_annual": "超额年化",
    }
    for key, label in metrics.items():
        vals = [r.get(key, 0) or 0 for r in results]
        mean_v = np.mean(vals)
        std_v = np.std(vals)
        print(f"  {label}: {mean_v:.4f} ± {std_v:.4f}")

    return results
