---
name: worklog
description: 工作进度记录
---

## 2026-05-29 P0~P2 推进记录

### 已完成

| 优先级 | 任务 | 文件 | 状态 |
|:-----:|------|:----:|:----:|
| P0-1 | 回测与线上信号不一致 | backtest.py, signal_engine.py | ✅ |
| P0-2 | 虚拟盘紧急止损 | paper_trader.py | ✅ |
| P0-3 | 基准对比框架 | backtest.py (自动算沪深300) | ✅ |
| P1-4 | 特征工程独立模块 | feature_pipeline.py (11函数 registry) | ✅ |
| P1-5 | Purged Walk-Forward CV | cross_validation.py (14折) | ✅ |
| P2-6 | DuckDB 迁移 | data_fetcher.py (双后端自动切换) | ✅ |
| P2-7 | 实验标准化输出 | experiment_logger.py (自动归档+图表) | ✅ |
| P2-8 | 三柱法模型观察 | pipeline.py (并行评分,不下单) | ✅ |

### 待推进 (P3)

- 事件驱动回测引擎（第一版）
- XGBoost vs LightGBM 对比实验
- Streamlit 监控增强 + Telegram Bot
- 特征重要性分析（去除噪声特征）
- temporal CNN 试跑

### 关键决策

1. backtest.py 保留内联特征计算作为"朴素引擎"，feature_pipeline.py 作为"标准引擎"，两者独立验证
2. DuckDB 不替换 SQLite，作为加速缓存层（查询走 DuckDB，写入走 SQLite）
3. 三柱法模型仅观察，不下单，收集一周数据后再做对比决策
4. 实验目录放入 git，图表文件 gitignore（仅记录元数据）
