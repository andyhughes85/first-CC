"""盘中预警 — 交易时段异动监测 + 推送"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from config import SERVERCHAN_KEY, POOL_MIN_AMOUNT
from push_service import _send_serverchan

log = logging.getLogger("intraday_watch")

# 预警阈值
ALERT_LIMITS = {
    "surge_pct": 0.05,       # 涨幅 ≥ 5%
    "surge_vol_ratio": 2.0,  # 且量比 ≥ 2.0
    "volume_spike": 5.0,     # 量比 ≥ 5.0（纯放量异动）
    "amount_floor": 2e8,     # 最低成交额 2亿（过滤微盘股）
}

_INDUSTRY_SHORT = {
    "C39计算机、通信和其他电子设备制造业": "电子",
    "C35专用设备制造业": "专用设备",
    "C26化学原料和化学制品制造业": "化工",
    "I65软件和信息技术服务业": "软件",
    "C38电气机械和器材制造业": "电气设备",
    "C27医药制造业": "医药",
    "C34通用设备制造业": "通用设备",
    "C36汽车制造业": "汽车",
    "C29橡胶和塑料制品业": "橡塑",
    "C30非金属矿物制品业": "非金属材料",
    "C33金属制品业": "金属制品",
    "D44电力、热力生产和供应业": "电力",
    "C32有色金属冶炼和压延加工业": "有色",
    "C37铁路、船舶、航空航天和其他运输设备制造业": "运输设备",
    "C40仪器仪表制造业": "仪器仪表",
    "C31黑色金属冶炼和压延加工业": "钢铁",
}


def _short_ind(name):
    if not name:
        return ""
    if name in _INDUSTRY_SHORT:
        return _INDUSTRY_SHORT[name]
    import re
    return re.sub(r"^[A-Z]\d+", "", name)


def run():
    import akshare as ak

    log.info("盘中预警: 获取全市场实时行情...")

    spot = None
    # 尝试1: 东财
    try:
        spot = ak.stock_zh_a_spot_em()
    except Exception:
        pass
    # 尝试2: 新浪（降级）
    if spot is None or spot.empty:
        try:
            raw = ak.stock_zh_a_spot()
            if raw is not None and not raw.empty:
                raw = raw.copy()
                raw["代码"] = raw["代码"].str.extract(r"(\d{6})", expand=False)
                raw.rename(columns={"名称": "名称", "最新价": "最新价",
                                    "涨跌幅": "涨跌幅", "成交量": "成交量",
                                    "成交额": "成交额", "量比": "量比",
                                    "市盈率-动态": "市盈率"}, inplace=True)
                spot = raw
        except Exception:
            pass

    if spot is None or spot.empty:
        log.warning("行情数据为空")
        return

    # 清洗
    spot = spot.copy()
    spot["代码"] = spot["代码"].astype(str).str.zfill(6)
    for col in ["最新价", "涨跌幅", "成交量", "成交额", "量比", "市盈率-动态"]:
        spot[col] = pd.to_numeric(spot[col], errors="coerce").fillna(0)

    # 过滤僵尸股
    spot = spot[spot["成交额"] >= ALERT_LIMITS["amount_floor"]]

    now = datetime.now().strftime("%H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    alerts = []

    # 条件1: 放量拉升（涨幅大 + 放量）
    mask_surge = (
        (spot["涨跌幅"] >= ALERT_LIMITS["surge_pct"] * 100)
        & (spot["量比"] >= ALERT_LIMITS["surge_vol_ratio"])
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
        (spot["量比"] >= ALERT_LIMITS["volume_spike"])
        & (spot["涨跌幅"] < ALERT_LIMITS["surge_pct"] * 100)
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
        for a in group[:5]:
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
