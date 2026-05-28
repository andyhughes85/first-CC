"""HMM v2 鐗瑰緛 vs v1 鐗瑰緛 鈥?鍒嗘鐜囧拰鍚庡競琛ㄧ幇瀵规瘮"""

import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'midline_strategy'))
import numpy as np
import pandas as pd
from data_fetcher import fetch_index_incremental
from market_state import judge_market_state, add_index_indicators
from hmm_market import load_hmm_model, predict_market_state, build_hmm_features

# ============== 鍔犺浇鏁版嵁 ==============
index_df = fetch_index_incremental()
index_df = add_index_indicators(index_df)
n = min(504, len(index_df))
recent = index_df.iloc[-n:]

# ============== 鍔犺浇 v2 妯″瀷锛堟柊鐗瑰緛锛?==============
hmm, scaler, state_map = load_hmm_model()
features_v2 = build_hmm_features(recent)
X_v2 = scaler.transform(features_v2.values)
hmm_states_v2 = hmm.predict(X_v2)
hmm_probs_v2 = hmm.predict_proba(X_v2)

# ============== 鍔犺浇 v1 妯″瀷锛堟棫鐗瑰緛锛岄渶瑕佸崟鐙瀯寤猴級 ==============
import os, joblib, logging
logging.basicConfig(level=logging.WARNING)
old_path = os.path.join(os.path.dirname(__file__), "models", "hmm_market_v1.pkl")
v1_data = joblib.load(old_path)
hmm_v1, scaler_v1, state_map_v1 = v1_data["hmm"], v1_data["scaler"], v1_data["state_map"]

def build_v1_features(df):
    """閲嶅缓 v1 鐗瑰緛"""
    features = pd.DataFrame(index=df.index)
    returns = df["close"] / df["close"].shift(1)
    returns = returns.replace(0, np.nan).clip(lower=1e-10)
    features["log_return"] = np.log(returns)
    features["volatility"] = features["log_return"].rolling(10).std()
    vol_col = "volume" if "volume" in df.columns and df["volume"].sum() > 0 else "amount"
    features["volume_change"] = df[vol_col].pct_change(5).replace([np.inf, -np.inf], np.nan)
    low_20 = df["close"].rolling(20).min()
    high_20 = df["close"].rolling(20).max()
    features["price_position"] = (df["close"] - low_20) / (high_20 - low_20 + 1e-10)
    return features.fillna(0).clip(-10, 10)

features_v1 = build_v1_features(recent)
X_v1 = scaler_v1.transform(features_v1.values)
hmm_states_v1 = hmm_v1.predict(X_v1)
hmm_probs_v1 = hmm_v1.predict_proba(X_v1)

# ============== 閫愭棩瀵规瘮 ==============
min_days = 60
prices = recent["close"].values

def forward_return(t, fwd, arr):
    return arr[t + fwd] / arr[t] - 1 if t + fwd < len(arr) else np.nan

def analyze(hmm_states, hmm_probs, state_map, label):
    """鍒嗘瀽鍒嗘鐜?+ 鍚庡競琛ㄧ幇"""
    div_count = 0
    total = 0
    fwd_rets = {5: [], 20: []}
    div_fwd_rets = {5: [], 20: []}
    bear_bull_rets = {20: []}  # MA=鐗涘競 鈫?HMM=鐔婂競

    for t in range(min_days, n):
        day_data = recent.iloc[:t+1]
        ma = judge_market_state(day_data)
        ma_state = ma["state"]

        hmm_idx = int(hmm_states[t])
        hmm_label = state_map.get(hmm_idx, "oscillation")
        hmm_conf = float(hmm_probs[t][hmm_idx])

        divergent = hmm_label != ma_state
        if divergent:
            div_count += 1

            # MA=鐗涘競 鈫?HMM=鐔婂競
            if ma_state == "bull" and hmm_label == "bear":
                if t + 20 < n:
                    bear_bull_rets[20].append(forward_return(t, 20, prices))

        total += 1

        for fwd in [5, 20]:
            if t + fwd >= n:
                continue
            r = forward_return(t, fwd, prices)
            fwd_rets[fwd].append(r)
            if divergent:
                div_fwd_rets[fwd].append(r)

    div_rate = div_count / total * 100 if total else 0

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  鍒嗘鐜? {div_count}/{total} = {div_rate:.1f}%")
    print(f"  鍒嗘鏂瑰悜: MA=鐗涘競鈫扝MM=鐔婂競 {len(bear_bull_rets[20])} 娆?)

    print(f"\n  鍚庡競琛ㄧ幇:")
    for fwd in [5, 20]:
        all_rets = fwd_rets[fwd]
        div_rets = div_fwd_rets[fwd]
        if all_rets:
            print(f"    {fwd}鏃?鈥?鍏ㄩ儴: {np.mean(all_rets)*100:+.1f}% "
                  f"鍒嗘: {np.mean(div_rets)*100:+.1f}% "
                  f"鍒嗘-鍏ㄩ儴: {np.mean(div_rets)*100 - np.mean(all_rets)*100:+.1f}%")

    if bear_bull_rets[20]:
        r = bear_bull_rets[20]
        print(f"\n  MA=鐗涘競鈫扝MM=鐔婂競 20鏃ヨ〃鐜?")
        print(f"    鍧噞np.mean(r)*100:+.1f}% 鑳滅巼{np.mean(np.array(r)>0)*100:.0f}% "
              f"({'棰勮鏈夋晥' if np.mean(r) < 0 else '璇垽'})")

    # 鍚勭姸鎬佸垎甯?    print(f"\n  鐘舵€佸垎甯?")
    for s in ["bear", "oscillation", "bull"]:
        cnt = sum(1 for t in range(min_days, n) if state_map.get(int(hmm_states[t]), "") == s)
        print(f"    {s}: {cnt} 澶?({cnt/total*100:.1f}%)")

    return div_rate

# ============== 璺戝垎鏋?==============
analyze(hmm_states_v1, hmm_probs_v1, state_map_v1, "HMM v1 (鏃х壒寰?")
analyze(hmm_states_v2, hmm_probs_v2, state_map, "HMM v2 (鏂扮壒寰?")
