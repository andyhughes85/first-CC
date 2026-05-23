"""市场状态判断 - HMM + 简化版双均线备用"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from scipy.stats import multivariate_normal
from config import MODELS_DIR, HMM_N_COMPONENTS, HMM_N_ITER
from config import MA_SHORT, MA_LONG, VOLATILITY_THRESHOLD


class GaussianHMM:
    """纯numpy实现的高斯HMM"""

    def __init__(self, n_components=3, n_iter=500, random_state=42):
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
        kmeans = KMeans(n_clusters=self.n_components, random_state=42, n_init="auto")
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
                log_alpha[t, j] = (max_v + np.log(np.sum(np.exp(log_alpha[t - 1] - max_v) * self.A[:, j]) + 1e-30)
                                   + log_emission[t, j])

        log_beta = np.zeros((n_samples, self.n_components))
        log_beta[-1] = 0
        for t in range(n_samples - 2, -1, -1):
            for i in range(self.n_components):
                max_v = np.max(log_beta[t + 1] + log_emission[t + 1])
                log_beta[t, i] = max_v + np.log(
                    np.sum(np.exp(log_beta[t + 1] + log_emission[t + 1] - max_v) * self.A[i, :]) + 1e-30)

        log_likelihood = np.max(log_alpha[-1]) + np.log(np.sum(np.exp(log_alpha[-1] - np.max(log_alpha[-1]))) + 1e-30)
        gamma = np.exp(log_alpha + log_beta - log_likelihood)
        gamma = gamma / gamma.sum(axis=1, keepdims=True)

        xi = np.zeros((n_samples - 1, self.n_components, self.n_components))
        for t in range(n_samples - 1):
            for i in range(self.n_components):
                for j in range(self.n_components):
                    xi[t, i, j] = np.exp(log_alpha[t, i] + np.log(self.A[i, j] + 1e-30)
                                         + log_emission[t + 1, j] + log_beta[t + 1, j] - log_likelihood)
        return gamma, xi, log_likelihood

    def _m_step(self, X, gamma, xi):
        self.pi = gamma[0] / (gamma[0].sum() + 1e-30)
        self.A = xi.sum(axis=0) / (xi.sum(axis=0).sum(axis=1, keepdims=True) + 1e-30)
        for i in range(self.n_components):
            gs = gamma[:, i].sum()
            if gs > 1e-10:
                self.means[i] = (gamma[:, i:i+1] * X).sum(axis=0) / gs
        for i in range(self.n_components):
            gs = gamma[:, i].sum()
            if gs > 1e-10:
                diff = X - self.means[i]
                self.covars[i] = ((gamma[:, i:i+1] * diff).T @ diff) / gs
                self.covars[i] += 1e-6 * np.eye(self.covars[i].shape[0])

    def fit(self, X):
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        self._init_params(X)
        prev_ll = -np.inf
        for it in range(self.n_iter):
            gamma, xi, ll = self._e_step(X)
            self._m_step(X, gamma, xi)
            if abs(ll - prev_ll) < 1e-6:
                break
            prev_ll = ll
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
            except:
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
        gamma, _, _ = self._e_step(X)
        return gamma


class MarketStateDetector:
    """市场状态识别器 - HMM + 简化版双均线备用"""

    def __init__(self, use_hmm=True):
        self.use_hmm = use_hmm
        self.hmm = GaussianHMM(n_components=HMM_N_COMPONENTS, n_iter=HMM_N_ITER)
        self.scaler = StandardScaler()
        self.state_label_map = {}

    def _label_states(self):
        ret_means = self.hmm.means[:, 0]
        sorted_idx = np.argsort(ret_means)
        mapping = {sorted_idx[0]: "bear", sorted_idx[1]: "oscillate", sorted_idx[2]: "bull"}
        reverse_map = {"bear": 0, "oscillate": 1, "bull": 2}
        self.state_label_map = {k: reverse_map[v] for k, v in mapping.items()}

    def _build_hmm_features(self, df):
        """构建HMM输入特征"""
        features = pd.DataFrame(index=df.index)
        features["log_return"] = np.log(df["close"] / df["close"].shift(1))
        features["volatility"] = features["log_return"].rolling(10).std()
        volume = df["volume"] if "volume" in df.columns else df.get("amount", df["close"] * 0)
        features["volume_change"] = volume.pct_change(5)
        features["price_position"] = (df["close"] - df["close"].rolling(20).min()) / (
            df["close"].rolling(20).max() - df["close"].rolling(20).min() + 1e-10
        )
        return features.fillna(0)

    def _simple_regime(self, df):
        """简化版：双均线+波动率判断市场状态"""
        last = df.iloc[-1]
        ma_s = df["close"].rolling(MA_SHORT).mean().iloc[-1]
        ma_l = df["close"].rolling(MA_LONG).mean().iloc[-1]
        returns = df["close"].pct_change().dropna()
        volatility = returns.tail(20).std()

        above_ma_short = last["close"] > ma_s
        above_ma_long = last["close"] > ma_l
        low_volatility = volatility < VOLATILITY_THRESHOLD

        if above_ma_short and above_ma_long and low_volatility:
            return "bull"
        elif not above_ma_short and not above_ma_long:
            return "bear"
        else:
            return "oscillate"

    def fit(self, index_df):
        """训练HMM或使用简化版"""
        if not self.use_hmm:
            regime = self._simple_regime(index_df)
            index_df["hmm_state"] = {"bear": 0, "oscillate": 1, "bull": 2}.get(regime, 1)
            index_df["hmm_label"] = regime
            return index_df

        features = self._build_hmm_features(index_df)
        X = self.scaler.fit_transform(features.values)
        self.hmm.fit(X)
        self._label_states()

        states = self.hmm.predict(X)
        index_df["hmm_state"] = states
        index_df["hmm_label"] = index_df["hmm_state"].map(
            {v: k for k, v in self.state_label_map.items()}
        )
        return index_df

    def get_current(self, index_df):
        """获取当前市场状态"""
        if self.use_hmm and hasattr(self.hmm, "means") and self.hmm.means is not None:
            features = self._build_hmm_features(index_df)
            X = self.scaler.transform(features.values)
            state = int(self.hmm.predict(X)[-1])
            proba = self.hmm.predict_proba(X)[-1]
            label = self.state_label_map.get(state, "oscillate")
        else:
            label = self._simple_regime(index_df)
            state = {"bear": 0, "oscillate": 1, "bull": 2}.get(label, 1)
            proba = np.array([0.33, 0.34, 0.33])

        name_map = {"bull": "上涨(牛)", "bear": "下跌(熊)", "oscillate": "震荡"}
        return {
            "state_code": state,
            "state_label": label,
            "state_name": name_map.get(label, str(label)),
            "probabilities": {"bull": float(proba[2]), "oscillate": float(proba[1]), "bear": float(proba[0])},
        }

    def get_position_suggest(self, regime_label):
        """根据市场状态给出仓位建议"""
        suggestions = {
            "bull": {"position": "80-100%", "desc": "可重仓操作"},
            "oscillate": {"position": "40-60%", "desc": "中等仓位，精选个股"},
            "bear": {"position": "0-20%", "desc": "空仓或轻仓观望"},
        }
        return suggestions.get(regime_label, {"position": "50%", "desc": "谨慎操作"})

    def save(self, path=None):
        path = path or os.path.join(MODELS_DIR, "hmm_model.pkl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({"model": self.hmm, "scaler": self.scaler,
                     "state_label_map": self.state_label_map}, path)

    def load(self, path=None):
        path = path or os.path.join(MODELS_DIR, "hmm_model.pkl")
        if os.path.exists(path):
            data = joblib.load(path)
            self.hmm = data["model"]
            self.scaler = data["scaler"]
            self.state_label_map = data.get("state_label_map", {})
