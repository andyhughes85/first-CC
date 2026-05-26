"""工具函数 — 交易日历"""

import datetime
import json
import os

# ── A股法定节假日（2025-2026年非周六日休市日）──
# 仅包含调休后工作日休市 + 周末开市（如有），日常周末由 weekday<5 过滤
_KNOWN_HOLIDAYS = {
    # 2025年
    "2025-01-01",  # 元旦
    *[f"2025-01-{d:02d}" for d in range(28, 32)],  # 春节 1/28-31
    *[f"2025-02-{d:02d}" for d in range(1, 5)],    # 春节 2/1-4
    "2025-04-04",  # 清明 4/4-6
    "2025-05-01", "2025-05-02",  # 劳动节 5/1-2
    *[f"2025-05-{d:02d}" for d in range(31, 32)],  # 端午 5/31
    *[f"2025-06-{d:02d}" for d in range(1, 3)],    # 端午 6/1-2
    *[f"2025-10-{d:02d}" for d in range(1, 8)],    # 国庆 10/1-7
    # 2026年
    "2026-01-01",
    *[f"2026-02-{d:02d}" for d in range(16, 23)],  # 春节 2/16-22
    "2026-04-06",  # 清明 4/6
    "2026-05-01",  # 劳动节 5/1
    *[f"2026-06-{d:02d}" for d in range(22, 24)],  # 端午 6/22-23
    *[f"2026-10-{d:02d}" for d in range(1, 8)],    # 国庆 10/1-7
}

# ── 调休后需要补班的周末交易日（周六/日开市）──
_KNOWN_WEEKEND_TRADE = {
    "2025-01-26",  # 周日 补春节
    "2025-02-08",  # 周六 补春节
    "2025-04-27",  # 周日 补劳动节
    "2026-02-14", "2026-02-15",  # 周末补春节
    "2026-04-26",  # 周末补劳动节
    "2026-09-27", "2026-10-10",  # 周末补国庆
}

_TRADE_CACHE = None
_CACHE_FILE = "trade_calendar_cache.json"


def _fetch_calendar():
    """从 Sina 获取交易日历，缓存到 JSON"""
    global _TRADE_CACHE
    if _TRADE_CACHE is not None:
        return _TRADE_CACHE
    # 尝试从本地缓存加载
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE) as f:
                _TRADE_CACHE = set(json.load(f))
                return _TRADE_CACHE
        except Exception:
            pass
    # 从 Sina 拉取
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        dates = set()
        for d in cal["trade_date"]:
            if hasattr(d, "date"):
                dates.add(str(d.date()))
            else:
                dates.add(str(d)[:10])
        # 缓存到文件
        try:
            with open(_CACHE_FILE, "w") as f:
                json.dump(sorted(dates), f)
        except Exception:
            pass
        _TRADE_CACHE = dates
        return dates
    except Exception:
        return None


def is_trade_day(dt=None):
    """判断是否为A股交易日 — 三层校验：API缓存 → 内置假日表 → 周末"""
    if dt is None:
        dt = datetime.datetime.now()
    if isinstance(dt, datetime.datetime):
        dt = dt.date()
    ds = str(dt)
    wd = dt.weekday()

    # 第一层：API 日历缓存
    cal = _fetch_calendar()
    if cal is not None:
        return ds in cal

    # 第二层：内置假日表
    if ds in _KNOWN_WEEKEND_TRADE:
        return True  # 调休工作日，即使周末也是交易日
    if ds in _KNOWN_HOLIDAYS:
        return False  # 法定假日，即使工作日也休市
    return wd < 5  # 第三层：基本周末过滤


def previous_trade_day(dt=None):
    """获取上一个交易日"""
    if dt is None:
        dt = datetime.datetime.now()
    if isinstance(dt, datetime.datetime):
        dt = dt.date()
    for i in range(1, 15):
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
    for i in range(1, 15):
        candidate = dt + datetime.timedelta(days=i)
        if is_trade_day(candidate):
            return candidate
    return dt + datetime.timedelta(days=1)
