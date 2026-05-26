"""推送模块 v2.0 — 基础推送 + 日报 + 周报 (Telegram)"""

import re
import requests
import logging
from datetime import datetime, timedelta
from config import PUSH_TYPE, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SERVERCHAN_KEY, TELEGRAM_PROXY, MAX_POSITION_PER_STOCK

# 行业短名映射（CSRC 代码 → 可读简称）
_INDUSTRY_SHORT_NAMES = {
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
    "C13农副食品加工业": "食品加工",
    "C15酒、饮料和精制茶制造业": "酒饮料",
    "C14食品制造业": "食品制造",
    "C17纺织业": "纺织",
    "C25石油、煤炭及其他燃料加工业": "石化燃料",
    "C28化学纤维制造业": "化纤",
    "I64互联网和相关服务": "互联网",
    "J66货币金融服务": "银行",
    "J67资本市场服务": "证券",
    "J68保险业": "保险",
    "K70房地产业": "房地产",
    "F51批发业": "批发",
    "F52零售业": "零售",
    "L72商务服务业": "商务服务",
    "M73研究和试验发展": "科研",
    "M74专业技术服务业": "专业技术",
    "N77生态保护和环境治理业": "环保",
    "Q83卫生": "医疗",
    "R86广播、电视、电影和影视录音制作业": "影视传媒",
    "R87文化艺术业": "文化艺术",
    "C41其他制造业": "其他制造",
    "C42废弃资源综合利用业": "资源回收",
}


def _shorten_industry(name):
    """将行业名转为短名，如 C26化学原料 → 化工"""
    if not name:
        return name
    # 先查映射表
    if name in _INDUSTRY_SHORT_NAMES:
        return _INDUSTRY_SHORT_NAMES[name]
    # 无映射则去掉字母+数字前缀
    return re.sub(r"^[A-Z]\d+", "", name)


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

def _position_advice(score, volume_ratio, deviation, market_state, pos_limit):
    """根据信号强度和市况生成建仓意见"""
    max_per_stock = MAX_POSITION_PER_STOCK  # 单股上限

    # 信号强度分级
    if score > 30:
        strength = "强"
        suggested = min(pos_limit * 0.3, max_per_stock)
    elif score > 15:
        strength = "中"
        suggested = min(pos_limit * 0.2, max_per_stock)
    else:
        strength = "弱"
        suggested = min(pos_limit * 0.1, max_per_stock)

    # 建仓方式
    if deviation < 0.02 and volume_ratio > 1.5:
        method = "可现价建仓"
    elif deviation < 0.02:
        method = "可建仓"
    else:
        method = "回踩20日线建仓"

    # 信号备注
    note_parts = []
    if volume_ratio > 3.0:
        note_parts.append("放量过激")
    elif volume_ratio > 2.0:
        note_parts.append("放量良好")
    if deviation > 0.05:
        note_parts.append("偏离偏大")
    if score > 30:
        note_parts.append("高分信号")
    note = " | ".join(note_parts) if note_parts else "-"

    return strength, suggested, method, note


def _summary_analysis(signals_df, market_state):
    """生成信号总结分析"""
    if signals_df is None or signals_df.empty:
        return ""
    lines = []
    n = len(signals_df)

    # 强度分布
    strong = sum(1 for s in signals_df["score"] if s > 30)
    medium = sum(1 for s in signals_df["score"] if 15 < s <= 30)
    weak = n - strong - medium
    dist_parts = []
    if strong:
        dist_parts.append(f"强{strong}")
    if medium:
        dist_parts.append(f"中{medium}")
    if weak:
        dist_parts.append(f"弱{weak}")
    lines.append(f"- 信号分布: {', '.join(dist_parts)}只")

    # 行业分布
    if "industry" in signals_df.columns:
        top_inds = signals_df["industry"].value_counts().head(3)
        ind_str = " | ".join(f"{_shorten_industry(ind)}({cnt}只)" for ind, cnt in top_inds.items())
        lines.append(f"- 行业集中: {ind_str}")

    # LGB 评分区间（如有）
    if "lgb_score" in signals_df.columns:
        lgb_min = signals_df["lgb_score"].min()
        lgb_max = signals_df["lgb_score"].max()
        lines.append(f"- LGB评分: {lgb_min:.4f} ~ {lgb_max:.4f}")

    # 市况建议
    state_advice = {
        "bull": "多头市场，按信号分批建仓",
        "oscillation": "震荡市，总仓不超过40%，高分信号优先",
        "bear": "熊市仅轻仓参与，严格止损",
        "wait": "数据不足，暂不操作",
    }
    advice = state_advice.get(market_state, "控制仓位，注意风险")
    lines.append(f"- 操作建议: {advice}")

    return "\n".join(lines)


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
    signals_df=None,
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
                name, mom = _shorten_industry(item[0]), item[1] if len(item) > 1 else ""
                inds.append(f"{name}({mom:+.1%})" if isinstance(mom, (int, float)) else name)
            else:
                inds.append(_shorten_industry(str(item)))
        lines.append("【行业TOP5】")
        lines.append("  ".join(inds) + "\n")

    # 信号
    lines.append(f"【信号】触发 *{signal_count}* 只")
    if filter_stats:
        parts = []
        if "base_pool" in filter_stats:
            parts.append(f"基础{filter_stats['base_pool']}")
        if "after_trend" in filter_stats:
            parts.append(f"均线{filter_stats['after_trend']}")
        if "vol_fail" in filter_stats:
            parts.append(f"量能-{filter_stats['vol_fail']}")
        if "div_fail" in filter_stats:
            parts.append(f"底背驰-{filter_stats['div_fail']}")
        if "caisen_fail" in filter_stats:
            parts.append(f"形态-{filter_stats['caisen_fail']}")
        if "industry_filter" in filter_stats and filter_stats["industry_filter"]:
            parts.append(f"行业-{filter_stats['industry_filter']}")
        if "bear_filter" in filter_stats:
            parts.append(f"熊市-{filter_stats['bear_filter']}")
        if "bottleneck" in filter_stats and filter_stats["bottleneck"]:
            parts.append(f"瓶颈-{filter_stats['bottleneck']}")
        if parts:
            lines.append(" > " + " → ".join(parts))
        if filter_stats.get("max_score"):
            lines.append(f"最高评分: {filter_stats['max_score']:.2f}")
    lines.append("")

    # 个股推荐+建仓意见
    if signals_df is not None and not signals_df.empty:
        lines.append("【个股推荐】")
        for i, (_, row) in enumerate(signals_df.head(10).iterrows(), 1):
            name = row.get("name", "")
            code = row.get("code", "")
            score = row.get("score", 0)
            vol_ratio = row.get("volume_ratio", 0)
            dev = row.get("deviation", 0)
            ind = _shorten_industry(row.get("industry", ""))

            strength, pos_advice, method, note = _position_advice(
                score, vol_ratio, dev, market_state, pos_limit
            )

            line = f"{i}. {name}({code})"
            if ind:
                line += f" | {ind}"
            line += f"\n   评分{score:.1f} | 量比{vol_ratio:.1f} | 偏离{dev:+.2%}"
            line += f"\n   [{strength}] {pos_advice:.0%}仓位 | {method}"
            if note != "-":
                line += f" | {note}"
            lines.append(line)
        lines.append("")

    # 总结分析
    lines.append("【总结】")
    if signals_df is not None and not signals_df.empty:
        lines.append(_summary_analysis(signals_df, market_state))
    else:
        parts = []
        if filter_stats:
            parts.append(f"基础池{filter_stats.get('base_pool','?')}只")
            parts.append(f"均线多头{filter_stats.get('after_trend','?')}只")
        if filter_stats and filter_stats.get("bottleneck"):
            parts.append(f"卡在{filter_stats['bottleneck']}过滤环节")
        if parts:
            lines.append("今日无信号，过滤漏斗: " + " → ".join(parts))
        else:
            lines.append("今日无信号，继续观察。")
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
    if PUSH_TYPE == "telegram":
        _send_tg(text)
    elif PUSH_TYPE == "serverchan":
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
    if PUSH_TYPE == "telegram":
        _send_tg(text)
    elif PUSH_TYPE == "serverchan":
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
    if PUSH_TYPE == "telegram":
        _send_tg(msg)
    elif PUSH_TYPE == "serverchan":
        _send_serverchan("中线波段系统启动", msg)


def send(signals_df, market_state, pos_limit):
    """统一推送入口（旧接口）"""
    if PUSH_TYPE == "telegram":
        send_to_telegram(signals_df, market_state, pos_limit)
    elif PUSH_TYPE == "serverchan":
        send_to_serverchan(signals_df, market_state, pos_limit)
    else:
        logging.warning("未知推送类型: %s", PUSH_TYPE)
