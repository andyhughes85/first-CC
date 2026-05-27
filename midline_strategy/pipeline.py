"""主流程 — 定时任务调度"""

import logging
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from data_fetcher import fetch_index_incremental, save_market_state, load_cached, get_conn as _get_conn
from market_state import judge_market_state, add_index_indicators
from signal_engine import generate_signals
from push_service import send_daily_report, send_weekly_report
from config import DB_PATH
from lgb_features import build_lgb_features, get_lgb_feature_cols
from lgb_model import LightGBMModel
from hmm_market import train_hmm_model, load_hmm_model, save_hmm_model, predict_market_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="trading_bot.log",
)

# 连续空仓计数器
_consecutive_empty = 0
_daily_state_history = []  # [(date, state, pos_limit, reason), ...]

# LightGBM 评分模型（懒加载）
_lgb_model = None

# HMM 市场状态模型（懒加载）
_hmm_model = None
_hmm_scaler = None
_hmm_state_map = None
_hmm_trained = False


def _ensure_hmm(index_df):
    """确保 HMM 模型已加载/训练，返回 (label, probs) 或 (None, None)"""
    global _hmm_model, _hmm_scaler, _hmm_state_map, _hmm_trained

    if _hmm_model is None:
        _hmm_model, _hmm_scaler, _hmm_state_map = load_hmm_model()
    if _hmm_model is not None:
        return predict_market_state(index_df, _hmm_model, _hmm_scaler, _hmm_state_map)

    # 首次运行：用全部指数数据训练
    if not _hmm_trained and len(index_df) >= 252:
        try:
            logging.info("首次训练 HMM 模型（%d 条数据）...", len(index_df))
            _hmm_model, _hmm_scaler, _hmm_state_map = train_hmm_model(index_df)
            save_hmm_model(_hmm_model, _hmm_scaler, _hmm_state_map)
            _hmm_trained = True
            logging.info("HMM 模型训练完成: %s", _hmm_state_map)
            return predict_market_state(index_df, _hmm_model, _hmm_scaler, _hmm_state_map)
        except Exception as e:
            logging.warning("HMM 训练失败: %s", e)
            _hmm_trained = True  # 避免重复失败
    return None, None


def _load_lgb_model():
    global _lgb_model
    if _lgb_model is not None:
        return _lgb_model
    # 切换到脚本目录（避免中文路径导致 LightGBM 加载失败）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    old_cwd = os.getcwd()
    os.chdir(script_dir)
    try:
        model = LightGBMModel()
        model.load("models/lgb_midline.txt")
        _lgb_model = model
        logging.info("LGB 模型加载成功")
        return model
    except Exception as e:
        logging.error("LGB 模型加载失败: %s", e)
        return None
    finally:
        os.chdir(old_cwd)


def lgb_warmup():
    """预加载 LGB 模型（供 UI 启动时预热调用），避免首次执行耗时"""
    return _load_lgb_model()


def get_last_run_info():
    """查询策略最后运行日期和状态"""
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT date, state FROM market_state_history ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return row if row else None
    except Exception:
        return None


def _lgb_rerank(signals, stocks_df):
    """用 LightGBM 模型对信号重排序"""
    model = _load_lgb_model()
    if model is None or signals.empty:
        return signals
    feature_cols = get_lgb_feature_cols()
    scores = []
    for _, row in signals.iterrows():
        code = row["code"]
        hist = stocks_df[stocks_df["code"] == code].sort_values("date").copy()
        if len(hist) < 80:
            scores.append(0)
            continue
        try:
            feat = build_lgb_features(hist)
            last = feat.iloc[-1:][feature_cols].fillna(0)
            proba = model.predict(last)[0]
            scores.append(round(proba, 4))
        except Exception as e:
            logging.debug("LGB 评分异常 %s: %s", code, e)
            scores.append(0)
    signals = signals.copy()
    signals["lgb_score"] = scores
    return signals.sort_values("lgb_score", ascending=False)


def get_hot_industries(stocks_df):
    """从个股数据计算行业动量，返回行业代码列表（与stock_list匹配）"""
    if stocks_df.empty or "industry" not in stocks_df.columns:
        return []

    # 获取每只股票最新 & 20天前的收盘价
    stocks_df["date"] = pd.to_datetime(stocks_df["date"])
    recent = stocks_df.sort_values("date").groupby("code").last().reset_index()
    oldest_dates = stocks_df["date"].max() - timedelta(days=30)
    oldest = (stocks_df[stocks_df["date"] >= oldest_dates]
              .sort_values("date").groupby("code").first().reset_index())

    ret = recent.merge(oldest, on="code", suffixes=("", "_old"))
    ret["momentum"] = ret["close"] / ret["close_old"] - 1

    # 过滤有效行业（≥20只股票）
    ind_sizes = ret["industry"].value_counts()
    valid = ind_sizes[ind_sizes >= 20].index
    ret = ret[ret["industry"].isin(valid)]

    if ret.empty:
        return []

    top = ret.groupby("industry")["momentum"].median().sort_values(ascending=False)
    return top.head(8).index.tolist()


def _status_update(status, label, state="running"):
    """更新 st.status 对象（容错，无 status 时跳过）"""
    if status is not None:
        try:
            status.update(label=label, state=state)
        except Exception:
            pass


def daily_job(status=None):
    """每日定时任务，status 可选传 st.status() 对象用于 UI 进度展示"""
    global _consecutive_empty, _daily_state_history

    logging.info("开始日线任务")
    _status_update(status, "📡 获取指数数据...")
    try:
        # 指数数据（轻量，可在线获取）
        index_df = fetch_index_incremental()
        if index_df is None or index_df.empty:
            logging.error("指数数据获取失败")
            _status_update(status, "❌ 指数数据获取失败", "error")
            return
        index_df = add_index_indicators(index_df)
        market_info = judge_market_state(index_df)
        ms, pos = market_info["state"], market_info["pos_limit"]

        # HMM 状态作为第二意见，分歧时取保守仓位
        hmm_label, hmm_probs = _ensure_hmm(index_df)
        if hmm_label:
            hmm_pos = {"bull": 0.8, "oscillation": 0.4, "bear": 0.1}.get(hmm_label, 0.4)
            hmm_conf = max(hmm_probs.values()) if hmm_probs else 0
            if ms == hmm_label:
                logging.info("HMM与MA状态一致: %s (HMM置信度%.0f%%)", ms, hmm_conf * 100)
            else:
                blended = min(pos, hmm_pos)
                logging.info("HMM与MA分歧: MA=%s HMM=%s(%.0f%%), 仓位%.0f%%→%.0f%%",
                             ms, hmm_label, hmm_conf * 100, pos * 100, blended * 100)
                pos = blended
                market_info["pos_limit"] = blended
            market_info["hmm_state"] = hmm_label
            market_info["hmm_probs"] = hmm_probs
            market_info["trend_detail"] += f" | HMM:{hmm_label}({hmm_conf:.0%})"

        _status_update(status, f"📊 市场状态: {ms} 仓位≤{pos:.0%}")
        hmm_log = ""
        if hmm_label and hmm_probs:
            prob_str = " ".join(f"{k}={v:.0%}" for k, v in hmm_probs.items())
            hmm_log = f" | HMM:{hmm_label} [{prob_str}]"
        logging.info("市场状态: %s, 仓位上限: %.0f%%%s", ms, pos * 100, hmm_log)

        # 个股数据（从缓存读取，不触发在线下载，避免超时）
        _status_update(status, "💾 加载个股缓存数据...")
        stocks_df = load_cached("stock_daily",
            start=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
        if not stocks_df.empty:
            try:
                stock_list = pd.read_sql("SELECT code, name, industry FROM stock_list", _get_conn())
                stocks_df = stocks_df.merge(stock_list[["code","name","industry"]], on="code", how="left")
            except Exception as e:
                logging.warning("行业信息加载失败: %s", e)
        n_stocks = stocks_df["code"].nunique() if not stocks_df.empty else 0
        _status_update(status, f"🔍 计算行业动量（{n_stocks} 只股票）...")
        logging.info("个股缓存数据: %d 条, %d 只", len(stocks_df), n_stocks)

        hot = get_hot_industries(stocks_df)
        _status_update(status, f"📈 强势行业: {hot[:3] if hot else '无'}")
        logging.info("强势行业: %s", hot)

        _status_update(status, "🎯 生成信号...")
        signals, filter_stats = generate_signals(stocks_df, hot, ms)
        _status_update(status, f"🤖 LGB 重排序（{len(signals)} 个信号）...")
        signals = _lgb_rerank(signals, stocks_df)

        # 虚拟盘自动交易
        _status_update(status, "💼 虚拟盘执行...")
        try:
            from paper_trader import PaperTrader
            _trader = PaperTrader()
            _trader.process(signals, market_info, stocks_df, datetime.now())
            n_pos = _trader.get_summary()["position_count"]
            _status_update(status, f"✅ 虚拟盘完成，持仓 {n_pos} 只")
            logging.info("虚拟盘处理完成，持仓 %d 只", n_pos)
        except Exception as e:
            logging.error("虚拟盘处理失败: %s", e, exc_info=True)

        signal_count = len(signals)
        if signal_count > 0:
            _consecutive_empty = 0
            logging.info("触发 %d 只个股信号", signal_count)
        else:
            _consecutive_empty += 1
            logging.info("今日无信号（连续空仓 %d 天）", _consecutive_empty)

        # 记录状态历史（内存+DB持久化）
        _daily_state_history.append((
            datetime.now().strftime("%Y-%m-%d"), ms, pos, market_info.get("trend_detail", "")
        ))
        hmm_state = market_info.get("hmm_state", "")
        hmm_conf = round(max(market_info.get("hmm_probs", {}).values(), default=0) * 100)
        save_market_state(
            datetime.now().strftime("%Y-%m-%d"), ms, pos,
            market_info.get("index_close", 0), market_info.get("trend_detail", ""),
            hmm_state=hmm_state, hmm_confidence=hmm_conf,
        )

        # 推送日报
        send_daily_report(
            market_state=ms,
            pos_limit=pos,
            index_close=market_info["index_close"],
            index_pct=market_info["index_pct"],
            atr_rank=market_info["atr_rank"],
            amt_rank=market_info["amt_rank"],
            trend_detail=market_info["trend_detail"],
            hot_industries=hot,
            signal_count=signal_count,
            filter_stats=filter_stats,
            consecutive_empty=_consecutive_empty,
            signals_df=signals if not signals.empty else None,
        )
    except Exception as e:
        logging.error("任务失败: %s", e, exc_info=True)


def weekly_job():
    """每周五定时周报"""
    global _daily_state_history

    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    week_start = monday.strftime("%Y-%m-%d")
    week_end = today.strftime("%Y-%m-%d")

    # 本周状态
    week_states = [s for s in _daily_state_history if s[0] >= week_start]

    send_weekly_report(
        week_start=week_start,
        week_end=week_end,
        daily_states=week_states,
        suggestion="可考虑增加周中行业动量再排序。",
    )
