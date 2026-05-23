"""CVaR 风险过滤模块"""

import numpy as np
import pandas as pd
from config import CVAR_CONFIDENCE, CVAR_LOOKBACK_DAYS, MAX_CVAR_RATIO


class RiskManager:
    """风险管理器 - CVaR计算 + 仓位建议"""

    def calc_cvar(self, returns):
        """计算CVaR"""
        if len(returns) < 20:
            return 0
        var = np.percentile(returns, (1 - CVAR_CONFIDENCE) * 100)
        cvar = returns[returns <= var].mean()
        return cvar

    def evaluate_stock(self, df):
        """评估个股风险"""
        if "pct_change" in df.columns:
            returns = df["pct_change"].dropna().tail(CVAR_LOOKBACK_DAYS)
        else:
            returns = df["close"].pct_change().dropna().tail(CVAR_LOOKBACK_DAYS)

        if len(returns) < 20:
            return {"cvar": 0, "var": 0, "risk_ok": False}

        var = np.percentile(returns, (1 - CVAR_CONFIDENCE) * 100)
        cvar = returns[returns <= var].mean()

        # 最大回撤
        cum = (1 + returns).cumprod()
        peak = cum.expanding().max()
        drawdown = (cum / peak - 1).min()

        return {
            "cvar": round(cvar, 4),
            "var": round(var, 4),
            "max_drawdown": round(drawdown, 4),
            "risk_ok": cvar >= MAX_CVAR_RATIO,
            "volatility": round(returns.std(), 4),
        }

    def calc_position_size(self, total_score, regime_label, cvar):
        """计算建议仓位比例"""
        base = total_score / 100.0

        # 市场状态调整
        regime_factor = {"bull": 1.0, "oscillate": 0.6, "bear": 0.2}
        rf = regime_factor.get(regime_label, 0.5)

        # CVaR调整
        cvar_factor = max(0, min(1, (abs(cvar) - 0.02) / 0.08)) if cvar < 0 else 0.5
        cvar_factor = 1 - cvar_factor * 0.5  # 风险越大仓位越小

        position = base * rf * cvar_factor
        return round(min(position, 0.1), 3)  # 单只不超过10%
