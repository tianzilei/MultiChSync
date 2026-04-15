# 质量评估指南

## 概述

MultiChSync 质量评估模块提供 SNIRF 文件的 fNIRS 数据质量自动评估。它实现了基于血红蛋白信号(HbO 和 HbR)既定指标的综合信号级质量评估框架。

核心目的: 自动检测坏通道,计算信号质量指标,并将质量元数据嵌入 SNIRF 文件以实现可重现的质量控制。

主要功能:
- 综合指标: 每个通道 14+ 个信号级质量指标
- 双重评估: 滤波前和滤波后质量评估
- 范式特定指标: 基于任务的 CNR 和静息态可靠性
- 元数据嵌入: 将质量评分和坏通道列表直接写入 SNIRF 文件
- 批量处理: 自动错误处理处理整个文件夹
- 灵活滤波: 带可选 TDDR 运动伪影校正的带通滤波

## 质量评估框架

### 信号级指标

基于 fnirs_signal_level_qc_metrics.md 中的综合规范,质量模块为每个 HbO 和 HbR 通道计算以下指标:

#### 1. 基本信号指标

| 指标 | 公式 | 描述 |
|--------|---------|-------------|
| Near-Flatline | 1 if max(abs(diff(x))) < tau_flat | 检测平坦或死通道 |
| Range | max(x) - min(x) | 信号幅度范围 |
| 变异系数 | sigma(x) / (|mu(x)| + epsilon_mu) | 归一化变异性 |
| tSNR | |mu(x)| / (sigma(x) + epsilon_sigma) | 时间信噪比 |
| 鲁棒导数指数 | median(|dx|) / (MAD(x) + epsilon_MAD) | 相对于基线变异性的信号变化 |
| 基线漂移 | |slope| / (sigma(x) + epsilon_sigma) | 相对于信号变异性的线性漂移 |
| 谱熵 | -Sigma(P(f) log P(f)) / log(N) | 频率分布均匀性 |

#### 2. 生理频带功率比

| 频带 | 频率范围 | 目的 |
|------|----------------|---------|
| 低频 | 0.01-0.08 Hz | Mayer 波和血管舒缩 |
| Mayer 带 | 0.08-0.15 Hz | Mayer 波(约 0.1 Hz) |
| 呼吸带 | 0.15-0.40 Hz | 呼吸相关振荡 |

指标:
- Mayer 比: P_mayer / (P_low + epsilon)
- 呼吸比: P_resp / (P_low + epsilon)

#### 3. HbO-HbR 对指标

| 指标 | 描述 | 预期范围 |
|--------|-------------|----------------|
| 相关性 | HbO 和 HbR 之间的 Pearson 相关 | 负值(典型: -0.3 到 -0.8) |
| 方差比 | sigma(HbO) / (sigma(HbR) + epsilon) | 约 2-4(HbO 通常更可变) |
| 导数相关性 | 一阶差分的相关性 | 负值 |

#### 4. 范式特定指标

任务范式:
- CNR(对比度噪声比): |mu_baseline - mu_response| / sqrt(sigma2_baseline + sigma2_response)
- 良好事件比例: 通过质量检查的事件百分比

静息态范式:
- 分半可靠性: 时间半部分之间功能连接矩阵的相关性
- 保留时长比例: 坏段移除后可用的数据

### 质量评分系统

每个指标使用锚点映射到质量评分(0-1):

| 质量等级 | 评分范围 | 描述 |
|--------------|-------------|-------------|
| 优秀 | 0.8-1.0 | 高质量信号,最小伪影 |
| 良好 | 0.6-0.8 | 可接受的分析质量 |
| 一般 | 0.4-0.6 | 中等伪影,谨慎使用 |
| 较差 | 0.0-0.4 | 严重伪影,考虑排除 |

硬阈值规则: 低于最低阈值的通道自动标记为坏:
- 近平坦线检测
- 极低 tSNR(< 1.0)
- 过度基线漂移
- 异常 HbO-HbR 相关性(> 0 或 < -0.95)

## 命令行用法

### 1. 单文件质量评估

```bash
# 使用默认参数评估
multichsync quality assess \
  --input Data/convert/fnirs/sub-001.snirf \
  --output-dir Data/quality

# 使用自定义参数
multichsync quality assess \
  --input Data/convert/fnirs/sub-001.snirf \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2 \
  --paradigm task \
  --resample-sfreq 4.0

# 启用 TDDR 运动伪影校正
multichsync quality assess \
  --input Data/convert/fnirs/sub-001.snirf \
  --output-dir Data/quality \
  --tddr

# 嵌入质量元数据到 SNIRF 文件
multichsync quality assess \
  --input Data/convert/fnirs/sub-001.snirf \
  --output-dir Data/quality \
  --embed-metadata
```

选项:
- --input: 输入 SNIRF 文件路径(必需)
- --output-dir: 输出目录(必需)
- --l-freq: 带通滤波低频截止(默认: 0.01 Hz)
- --h-freq: 带通滤波高频截止(默认: 0.2 Hz)
- --paradigm: 范式类型(task 或 rest,默认: task)
- --resample-sfreq: 重采样频率(Hz,默认: 不重采样)
- --tddr: 启用 TDDR 运动伪影校正(默认: 禁用)
- --embed-metadata: 将质量评分嵌入 SNIRF 文件(默认: 禁用)
- --verbose: 显示详细输出

### 2. 批量质量评估

```bash
# 批量评估目录中的所有 SNIRF 文件
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality

# 使用自定义滤波参数
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.5

# 跳过已有结果的文件
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --skip-existing

# 限制并发进程数
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --max-workers 4
```

选项:
- --input-dir: 包含 SNIRF 文件的输入目录(必需)
- --output-dir: 评估结果的输出目录(必需)
- --l-freq: 带通滤波低频截止(默认: 0.01 Hz)
- --h-freq: 带通滤波高频截止(默认: 0.2 Hz)
- --paradigm: 范式类型(task 或 rest)
- --skip-existing: 跳过已有评估结果的文件
- --max-workers: 最大并发进程数(默认: 4)
- --verbose: 显示详细输出

### 3. 质量报告解读

质量评估模块生成以下输出文件:

#### 3.1 通道级别详细指标

滤波前质量指标(*_prefilter_detail.csv):
```csv
channel,flatline,range,cv,tsnr,derivative_idx,baseline_drift,spectral_entropy
HbO_S1-D1,0,25.3,0.12,8.2,0.45,0.08,0.92
HbR_S1-D1,0,18.7,0.15,6.8,0.52,0.11,0.89
```

滤波后质量指标(*_postfilter_detail.csv):
```csv
channel,flatline,range,cv,tsnr,derivative_idx,baseline_drift,spectral_entropy,mayer_ratio,resp_ratio
HbO_S1-D1,0,22.1,0.10,9.5,0.38,0.05,0.88,0.42,0.28
HbR_S1-D1,0,16.3,0.12,7.9,0.45,0.07,0.85,0.38,0.31
```

#### 3.2 汇总统计

总体质量评分(*_summary.csv):
```csv
channel,overall_score,quality_grade,is_bad_channel,reason
HbO_S1-D1,0.82,Good,False,
HbR_S1-D1,0.75,Good,False,
HbO_S2-D2,0.35,Poor,True,low_tsnr
```

坏通道列表(*_bad_channels.txt):
```
Bad channels (3):
- HbO_S2-D2 (low_tsnr)
- HbR_S3-D3 (flatline)
- HbO_S4-D4 (high_baseline_drift)
```

#### 3.3 可视化

通道质量热图(*_channel_quality_heatmap.png):
- 展示所有通道的总体质量评分
- 使用颜色编码: 绿色(好) -> 黄色(一般) -> 红色(差)

信噪比分布(*_snr_distribution.png):
- 显示 tSNR 值的直方图分布
- 标注阈值线

HbO-HbR 相关性图(*_hbr_hbo_correlation.png):
- HbO vs HbR 散点图
- 显示相关系数和回归线

## Python API 用法

### 导入模块

```python
from multichsync.quality import (
    assess_quality,
    batch_assess_quality,
    compute_signal_metrics,
    compute_paradigm_metrics,
    generate_quality_report,
    embed_quality_metadata
)
```

### 单文件评估示例

```python
from multichsync.quality import assess_quality

result = assess_quality(
    input_path="Data/convert/fnirs/sub-001.snirf",
    output_dir="Data/quality",
    l_freq=0.01,
    h_freq=0.2,
    paradigm="task",
    embed_metadata=True
)

print(f"总体评分: {result['overall_score']}")
print(f"坏通道: {result['bad_channels']}")
print(f"详细指标: {result['detailed_metrics']}")
```

### 批量评估示例

```python
from multichsync.quality import batch_assess_quality

results = batch_assess_quality(
    input_dir="Data/convert/fnirs",
    output_dir="Data/quality",
    l_freq=0.01,
    h_freq=0.2,
    max_workers=4,
    skip_existing=True
)

total_files = len(results)
bad_channels_count = sum(1 for r in results if r['bad_channels'])
print(f"包含坏通道的文件: {bad_channels_count}/{total_files}")
```

### 指标计算示例

```python
from multichsync.quality import compute_signal_metrics
import numpy as np

x = np.random.randn(1000)

metrics = compute_signal_metrics(
    signal=x,
    sample_rate=10.0
)

print(f"tSNR: {metrics['tsnr']:.2f}")
print(f"变异系数: {metrics['cv']:.3f}")
print(f"基线漂移: {metrics['baseline_drift']:.3f}")
```

## 质量评分详解

### 评分计算方法

每个指标的评分使用锚点映射:

```python
def map_to_score(value, thresholds):
    if value <= thresholds['poor']:
        return value / thresholds['poor'] * 0.4
    elif value <= thresholds['fair']:
        return 0.4 + (value - thresholds['poor']) / (thresholds['fair'] - thresholds['poor']) * 0.2
    elif value <= thresholds['good']:
        return 0.6 + (value - thresholds['fair']) / (thresholds['good'] - thresholds['fair']) * 0.2
    else:
        return 0.8 + min(0.2, (value - thresholds['good']) / thresholds['good'] * 0.2)
```

### 总体评分计算

总体质量评分是各指标评分的加权平均:

```python
weights = {
    'tsnr': 0.20,
    'cv': 0.15,
    'baseline_drift': 0.15,
    'spectral_entropy': 0.10,
    'mayer_ratio': 0.10,
    'resp_ratio': 0.10,
    'hbo_hbr_corr': 0.15,
    'derivative_corr': 0.05
}

overall_score = sum(weights[k] * metrics[k] for k in weights)
```

### 坏通道判定规则

硬阈值规则(自动标记为坏):
- flatline == 1: 近平坦线信号
- tsnr < 1.0: 极低信噪比
- baseline_drift > 0.5: 过度基线漂移
- hbo_hbr_corr > 0: 正相关(生理上异常)
- hbo_hbr_corr < -0.95: 极强负相关

软阈值规则(基于总体评分):
- overall_score < 0.4: 标记为坏

## 故障排除

### 常见问题

SNIRF 文件无法读取:
- 验证文件格式是否符合 SNIRF v1.1 规范
- 检查 HDF5 文件结构是否完整
- 尝试使用 h5py 直接验证

内存不足:
- 减少 --max-workers 数量
- 使用 --resample-sfreq 4.0 降低采样率
- 批量处理改为逐个文件处理

TDDR 校正失败:
- 确保信号长度足够(至少 30 秒)
- 检查是否存在极端运动伪影
- 尝试禁用 TDDR 使用默认滤波

质量评分异常:
- 检查采样率设置是否正确
- 验证 HbO 和 HbR 通道配对是否正确
- 查看详细指标文件定位问题

### 验证评估结果

```python
import pandas as pd

summary = pd.read_csv("Data/quality/sub-001_summary.csv")
print(f"好通道数: {(~summary['is_bad_channel']).sum()}")
print(f"坏通道数: {summary['is_bad_channel'].sum()}")

bad_channels = summary[summary['is_bad_channel']]
print(bad_channels[['channel', 'reason']])

detail = pd.read_csv("Data/quality/sub-001_postfilter_detail.csv")
print(f"\ntSNR 统计:")
print(detail['tsnr'].describe())
```

## 相关文档

- 快速开始(quickstart.md) - 端到端工作流程
- fNIRS 转换指南(fnirs_conversion.md) - fNIRS 数据转换
- 质量指标规范(../../en/technical/fnirs_signal_level_qc_metrics.md) - 详细质量指标定义(英文)
- English Quality Assessment Guide(../en/guides/quality_assessment.md) - English version