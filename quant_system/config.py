"""系统配置"""

# ========== 基本路径 ==========
MODELS_DIR = "models"
DATA_DIR = "data"
CACHE_DIR = "cache"

# ========== 股票池配置 ==========
# 全A股自动获取，这里是指数代码
INDEX_CODE = "000300"          # 沪深300
BENCHMARK_SYMBOL = "sh000300"

# 训练日期范围
TRAIN_START_DATE = "20200101"

# ========== 市场状态判断 ==========
# HMM 参数
HMM_N_COMPONENTS = 3
HMM_N_ITER = 1000

# 简化版（双均线+波动率）备用
MA_SHORT = 20
MA_LONG = 60
VOLATILITY_THRESHOLD = 0.4

# ========== 行业配置 ==========
TOP_INDUSTRIES_N = 5          # 取动量前N个行业
INDUSTRY_MOMENTUM_DAYS = 20   # 行业动量计算窗口
INDUSTRY_TURNOVER_THRESHOLD = 0.3  # 成交额占比变化阈值（防止过度拥挤）

# ========== 买入触发条件（核心规则引擎）==========
# 条件A - 均线
MA_PERIODS = [5, 10, 20, 60]
MAX_PRICE_DEVIATION_MA20 = 0.08   # 偏离20日线不超过8%

# 条件B - 成交量
VOLUME_MA_PERIOD = 20
VOLUME_MIN_RATIO = 1.5       # 今日量 > 1.5倍均量
VOLUME_MAX_RATIO = 4.0       # 今日量 < 4倍均量（排除异常放量）

# 条件C - 短期回调确认（可选）
PULLBACK_LOOKBACK = 3        # 前N天
PULLBACK_VOLUME_RATIO = 0.7  # 缩量到均量的70%以下

# 条件D - 评分权重
SCORE_WEIGHTS = {
    "trend": 0.30,            # 趋势得分
    "volume": 0.25,           # 量能得分
    "momentum": 0.20,         # 动量得分
    "industry": 0.15,         # 行业得分
    "risk": 0.10,             # 风险得分（CVaR）
}

# ========== LightGBM 打分 ==========
LGB_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
    "min_data_in_leaf": 50,
    "is_unbalance": True,
}
N_ESTIMATORS = 200
EARLY_STOPPING_ROUNDS = 50
TRAIN_SPLIT_RATIO = 0.8

FORWARD_DAYS = 5             # 未来5日
BUY_THRESHOLD = 0.03         # 收益>3%视为正样本

# ========== CVaR 风控 ==========
CVAR_CONFIDENCE = 0.95
CVAR_LOOKBACK_DAYS = 252
MAX_CVAR_RATIO = -0.05       # CVaR > -5%

# ========== 信号输出 ==========
MIN_SCORE = 0.60             # 最低综合评分
MAX_SIGNALS_PER_DAY = 10     # 每日最多推送信号数

# ========== 推送配置 ==========
PUSH_CONFIG = {
    "qy_webhook": "",         # 企业微信机器人Webhook URL
    "dingtalk_webhook": "",   # 钉钉机器人Webhook URL
    "serverchan_key": "",     # Server酱Key
    "smtp_host": "",          # 邮件SMTP
    "smtp_port": 465,
    "smtp_user": "",
    "smtp_pass": "",
    "email_to": "",
}

# ========== 定时任务 ==========
SCHEDULE_TIME = "15:10"      # 每日盘后执行时间
