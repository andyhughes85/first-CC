---
name: feature-pipeline
description: 特征工程管道
---

## feature_pipeline.py

统一管理所有技术指标计算，使用 registry 模式注册。

### 注册函数（11个）
- ma, volume_ma, atr — 基础均线/量/ATR
- momentum — 动量因子
- caisen — 蔡森三法（破底翻/假突破/W底）
- macd — MACD + 底背驰
- rsi — RSI
- bollinger — 布林带
- amplitude — N日振幅
- price_pattern — 量价形态
- lgb_features — LightGBM 40+维特征

### 统一入口
`python
from feature_pipeline import build_all_features
result = build_all_features(df, use_kama=False)
`

### 设计原则
- 保持 backtest.py 内联版本作为"朴素引擎"，feature_pipeline.py 作为"标准引擎"
- 两者独立计算，每月对比一次中间结果确保一致
- 新特征只需加一个 @register 函数，无需改多处
- 本文件导入不依赖其他模块（除 kama 为可选）

## cross_validation.py

Purged Walk-Forward 交叉验证。

- n_train=504, n_test=126, n_purge=60
- 2020-2025 共生成 14 折
- 各折输出完整指标，最终输出均值±标准差
- 用于识别过拟合和评估模型泛化能力

## backtest_summary.json 新增字段
- benchmark_name, benchmark_return, benchmark_annual
- excess_return, excess_annual
- 每次回测自动计算沪深300基准
