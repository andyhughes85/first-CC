"""中线策略 — 虚拟盘监控面板"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import subprocess, os

st.set_page_config(page_title="中线策略监控", page_icon="📊", layout="wide")

st.markdown("""
<style>
#root > div:first-child { padding: 0 1rem; }
.stTabs [data-baseweb="tab-list"] { gap: 0; }
.stTabs [data-baseweb="tab"] { padding: 0.5rem 1.2rem; }
div[data-testid="stMetric"] {
    background: #1E2128; border-radius: 8px; padding: 12px 16px;
    border: 1px solid #2E3138;
}
div[data-testid="stMetric"] label { color: #888; font-size: 0.8rem; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
.bull { background: #00C85322; color: #00C853; border: 1px solid #00C85355; }
.bear { background: #FF174422; color: #FF1744; border: 1px solid #FF174455; }
.oscillation { background: #FFD60022; color: #FFD600; border: 1px solid #FFD60055; }
.wait { background: #88888822; color: #888; border: 1px solid #88888855; }
.dataframe { font-size: 0.85rem; }
.stButton > button { border-radius: 6px; font-weight: 500; }
.news-item { padding: 6px 0; border-bottom: 1px solid #1E2128; font-size: 0.85rem; line-height: 1.4; }
.news-tag { display: inline-block; font-size: 0.7rem; padding: 1px 6px; border-radius: 4px; background: #1E2128; color: #888; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

# ── 引擎初始化 ──
# 缓存 pipeline 模块（含 LGB 模型），避免每次点击重复加载
@st.cache_resource
def _init_engine():
    from pipeline import daily_job, get_last_run_info, lgb_warmup
    lgb_warmup()  # 预热 LGB 模型到内存（首次约25s，后续 rerun 复用缓存）
    return daily_job, get_last_run_info

_daily_job, _get_last_run_info = _init_engine()

# ── 数据加载 ──
from paper_trader import PaperTrader
from market_state import judge_market_state, add_index_indicators
from data_fetcher import fetch_index_incremental

_trader = PaperTrader()
market = {"state":"wait","pos_limit":0,"index_close":0,"index_pct":0,"trend_detail":"未获取"}
try:
    idx = fetch_index_incremental()
    if idx is not None and len(idx) > 60:
        idx = add_index_indicators(idx)
        market = judge_market_state(idx)
except: pass

positions = _trader.get_positions()
trades = _trader.get_trades()
equity = _trader.get_equity_curve()
summary = _trader.get_summary()
try: signals_df = _trader.get_today_signals()
except: signals_df = pd.DataFrame()

state = market.get("state","wait")
pos_limit = market.get("pos_limit",0)
state_labels = {"bull":"🐂 牛市","oscillation":"⚖️ 震荡","bear":"🐻 熊市","wait":"⏳ 等待"}
now = datetime.now()

# ── 侧栏 ──
with st.sidebar:
    st.title("⚙️ 控制面板")
    st.subheader("系统状态")
    st.caption(f"{now.strftime('%Y-%m-%d %H:%M')}")

    last_run = _get_last_run_info()
    today_str = now.strftime("%Y-%m-%d")
    already_ran_today = last_run and last_run[0] == today_str
    state_str = last_run[1] if already_ran_today else None
    state_emoji = {"bull": "🐂", "oscillation": "⚖️", "bear": "🐻", "wait": "⏳"}.get(state_str, "")

    col1, col2 = st.columns(2)
    with col1:
        btn_label = "▶ 跑策略" if not already_ran_today else "▶ 重新执行"
        if st.button(btn_label, width="stretch"):
            with st.spinner("执行中（约5-10秒）..."):
                try:
                    _daily_job()
                    st.success("✅ 策略执行完成")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")
    with col2:
        if st.button("🔄 刷新", width="stretch"):
            st.rerun()

    if already_ran_today:
        st.caption(f"✅ 今日已运行  {state_emoji}{state_str or ''}")
    else:
        st.caption("⏳ 今日尚未运行")

    st.divider()
    st.caption(f"初始资金: ¥1,000,000")
    st.caption(f"单股上限: 10% | 最大持仓: 10只")
    st.caption(f"止损: -7% | 时间止损: 15天")
    cl = summary.get("consecutive_losses",0)
    if cl >= 3: st.warning(f"⚠️ 连亏{cl}次")

# ── Tab布局 ──
tab0, tab1, tab2, tab3, tab4 = st.tabs(["📖 策略说明", "📊 仪表盘", "💼 持仓", "📋 交易记录", "📰 要闻精选"])

with tab0:
    st.title("中线波段策略系统 v3.1")

    st.markdown("""
    ### 概述
    基于技术面信号 + 市场状态分类的**中线波段选股系统**，专攻 A 股日线级别波段。
    每日自动扫描全市场股票，结合趋势、量能、形态等因子评分选股，依据市场状态动态调整仓位。

    ---
    ### 策略流程

    ```
    获取数据 → 计算指标 → 信号过滤 → 评分排序 → 虚拟盘执行 → 推送日报
    ```

    | 环节 | 说明 |
    |------|------|
    | **数据源** | 沪深300指数 + 全市场个股日线（akshare/baostock） |
    | **基础池** | 全市场过滤（成交额≥5000万，剔除ST+僵尸股） |
    | **均线过滤** | 要求 MA5 > MA10 > MA20 > MA60（多头排列） |
    | **量能过滤** | 量比 ≥ 1.0（震荡市）或 ≥ 1.5（牛市），且 ≤ 4.0 |
    | **偏离过滤** | 收盘价偏离20日线 ≤ 5% |
    | **形态识别** | 底部背离、W底突破、假突破回落等 |
    | **评分排序** | 多因子加权评分（均线位置+量比+动量+形态+回撤） |
    | **AI 重排序** | LightGBM 模型对信号二次排序（可选） |
    | **行业筛选** | 取近30日行业动量前8名优先 |

    ---
    ### 市场状态分类

    基于沪深300指数的SMA20/SMA60趋势 + ATR波动率分位 + 成交额分位：

    | 状态 | 条件 | 仓位上限 |
    |------|------|---------|
    | 🐂 **牛市** | SMA20↑SMA60 + 成交额活跃 + 非高波 | ≤ 80% |
    | ⚖️ **震荡** | 其他情况 | ≤ 40% |
    | 🐻 **熊市** | SMA20↓SMA60 + 高波动 | ≤ 10% |
    | ⏳ **等待** | 数据不足60日 | 0% |

    ---
    ### 风控机制

    | 规则 | 参数 |
    |------|------|
    | **硬止损** | 单笔亏损 ≥ -7% 强制平仓 |
    | **移动止盈** | 牛市 3×ATR / 震荡 2×ATR 回撤止盈 |
    | **趋势破坏** | 收盘价 < MA10 - 1.5×ATR |
    | **海龟出场** | 收盘价跌破10日最低价 |
    | **时间止损** | 持仓 ≥ 15日强制平仓 |
    | **连亏冷却** | 连续3笔亏损 → 暂停开仓5天 |
    | **状态缓冲** | 市场状态切换后沿用旧规则3天 |

    ---
    ### 虚拟盘交易

    系统内置**虚拟盘引擎**（`PaperTrader`），自动执行信号：
    - 按评分从高到低依次开仓
    - 单股仓位 ≤ 10%，最大持仓 10 只
    - 自动追踪持仓市价、触发出场条件
    - 每日记录权益曲线，支持手动干预平仓
    - 所有数据持久化到 SQLite，Web 界面实时监控

    ---
    ### 回测表现（V3，2020-2025）

    | 指标 | 值 |
    |------|-----|
    | 年化收益率 | +8.53% |
    | 胜率 | 40.7% |
    | 盈亏比 | 2.72 |
    | 最大回撤 | -10.75% |
    | 夏普比率 | 0.82 |
    | 交易次数 | ~600次 |

    ---
    ### 技术栈

    | 组件 | 技术 |
    |------|------|
    | 数据获取 | akshare, baostock |
    | 信号引擎 | pandas, numpy |
    | AI 排序 | LightGBM |
    | 市场分类 | HMM 隐马尔可夫模型 |
    | 虚拟盘 | Python + SQLite |
    | Web 界面 | Streamlit + Plotly |
    | 消息推送 | Telegram Bot / Server酱 |
    | 定时任务 | schedule 库 |
    """)

with tab1:
    # KPI
    bc = state if state in ("bull","bear","oscillation") else "wait"
    cols = st.columns(5)
    with cols[0]:
        st.markdown(f'<div class="badge {bc}" style="font-size:1rem;padding:6px 16px">{state_labels.get(state,state)} 仓位≤{pos_limit:.0%}</div>', unsafe_allow_html=True)
        st.caption(market.get("trend_detail",""))
    with cols[1]: st.metric("持仓数量", summary.get("position_count",0))
    with cols[2]:
        pv = summary.get("total_pnl_pct",0)
        st.metric("累计盈亏", f"{pv:+.2f}%")
    with cols[3]: st.metric("交易次数", summary.get("total_trades",0))
    with cols[4]: st.metric("今日信号", len(signals_df) if not signals_df.empty else 0)

    # 权益曲线
    if not equity.empty:
        st.subheader("权益曲线")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=equity["date"],y=equity["total_equity"],mode="lines",name="总权益",
            line=dict(color="#00C853",width=2),fill="tozeroy",fillcolor="rgba(0,200,83,0.08)"))
        fig.add_trace(go.Scatter(x=equity["date"],y=equity["cash"],mode="lines",name="现金",
            line=dict(color="#448AFF",width=1,dash="dash")))
        if "market_state" in equity.columns:
            clrs = {"bull":"rgba(0,200,83,0.3)","oscillation":"rgba(255,214,0,0.3)","bear":"rgba(255,23,68,0.3)","wait":"rgba(136,136,136,0.3)"}
            for ms in equity["market_state"].unique():
                m = equity["market_state"]==ms
                if m.any(): s=equity[m]; fig.add_vrect(x0=s["date"].iloc[0],x1=s["date"].iloc[-1],fillcolor=clrs.get(ms,"rgba(136,136,136,0.15)"),layer="below",line_width=0,opacity=0.5)
        fig.update_layout(height=350,margin=dict(l=0,r=0,t=0,b=0),plot_bgcolor="#0E1117",paper_bgcolor="#0E1117",
            font=dict(color="#FAFAFA"),hovermode="x unified",xaxis=dict(showgrid=False),yaxis=dict(showgrid=True,gridcolor="#2E3138"),
            legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1))
        st.plotly_chart(fig,width="stretch")

    # 当前持仓
    st.subheader("当前持仓")
    if not positions.empty:
        d = positions[["code","name","entry_price","current_price","shares","pnl_pct","market_state"]].copy()
        d.columns = ["代码","名称","入场价","现价","股数","盈亏","入场状态"]
        d["盈亏"] = d["盈亏"].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "-")
        d["市值"] = (positions["current_price"]*positions["shares"]).apply(lambda x: f"¥{x:,.0f}")
        st.dataframe(d,width="stretch",hide_index=True)
    else: st.info("暂无持仓")

    # 今日信号
    st.subheader("最近信号")
    if not signals_df.empty:
        d = signals_df[["date","code","name","score","close","volume_ratio","industry"]].head(10).copy()
        d.columns = ["日期","代码","名称","评分","收盘价","量比","行业"]
        d["评分"] = d["评分"].round(2)
        st.dataframe(d,width="stretch",hide_index=True)
    else: st.info("暂无信号记录")

with tab2:
    st.subheader("持仓明细")
    if not positions.empty:
        d = positions[["code","name","entry_date","entry_price","current_price",
                        "shares","pnl_pct","highest_close","trailing_activated","market_state"]].copy()
        d.columns = ["代码","名称","入场日","入场价","现价","股数","盈亏%","最高价","移动止盈","市场状态"]
        d["盈亏%"] = d["盈亏%"].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "-")
        d["移动止盈"] = d["移动止盈"].apply(lambda x: "✅ 已激活" if x else "—")
        st.dataframe(d,width="stretch",hide_index=True)

        st.subheader("手动平仓")
        cnt = min(len(positions),5)
        cols = st.columns(cnt)
        for i,(_,row) in enumerate(positions.iterrows()):
            with cols[i%cnt]:
                if st.button(f"平仓 {row['code']}", key=f"close_{row['code']}"):
                    with st.spinner(f"平仓 {row['name']}..."):
                        _trader.close_position(row["code"],row["current_price"] or row["entry_price"],"手动平仓",datetime.now())
                    st.success(f"✅ {row['name']} 已平仓")
                    st.rerun()
    else: st.info("暂无持仓")

with tab3:
    st.subheader("交易记录")
    if not trades.empty:
        col1,col2 = st.columns(2)
        with col1: code_f = st.text_input("代码筛选","")
        with col2: show_all = st.checkbox("显示全部",True)

        d = trades[["date","code","name","action","price","shares","pnl","pnl_pct","reason","hold_days"]].copy()
        if code_f: d = d[d["code"].str.contains(code_f,na=False)]
        if not show_all: d = d.head(50)

        d.columns = ["日期","代码","名称","方向","价格","股数","盈亏","盈亏%","原因","持有天数"]
        d["盈亏%"] = d["盈亏%"].apply(lambda x: f"{x:+.2%}" if pd.notna(x) and x!=0 else "-")
        d["盈亏"] = d["盈亏"].apply(lambda x: f"¥{x:+,.2f}" if pd.notna(x) and x!=0 else "-")
        st.dataframe(d,width="stretch",hide_index=True)

        sells = trades[trades["action"]=="sell"].copy()
        if not sells.empty:
            st.subheader("绩效统计")
            kcols = st.columns(5)
            wins = sells[sells["pnl"]>0]; losses = sells[sells["pnl"]<=0]
            aw = wins["pnl_pct"].mean()*100 if not wins.empty else 0
            al = losses["pnl_pct"].mean()*100 if not losses.empty else 0
            kcols[0].metric("总交易",len(sells))
            kcols[1].metric("胜率",f"{len(wins)/len(sells)*100:.1f}%")
            kcols[2].metric("平均盈利",f"{aw:.2f}%")
            kcols[3].metric("平均亏损",f"{al:.2f}%")
            kcols[4].metric("盈亏比",f"{abs(aw/al):.2f}" if al!=0 else "∞")

            sells["date"] = pd.to_datetime(sells["date"])
            sells["ym"] = sells["date"].dt.strftime("%Y-%m")
            monthly = sells.groupby("ym")["pnl_pct"].sum()*100
            if len(monthly)>1:
                fig = px.bar(x=monthly.index,y=monthly.values,color=monthly.values,
                    color_continuous_scale=["#FF1744","#FFD600","#00C853"],
                    labels={"x":"","y":"月收益%"},height=250)
                fig.update_layout(plot_bgcolor="#0E1117",paper_bgcolor="#0E1117",
                    font=dict(color="#FAFAFA"),showlegend=False,
                    xaxis=dict(showgrid=False),yaxis=dict(showgrid=True,gridcolor="#2E3138"),
                    margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig,width="stretch")
    else: st.info("暂无交易记录")

with tab4:
    st.subheader("精选个股日报")
    if not signals_df.empty:
        for _, row in signals_df.head(8).iterrows():
            s = float(row.get("score",0)); vr = float(row.get("volume_ratio",0)); dv = float(row.get("deviation",0))
            ind = row.get("industry","")
            if isinstance(ind,float): ind=""
            strength = "强" if s>30 else ("中" if s>15 else "弱")
            method = "可现价建仓" if dv<0.02 and vr>1.5 else ("可建仓" if dv<0.02 else "回踩20日线建仓")
            st.markdown(f"**{row.get('name','')}** ({row.get('code','')}) · 评分 **{s:.1f}** · [{strength}] {method}")
            st.caption(f"{ind} | 量比{vr:.1f} | 偏离{dv:+.2%}")
            st.markdown("---")
    else: st.info("今日暂无信号")

    st.divider()
    st.subheader("每日要闻")
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import akshare as ak
            news = ak.stock_news_main_cx()
        if news is not None and not news.empty:
            for _, row in news.head(15).iterrows():
                st.markdown(f'<div class="news-item"><span class="news-tag">{row.get("tag","")}</span>{row.get("summary","")[:120]}</div>',
                    unsafe_allow_html=True)
        else: st.info("暂无要闻")
    except Exception as e: st.caption(f"新闻暂时不可用")

    st.divider()
    st.subheader("系统参数")
    st.caption(f"初始资金: ¥1,000,000 | 单股上限: 10% | 最大持仓: 10只")
    st.caption(f"止损: -7% | 时间止损: 15天 | 现金: ¥{summary.get('cash',0):,.2f}")
