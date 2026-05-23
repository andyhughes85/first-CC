"""主流水线 - 整合所有模块生成每日买入信号"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from datetime import datetime

from config import MODELS_DIR, MAX_SIGNALS_PER_DAY
from data_fetcher import (
    get_index_hist, get_all_a_stocks, get_batch_stock_data,
    get_realtime_quote,
)
from market_state import MarketStateDetector
from industry_selector import IndustrySelector
from rule_engine import RuleEngine
from stock_scorer import StockScorer
from risk_manager import RiskManager
from push_notifier import PushNotifier


class DailyPipeline:
    """每日选股流水线"""

    def __init__(self):
        self.market = MarketStateDetector(use_hmm=True)
        self.industry = IndustrySelector()
        self.rule = RuleEngine()
        self.scorer = StockScorer()
        self.risk = RiskManager()
        self.notifier = PushNotifier()
        self.index_data = None
        self.regime = None

    def step_market_state(self):
        """第1步: 判断市场状态"""
        print("\n" + "=" * 50)
        print("📊 第1步: 市场状态判断")
        print("=" * 50)

        self.index_data = get_index_hist()
        if self.index_data.empty:
            raise RuntimeError("无法获取指数数据")

        # 尝试加载HMM，否则新训练
        self.market.load()
        self.index_data = self.market.fit(self.index_data)
        self.market.save()

        self.regime = self.market.get_current(self.index_data)
        pos_suggest = self.market.get_position_suggest(self.regime["state_label"])

        print(f"  市场状态: {self.regime['state_name']}")
        print(f"  概率分布: {self.regime['probabilities']}")
        print(f"  仓位建议: {pos_suggest['position']} ({pos_suggest['desc']})")

        return self.regime

    def step_industry_selection(self):
        """第2步: 行业筛选"""
        print("\n" + "=" * 50)
        print("🏭 第2步: 强势行业筛选")
        print("=" * 50)

        top_inds = self.industry.update()
        print(f"\n  选出的强势行业:")
        for ind in top_inds:
            print(f"    ✅ {ind}")

        return top_inds

    def step_get_stock_data(self, all_codes=None):
        """第3步: 获取股票数据"""
        print("\n" + "=" * 50)
        print("💾 第3步: 获取数据")
        print("=" * 50)

        if all_codes is None:
            all_codes = get_all_a_stocks()
        print(f"  股票池: {len(all_codes)} 只")

        stock_data = get_batch_stock_data(all_codes)
        print(f"  获取成功: {len(stock_data)} 只")
        return stock_data, all_codes

    def step_screening(self, stock_data, all_codes):
        """第4步: 规则引擎筛选 + 评分"""
        print("\n" + "=" * 50)
        print("🔍 第4步: 规则引擎筛选")
        print("=" * 50)

        # 构建行业映射（只在强势行业中查找）
        stock_industry_map = self.industry.build_stock_industry_map(set(stock_data.keys()))

        results = []
        total = len(stock_data)
        for i, (sym, df) in enumerate(stock_data.items()):
            industry_ok = sym in stock_industry_map
            ind_name = stock_industry_map.get(sym, "")

            result = self.rule.evaluate(df, industry_ok)
            if result is None:
                continue

            # CVaR风险检查
            risk_info = self.risk.evaluate_stock(df)
            if not risk_info["risk_ok"]:
                continue

            # LightGBM打分（如果模型已训练）
            lgb_score = 0
            if hasattr(self.scorer, "model") and self.scorer.model is not None:
                lgb_score = self.scorer.score(df)

            result.update({
                "symbol": sym,
                "industry": ind_name,
                "cvar": risk_info["cvar"],
                "max_drawdown": risk_info["max_drawdown"],
                "volatility": risk_info["volatility"],
                "score": lgb_score,
            })
            results.append(result)

            if (i + 1) % 500 == 0:
                print(f"  进度: {i+1}/{total} | 已发现: {len(results)}")

        if not results:
            print("  本轮无满足条件的个股")
            return []

        # 按综合评分排序
        results.sort(key=lambda x: x["total_score"], reverse=True)

        # 尝试加载LightGBM打分修正
        try:
            self.scorer.load()
        except:
            pass

        # 取Top N
        top_results = results[:MAX_SIGNALS_PER_DAY]

        print(f"\n  通过筛选: {len(results)} 只")
        print(f"  Top {len(top_results)}:")
        for r in top_results:
            print(f"    {r['symbol']:6s} 评分:{r['total_score']:.1f}  "
                  f"行业:{r.get('industry', '-')[:6]:6s}  "
                  f"CVaR:{r['cvar']:.2%}  "
                  f"LGB:{r.get('score', 0)}")

        return top_results

    def step_realtime(self, signals):
        """第5步: 获取实时行情补充"""
        print("\n" + "=" * 50)
        print("📡 第5步: 实时行情补充")
        print("=" * 50)

        if not signals:
            return signals

        codes = [s["symbol"] for s in signals]
        realtime = get_realtime_quote()
        if realtime.empty:
            return signals

        for s in signals:
            match = realtime[realtime["code"] == s["symbol"]]
            if not match.empty:
                r = match.iloc[0]
                s["name"] = r.get("name", "")
                s["pct"] = r.get("pct", 0)
                s["turnover"] = r.get("turnover", 0)
                if "name" in r:
                    s["name"] = r["name"]

        return signals

    def step_push(self, signals):
        """第6步: 推送信号"""
        print("\n" + "=" * 50)
        print("📱 第6步: 消息推送")
        print("=" * 50)

        if not signals:
            print("  无信号，跳过推送")
            return

        industry_report = "\n".join(f"  - {ind}" for ind in self.industry.top_industries)
        title = f"A股买入信号 {datetime.now().strftime('%Y-%m-%d')}"
        content = PushNotifier.format_signal_message(signals, self.regime, industry_report)

        print("\n" + content)
        self.notifier.push_all(title, content)

    def run(self, use_cache=True, push=False):
        """运行完整流水线"""
        print(f"\n{'#' * 50}")
        print(f"# A股中线波段买入信号系统")
        print(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#' * 50}")

        try:
            # Step 1-2
            regime = self.step_market_state()
            top_inds = self.step_industry_selection()

            # 熊市过滤
            if regime["state_label"] == "bear":
                print("\n⚠️ 当前为熊市，暂停选股")
                if push:
                    msg = (f"## {datetime.now().strftime('%Y-%m-%d')} 市场预警\n\n"
                           f"当前市场状态: **{regime['state_name']}**\n\n"
                           f"建议空仓观望，不生成买入信号。")
                    self.notifier.push_all("A股市场预警", msg)
                return

            # Step 3-6
            stock_data, all_codes = self.step_get_stock_data()
            signals = self.step_screening(stock_data, all_codes)
            signals = self.step_realtime(signals)
            if push:
                self.step_push(signals)

            return signals, regime

        except Exception as e:
            print(f"\n❌ 流水线执行出错: {e}")
            import traceback
            traceback.print_exc()
            return None, None


def run_scheduled():
    """定时运行入口（用于schedule/任务计划程序调用）"""
    pipeline = DailyPipeline()
    signals, regime = pipeline.run(use_cache=True, push=True)
    return signals, regime


if __name__ == "__main__":
    pipeline = DailyPipeline()
    pipeline.run(push=True)
