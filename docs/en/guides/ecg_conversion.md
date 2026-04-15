# ECG Conversion Guide

## Overview

The ECG conversion module supports converting Biopac ACQ files to CSV format. It provides flexible output options including grouped CSV files by channel type and supports two backend libraries (bioread and neurokit2) for reading ACQ files.

**Key capabilities:**
- Read Biopac ACQ files using either bioread or neurokit2 backend
- Export to CSV format with optional grouping by channel type
- Batch processing of multiple ACQ files
- Resampling to specified sampling rates
- Integration with the MultiChSync workflow for marker extraction

## Supported Formats

### Input Formats
- **Biopac ACQ**: `.acq` files from Biopac data acquisition systems

### Output Formats
- **CSV**: Comma-separated values format with flexible grouping options

## Command Line Usage

### Single File Conversion

```bash
# Convert ACQ to CSV with default settings (grouped by channel type)
multichsync ecg convert \
  --acq data.acq \
  --output ./converted

# Convert with custom sampling rate
multichsync ecg convert \
  --acq data.acq \
  --output ./converted \
  --sampling-rate 500

# Convert to single CSV file (no grouping)
multichsync ecg convert \
  --acq data.acq \
  --output ./converted/single.csv \
  --no-group

# Specify float format for CSV output
multichsync ecg convert \
  --acq data.acq \
  --output ./converted \
  --float-format "%.8f"
```

**Options:**
- `--acq`: Input ACQ file path (required)
- `--output`: Output file path or directory (optional, defaults to `convert/` subdirectory)
- `--sampling-rate`: Target sampling rate in Hz (optional, default: 250)
- `--no-group`: Output single CSV file instead of grouping by channel type (default: grouped)
- `--float-format`: Float format string for CSV output (default: `"%.6f"`)
- `--format`: Output format (currently only `csv` is supported)

### Batch Conversion

```bash
# Convert all ACQ files in a directory
multichsync ecg batch \
  --input-dir ./raw_ecg \
  --output-dir ./converted/ecg

# Convert with custom sampling rate
multichsync ecg batch \
  --input-dir ./raw_ecg \
  --output-dir ./converted/ecg \
  --sampling-rate 500

# Convert to single CSV files (no grouping)
multichsync ecg batch \
  --input-dir ./raw_ecg \
  --output-dir ./converted/ecg \
  --no-group
```

**Options:**
- `--input-dir`: Input directory containing ACQ files (required)
- `--output-dir`: Output directory for converted files (required)
- `--sampling-rate`: Target sampling rate in Hz (optional, default: 250)
- `--no-group`: Output single CSV files instead of grouping by channel type (default: grouped)
- `--float-format`: Float format string for CSV output (default: `"%.6f"`)
- `--format`: Output format (currently only `csv` is supported)

## Python API Usage

### Import the Module

```python
from multichsync.ecg import (
    convert_acq_to_csv,
    batch_convert_acq_to_csv,
    parse_acq_file,
    get_channel_info
)
```

### Single File Conversion

```python
# Convert with default settings (grouped by channel type)
result = convert_acq_to_csv(
    acq_path="data.acq",
    output_path="./converted",
    sampling_rate=250,      # Target sampling rate (Hz)
    group_by_type=True,     # Group output by channel type
    float_format="%.6f"     # Float format for CSV
)

# Result is a dictionary when group_by_type=True
if isinstance(result, dict):
    print("Output files:")
    for group, file_path in result.items():
        print(f"  {group}: {file_path}")
else:
    print(f"Output file: {result}")

# Convert to single CSV file
single_file = convert_acq_to_csv(
    acq_path="data.acq",
    output_path="./converted/single.csv",
    sampling_rate=500,
    group_by_type=False
)
print(f"Single output file: {single_file}")
```

### Batch Conversion

```python
# Batch convert all ACQ files in a directory
results = batch_convert_acq_to_csv(
    input_dir="./raw_ecg",
    output_dir="./converted/ecg",
    sampling_rate=250,
    group_by_type=True
)

print(f"Successfully converted {len(results)} files")
for acq_file, output_files in results.items():
    print(f"  {acq_file} -> {output_files}")
```

### Direct File Parsing

```python
# Parse ACQ file without conversion
parsed = parse_acq_file(
    acq_path="data.acq",
    sampling_rate=250
)

# Access parsed data
data_df = parsed['data']           # DataFrame with channel data
channels = parsed['channels']      # Channel information
original_sr = parsed['original_sr'] # Original sampling rate
sampling_rate = parsed['sampling_rate'] # Actual sampling rate after resampling
duration = parsed['duration']      # Data duration in seconds
metadata = parsed['metadata']      # File metadata

print(f"Data shape: {data_df.shape}")
print(f"Channels: {len(channels)}")
print(f"Sampling rate: {sampling_rate} Hz")
print(f"Duration: {duration:.2f} seconds")

# Get channel information
channel_info = get_channel_info(acq_path="data.acq")
print(f"Channel info: {channel_info}")
```

## Output Format Details

### Grouped Output (Default)

When `group_by_type=True` (default), the module creates separate CSV files for different channel types:

```
converted/
├── data_ecg.csv          # ECG channels
├── data_resp.csv         # Respiration channels  
├── data_ppg.csv          # PPG channels
├── data_eda.csv          # EDA channels
├── data_marker.csv       # Marker channels
└── data_other.csv        # Other/unknown channels
```

**Channel type detection:** The module automatically detects channel types based on normalized channel names:
- `ecg`, `ekg`, `electrocardiogram`, `heartrate`
- `resp`, `respiration`, `breathing`
- `ppg`, `photoplethysmography`
- `eda`, `gsr`, `galvanicskinresponse`
- `marker`, `trigger`, `event`
- Others are classified as `other`

### Single File Output

When `group_by_type=False`, all channels are saved to a single CSV file:

```csv
time,Channel1,Channel2,Marker,...
0.000,0.123456,-0.045678,0.0,...
0.004,0.124567,-0.046789,0.0,...
0.008,0.125678,-0.047890,0.0,...
...
```

### CSV Format Specifications

- **Time column**: First column is always time in seconds
- **Channel columns**: Subsequent columns contain channel data
- **Header**: Column names match original channel names
- **Float precision**: Controlled by `float_format` parameter (default: `"%.6f"`)
- **Encoding**: UTF-8 with BOM for compatibility with various software

## Integration with MultiChSync Workflow

The ECG conversion module is designed to work seamlessly with the overall MultiChSync pipeline:

### 1. Data Organization
```
Data/
├── raw/ECG/                 # Original ACQ files
│   ├── subject1.acq
│   ├── subject2.acq
│   └── ...
└── convert/ECG/            # Converted CSV files
    ├── subject1_ecg.csv
    ├── subject1_resp.csv
    ├── subject1_marker.csv
    └── ...
```

### 2. Marker Extraction
After conversion, event markers can be extracted from marker CSV files:

```bash
# Extract markers from ECG marker CSV
multichsync marker extract \
  --input Data/convert/ECG/subject1_marker.csv \
  --type biopac \
  --fs 500 \
  --tolerance 0.2 \
  --output Data/marker/ecg/subject1_marker.csv
```

### 3. Multi-Modal Synchronization
ECG data can be synchronized with fNIRS and EEG data using the marker matching pipeline.

## Examples

### Complete ECG Processing Pipeline

```bash
# 1. Convert raw ACQ files to CSV format
multichsync ecg batch \
  --input-dir Data/raw/ECG \
  --output-dir Data/convert/ECG \
  --sampling-rate 500

# 2. Extract markers from converted files
python extract_all_markers.py --types ecg

# 3. Clean extracted markers
multichsync marker clean \
  --input Data/marker/ecg \
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
from multichsync.ecg import convert_acq_to_csv, parse_acq_file

def process_ecg_directory(input_dir, output_dir, sampling_rate=500):
    """Custom ECG processing function"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Find all ACQ files
    acq_files = list(input_path.rglob("*.acq"))
    print(f"Found {len(acq_files)} ACQ files")
    
    # Process each file
    for acq_file in acq_files:
        try:
            # Generate output directory structure
            rel_path = acq_file.relative_to(input_path)
            out_dir = output_path / rel_path.parent / acq_file.stem
            out_dir.mkdir(parents=True, exist_ok=True)
            
            # Convert file with grouping
            result = convert_acq_to_csv(
                acq_path=str(acq_file),
                output_path=str(out_dir),
                sampling_rate=sampling_rate,
                group_by_type=True
            )
            
            print(f"✓ {acq_file.name} -> {len(result)} CSV files")
            
            # Additional processing: parse for metadata
            parsed = parse_acq_file(str(acq_file), sampling_rate)
            print(f"  Channels: {len(parsed['channels'])}, "
                  f"Duration: {parsed['duration']:.1f}s, "
                  f"SR: {parsed['sampling_rate']}Hz")
            
        except Exception as e:
            print(f"✗ Failed to process {acq_file.name}: {e}")

# Usage
process_ecg_directory(
    input_dir="Data/raw/ECG",
    output_dir="Data/convert/ECG",
    sampling_rate=500
)
```

### Advanced: Custom Channel Type Detection

```python
from multichsync.ecg.parser import group_channels_by_type

# Parse file to get channel information
parsed = parse_acq_file("data.acq", sampling_rate=250)
channels = parsed['channels']

# Group channels by type
grouped = group_channels_by_type(channels)

print("Channel groups:")
for group_type, channel_indices in grouped.items():
    channel_names = [channels[i]['name'] for i in channel_indices]
    print(f"  {group_type}: {', '.join(channel_names)}")

# Custom channel type mapping
custom_type_map = {
    'ecg': ['ECG_100', 'ECG_101'],
    'resp': ['RESP_40', 'Respiration'],
    'custom': ['MyCustomChannel']
}

# You can extend the grouping logic in your own code
```

## Backend Libraries

The ECG module supports two backend libraries for reading ACQ files:

### 1. Bioread (Preferred)
- **Pros**: Native Python implementation, no MATLAB dependency
- **Cons**: May not support all ACQ file features
- **Installation**: `pip install bioread`

### 2. NeuroKit2
- **Pros**: Comprehensive physiological signal processing
- **Cons**: Requires MATLAB Engine for Python or ACQ file conversion
- **Installation**: `pip install neurokit2`

**Automatic fallback:** The module automatically uses bioread if available, otherwise falls back to neurokit2. If neither is available, an ImportError is raised.

## Troubleshooting

### Common Issues

**1. Backend library not installed**
```
ImportError: bioread or neurokit2 library required to read ACQ files
```
**Solution:** Install bioread: `pip install bioread`

**2. ACQ file format not supported**
```
ValueError: Unsupported ACQ file version or format
```
**Solution:** Ensure the ACQ file is from a supported Biopac system version. Try converting with neurokit2 if bioread fails.

**3. Insufficient memory for large files**
```
MemoryError: Unable to allocate array with shape ...
```
**Solution:** Process files individually or increase available memory.

**4. Permission denied when writing files**
```
PermissionError: [Errno 13] Permission denied: 'output.csv'
```
**Solution:** Check write permissions for the output directory.

**5. Channel type detection errors**
```
KeyError: 'Unknown channel type'
```
**Solution:** Check channel names in the ACQ file and adjust type detection logic if needed.

### Debugging Tips

1. **Test with a single file first:**
   ```bash
   multichsync ecg convert --acq test.acq --output ./test_output --verbose
   ```

2. **Check file information:**
   ```python
   from multichsync.ecg import parse_acq_file
   parsed = parse_acq_file("data.acq")
   print(f"Channels: {len(parsed['channels'])}")
   for ch in parsed['channels']:
       print(f"  {ch['name']}: {ch['samples']} samples at {ch['sampling_rate']} Hz")
   ```

3. **Verify dependencies:**
   ```python
   try:
       import bioread
       print(f"bioread version: {bioread.__version__}")
   except ImportError:
       print("bioread not installed")
   
   try:
       import neurokit2 as nk
       print(f"neurokit2 version: {nk.__version__}")
   except ImportError:
       print("neurokit2 not installed")
   ```

4. **Check disk space and permissions** before batch processing.

## Advanced Usage

### Custom Resampling

```python
from multichsync.ecg import parse_acq_file
import pandas as pd
from scipy import signal

# Parse ACQ file
parsed = parse_acq_file("data.acq", sampling_rate=None)  # Keep original SR
data = parsed['data']
original_sr = parsed['original_sr']
target_sr = 250  # Desired sampling rate

# Custom resampling logic
if original_sr != target_sr:
    resample_ratio = target_sr / original_sr
    num_samples = int(len(data) * resample_ratio)
    
    # Resample each channel
    resampled_data = {}
    for col in data.columns:
        if col == 'time':
            # Resample time vector
            original_time = data[col].values
            resampled_time = np.linspace(
                original_time[0], 
                original_time[-1], 
                num_samples
            )
            resampled_data[col] = resampled_time
        else:
            # Resample signal
            signal_data = data[col].values
            resampled_signal = signal.resample(signal_data, num_samples)
            resampled_data[col] = resampled_signal
    
    resampled_df = pd.DataFrame(resampled_data)
    print(f"Resampled from {original_sr}Hz to {target_sr}Hz")
```

### Quality Control Integration

While MultiChSync's quality assessment focuses on fNIRS data, ECG quality can be assessed using the converted CSV files:

```python
import pandas as pd
import neurokit2 as nk

# Load converted ECG data
ecg_df = pd.read_csv("converted/ecg_data.csv")
time = ecg_df['time'].values
ecg_signal = ecg_df['ECG_Channel'].values  # Adjust column name

# Perform ECG quality assessment using neurokit2
signals, info = nk.ecg_process(ecg_signal, sampling_rate=250)
quality = nk.ecg_quality(ecg_signal, sampling_rate=250, method="zhao2018")

print(f"ECG quality score: {quality:.3f}")
print(f"Detected heart rate: {info['ECG_Rate'].mean():.1f} BPM")
```

## Related Documentation

- [Quick Start Guide](../guides/quickstart.md) - End-to-end workflow examples
- [Installation Guide](../guides/installation.md) - Setup and dependencies
- [Marker Processing Guide](../guides/marker_processing.md) - Extracting and processing ECG markers
- [Architecture Overview](../architecture/overview.md) - System design and components

## References

- **Biopac Systems**: Biopac MP150/MP160 Data Acquisition Systems Documentation
- **Bioread**: Python library for reading Biopac ACQ files (https://github.com/uwmadison-chm/bioread)
- **NeuroKit2**: Makowski et al. (2021) NeuroKit2: A Python toolbox for neurophysiological signal processing. Behavior Research Methods.
- **ECG Signal Processing**: Sörnmo & Laguna (2005) Bioelectrical Signal Processing in Cardiac and Neurological Applications.