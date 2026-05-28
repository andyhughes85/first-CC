"""鏂瑰悜B 涓夌浠撲綅鏂规瀵规瘮"""

import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'midline_strategy'))
import numpy as np
import pandas as pd
from data_fetcher import fetch_index_incremental
from market_state import judge_market_state, add_index_indicators
from hmm_market import load_hmm_model, predict_market_state, build_hmm_features

print("鍔犺浇鏁版嵁...")
index_df = fetch_index_incremental()
index_df = add_index_indicators(index_df)
n = min(504, len(index_df))
recent = index_df.iloc[-n:]

hmm, scaler, state_map = load_hmm_model()
features = build_hmm_features(recent)
X = scaler.transform(features.values)
hmm_states = hmm.predict(X)
hmm_probs = hmm.predict_proba(X)

min_days = 60
schemes = {
    "褰撳墠瑙勫垯 min(pos,hmm_pos)": [],
    "鏂瑰悜B 绌轰粨 0.0": [],
    "鏂瑰悜B 鍗婁粨 0.5": [],
}

results = []
for t in range(min_days, n):
    day_data = recent.iloc[:t+1]
    ma = judge_market_state(day_data)
    ma_state, ma_pos = ma["state"], ma["pos_limit"]

    hmm_idx = int(hmm_states[t])
    hmm_label = state_map.get(hmm_idx, "oscillation")
    hmm_pos = {"bull": 0.8, "oscillation": 0.4, "bear": 0.1}.get(hmm_label, 0.4)
    hmm_conf = float(hmm_probs[t][hmm_idx])

    # 褰撴棩鏀剁洏鏀剁泭鐜囷紙绠€鍖栵細鐢ㄦ鏃ユ敹鐩婏級
    next_ret = 0
    if t + 1 < n:
        next_ret = recent.iloc[t+1]["close"] / recent.iloc[t]["close"] - 1

    # 褰撳墠瑙勫垯
    pos1 = min(ma_pos, hmm_pos) if hmm_label != ma_state else ma_pos

    # 鏂瑰悜B 涓夌鏂规
    if hmm_label != ma_state and ma_state == "bull" and hmm_label == "bear":
        pos2 = 0.0   # 绌轰粨
        pos3 = 0.5   # 鍗婁粨
    else:
        pos2 = ma_pos
        pos3 = ma_pos

    results.append({
        "date": str(recent.iloc[t]["date"])[:10],
        "ma_state": ma_state, "hmm_state": hmm_label,
        "hmm_conf": round(hmm_conf * 100),
        "next_ret": next_ret,
        "pos_current": pos1,
        "pos_b_dir_0": pos2,
        "pos_b_dir_05": pos3,
    })

df = pd.DataFrame(results)

# 璁＄畻姣忕鏂规鐨勬€绘敹鐩婏紙绠€鍖栵細浠撲綅 脳 娆℃棩鏀剁泭锛屾棩绱箻锛?for col, label in [
    ("pos_current", "褰撳墠瑙勫垯"),
    ("pos_b_dir_0", "鏂瑰悜B绌轰粨"),
    ("pos_b_dir_05", "鏂瑰悜B鍗婁粨"),
]:
    df["ret_" + col] = df[col] * df["next_ret"]
    cum = (1 + df["ret_" + col]).cumprod()
    total_ret = cum.iloc[-1] - 1
    max_dd = (cum / cum.cummax() - 1).min()
    annual = (1 + total_ret) ** (252 / len(df)) - 1
    sharpe = df["ret_" + col].mean() / df["ret_" + col].std() * np.sqrt(252) if df["ret_" + col].std() > 0 else 0

    print(f"\n{label}:")
    print(f"  鎬绘敹鐩? {total_ret*100:.1f}%")
    print(f"  骞村寲: {annual*100:.1f}%")
    print(f"  鏈€澶у洖鎾? {max_dd*100:.1f}%")
    print(f"  澶忔櫘: {sharpe:.2f}")

# 鍙湅鍒嗘鏃?print("\n" + "=" * 50)
print("鍒嗘鏃ヨ〃鐜板姣旓紙浠呭垎姝у彂鐢熺殑浜ゆ槗鏃ワ級")
div = df[df["ma_state"] != df["hmm_state"]]
for col, label in [
    ("pos_current", "褰撳墠瑙勫垯"),
    ("pos_b_dir_0", "鏂瑰悜B绌轰粨"),
    ("pos_b_dir_05", "鏂瑰悜B鍗婁粨"),
]:
    div_ret = (1 + div["ret_" + col]).prod() - 1
    win = (div["ret_" + col] > 0).mean()
    print(f"\n{label}:")
    print(f"  鍒嗘鏃ョ疮璁℃敹鐩? {div_ret*100:.1f}%")
    print(f"  鍒嗘鏃ヨ儨鐜? {win*100:.0f}%")

# MA鐗涘競+HMM鐔婂競鍦烘櫙璇︾粏鏁版嵁
print("\n" + "=" * 50)
print("MA=鐗涘競 鈫?HMM=鐔婂競 鍦烘櫙璇︾粏鏁版嵁")
bear_bull = df[(df["ma_state"] == "bull") & (df["hmm_state"] == "bear")]
print(f"  鍑虹幇娆℃暟: {len(bear_bull)}")
print(f"  HMM骞冲潎缃俊搴? {bear_bull['hmm_conf'].mean():.0f}%")
print(f"  娆℃棩骞冲潎鏀剁泭: {bear_bull['next_ret'].mean()*100:.2f}%")
print(f"  娆℃棩鑳滅巼: {(bear_bull['next_ret'] > 0).mean()*100:.0f}%")
print(f"  鎸夊綋鍓嶈鍒欎粨浣? {bear_bull['pos_current'].mean():.0%}")
print(f"  鏂瑰悜B绌轰粨閬垮紑鎹熷け: {(-bear_bull['next_ret'].clip(upper=0)).sum()*100:.1f}% cumulative")
print(f"  鏂瑰悜B绌轰粨閿欒繃鏀剁泭: {(bear_bull['next_ret'].clip(lower=0)).sum()*100:.1f}% cumulative")
