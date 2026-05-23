# CLAUDE.md

## Project Overview

每日选股推送 — A股中线波段选股系统，全市场扫描 + 技术指标筛选 + Telegram推送。

仓库包含三个子系统：
- **`midline_strategy/`** — 主力中线波段策略（定时运行中）
- **`quant_system/`** — 量化系统 v2（HMM + LightGBM + CVaR 风控，实验性）
- **`youtube-studio/`** — YouTube 频道自动化（脚本生成 + AI 缩略图 + n8n 工作流 + 上传）

## Tech Stack

- **Python 3.14** (akshare, baostock, pandas, requests, schedule, lightgbm, hmmlearn)
- **SQLite** (本地缓存股票数据)
- **Telegram Bot** / Server酱 / 企业微信 (消息推送)
- **部署**: 阿里云 Ubuntu + crontab 定时任务

## Modules — midline_strategy/

| 模块 | 说明 |
|------|------|
| `data_fetcher.py` | 数据获取：全市场交易池、指数/个股日线、多源降级、并发快照 |
| `signal_engine.py` | 信号生成：均线多头+放量+低偏离，向量化筛选 |
| `market_state.py` | 市场状态判断：均线、ATR、仓位控制 |
| `push_service.py` | 消息推送：Telegram / Server酱 / 企业微信 |
| `pipeline.py` | 主流程调度：15:35 / 18:00 定时任务 |
| `config.py` | 策略参数配置 |
| `utils.py` | 工具函数（交易日判断等） |
| `backtest.py` | 回测引擎，逐日模拟，2018~2025 历史区间 |
| `bot.py` | Telegram 机器人 — 接收中文指令，执行选股操作 |

## Modules — quant_system/

| 模块 | 说明 |
|------|------|
| `pipeline.py` | `DailyPipeline` 主流水线：市场状态→行业筛选→数据获取→规则引擎→评分→推送 |
| `market_state.py` | HMM 市场状态检测器（3状态：牛/震荡/熊） |
| `industry_selector.py` | 行业动量筛选（20日） |
| `rule_engine.py` | 规则引擎：均线多头+放量+回调确认 |
| `signal_generator.py` | 信号生成器 |
| `stock_scorer.py` | LightGBM 打分模型 |
| `feature_engineer.py` | 特征工程（技术指标 40+ 维） |
| `lgb_model.py` | LightGBM 训练封装 |
| `hmm_model.py` | 隐马尔可夫模型 |
| `cvar_risk.py` | CVaR 风险计算 |
| `risk_manager.py` | 风险管理器 |
| `data_fetcher.py` | 多源数据获取 |
| `push_notifier.py` | 多渠道推送 |
| `config.py` | 系统配置 |

## Key Architecture — midline_strategy

- **全市场A股池**：`refresh_trading_pool()` 通过 `ak.stock_zh_a_spot()` 获取全市场约5000只股票，剔除ST，多源降级
- **增量数据**：`fetch_index_incremental()` / `update_stock_data_daily()` 仅拉取缺失日期
- **并发快照**：`fetch_daily_snapshot()` 全市场并行获取当日行情
- **定时任务**：`schedule` 库，15:35 / 18:00 执行，周五 18:00 周报
- **推送**：`push_service.py` 统一入口，Telegram 为主

## Signal Conditions (midline_strategy/signal_engine.py)

1. 均线多头排列：MA5 > MA10 > MA20 > MA60
2. 放量：量比 1.5~4.0
3. 偏离 20 日线 < 8%
4. 熊市额外：量比 > 2.5

Risk: 单股 ≤ 10%，止损 -7%，止盈 10%，时间止损 15 自然日

## Telegram Bot (bot.py) — 手机自然语言控制

运行在服务器上的 systemd 服务 `stock-bot.service`，开机自启，断线自动重连。

**支持的指令：**
- **跑选股** — 立即运行选股策略
- **看日志** — 查看最近运行日志
- **更新代码** — 从 GitHub 拉取最新代码
- **市场状态** — 查看当前大盘状态
- **定时任务** — 查看 crontab 设置
- **回测** — 运行回测
- **数据库** — 查看数据库概况
- **帮助** — 显示可用指令

**Telegram Config (config.py)**

- Token: `8991675281:AAFbGF0xvlpzs9RZafY8U6k8cmwEoYKe02s`
- Chat ID: `-5277218158`
- Server酱: `SCT353028TEFdxCoH9ZCauuBaDj1R7DBM8`
- Proxy: `socks5h://127.0.0.1:1080` (Vultr SOCKS5 隧道，用于翻墙推送)

## Server Deployment

| 服务器 | IP | 用途 |
|--------|----|------|
| 阿里云 | 47.113.118.5 (root) | 选股程序运行路径 `/root/midline_strategy/` |
| Vultr | 45.77.96.229 (root) | Telegram 代理隧道 + YouTube Studio 项目 |

阿里云内网: 172.18.240.161, WireGuard: 10.66.66.1/24
Crontab: 10 15/30 15 * 1-5

## Run

```bash
# midline_strategy 子系统
cd midline_strategy
python pipeline.py                          # 启动定时任务
python -c "from data_fetcher import refresh_trading_pool; refresh_trading_pool()"  # 手动刷新交易池

# quant_system 子系统
cd quant_system
python pipeline.py                          # 运行完整流水线
python train.py                             # 训练 LightGBM 模型

# youtube-studio 子系统
cd youtube-studio
python pipeline.py "视频主题"                # 运行完整视频制作流水线
python pipeline.py "AI 工具" --style 教程 --duration 8  # 指定风格和时长
python script_gen.py                        # 单独生成脚本
python thumbnail_gen.py                     # 单独生成缩略图
```

## Memory System

跨对话记忆存储在 `C:\Users\HLC\.claude\projects\D--first-CC\memory\`：
- `MEMORY.md` — 索引文件，每次对话自动加载
- `strategy-workflow.md` — 策略完整流程和服务器配置
- `backtest.md` — 回测系统设计

## Context Window Tips

- 对话变长后会自动压缩，压缩后无法恢复被压缩的细节
- 重要信息使用 `claude.md`（本项目文件）存储，每次对话自动加载
- `/compact` 可手动整理上下文释放空间
- 完成一个独立任务后建议开新对话，避免上下文污染
