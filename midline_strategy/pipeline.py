"""主流程 — 定时任务调度"""

import schedule
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
from data_fetcher import fetch_daily_data
from market_state import judge_market_state, add_index_indicators
from signal_engine import generate_signals
from push_service import send, send_test, send_daily_report, send_weekly_report
from utils import is_trade_day
from config import DB_PATH, SCHEDULE_TIME, SCHEDULE_RETRY_TIME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="trading_bot.log",
)

# 连续空仓计数器
_consecutive_empty = 0
_daily_state_history = []  # [(date, state, pos_limit, reason), ...]


def get_hot_industries():
    """简易行业动量筛选（返回前N个申万一级行业）"""
    try:
        import akshare as ak

        df = ak.stock_board_industry_name_ths()
        names = df["name"].tolist()
        return names[:5] if len(names) >= 5 else names
    except Exception as e:
        logging.warning("行业数据获取失败: %s，使用默认列表", e)
        return ["电子", "医药生物", "电力设备", "食品饮料", "汽车"]


def daily_job():
    """每日定时任务"""
    global _consecutive_empty, _daily_state_history

    logging.info("开始日线任务")
    try:
        data = fetch_daily_data()
        if data is None or data["index"].empty:
            logging.warning("数据获取失败，退出")
            return

        index_df = data["index"].copy()
        index_df = add_index_indicators(index_df)
        market_info = judge_market_state(index_df)
        ms, pos = market_info["state"], market_info["pos_limit"]
        logging.info("市场状态: %s, 仓位上限: %.0f%%", ms, pos * 100)

        hot = get_hot_industries()
        logging.info("强势行业: %s", hot)

        stocks_df = data.get("stocks", pd.DataFrame())
        signals, filter_stats = generate_signals(stocks_df, hot, ms)

        signal_count = len(signals)
        if signal_count > 0:
            _consecutive_empty = 0
            logging.info("触发 %d 只个股信号", signal_count)
        else:
            _consecutive_empty += 1
            logging.info("今日无信号（连续空仓 %d 天）", _consecutive_empty)

        # 记录状态历史
        _daily_state_history.append((
            datetime.now().strftime("%Y-%m-%d"), ms, pos, market_info.get("trend_detail", "")
        ))

        # 推送日报
        send_daily_report(
            market_state=ms,
            pos_limit=pos,
            index_close=market_info["index_close"],
            index_pct=market_info["index_pct"],
            atr_rank=market_info["atr_rank"],
            amt_rank=market_info["amt_rank"],
            trend_detail=market_info["trend_detail"],
            hot_industries=hot,
            signal_count=signal_count,
            filter_stats=filter_stats,
            consecutive_empty=_consecutive_empty,
        )
    except Exception as e:
        logging.error("任务失败: %s", e, exc_info=True)


def weekly_job():
    """每周五定时周报"""
    global _daily_state_history

    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    week_start = monday.strftime("%Y-%m-%d")
    week_end = today.strftime("%Y-%m-%d")

    # 本周状态
    week_states = [s for s in _daily_state_history if s[0] >= week_start]

    send_weekly_report(
        week_start=week_start,
        week_end=week_end,
        daily_states=week_states,
        suggestion="可考虑增加周中行业动量再排序。",
    )


if __name__ == "__main__":
    logging.info("中线波段策略系统启动")
    send_test()
    schedule.every().day.at(SCHEDULE_TIME).do(daily_job)
    schedule.every().day.at(SCHEDULE_RETRY_TIME).do(daily_job)
    schedule.every().friday.at("18:00").do(weekly_job)
    logging.info("定时任务已设置: %s, %s (周五+周报18:00)", SCHEDULE_TIME, SCHEDULE_RETRY_TIME)

    while True:
        schedule.run_pending()
        time.sleep(60)
