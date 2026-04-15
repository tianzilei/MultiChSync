# fNIRS 转换指南

本指南介绍如何将 Shimadzu/NIRS-SPM TXT 文件转换为 SNIRF（Shared Near Infrared Spectroscopy Format）v1.1 格式，这是 fNIRS 数据的标准格式。

## 概述

MultiChSync 将 Shimadzu TXT 文件（从 NIRS-SPM 或 Shimadzu 设备导出）转换为 SNIRF v1.1 格式，具有以下特性：

- **完整的 SNIRF v1.1 合规性** - 所有必需字段正确填充
- **HDF5 压缩** - 可选的 gzip 压缩以减小文件大小
- **自动事件提取** - 从 Mark 列提取刺激事件，从 Count 列提取辅助数据
- **坐标映射** - 将源/检测器标签（T1-T8, R1-R8）映射到 3D 坐标
- **MNE-Python 兼容性** - 用于无缝 MNE 集成的可选补丁
- **BIDS 命名** - 输出文件遵循 BIDS 命名约定

## 输入格式要求

### Shimadzu TXT 文件结构
转换器期望 TXT 文件具有以下列：

| 列 | 描述 | 必需 |
|--------|-------------|----------|
| Time(min) | 时间（分钟） | 是 |
| OxyHb | 氧合血红蛋白浓度 | 是 |
| DeoxyHb | 脱氧血红蛋白浓度 | 是 |
| TotalHb | 总血红蛋白浓度 | 是 |
| Mark | 事件标记（0=无事件，1=事件） | 否 |
| Count | 辅助数据的计数器 | 否 |
| Protocol Type | 协议信息（用于标记提取） | 否 |

**注意**: 转换器自动检测列名并处理变体。

### 坐标文件
两个 CSV 文件定义源和检测器的 3D 位置：

**source_coordinates.csv**:
```csv
label,x,y,z
T1,0.0,0.0,0.0
T2,30.0,0.0,0.0
T3,60.0,0.0,0.0
T4,90.0,0.0,0.0
T5,0.0,30.0,0.0
T6,30.0,30.0,0.0
T7,60.0,30.0,0.0
T8,90.0,30.0,0.0
```

**detector_coordinates.csv**:
```csv
label,x,y,z
R1,15.0,20.0,0.0
R2,45.0,20.0,0.0
R3,75.0,20.0,0.0
R4,105.0,20.0,0.0
R5,15.0,50.0,0.0
R6,45.0,50.0,0.0
R7,75.0,50.0,0.0
R8,105.0,50.0,0.0
```

**要求**:
- 标签必须匹配源的模式 `T<number>`，检测器的 `R<number>`
- 坐标应以毫米为单位
- 数据中使用的所有源/检测器都必须定义

## 基本转换

### 命令行界面

#### 单文件转换
```bash
multichsync fnirs convert \
  --txt-path Data/raw/fnirs/sub-001_task-rest.TXT \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output Data/convert/fnirs/sub-001_task-rest.snirf
```

#### 批量转换
```bash
multichsync fnirs batch \
  --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs
```

### Python API
```python
from multichsync.fnirs import convert_fnirs_to_snirf

output_path = convert_fnirs_to_snirf(
    txt_path="Data/raw/fnirs/sub-001_task-rest.TXT",
    src_coords_csv="Data/source_coordinates.csv",
    det_coords_csv="Data/detector_coordinates.csv",
    output_path="Data/convert/fnirs/sub-001_task-rest.snirf"
)
```

## 高级选项

### HDF5 压缩
启用 gzip 压缩以减小文件大小（默认启用）：

```bash
# 禁用压缩
multichsync fnirs convert ... --no-compress

# Python API
convert_fnirs_to_snirf(..., compress=False)
```

### 刺激事件提取
转换器自动从 Mark 列创建刺激事件：

```bash
# 禁用刺激事件提取
multichsync fnirs convert ... --no-stim

# Python API
convert_fnirs_to_snirf(..., include_stim_from_mark=False)
```

### 辅助数据
Count 列可以作为辅助数据包含：

```bash
# 排除 Count 列作为辅助数据
multichsync fnirs convert ... --no-aux-count

# Python API
convert_fnirs_to_snirf(..., include_aux_count=False)
```

### 坐标系统规范
定义使用的坐标系统：

```bash
# 指定坐标系统（默认: "Other"）
multichsync fnirs convert ... --coordinate-system "Other"

# Python API
convert_fnirs_to_snirf(
    ...,
    coordinate_system="Other",
    coordinate_system_description="3D coordinates in millimeter units; exact standard template/system not declared in source export."
)
```

### MNE-Python 兼容性
可选的补丁确保与 MNE-Python 的无缝集成：

```bash
# 禁用 MNE 补丁（默认启用）
multichsync fnirs convert ... --no-mne-patch

# Python API
convert_fnirs_to_snirf(..., patch_for_mne=False)
```

## 输出格式

### SNIRF 文件结构
转换后的 SNIRF 文件包含：

```
/{subject}/
    /nirs1/
        data: [N_channels x N_samples]HbO/HbR data
        time: [N_samples] time vector
        stimulus: Cond1, Cond2, ... (if --stim enabled)
        auxiliary: Count data (if --aux-count enabled)
        /probe/
            sourcePos3D: [N_sources x 3] source coordinates
            detectorPos3D: [N_detectors x 3] detector coordinates
            landmarkPos3D: landmark positions
            /wavelengths/
            /sourceLabels/
            /detectorLabels/
        /meta/
            # BIDS and custom metadata
```

### BIDS 命名约定
输出文件遵循 BIDS 命名约定：
```
sub-<label>_task-<name>[_acq-<label>][_run-<index>].snirf
```

## 故障排除

### 常见问题

**列名不匹配**
- 检查 TXT 文件的列名是否与预期匹配
- 转换器会自动检测常见的列名变体
- 如有自定义列名，可能需要手动处理

**坐标标签未找到**
- 确保坐标 CSV 文件包含数据中使用的所有标签
- 检查标签格式（应为 T1-T8 和 R1-R8）

**MNE 读取错误**
- 尝试使用 `--no-mne-patch` 禁用 MNE 补丁
- 检查 MNE 版本是否兼容

### 验证输出
```bash
# 使用 Python 验证 SNIRF 文件
import h5py
import numpy as np

with h5py.File('output.snirf', 'r') as f:
    print("Data shape:", f['/sub1/nirs1/data'].shape)
    print("Time points:", f['/sub1/nirs1/time'].shape)
    print("Stimuli:", list(f['/sub1/nirs1/stimulus'].keys()))
```

## 相关文档

- [安装指南](installation.md) - 安装和依赖
- [快速开始](quickstart.md) - 端到端工作流程
- [EEG 转换指南](../en/guides/eeg_conversion.md) - EEG 转换（英文）
- [ECG 转换指南](../en/guides/ecg_conversion.md) - ECG 转换（英文）
- [English fNIRS Conversion Guide](../en/guides/fnirs_conversion.md) - English version