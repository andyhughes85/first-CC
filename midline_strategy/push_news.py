"""发送最新市场消息到Telegram"""
import akshare as ak
import requests
import logging
from datetime import datetime

TELEGRAM_TOKEN = "8991675281:AAFbGF0xvlpzs9RZafY8U6k8cmwEoYKe02s"
TELEGRAM_CHAT_ID = "7398413981"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }, timeout=10)
    result = resp.json()
    if result.get("ok"):
        print("✅ 推送成功")
    else:
        print("❌ 推送失败:", resp.text)

# 获取最新财经新闻
print("获取市场消息...")
try:
    news_df = ak.stock_news_em(symbol="DJI")  # 使用道琼斯获取全球市场新闻
    news_items = news_df.head(5)
    text = f"【市场快讯】{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    for _, row in news_items.iterrows():
        text += f"📰 {row.get('标题', row.get('title', '无标题'))}\n\n"
    send_telegram(text)
except Exception as e:
    print(f"stock_news_em 失败: {e}")
    try:
        news_df = ak.news_other("财经")
        news_items = news_df.head(5)
        text = f"【市场快讯】{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        for _, row in news_items.iterrows():
            text += f"📰 {row.get('title', '无标题')}\n\n"
        send_telegram(text)
    except Exception as e2:
        print(f"也失败: {e2}")
        send_telegram(f"【市场快讯】{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n今日暂无最新消息推送。")
