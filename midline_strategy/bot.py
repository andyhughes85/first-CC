"""Telegram 机器人 — 接收自然语言指令，执行选股操作"""

import subprocess
import logging
import os
import time
import json
import requests
import signal
import sys

# ── 配置 ──
TOKEN = "8991675281:AAFbGF0xvlpzs9RZafY8U6k8cmwEoYKe02s"
ALLOWED_CHAT_IDS = {"-5277218158", "7398413981"}
PROXY = "socks5h://127.0.0.1:1080"
BASE_DIR = "/root/first-CC/midline_strategy"
API = f"https://api.telegram.org/bot{TOKEN}"
POLL_INTERVAL = 3  # 轮询间隔（秒）

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=os.path.join(BASE_DIR, "bot.log"),
)
logger = logging.getLogger(__name__)

# 已处理的消息ID
_processed = set()


def tg(method, data=None, timeout=15):
    """调用 Telegram API"""
    sess = requests.Session()
    sess.proxies = {"https": PROXY, "http": PROXY}
    try:
        r = sess.post(f"{API}/{method}", json=data, timeout=timeout)
        return r.json()
    except Exception as e:
        logger.error(f"Telegram API 调用失败: {e}")
        return {"ok": False}


def run(cmd, timeout=60):
    """执行 shell 命令"""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=BASE_DIR
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out.strip() or "(无输出)"
    except subprocess.TimeoutExpired:
        return f"(超时: >{timeout}秒)"
    except Exception as e:
        return f"(失败: {e})"


def parse_intent(text):
    """自然语言 -> (回复前缀, [命令列表])"""
    t = text.strip()

    if t == "/start":
        return ("选股机器人已启动！\n\n"
                "发送「帮助」查看我能做什么。", [])

    if any(kw in t for kw in ["跑选股", "运行", "选股", "开跑", "跑一下", "pipeline", "跑策略"]):
        return "正在跑选股...", [
            f"cd {BASE_DIR} && python pipeline.py"
        ]

    if any(kw in t for kw in ["日志", "log", "看看", "最近", "运行情况"]):
        return "最近运行日志：", [
            f"tail -50 {BASE_DIR}/trading_bot.log 2>/dev/null || echo '日志文件不存在'"
        ]

    if any(kw in t for kw in ["更新", "pull", "拉取", "同步", "升级"]):
        return "正在从 GitHub 拉取最新代码...", [
            "cd /root/first-CC && git pull"
        ]

    if any(kw in t for kw in ["市场", "状态", "行情", "大盘"]):
        code = (
            "from market_state import judge_market_state, add_index_indicators;"
            "from data_fetcher import fetch_index_incremental;"
            "idx = fetch_index_incremental();"
            "idx = add_index_indicators(idx);"
            "info = judge_market_state(idx);"
            "print(f'状态: {info[\"state\"]}');"
            "print(f'仓位上限: {info[\"pos_limit\"]:.0%}');"
            "print(f'沪深300: {info[\"index_close\"]:.2f} ({info[\"index_pct\"]:+.2%})');"
            "print(f'趋势: {info[\"trend_detail\"]}')"
        )
        return "当前市场状态：", [
            f"cd {BASE_DIR} && python -c \"{code}\""
        ]

    if any(kw in t for kw in ["定时", "crontab", "任务", "排程"]):
        return "定时任务：", ["crontab -l"]

    if any(kw in t for kw in ["回测", "backtest", "历史测试"]):
        return "正在运行回测...（较慢）", [
            f"cd {BASE_DIR} && python backtest.py --summary 2>&1 | tail -30"
        ]

    if any(kw in t for kw in ["数据库", "db", "数据量", "股票池"]):
        code = (
            "import sqlite3;"
            "conn = sqlite3.connect('trading_data.db');"
            "tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall();"
            "for t in tables:"
            "  cnt = conn.execute(f'SELECT COUNT(*) FROM {t[0]}').fetchone()[0];"
            "  print(f'  {t[0]}: {cnt} 行');"
            "conn.close()"
        )
        return "数据库概况：", [
            f"ls -lh {BASE_DIR}/trading_data.db",
            f"cd {BASE_DIR} && python -c \"{code}\"",
        ]

    if any(kw in t for kw in ["帮助", "help", "命令", "功能", "怎么用"]):
        return (
            "我可以听懂这些指令：\n\n"
            "跑选股 — 立即运行选股策略\n"
            "看日志 — 查看最近运行日志\n"
            "更新代码 — 从 GitHub 拉取最新代码\n"
            "市场状态 — 查看当前大盘状态\n"
            "定时任务 — 查看 crontab 设置\n"
            "回测 — 运行回测\n"
            "数据库 — 查看数据库概况\n"
            "帮助/bot — 显示这条消息\n"
            "重启bot — 重启机器人",
            []
        )

    if any(kw in t for kw in ["重启", "重启bot"]):
        return "正在重启机器人...", []
        # 重启在外部处理

    return None, []


def handle_updates():
    """轮询获取新消息"""
    offset = 0
    while True:
        try:
            resp = tg("getUpdates", {
                "offset": offset,
                "timeout": 10,
                "allowed_updates": ["message"],
            })
            if not resp.get("ok"):
                time.sleep(POLL_INTERVAL)
                continue

            for upd in resp.get("result", []):
                update_id = upd["update_id"]
                offset = update_id + 1

                msg = upd.get("message")
                if not msg or not msg.get("text"):
                    continue
                if update_id in _processed:
                    continue
                _processed.add(update_id)

                chat_id = str(msg["chat"]["id"])
                text = msg["text"].strip()

                logger.info(f"来自 {chat_id}: {text}")

                # 权限检查
                if chat_id not in ALLOWED_CHAT_IDS:
                    tg("sendMessage", {
                        "chat_id": chat_id,
                        "text": "你没有权限使用此机器人",
                    })
                    continue

                # 解析意图
                reply, commands = parse_intent(text)

                if reply == "正在重启机器人...":
                    tg("sendMessage", {"chat_id": chat_id, "text": "机器人即将重启..."})
                    os.kill(os.getpid(), signal.SIGTERM)
                    return

                if commands:
                    tg("sendMessage", {
                        "chat_id": chat_id,
                        "text": f"{reply}\n⏳ 执行中..."
                    })
                    outputs = []
                    for cmd in commands:
                        timeout = 120 if "backtest" in cmd else 60
                        out = run(cmd, timeout=timeout)
                        outputs.append(out)
                    result = "\n\n".join(outputs)
                    if len(result) > 3500:
                        result = result[:3500] + "\n\n...（已截断）"
                    tg("sendMessage", {
                        "chat_id": chat_id,
                        "text": f"✅ 完成\n{result}"
                    })
                elif reply:
                    tg("sendMessage", {"chat_id": chat_id, "text": reply})
                else:
                    tg("sendMessage", {
                        "chat_id": chat_id,
                        "text": "我没理解。试试发送「帮助」查看我能做什么。"
                    })

        except Exception as e:
            logger.error(f"轮询异常: {e}")
            time.sleep(POLL_INTERVAL)


def main():
    logger.info("机器人启动")
    print("机器人已启动，等待指令...")
    handle_updates()


if __name__ == "__main__":
    main()
