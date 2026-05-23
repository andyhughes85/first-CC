"""核心规则引擎 - 买入触发条件（均线多头排列 + 量能 + 行业确认）"""

import pandas as pd
import numpy as np
from config import (
    MA_PERIODS, MAX_PRICE_DEVIATION_MA20,
    VOLUME_MA_PERIOD, VOLUME_MIN_RATIO, VOLUME_MAX_RATIO,
    SCORE_WEIGHTS, MIN_SCORE,
)


class RuleEngine:
    """买入触发条件检查"""

    def check_ma_alignment(self, df):
        """条件A1: 均线多头排列 MA5 > MA10 > MA20 > MA60"""
        for p in MA_PERIODS:
            df[f"ma{p}"] = df["close"].rolling(p).mean()
        last = df.iloc[-1]
        return last["ma5"] > last["ma10"] > last["ma20"] > last["ma60"]

    def check_price_position(self, df):
        """条件A2: 价格在10日线上方，偏离20日线不超过8%"""
        last = df.iloc[-1]
        ma10 = df["close"].rolling(10).mean().iloc[-1]
        ma20 = df["close"].rolling(20).mean().iloc[-1]
        deviation = (last["close"] - ma20) / ma20 if ma20 > 0 else 0
        return last["close"] > ma10, abs(deviation) <= MAX_PRICE_DEVIATION_MA20, deviation

    def check_pullback(self, df):
        """条件A3(可选): 前3天缩量回调至10日线附近，今日放量站回5日线"""
        if len(df) < 6:
            return False, 0
        vol_ma5 = df["volume"].rolling(5).mean()
        recent = df.tail(6).copy()
        # 前3天是否有缩量回调
        pullback_days = 0
        for i in range(1, 4):
            if recent.iloc[-(1 + i)]["close"] < recent.iloc[-(1 + i)]["close"] * 1.0:
                if recent.iloc[-(1 + i)]["volume"] < vol_ma5.iloc[-(1 + i)] * 0.8:
                    pullback_days += 1
        # 今日放量站回5日线
        today_ma5 = df["close"].rolling(5).mean().iloc[-1]
        back_to_ma5 = df.iloc[-1]["close"] > today_ma5
        volume_expand = df.iloc[-1]["volume"] > vol_ma5.iloc[-1]
        return pullback_days >= 2 and back_to_ma5 and volume_expand, pullback_days

    def check_volume(self, df):
        """条件B: 今日成交量 > 1.5倍20日均量 AND < 4倍20日均量"""
        vol_ma20 = df["volume"].rolling(VOLUME_MA_PERIOD).mean().iloc[-1]
        today_vol = df.iloc[-1]["volume"]
        ratio = today_vol / vol_ma20 if vol_ma20 > 0 else 0
        return ratio >= VOLUME_MIN_RATIO and ratio <= VOLUME_MAX_RATIO, ratio

    def score_trend(self, df):
        """趋势得分（0-100）"""
        score = 50
        # 均线多头排列加分
        ma_values = {p: df["close"].rolling(p).mean().iloc[-1] for p in MA_PERIODS}
        if ma_values[5] > ma_values[10] > ma_values[20] > ma_values[60]:
            score += 30
        elif ma_values[5] > ma_values[10] > ma_values[20]:
            score += 15

        # 价格位置
        _, _, deviation = self.check_price_position(df)
        if abs(deviation) < 0.03:
            score += 10  # 刚突破，空间大
        elif abs(deviation) < 0.05:
            score += 5

        # 短期回调确认加分
        pullback_ok, _ = self.check_pullback(df)
        if pullback_ok:
            score += 10

        return min(score, 100)

    def score_momentum(self, df):
        """动量得分（0-100）"""
        score = 50
        # 5日涨幅
        ret_5d = df["close"].iloc[-1] / df["close"].iloc[-6] - 1 if len(df) >= 6 else 0
        # 10日涨幅
        ret_10d = df["close"].iloc[-1] / df["close"].iloc[-11] - 1 if len(df) >= 11 else 0

        if ret_5d > 0.05:
            score += 20
        elif ret_5d > 0.02:
            score += 10
        elif ret_5d < -0.02:
            score -= 10

        if 0 < ret_10d < 0.15:
            score += 15  # 温和上涨
        elif ret_10d > 0.15:
            score += 5   # 涨幅过大谨慎

        score = max(0, min(100, score))
        return score, ret_5d, ret_10d

    def score_volume(self, df):
        """量能得分（0-100）"""
        vol_ok, ratio = self.check_volume(df)
        if vol_ok:
            if VOLUME_MIN_RATIO <= ratio <= 2.0:
                return 85, ratio
            else:
                return 70, ratio
        else:
            if ratio < VOLUME_MIN_RATIO:
                return 30, ratio
            else:
                return 10, ratio

    def evaluate(self, df, industry_ok=False):
        """完整评估一只股票是否符合买入条件"""
        if df is None or len(df) < 61:  # 需要足够数据
            return None

        # 条件A1: 均线多头排列（必要条件）
        if not self.check_ma_alignment(df):
            return None

        # 条件A2: 价格位置
        price_ok, deviation_ok, deviation = self.check_price_position(df)
        if not price_ok or not deviation_ok:
            return None

        # 条件B: 成交量
        vol_ok, vol_ratio = self.check_volume(df)
        if not vol_ok:
            return None

        # 条件C: 行业确认（非必须，但加分）
        # 条件D: 市场过滤在外部做

        # 综合评分
        trend_score = self.score_trend(df)
        vol_score, _ = self.score_volume(df)
        mom_score, ret_5d, ret_10d = self.score_momentum(df)
        ind_score = 80 if industry_ok else 50

        total_score = (
            trend_score * SCORE_WEIGHTS["trend"]
            + vol_score * SCORE_WEIGHTS["volume"]
            + mom_score * SCORE_WEIGHTS["momentum"]
            + ind_score * SCORE_WEIGHTS["industry"]
        )

        last = df.iloc[-1]
        result = {
            "ma_alignment": True,
            "deviation": round(deviation, 4),
            "vol_ratio": round(vol_ratio, 2),
            "ret_5d": round(ret_5d * 100, 2),
            "ret_10d": round(ret_10d * 100, 2),
            "industry_ok": industry_ok,
            "trend_score": round(trend_score, 1),
            "volume_score": round(vol_score, 1),
            "momentum_score": round(mom_score, 1),
            "industry_score": round(ind_score, 1),
            "total_score": round(total_score, 1),
            "close": round(last.get("close", 0), 2),
            "volume": int(last.get("volume", 0)),
        }

        # 可选：短期回调加分
        pullback_ok, pullback_days = self.check_pullback(df)
        result["pullback_ok"] = pullback_ok
        if pullback_ok:
            result["total_score"] = min(result["total_score"] + 5, 100)

        return result
