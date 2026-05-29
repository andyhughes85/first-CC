"""虚拟盘交易引擎 — 自动执行信号、追踪持仓、记录权益"""

import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from config import DB_PATH, STOP_LOSS, TIME_STOP_DAYS, MAX_POSITION_PER_STOCK
from push_service import _send_tg, _send_serverchan

# 回测参数（与 backtest.py 对齐）
_SINGLE_POSITION = 0.08  # 单只股票基准仓位
_POS_LIMITS = {"bull": 0.8, "oscillation": 0.4, "bear": 0.1}


class PaperTrader:
    """虚拟盘交易引擎"""

    def __init__(self, db_path=DB_PATH, initial_capital=1_000_000):
        self.db_path = db_path
        self.initial_capital = initial_capital
        self.commission = 0.0002  # 万二，与 backtest.py 对齐
        self.slippage = 0.001     # 千一
        self._init_db()
        self._load_state()

    # ── 数据库初始化 ──

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                code TEXT PRIMARY KEY, name TEXT, shares INTEGER,
                entry_price REAL, entry_date TEXT, current_price REAL,
                highest_close REAL, trailing_activated INTEGER DEFAULT 0,
                atr_entry REAL, pnl REAL DEFAULT 0, pnl_pct REAL DEFAULT 0,
                market_state TEXT, buy_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, action TEXT,
                price REAL, shares INTEGER, pnl REAL, pnl_pct REAL,
                reason TEXT, date TEXT, hold_days INTEGER
            );
            CREATE TABLE IF NOT EXISTS paper_equity (
                date TEXT PRIMARY KEY, cash REAL, market_value REAL,
                total_equity REAL, pos_limit REAL, market_state TEXT
            );
            CREATE TABLE IF NOT EXISTS paper_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, code TEXT, name TEXT,
                close REAL, volume_ratio REAL, deviation REAL,
                score REAL, industry TEXT, executed INTEGER DEFAULT 0
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_signals_date_code
                ON paper_signals(date, code);
        """)
        conn.commit()
        conn.close()

    def _load_state(self):
        """从数据库恢复状态"""
        conn = sqlite3.connect(self.db_path)
        # 恢复现金
        cur = conn.execute("SELECT cash FROM paper_equity ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        self.cash = row[0] if row else float(self.initial_capital)

        # 恢复连亏计数（从最近5笔交易计算）
        rows = conn.execute(
            "SELECT pnl FROM paper_trades WHERE action='sell' ORDER BY id DESC LIMIT 5"
        ).fetchall()
        self._consecutive_losses = 0
        for r in rows:
            if r[0] is not None and r[0] <= 0:
                self._consecutive_losses += 1
            else:
                break
        self._cool_until = None
        conn.close()

    # ── 每日核心调用 ──

    def process(self, signals, market_state, stocks_df, date):
        """每日处理：更新市价→检查出场→执行入场→记录权益"""
        today = pd.Timestamp(date)

        # 1. 更新持仓市价
        self._update_prices(stocks_df)

        # 2. 检查出场条件
        self._check_exits(stocks_df, market_state, today)

        # 3. 执行新信号入场
        self._check_entries(signals, market_state, stocks_df, today)

        # 4. 记录当日权益
        self._snapshot_equity(today, market_state)

    # ── 持仓管理 ──

    def _update_prices(self, stocks_df):
        """用最新数据更新持仓市价"""
        if stocks_df.empty:
            return
        conn = sqlite3.connect(self.db_path)
        positions = conn.execute("SELECT code, highest_close FROM paper_positions").fetchall()
        for code, highest in positions:
            row = stocks_df[stocks_df["code"] == code]
            if row.empty:
                continue
            close = float(row.iloc[-1]["close"])
            new_high = max(highest or 0, close)
            pnl = close / self._get_entry_price(code, conn) - 1 if self._get_entry_price(code, conn) else 0
            conn.execute(
                "UPDATE paper_positions SET current_price=?, highest_close=?, pnl=?, pnl_pct=? WHERE code=?",
                (close, new_high, round(pnl, 4), round(pnl, 4), code)
            )
        conn.commit()
        conn.close()

    def _get_entry_price(self, code, conn=None):
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            own = True
        else:
            own = False
        cur = conn.execute("SELECT entry_price FROM paper_positions WHERE code=?", (code,))
        row = cur.fetchone()
        if own:
            conn.close()
        return row[0] if row else 0

    def open_position(self, code, name, price, shares, market_state, date, reason="信号"):
        """开仓"""
        cost = shares * price * (1 + self.commission)
        if cost > self.cash:
            return False
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO paper_positions VALUES (?,?,?,?,?,?,?,0,0,0,0,?,?)",
            (code, name, shares, price, date.strftime("%Y-%m-%d"), price, price,
             market_state, reason)
        )
        # 记录买入交易
        conn.execute(
            "INSERT INTO paper_trades (code, name, action, price, shares, pnl, pnl_pct, reason, date, hold_days) "
            "VALUES (?,?,?,?,?,0,0,?,?,0)",
            (code, name, "buy", price, shares, reason, date.strftime("%Y-%m-%d"))
        )
        self.cash -= cost
        conn.commit()
        conn.close()
        return True

    def close_position(self, code, price, reason, date):
        """平仓"""
        conn = sqlite3.connect(self.db_path)
        pos = conn.execute(
            "SELECT name, shares, entry_price, entry_date FROM paper_positions WHERE code=?", (code,)
        ).fetchone()
        if not pos:
            conn.close()
            return False
        name, shares, entry_price, entry_date_str = pos
        entry_date = pd.Timestamp(entry_date_str)
        hold_days = (date - entry_date).days
        proceeds = shares * price * (1 - self.commission)
        pnl = proceeds - shares * entry_price
        pnl_pct = price / entry_price - 1

        self.cash += proceeds

        # 连亏计数
        if pnl <= 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= 3:
                self._cool_until = date + timedelta(days=5)
        else:
            self._consecutive_losses = 0

        conn.execute("DELETE FROM paper_positions WHERE code=?", (code,))
        conn.execute(
            "INSERT INTO paper_trades (code, name, action, price, shares, pnl, pnl_pct, reason, date, hold_days) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (code, name, "sell", price, shares, round(pnl, 2), round(pnl_pct, 4),
             reason, date.strftime("%Y-%m-%d"), hold_days)
        )
        conn.commit()
        conn.close()

        # 推送出场通知
        emoji = "🛑" if pnl <= 0 else "✅"
        direction = "止损" if pnl <= 0 else "止盈"
        msg = (
            f"{emoji} 虚拟盘 {direction} {name}({code})\n"
            f"卖出价: {price:.2f} | 盈亏: {pnl:+.2f} ({pnl_pct:+.2%})\n"
            f"持仓: {hold_days}天 | 原因: {reason}"
        )
        _send_tg(msg)
        _send_serverchan(f"虚拟盘 {direction} {name}", msg)

        return True

    # ── 出场检查（复用 backtest.py 逻辑）──

    def _check_exits(self, stocks_df, market_state, today):
        """遍历持仓，检查出场条件"""
        if today is None:
            today = datetime.now()
        state = market_state.get("state", "oscillation")
        conn = sqlite3.connect(self.db_path)
        positions = conn.execute("SELECT * FROM paper_positions").fetchall()
        cols = ["code", "name", "shares", "entry_price", "entry_date", "current_price",
                "highest_close", "trailing_activated", "atr_entry", "pnl", "pnl_pct",
                "market_state", "buy_reason"]
        conn.close()

        for row in positions:
            pos = dict(zip(cols, row))
            code = pos["code"]
            close = pos["current_price"] or pos["entry_price"]
            entry_p = pos["entry_price"]
            pnl = close / entry_p - 1
            hold = (today - pd.Timestamp(pos["entry_date"])).days
            highest = pos["highest_close"] or close
            atr_e = pos["atr_entry"] or 0
            use_atr = atr_e > 0

            reason = None

            # 1. 硬止损
            if pnl <= STOP_LOSS:
                reason = "止损"

            # 2. 市场状态自适应出场
            if reason is None:
                if state == "bull":
                    if use_atr:
                        trail = highest - atr_e * 3
                    else:
                        trail = highest * 0.92
                    if close <= trail:
                        reason = "牛市移动止盈"
                elif state == "bear":
                    if pnl >= 0.08:
                        reason = "熊市保守止盈"
                    elif hold >= 10:
                        reason = "熊市时间止损"
                else:  # oscillation
                    if hold >= TIME_STOP_DAYS:
                        reason = "震荡时间止损"
                    elif pnl >= 0.10:
                        # 激活移动止盈（持久化到DB）
                        conn = sqlite3.connect(self.db_path)
                        conn.execute("UPDATE paper_positions SET trailing_activated=1 WHERE code=?", (code,))
                        conn.commit()
                        conn.close()
                    if pos.get("trailing_activated"):
                        if use_atr:
                            trail_stop = max(highest - atr_e * 2, entry_p * 1.03)
                        else:
                            trail_stop = max(highest * 0.95, entry_p * 1.03)
                        if close <= trail_stop:
                            reason = "震荡移动止盈"

            # 3. 趋势破坏 + 海龟出场
            if reason is None:
                hist = stocks_df[stocks_df["code"] == code].sort_values("date")
                if len(hist) >= 10:
                    hist["ma10"] = hist["close"].rolling(10).mean()
                    hist["tr"] = np.maximum(
                        hist["high"] - hist["low"],
                        np.maximum(abs(hist["high"] - hist["close"].shift(1)),
                                   abs(hist["low"] - hist["close"].shift(1)))
                    )
                    hist["atr"] = hist["tr"].rolling(14).mean()
                    ma10 = hist["ma10"].iloc[-1]
                    curr_atr = max(hist["atr"].iloc[-1], atr_e) if use_atr else 0
                    if curr_atr > 0:
                        if close < ma10 - curr_atr * 1.5:
                            reason = "趋势破坏"
                    else:
                        if close < ma10 * 0.96:
                            reason = "趋势破坏"
                    if reason is None and len(hist) >= 11:
                        if close < hist["low"].iloc[-11:-1].min():
                            reason = "海龟出场"

            if reason:
                self.close_position(code, close, reason, today)

            # 冷却提示
            if self._cool_until and today < self._cool_until:
                pass  # 冷却期间不入场

    # ── 入场检查 ──

    def _check_entries(self, signals, market_state, stocks_df, today):
        """执行新信号入场"""
        if signals is None or signals.empty:
            return
        state = market_state.get("state", "oscillation")
        pos_limit = market_state.get("pos_limit", _POS_LIMITS.get(state, 0.4))
        if state == "wait":
            return

        # 冷却检查
        if self._cool_until and today and today < self._cool_until:
            return

        # 计算可用仓位上限
        max_market_val = self.initial_capital * pos_limit
        cur_val = self._market_value()
        max_new = max_market_val - cur_val
        if max_new <= 0:
            return

        conn = sqlite3.connect(self.db_path)
        existing = {r[0] for r in conn.execute("SELECT code FROM paper_positions").fetchall()}
        conn.close()

        # 持久化今日信号
        self._save_signals(signals, today)

        # 按分数从高到低执行
        for _, row in signals.iterrows():
            code = row["code"]
            if code in existing:
                continue
            if self._position_count() >= 10:  # 最大持仓数
                break

            name = row.get("name", "")
            price = float(row["close"])
            per_budget = min(self.initial_capital * _SINGLE_POSITION, max_new * 0.5)
            if self.cash < per_budget:
                continue

            shares = int(per_budget / (price * (1 + self.commission)) / 100) * 100
            if shares < 100:
                continue
            cost = shares * price * (1 + self.commission)
            if cost > self.cash:
                continue

            self._set_atr_entry(code, stocks_df)
            self.open_position(code, name, price, shares, state, today)
            existing.add(code)

    def _set_atr_entry(self, code, stocks_df):
        """计算并保存买入时ATR"""
        hist = stocks_df[stocks_df["code"] == code].sort_values("date")
        if len(hist) < 15:
            return
        hi, lo, clo = hist["high"].values, hist["low"].values, hist["close"].values
        tr = np.maximum(hi[-15:] - lo[-15:],
                        np.maximum(abs(hi[-15:] - clo[-16:-1]),
                                   abs(lo[-15:] - clo[-16:-1])))
        atr_val = float(np.mean(tr))
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE paper_positions SET atr_entry=? WHERE code=?", (atr_val, code))
        conn.commit()
        conn.close()

    # ── 数据查询 ──

    def _market_value(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT shares, current_price FROM paper_positions"
        ).fetchall()
        conn.close()
        return sum(s * (p or 0) for s, p in rows)

    def _position_count(self):
        conn = sqlite3.connect(self.db_path)
        cnt = conn.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]
        conn.close()
        return cnt

    def _snapshot_equity(self, today, market_state):
        conn = sqlite3.connect(self.db_path)
        mkt_val = self._market_value()
        total = self.cash + mkt_val
        state = market_state.get("state", "oscillation") if market_state else "oscillation"
        pos_limit = market_state.get("pos_limit", _POS_LIMITS.get(state, 0.4)) if market_state else 0.4
        conn.execute(
            "INSERT OR REPLACE INTO paper_equity VALUES (?,?,?,?,?,?)",
            (today.strftime("%Y-%m-%d"), round(self.cash, 2), round(mkt_val, 2),
             round(total, 2), pos_limit, state)
        )
        conn.commit()
        conn.close()

    def _save_signals(self, signals_df, today):
        if signals_df is None or signals_df.empty:
            return
        conn = sqlite3.connect(self.db_path)
        date_str = today.strftime("%Y-%m-%d")
        for _, row in signals_df.iterrows():
            conn.execute(
                "INSERT OR IGNORE INTO paper_signals "
                "(date, code, name, close, volume_ratio, deviation, score, industry) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (date_str, row["code"], row.get("name", ""),
                 float(row["close"]), float(row.get("volume_ratio", 0)),
                 float(row.get("deviation", 0)), float(row.get("score", 0)),
                 row.get("industry", ""))
            )
        conn.commit()
        conn.close()

    # ── UI 查询接口 ──

    def refresh_spot_prices(self):
        """获取持仓股票实时行情，更新数据库中的 current_price 和盈亏"""
        conn = sqlite3.connect(self.db_path)
        positions = conn.execute(
            "SELECT code, entry_price FROM paper_positions"
        ).fetchall()
        if not positions:
            conn.close()
            return

        codes = {p[0] for p in positions}
        entry_map = {p[0]: p[1] for p in positions}
        updated = 0

        # 1. 优先从 stock_daily 拿今日收盘数据（15:35 后有数据）
        today = datetime.now().strftime("%Y-%m-%d")
        for code, entry_price in positions:
            row = conn.execute(
                "SELECT close FROM stock_daily WHERE code=? AND date=?",
                (code, today)
            ).fetchone()
            if row:
                close = float(row[0])
                pnl = close / entry_price - 1 if entry_price > 0 else 0
                conn.execute(
                    "UPDATE paper_positions SET current_price=?, pnl=?, pnl_pct=? WHERE code=?",
                    (close, round(pnl, 4), round(pnl, 4), code)
                )
                updated += 1

        # 2. 剩余未更新的走实时行情（直接调用新浪单个股票接口，轻量）
        if updated < len(positions):
            try:
                import requests as _req
                _SZ_NEW = {"0", "3"}  # 深圳: 000/002/300
                _SH_NEW = {"6"}       # 上海: 600/601/603/605
                sina_codes = ",".join(
                    f"sh{c}" if c[0] in _SH_NEW else f"sz{c}" for c in codes
                )
                resp = _req.get(
                    f"http://hq.sinajs.cn/list={sina_codes}",
                    headers={"Referer": "https://finance.sina.com.cn"},
                    timeout=10,
                )
                resp.encoding = "gbk"
                for line in resp.text.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("=\"")
                    if len(parts) < 2:
                        continue
                    data = parts[1].rstrip("\";")
                    fields = data.split(",")
                    if len(fields) < 4:
                        continue
                    code = parts[0].split("_")[-1].lstrip("sh").lstrip("sz")
                    close = float(fields[3]) if fields[3] else 0  # 最新价
                    if close <= 0:
                        continue
                    entry_price = entry_map.get(code, 0)
                    pnl = close / entry_price - 1 if entry_price > 0 else 0
                    conn.execute(
                        "UPDATE paper_positions SET current_price=?, pnl=?, pnl_pct=? WHERE code=?",
                        (close, round(pnl, 4), round(pnl, 4), code)
                    )
                    updated += 1
                    logging.info("实时更新 %s: %.2f (%.2f%%)", code, close, pnl * 100)
            except Exception as e:
                logging.warning("实时行情更新失败: %s", e)

        if updated:
            logging.info("持仓价格更新: %d/%d 只", updated, len(positions))
        conn.commit()
        conn.close()

    def get_positions(self):
        """获取持仓（含止损检查 + 实时价格刷新）"""
        self.refresh_spot_prices()
        self.emergency_exit_check()
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql("SELECT * FROM paper_positions", conn)
        conn.close()
        return df

    def emergency_exit_check(self):
        try:
            conn = sqlite3.connect(self.db_path)
            positions = conn.execute(
                "SELECT code, name, shares, entry_price, current_price, entry_date FROM paper_positions"
            ).fetchall()
            conn.close()
            for code, name, shares, entry_p, curr_p, entry_date_str in positions:
                if not curr_p or curr_p <= 0:
                    continue
                pnl = curr_p / entry_p - 1
                if pnl <= -0.07:
                    from datetime import datetime
                    import pandas as pd
                    import logging
                    today = datetime.now()
                    hold = (today - pd.Timestamp(entry_date_str)).days
                    logging.warning("紧急止损触发: %s(%s) 盈亏%.2f%%", name, code, pnl*100)
                    self.close_position(code, curr_p, "止损", today)
        except Exception as e:
            import logging
            logging.error("紧急止损检查异常: %s", e)

    def get_trades(self):
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql("SELECT * FROM paper_trades ORDER BY id DESC", conn)
        conn.close()
        return df

    def get_equity_curve(self):
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql("SELECT * FROM paper_equity ORDER BY date", conn)
        conn.close()
        return df

    def get_today_signals(self, date=None):
        conn = sqlite3.connect(self.db_path)
        if date:
            d = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
            df = pd.read_sql("SELECT * FROM paper_signals WHERE date=? ORDER BY score DESC", conn, params=(d,))
        else:
            df = pd.read_sql("SELECT * FROM paper_signals ORDER BY date DESC, score DESC LIMIT 50", conn)
        conn.close()
        return df

    def get_summary(self):
        conn = sqlite3.connect(self.db_path)
        # 交易统计
        sells = pd.read_sql(
            "SELECT * FROM paper_trades WHERE action='sell'", conn
        )
        # 持仓统计
        pos_count = conn.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]
        # 权益
        eq = pd.read_sql("SELECT * FROM paper_equity ORDER BY date", conn)
        conn.close()

        total_trades = len(sells)
        wins = sells[sells["pnl"] > 0] if not sells.empty else pd.DataFrame()
        losses = sells[sells["pnl"] <= 0] if not sells.empty else pd.DataFrame()

        summary = {
            "position_count": pos_count,
            "total_trades": total_trades,
            "win_rate": round(len(wins) / total_trades * 100, 1) if total_trades > 0 else 0,
            "total_pnl": round(sells["pnl"].sum(), 2) if not sells.empty else 0,
            "total_pnl_pct": round((sells["pnl"].sum() / self.initial_capital) * 100, 2) if not sells.empty else 0,
            "cash": round(self.cash, 2),
            "consecutive_losses": self._consecutive_losses,
        }
        if not sells.empty:
            summary["avg_win"] = round(wins["pnl_pct"].mean() * 100, 2) if not wins.empty else 0
            summary["avg_loss"] = round(losses["pnl_pct"].mean() * 100, 2) if not losses.empty else 0
            summary["profit_ratio"] = round(abs(summary["avg_win"] / summary["avg_loss"]), 2) if summary["avg_loss"] != 0 else 0
        if not eq.empty:
            first_eq = eq.iloc[0]["total_equity"]
            last_eq = eq.iloc[-1]["total_equity"]
            days = len(eq)
            summary["total_return"] = round((last_eq / first_eq - 1) * 100, 2) if first_eq > 0 else 0
            summary["annual_return"] = round(
                ((last_eq / first_eq) ** (252 / max(days, 1)) - 1) * 100, 2
            ) if first_eq > 0 and days > 0 else 0
        return summary
