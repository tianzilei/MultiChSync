# MultiChSync 文档(中文)

欢迎访问 MultiChSync 中文文档。本目录包含:

- architecture/: 架构决策和原理
- guides/: 使用指南和教程
- api/: API 参考文档
- technical/: 技术规格
- contributing/: 开发指南
- development/: 开发文档(脚本说明等)

## 快速链接

### 指南
- 安装指南(guides/installation.md) - 安装和需求
- 快速开始(guides/quickstart.md) - 端到端工作流程
- fNIRS 转换指南(guides/fnirs_conversion.md) - Shimadzu 到 SNIRF 转换
- EEG 转换指南(guides/eeg_conversion.md) - Curry/EEGLAB 到 BrainVision 转换
- ECG 转换指南(guides/ecg_conversion.md) - Biopac ACQ 到 CSV 转换
- Marker 处理指南(guides/marker_processing.md) - 多设备 marker 同步
- 质量评估指南(guides/quality_assessment.md) - fNIRS 信号质量评估

### 参考文档
- API 参考(api/index.md) - Python 接口文档(待翻译)
- 架构概述(architecture/overview.md) - 系统设计(待翻译)
- 技术规格(technical/) - 详细技术文档(待翻译)

### 开发文档
- 代码风格指南(contributing/CODE_STYLE.md) - 编码规范和模式(原始文件,中英混合)
- 开发脚本说明(development/scripts_development.md) - 开发脚本使用说明
- 分析脚本说明(development/scripts_analysis.md) - 分析脚本使用说明
- 调试笔记(development/debug_notes_2026-04-13.md) - 开发调试记录

## 文档结构

```
docs/zh/
├── architecture/           # 架构决策和原理
│   └── overview.md        # 系统架构概述(待翻译)
├── guides/                # 使用指南和教程
│   ├── installation.md    # 安装指南
│   ├── quickstart.md      # 快速开始指南
│   ├── fnirs_conversion.md # fNIRS 转换指南
│   ├── eeg_conversion.md  # EEG 转换指南
│   ├── ecg_conversion.md  # ECG 转换指南
│   ├── marker_processing.md # Marker 处理指南
│   └── quality_assessment.md # 质量评估指南
├── api/                   # API 参考文档
│   └── index.md          # API 参考索引(待翻译)
├── technical/             # 技术规格
│   ├── fnirs_signal_level_qc_metrics.md # fNIRS 质量指标规范(待翻译)
│   └── event_matching_analysis.md      # 事件匹配分析规范(待翻译)
├── contributing/          # 开发指南
│   └── CODE_STYLE.md     # 代码风格指南(原始文件,中英混合)
└── development/           # 开发文档
    ├── scripts_development.md # 开发脚本说明
    ├── scripts_analysis.md    # 分析脚本说明
    └── debug_notes_2026-04-13.md # 调试笔记
```

## 获取帮助

如需 MultiChSync 帮助:

1. 查看指南(guides/)获取分步说明
2. 查阅 API 参考(api/index.md)了解 Python 用法
3. 研究技术规格(technical/)了解详细算法
4. 参考架构概述(architecture/overview.md)理解系统设计

## 贡献中文文档

欢迎贡献以改进中文文档。请遵循代码风格指南(contributing/CODE_STYLE.md)中的写作规范。

更新文档时:

1. 确保所有示例可运行且最新
2. 行为变化时同时更新指南和 API 参考
3. 保持语言清晰简洁
4. 在所有文档中使用一致的术语

## 相关文档

- English Documentation(../en/README.md) - 英文文档
- 项目 README(../../README.md) - 项目概览(英文)