"""CVaR条件风险价值 - 风险过滤模块"""

import numpy as np
import pandas as pd
from config import CVAR_CONFIDENCE, CVAR_LOOKBACK_DAYS, MAX_CVAR_RATIO


def calc_var(returns, confidence=CVAR_CONFIDENCE):
    """计算VaR (Value at Risk)"""
    return np.percentile(returns, (1 - confidence) * 100)


def calc_cvar(returns, confidence=CVAR_CONFIDENCE):
    """计算CVaR (Conditional Value at Risk) - 期望尾部损失"""
    var = calc_var(returns, confidence)
    cvar = returns[returns <= var].mean()
    return cvar


def calc_daily_cvar(df, lookback=CVAR_LOOKBACK_DAYS, confidence=CVAR_CONFIDENCE):
    """计算个股日频CVaR"""
    # 使用日收益率
    if "pct_change" in df.columns:
        returns = df["pct_change"].dropna().tail(lookback) / 100
    else:
        returns = df["close"].pct_change().dropna().tail(lookback)

    if len(returns) < 20:
        return 0, 0

    var = calc_var(returns, confidence)
    cvar = calc_cvar(returns, confidence)

    return var, cvar


def calc_cvar_ratio(returns, confidence=CVAR_CONFIDENCE):
    """计算收益风险比 (预期收益 / CVaR)"""
    expected_ret = returns.mean()
    cvar = calc_cvar(returns, confidence)
    if abs(cvar) < 1e-10:
        return 0
    return expected_ret / abs(cvar)


def is_risk_acceptable(df, max_cvar=MAX_CVAR_RATIO, confidence=CVAR_CONFIDENCE):
    """判断风险是否可接受 (CVaR > max_cvar才允许买入)"""
    _, cvar = calc_daily_cvar(df, confidence=confidence)
    return cvar >= max_cvar, cvar


def cvar_filter(signals_df, stock_data_dict, confidence=CVAR_CONFIDENCE):
    """CVaR风控过滤：只保留风险可接受的信号"""
    results = []
    for _, row in signals_df.iterrows():
        sym = row["symbol"]
        df = stock_data_dict.get(sym)
        if df is None:
            continue

        ok, cvar = is_risk_acceptable(df, confidence=confidence)
        row["cvar"] = round(float(cvar), 4)
        row["risk_ok"] = ok
        results.append(row)

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values("buy_prob", ascending=False)
        result_df["rank"] = range(1, len(result_df) + 1)
    return result_df


def portfolio_cvar(weights, returns_cov, confidence=CVAR_CONFIDENCE):
    """计算投资组合CVaR（用于组合优化）"""
    # 使用协方差矩阵和权重模拟组合收益
    from scipy.stats import multivariate_normal
    np.random.seed(42)
    simulated = multivariate_normal.rvs(
        mean=None, cov=returns_cov, size=100000
    )
    portfolio_returns = simulated @ weights
    return calc_cvar(portfolio_returns, confidence)
