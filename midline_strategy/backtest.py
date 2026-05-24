"""回测系统 — 逐日模拟 (独立于线上配置)"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import STOCK_MA5, STOCK_MA10, STOCK_MA20, STOCK_MA60, VOL_RATIO_MIN, VOL_RATIO_MAX, MAX_DEVIATION
from data_fetcher import load_cached
from market_state import judge_market_state, add_index_indicators


class BacktestConfig:
    """回测参数，与 config.py 独立，避免污染线上配置"""
    STOP_LOSS = -0.07
    TAKE_PROFIT = 0.10
    TIME_STOP = 15
    COMMISSION = 0.0002
    SLIPPAGE = 0.001
    SINGLE_POSITION = 0.08
    MAX_POSITIONS = 10
    TOP_INDUSTRIES = 5
    INDUSTRY_MOMENTUM_DAYS = 20


BT = BacktestConfig  # 别名


class Backtest:
    """A股中线波段策略回测引擎"""

    def __init__(self, start_date="2018-01-01", end_date="2025-12-31",
                 initial_capital=1_000_000, max_stocks=None):
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)
        self.initial_capital = initial_capital
        self.max_stocks = max_stocks  # None = 全部股票

        self.cash = initial_capital
        self.positions = {}          # code -> Position
        self.equity_curve = []       # [(date, total_value)]
        self.trades = []             # 已完成的交易
        self._daily_signal_count = 0

        # 加载数据（含温漂）
        warmup = timedelta(days=180)
        self._load_data(warmup)
        self._precompute_signals()
        self._precompute_market_states()

    # ---- 数据加载 ----

    def _load_data(self, warmup):
        load_start = (self.start_date - warmup).strftime("%Y-%m-%d")
        load_end = self.end_date.strftime("%Y-%m-%d")

        idx = load_cached("index_daily", start=load_start, end=load_end)
        if len(idx) < 60:
            raise ValueError(f"指数数据不足({len(idx)}条)，需 ≥60 条。"
                             "请先用 data_fetcher 补充历史数据。")
        self.index_df = add_index_indicators(idx).sort_values("date").reset_index(drop=True)
        self.index_df["date"] = pd.to_datetime(self.index_df["date"])

        stocks = load_cached("stock_daily", start=load_start, end=load_end)
        if stocks.empty:
            raise ValueError("个股数据为空，请先用 data_fetcher 补充历史数据。")
        stock_list = load_cached("stock_list")
        if not stock_list.empty:
            stocks = stocks.merge(stock_list[["code", "name", "industry"]], on="code", how="left")
        stocks["date"] = pd.to_datetime(stocks["date"])

        # 缩小股票池（取交易日最多的前 N 只）
        if self.max_stocks:
            top_codes = (
                stocks.groupby("code").size()
                .sort_values(ascending=False)
                .head(self.max_stocks)
                .index
            )
            stocks = stocks[stocks["code"].isin(top_codes)]
            print(f"股票池限制: {self.max_stocks}只（按交易日数排序）")

        stocks = stocks.sort_values(["code", "date"]).reset_index(drop=True)
        self.stock_df = stocks

        trade_dates = sorted(stocks[stocks["date"] >= self.start_date]["date"].unique())
        self.trade_dates = trade_dates if trade_dates else []
        if not self.trade_dates:
            raise ValueError(f"{load_start}~{load_end} 间无交易日数据")

        n_stocks = self.stock_df["code"].nunique()
        n_rows = len(self.stock_df)
        print(f"数据加载: {len(self.index_df)}条指数, {n_rows}条个股({n_stocks}只)")
        print(f"交易日: {len(self.trade_dates)}天 ({self.trade_dates[0].date()} ~ {self.trade_dates[-1].date()})")

    # ---- 信号预计算 ----

    def _precompute_signals(self):
        df = self.stock_df.copy()

        def _calc(group):
            g = group.sort_values("date")
            g["ma5"] = g["close"].rolling(STOCK_MA5, min_periods=STOCK_MA5).mean()
            g["ma10"] = g["close"].rolling(STOCK_MA10, min_periods=STOCK_MA10).mean()
            g["ma20"] = g["close"].rolling(STOCK_MA20, min_periods=STOCK_MA20).mean()
            g["ma60"] = g["close"].rolling(STOCK_MA60, min_periods=STOCK_MA60).mean()
            g["vol_ma20"] = g["volume"].rolling(20, min_periods=20).mean()
            return g

        df = (df.set_index("code")
              .groupby(level=0, group_keys=False)
              .apply(_calc)
              .reset_index())
        df = df.dropna(subset=["ma5", "ma10", "ma20", "ma60", "vol_ma20"])

        df["vol_ratio"] = df["volume"] / df["vol_ma20"]
        df["deviation"] = (df["close"] - df["ma20"]) / df["ma20"]

        mask_trend = (
            (df["ma5"] > df["ma10"])
            & (df["ma10"] > df["ma20"])
            & (df["ma20"] > df["ma60"])
            & (df["close"] > df["ma10"])
        )
        mask_vol = (df["vol_ratio"] >= VOL_RATIO_MIN) & (df["vol_ratio"] <= VOL_RATIO_MAX)
        mask_dev = df["deviation"] < MAX_DEVIATION
        df["signal"] = mask_trend & mask_vol & mask_dev

        df["score"] = (
            (df["ma5"] / df["ma60"] - 1) * 100
            + df["vol_ratio"] * 0.5
            - abs(df["deviation"]) * 50
        )

        self._sig_df = df[df["signal"]].copy()

    # ---- 市场状态预计算 ----

    def _precompute_market_states(self):
        states = {}
        idx = self.index_df
        for i in range(len(idx)):
            date = idx.iloc[i]["date"]
            lookback = min(i + 1, 500)
            tmp = idx.iloc[i + 1 - lookback: i + 1]
            if len(tmp) >= 60:
                states[date] = judge_market_state(tmp)
            else:
                states[date] = {"state": "wait", "pos_limit": 0.0}
        self._market_states = states

    def _get_market_info(self, date):
        return self._market_states.get(date, {"state": "wait", "pos_limit": 0.0})

    # ---- 行业动量 ----

    def _get_hot_industries(self, date):
        if "industry" not in self.stock_df.columns:
            return []
        cutoff = date - timedelta(days=BT.INDUSTRY_MOMENTUM_DAYS * 2)
        hist = self.stock_df[
            (self.stock_df["date"] <= date)
            & (self.stock_df["date"] >= cutoff)
            & (self.stock_df["industry"].notna())
            & (self.stock_df["industry"] != "")
        ].copy()
        if hist.empty or hist["code"].nunique() < 50:
            return ["电子", "医药生物", "电力设备", "食品饮料", "汽车"]

        recent = hist[hist["date"] == hist.groupby("code")["date"].transform("max")]
        oldest = hist[hist["date"] == hist.groupby("code")["date"].transform("min")]
        mom = recent[["code", "close"]].merge(
            oldest[["code", "close"]], on="code", suffixes=("_r", "_o"), how="inner"
        )
        mom["return"] = mom["close_r"] / mom["close_o"] - 1
        ind_mom = (
            mom.merge(self.stock_df[["code", "industry"]].drop_duplicates("code"), on="code")
            .groupby("industry")["return"]
            .median()
            .sort_values(ascending=False)
        )
        return ind_mom.head(BT.TOP_INDUSTRIES).index.tolist()

    # ---- 买卖逻辑 ----

    def _sell_check(self, date):
        today = self.stock_df[self.stock_df["date"] == date]
        to_close = []
        for code, pos in self.positions.items():
            row = today[today["code"] == code]
            if row.empty:
                continue
            r = row.iloc[0]
            close = r["close"]
            pnl = close / pos["buy_price"] - 1
            hold = (date - pos["buy_date"]).days

            reason = None
            if pnl <= BT.STOP_LOSS:
                reason = "止损"
            elif pnl >= BT.TAKE_PROFIT:
                reason = "止盈"
            elif hold >= BT.TIME_STOP:
                reason = "时间止损"
            else:
                hist = self.stock_df[
                    (self.stock_df["code"] == code) & (self.stock_df["date"] <= date)
                ]
                if len(hist) >= STOCK_MA10:
                    ma10 = hist["close"].rolling(STOCK_MA10).mean().iloc[-1]
                    if close < ma10:
                        reason = "趋势破坏"

            if reason:
                self._sell(code, date, r, reason)
                to_close.append(code)
        for c in to_close:
            del self.positions[c]

    def _sell(self, code, date, row, reason):
        pos = self.positions[code]
        next_date = date + timedelta(days=1)
        next_day = self.stock_df[
            (self.stock_df["code"] == code) & (self.stock_df["date"] == next_date)
        ]
        if not next_day.empty:
            sell_price = next_day.iloc[0]["open"] * (1 - BT.SLIPPAGE)
        else:
            sell_price = row["close"] * (1 - BT.SLIPPAGE)
        proceeds = pos["shares"] * sell_price * (1 - BT.COMMISSION)
        self.cash += proceeds
        pnl = sell_price / pos["buy_price"] - 1
        self.trades.append({
            "code": code,
            "name": pos.get("name", ""),
            "buy_date": pos["buy_date"].strftime("%Y-%m-%d"),
            "buy_price": round(pos["buy_price"], 3),
            "sell_date": date.strftime("%Y-%m-%d"),
            "sell_price": round(sell_price, 3),
            "pnl": round(pnl, 4),
            "reason": reason,
        })

    # noinspection PyMethodMayBeStatic
    def _calc_score(self, row):
        vol_ratio = row["volume"] / row["vol_ma20"] if row["vol_ma20"] > 0 else 0
        deviation = (row["close"] - row["ma20"]) / row["ma20"]
        return (
            (row["ma5"] / row["ma60"] - 1) * 100
            + vol_ratio * 0.5
            - abs(deviation) * 50
        )

    def _buy_check(self, date):
        market_info = self._get_market_info(date)
        state = market_info["state"]
        pos_limit = market_info["pos_limit"]
        if state == "wait":
            return

        target_signals = self._sig_df[self._sig_df["date"] == date].copy()
        if target_signals.empty:
            return

        hot = self._get_hot_industries(date)
        if hot:
            target_signals = target_signals[
                target_signals["industry"].isin(hot) | target_signals["industry"].isna()
            ]
        if target_signals.empty:
            return

        target_signals = target_signals.sort_values("score", ascending=False)

        max_market_val = self.initial_capital * pos_limit
        cur_val = self._market_value(date)
        max_new = max_market_val - cur_val
        if max_new <= 0:
            return

        for _, row in target_signals.iterrows():
            code = row["code"]
            if code in self.positions:
                continue
            if len(self.positions) >= BT.MAX_POSITIONS:
                break

            per_budget = min(self.initial_capital * BT.SINGLE_POSITION, max_new * 0.5)
            if self.cash < per_budget:
                continue

            next_date = date + timedelta(days=1)
            next_day = self.stock_df[
                (self.stock_df["code"] == code) & (self.stock_df["date"] == next_date)
            ]
            if next_day.empty:
                continue

            buy_price = next_day.iloc[0]["open"] * (1 + BT.SLIPPAGE)
            shares = int(per_budget / (buy_price * (1 + BT.COMMISSION)) / 100) * 100
            if shares < 100:
                continue
            cost = shares * buy_price * (1 + BT.COMMISSION)
            if cost > self.cash:
                continue

            self.cash -= cost
            self.positions[code] = {
                "code": code,
                "name": row.get("name", ""),
                "buy_date": date,
                "buy_price": buy_price,
                "shares": shares,
            }

    def _market_value(self, date):
        today = self.stock_df[self.stock_df["date"] == date]
        total = 0.0
        for code, pos in self.positions.items():
            row = today[today["code"] == code]
            price = row.iloc[0]["close"] if not row.empty else pos["buy_price"]
            total += pos["shares"] * price
        return total

    # ---- 主循环 ----

    def run(self):
        days = len(self.trade_dates)
        print(f"\n回测开始: {self.trade_dates[0].date()} ~ {self.trade_dates[-1].date()}")
        print(f"交易日: {days}天 | 初始资金: {self.initial_capital:,.0f}")
        print("-" * 50)

        for i, date in enumerate(self.trade_dates):
            if (i + 1) % 200 == 0:
                print(f"进度: {i+1}/{days}天 ({(i+1)/days:.0%})")

            self._sell_check(date)
            self._buy_check(date)
            mv = self._market_value(date)
            self.equity_curve.append((date, self.cash + mv))

        self._report()

    # ---- 绩效报告 ----

    def _report(self):
        print("\n" + "=" * 50)
        print("回测报告")
        print("=" * 50)

        n_trades = len(self.trades)
        if n_trades == 0:
            print("\n无交易记录")
            return

        trades = pd.DataFrame(self.trades)

        # 胜率
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] <= 0]
        win_rate = len(wins) / n_trades
        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0.0
        avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0.0
        pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        # 连续亏损
        max_consec_loss = 0
        cur = 0
        for pnl in trades["pnl"]:
            if pnl <= 0:
                cur += 1
                max_consec_loss = max(max_consec_loss, cur)
            else:
                cur = 0

        # 权益曲线
        eq = pd.DataFrame(self.equity_curve, columns=["date", "value"])
        total_return = eq["value"].iloc[-1] / eq["value"].iloc[0] - 1

        years = (self.end_date - self.start_date).days / 365.25
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else total_return

        eq["daily_ret"] = eq["value"].pct_change()
        ann_vol = eq["daily_ret"].std() * np.sqrt(252)
        sharpe = (annual_return - 0.02) / ann_vol if ann_vol > 0 else 0

        # 最大回撤
        cummax = eq["value"].cummax()
        dd = (eq["value"] - cummax) / cummax
        max_dd = dd.min()
        dd_start = dd.idxmin()
        dd_end = dd[dd_start:].cummax().idxmax() if dd_start < len(dd) - 1 else len(dd) - 1
        dd_days = (eq.iloc[dd_end]["date"] - eq.iloc[dd_start]["date"]).days

        # 基准
        bench = self.index_df[
            (self.index_df["date"] >= self.start_date)
            & (self.index_df["date"] <= self.end_date)
        ]
        bench_start = bench.iloc[0]["close"]
        bench_end = bench.iloc[-1]["close"]
        bench_return = bench_end / bench_start - 1

        # 分年度
        eq["year"] = eq["date"].dt.year
        yearly = eq.groupby("year")["value"].agg(["first", "last"])
        yearly["return"] = yearly["last"] / yearly["first"] - 1

        # ---- 输出 ----

        print(f"\n交易次数: {n_trades} ({n_trades / max(years, 0.1):.1f}次/年)")
        print(f"胜率:          {win_rate:.1%}")
        print(f"平均盈利:      {avg_win:.2%}")
        print(f"平均亏损:      {avg_loss:.2%}")
        print(f"盈亏比:        {pl_ratio:.2f}")
        print(f"最大连续亏损:  {max_consec_loss}次")
        print(f"\n总收益率:      {total_return:+.2%}")
        print(f"年化收益率:    {annual_return:+.2%}")
        print(f"年化波动率:    {ann_vol:.2%}")
        print(f"夏普比率:      {sharpe:.2f}")
        print(f"最大回撤:      {max_dd:.2%}")
        print(f"回撤持续期:    {dd_days}天")
        print(f"\n基准(沪深300): {bench_return:+.2%}")
        print(f"超额收益:      {total_return - bench_return:+.2%}")

        # 年度收益
        print(f"\n{'年度收益':-<42}")
        for yr, row in yearly.iterrows():
            yr_label = f"{yr}: {row['return']:+.2%}"
            bar = "█" * max(0, int(row["return"] * 100))
            print(f"  {yr_label:<22} {bar}")
        print("-" * 42)

        # 绿灯
        green = all([
            annual_return > 0.08,
            win_rate > 0.40,
            pl_ratio > 2.0,
            max_dd > -0.25,
        ])
        if green:
            print("\n✅ 策略通过绿灯验证")
        else:
            print("\n⚠️ 策略未通过绿灯验证")
            if annual_return <= 0.08:
                print("   - 年化收益率 ≤ 8%")
            if win_rate <= 0.40:
                print("   - 胜率 ≤ 40%")
            if pl_ratio <= 2.0:
                print(f"   - 盈亏比 ≤ 2.0 ({pl_ratio:.2f})")
            if max_dd <= -0.25:
                print(f"   - 最大回撤 ≥ 25% ({max_dd:.2%})")

        # 最近交易
        print(f"\n{'最近10笔交易':-<42}")
        for _, t in trades.tail(10).iterrows():
            print(f"  {t['sell_date']} {t.get('name','')}({t['code']}) "
                  f"{t['pnl']:+.2%} | {t['reason']}")


if __name__ == "__main__":
    import sys
    max_stocks = 300
    if "--summary" in sys.argv:
        max_stocks = 300
    bt = Backtest(start_date="2018-01-01", end_date="2025-12-31", max_stocks=max_stocks)
    bt.run()
