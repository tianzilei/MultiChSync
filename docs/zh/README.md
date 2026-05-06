# MultiChSync

多模态神经影像数据（fNIRS、EEG、ECG）转换与同步工具。

## 功能特性

- **fNIRS**: 将 Shimadzu/NIRS-SPM TXT 格式转换为 SNIRF v1.1，支持 MNE 兼容性修复
- **EEG**: 将 Curry/EEGLAB 格式转换为 BrainVision/EEGLAB/EDF 格式，支持固定采样率
- **ECG**: 将 Biopac ACQ 格式转换为 CSV 格式，支持固定采样率
- **Marker 处理**: 跨模态提取、清洗、匹配和裁剪事件标记，支持漂移校正和详细报告
- **质量评估**: 自动化 fNIRS 信号质量评估，支持元数据写入 SNIRF 文件
- **BIDS 兼容**: 输出文件遵循 BIDS 命名规范

## 快速开始

### 安装

```bash
# 克隆仓库
git clone <repository-url>
cd multichsync

# 安装核心依赖
pip install -e .

# 安装全部开发工具（pytest, black, ruff, mypy）
pip install -e ".[dev]"

# 安装可选的质量评估扩展
pip install -e ".[quality]"
```

### 数据转换

```bash
# fNIRS: TXT 转 SNIRF
multichsync fnirs batch --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs

# EEG: 转换为 BrainVision 格式（默认 250Hz）
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision \
  --output-dir Data/convert/EEG --recursive --sampling-rate 250

# ECG: ACQ 转 CSV
multichsync ecg batch --input-dir Data/raw/ECG \
  --output-dir Data/convert/ECG --sampling-rate 250
```

### 固定采样率

EEG 和 ECG 转换支持固定采样率输出，确保下游处理的一致性：

```bash
# EEG: 以 250Hz 转换（使用 --sampling-rate 时的默认值）
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --sampling-rate 250

# EEG: 自定义采样率（500Hz）
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --sampling-rate 500

# EEG: 保持原始采样率（不传 --sampling-rate 参数）
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision

# ECG: 以 250Hz 转换（默认）
multichsync ecg batch --input-dir Data/raw/ECG --sampling-rate 250
```

**注意:** EEG 重采样使用 0.1Hz 的容差阈值。当原始采样率与目标采样率接近时，会跳过不必要的重采样处理。

### Marker 处理流程

```bash
# 提取单个文件的 marker（自动检测类型）
multichsync marker extract --input Data/raw/fnirs/sub-001_task-rest_fnirs.csv --type fnirs

# 批量提取所有模态的 marker
multichsync marker batch --types fnirs,ecg,eeg

# 清洗 marker（去重、过滤质量、移除 t=0 的起始标记）
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start

# 生成受试者级别的报告（扫描 Data/convert/ 和 Data/raw/）
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# 跨设备匹配 marker（支持多种匹配算法）
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg \
  --output-dir Data/matching --method hungarian

# 按文件名匹配（自动从 Data/convert 加载）
multichsync marker match --filename sub-060_ses-01_task-rest \
  --output-dir Data/matching

# 裁剪匹配后的时间线至最短序列
multichsync marker crop --timeline-csv Data/matching/matched_timeline.csv \
  --metadata-json Data/matching/matched_metadata.json --output-prefix cropped

# 手动调整设备偏移量并重新生成匹配时间线
multichsync marker manual-match \
  --json-path Data/matching/matched_metadata.json \
  --offsets "[1.5, -0.3]" \
  --prefix manual

# 基于匹配结果裁剪多设备原始数据
multichsync marker matchcrop --timeline-csv Data/matching/matched_timeline.csv \
  --metadata-json Data/matching/matched_metadata.json \
  --reference sub-060_ses-01_task-rest_fnirs --output-dir Data/matchcrop

# 基于共识时间范围裁剪所有设备数据
multichsync marker matchcrop-aligned \
  --json-path Data/matching/matched_metadata.json \
  --start-time 0.0 --end-time 300.0 --taskname newtask

# 支持的匹配方法（通过 --method 参数）:
#   hungarian    - 匈牙利算法（默认）
#   mincostflow  - 最小费用流
#   sinkhorn     - Sinkhorn 最优传输
```

### fNIRS 质量评估

```bash
# 批量基础质量评估
multichsync quality batch --input-dir Data/convert/fnirs \
  --output-dir Data/quality --l-freq 0.01 --h-freq 0.2

# 质量评估并将结果写入 SNIRF 元数据
multichsync quality batch-with-metadata --input-dir Data/convert/fnirs \
  --output-dir Data/quality

# 批量计算静息态指标
multichsync quality resting-metrics --input-dir Data/convert/fnirs

# 生成可视化图表
multichsync quality visualize --input Data/convert/fnirs/sub-001.snirf
```

## 数据目录结构

```
Data/
├── raw/               # 原始数据
│   ├── fnirs/        # .txt, .csv 文件
│   ├── EEG/          # .set, .fdt 文件
│   └── ECG/          # .acq 文件
├── convert/          # 转换后的数据
│   ├── fnirs/        # .snirf 文件
│   ├── EEG/          # .vhdr, .vmrk, .eeg 文件
│   └── ECG/          # .csv 文件
├── marker/           # 提取的标记
│   ├── fnirs/
│   ├── ecg/
│   ├── eeg/
│   └── info/         # 受试者报告
├── matching/         # 跨设备匹配结果
└── quality/          # fNIRS 质量报告
```

## 系统依赖

- Python >= 3.8
- numpy, pandas, h5py, scipy, networkx
- mne（EEG/fNIRS 处理）
- bioread（ACQ 文件读取）
- pybv（BrainVision 格式导出）
- neurokit2（ECG 处理）
- snirf（SNIRF 格式验证）
- mne-nirs（可选，用于 SNIRF 元数据写入）

安装所有依赖：
```bash
pip install -r requirements.txt
```

## 开发指南

### 环境配置

```bash
pip install -e ".[dev]"
```

### 常用命令

| 工具 | 命令 | 说明 |
|------|------|------|
| 测试 | `pytest --cov=multichsync --cov-report=term-missing -n auto` | 运行全部测试并生成覆盖率报告 |
| 单文件测试 | `pytest tests/unit/test_fnirs_converter.py -v` | 运行指定测试文件 |
| 格式化 | `black multichsync tests` | 自动格式化代码 |
| 静态检查 | `ruff check multichsync tests` | 代码静态分析 |
| 类型检查 | `mypy multichsync` | 类型注解检查 |

### 持续集成

GitHub Actions 在推送/PR 到 `main`/`develop` 分支时自动运行。测试矩阵覆盖 3 个操作系统 × Python 3.8–3.12（排除 macos-3.12 和 windows-3.12）。流水线包括测试、代码检查和覆盖率检查（阈值：35%）。

### AI 代理指南

如使用 AI 编码代理，请参考 [AGENTS.md](../en/contributing/agents.md) 获取仓库特定的架构、工具链、测试和常见注意事项指南。

## 文档

详细的文档位于 `docs/` 目录：

- **[English Documentation](../en/README.md)** - 完整英文文档
- **[中文文档](README.md)** - 中文文档

文档内容包括：
- 安装和快速入门指南
- 模块专用指南（fNIRS、EEG、ECG、marker、质量评估）
- API 参考和架构概述
- 技术规格和开发指南
- AI 代理开发指南

## 许可证

MIT License

## 贡献代码

欢迎提交 Issue 和 Pull Request。提交前请确保：

1. 安装开发依赖：`pip install -e ".[dev]"`
2. 格式化代码：`black multichsync tests`
3. 检查代码规范：`ruff check multichsync tests`
4. 运行类型检查：`mypy multichsync`
5. 确保测试通过：`pytest --cov=multichsync -n auto`
