"""HMM 市场状态识别 — 纯 numpy 实现，用于中线策略"""

import os
import joblib
import numpy as np
import pandas as pd
from scipy.stats import multivariate_normal

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "hmm_market.pkl")


class GaussianHMM:
    """高斯隐马尔可夫模型（纯 numpy/scipy，无需 hmmlearn）"""

    def __init__(self, n_components=3, n_iter=100, random_state=42):
        self.n_components = n_components
        self.n_iter = n_iter
        self.random_state = random_state
        np.random.seed(random_state)
        self.pi = None
        self.A = None
        self.means = None
        self.covars = None

    def _init_params(self, X):
        n_features = X.shape[1]
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=self.n_components, random_state=self.random_state, n_init="auto")
        labels = kmeans.fit_predict(X)
        self.pi = np.ones(self.n_components) / self.n_components
        self.A = np.ones((self.n_components, self.n_components)) * 0.1
        np.fill_diagonal(self.A, 0.8)
        self.A = self.A / self.A.sum(axis=1, keepdims=True)
        self.means = kmeans.cluster_centers_
        self.covars = np.zeros((self.n_components, n_features, n_features))
        for i in range(self.n_components):
            cluster_data = X[labels == i]
            if len(cluster_data) > 1:
                self.covars[i] = np.cov(cluster_data, rowvar=False) + 1e-6 * np.eye(n_features)
            else:
                self.covars[i] = np.eye(n_features)

    def _e_step(self, X):
        n_samples = X.shape[0]
        log_emission = np.zeros((n_samples, self.n_components))
        for i in range(self.n_components):
            try:
                mvn = multivariate_normal(self.means[i], self.covars[i], allow_singular=True)
                log_emission[:, i] = mvn.logpdf(X)
            except Exception:
                log_emission[:, i] = -np.inf

        log_alpha = np.zeros((n_samples, self.n_components))
        log_alpha[0] = np.log(self.pi + 1e-30) + log_emission[0]
        for t in range(1, n_samples):
            for j in range(self.n_components):
                max_v = np.max(log_alpha[t - 1])
                log_alpha[t, j] = max_v + np.log(
                    np.sum(np.exp(log_alpha[t - 1] - max_v) * self.A[:, j]) + 1e-30
                ) + log_emission[t, j]

        log_beta = np.zeros((n_samples, self.n_components))
        log_beta[-1] = 0
        for t in range(n_samples - 2, -1, -1):
            for i in range(self.n_components):
                max_v = np.max(log_beta[t + 1] + log_emission[t + 1])
                log_beta[t, i] = max_v + np.log(
                    np.sum(np.exp(log_beta[t + 1] + log_emission[t + 1] - max_v) * self.A[i, :]) + 1e-30
                )

        log_likelihood = np.max(log_alpha[-1]) + np.log(
            np.sum(np.exp(log_alpha[-1] - np.max(log_alpha[-1]))) + 1e-30
        )
        gamma = np.exp(log_alpha + log_beta - log_likelihood)
        gamma = gamma / gamma.sum(axis=1, keepdims=True)

        xi = np.zeros((n_samples - 1, self.n_components, self.n_components))
        for t in range(n_samples - 1):
            for i in range(self.n_components):
                for j in range(self.n_components):
                    xi[t, i, j] = np.exp(
                        log_alpha[t, i] + np.log(self.A[i, j] + 1e-30)
                        + log_emission[t + 1, j] + log_beta[t + 1, j] - log_likelihood
                    )
        return gamma, xi, log_likelihood

    def _m_step(self, X, gamma, xi):
        self.pi = gamma[0] / gamma[0].sum()
        self.A = xi.sum(axis=0) / xi.sum(axis=0).sum(axis=1, keepdims=True)
        self.A = self.A / self.A.sum(axis=1, keepdims=True)
        for i in range(self.n_components):
            gs = gamma[:, i].sum()
            if gs > 1e-10:
                self.means[i] = (gamma[:, i:i+1] * X).sum(axis=0) / gs
        for i in range(self.n_components):
            gs = gamma[:, i].sum()
            if gs > 1e-10:
                diff = X - self.means[i]
                self.covars[i] = (gamma[:, i:i+1] * diff).T @ diff / gs
                self.covars[i] += 1e-6 * np.eye(self.covars[i].shape[0])

    def fit(self, X):
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        self._init_params(X)
        prev_ll = -np.inf
        for _ in range(self.n_iter):
            gamma, xi, log_likelihood = self._e_step(X)
            self._m_step(X, gamma, xi)
            if abs(log_likelihood - prev_ll) < 1e-6:
                break
            prev_ll = log_likelihood
        return self

    def predict(self, X):
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        n_samples, n_states = X.shape[0], self.n_components
        log_emission = np.zeros((n_samples, n_states))
        for i in range(n_states):
            try:
                mvn = multivariate_normal(self.means[i], self.covars[i], allow_singular=True)
                log_emission[:, i] = mvn.logpdf(X)
            except Exception:
                log_emission[:, i] = -np.inf
        delta = np.zeros((n_samples, n_states))
        psi = np.zeros((n_samples, n_states), dtype=int)
        delta[0] = np.log(self.pi + 1e-30) + log_emission[0]
        for t in range(1, n_samples):
            for j in range(n_states):
                prods = delta[t - 1] + np.log(self.A[:, j] + 1e-30)
                psi[t, j] = np.argmax(prods)
                delta[t, j] = prods[psi[t, j]] + log_emission[t, j]
        states = np.zeros(n_samples, dtype=int)
        states[-1] = np.argmax(delta[-1])
        for t in range(n_samples - 2, -1, -1):
            states[t] = psi[t + 1, states[t + 1]]
        return states

    def predict_proba(self, X):
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        gamma, _, _ = self._e_step(X)
        return gamma


def build_hmm_features(df):
    """构建 HMM 输入特征（4维：对数收益、波动率、成交量变化、价格位置）"""
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
    return features.fillna(0).clip(-10, 10)  # 裁剪极端值防溢出


def train_hmm_model(index_df):
    """用指数历史数据训练 HMM，返回 MarketRegimeHMM 实例"""
    from sklearn.preprocessing import StandardScaler

    features = build_hmm_features(index_df)
    X = features.values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    hmm = GaussianHMM(n_components=3, n_iter=100)
    hmm.fit(X_scaled)

    # 按收益率均值自动标注状态
    sorted_idx = np.argsort(hmm.means[:, 0])
    state_map = {int(sorted_idx[0]): "bear", int(sorted_idx[1]): "oscillation", int(sorted_idx[2]): "bull"}

    return hmm, scaler, state_map


def load_hmm_model(path=None):
    """加载已保存的 HMM 模型"""
    path = path or MODEL_PATH
    if not os.path.exists(path):
        return None, None, None
    data = joblib.load(path)
    return data["hmm"], data["scaler"], data["state_map"]


def save_hmm_model(hmm, scaler, state_map, path=None):
    """保存 HMM 模型"""
    path = path or MODEL_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump({"hmm": hmm, "scaler": scaler, "state_map": state_map}, path)


def predict_market_state(index_df, hmm, scaler, state_map):
    """预测最新市场状态，返回 (state_label, probabilities_dict)"""
    features = build_hmm_features(index_df)
    X_scaled = scaler.transform(features.values)
    states = hmm.predict(X_scaled)
    proba = hmm.predict_proba(X_scaled)

    latest_state = int(states[-1])
    latest_proba = proba[-1]
    label = state_map.get(latest_state, "oscillation")

    prob_dict = {}
    reverse = {"bull": "bull", "oscillation": "oscillation", "bear": "bear"}
    for state_idx, state_label in state_map.items():
        prob_dict[state_label] = float(latest_proba[state_idx])

    return label, prob_dict
