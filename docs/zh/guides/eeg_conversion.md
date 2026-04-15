# EEG 转换指南

## 概述

EEG 转换模块支持在不同格式之间转换 EEG 数据文件。它利用 MNE-Python 读取 EEG 文件，并提供导出到神经影像研究中常用的标准 EEG 格式。

**主要功能:**
- 支持 Curry 和 EEGLAB 格式读取 EEG 文件
- 导出到 BrainVision、EEGLAB 或 EDF 格式
- 批量处理多个文件
- 与 MultiChSync 工作流程集成

## 支持的格式

### 输入格式
- **EEGLAB**: `.set` 文件（可选 `.fdt` 数据文件）
- **Curry**: 多种文件扩展名，包括 `.cdt`、`.dap`、`.dat`、`.rs3`、`.cef`、`.cdt.dpa`

### 输出格式
- **BrainVision**: 行业标准格式，包含单独的 `.vhdr`、`.vmrk` 和 `.eeg` 文件
- **EEGLAB**: MATLAB 兼容的 `.set` 文件
- **EDF**: 欧洲数据格式，一种广泛支持的生物医学信号格式

## 命令行用法

### 单文件转换

```bash
# 转换为 BrainVision 格式（默认）
multichsync eeg convert \
  --file-path data.set \
  --format BrainVision \
  --output ./converted

# 转换为 EEGLAB 格式
multichsync eeg convert \
  --file-path data.cdt \
  --format EEGLAB \
  --output ./converted

# 转换为 EDF 格式
multichsync eeg convert \
  --file-path data.set \
  --format EDF \
  --output ./converted
```

**选项:**
- `--file-path`: 输入 EEG 文件路径（必需）
- `--format`: 输出格式：`BrainVision`（默认）、`EEGLAB` 或 `EDF`
- `--output`: 输出目录或文件路径（可选，默认为 `convert/` 子目录）
- `--preload`: 将数据预加载到内存（默认: `False`）
- `--overwrite`: 覆盖现有文件（默认: `False`）
- `--verbose`: 显示详细输出（默认: 遵循全局详细设置）

### 批量转换

```bash
# 将目录中的所有 EEG 文件转换为 BrainVision 格式
multichsync eeg batch \
  --input-dir ./raw_eeg \
  --format BrainVision \
  --output-dir ./converted/eeg

# 使用递归目录搜索转换
multichsync eeg batch \
  --input-dir ./raw_eeg \
  --format BrainVision \
  --output-dir ./converted/eeg \
  --recursive

# 转换为 EEGLAB 格式并预加载
multichsync eeg batch \
  --input-dir ./raw_eeg \
  --format EEGLAB \
  --output-dir ./converted/eeg \
  --preload
```

**选项:**
- `--input-dir`: 包含 EEG 文件的输入目录（必需）
- `--format`: 输出格式：`BrainVision`（默认）、`EEGLAB` 或 `EDF`
- `--output-dir`: 转换后文件的输出目录（必需）
- `--recursive`: 在子目录中递归搜索文件（默认: `False`）
- `--preload`: 将数据预加载到内存（默认: `False`）
- `--overwrite`: 覆盖现有文件（默认: `False`）
- `--verbose`: 显示详细输出（默认: 遵循全局详细设置）

## Python API 用法

### 导入模块

```python
from multichsync.eeg import (
    convert_eeg_format,
    convert_eeg_to_brainvision,
    convert_eeg_to_eeglab,
    convert_eeg_to_edf,
    batch_convert_eeg_format,
    batch_convert_eeg_to_brainvision,
    batch_convert_eeg_to_eeglab,
    batch_convert_eeg_to_edf,
    parse_eeg_header,
    get_channel_info
)
```

### 单文件转换示例

```python
# 转换为 BrainVision 格式
output_path = convert_eeg_to_brainvision(
    file_path="data.set",
    output_dir="./converted",
    overwrite=False
)

# 转换为 EEGLAB 格式
output_path = convert_eeg_to_eeglab(
    file_path="data.cdt",
    output_dir="./converted",
    overwrite=False
)

# 转换为 EDF 格式
output_path = convert_eeg_to_edf(
    file_path="data.set",
    output_dir="./converted",
    overwrite=False
)
```

### 批量转换示例

```python
# 批量转换为 BrainVision 格式
results = batch_convert_eeg_to_brainvision(
    input_dir="./raw_eeg",
    output_dir="./converted/eeg",
    recursive=True,
    overwrite=False
)

# 批量转换为 EEGLAB 格式
results = batch_convert_eeg_to_eeglab(
    input_dir="./raw_eeg",
    output_dir="./converted/eeg",
    recursive=True,
    preload=True,
    overwrite=False
)
```

## 获取通道信息

### 获取通道信息

```python
from multichsync.eeg import get_channel_info

# 获取通道信息
channels = get_channel_info("data.set")
print(channels)
# 输出示例:
# [{'name': 'Fp1', 'type': 'EEG', 'unit': 'µV'},
#  {'name': 'Fp2', 'type': 'EEG', 'unit': 'µV'},
#  ...]
```

## 故障排除

### 常见问题

**MNE 无法读取文件**
- 确保已安装适当的 MNE 格式支持
- 检查文件是否损坏
- 验证文件扩展名是否被支持

**内存问题**
- 对于大型文件，使用 `--preload False`（默认）以流式处理
- 增加可用系统内存

**格式转换错误**
- 验证目标格式是否支持所有通道类型
- 检查采样率是否兼容

### 验证输出

```python
import mne

# 使用 MNE 读取转换后的文件
raw = mne.io.read_raw_brainvision(
    "./converted/eeg/subject1.vhdr",
    preload=True
)

print(f"通道数: {len(raw.ch_names)}")
print(f"采样率: {raw.info['sfreq']} Hz")
print(f"持续时间: {raw.times[-1]:.2f} 秒")
```

## 相关文档

- [安装指南](installation.md) - 安装和依赖
- [快速开始](quickstart.md) - 端到端工作流程
- [fNIRS 转换指南](fnirs_conversion.md) - fNIRS 转换
- [ECG 转换指南](ecg_conversion.md) - ECG 转换
- [标记处理指南 (英文)](../en/guides/marker_processing.md) - EEG 标记提取
- [English EEG Conversion Guide](../en/guides/eeg_conversion.md) - English version