"""HMM隐马尔可夫模型 - 识别市场状态（牛/震荡/熊）
纯numpy/scipy实现，无需hmmlearn"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from scipy.stats import multivariate_normal
from config import HMM_N_COMPONENTS, HMM_N_ITER, MODELS_DIR
from feature_engineer import build_hmm_features


class GaussianHMM:
    """高斯隐马尔可夫模型（纯numpy实现）"""

    def __init__(self, n_components=3, n_iter=100, random_state=42):
        self.n_components = n_components
        self.n_iter = n_iter
        self.random_state = random_state
        np.random.seed(random_state)

        self.pi = None          # 初始状态概率 (n_components,)
        self.A = None           # 转移矩阵 (n_components, n_components)
        self.means = None       # 均值 (n_components, n_features)
        self.covars = None      # 协方差 (n_components, n_features, n_features)

    def _init_params(self, X):
        n_samples, n_features = X.shape

        # 用KMeans初始化参数
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=self.n_components, random_state=self.random_state,
                        n_init="auto")
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
        """E-step: 前向后向算法"""
        n_samples = X.shape[0]

        # 发射概率 (对数形式避免下溢)
        log_emission = np.zeros((n_samples, self.n_components))
        for i in range(self.n_components):
            try:
                mvn = multivariate_normal(self.means[i], self.covars[i], allow_singular=True)
                log_emission[:, i] = mvn.logpdf(X)
            except Exception:
                log_emission[:, i] = -np.inf

        # 前向算法 (log scale)
        log_alpha = np.zeros((n_samples, self.n_components))
        log_alpha[0] = np.log(self.pi + 1e-30) + log_emission[0]
        for t in range(1, n_samples):
            for j in range(self.n_components):
                max_val = np.max(log_alpha[t - 1])
                log_sum = max_val + np.log(
                    np.sum(np.exp(log_alpha[t - 1] - max_val) * self.A[:, j]) + 1e-30
                )
                log_alpha[t, j] = log_sum + log_emission[t, j]

        # 后向算法 (log scale)
        log_beta = np.zeros((n_samples, self.n_components))
        log_beta[-1] = 0
        for t in range(n_samples - 2, -1, -1):
            for i in range(self.n_components):
                max_val = np.max(log_beta[t + 1] + log_emission[t + 1])
                log_beta[t, i] = max_val + np.log(
                    np.sum(np.exp(log_beta[t + 1] + log_emission[t + 1] - max_val) * self.A[i, :]) + 1e-30
                )

        # 后验概率 gamma(t,i) = P(state_t = i | X)
        log_likelihood = np.max(log_alpha[-1]) + np.log(
            np.sum(np.exp(log_alpha[-1] - np.max(log_alpha[-1]))) + 1e-30
        )

        gamma = np.exp(log_alpha + log_beta - log_likelihood)
        gamma = gamma / gamma.sum(axis=1, keepdims=True)

        # xi(t,i,j) = P(state_t=i, state_{t+1}=j | X)
        xi = np.zeros((n_samples - 1, self.n_components, self.n_components))
        for t in range(n_samples - 1):
            for i in range(self.n_components):
                for j in range(self.n_components):
                    xi[t, i, j] = np.exp(
                        log_alpha[t, i] + np.log(self.A[i, j] + 1e-30)
                        + log_emission[t + 1, j] + log_beta[t + 1, j]
                        - log_likelihood
                    )

        return gamma, xi, log_likelihood

    def _m_step(self, X, gamma, xi):
        """M-step: 更新参数"""
        n_components = self.n_components

        # 更新初始状态概率
        self.pi = gamma[0] / gamma[0].sum()

        # 更新转移矩阵
        self.A = xi.sum(axis=0) / xi.sum(axis=0).sum(axis=1, keepdims=True)
        self.A = self.A / self.A.sum(axis=1, keepdims=True)

        # 更新均值
        for i in range(n_components):
            gamma_sum = gamma[:, i].sum()
            if gamma_sum > 1e-10:
                self.means[i] = (gamma[:, i:i+1] * X).sum(axis=0) / gamma_sum

        # 更新协方差
        for i in range(n_components):
            gamma_sum = gamma[:, i].sum()
            if gamma_sum > 1e-10:
                diff = X - self.means[i]
                weighted_diff = gamma[:, i:i+1] * diff
                self.covars[i] = (weighted_diff.T @ diff) / gamma_sum
                self.covars[i] += 1e-6 * np.eye(self.covars[i].shape[0])

    def fit(self, X):
        """训练HMM (Baum-Welch算法)"""
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        self._init_params(X)
        prev_ll = -np.inf

        for iteration in range(self.n_iter):
            gamma, xi, log_likelihood = self._e_step(X)
            self._m_step(X, gamma, xi)

            if abs(log_likelihood - prev_ll) < 1e-6:
                break
            prev_ll = log_likelihood

        return self

    def predict(self, X):
        """Viterbi解码：预测最可能的状态序列"""
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        n_samples = X.shape[0]
        n_states = self.n_components

        # 发射概率 (log)
        log_emission = np.zeros((n_samples, n_states))
        for i in range(n_states):
            try:
                mvn = multivariate_normal(self.means[i], self.covars[i], allow_singular=True)
                log_emission[:, i] = mvn.logpdf(X)
            except Exception:
                log_emission[:, i] = -np.inf

        # Viterbi
        delta = np.zeros((n_samples, n_states))
        psi = np.zeros((n_samples, n_states), dtype=int)
        delta[0] = np.log(self.pi + 1e-30) + log_emission[0]

        for t in range(1, n_samples):
            for j in range(n_states):
                prods = delta[t - 1] + np.log(self.A[:, j] + 1e-30)
                psi[t, j] = np.argmax(prods)
                delta[t, j] = prods[psi[t, j]] + log_emission[t, j]

        # 回溯
        states = np.zeros(n_samples, dtype=int)
        states[-1] = np.argmax(delta[-1])
        for t in range(n_samples - 2, -1, -1):
            states[t] = psi[t + 1, states[t + 1]]

        return states

    def predict_proba(self, X):
        """计算各状态的后验概率"""
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        gamma, _, _ = self._e_step(X)
        return gamma

    def score(self, X):
        """计算对数似然"""
        X = np.asarray(X, dtype=np.float64)
        _, _, log_likelihood = self._e_step(X)
        return log_likelihood


class MarketRegimeHMM:
    """HMM市场状态识别器"""

    STATE_MAP = {0: "bear", 1: "oscillate", 2: "bull"}

    def __init__(self, n_components=HMM_N_COMPONENTS):
        self.n_components = n_components
        self.model = GaussianHMM(n_components=n_components, n_iter=HMM_N_ITER)
        self.scaler = StandardScaler()
        self.state_label_map = {}

    def _label_states(self):
        """根据均值自动标记状态"""
        ret_means = self.model.means[:, 0]
        sorted_idx = np.argsort(ret_means)
        mapping = {}
        mapping[sorted_idx[0]] = "bear"
        mapping[sorted_idx[1]] = "oscillate"
        mapping[sorted_idx[2]] = "bull"

        reverse_map = {"bear": 0, "oscillate": 1, "bull": 2}
        self.state_label_map = {k: reverse_map[v] for k, v in mapping.items()}

    def fit(self, df, force_retrain=True):
        """训练HMM模型并识别市场状态"""
        features = build_hmm_features(df)
        X = features.values
        X_scaled = self.scaler.fit_transform(X)

        self.model.fit(X_scaled)
        self._label_states()

        # 解码所有状态
        states = self.model.predict(X_scaled)
        df["hmm_state"] = states
        df["hmm_label"] = df["hmm_state"].map(
            {v: k for k, v in self.state_label_map.items()}
        )
        return df

    def predict_state(self, df):
        """预测最新市场状态"""
        features = build_hmm_features(df)
        X_scaled = self.scaler.transform(features.values)
        states = self.model.predict(X_scaled)
        return int(states[-1])

    def predict_state_proba(self, df):
        """预测各状态概率"""
        features = build_hmm_features(df)
        X_scaled = self.scaler.transform(features.values)
        proba = self.model.predict_proba(X_scaled)
        return proba[-1]

    def get_current_regime(self, df):
        """获取当前市场状态描述"""
        state = self.predict_state(df)
        proba = self.predict_state_proba(df)

        # 映射状态标签
        label = None
        for orig_state, mapped_label in self.state_label_map.items():
            if orig_state == state:
                label = mapped_label
                break
        label_name = {"bull": "上涨(牛)", "bear": "下跌(熊)", "oscillate": "震荡"}.get(
            label, str(label)
        )

        # 构建概率字典
        prob_dict = {}
        for orig_state, mapped_label in self.state_label_map.items():
            idx = list(self.state_label_map.values()).index(orig_state)
            prob_label = {0: "bear", 1: "oscillate", 2: "bull"}.get(orig_state, f"state_{orig_state}")
            prob_dict[prob_label] = float(proba[idx])

        return {
            "state_code": int(state),
            "state_label": label,
            "state_name": label_name,
            "probabilities": prob_dict,
        }

    def save(self, path=None):
        """保存模型"""
        path = path or os.path.join(MODELS_DIR, "hmm_model.pkl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({
            "model": self.model,
            "scaler": self.scaler,
            "state_label_map": self.state_label_map,
        }, path)

    def load(self, path=None):
        """加载模型"""
        path = path or os.path.join(MODELS_DIR, "hmm_model.pkl")
        if os.path.exists(path):
            data = joblib.load(path)
            self.model = data["model"]
            self.scaler = data["scaler"]
            self.state_label_map = data.get("state_label_map", {})


def add_hmm_feature_to_stock(stock_df, index_df, hmm_model):
    """为个股添加HMM市场状态特征"""
    index_states = index_df[["date", "hmm_state", "hmm_label"]].copy()
    stock_with_hmm = stock_df.merge(index_states, on="date", how="left")
    stock_with_hmm["hmm_state"] = stock_with_hmm["hmm_state"].fillna(0).astype(int)
    stock_with_hmm["hmm_label"] = stock_with_hmm["hmm_label"].fillna("unknown")
    return stock_with_hmm
