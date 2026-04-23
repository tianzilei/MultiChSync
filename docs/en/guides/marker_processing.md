# Marker Processing Guide

## Overview

The MultiChSync marker processing module provides a complete pipeline for extracting, cleaning, matching, and cropping multi-device marker data from fNIRS, EEG, and ECG recordings. This guide covers the **entire marker workflow** from raw data to synchronized, cropped output.

**Core Purpose**: Synchronize event markers across multiple recording devices (fNIRS, EEG, ECG) to enable time-aligned analysis of multimodal neuroimaging data.

**Key Features**:
- **Multi-format extraction**: Extract markers from Biopac (ECG), BrainVision (EEG), and Shimadzu fNIRS formats
- **Drift correction**: Estimate and correct linear clock drift between devices
- **Confidence scoring**: All matches include confidence scores (0-1) based on temporal proximity
- **Flexible algorithms**: Hungarian, Min-Cost Flow, and Sinkhorn matching algorithms
- **Integrated cropping**: Crop raw data files to synchronized time windows
- **Task name modification**: Update task names in output files for BIDS compatibility

## Supported Formats

### Input Marker Formats

| Format | Device | File Extension | Key Columns | Extraction Function |
|--------|--------|----------------|-------------|---------------------|
| **Biopac/ECG** | ECG | `.csv` | Single voltage column (0V/5V) | `extract_biopac_marker()` |
| **BrainVision** | EEG | `.vmrk` (with `.vhdr`) | Marker positions + SamplingInterval | `extract_brainvision_marker()` |
| **Shimadzu fNIRS** | fNIRS | `.csv` | "Start Time", "Protocol Type" | `extract_fnirs_marker()` |

### Output Formats

| Format | Description | File Pattern |
|--------|-------------|--------------|
| **Marker CSV** | Standardized marker times | `{device}_marker.csv` (columns: `index`, `Time(sec)`) |
| **Timeline CSV** | Consensus timeline across devices | `{prefix}_timeline.csv` |
| **Metadata JSON** | Matching parameters and results | `{prefix}_metadata.json` |
| **Quality Plots** | Visualization of matches | `{prefix}_*.png` |

## Command Line Usage

### 1. Marker Extraction

Extract markers from individual files:

```bash
# Extract from fNIRS CSV
multichsync marker extract \
  --input-file Data/raw/fnirs/sub-001_task-rest.csv \
  --output-file Data/marker/fnirs/sub-001_task-rest_marker.csv \
  --device-type fnirs

# Extract from EEG BrainVision
multichsync marker extract \
  --input-file Data/raw/eeg/sub-001_task-rest.vmrk \
  --output-file Data/marker/eeg/sub-001_task-rest_marker.csv \
  --device-type eeg

# Extract from ECG Biopac
multichsync marker extract \
  --input-file Data/raw/ecg/sub-001_task-rest.csv \
  --output-file Data/marker/ecg/sub-001_task-rest_marker.csv \
  --device-type ecg
```

**Batch extraction** from a directory:

```bash
multichsync marker batch \
  --input-dir Data/raw/fnirs \
  --output-dir Data/marker/fnirs \
  --device-type fnirs \
  --pattern "*.csv"
```

### 2. Marker Cleaning

Clean extracted marker files (remove duplicates, sort, filter):

```bash
# Clean single file
multichsync marker clean \
  --input-file Data/marker/fnirs/sub-001_task-rest_marker.csv \
  --output-file Data/marker/fnirs/sub-001_task-rest_marker_cleaned.csv \
  --min-interval 1.0 \
  --remove-start

# Clean entire directory
multichsync marker clean \
  --input-dir Data/marker/fnirs \
  --output-dir Data/marker/fnirs_cleaned \
  --min-interval 1.0 \
  --min-rows 5
```

**Cleaning Operations**:
- Remove files with fewer than `--min-rows` markers
- Sort markers by time
- Remove markers at time 0 (if `--remove-start`)
- Remove markers closer than `--min-interval` seconds
- Return status: "cleaned", "deleted_empty", "skipped_ok", or "error"

### 3. Marker Information Extraction

Extract metadata and statistics from marker files:

```bash
multichsync marker info \
  --input-dir Data/marker \
  --output-dir Data/marker/info \
  --parse-filenames
```

**Output Files**:
- `subject_XXX_marker_report.csv` - Per-subject summary
- `report_errors.csv` - Error log
- `duration_summary.csv` - Recording durations

**Filename Parsing** (with `--parse-filenames`):
1. **BIDS format**: `sub-xxx_ses-xx_task-xxx_modality`
2. **Date+Subject**: `yyyymmddnnn[_part]`
3. **Project+Subject+Segment**: `PPPP_nnn_SEG_*`

### 4. Marker Matching

Match markers across multiple devices:

```bash
multichsync marker match \
  --input-files \
    Data/marker/fnirs/sub-001_task-rest_marker.csv \
    Data/marker/eeg/sub-001_task-rest_marker.csv \
    Data/marker/ecg/sub-001_task-rest_marker.csv \
  --output-dir Data/matching/sub-001 \
  --device-names fnirs eeg ecg \
  --max-time-diff 2.0 \
  --sigma-time 0.75 \
  --drift-method theilsen \
  --match-algorithm hungarian \
  --generate-plots
```

**Advanced Matching Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--max-time-diff` | Maximum allowed time difference for matches (seconds) | 3.0 |
| `--sigma-time` | Standard deviation for confidence scoring (seconds) | 0.75 |
| `--drift-method` | Drift correction: "endpoints", "theilsen", or "none" | "theilsen" |
| `--match-algorithm` | Matching algorithm: "hungarian", "mincostflow", "sinkhorn" | "hungarian" |
| `--unmatch-cost-a` | Cost for leaving device A markers unmatched | 2.0 |
| `--unmatch-cost-b` | Cost for leaving device B markers unmatched | 2.0 |
| `--generate-plots` | Generate matching visualization plots | False |

**Output Files** (in `--output-dir`):
- `{prefix}_timeline.csv` - Consensus timeline with device columns
- `{prefix}_metadata.json` - Matching parameters and results
- `{prefix}_matches.png` - Matching visualization
- `{prefix}_drift.png` - Drift correction visualization

### 5. Timeline Cropping

Crop timelines to the shortest device duration:

```bash
multichsync marker crop \
  --timeline-csv Data/matching/sub-001/sub-001_timeline.csv \
  --metadata-json Data/matching/sub-001/sub-001_metadata.json \
  --output-dir Data/matching/sub-001/cropped
```

**Operation**: Finds the device with shortest recording duration, crops all other device timelines to match.

### 6. Raw Data Cropping

Crop original data files to matched timeline:

```bash
multichsync marker matchcrop \
  --timeline-csv Data/matching/sub-001/sub-001_timeline.csv \
  --metadata-json Data/matching/sub-001/sub-001_metadata.json \
  --reference fnirs \
  --output-dir Data/cropped/sub-001
```

**Operation**:
1. Locates original data files in `Data/convert/{device_type}/`
2. Applies device offset correction
3. Crops to reference device time range
4. Saves cropped files with time re-indexed to start at 0

### 7. Aligned Cropping with Task Name

Crop with aligned timeline and optional task name modification:

```bash
multichsync marker matchcrop-aligned \
  --json-path Data/matching/sub-001/sub-001_metadata.json \
  --start-time 10.0 \
  --end-time 300.0 \
  --taskname "resting_state" \
  --output-dir Data/cropped/aligned/sub-001
```

**Operation**:
1. Uses specified `--start-time` and `--end-time` (required), validates against consensus time range from metadata
2. Modifies task name in output files (for BIDS compatibility)
3. Applies drift correction to each device
4. Crops and saves synchronized files

## Python API Usage

### Import Structure

```python
from multichsync.marker import (
    # Extraction
    extract_fnirs_marker,
    extract_biopac_marker,
    extract_brainvision_marker,
    extract_marker_time_only,
    
    # Cleaning
    clean_marker_csv,
    clean_marker_folder,
    
    # Information extraction
    extract_marker_info,
    
    # Matching
    match_multiple_files_enhanced,
    match_by_filename,
    
    # Cropping
    matchcrop,
    matchcrop_aligned,
)

from multichsync.marker.timeline_cropper import crop_timelines_to_shortest
from multichsync.marker.matcher import (
    match_events_with_confidence,
    match_hungarian_with_confidence,
    estimate_linear_drift,
    DriftResult,
)
```

### Example Workflows

#### Complete Pipeline Example

```python
import pandas as pd
from pathlib import Path
from multichsync.marker import (
    extract_fnirs_marker,
    extract_brainvision_marker,
    match_multiple_files_enhanced,
    matchcrop,
)

# 1. Extract markers
fnirs_marker = extract_fnirs_marker(
    "Data/raw/fnirs/sub-001_task-rest.csv",
    "Data/marker/fnirs/sub-001_task-rest_marker.csv"
)

eeg_marker = extract_brainvision_marker(
    "Data/raw/eeg/sub-001_task-rest.vmrk",
    "Data/marker/eeg/sub-001_task-rest_marker.csv"
)

# 2. Match across devices
timeline, metadata = match_multiple_files_enhanced(
    input_files=[
        "Data/marker/fnirs/sub-001_task-rest_marker.csv",
        "Data/marker/eeg/sub-001_task-rest_marker.csv",
    ],
    device_names=["fnirs", "eeg"],
    output_dir="Data/matching/sub-001",
    max_time_diff_s=2.0,
    sigma_time_s=0.75,
    drift_method="theilsen",
    match_algorithm="hungarian",
    generate_plots=True,
)

# 3. Crop raw data
crop_results = matchcrop(
    timeline_csv="Data/matching/sub-001/sub-001_timeline.csv",
    metadata_json="Data/matching/sub-001/sub-001_metadata.json",
    reference="fnirs",
    output_dir="Data/cropped/sub-001",
)

print(f"Cropped {len(crop_results)} files")
```

#### Drift Correction Example

```python
from multichsync.marker.matcher import estimate_linear_drift, apply_drift_correction
import numpy as np

# Reference and device times
t_ref = np.array([1.0, 2.0, 3.0, 4.0, 5.0])  # Consensus timeline
t_dev = np.array([1.1, 2.15, 3.05, 4.2, 5.25])  # Device with drift

# Estimate drift
drift_result = estimate_linear_drift(
    t_ref, t_dev,
    method="theilsen",
    min_pairs=3,
    n_iterations=3
)

print(f"Offset: {drift_result.offset:.3f} s")
print(f"Scale: {drift_result.scale:.6f}")
print(f"R²: {drift_result.r_squared:.3f}")

# Apply correction
corrected_times = apply_drift_correction(t_ref, drift_result)
```

#### Confidence-Based Matching Example

```python
from multichsync.marker.matcher import match_hungarian_with_confidence

t1 = np.array([1.0, 2.0, 3.0, 4.0])
t2 = np.array([1.05, 2.1, 3.2, 4.15])

matches, confidences = match_hungarian_with_confidence(
    t1, t2,
    sigma_time_s=0.5,
    max_time_diff_s=1.0,
)

for (i, j), conf in zip(matches, confidences):
    print(f"Match: t1[{i}]={t1[i]:.2f}s ↔ t2[{j}]={t2[j]:.2f}s (confidence={conf:.3f})")
```

## Examples

### Example 1: Basic Two-Device Synchronization

**Scenario**: Synchronize fNIRS and EEG recordings from a resting-state experiment.

```bash
# 1. Convert raw data (prerequisite)
multichsync convert fnirs --input-dir Data/raw/fnirs --output-dir Data/convert/fnirs
multichsync convert eeg --input-dir Data/raw/eeg --output-dir Data/convert/eeg

# 2. Extract markers
multichsync marker batch --input-dir Data/convert/fnirs --output-dir Data/marker/fnirs --device-type fnirs
multichsync marker batch --input-dir Data/convert/eeg --output-dir Data/marker/eeg --device-type eeg

# 3. Match markers
multichsync marker match \
  --input-files \
    Data/marker/fnirs/sub-001_task-rest_marker.csv \
    Data/marker/eeg/sub-001_task-rest_marker.csv \
  --output-dir Data/matching/sub-001 \
  --device-names fnirs eeg \
  --drift-method theilsen

# 4. Crop data
multichsync marker matchcrop \
  --timeline-csv Data/matching/sub-001/sub-001_timeline.csv \
  --metadata-json Data/matching/sub-001/sub-001_metadata.json \
  --reference fnirs \
  --output-dir Data/cropped/sub-001
```

### Example 2: Three-Device with Quality Assessment

**Scenario**: Synchronize fNIRS, EEG, and ECG with comprehensive quality metrics.

```bash
# Complete pipeline with quality assessment
multichsync pipeline \
  --input-dir Data/raw \
  --output-dir Data/processed \
  --subjects sub-001 sub-002 \
  --tasks rest nback \
  --devices fnirs eeg ecg \
  --match-params '{"max_time_diff": 2.0, "drift_method": "theilsen"}' \
  --quality-metrics all
```

### Example 3: Batch Processing with Error Handling

```python
from pathlib import Path
from multichsync.marker import extract_marker_info
import pandas as pd

# Process all subjects
input_dir = Path("Data/marker")
output_dir = Path("Data/marker/info")

# Extract information with error handling
report_df, error_df = extract_marker_info(
    input_dir=input_dir,
    output_dir=output_dir,
    parse_filenames=True,
    continue_on_error=True,
)

# Analyze results
print(f"Processed {len(report_df)} subjects")
print(f"Errors: {len(error_df)}")

# Identify problematic files
problematic = error_df[error_df["error_type"] != "NO_MARKERS"]
if not problematic.empty:
    print("Problematic files:")
    for _, row in problematic.iterrows():
        print(f"  {row['filename']}: {row['error_message']}")
```

## Troubleshooting

### Common Issues

#### 1. "No markers found" or empty output

**Causes**:
- Voltage thresholds incorrect for ECG markers
- Wrong device type specified
- File encoding issues (especially fNIRS CSV files)
- Marker column names don't match expected patterns

**Solutions**:
```bash
# Check file content
head -n 5 Data/raw/ecg/sub-001.csv

# Try different encodings for fNIRS
multichsync marker extract \
  --input-file Data/raw/fnirs/sub-001.csv \
  --encoding utf-8-sig  # or gbk, latin1

# Manually inspect marker positions
python -c "
import pandas as pd
df = pd.read_csv('Data/raw/fnirs/sub-001.csv')
print(df.columns)
print(df[['Start Time', 'Protocol Type']].head(10))
"
```

#### 2. Poor matching quality (low confidence scores)

**Causes**:
- Large clock drift between devices
- Missing markers in one device
- Incorrect sampling rate assumptions
- Excessive noise in marker signals

**Solutions**:
```bash
# Enable drift correction
multichsync marker match --drift-method theilsen

# Increase maximum time difference
multichsync marker match --max-time-diff 3.0

# Use more robust matching algorithm
multichsync marker match --match-algorithm mincostflow

# Generate and inspect plots
multichsync marker match --generate-plots
```

#### 3. "File not found" during cropping

**Causes**:
- Original data files moved from `Data/convert/` directory
- Filename patterns don't match between marker and data files
- Device type incorrectly inferred

**Solutions**:
```bash
# Check data path structure
ls -la Data/convert/fnirs/

# Verify filename matching
python -c "
from multichsync.marker.matchcrop import find_raw_data_file
from pathlib import Path

marker_file = Path('Data/marker/fnirs/sub-001_marker.csv')
data_file = find_raw_data_file(marker_file, 'fnirs')
print(f'Found: {data_file}')
"

# Manually specify data directory
multichsync marker matchcrop \
  --data-dir /alternative/path/to/convert \
  --timeline-csv ...
```

#### 4. Memory issues with large files

**Causes**:
- Very long recordings (>1 hour)
- High sampling rates (>1000 Hz)
- Many marker events (>1000)

**Solutions**:
```bash
# Clean markers first to reduce count
multichsync marker clean --min-interval 2.0

# Use simpler matching algorithm
multichsync marker match --match-algorithm hungarian

# Process in chunks
multichsync marker match \
  --chunk-size 100 \
  --overlap 10
```

### Error Messages and Solutions

| Error Message | Likely Cause | Solution |
|---------------|--------------|----------|
| `"Column 'reference_time' not found"` | Wrong column name in marker CSV | Check column names, use `--time-col` option |
| `"No valid markers found after cleaning"` | All markers filtered out | Adjust `--min-interval` or `--min-rows` |
| `"Drift estimation failed: insufficient pairs"` | Too few matching markers | Check marker extraction, reduce `--max-time-diff` |
| `"Cannot locate raw data file"` | Data file missing or renamed | Verify `Data/convert/` structure |
| `"Confidence matrix singular"` | Identical timestamps | Clean markers with `--min-interval` |

## Related Documentation

- **[Installation Guide](installation.md)** - System requirements and installation
- **[Quickstart Guide](quickstart.md)** - End-to-end workflow example  
- **[fNIRS Conversion Guide](fnirs_conversion.md)** - Shimadzu to SNIRF conversion
- **[EEG Conversion Guide](eeg_conversion.md)** - Curry/EEGLAB to BrainVision conversion
- **[ECG Conversion Guide](ecg_conversion.md)** - Biopac ACQ to CSV conversion
- **[Quality Assessment Guide](quality_assessment.md)** - Signal quality metrics
- **[Event Matching Analysis](../event_matching_analysis.md)** - Algorithm details (legacy)

## Best Practices

### 1. Data Organization

```
Data/
├── raw/                    # Original recordings
│   ├── fnirs/             # Shimadzu TXT files
│   ├── eeg/               # Curry/EEGLAB files  
│   └── ecg/               # Biopac ACQ files
├── convert/               # Converted formats
│   ├── fnirs/             # SNIRF files
│   ├── eeg/               # BrainVision files
│   └── ecg/               # CSV files
├── marker/                # Extracted markers
│   ├── fnirs/             # fNIRS marker CSV
│   ├── eeg/               # EEG marker CSV
│   └── ecg/               # ECG marker CSV
├── matching/              # Matching results
│   └── {subject}/         # Per-subject matching
└── cropped/               # Synchronized, cropped data
    └── {subject}/         # Final analysis-ready data
```

### 2. Naming Conventions

- Use BIDS-style naming: `sub-XXX_ses-YY_task-ZZZ_{modality}.ext`
- Include subject, session, and task identifiers
- Maintain consistent naming across modalities
- Use underscores instead of spaces

### 3. Quality Control Steps

1. **Pre-matching**: Verify marker counts per device (>5 markers recommended)
2. **Post-matching**: Check confidence scores (>0.7 recommended)
3. **Visual inspection**: Review generated plots for alignment quality
4. **Duration verification**: Ensure cropped files have expected durations

### 4. Performance Optimization

- **Batch processing**: Use `marker batch` for large datasets
- **Parallel processing**: Run multiple subjects concurrently
- **Memory management**: Clean markers before matching for large recordings
- **Caching**: Reuse matching results when parameters unchanged

## API Reference

### Core Functions

#### `extract_fnirs_marker(input_csv, output_csv, encoding='auto')`
Extract markers from Shimadzu fNIRS CSV files.

**Parameters**:
- `input_csv`: Path to fNIRS CSV file
- `output_csv`: Path for output marker CSV
- `encoding`: File encoding ('gbk', 'utf-8-sig', 'latin1', or 'auto')

**Returns**: `pd.DataFrame` with columns: `index`, `Time(sec)`

#### `match_multiple_files_enhanced(input_files, device_names, output_dir, **kwargs)`
Match markers across multiple devices with drift correction.

**Parameters**:
- `input_files`: List of marker CSV file paths
- `device_names`: Corresponding device names
- `output_dir`: Directory for output files
- `**kwargs`: Matching parameters (see CLI options)

**Returns**: Tuple of `(timeline_df, metadata_dict)`

#### `matchcrop(timeline_csv, metadata_json, reference, output_dir)`
Crop raw data files to matched timeline.

**Parameters**:
- `timeline_csv`: Path to timeline CSV
- `metadata_json`: Path to metadata JSON
- `reference`: Reference device name
- `output_dir`: Directory for cropped files

**Returns**: Dictionary of cropping results

### Data Classes

#### `DriftResult`
Stores drift correction parameters.

**Attributes**:
- `offset`: Time offset (seconds)
- `scale`: Clock drift scale factor
- `r_squared`: Goodness of fit (0-1)
- `n_matches`: Number of matched pairs used
- `method`: Estimation method used

#### `DeviceInfo`
Stores device metadata and timestamps.

**Attributes**:
- `name`: Device identifier
- `marker_times`: Array of marker timestamps
- `time_range`: `(start, end)` time range
- `sampling_rate`: Sampling rate (Hz)
- `file_path`: Path to original data file

## Version History

- **v1.0** (2024): Initial release with basic matching
- **v1.1** (2024): Added drift correction and confidence scoring
- **v1.2** (2024): Enhanced cropping with task name modification
- **v1.3** (2025): Added batch processing and error handling

## Support

For issues and questions:
1. Check the [troubleshooting](#troubleshooting) section
2. Review example workflows in [Examples](#examples)
3. Submit an issue on GitHub with:
   - Error messages and traceback
   - Sample data (if possible)
   - Command used and parameters
