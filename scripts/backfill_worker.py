"""单只股票回填工作进程"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ["STREAMLIT_RUN"] = "1"
import warnings
warnings.filterwarnings("ignore")

code = sys.argv[1]
from data_fetcher import download_stock_history, save_data
df = download_stock_history(code, 180)
if df is not None and not df.empty:
    save_data(df, "stock_daily")
    print(f"OK:{code}:{len(df)}")
else:
    print(f"FAIL:{code}:empty")
    sys.exit(1)
