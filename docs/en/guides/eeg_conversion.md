# EEG Conversion Guide

## Overview

The EEG conversion module supports converting EEG data files between various formats. It leverages MNE-Python for reading EEG files and provides export to standard EEG formats commonly used in neuroimaging research.

**Key capabilities:**
- Read EEG files in Curry and EEGLAB formats
- Export to BrainVision, EEGLAB, or EDF formats
- Batch processing of multiple files
- Integration with the MultiChSync workflow

## Supported Formats

### Input Formats
- **EEGLAB**: `.set` files (with optional `.fdt` data files)
- **Curry**: Multiple file extensions including `.cdt`, `.dap`, `.dat`, `.rs3`, `.cef`, `.cdt.dpa`

### Output Formats
- **BrainVision**: Industry-standard format with separate `.vhdr`, `.vmrk`, and `.eeg` files
- **EEGLAB**: MATLAB-compatible `.set` files
- **EDF**: European Data Format, a widely supported format for biomedical signals

## Command Line Usage

### Single File Conversion

```bash
# Convert to BrainVision format (default)
multichsync eeg convert \
  --file-path data.set \
  --format BrainVision \
  --output ./converted

# Convert to EEGLAB format
multichsync eeg convert \
  --file-path data.cdt \
  --format EEGLAB \
  --output ./converted

# Convert to EDF format
multichsync eeg convert \
  --file-path data.set \
  --format EDF \
  --output ./converted
```

**Options:**
- `--file-path`: Input EEG file path (required)
- `--format`: Output format: `BrainVision` (default), `EEGLAB`, or `EDF`
- `--output`: Output directory or file path (optional, defaults to `convert/` subdirectory)
- `--preload`: Preload data into memory (default: `False`)
- `--overwrite`: Overwrite existing files (default: `False`)
- `--verbose`: Show verbose output (default: follows global verbosity)

### Batch Conversion

```bash
# Convert all EEG files in a directory to BrainVision format
multichsync eeg batch \
  --input-dir ./raw_eeg \
  --format BrainVision \
  --output-dir ./converted/eeg

# Convert with recursive directory search
multichsync eeg batch \
  --input-dir ./raw_eeg \
  --format BrainVision \
  --output-dir ./converted/eeg \
  --recursive

# Convert to EEGLAB format with preloading
multichsync eeg batch \
  --input-dir ./raw_eeg \
  --format EEGLAB \
  --output-dir ./converted/eeg \
  --preload
```

**Options:**
- `--input-dir`: Input directory containing EEG files (required)
- `--format`: Output format: `BrainVision` (default), `EEGLAB`, or `EDF`
- `--output-dir`: Output directory for converted files (required)
- `--recursive`: Search for files recursively in subdirectories (default: `False`)
- `--preload`: Preload data into memory (default: `False`)
- `--overwrite`: Overwrite existing files (default: `False`)
- `--verbose`: Show verbose output (default: follows global verbosity)

## Python API Usage

### Import the Module

```python
from multichsync.eeg import (
    convert_eeg_format,
    convert_eeg_to_brainvision,
    convert_eeg_to_eeglab,
    convert_eeg_to_edf,
    batch_convert_eeg_format,
    batch_convert_eeg_to_brainvision,
    batch_convert_eeg_to_eeglab,
    batch_convert_eeg_to_edf
)
```

### Single File Conversion

```python
# General conversion function
raw, output_path = convert_eeg_format(
    file_path="data.set",
    export_format="BrainVision",  # "BrainVision", "EEGLAB", or "EDF"
    output_path="./converted",
    preload=False,
    overwrite=False,
    verbose=None
)

print(f"Converted file saved to: {output_path}")
print(f"Raw object channels: {len(raw.ch_names)}")
print(f"Sampling rate: {raw.info['sfreq']} Hz")

# Format-specific convenience functions
raw_bv, bv_path = convert_eeg_to_brainvision(
    file_path="data.set",
    output_path="./converted/brainvision"
)

raw_eeglab, eeglab_path = convert_eeg_to_eeglab(
    file_path="data.cdt",
    output_path="./converted/eeglab"
)

raw_edf, edf_path = convert_eeg_to_edf(
    file_path="data.set",
    output_path="./converted/edf"
)
```

### Batch Conversion

```python
# General batch conversion
results = batch_convert_eeg_format(
    input_dir="./raw_eeg",
    export_format="BrainVision",
    output_dir="./converted/eeg",
    recursive=True,
    preload=False,
    overwrite=False,
    verbose=None
)

print(f"Successfully converted {len(results)} files")

# Format-specific batch functions
results_bv = batch_convert_eeg_to_brainvision(
    input_dir="./raw_eeg",
    output_dir="./converted/brainvision",
    recursive=True
)

results_eeglab = batch_convert_eeg_to_eeglab(
    input_dir="./raw_eeg",
    output_dir="./converted/eeglab"
)

results_edf = batch_convert_eeg_to_edf(
    input_dir="./raw_eeg",
    output_dir="./converted/edf"
)
```

## File Format Details

### BrainVision Format
The BrainVision format consists of three files:
1. `.vhdr` - Header file (text format, contains metadata)
2. `.vmrk` - Marker file (text format, contains event markers)
3. `.eeg` - Data file (binary format, contains EEG data)

**Output structure:**
```
converted/
├── subject1.vhdr
├── subject1.vmrk
├── subject1.eeg
├── subject2.vhdr
├── subject2.vmrk
└── subject2.eeg
```

### EEGLAB Format
EEGLAB format uses a single `.set` file (MATLAB format) that contains both data and metadata. For large datasets, a separate `.fdt` file may be created for the binary data.

### EDF Format
EDF (European Data Format) is a simple, widely supported binary format for biomedical signals. Each file contains a header section followed by data records.

## Integration with MultiChSync Workflow

The EEG conversion module is designed to work seamlessly with the overall MultiChSync pipeline:

### 1. Data Organization
```
Data/
├── raw/EEG/                 # Original EEG files
│   ├── subject1.set
│   ├── subject2.cdt
│   └── ...
└── convert/EEG/            # Converted files
    ├── subject1.vhdr
    ├── subject1.vmrk
    ├── subject1.eeg
    └── ...
```

### 2. Marker Extraction
After conversion, event markers can be extracted from BrainVision `.vmrk` files:

```bash
multichsync marker extract \
  --input Data/convert/EEG/subject1.vmrk \
  --type brainvision \
  --output Data/marker/eeg/subject1_marker.csv
```

### 3. Multi-Modal Synchronization
EEG data can be synchronized with fNIRS and ECG data using the marker matching pipeline.

## Examples

### Complete EEG Processing Pipeline

```bash
# 1. Convert raw EEG files to BrainVision format
multichsync eeg batch \
  --input-dir Data/raw/EEG \
  --format BrainVision \
  --output-dir Data/convert/EEG \
  --recursive

# 2. Extract markers from converted files
python extract_all_markers.py --types eeg

# 3. Clean extracted markers
multichsync marker clean \
  --input Data/marker/eeg \
  --inplace \
  --min-rows 2 \
  --min-interval 1.0

# 4. Generate subject reports
multichsync marker info \
  --input-dir Data/marker \
  --output-dir Data/marker/info
```

### Python Script for Custom Processing

```python
import os
from pathlib import Path
from multichsync.eeg import convert_eeg_format

def process_eeg_directory(input_dir, output_dir, target_format="BrainVision"):
    """Custom EEG processing function"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Find all EEG files
    eeg_extensions = {'.set', '.cdt', '.dap', '.dat', '.rs3', '.cef'}
    eeg_files = []
    
    for ext in eeg_extensions:
        eeg_files.extend(input_path.rglob(f"*{ext}"))
    
    print(f"Found {len(eeg_files)} EEG files")
    
    # Convert each file
    for eeg_file in eeg_files:
        try:
            # Generate output path
            rel_path = eeg_file.relative_to(input_path)
            out_file = output_path / rel_path.with_suffix(
                '.vhdr' if target_format == 'BrainVision' else 
                '.set' if target_format == 'EEGLAB' else 
                '.edf'
            )
            out_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert file
            raw, converted_path = convert_eeg_format(
                file_path=eeg_file,
                export_format=target_format,
                output_path=out_file,
                preload=False,
                overwrite=False
            )
            
            print(f"✓ {eeg_file.name} -> {converted_path}")
            
        except Exception as e:
            print(f"✗ Failed to convert {eeg_file.name}: {e}")

# Usage
process_eeg_directory(
    input_dir="Data/raw/EEG",
    output_dir="Data/convert/EEG",
    target_format="BrainVision"
)
```

## Troubleshooting

### Common Issues

**1. MNE-Python not installed**
```
ImportError: MNE-Python library required to read EEG files
```
**Solution:** Install MNE-Python: `pip install mne`

**2. Unsupported file format**
```
ValueError: Cannot determine format for: file.xyz
```
**Solution:** Ensure the file has a supported extension. Use `--format` to explicitly specify the input format if needed.

**3. Missing data file (EEGLAB)**
```
FileNotFoundError: Cannot find data file: file.fdt
```
**Solution:** Ensure both `.set` and `.fdt` files are present in the same directory.

**4. Permission denied when writing files**
```
PermissionError: [Errno 13] Permission denied: 'output.vhdr'
```
**Solution:** Check write permissions for the output directory.

**5. Insufficient memory for large files**
```
MemoryError: Unable to allocate array with shape ...
```
**Solution:** Use `preload=False` (default) or process files individually.

### Debugging Tips

1. **Enable verbose output:**
   ```bash
   multichsync eeg convert --file-path data.set --verbose
   ```

2. **Test with a single file first:**
   ```bash
   multichsync eeg convert --file-path test.set --output ./test_output
   ```

3. **Check file permissions and disk space** before batch processing.

4. **Verify dependencies:**
   ```python
   import mne
   print(f"MNE version: {mne.__version__}")
   ```

## Advanced Usage

### Custom Preprocessing

The EEG conversion module returns MNE Raw objects, which can be used for custom preprocessing:

```python
from multichsync.eeg import convert_eeg_format
import mne

# Convert file and get Raw object
raw, output_path = convert_eeg_format(
    file_path="data.set",
    export_format="BrainVision",
    output_path="./converted"
)

# Apply custom preprocessing
raw.filter(1.0, 40.0)  # Bandpass filter
raw.notch_filter(50.0)  # Notch filter for line noise

# Re-reference to average
raw.set_eeg_reference('average')

# Save preprocessed data
raw.save("./converted/preprocessed.fif", overwrite=True)
```

### Quality Control Integration

While MultiChSync's quality assessment focuses on fNIRS data, EEG quality can be assessed using MNE's built-in functions:

```python
import mne
from multichsync.eeg import convert_eeg_format

# Convert and load EEG data
raw, _ = convert_eeg_format("data.set", preload=True)

# Compute EEG quality metrics
power_spectrum = raw.compute_psd()
print(f"Power spectrum shape: {power_spectrum.shape}")

# Detect bad channels
raw.info['bads'] = []  # Clear existing bad channels
raw.plot(duration=5, n_channels=30)  # Visual inspection
```

## Related Documentation

- [Quick Start Guide](../guides/quickstart.md) - End-to-end workflow examples
- [Installation Guide](../guides/installation.md) - Setup and dependencies
- [Marker Processing Guide](../guides/marker_processing.md) - Extracting and processing EEG markers
- [Architecture Overview](../architecture/overview.md) - System design and components

## References

- **MNE-Python**: Gramfort et al. (2013) MEG and EEG data analysis with MNE-Python. Frontiers in Neuroscience.
- **BrainVision Format**: Brain Products GmbH. (2021) BrainVision Core Data Format 1.0.
- **EEGLAB**: Delorme & Makeig (2004) EEGLAB: an open source toolbox for analysis of single-trial EEG dynamics. Journal of Neuroscience Methods.
- **EDF Format**: Kemp et al. (1992) A simple format for exchange of digitized polygraphic recordings. Electroencephalography and Clinical Neurophysiology.