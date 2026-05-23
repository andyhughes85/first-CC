"""A股数据获取模块 - 支持日K线、分钟K线、行业分类、基本面、北向资金"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import DATA_DIR


def get_index_hist(symbol="000300", start_date="20200101", end_date=None):
    """获取指数历史日K线（使用新浪数据源）"""
    try:
        import akshare as ak
        # 新浪源，symbol格式: sh000300
        sina_symbol = f"sh{symbol}" if not symbol.startswith(("sh", "sz")) else symbol
        df = ak.stock_zh_index_daily(symbol=sina_symbol)
        if df is None or df.empty:
            return pd.DataFrame()
        # stock_zh_index_daily 返回的列名: date, open, high, low, close, volume
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        # 按开始日期过滤
        if start_date:
            start_dt = pd.to_datetime(start_date)
            df = df[df["date"] >= start_dt].reset_index(drop=True)
        if end_date:
            end_dt = pd.to_datetime(end_date)
            df = df[df["date"] <= end_dt].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"[数据] 获取指数数据失败: {e}")
        return pd.DataFrame()


def get_stock_hist(symbol, start_date="20200101", end_date=None, adjust="qfq"):
    """获取个股历史日K线"""
    try:
        import akshare as ak
        end = end_date or datetime.now().strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                start_date=start_date, end_date=end, adjust=adjust)
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        col_map = {}
        for c in df.columns:
            if "收盘" in c: col_map[c] = "close"
            elif "开盘" in c: col_map[c] = "open"
            elif "最高" in c: col_map[c] = "high"
            elif "最低" in c: col_map[c] = "low"
            elif "成交量" in c: col_map[c] = "volume"
            elif "成交额" in c: col_map[c] = "amount"
            elif "振幅" in c: col_map[c] = "amplitude"
            elif "涨跌幅" in c: col_map[c] = "pct_change"
            elif "涨跌额" in c: col_map[c] = "change"
            elif "换手率" in c: col_map[c] = "turnover"
            elif "市盈率" in c: col_map[c] = "pe"
            elif "市净率" in c: col_map[c] = "pb"
        df = df.rename(columns=col_map)
        if "date" not in df.columns:
            for c in df.columns:
                if "日期" in c or "date" in c:
                    df = df.rename(columns={c: "date"})
                    break
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        if "pct_change" in df.columns:
            df["pct_change"] = df["pct_change"] / 100.0
        return df
    except Exception as e:
        print(f"[数据] 获取 {symbol} 失败: {e}")
        return pd.DataFrame()


def get_all_a_stocks():
    """获取全部A股代码列表"""
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        codes = df["代码"].tolist()
        print(f"[数据] A股总数: {len(codes)}")
        return codes
    except Exception as e:
        print(f"[数据] 获取股票列表失败: {e}")
        return []


def get_batch_stock_data(symbols, start_date="20200101", end_date=None):
    """批量获取个股数据（自动缓存加速）"""
    os.makedirs(DATA_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    cache_file = os.path.join(DATA_DIR, f"stock_data_{today_str}.pkl")

    if os.path.exists(cache_file):
        import joblib
        data = joblib.load(cache_file)
        print(f"[数据] 加载缓存: {len(data)} 只股票")
        return data

    data = {}
    total = len(symbols)
    for i, sym in enumerate(symbols):
        if i >= 2000:  # 限制数量避免超时
            break
        df = get_stock_hist(sym, start_date, end_date)
        if not df.empty:
            data[sym] = df
        if (i + 1) % 100 == 0:
            print(f"[数据] 进度: {i+1}/{total}")

    import joblib
    joblib.dump(data, cache_file)
    print(f"[数据] 获取完成: {len(data)} 只, 已缓存")
    return data


def get_industry_momentum():
    """获取申万一级行业动量"""
    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        industries = df["板块名称"].tolist()

        results = []
        end = datetime.now()
        start = end - timedelta(days=60)

        for ind in industries:
            try:
                ind_df = ak.stock_board_industry_hist_em(
                    symbol=ind, period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                )
                if ind_df is not None and len(ind_df) > 20:
                    ret_20d = (ind_df["收盘价"].iloc[-1] /
                               ind_df["收盘价"].iloc[-21] - 1)
                    amount_series = ind_df["成交额"].iloc[-21:]
                    amount_ratio = (amount_series.iloc[-1] /
                                    amount_series.iloc[-21:].mean())
                    results.append({
                        "industry": ind,
                        "momentum_20d": ret_20d,
                        "amount_ratio": amount_ratio,
                    })
            except:
                continue

        return pd.DataFrame(results).sort_values("momentum_20d", ascending=False)
    except Exception as e:
        print(f"[数据] 获取行业动量失败: {e}")
        return pd.DataFrame()


def get_realtime_quote():
    """获取全市场实时行情"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        df.columns = [c.lower() for c in df.columns]
        col_map = {}
        for c in df.columns:
            if "代码" in c: col_map[c] = "code"
            elif "名称" in c: col_map[c] = "name"
            elif "最新价" in c: col_map[c] = "price"
            elif "涨跌幅" in c: col_map[c] = "pct"
            elif "成交量" in c: col_map[c] = "volume"
            elif "成交额" in c: col_map[c] = "amount"
            elif "换手率" in c: col_map[c] = "turnover"
            elif "量比" in c: col_map[c] = "volume_ratio"
            elif "市盈率" in c and "动态" in c: col_map[c] = "pe"
            elif "市净率" in c: col_map[c] = "pb"
            elif "总市值" in c: col_map[c] = "total_mv"
        df = df.rename(columns=col_map)
        return df
    except Exception as e:
        print(f"[数据] 获取实时行情失败: {e}")
        return pd.DataFrame()
