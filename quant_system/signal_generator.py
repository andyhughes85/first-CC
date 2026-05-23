"""信号生成器 - 整合HMM + LightGBM + CVaR生成最终买入信号"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime

from config import (
    WATCHLIST, INDEX_CODE, FORWARD_DAYS, BUY_THRESHOLD,
    MIN_SIGNAL_PROB, MODELS_DIR,
)
from data_fetcher import (
    get_index_data, get_batch_stock_data, get_realtime_quote,
)
from feature_engineer import (
    build_lgb_features, create_label, get_lgb_feature_cols,
)
from hmm_model import MarketRegimeHMM, add_hmm_feature_to_stock
from lgb_model import LightGBMBuySignal
from cvar_risk import cvar_filter, is_risk_acceptable


class SignalGenerator:
    """整合HMM + LightGBM + CVaR的完整信号生成器"""

    def __init__(self, index_code=INDEX_CODE, watchlist=None):
        self.index_code = index_code
        self.watchlist = watchlist or WATCHLIST
        self.hmm = MarketRegimeHMM()
        self.lgb = LightGBMBuySignal()
        self.feature_cols = get_lgb_feature_cols()
        self.index_data = None

    def load_models(self, hmm_path=None, lgb_path=None):
        """加载已训练的模型"""
        self.hmm.load(hmm_path)
        self.lgb.load(lgb_path)

    def check_trained(self):
        """检查模型是否已训练"""
        hmm_path = os.path.join(MODELS_DIR, "hmm_model.pkl")
        lgb_path = os.path.join(MODELS_DIR, "lgb_model.txt")
        return os.path.exists(hmm_path) and os.path.exists(lgb_path)

    def update_index_data(self):
        """更新指数数据并识别市场状态"""
        print(">>> 获取指数数据...")
        self.index_data = get_index_data(self.index_code)
        if self.index_data.empty:
            raise ValueError("无法获取指数数据")

        # HMM识别市场状态
        print(">>> HMM识别市场状态...")
        self.index_data = self.hmm.fit(self.index_data)
        latest_regime = self.hmm.get_current_regime(self.index_data)
        print(f"   当前市场状态: {latest_regime['state_name']}")
        print(f"   概率分布: {latest_regime['probabilities']}")
        return latest_regime

    def generate_signals(self, symbols=None, use_realtime=False):
        """生成每日买入信号"""
        symbols = symbols or self.watchlist
        today = datetime.now().strftime("%Y-%m-%d")

        # 1. 获取市场状态
        regime = self.update_index_data()
        current_hmm_state = regime["state_code"]

        # 熊市不出信号（风控）
        if regime["state_label"] == "bear":
            print(f"\n>>> 当前为熊市，暂停买入信号")
            return pd.DataFrame(), regime

        # 2. 获取个股数据
        print(f">>> 获取 {len(symbols)} 只个股数据...")
        stock_data = get_batch_stock_data(symbols)

        # 3. 构建特征 + HMM状态映射
        print(">>> 构建特征...")
        processed_data = {}
        for sym, df in stock_data.items():
            try:
                df = build_lgb_features(df)
                df = create_label(df, FORWARD_DAYS, BUY_THRESHOLD)
                # 合并HMM状态
                if self.index_data is not None:
                    df = add_hmm_feature_to_stock(df, self.index_data, self.hmm)
                processed_data[sym] = df
            except Exception as e:
                print(f"   处理 {sym} 失败: {e}")

        # 4. LightGBM预测
        print(">>> LightGBM生成买入概率...")
        if use_realtime:
            realtime = get_realtime_quote(symbols)
        else:
            realtime = None

        # 用最近N天数据做预测
        signal_list = []
        for sym, df in processed_data.items():
            try:
                # 确保所有特征列存在
                available_features = [c for c in self.feature_cols if c in df.columns]
                if len(available_features) < 10:
                    continue

                lgb_result = self.lgb.get_buy_signals(df, current_hmm_state)
                row = lgb_result.iloc[0]
                signal_list.append({
                    "symbol": sym,
                    "close": row["close"],
                    "buy_prob": row["buy_prob"],
                    "signal": row["signal"],
                })
            except Exception as e:
                pass

        signals_df = pd.DataFrame(signal_list)
        if signals_df.empty:
            print("   无可用信号")
            return signals_df, regime

        # 5. CVaR风险过滤
        print(">>> CVaR风险过滤...")
        for sym in symbols:
            if sym in processed_data:
                ok, cvar_val = is_risk_acceptable(processed_data[sym])
                signals_df.loc[signals_df["symbol"] == sym, "cvar"] = round(cvar_val, 4)
                signals_df.loc[signals_df["symbol"] == sym, "risk_ok"] = ok

        # 合并实时数据（如果有）
        if realtime is not None and not realtime.empty:
            signals_df = signals_df.merge(
                realtime[["symbol", "name", "pct", "turnover", "pe", "pb"]],
                on="symbol", how="left"
            )

        # 排序：按买入概率降序
        signals_df = signals_df.sort_values("buy_prob", ascending=False).reset_index(drop=True)
        signals_df["rank"] = range(1, len(signals_df) + 1)
        signals_df["signal_date"] = today

        return signals_df, regime

    def print_signal_report(self, signals_df, regime):
        """打印信号报告"""
        if signals_df.empty:
            print("\n========== 今日无买入信号 ==========")
            return

        # 过滤出可信信号
        buy_signals = signals_df[
            (signals_df["signal"] == 1) &
            (signals_df.get("risk_ok", True) == True)
        ]

        print("\n" + "=" * 70)
        print(f"📊 A股买入信号报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        print(f"市场状态: {regime['state_name']}")

        if buy_signals.empty:
            print("\n❌ 当前无满足条件的买入信号")
            print("   (概率不足或风险过高)")
            return

        print(f"\n🔥 推荐买入 ({len(buy_signals)} 只):")
        print("-" * 70)
        for _, row in buy_signals.iterrows():
            name = row.get("name", row["symbol"])
            prob = row["buy_prob"] * 100
            cvar_str = f"CVaR: {row.get('cvar', 0)*100:.1f}%"
            pct = row.get("pct", 0)
            pct_str = f"今日: {pct:+.2f}%" if pct != 0 else ""
            print(f"  #{row['rank']} {name}({row['symbol']}) "
                  f"概率 {prob:.1f}% | {cvar_str} | {pct_str}")

        print("\n📋 全市场信号概览:")
        print("-" * 70)
        for _, row in signals_df.iterrows():
            name = row.get("name", row["symbol"])
            prob = row["buy_prob"] * 100
            risk_ok = "✅" if row.get("risk_ok", False) else "❌"
            print(f"  {risk_ok} {name:10s}  买入概率: {prob:5.1f}%  "
                  f"CVaR: {row.get('cvar', 0)*100:+.1f}%")

        print("=" * 70)
