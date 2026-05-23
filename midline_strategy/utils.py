"""工具函数"""

import datetime


def is_trade_day(dt=None):
    """判断是否为A股交易日"""
    if dt is None:
        dt = datetime.datetime.now()
    if isinstance(dt, datetime.datetime):
        dt = dt.date()
    try:
        import akshare as ak
        calendar_df = ak.tool_trade_date_hist_sina()
        trade_dates = set(calendar_df["trade_date"].apply(
            lambda x: x.date() if hasattr(x, "date") else x
        ))
        return dt in trade_dates
    except Exception:
        return dt.weekday() < 5


def previous_trade_day(dt=None):
    """获取上一个交易日"""
    if dt is None:
        dt = datetime.datetime.now()
    if isinstance(dt, datetime.datetime):
        dt = dt.date()
    for i in range(1, 10):
        candidate = dt - datetime.timedelta(days=i)
        if is_trade_day(candidate):
            return candidate
    return dt - datetime.timedelta(days=1)


def next_trade_day(dt=None):
    """获取下一个交易日"""
    if dt is None:
        dt = datetime.datetime.now()
    if isinstance(dt, datetime.datetime):
        dt = dt.date()
    for i in range(1, 10):
        candidate = dt + datetime.timedelta(days=i)
        if is_trade_day(candidate):
            return candidate
    return dt + datetime.timedelta(days=1)
