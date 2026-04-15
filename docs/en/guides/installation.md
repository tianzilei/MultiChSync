# Installation Guide

This guide covers how to install MultiChSync on various platforms.

## Prerequisites

### System Requirements
- **Operating System**: Linux, macOS, or Windows
- **Python**: Version 3.8 or higher
- **Disk Space**: Minimum 1GB for installation, plus space for data
- **Memory**: 4GB RAM minimum, 8GB+ recommended for large datasets

### Required System Libraries
- **Linux**: Build essentials, HDF5 libraries
- **macOS**: Xcode Command Line Tools
- **Windows**: Visual C++ Build Tools

## Installation Methods

### Method 1: Install from Source (Recommended for Development)

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd multichsync
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   
   # On Linux/macOS:
   source venv/bin/activate
   
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install in development mode**:
   ```bash
   pip install -e .
   ```

### Method 2: Install via pip (For End Users)

```bash
pip install multichsync
```

### Method 3: Install with Optional Dependencies

For full functionality including advanced SNIRF metadata writing:

```bash
# From source with all extras
pip install -e .[all]

# Via pip with all extras (when published)
pip install multichsync[all]
```

## Dependency Management

### Core Dependencies
MultiChSync requires the following Python packages which are automatically installed:

| Package | Version | Purpose |
|---------|---------|---------|
| numpy | >=1.21.0 | Numerical computations |
| pandas | >=1.3.0 | Data manipulation |
| h5py | >=3.0.0 | HDF5/SNIRF file handling |
| scipy | >=1.7.0 | Scientific computing |
| snirf | >=0.5.0 | SNIRF format validation |
| mne | >=1.0.0 | EEG/fNIRS processing |
| bioread | >=2.0.0 | ACQ file reading |
| pybv | >=0.5.0 | BrainVision format export |
| neurokit2 | >=0.2.0 | ECG processing |

### Optional Dependencies

| Package | Purpose | Install Command |
|---------|---------|-----------------|
| mne-nirs | Enhanced SNIRF metadata writing | `pip install mne-nirs` |
| networkx | Alternative matching algorithms | `pip install networkx` |
| pytest | Running tests | `pip install pytest` |
| matplotlib | Additional plotting | `pip install matplotlib` |

### Installing All Dependencies

```bash
# Using requirements.txt (from source)
pip install -r requirements.txt

# Install optional dependencies
pip install mne-nirs networkx matplotlib
```

## Platform-Specific Instructions

### Linux (Ubuntu/Debian)

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install python3-dev python3-pip build-essential
sudo apt-get install libhdf5-dev

# Install MultiChSync
pip install multichsync
```

### Linux (Fedora/RHEL/CentOS)

```bash
# Install system dependencies
sudo dnf install python3-devel python3-pip gcc gcc-c++
sudo dnf install hdf5-devel

# Install MultiChSync
pip install multichsync
```

### macOS

```bash
# Install Xcode Command Line Tools
xcode-select --install

# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install HDF5 via Homebrew
brew install hdf5

# Install MultiChSync
pip install multichsync
```

### Windows

1. **Install Python 3.8+** from [python.org](https://www.python.org/downloads/)
   - Check "Add Python to PATH" during installation

2. **Install Visual C++ Build Tools**:
   - Download from [Microsoft Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
   - Install with "Desktop development with C++" workload

3. **Open Command Prompt or PowerShell**:
   ```powershell
   pip install multichsync
   ```

## Verification

After installation, verify that MultiChSync is working correctly:

### Check Installation
```bash
# Check version
multichsync --version

# Show help
multichsync --help
```

### Run Basic Tests
```bash
# Test fNIRS module import
python -c "from multichsync.fnirs import convert_fnirs_to_snirf; print('fNIRS module OK')"

# Test ECG module import
python -c "from multichsync.ecg import convert_acq_to_csv; print('ECG module OK')"

# Test EEG module import
python -c "from multichsync.eeg import convert_eeg_format; print('EEG module OK')"
```

### Test Data Conversion (Optional)
Create a test directory structure and run a simple conversion:

```bash
# Create test directories
mkdir -p test_data/raw/fnirs
mkdir -p test_data/convert

# Run a test conversion (requires sample data)
# multichsync fnirs convert --txt-path sample.TXT \
#   --src-coords source_coordinates.csv \
#   --det-coords detector_coordinates.csv \
#   --output test_data/convert/test.snirf
```

## Troubleshooting

### Common Issues

#### 1. "h5py" Installation Failures
**Symptoms**: `ImportError: No module named 'h5py'` or compilation errors

**Solutions**:
- **Linux**: Install system HDF5 libraries first
  ```bash
  sudo apt-get install libhdf5-dev  # Ubuntu/Debian
  sudo dnf install hdf5-devel       # Fedora/RHEL
  ```
- **macOS**: Install via Homebrew
  ```bash
  brew install hdf5
  pip install --no-binary h5py h5py
  ```
- **Windows**: Use precompiled wheels
  ```bash
  pip install h5py
  ```

#### 2. "mne" Import Errors
**Symptoms**: `ImportError: cannot import name 'Raw' from 'mne'`

**Solutions**:
- Upgrade MNE-Python:
  ```bash
  pip install --upgrade mne
  ```
- Install specific version:
  ```bash
  pip install mne==1.0.0
  ```

#### 3. Permission Errors
**Symptoms**: `Permission denied` when installing

**Solutions**:
- Use virtual environment (recommended)
- Use `--user` flag:
  ```bash
  pip install --user multichsync
  ```
- On Linux/macOS, avoid `sudo pip`

#### 4. Memory Errors During Processing
**Symptoms**: `MemoryError` or `Killed` during large file processing

**Solutions**:
- Process files individually instead of batch
- Increase system swap space
- Use `--max-files` option to limit batch size

### Getting Help

If you encounter issues not covered here:

1. **Check the documentation**: Review this guide and the README
2. **Search existing issues**: Check the GitHub issue tracker
3. **Create a new issue**: Provide:
   - Operating system and Python version
   - Complete error message
   - Steps to reproduce
   - Relevant log output

## Upgrading

### Upgrade from Previous Version
```bash
# If installed via pip
pip install --upgrade multichsync

# If installed from source
cd multichsync
git pull
pip install -e . --upgrade
```

### Check Current Version
```bash
multichsync --version
python -c "import multichsync; print(multichsync.__version__)"
```

## Uninstallation

### Remove MultiChSync
```bash
# If installed via pip
pip uninstall multichsync

# Also remove optional dependencies if desired
pip uninstall mne-nirs networkx
```

### Clean Up Data
Remove any remaining data directories:
```bash
# Be careful - this will delete all processed data
rm -rf Data/convert Data/marker Data/quality
```

---

*Next Steps*: After installation, proceed to the [Quick Start Guide](quickstart.md) to begin using MultiChSync.