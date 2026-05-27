"""盘中预警 — 交易时段异动监测 + 推送"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from config import (
    SERVERCHAN_KEY, POOL_MIN_AMOUNT,
    ALERT_SURGE_PCT, ALERT_SURGE_VOL_RATIO,
    ALERT_VOLUME_SPIKE, ALERT_AMOUNT_FLOOR, ALERT_MAX_PER_TYPE,
)
from push_service import _send_serverchan, INDUSTRY_SHORT_NAMES

log = logging.getLogger("intraday_watch")


def _short_ind(name):
    if not name:
        return ""
    if name in INDUSTRY_SHORT_NAMES:
        return INDUSTRY_SHORT_NAMES[name]
    import re
    return re.sub(r"^[A-Z]\d+", "", name)


def run():
    try:
        _run()
    except Exception as e:
        log.error("盘中预警异常: %s", e, exc_info=True)


def _get_volume_ratio(spot):
    """获取量比：优先用原始列，缺失时从成交额估算"""
    spot = spot.copy()
    if "量比" in spot.columns:
        return pd.to_numeric(spot["量比"], errors="coerce").fillna(0)
    # 新浪源无量比，用成交额/5日均额估算
    if "成交额" in spot.columns and "amount_ma5" in spot.columns:
        amt = pd.to_numeric(spot["成交额"], errors="coerce").fillna(0)
        ma5 = pd.to_numeric(spot["amount_ma5"], errors="coerce").fillna(0).replace(0, np.nan)
        return (amt / ma5).fillna(1.0).clip(0, 20)
    return pd.Series(1.0, index=spot.index)


def _run():
    import akshare as ak

    log.info("盘中预警: 获取全市场实时行情...")

    spot = None
    # 尝试1: 东财（含量比字段）
    try:
        raw = ak.stock_zh_a_spot_em()
        if raw is not None and not raw.empty:
            raw = raw.copy()
            raw.rename(columns={
                "代码": "代码", "名称": "名称", "最新价": "最新价",
                "涨跌幅": "涨跌幅", "成交量": "成交量", "成交额": "成交额",
                "量比": "量比", "市盈率-动态": "市盈率",
            }, inplace=True)
            spot = raw
    except Exception:
        pass

    # 尝试2: 新浪（降级，无量比字段）
    if spot is None or spot.empty:
        try:
            raw = ak.stock_zh_a_spot()
            if raw is not None and not raw.empty:
                raw = raw.copy()
                raw["代码"] = raw["代码"].str.extract(r"(\d{6})", expand=False)
                raw.rename(columns={
                    "名称": "名称", "最新价": "最新价",
                    "涨跌幅": "涨跌幅", "成交量": "成交量",
                    "成交额": "成交额",
                }, inplace=True)
                spot = raw
        except Exception:
            pass

    if spot is None or spot.empty:
        log.warning("行情数据为空")
        return

    # 清洗
    spot = spot.copy()
    spot["代码"] = spot["代码"].astype(str).str.zfill(6)
    for col in ["最新价", "涨跌幅", "成交量", "成交额"]:
        if col in spot.columns:
            spot[col] = pd.to_numeric(spot[col], errors="coerce").fillna(0)
    spot["量比"] = _get_volume_ratio(spot)
    for col in ["市盈率"]:
        if col in spot.columns:
            spot[col] = pd.to_numeric(spot[col], errors="coerce").fillna(0)

    # 过滤僵尸股
    spot = spot[spot["成交额"] >= ALERT_AMOUNT_FLOOR]

    now = datetime.now().strftime("%H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    alerts = []

    # 条件1: 放量拉升（涨幅大 + 放量）
    mask_surge = (
        (spot["涨跌幅"] >= ALERT_SURGE_PCT * 100)
        & (spot["量比"] >= ALERT_SURGE_VOL_RATIO)
    )
    surge = spot[mask_surge].nlargest(10, "涨跌幅")
    for _, row in surge.iterrows():
        alerts.append({
            "type": "🚀 放量拉升",
            "code": row["代码"],
            "name": row["名称"],
            "pct": row["涨跌幅"],
            "vol_ratio": row["量比"],
            "amount": row["成交额"],
            "industry": _short_ind(row.get("行业", "")),
        })

    # 条件2: 纯放量异动（量比极大）
    mask_vol = (
        (spot["量比"] >= ALERT_VOLUME_SPIKE)
        & (spot["涨跌幅"] < ALERT_SURGE_PCT * 100)
    )
    vol_spike = spot[mask_vol].nlargest(10, "量比")
    for _, row in vol_spike.iterrows():
        alerts.append({
            "type": "📊 放量异动",
            "code": row["代码"],
            "name": row["名称"],
            "pct": row["涨跌幅"],
            "vol_ratio": row["量比"],
            "amount": row["成交额"],
            "industry": _short_ind(row.get("行业", "")),
        })

    if not alerts:
        log.info("今日无异动")
        _send_serverchan(f"盘中预警 {today} {now}", "✅ 当前无异常信号")
        return

    # 按类型分组，每组最多5条
    lines = [f"📡 盘中预警 {today} {now}\n"]
    for atype in ["🚀 放量拉升", "📊 放量异动"]:
        group = [a for a in alerts if a["type"] == atype]
        if not group:
            continue
        lines.append(f"【{atype}】")
        for a in group[:ALERT_MAX_PER_TYPE]:
            ind_str = f" | {a['industry']}" if a['industry'] else ""
            lines.append(
                f"  {a['name']}({a['code']}){ind_str}\n"
                f"    涨幅{a['pct']:+.1f}% 量比{a['vol_ratio']:.1f}"
            )
        lines.append("")

    # 行业集中度
    ind_counts = {}
    for a in alerts:
        if a["industry"]:
            ind_counts[a["industry"]] = ind_counts.get(a["industry"], 0) + 1
    hot_inds = sorted(ind_counts.items(), key=lambda x: -x[1])[:3]
    if hot_inds:
        lines.append("【行业集中】")
        lines.append("  " + " | ".join(f"{ind}({n}只)" for ind, n in hot_inds))
        lines.append("")

    lines.append("仅供参考，不构成投资建议。")
    text = "\n".join(lines)
    _send_serverchan(f"盘中预警 {today} {now} ({len(alerts)}条异动)", text)
    log.info("推送完成: %d 条异动", len(alerts))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    run()
