"""后台定时调度 — 交易日 15:35 / 18:00 自动跑策略 + 盘中预警"""
import schedule
import time
import logging
from datetime import datetime, time as dtime
from pipeline import daily_job
from intraday_watch import run as intraday_watch
from utils import is_trade_day

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="trading_bot.log",
)
log = logging.getLogger("scheduler")


def job():
    try:
        now = datetime.now()
        if not is_trade_day(now):
            log.info("非交易日，跳过定时执行")
            return
        log.info("定时任务触发")
        daily_job()
        log.info("定时任务完成")
    except Exception as e:
        log.error("定时任务失败: %s", e, exc_info=True)


def watch_job():
    try:
        now = datetime.now()
        if not is_trade_day(now):
            return
        log.info("盘中预警触发")
        intraday_watch()
    except Exception as e:
        log.error("盘中预警失败: %s", e, exc_info=True)


# 盘中预警（交易时段每2小时）
for t in ["10:00", "11:00", "13:30", "14:30"]:
    schedule.every().day.at(t).do(watch_job)


# 先检查当前时间是否已过今日的执行点
now = datetime.now()
if now.hour < 15 or (now.hour == 15 and now.minute < 35):
    schedule.every().day.at("15:35").do(job)
    schedule.every().day.at("18:00").do(job)
    log.info("今日 15:35 / 18:00 定时任务已设置")
elif now.hour < 18 or (now.hour == 18 and now.minute < 0):
    schedule.every().day.at("18:00").do(job)
    log.info("今日 18:00 定时任务已设置")
else:
    # 今日已过执行时间，明天生效
    schedule.every().day.at("15:35").do(job)
    schedule.every().day.at("18:00").do(job)
    log.info("今日已过执行时间，明日 15:35 / 18:00 生效")

log.info("调度器启动完成，每 60 秒检查一次")

while True:
    schedule.run_pending()
    time.sleep(60)
