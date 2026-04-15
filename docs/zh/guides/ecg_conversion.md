# ECG 转换指南

## 概述

ECG 转换模块支持将 Biopac ACQ 文件转换为 CSV 格式。它提供灵活的输出选项，包括按通道类型分组的 CSV 文件，并支持两个后端库（bioread 和 neurokit2）用于读取 ACQ 文件。

**主要功能:**
- 使用 bioread 或 neurokit2 后端读取 Biopac ACQ 文件
- 导出为 CSV 格式，可选择按通道类型分组
- 批量处理多个 ACQ 文件
- 重采样到指定采样率
- 与 MultiChSync 工作流程集成以进行标记提取

## 支持的格式

### 输入格式
- **Biopac ACQ**: 来自 Biopac 数据采集系统的 `.acq` 文件

### 输出格式
- **CSV**: 带灵活分组选项的逗号分隔值格式

## 命令行用法

### 单文件转换

```bash
# 使用默认设置（按通道类型分组）将 ACQ 转换为 CSV
multichsync ecg convert \
  --acq data.acq \
  --output ./converted

# 使用自定义采样率转换
multichsync ecg convert \
  --acq data.acq \
  --output ./converted \
  --sampling-rate 500

# 转换为单个 CSV 文件（不分组）
multichsync ecg convert \
  --acq data.acq \
  --output ./converted/single.csv \
  --no-group

# 指定 CSV 输出的浮点格式
multichsync ecg convert \
  --acq data.acq \
  --output ./converted \
  --float-format "%.8f"
```

**选项:**
- `--acq`: 输入 ACQ 文件路径（必需）
- `--output`: 输出文件路径或目录（可选，默认为 `convert/` 子目录）
- `--sampling-rate`: 目标采样率，单位 Hz（可选，默认: 250）
- `--no-group`: 输出单个 CSV 文件而不是按通道类型分组（默认: 分组）
- `--float-format`: CSV 输出的浮点格式字符串（默认: `"%.6f"`）
- `--format`: 输出格式（目前仅支持 `csv`）

### 批量转换

```bash
# 转换目录中的所有 ACQ 文件
multichsync ecg batch \
  --input-dir ./raw_ecg \
  --output-dir ./converted/ecg

# 使用自定义采样率转换
multichsync ecg batch \
  --input-dir ./raw_ecg \
  --output-dir ./converted/ecg \
  --sampling-rate 500

# 转换为单个 CSV 文件（不分组）
multichsync ecg batch \
  --input-dir ./raw_ecg \
  --output-dir ./converted/ecg \
  --no-group
```

**选项:**
- `--input-dir`: 包含 ACQ 文件的输入目录（必需）
- `--output-dir`: 转换后文件的输出目录（必需）
- `--sampling-rate`: 目标采样率，单位 Hz（可选，默认: 250）
- `--no-group`: 输出单个 CSV 文件而不是按通道类型分组（默认: 分组）
- `--float-format`: CSV 输出的浮点格式字符串（默认: `"%.6f"`）
- `--format`: 输出格式（目前仅支持 `csv`）

## Python API 用法

### 导入模块

```python
from multichsync.ecg import (
    convert_acq_to_csv,
    batch_convert_acq_to_csv,
    parse_acq_file,
    get_channel_info
)
```

### 单文件转换示例

```bash
# 转换为 CSV（默认分组）
output_path = convert_acq_to_csv(
    acq_path="data.acq",
    output_dir="./converted"
)

# 转换为单个 CSV 文件
output_path = convert_acq_to_csv(
    acq_path="data.acq",
    output_path="./converted/single.csv",
    group_by_type=False
)

# 使用自定义采样率
output_path = convert_acq_to_csv(
    acq_path="data.acq",
    output_dir="./converted",
    sampling_rate=500
)
```

### 批量转换示例

```python
# 批量转换所有 ACQ 文件
results = batch_convert_acq_to_csv(
    input_dir="./raw_ecg",
    output_dir="./converted/ecg"
)

# 使用自定义设置批量转换
results = batch_convert_acq_to_csv(
    input_dir="./raw_ecg",
    output_dir="./converted/ecg",
    sampling_rate=500,
    group_by_type=False,
    float_format="%.8f"
)
```

### 获取通道信息

```python
from multichsync.ecg import get_channel_info

# 获取通道信息
channels = get_channel_info("data.acq")
print(channels)
# 输出示例:
# [{'name': 'ECG', 'type': 'ECG', 'unit': 'mV'},
#  {'name': 'Resp', 'type': 'Respiration', 'unit': 'V'},
#  ...]
```

## 输出格式

### 分组输出（默认）
当使用分组输出时，每个通道类型创建单独的 CSV 文件：

```
converted/
├── ECG/
│   ├── channel_1.csv
│   └── channel_2.csv
├── Respiration/
│   └── channel_3.csv
└── Trigger/
    └── channel_4.csv
```

### 单文件输出
使用 `--no-group` 时，所有通道数据合并到一个 CSV 文件中：

```csv
time,channel_1,channel_2,channel_3
0.000,-0.012,0.234,0.001
0.004,-0.011,0.235,0.002
...
```

## 故障排除

### 常见问题

**无法读取 ACQ 文件**
- 确保已安装 bioread 或 neurokit2
- 检查文件是否损坏或格式是否受支持

**采样率不匹配**
- 验证目标采样率是否与您的分析兼容
- 注意重采样可能导致数据失真

**通道分组问题**
- 某些通道可能无法自动识别类型
- 检查输出目录结构以确认分组

### 验证输出

```python
import pandas as pd

# 读取转换后的 CSV 文件
df = pd.read_csv("./converted/single.csv")
print(f"行数: {len(df)}")
print(f"列数: {len(df.columns)}")
print(f"采样率: {1/(df['time'].iloc[1] - df['time'].iloc[0]):.2f} Hz")
```

## 与标记处理的集成

ECG 转换与 MultiChSync 的标记处理模块无缝集成：

```bash
# 转换 ECG 文件
multichsync ecg batch --input-dir ./raw_ecg --output-dir ./converted/ecg

# 从转换后的 CSV 文件提取标记
multichsync marker extract \
  --input-file ./converted/ecg/ecg_001_input.csv \
  --output-file ./marker/ecg/ecg_001_marker.csv \
  --device-type ecg
```

## 相关文档

- [安装指南](installation.md) - 安装和依赖
- [快速开始](quickstart.md) - 端到端工作流程
- [fNIRS 转换指南](fnirs_conversion.md) - fNIRS 转换
- [EEG 转换指南](eeg_conversion.md) - EEG 转换
- [标记处理指南 (英文)](../en/guides/marker_processing.md) - ECG 标记提取
- [English ECG Conversion Guide](../en/guides/ecg_conversion.md) - English version