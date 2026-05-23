"""推送模块 v2.0 — 基础推送 + 日报 + 周报 (Telegram)"""

import requests
import logging
from datetime import datetime, timedelta
from config import PUSH_TYPE, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SERVERCHAN_KEY, TELEGRAM_PROXY


def _tg_session():
    s = requests.Session()
    if TELEGRAM_PROXY:
        s.proxies = {"https": TELEGRAM_PROXY, "http": TELEGRAM_PROXY}
    s.timeout = 15
    return s


def _send_tg(text):
    """发送纯文本到 Telegram"""
    try:
        sess = _tg_session()
        resp = sess.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        )
        if resp.json().get("ok"):
            logging.info("Telegram推送成功")
        else:
            logging.warning("Telegram推送失败: %s", resp.text)
    except Exception as e:
        logging.error("Telegram推送异常: %s", e)


def _send_serverchan(title, desp):
    """发送到 Server酱"""
    if not SERVERCHAN_KEY:
        return
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
            data={"title": title, "desp": desp}, timeout=10,
        )
        result = resp.json()
        if result.get("code") == 0:
            logging.info("Server酱推送成功")
        else:
            logging.warning("Server酱推送失败: %s", result.get("message", resp.text))
    except Exception as e:
        logging.error("Server酱推送异常: %s", e)


# ==================== 日报 ====================

def send_daily_report(
    market_state: str,
    pos_limit: float,
    index_close: float,
    index_pct: float,
    atr_rank: float,
    amt_rank: float,
    trend_detail: str,
    hot_industries: list,
    signal_count: int,
    filter_stats: dict = None,
    vol_anomalies: list = None,
    pe_cheap: list = None,
    consecutive_empty: int = 0,
):
    """推送中线波段日报到 Telegram"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"📊 中线波段日报 {today_str}\n"]

    # 市场
    vol_label = "放量" if amt_rank > 0.6 else "缩量"
    wave_label = "高波" if atr_rank > 0.7 else "低波"
    pct_label = f"{index_pct:+.2%}"
    lines.append(f"【市场】{market_state} | 仓位≤{pos_limit:.0%}")
    lines.append(f"沪深300: {index_close:.2f} ({pct_label}) | {vol_label} | {wave_label}")
    lines.append(f"趋势: {trend_detail}\n")

    # 行业
    if hot_industries:
        inds = []
        for item in hot_industries[:5]:
            if isinstance(item, (list, tuple)):
                name, mom = item[0], item[1] if len(item) > 1 else ""
                inds.append(f"{name}({mom:+.1%})" if isinstance(mom, (int, float)) else name)
            else:
                inds.append(str(item))
        lines.append("【行业TOP5】")
        lines.append("  ".join(inds) + "\n")

    # 信号
    lines.append(f"【信号】触发 *{signal_count}* 只")
    if filter_stats:
        parts = []
        if "base_pool" in filter_stats:
            parts.append(f"基础池{filter_stats['base_pool']}")
        if "after_trend" in filter_stats:
            parts.append(f"均线过滤{filter_stats['after_trend']}")
        if "vol_fail" in filter_stats:
            parts.append(f"量能过滤{filter_stats['vol_fail']}")
        if "bear_filter" in filter_stats:
            parts.append(f"熊市过滤{filter_stats['bear_filter']}")
        if parts:
            lines.append(" > " + " → ".join(parts))
        if filter_stats.get("max_score"):
            lines.append(f"最高评分: {filter_stats['max_score']:.2f}")
    lines.append("")

    # 量能异常
    if vol_anomalies:
        lines.append("⭐ 量能异常")
        for item in vol_anomalies[:5]:
            if isinstance(item, (list, tuple)):
                code, name, vtype, ratio, ind = item[0], item[1], item[2], item[3], item[4] if len(item) > 4 else ""
                lines.append(f"  {name}({code}) {vtype} {ratio:.0%} | {ind}")
            else:
                lines.append(f"  {item}")
        lines.append("")

    # 估值洼地
    if pe_cheap:
        lines.append("▼ 估值洼地")
        for item in pe_cheap[:3]:
            if isinstance(item, (list, tuple)):
                code, name, pe, pct, ind = item[0], item[1], item[2], item[3], item[4] if len(item) > 4 else ""
                lines.append(f"  {name}({code}) PE{pe:.1f} (分位{pct:.0%}) | {ind}")
            else:
                lines.append(f"  {item}")
        lines.append("")

    # 风控
    lines.append("【风控】")
    lines.append(f"单股≤10% | 止损-7% | 连空{consecutive_empty}天")
    lines.append("仅供参考，不构成投资建议。尾盘确认信号，次日集合竞价观察承接。")

    text = "\n".join(lines)
    _send_tg(text)
    _send_serverchan(f"中线波段日报 {today_str}", text)


# ==================== 周报 ====================

def send_weekly_report(
    week_start: str,
    week_end: str,
    daily_states: list = None,
    industry_changes: dict = None,
    signal_summary: dict = None,
    top_untriggered: list = None,
    watchlist_vol: list = None,
    watchlist_pe: list = None,
    suggestion: str = "",
):
    """推送中线波段周报到 Telegram"""
    lines = [f"📊 中线波段周报 {week_start} ~ {week_end}\n"]

    # 状态演变
    lines.append("【市场状态演变】")
    if daily_states:
        changes = []
        prev = None
        for date, state, _, reason in daily_states:
            if state != prev:
                changes.append(f"{date} → {state}({reason})" if reason else f"{date} → {state}")
            prev = state
        if changes:
            arrows = " → ".join([c.split(" ")[-1] for c in changes])
            lines.append(arrows)
            lines.append(f"切换: {changes[-1]}")
    else:
        lines.append("本周数据不足")
    lines.append("")

    # 行业变迁
    lines.append("【强势行业变迁】")
    if industry_changes:
        if industry_changes.get("start_top"):
            lines.append(f"周初: {', '.join(industry_changes['start_top'][:5])}")
        if industry_changes.get("end_top"):
            lines.append(f"周末: {', '.join(industry_changes['end_top'][:5])}")
        if industry_changes.get("faded"):
            lines.append(f"退潮: {', '.join(industry_changes['faded'][:3])}⚠️")
    lines.append("")

    # 信号统计
    lines.append("【本周信号统计】")
    if signal_summary:
        total = signal_summary.get("total", 0)
        wins = signal_summary.get("wins", 0)
        losses = signal_summary.get("losses", 0)
        lines.append(f"触发: {total}次 | 胜率: {wins}/{total if total else 1} ({wins/total:.0%})" if total > 0 else "本周无信号")
        for detail in signal_summary.get("details", []):
            lines.append(f"  {detail[0]} {detail[1]} {detail[2]:+.1%}")
        lines.append(f"持仓: {signal_summary.get('holdings', 0)}只")
    lines.append("")

    # 高分未触发
    if top_untriggered:
        lines.append("【高分未触发(TOP3)】")
        for code, name, score, reason in top_untriggered[:3]:
            lines.append(f"  {name}({code}) 评分{score:.2f} | 差在{reason}")
        lines.append("")

    # 观察池
    lines.append("【下周观察池】")
    if watchlist_vol:
        items = [f"{name}({vtype})" for name, vtype in watchlist_vol[:5]]
        lines.append("量能异动: " + ", ".join(items))
    if watchlist_pe:
        items = [f"{name}(PE{pe:.1f})" for name, pe in watchlist_pe[:3]]
        lines.append("估值洼地: " + ", ".join(items))
    if suggestion:
        lines.append(f"建议: {suggestion}")
    lines.append("")
    lines.append("仅供参考，不构成投资建议。")

    text = "\n".join(lines)
    _send_tg(text)
    _send_serverchan(f"中线波段周报 {week_start}~{week_end}", text)


# ==================== 旧接口兼容 ====================

def send_to_telegram(signals_df, market_state, pos_limit):
    """旧版信号推送"""
    if signals_df.empty:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    has_industry = "industry" in signals_df.columns
    industry_line = ""
    if has_industry:
        industries = signals_df["industry"].unique()
        industry_line = f"\n强势行业: {', '.join(industries)}"
    text = f"中线波段信号 {now}\n市场: {market_state} (仓位上限:{pos_limit:.0%}){industry_line}\n\n"
    for _, row in signals_df.iterrows():
        extra = f" | {row['industry']}" if has_industry else ""
        text += f"{row['name']}({row['code']}){extra}\n收盘:{row['close']:.2f} 量比:{row['volume_ratio']:.1f} 偏离20线:{row['deviation']:.2%}\n{row['reason']}\n\n"
    text += "仅供参考，单股<=10%，止损-7%"
    _send_tg(text)


def send_to_serverchan(signals_df, market_state, pos_limit):
    """Server酱推送（保留旧接口）"""
    if signals_df.empty:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    has_industry = "industry" in signals_df.columns
    industry_line = ""
    if has_industry:
        industries = signals_df["industry"].unique()
        industry_line = f"- **强势行业**: {', '.join(industries)}"
    title = f"中线波段信号 {now} ({len(signals_df)}只)"
    desp = (
        f"### 市场状态\n"
        f"- **状态**: {market_state}\n"
        f"- **仓位上限**: {pos_limit:.0%}\n"
        f"{industry_line}\n\n"
        f"### 触发个股（共{len(signals_df)}只）\n\n"
    )
    for _, row in signals_df.iterrows():
        extra = f" | {row['industry']}" if has_industry else ""
        desp += (
            f"**{row['name']}** ({row['code']}){extra}  \n"
            f"收盘: {row['close']:.2f} | "
            f"量比: {row['volume_ratio']:.1f} | "
            f"偏离20线: {row['deviation']:.2%} | "
            f"{row['reason']}  \n\n"
        )
    desp += "---\n尾盘确认信号，次日集合竞价观察承接。仅供参考。"
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
            data={"title": title, "desp": desp}, timeout=10,
        )
        result = resp.json()
        if result.get("code") == 0:
            logging.info("Server酱推送成功")
        else:
            logging.warning("Server酱推送失败: %s", result.get("message", resp.text))
    except Exception as e:
        logging.error("Server酱推送异常: %s", e)


def send_test():
    """发送测试消息"""
    msg = (
        f"中线波段系统启动 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"定时任务: 15:35 / 18:00\n推送: {PUSH_TYPE}"
    )
    _send_tg(msg)


def send(signals_df, market_state, pos_limit):
    """统一推送入口（旧接口）"""
    if PUSH_TYPE == "telegram":
        send_to_telegram(signals_df, market_state, pos_limit)
    elif PUSH_TYPE == "serverchan":
        send_to_serverchan(signals_df, market_state, pos_limit)
    else:
        logging.warning("未知推送类型: %s", PUSH_TYPE)
