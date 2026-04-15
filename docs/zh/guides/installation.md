# 安装指南

本指南介绍如何在各种平台上安装 MultiChSync。

## 前提条件

### 系统要求
- **操作系统**: Linux、macOS 或 Windows
- **Python**: 3.8 或更高版本
- **磁盘空间**: 安装至少 1GB，数据存储需额外空间
- **内存**: 最低 4GB RAM，大数据集建议 8GB+

### 所需系统库
- **Linux**: Build essentials, HDF5 libraries
- **macOS**: Xcode Command Line Tools
- **Windows**: Visual C++ Build Tools

## 安装方法

### 方法 1: 从源码安装（推荐用于开发）

1. **克隆仓库**:
   ```bash
   git clone <repository-url>
   cd multichsync
   ```

2. **创建虚拟环境**（推荐）:
   ```bash
   python -m venv venv
   
   # Linux/macOS:
   source venv/bin/activate
   
   # Windows:
   venv\Scripts\activate
   ```

3. **以开发模式安装**:
   ```bash
   pip install -e .
   ```

### 方法 2: 通过 pip 安装（适用于终端用户）

```bash
pip install multichsync
```

### 方法 3: 安装可选依赖

如需完整功能（包括高级 SNIRF 元数据写入）:

```bash
# 从源码安装所有额外依赖
pip install -e .[all]

# 通过 pip 安装（发布后）
pip install multichsync[all]
```

## 依赖管理

### 核心依赖
MultiChSync 需要以下 Python 包，会自动安装：

| 包 | 版本 | 用途 |
|---------|---------|---------|
| numpy | >=1.21.0 | 数值计算 |
| pandas | >=1.3.0 | 数据处理 |
| h5py | >=3.0.0 | HDF5/SNIRF 文件处理 |
| scipy | >=1.7.0 | 科学计算 |
| snirf | >=0.5.0 | SNIRF 格式验证 |
| mne | >=1.0.0 | EEG/fNIRS 处理 |
| bioread | >=2.0.0 | ACQ 文件读取 |
| pybv | >=0.5.0 | BrainVision 格式导出 |
| neurokit2 | >=0.2.0 | ECG 处理 |

### 可选依赖

| 包 | 用途 | 安装命令 |
|---------|---------|-----------------|
| mne-nirs | 增强 SNIRF 元数据写入 | `pip install mne-nirs` |
| networkx | 替代匹配算法 | `pip install networkx` |
| pytest | 运行测试 | `pip install pytest` |
| matplotlib | 额外绘图功能 | `pip install matplotlib` |

### 安装所有依赖

```bash
# 使用 requirements.txt（从源码）
pip install -r requirements.txt

# 安装可选依赖
pip install mne-nirs networkx matplotlib
```

## 平台特定说明

### Linux (Ubuntu/Debian)

```bash
# 安装系统依赖
sudo apt-get update
sudo apt-get install python3-dev python3-pip build-essential
sudo apt-get install libhdf5-dev

# 安装 MultiChSync
pip install multichsync
```

### Linux (Fedora/RHEL/CentOS)

```bash
# 安装系统依赖
sudo dnf install python3-devel python3-pip gcc gcc-c++
sudo dnf install hdf5-devel

# 安装 MultiChSync
pip install multichsync
```

### macOS

```bash
# 安装 Xcode Command Line Tools
xcode-select --install

# 安装 Homebrew（如未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 通过 Homebrew 安装 HDF5
brew install hdf5

# 安装 MultiChSync
pip install multichsync
```

### Windows

1. **安装 Python 3.8+** 从 [python.org](https://www.python.org/downloads/)
   - 安装时勾选 "Add Python to PATH"

2. **安装 Visual C++ Build Tools**:
   - 从 [Microsoft Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) 下载
   - 安装时选择 "Desktop development with C++" 工作负载

3. **打开命令提示符或 PowerShell**:
   ```powershell
   pip install multichsync
   ```

## 验证安装

安装完成后，运行以下命令验证：

```bash
# 检查 multichsync 是否可用
multichsync --help

# 显示版本信息
multichsync --version
```

## 故障排除

### 常见问题

**h5py 安装失败**
- Linux: 确保已安装 `libhdf5-dev`
- macOS: 通过 Homebrew 安装 `hdf5`
- Windows: 确保已安装 Visual C++ Build Tools

**MNE 相关错误**
- 确保安装完整版本的 MNE: `pip install mne`

**权限错误**
- 使用 `--user` 标志: `pip install --user multichsync`
- 或者使用虚拟环境（推荐）

## 相关文档

- [快速开始](quickstart.md) - 端到端工作流程
- [fNIRS 转换指南](fnirs_conversion.md) - Shimadzu 到 SNIRF 转换
- [English Documentation](../en/guides/installation.md) - English version