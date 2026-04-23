# 标记处理指南

## 概述

MultiChSync 标记处理模块提供了从 fNIRS、EEG 和 ECG 记录中提取、清理、匹配和多设备标记数据裁剪的完整管道。本指南介绍从原始数据到同步裁剪输出的完整标记工作流程。

核心目的: 同步多个记录设备(fNIRS、EEG、ECG)之间的事件标记，以实现多模态神经影像数据的时间对齐分析。

主要功能:
- 多格式提取: 从 Biopac(ECG)、BrainVision(EEG)和 Shimadzu fNIRS 格式提取标记
- 漂移校正: 估计和校正设备之间的线性时钟漂移
- 置信度评分: 所有匹配都包含基于时间邻近性的置信度评分(0-1)
- 灵活算法: Hungarian、Min-Cost Flow 和 Sinkhorn 匹配算法
- 集成裁剪: 裁剪原始数据文件到同步时间窗口
- 任务名称修改: 更新输出文件中的任务名称以实现 BIDS 兼容性

## 支持的格式

### 输入标记格式

| 格式 | 设备 | 文件扩展名 | 关键列 | 提取函数 |
|--------|--------|----------------|-------------|---------------------|
| Biopac/ECG | ECG | .csv | 单电压列(0V/5V) | extract_biopac_marker() |
| BrainVision | EEG | .vmrk(含 .vhdr) | 标记位置 + SamplingInterval | extract_brainvision_marker() |
| Shimadzu fNIRS | fNIRS | .csv | Start Time, Protocol Type | extract_fnirs_marker() |

### 输出格式

| 格式 | 描述 | 文件模式 |
|--------|-------------|--------------|
| 标记 CSV | 标准化的标记时间 | {device}_marker.csv(列: index, Time(sec)) |
| 时间线 CSV | 跨设备的共识时间线 | {prefix}_timeline.csv |
| 元数据 JSON | 匹配参数和结果 | {prefix}_metadata.json |
| 质量图 | 匹配可视化 | {prefix}_*.png |

## 命令行用法

### 1. 标记提取

从单个文件提取标记:

```bash
# 从 fNIRS CSV 提取
multichsync marker extract \
  --input-file Data/raw/fnirs/sub-001_task-rest.csv \
  --output-file Data/marker/fnirs/sub-001_task-rest_marker.csv \
  --device-type fnirs

# 从 EEG BrainVision 提取
multichsync marker extract \
  --input-file Data/raw/eeg/sub-001_task-rest.vmrk \
  --output-file Data/marker/eeg/sub-001_task-rest_marker.csv \
  --device-type eeg

# 从 ECG Biopac 提取
multichsync marker extract \
  --input-file Data/raw/ecg/sub-001_task-rest.csv \
  --output-file Data/marker/ecg/sub-001_task-rest_marker.csv \
  --device-type ecg
```

从目录批量提取:

```bash
multichsync marker batch \
  --input-dir Data/raw/fnirs \
  --output-dir Data/marker/fnirs \
  --device-type fnirs \
  --pattern "*.csv"
```

### 2. 标记清理

清理提取的标记文件(去重、排序、过滤):

```bash
# 清理单个文件
multichsync marker clean \
  --input-file Data/marker/fnirs/sub-001_task-rest_marker.csv \
  --output-file Data/marker/fnirs/sub-001_task-rest_marker_cleaned.csv \
  --min-interval 1.0 \
  --remove-start

# 清理整个目录
multichsync marker clean \
  --input-dir Data/marker/fnirs \
  --output-dir Data/marker/fnirs_cleaned \
  --min-interval 1.0 \
  --min-rows 5
```

清理操作:
- 删除标记数少于 --min-rows 的文件
- 按时间排序标记
- 删除时间 0 处的标记(如有 --remove-start)
- 删除间隔小于 --min-interval 秒的标记
- 返回状态: cleaned、deleted_empty、skipped_ok 或 error

### 3. 标记信息提取

生成受试者级别的标记统计报告:

```bash
# 生成单个标记文件的信息
multichsync marker info \
  --input-file Data/marker/fnirs/sub-001_marker.csv \
  --output-file Data/marker/info/sub-001_info.csv

# 从目录批量生成报告
multichsync marker info \
  --input-dir Data/marker \
  --output-dir Data/marker/info
```

### 4. 跨设备标记匹配

匹配来自不同设备的标记时间:

```bash
# 匹配特定文件
multichsync marker match \
  --input-files \
    Data/marker/fnirs/sub-001_marker.csv \
    Data/marker/ecg/sub-001_marker.csv \
    Data/marker/eeg/sub-001_marker.csv \
  --device-names fnirs ecg eeg \
  --output-dir Data/matching \
  --max-time-diff 2.0

# 使用特定算法(默认: hungarian)
multichsync marker match \
  --input-files ... \
  --algorithm hungarian \
  --drift-correction

# 从目录匹配所有 BIDS 文件
multichsync marker match \
  --input-dir Data/marker \
  --output-dir Data/matching \
  --max-time-diff 2.0
```

匹配选项:
- --algorithm: 匹配算法(hungarian、mcf、sinkhorn)
- --drift-correction: 启用线性时钟漂移校正
- --max-time-diff: 匹配最大时间差(秒)
- --confidence-threshold: 最低置信度阈值(0-1)

### 5. 使用对齐时间线裁剪数据

使用匹配后的时间线裁剪原始数据文件:

```bash
# 裁剪 fNIRS SNIRF 文件
multichsync crop \
  --input-dir Data/convert/fnirs \
  --timeline Data/matching/matched_timeline.csv \
  --output-dir Data/cropped/fnirs

# 裁剪 EEG BrainVision 文件
multichsync crop \
  --input-dir Data/convert/eeg \
  --timeline Data/matching/matched_timeline.csv \
  --output-dir Data/cropped/eeg

# 批量裁剪所有模态
multichsync crop batch \
  --convert-dir Data/convert \
  --timeline Data/matching/matched_timeline.csv \
  --output-dir Data/cropped
```

### 6. 原始数据裁剪

裁剪原始数据文件到匹配的时间线:

```bash
multichsync marker matchcrop \
  --timeline-csv Data/matching/sub-001/sub-001_timeline.csv \
  --metadata-json Data/matching/sub-001/sub-001_metadata.json \
  --reference fnirs \
  --output-dir Data/cropped/sub-001
```

**操作**:
1. 在 `Data/convert/{device_type}/` 中定位原始数据文件
2. 应用设备偏移校正
3. 裁剪到参考设备时间范围
4. 保存裁剪后的文件，时间重新索引从0开始

### 7. 对齐裁剪与任务名称修改

使用对齐时间线裁剪并可选修改任务名称:

```bash
multichsync marker matchcrop-aligned \
  --json-path Data/matching/sub-001/sub-001_metadata.json \
  --start-time 10.0 \
  --end-time 300.0 \
  --taskname "resting_state" \
  --output-dir Data/cropped/aligned/sub-001
```

**操作**:
1. 使用指定的 `--start-time` 和 `--end-time` (必填)，根据元数据中的共识时间范围进行验证
2. 修改输出文件中的任务名称(用于 BIDS 兼容性)
3. 对每个设备应用漂移校正
4. 裁剪并保存同步文件

## Python API 用法

### 导入模块

```python
from multichsync.marker import (
    extract_biopac_marker,
    extract_brainvision_marker,
    extract_fnirs_marker,
    batch_extract_markers,
    clean_markers,
    batch_clean_markers,
    match_markers,
    match_markers_by_algorithm,
    apply_drift_correction,
    crop_data_by_timeline,
    batch_crop_data
)
```

### 标记提取示例

```python
# 从 Biopac CSV 提取标记
marker_df = extract_biopac_marker(
    input_path="Data/raw/ecg/sub-001.csv",
    output_path="Data/marker/ecg/sub-001_marker.csv",
    threshold=1.0,
    edge="rising"
)

# 从 BrainVision 提取标记
marker_df = extract_brainvision_marker(
    vmrk_path="Data/raw/eeg/sub-001.vmrk",
    vhdr_path="Data/raw/eeg/sub-001.vhdr",
    output_path="Data/marker/eeg/sub-001_marker.csv"
)

# 从 fNIRS CSV 提取标记
marker_df = extract_fnirs_marker(
    input_path="Data/raw/fnirs/sub-001.csv",
    output_path="Data/marker/fnirs/sub-001_marker.csv",
    protocol_col="Protocol Type"
)
```

### 标记清理示例

```python
# 清理单个标记文件
cleaned_df = clean_markers(
    input_path="Data/marker/fnirs/sub-001_marker.csv",
    output_path="Data/marker/fnirs/sub-001_marker_cleaned.csv",
    min_interval=1.0,
    remove_start=True,
    min_rows=5
)
```

### 标记匹配示例

```python
# 匹配多个设备的标记
from multichsync.marker import match_markers

result = match_markers(
    input_files=[
        "Data/marker/fnirs/sub-001_marker.csv",
        "Data/marker/ecg/sub-001_marker.csv",
        "Data/marker/eeg/sub-001_marker.csv"
    ],
    device_names=["fnirs", "ecg", "eeg"],
    output_dir="Data/matching",
    max_time_diff=2.0,
    algorithm="hungarian",
    drift_correction=True
)

print(result["matched_timeline"])
print(result["confidence_scores"])
print(result["metadata"])
```

### 数据裁剪示例

```python
# 使用时间线裁剪 fNIRS 数据
from multichsync.marker import crop_data_by_timeline

crop_data_by_timeline(
    input_dir="Data/convert/fnirs",
    timeline_path="Data/matching/matched_timeline.csv",
    output_dir="Data/cropped/fnirs",
    file_pattern="*.snirf"
)
```

## 匹配算法详解

### Hungarian 算法
默认算法,使用线性分配找到最优匹配:

```python
result = match_markers(
    input_files=[...],
    algorithm="hungarian"
)
```

### Min-Cost Flow (MCF)
更适合处理缺失标记的情况:

```python
result = match_markers(
    input_files=[...],
    algorithm="mcf",
    max_time_diff=2.0
)
```

### Sinkhorn 算法
基于最优传输的软匹配算法:

```python
result = match_markers(
    input_files=[...],
    algorithm="sinkhorn",
    regularization=0.1
)
```

## 漂移校正

设备之间存在时钟漂移时,启用漂移校正:

```bash
multichsync marker match \
  --input-files ... \
  --drift-correction \
  --drift-degree 1
```

漂移校正通过以下方式处理时钟差异:
1. 估计每对设备之间的线性漂移率
2. 调整标记时间以消除系统性偏移
3. 重新运行匹配算法

## 输出说明

### 时间线 CSV
```csv
index,fnirs_time,ecg_time,eeg_time,confidence
0,0.0,0.05,-0.02,0.95
1,2.5,2.48,2.52,0.88
2,5.0,5.02,4.98,0.92
```

### 元数据 JSON
```json
{
  "algorithm": "hungarian",
  "total_markers": 15,
  "matched_markers": 14,
  "confidence_mean": 0.89,
  "drift_corrected": true
}
```

### 可视化图
- matched_timeline_alignment.png: 时间线对齐可视化
- matched_confidence_distribution.png: 置信度分数分布
- matched_drift_correction.png: 漂移校正前后对比(如果启用)

## 故障排除

### 常见问题

没有找到匹配:
- 增大 --max-time-diff 值
- 检查设备时间是否在同一参考框架
- 验证标记提取是否正确

置信度分数过低:
- 检查时间同步精度
- 验证时钟漂移是否需要校正
- 考虑使用 --confidence-threshold 过滤低质量匹配

漂移校正失败:
- 确保每个设备至少有 5 个标记
- 检查是否存在非线性漂移
- 尝试使用更高阶漂移模型

### 验证匹配结果

```python
import pandas as pd

timeline = pd.read_csv("Data/matching/matched_timeline.csv")
metadata = pd.read_json("Data/matching/matched_metadata.json")

print(f"平均置信度: {timeline['confidence'].mean():.2f}")
print(f"最低置信度: {timeline['confidence'].min():.2f}")
```

## 相关文档

- 快速开始(quickstart.md) - 端到端工作流程
- fNIRS 转换指南(fnirs_conversion.md) - fNIRS 数据转换
- EEG 转换指南(eeg_conversion.md) - EEG 数据转换
- ECG 转换指南(ecg_conversion.md) - ECG 数据转换
- 质量评估指南(quality_assessment.md) - 数据质量评估
- English Marker Processing Guide(../en/guides/marker_processing.md) - English version