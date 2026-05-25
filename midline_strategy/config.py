# ================== 策略参数 ==================
MARKET_MA_SHORT = 20
MARKET_MA_LONG = 60
ATR_PERIOD = 14
VOL_MA_PERIOD = 20

STOCK_MA5 = 5
STOCK_MA10 = 10
STOCK_MA20 = 20
STOCK_MA60 = 60
VOL_RATIO_MIN = 1.2
VOL_RATIO_MAX = 4.0
MAX_DEVIATION = 0.05

# ================== KAMA 自适应均线 ==================
KAMA_ER_FAST = 2       # 快速 EMA 周期（固定）
KAMA_ER_SLOW = 30      # 慢速 EMA 周期（固定）
KAMA_MARKET_SHORT = 10  # 市场短期 ER 周期（替代 MA20）
KAMA_MARKET_LONG = 30   # 市场长期 ER 周期（替代 MA60）
KAMA_STOCK_SHORT = 5    # 个股短期 ER 周期（替代 MA5）
KAMA_STOCK_MID = 10     # 个股中短期 ER 周期（替代 MA10）
KAMA_STOCK_LONG = 20    # 个股中长期 ER 周期（替代 MA20）
KAMA_STOCK_MAIN = 30    # 个股主趋势 ER 周期（替代 MA60）

# ================== 风控参数 ==================
MAX_POSITION_PER_STOCK = 0.10   # 单只股票仓位上限
STOP_LOSS = -0.07               # 止损线
TAKE_PROFIT = 0.10              # 止盈线
TIME_STOP_DAYS = 15             # 时间止损天数

# ================== 行业 ==================
TOP_INDUSTRIES_N = 5
INDUSTRY_MOMENTUM_DAYS = 20

# ================== 数据 ==================
INDEX_CODE = "000300"          # 沪深300
SINA_INDEX_SYMBOL = "sh000300"
START_DATE = "20200101"
DB_PATH = "trading_data.db"

# ================== 推送 ==================
PUSH_TYPE = "telegram"  # "telegram" | "serverchan"
TELEGRAM_TOKEN = "8991675281:AAFbGF0xvlpzs9RZafY8U6k8cmwEoYKe02s"
TELEGRAM_CHAT_ID = "-5277218158"
SERVERCHAN_KEY = "SCT353028TEFdxCoH9ZCauuBaDj1R7DBM8"
TELEGRAM_PROXY = "socks5h://127.0.0.1:1080"  # Telegram代理（Vultr SOCKS5隧道）

# ================== 定时 ==================
SCHEDULE_TIME = "15:35"
SCHEDULE_RETRY_TIME = "18:00"
