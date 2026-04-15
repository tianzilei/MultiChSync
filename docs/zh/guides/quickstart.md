# 快速开始指南

本指南将帮助您在几分钟内开始使用 MultiChSync。我们将介绍从数据转换到标记同步的完整工作流程。

## 概述

MultiChSync 通过三个主要阶段处理多模态神经影像数据：

1. **数据转换**: 将原始数据转换为标准格式
2. **标记处理**: 提取、清理和同步事件标记
3. **质量评估**: 评估 fNIRS 信号质量

## 步骤 1: 准备数据

### 推荐的目录结构
```
Data/
├── raw/
│   ├── fnirs/          # Shimadzu .TXT 或 .csv 文件
│   ├── EEG/           # Curry .set 或 EEGLAB .set 文件
│   └── ECG/           # Biopac .acq 文件
├── convert/           # 转换后的数据（自动创建）
├── marker/           # 提取的标记（自动创建）
└── quality/          # 质量报告（自动创建）
```

### 所需坐标文件（用于 fNIRS）
将这些文件放在 `Data/` 目录中：
- `source_coordinates.csv` - fNIRS 源的 3D 位置（T1-T8 标签）
- `detector_coordinates.csv` - fNIRS 检测器的 3D 位置（R1-R8 标签）

坐标文件格式示例：
```csv
label,x,y,z
T1,0.0,0.0,0.0
T2,30.0,0.0,0.0
...
R1,15.0,20.0,0.0
R2,45.0,20.0,0.0
...
```

## 步骤 2: 转换数据

### 转换 fNIRS 数据
```bash
# 单文件转换
multichsync fnirs convert \
  --txt-path Data/raw/fnirs/sample.TXT \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output Data/convert/fnirs/sample.snirf

# 批量转换（推荐）
multichsync fnirs batch \
  --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs
```

### 转换 EEG 数据
```bash
# 批量转换 EEG 文件为 BrainVision 格式
multichsync eeg batch \
  --input-dir Data/raw/EEG \
  --format BrainVision \
  --output-dir Data/convert/EEG \
  --recursive
```

### 转换 ECG 数据
```bash
# 批量转换 ECG 文件
multichsync ecg batch \
  --input-dir Data/raw/ECG \
  --output-dir Data/convert/ECG
```

## 步骤 3: 提取事件标记

### 从所有模态提取标记
```bash
# 提取所有标记类型
multichsync marker batch --types fnirs,ecg,eeg

# 或使用 Python 脚本获得更多控制
python extract_all_markers.py --max-files 5  # 使用前 5 个文件测试
```

**功能说明:**
- **fNIRS 标记**: 从 `Data/raw/fnirs/*.csv` 提取 → `Data/marker/fnirs/`
- **ECG 标记**: 从 `Data/convert/ecg/*input.csv` 提取 → `Data/marker/ecg/`
- **EEG 标记**: 从 `Data/convert/eeg/**/*.vmrk` 提取 → `Data/marker/eeg/`

### 清理提取的标记
```bash
# 清理所有标记文件
multichsync marker clean \
  --input Data/marker \
  --inplace \
  --min-rows 2 \
  --min-interval 1.0
```

## 步骤 4: 生成标记报告

### 创建受试者级别报告
```bash
multichsync marker info \
  --input-dir Data/marker \
  --output-dir Data/marker/info
```

这将创建：
- `subject_XXX_marker_report.csv` - 每个受试者的标记统计
- `report_errors.csv` - 处理失败的文件

## 步骤 5: 跨设备同步标记

### 匹配多个设备的标记
```bash
# 匹配特定文件
multichsync marker match \
  --input-files \
    Data/marker/fnirs/20251101060_1_marker.csv \
    Data/marker/ecg/20251101060part1_marker.csv \
    Data/marker/eeg/WJTB_060_SEG_01_marker.csv \
  --device-names fnirs ecg eeg \
  --output-dir Data/matching \
  --max-time-diff 2.0
```

### 替代方案：匹配目录中的所有文件
```bash
# 匹配所有 BIDS 格式的标记文件
multichsync marker match \
  --input-dir Data/marker \
  --output-dir Data/matching \
  --max-time-diff 5.0
```

**输出文件:**
- `matched_timeline.csv` - 包含设备时间的共识时间线
- `matched_metadata.json` - 匹配参数和统计
- `matched_timeline_alignment.png` - 对齐时间线的可视化
- `matched_confidence_distribution.png` - 置信度分数分布

## 步骤 6: 使用对齐的时间线裁剪数据

### 根据匹配结果裁剪原始数据文件
```bash
# 使用对齐时间线裁剪 fNIRS 数据
multichsync crop \
  --input-dir Data/convert/fnirs \
  --timeline Data/matching/matched_timeline.csv \
  --output-dir Data/cropped/fnirs

# 裁剪 EEG 数据
multichsync crop \
  --input-dir Data/convert/eeg \
  --timeline Data/matching/matched_timeline.csv \
  --output-dir Data/cropped/eeg
```

### 批量裁剪（一次性处理所有模态）
```bash
# 使用对齐时间线裁剪所有已转换的数据
multichsync crop batch \
  --convert-dir Data/convert \
  --timeline Data/matching/matched_timeline.csv \
  --output-dir Data/cropped
```

## 步骤 7: 质量评估（fNIRS）

### 评估 fNIRS 数据质量
```bash
# 批量评估 fNIRS 数据质量
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2

# 使用自定义参数评估
multichsync quality assess \
  --input Data/convert/fnirs/sub-001.snirf \
  --output-dir Data/quality \
  --paradigm task \
  --l-freq 0.01 \
  --h-freq 0.5 \
  --resample-sfreq 4.0
```

### 解释质量报告

质量评估模块生成以下文件：

1. **通道级别详细指标**:
   - `*_prefilter_detail.csv` - 滤波前的质量指标
   - `*_postfilter_detail.csv` - 滤波后的质量指标

2. **汇总统计**:
   - `*_summary.csv` - 每个通道的总体质量评分
   - `*_bad_channels.txt` - 标记为坏通道的列表

3. **可视化**:
   - `*_channel_quality_heatmap.png` - 通道质量热图
   - `*_snr_distribution.png` - 信噪比分布

**质量评分范围**:
- 0.8-1.0: 优秀（Excellent）
- 0.6-0.8: 良好（Good）
- 0.4-0.6: 一般（Fair）
- 0.0-0.4: 较差（Poor）

## 完整工作流程示例

### 1. 准备数据目录
```bash
mkdir -p Data/raw/{fnirs,EEG,ECG}
mkdir -p Data/convert/{fnirs,EEG,ECG}
mkdir -p Data/{marker,quality,matching}
```

### 2. 放置原始数据
- 将 Shimadzu TXT 文件复制到 `Data/raw/fnirs/`
- 将 Curry/EEGLAB 文件复制到 `Data/raw/EEG/`
- 将 Biopac ACQ 文件复制到 `Data/raw/ECG/`

### 3. 运行完整转换流程
```bash
# 转换所有数据
multichsync fnirs batch --input-dir Data/raw/fnirs --src-coords Data/source_coordinates.csv --det-coords Data/detector_coordinates.csv --output-dir Data/convert/fnirs
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --output-dir Data/convert/EEG
multichsync ecg batch --input-dir Data/raw/ECG --output-dir Data/convert/ECG

# 提取和处理标记
multichsync marker batch --types fnirs,ecg,eeg
multichsync marker clean --input Data/marker --inplace
multichsync marker match --input-dir Data/marker --output-dir Data/matching --max-time-diff 2.0

# 质量评估
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality
```

## 下一步

- 查看[安装指南](installation.md)了解详细安装说明
- 查看[fNIRS 转换指南](fnirs_conversion.md)了解更多 fNIRS 转换选项
- 查看[EEG 转换指南](../en/guides/eeg_conversion.md)了解更多 EEG 转换选项（英文）
- 查看[ECG 转换指南](../en/guides/ecg_conversion.md)了解更多 ECG 转换选项（英文）
- 查看[标记处理指南](../en/guides/marker_processing.md)了解更多高级标记处理（英文）
- 查看[质量评估指南](../en/guides/quality_assessment.md)了解更多质量评估选项（英文）
- [English Quick Start](../en/guides/quickstart.md) - English version