"""中线策略 — 虚拟盘监控面板"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import subprocess
import os

st.set_page_config(page_title="中线策略监控", page_icon="📊", layout="wide")

# ── 样式 ──
st.markdown("""
<style>
/* 全局 */
#root > div:first-child { padding: 0 1rem; }
.stTabs [data-baseweb="tab-list"] { gap: 0; }
.stTabs [data-baseweb="tab"] { padding: 0.5rem 1.2rem; }
/* 卡片 */
div[data-testid="stMetric"] {
    background: #1E2128; border-radius: 8px; padding: 12px 16px;
    border: 1px solid #2E3138;
}
div[data-testid="stMetric"] label { color: #888; font-size: 0.8rem; }
/* 状态徽章 */
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
         font-size: 0.8rem; font-weight: 600; }
.bull { background: #00C85322; color: #00C853; border: 1px solid #00C85355; }
.bear { background: #FF174422; color: #FF1744; border: 1px solid #FF174455; }
.oscillation { background: #FFD60022; color: #FFD600; border: 1px solid #FFD60055; }
.wait { background: #88888822; color: #888; border: 1px solid #88888855; }
/* 表格 */
.dataframe { font-size: 0.85rem; }
td.pnl-positive { color: #00C853; font-weight: 600; }
td.pnl-negative { color: #FF1744; font-weight: 600; }
/* 按钮配色 */
.stButton > button { border-radius: 6px; font-weight: 500; }
.stButton > button[kind="primary"] { background: #00C853; color: #000; }
</style>
""", unsafe_allow_html=True)

# ── 侧栏 ──
with st.sidebar:
    st.title("⚙️ 控制面板")

    # 系统状态
    st.subheader("系统状态")
    now = datetime.now()
    st.caption(f"当前时间: {now.strftime('%Y-%m-%d %H:%M')}")

    # 操作按钮
    st.subheader("操作")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ 跑策略", use_container_width=True):
            with st.spinner("执行中..."):
                try:
                    r = subprocess.run(
                        ["python", "-c", "from pipeline import daily_job; daily_job()"],
                        cwd=os.path.dirname(__file__) or ".",
                        capture_output=True, text=True, timeout=120,
                        encoding="utf-8", errors="replace"
                    )
                    st.success("✅ 策略执行完成")
                    st.caption(r.stdout[-300:] if r.stdout else "无输出")
                except subprocess.TimeoutExpired:
                    st.error("⏰ 超时")
                except Exception as e:
                    st.error(f"❌ {e}")
    with col2:
        if st.button("🔄 刷新数据", use_container_width=True):
            st.rerun()

    # 快捷导航
    st.subheader("导航")
    st.page_link("app.py", label="📊 仪表盘", use_container_width=True)

    # 底部参数
    st.divider()
    st.caption(f"初始资金: ¥1,000,000")
    st.caption(f"单股上限: 10% | 最大持仓: 10只")
    st.caption(f"止损: -7% | 时间止损: 15天")

# ── 数据加载 ──
@st.cache_data(ttl=30)
def load_data():
    from paper_trader import PaperTrader
    from market_state import judge_market_state, add_index_indicators
    from data_fetcher import fetch_index_incremental, load_cached

    trader = PaperTrader()
    positions = trader.get_positions()
    trades = trader.get_trades()
    equity = trader.get_equity_curve()
    summary = trader.get_summary()

    # 市场状态
    market_info = {"state": "wait", "pos_limit": 0, "index_close": 0, "trend_detail": "未获取"}
    try:
        idx = fetch_index_incremental()
        if idx is not None and len(idx) > 60:
            idx = add_index_indicators(idx)
            market_info = judge_market_state(idx)
    except Exception:
        pass

    return {
        "trader": trader, "positions": positions, "trades": trades,
        "equity": equity, "summary": summary, "market": market_info,
    }

data = load_data()
trader = data["trader"]
market = data["market"]
summary = data["summary"]

# ── Tab1: 仪表盘 ──
tab1, tab2, tab3 = st.tabs(["📊 仪表盘", "💼 持仓", "📋 交易记录"])

with tab1:
    # --- KPI 行 ---
    state = market.get("state", "wait")
    state_labels = {"bull": "🐂 牛市", "oscillation": "⚖️ 震荡", "bear": "🐻 熊市", "wait": "⏳ 等待"}
    pos_limit = market.get("pos_limit", 0)

    cols = st.columns(4)
    with cols[0]:
        badge_class = state if state in ("bull", "bear", "oscillation") else "wait"
        st.markdown(
            f'<div class="badge {badge_class}" style="font-size:1rem;padding:6px 16px">'
            f'{state_labels.get(state, state)} 仓位上限{pos_limit:.0%}</div>',
            unsafe_allow_html=True
        )
        st.caption(market.get("trend_detail", ""))
    with cols[1]:
        st.metric("持仓数量", summary.get("position_count", 0))
    with cols[2]:
        pnl_val = summary.get("total_pnl_pct", 0)
        st.metric("累计盈亏", f"{pnl_val:+.2f}%", delta=f"{pnl_val:+.2f}%" if pnl_val != 0 else None)
    with cols[3]:
        st.metric("交易次数", summary.get("total_trades", 0))

    # --- 权益曲线 ---
    eq = data["equity"]
    if not eq.empty:
        st.subheader("权益曲线")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eq["date"], y=eq["total_equity"],
            mode="lines", name="总权益",
            line=dict(color="#00C853", width=2),
            fill="tozeroy", fillcolor="rgba(0,200,83,0.08)"
        ))
        fig.add_trace(go.Scatter(
            x=eq["date"], y=eq["cash"],
            mode="lines", name="现金",
            line=dict(color="#448AFF", width=1, dash="dash")
        ))
        # 标注仓位上限区域
        if "pos_limit" in eq.columns:
            max_val = eq["total_equity"].max()
            eq["max_equity"] = eq["pos_limit"] * 1000000
            # 显示市场状态色块
            if "market_state" in eq.columns:
                colors = {"bull": "rgba(0,200,83,0.3)", "oscillation": "rgba(255,214,0,0.3)",
                          "bear": "rgba(255,23,68,0.3)", "wait": "rgba(136,136,136,0.3)"}
                for ms in eq["market_state"].unique():
                    mask = eq["market_state"] == ms
                    if mask.any():
                        eq_sub = eq[mask]
                        fig.add_vrect(
                            x0=eq_sub["date"].iloc[0], x1=eq_sub["date"].iloc[-1],
                            fillcolor=colors.get(ms, "rgba(136,136,136,0.15)"),
                            layer="below", line_width=0, opacity=0.5,
                        )

        fig.update_layout(
            height=350, margin=dict(l=0, r=0, t=0, b=0),
            plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
            font=dict(color="#FAFAFA"), hovermode="x unified",
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="#2E3138"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- 当前持仓 ---
    pos = data["positions"]
    st.subheader("当前持仓")
    if not pos.empty:
        # 计算浮动盈亏显示
        display = pos[["code", "name", "entry_price", "current_price", "shares", "pnl_pct", "market_state"]].copy()
        display.columns = ["代码", "名称", "入场价", "现价", "股数", "盈亏", "入场状态"]
        display["盈亏"] = display["盈亏"].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "-")
        display["市值"] = (pos["current_price"] * pos["shares"]).apply(lambda x: f"¥{x:,.0f}")

        def color_pnl(v):
            try:
                return "color: #00C853" if float(v.strip("%")) > 0 else "color: #FF1744"
            except:
                return ""
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("暂无持仓")

    # --- 今日信号 ---
    st.subheader("最近信号")
    try:
        signals = trader.get_today_signals()
        if not signals.empty:
            sig_display = signals[["date", "code", "name", "score", "close", "volume_ratio", "industry"]].head(10).copy()
            sig_display.columns = ["日期", "代码", "名称", "评分", "收盘价", "量比", "行业"]
            sig_display["评分"] = sig_display["评分"].round(2)
            st.dataframe(sig_display, use_container_width=True, hide_index=True)
        else:
            st.info("暂无信号记录")
    except Exception as e:
        st.caption(f"信号加载: {e}")

with tab2:
    st.subheader("持仓明细")
    pos = data["positions"]
    if not pos.empty:
        display = pos[["code", "name", "entry_date", "entry_price", "current_price",
                       "shares", "pnl_pct", "highest_close", "trailing_activated", "market_state"]].copy()
        display.columns = ["代码", "名称", "入场日", "入场价", "现价",
                           "股数", "盈亏%", "最高价", "移动止盈", "市场状态"]
        display["盈亏%"] = display["盈亏%"].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "-")
        display["移动止盈"] = display["移动止盈"].apply(lambda x: "✅ 已激活" if x else "—")

        # 着色
        def highlight_pnl(row):
            try:
                v = float(str(row["盈亏%"]).strip("%"))
                return ["color: #00C853" if v > 0 else "color: #FF1744" if v < 0 else ""] * len(row)
            except:
                return [""] * len(row)
        st.dataframe(display, use_container_width=True, hide_index=True)

        # 平仓操作（每行一个按钮）
        st.subheader("手动平仓")
        cols = st.columns(min(len(pos), 5))
        for i, (_, row) in enumerate(pos.iterrows()):
            with cols[i % 5]:
                if st.button(f"平仓 {row['code']}", key=f"close_{row['code']}"):
                    with st.spinner(f"平仓 {row['name']}..."):
                        trader.close_position(
                            row["code"], row["current_price"] or row["entry_price"],
                            "手动平仓", datetime.now()
                        )
                    st.success(f"✅ {row['name']} 已平仓")
                    st.rerun()
    else:
        st.info("暂无持仓")

with tab3:
    st.subheader("交易记录")
    trades = data["trades"]
    if not trades.empty:
        # 筛选
        col1, col2 = st.columns(2)
        with col1:
            code_filter = st.text_input("代码筛选", "")
        with col2:
            show_all = st.checkbox("显示全部", True)

        display = trades[["date", "code", "name", "action", "price", "shares", "pnl", "pnl_pct", "reason", "hold_days"]].copy()
        if code_filter:
            display = display[display["code"].str.contains(code_filter, na=False)]
        if not show_all:
            display = display.head(50)

        display.columns = ["日期", "代码", "名称", "方向", "价格", "股数", "盈亏", "盈亏%", "原因", "持有天数"]
        display["盈亏%"] = display["盈亏%"].apply(
            lambda x: f"{x:+.2%}" if pd.notna(x) and x != 0 else "-"
        )
        display["盈亏"] = display["盈亏"].apply(
            lambda x: f"¥{x:+,.2f}" if pd.notna(x) and x != 0 else "-"
        )
        st.dataframe(display, use_container_width=True, hide_index=True)

        # 绩效统计
        st.subheader("绩效统计")
        sells = trades[trades["action"] == "sell"].copy()
        if not sells.empty:
            kpi_cols = st.columns(5)
            with kpi_cols[0]:
                st.metric("总交易", len(sells))
            with kpi_cols[1]:
                wins = sells[sells["pnl"] > 0]
                win_rate = len(wins) / len(sells) * 100 if len(sells) > 0 else 0
                st.metric("胜率", f"{win_rate:.1f}%")
            with kpi_cols[2]:
                avg_win = wins["pnl_pct"].mean() * 100 if not wins.empty else 0
                st.metric("平均盈利", f"{avg_win:.2f}%")
            with kpi_cols[3]:
                losses = sells[sells["pnl"] <= 0]
                avg_loss = losses["pnl_pct"].mean() * 100 if not losses.empty else 0
                st.metric("平均亏损", f"{avg_loss:.2f}%")
            with kpi_cols[4]:
                profit_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
                st.metric("盈亏比", f"{profit_ratio:.2f}")

            # 月度盈亏热力图
            sells["date"] = pd.to_datetime(sells["date"])
            sells["year_month"] = sells["date"].dt.strftime("%Y-%m")
            monthly = sells.groupby("year_month")["pnl_pct"].sum() * 100
            if len(monthly) > 1:
                st.subheader("月度收益")
                fig = px.bar(
                    x=monthly.index, y=monthly.values,
                    color=monthly.values,
                    color_continuous_scale=["#FF1744", "#FFD600", "#00C853"],
                    labels={"x": "", "y": "月收益%"}, height=250
                )
                fig.update_layout(
                    plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
                    font=dict(color="#FAFAFA"), showlegend=False,
                    xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="#2E3138"),
                    margin=dict(l=0, r=0, t=0, b=0)
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无交易记录")
