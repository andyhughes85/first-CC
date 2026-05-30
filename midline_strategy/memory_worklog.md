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

## 2026-05-30 P0 推进记录

### 已完成

| 优先级 | 任务 | 文件 | 状态 |
|:-----:|------|:----:|:----:|
| P0-9 | Telegram 隧道修复 (阿里云->Vultr东京/月) | config.py, Vultr Dante SOCKS5 | ✅ |
| P1-9 | 基准指数可配置 | config.py (BENCHMARK_CODE), backtest.py | ✅ |
| P1-10 | 清理 Continue 冗余配置 | C:\Users\HLC\.continue (删config.ts/yaml) | ✅ |
| P2-9 | 清理旧隧道脚本 | customer-service-bot (删start_tunnel/tunnel_runner/run_tunnel/socks5_proxy) | ✅ |
| P2-10 | 清理废弃 start_ui.bat | Streamlit看板待P3重写 | ✅ |
| **P3-4** | **特征重要性分析 (提前完成)** | **feature_importance.py + experiments/ 3模型分析** | ✅ |

### 特征重要性核心发现

| 特征 | lgb_meta_triple | lgb_midline | lgb_meta | 结论 |
|:----|:---------------:|:-----------:|:--------:|:----|
| **atr_ratio** | 1st 52.6% | 1st 26.1% | 4th 5.5% | 三模型都靠前，核心保留特征 |
| **macd_cross** | 0.00 | 0.00 | 27.76 | **下次训练可删除** |
| **ma5_10_cross** | 0.00 | 153.20 | 60.20 | **下次训练可删除** |
| **momentum** | 66.75 | 6120.34 | 710.71 | 仅中线模型有用，保留 |

### 待推进 (P3 剩余)

- 事件驱动回测引擎（第一版）
- XGBoost vs LightGBM 对比实验
- Streamlit 监控增强 + Telegram Bot
- temporal CNN 试跑

### 关键决策 (补充)

5. Vultr 东京节点/月，Dante SOCKS5 直连，不再需要本地 SOCKS5 代理 + SSH 反向隧道架构
6. feature_pipeline.py 作为"标准引擎"尚未被 lgb_trainer.py 使用--需等下一次模型训练时切换

## 2026-05-30 P0~P2 推进记录 (续)

| 优先级 | 任务 | 文件 | 状态 |
|:-----:|------|:----:|:----:|
| P0 | lgb_trainer.py 切换至 feature_pipeline.py | lgb_trainer.py | ✅ |
| P0a | build_training_dataset 向量化 (1406只一次) | lgb_trainer.py | ✅ |
| P0b | calc_macd 补充 macd_diff/macd_dea 列 | feature_pipeline.py | ✅ |
| P1 | 特征精简 26->24 (删macd_cross/ma5_10_cross) | feature_pipeline.py, lgb_features.py | ✅ |
| P2 | 重新训练 lgb_midline | models/lgb_midline.txt | ✅ |

### 训练结果

| 指标 | 旧模型(bak) | 新模型 | 变化 |
|:----|:----------:|:------:|:----:|
| AUC | 0.612 | 0.611 | ≈持平 |
| Precision | 0.295 | 0.297 | ±0 |
| Recall | 0.571 | 0.575 | ±0 |
| 特征数 | 26 | 24 | -2(无效特征) |

**分析**: 量价特征对"未来20日收益>8%"区分度有限(AUC~0.61)，需考虑扩展特征或调整标签策略。

### 待推进

| # | 任务 |
|:-:|:----|
| P3 | 训练 lgb_meta (单一元标注, 替换 triple) |
| P4 | 模型上线替换 |
| P5 | 清理三柱法观察通道代码/过期文件 |

