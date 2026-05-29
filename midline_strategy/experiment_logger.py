"""实验记录器 — 每次回测自动生成图表 + 报告 + 目录归档

用法：
    from experiment_logger import log_experiment
    log_experiment("backtest_summary.json", "backtest_trades.csv", notes="V4改进: close>ma10")
"""

import json, os, shutil, subprocess
from datetime import datetime
import pandas as pd
import numpy as np

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS_DIR = os.path.join(_SCRIPT_DIR, "experiments")


def _ensure_experiment_dir():
    os.makedirs(_EXPERIMENTS_DIR, exist_ok=True)


def _next_experiment_id():
    today = datetime.now().strftime("%Y%m%d")
    existing = [d for d in os.listdir(_EXPERIMENTS_DIR) if d.startswith(today)]
    seq = len(existing) + 1
    return f"{today}_v{seq}"


def _read_summary(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _plot_equity_curve(trades_csv, summary, output_dir):
    """权益曲线 + 回撤图"""
    if not _HAS_PLOTLY:
        return
    
    df = pd.read_csv(os.path.join(_SCRIPT_DIR, "backtest_equity.csv"))
    df["date"] = pd.to_datetime(df["date"])
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.7, 0.3],
                        subplot_titles=["权益曲线", "回撤"])
    
    fig.add_trace(go.Scatter(x=df["date"], y=df["value"],
                             mode="lines", name="策略净值",
                             line=dict(color="green", width=2)),
                  row=1, col=1)
    
    # 基准（如果有）
    if summary.get("benchmark_return") is not None:
        from data_fetcher import load_cached
        try:
            bench = load_cached("index_daily", start=df["date"].min().strftime("%Y-%m-%d"),
                                end=df["date"].max().strftime("%Y-%m-%d"))
            if not bench.empty:
                bench["date"] = pd.to_datetime(bench["date"])
                bench["norm"] = bench["close"] / bench["close"].iloc[0] * summary["initial_capital"]
                fig.add_trace(go.Scatter(x=bench["date"], y=bench["norm"],
                                         mode="lines", name="沪深300",
                                         line=dict(color="blue", width=1, dash="dash")),
                              row=1, col=1)
        except Exception:
            pass
    
    # 回撤
    cummax = df["value"].cummax()
    dd = (df["value"] - cummax) / cummax
    fig.add_trace(go.Scatter(x=df["date"], y=dd,
                             mode="lines", name="回撤",
                             fill="tozeroy",
                             line=dict(color="red", width=1)),
                  row=2, col=1)
    
    fig.update_layout(height=600, title="权益曲线",
                      showlegend=True,
                      hovermode="x unified")
    fig.write_image(os.path.join(output_dir, "equity_curve.png"),
                    width=1200, height=600, scale=2)
    print("  权益曲线: equity_curve.png")


def _plot_monthly_heatmap(trades_csv, output_dir):
    """月度收益热力图"""
    if not _HAS_PLOTLY:
        return
    df = pd.read_csv(trades_csv)
    if df.empty:
        return
    df["sell_date"] = pd.to_datetime(df["sell_date"])
    df["yearmon"] = df["sell_date"].dt.to_period("M").astype(str)
    
    monthly = df.groupby("yearmon")["pnl"].sum().reset_index()
    monthly["year"] = monthly["yearmon"].str[:4].astype(int)
    monthly["month"] = monthly["yearmon"].str[5:7].astype(int)
    
    pivot = monthly.pivot_table(index="year", columns="month", values="pnl", aggfunc="sum")
    pivot = pivot.reindex(columns=range(1, 13))
    
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values * 100,
        x=[f"{m}月" for m in pivot.columns],
        y=pivot.index,
        colorscale="RdYlGn",
        zmid=0,
        text=np.round(pivot.values * 100, 1),
        texttemplate="%{text}%",
        hovertemplate="%{y}年%{x}: %{z:.1f}%<extra></extra>"
    ))
    fig.update_layout(title="月度收益热力图 (%)", height=400)
    fig.write_image(os.path.join(output_dir, "monthly_heatmap.png"),
                    width=800, height=400, scale=2)
    print("  月度收益: monthly_heatmap.png")


def _plot_hold_dist(trades_csv, output_dir):
    """持仓天数分布图"""
    if not _HAS_PLOTLY:
        return
    df = pd.read_csv(trades_csv)
    if df.empty:
        return
    df["buy_date"] = pd.to_datetime(df["buy_date"])
    df["sell_date"] = pd.to_datetime(df["sell_date"])
    df["hold_days"] = (df["sell_date"] - df["buy_date"]).dt.days
    
    fig = make_subplots(rows=1, cols=2, subplot_titles=["持仓天数分布", "按原因分类"],
                        specs=[[{"type": "bar"}, {"type": "pie"}]])
    
    fig.add_trace(go.Histogram(x=df["hold_days"], nbinsx=20,
                               name="交易次数", marker_color="steelblue"),
                  row=1, col=1)
    
    reason_stats = df.groupby("reason").agg(
        次数=("pnl", "count"),
        胜率=("pnl", lambda x: (x > 0).mean())
    ).sort_values("次数", ascending=False).head(8)
    
    fig.add_trace(go.Pie(labels=reason_stats.index, values=reason_stats["次数"],
                         textinfo="label+percent",
                         hovertemplate="%{label}<br>%{value}次<br>胜率%{customdata:.0%}<extra></extra>",
                         customdata=reason_stats["胜率"]),
                  row=1, col=2)
    
    fig.update_layout(height=400, title="交易分析")
    fig.write_image(os.path.join(output_dir, "trades_analysis.png"),
                    width=1000, height=400, scale=2)
    print("  交易分析: trades_analysis.png")


def _save_readme(summary, output_dir, notes=""):
    """生成 README.md 说明"""
    lines = [
        f"# 实验: {os.path.basename(output_dir)}",
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 核心指标",
        f"- 年化收益率: {summary.get('annual_return', 0):.2%}",
        f"- 夏普比率: {summary.get('sharpe', 0):.2f}",
        f"- 最大回撤: {summary.get('max_drawdown', 0):.2%}",
        f"- 胜率: {summary.get('win_rate', 0):.1%}",
        f"- 盈亏比: {abs(summary.get('avg_win', 0) / summary.get('avg_loss', 1)):.2f}",
        f"- 交易次数: {summary.get('n_trades', 0)}",
        f"- 基准年化: {summary.get('benchmark_annual', 0):.2%}",
        f"- 超额年化: {summary.get('excess_annual', 0):.2%}",
        "",
    ]
    if notes:
        lines.append("## 说明")
        lines.append(notes)
        lines.append("")
    lines.append("## 参数")
    lines.append(f"- 初始资金: {summary.get('initial_capital', 'N/A')}")
    lines.append(f"- 时间区间: {summary.get('start_date', '')} ~ {summary.get('end_date', '')}")
    lines.append(f"- 绿灯: {'通过' if summary.get('green_light') else '未通过'}")
    
    with open(os.path.join(output_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("  README.md")


def log_experiment(summary_path=None, trades_csv=None, notes=""):
    """记录一次实验

    Parameters
    ----------
    summary_path : str or None
        backtest_summary.json 路径，None 则自动查找
    trades_csv : str or None
        backtest_trades.csv 路径，None 则自动查找
    notes : str
        实验说明
    """
    # 自动查找文件
    if summary_path is None:
        summary_path = os.path.join(_SCRIPT_DIR, "backtest_summary.json")
    if trades_csv is None:
        trades_csv = os.path.join(_SCRIPT_DIR, "backtest_trades.csv")
    
    if not os.path.exists(summary_path):
        print(f"错误: {summary_path} 不存在")
        return
    
    _ensure_experiment_dir()
    
    # 读取当前 git diff 信息
    git_diff = ""
    try:
        git_diff = subprocess.check_output(
            ["git", "log", "--oneline", "-5"],
            cwd=_SCRIPT_DIR, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        git_diff = "(非 git 仓库)"
    
    # 读取回测结果
    summary = _read_summary(summary_path)
    
    # 创建实验目录
    exp_id = _next_experiment_id()
    exp_dir = os.path.join(_EXPERIMENTS_DIR, exp_id)
    os.makedirs(exp_dir)
    
    print(f"\n实验记录: {exp_id}")
    print(f"目录: {exp_dir}")
    
    # 复制回测结果
    try:
        shutil.copy2(summary_path, os.path.join(exp_dir, "summary.json"))
    except Exception:
        pass
    try:
        if os.path.exists(trades_csv):
            shutil.copy2(trades_csv, os.path.join(exp_dir, "trades.csv"))
    except Exception:
        pass
    try:
        eq_path = os.path.join(_SCRIPT_DIR, "backtest_equity.csv")
        if os.path.exists(eq_path):
            shutil.copy2(eq_path, os.path.join(exp_dir, "equity.csv"))
    except Exception:
        pass
    
    # 生成图表（失败不阻塞）
    try:
        _plot_equity_curve(trades_csv, summary, exp_dir)
    except Exception as e:
        print(f"  权益曲线生成失败: {e}")
    
    try:
        if os.path.exists(trades_csv):
            _plot_monthly_heatmap(trades_csv, exp_dir)
            _plot_hold_dist(trades_csv, exp_dir)
    except Exception as e:
        print(f"  交易分析图失败: {e}")
    
    # README
    _save_readme(summary, exp_dir, notes)
    
    # 存 git 信息
    if git_diff:
        with open(os.path.join(exp_dir, "git_log.txt"), "w") as f:
            f.write(git_diff)
    
    print(f"\n实验已记录到: experiments/{exp_id}/")
    print("  summary.json, trades.csv, equity.csv")
    print("  equity_curve.png, monthly_heatmap.png, trades_analysis.png")
    print("  README.md")
    return exp_id


def list_experiments():
    """列出所有实验"""
    _ensure_experiment_dir()
    exps = sorted([d for d in os.listdir(_EXPERIMENTS_DIR)
                   if os.path.isdir(os.path.join(_EXPERIMENTS_DIR, d))],
                  reverse=True)
    if not exps:
        print("暂无实验记录")
        return
    
    print(f"\n实验列表 ({len(exps)} 个):")
    print("-" * 60)
    for e in exps[:20]:
        readme = os.path.join(_EXPERIMENTS_DIR, e, "README.md")
        summary = os.path.join(_EXPERIMENTS_DIR, e, "summary.json")
        ret = ""
        if os.path.exists(summary):
            try:
                with open(summary) as f:
                    s = json.load(f)
                ret = f"年化{s.get('annual_return',0):.2%} 夏普{s.get('sharpe',0):.2f}"
            except Exception:
                pass
        print(f"  {e:20s} {ret}")
