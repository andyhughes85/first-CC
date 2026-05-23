# ================== 策略参数 ==================
MARKET_MA_SHORT = 20
MARKET_MA_LONG = 60
ATR_PERIOD = 14
VOL_MA_PERIOD = 20

STOCK_MA5 = 5
STOCK_MA10 = 10
STOCK_MA20 = 20
STOCK_MA60 = 60
VOL_RATIO_MIN = 1.5
VOL_RATIO_MAX = 4.0
MAX_DEVIATION = 0.08

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
