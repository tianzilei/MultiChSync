# API Reference

## Overview

This API reference provides detailed documentation for the MultiChSync Python interface. For command-line usage, see the [Guides](../guides/).

**Note**: This reference is manually maintained. For complete, up-to-date function signatures, refer to the source code or use Python's built-in `help()` function.

## Module Structure

```
multichsync/
├── __init__.py           # Top-level imports
├── cli.py                # Command-line interface
├── fnirs/                # fNIRS conversion module
│   ├── __init__.py
│   ├── converter.py
│   ├── parser.py
│   └── writer.py
├── eeg/                  # EEG conversion module
│   ├── __init__.py
│   ├── converter.py
│   └── parser.py
├── ecg/                  # ECG conversion module
│   ├── __init__.py
│   ├── converter.py
│   └── parser.py
├── marker/               # Marker processing module
│   ├── __init__.py
│   ├── extractor.py
│   ├── matcher.py
│   ├── timeline_cropper.py
│   ├── matchcrop.py
│   ├── matchcrop_aligned.py
│   └── info_extractor.py
└── quality/              # Quality assessment module
    ├── __init__.py
    └── assessor.py
```

## Top-Level Imports

The main package exports commonly used functions from each module:

```python
# fNIRS conversion
from multichsync.fnirs import convert_fnirs_to_snirf, batch_convert_fnirs

# EEG conversion  
from multichsync.eeg import convert_eeg_format, batch_convert_eeg

# ECG conversion
from multichsync.ecg import convert_acq_to_csv, batch_convert_ecg

# Marker processing
from multichsync.marker import (
    extract_fnirs_marker,
    extract_brainvision_marker,
    extract_biopac_marker,
    clean_marker_csv,
    match_multiple_files_enhanced,
    matchcrop,
    matchcrop_aligned,
    extract_marker_info,
)

# Quality assessment
from multichsync.quality import (
    process_one_snirf,
    batch_process_snirf_folder,
    process_one_snirf_with_metadata,
    assess_hb_quality_comprehensive,
    compute_signal_metrics,
    compute_task_metrics,
    compute_resting_metrics,
)
```

## fNIRS Module

### `multichsync.fnirs`

**Purpose**: Convert Shimadzu/NIRS-SPM TXT files to SNIRF v1.1 format.

#### Key Functions

##### `convert_fnirs_to_snirf(txt_path, src_coords_csv, det_coords_csv, output_path, **kwargs)`
Convert single fNIRS TXT file to SNIRF format.

**Parameters**:
- `txt_path`: Path to Shimadzu TXT file
- `src_coords_csv`: Path to source coordinates CSV
- `det_coords_csv`: Path to detector coordinates CSV  
- `output_path`: Output SNIRF file path
- `**kwargs`: Additional conversion options

**Returns**: Path to created SNIRF file

**Example**:
```python
from multichsync.fnirs import convert_fnirs_to_snirf

output = convert_fnirs_to_snirf(
    txt_path="data.TXT",
    src_coords_csv="sources.csv",
    det_coords_csv="detectors.csv",
    output_path="output.snirf",
    measurement_date="2024-01-01",
)
```

##### `batch_convert_fnirs(input_dir, output_dir, src_coords_csv, det_coords_csv, **kwargs)`
Batch convert multiple TXT files.

**Parameters**:
- `input_dir`: Directory containing TXT files
- `output_dir`: Output directory for SNIRF files
- `src_coords_csv`, `det_coords_csv`: Coordinate files
- `**kwargs`: Conversion options passed to `convert_fnirs_to_snirf`

**Returns**: List of conversion results

**See also**: [fNIRS Conversion Guide](../guides/fnirs_conversion.md)

## EEG Module

### `multichsync.eeg`

**Purpose**: Convert EEG data between formats (Curry, EEGLAB, BrainVision, EDF).

#### Key Functions

##### `convert_eeg_format(input_path, output_path, input_format=None, output_format='BrainVision', **kwargs)`
Convert single EEG file between formats.

**Parameters**:
- `input_path`: Path to input EEG file
- `output_path`: Path for output file
- `input_format`: Input format ('Curry', 'EEGLAB', 'auto')
- `output_format`: Output format ('BrainVision', 'EEGLAB', 'EDF')
- `**kwargs`: Conversion options

**Returns**: Dictionary with conversion results

**Example**:
```python
from multichsync.eeg import convert_eeg_format

result = convert_eeg_format(
    input_path="data.set",
    output_path="data.vhdr",
    input_format="EEGLAB",
    output_format="BrainVision",
    montage="standard_1020",
)
```

##### `batch_convert_eeg(input_dir, output_dir, input_format=None, output_format='BrainVision', **kwargs)`
Batch convert EEG files in directory.

**See also**: [EEG Conversion Guide](../guides/eeg_conversion.md)

## ECG Module

### `multichsync.ecg`

**Purpose**: Convert Biopac ACQ files to CSV format.

#### Key Functions

##### `convert_acq_to_csv(acq_path, output_path=None, grouped=True, **kwargs)`
Convert Biopac ACQ file to CSV.

**Parameters**:
- `acq_path`: Path to .acq file
- `output_path`: Output directory or file path
- `grouped`: If True, create separate CSV per channel group
- `**kwargs`: Conversion options

**Returns**: Dictionary with conversion results

**Example**:
```python
from multichsync.ecg import convert_acq_to_csv

result = convert_acq_to_csv(
    acq_path="recording.acq",
    output_path="./converted",
    grouped=True,
    sampling_rate=1000,
)
```

##### `batch_convert_ecg(input_dir, output_dir, **kwargs)`
Batch convert ACQ files in directory.

**See also**: [ECG Conversion Guide](../guides/ecg_conversion.md)

## Marker Module

### `multichsync.marker`

**Purpose**: Extract, clean, match, and crop event markers across multiple devices.

#### Extraction Functions

##### `extract_fnirs_marker(input_csv, output_csv, encoding='auto')`
Extract markers from Shimadzu fNIRS CSV files.

##### `extract_brainvision_marker(vmrk_path, output_csv, vhdr_path=None)`
Extract markers from BrainVision .vmrk files.

##### `extract_biopac_marker(input_csv, output_csv, fs=500, tolerance=0.2)`
Extract markers from Biopac/ECG CSV files.

#### Cleaning Functions

##### `clean_marker_csv(csv_path, out_path=None, **kwargs)`
Clean individual marker CSV file.

##### `clean_marker_folder(input_dir, output_dir=None, **kwargs)`
Batch clean marker files in directory.

#### Matching Functions

##### `match_multiple_files_enhanced(input_files, device_names, output_dir, **kwargs)`
Match markers across multiple devices with drift correction.

**Parameters**:
- `input_files`: List of marker CSV file paths
- `device_names`: Corresponding device names
- `output_dir`: Directory for output files
- `**kwargs`: Matching parameters:
  - `max_time_diff_s`: Maximum allowed time difference (default: 3.0)
  - `sigma_time_s`: Confidence scoring standard deviation (default: 0.75)
  - `drift_method`: "endpoints", "theilsen", or "none" (default: "theilsen")
  - `match_algorithm`: "hungarian", "mincostflow", "sinkhorn" (default: "hungarian")
  - `generate_plots`: Generate visualization plots (default: False)

**Returns**: Tuple of `(timeline_df, metadata_dict)`

#### Cropping Functions

##### `matchcrop(timeline_csv, metadata_json, reference, output_dir)`
Crop raw data files to matched timeline.

##### `matchcrop_aligned(json_path, start_time=None, end_time=None, taskname=None, output_dir=None)`
Crop with aligned timeline and task name modification.

#### Information Extraction

##### `extract_marker_info(input_dir, output_dir, **kwargs)`
Extract metadata and statistics from marker files.

**See also**: [Marker Processing Guide](../guides/marker_processing.md)

## Quality Module

### `multichsync.quality`

**Purpose**: Automated fNIRS data quality assessment for SNIRF files.

#### Processing Functions

##### `process_one_snirf(snirf_path, out_dir, **kwargs)`
Process single SNIRF file for quality assessment.

##### `batch_process_snirf_folder(in_dir, out_dir, **kwargs)`
Batch process SNIRF files in directory.

##### `process_one_snirf_with_metadata(snirf_path, out_dir, **kwargs)`
Process single file with metadata writing.

##### `batch_process_snirf_folder_with_metadata(in_dir, out_dir, **kwargs)`
Batch process with metadata writing.

#### Assessment Functions

##### `assess_hb_quality_comprehensive(raw, fs, paradigm="resting", **kwargs)`
Comprehensive HbO/HbR quality assessment.

**Parameters**:
- `raw`: MNE Raw object or data array
- `fs`: Sampling frequency (Hz)
- `paradigm`: "resting" or "task"
- `events`: Event dictionary for task paradigm
- `apply_hard_gating`: Apply automatic bad channel detection

**Returns**: Tuple of `(quality_df, bad_channels, summary_dict)`

##### `compute_signal_metrics(x, fs, **kwargs)`
Compute signal-level quality metrics.

##### `compute_hbo_hbr_pair_metrics(hbo, hbr, fs, **kwargs)`
Compute HbO-HbR pair metrics.

##### `compute_task_metrics(hbo_data, hbr_data, fs, events, **kwargs)`
Compute task-based metrics (CNR, GoodEventFraction).

##### `compute_resting_metrics(hbo_data, hbr_data, fs, **kwargs)`
Compute resting-state metrics (split-half reliability).

**See also**: [Quality Assessment Guide](../guides/quality_assessment.md)

## Data Classes

### `DriftResult` (`multichsync.marker.matcher`)
Stores drift correction parameters.

**Attributes**:
- `offset`: Time offset (seconds)
- `scale`: Clock drift scale factor
- `r_squared`: Goodness of fit (0-1)
- `n_matches`: Number of matched pairs used
- `method`: Estimation method used

### `DeviceInfo` (`multichsync.marker.matcher`)
Stores device metadata and timestamps.

**Attributes**:
- `name`: Device identifier
- `marker_times`: Array of marker timestamps
- `time_range`: `(start, end)` time range
- `sampling_rate`: Sampling rate (Hz)
- `file_path`: Path to original data file

## Command-Line Interface

The CLI is implemented in `multichsync.cli` and provides comprehensive command-line access to all functionality.

### Module Structure

```bash
multichsync <module> <command> [options]
```

### Available Modules and Commands

| Module | Commands | Description |
|--------|----------|-------------|
| `fnirs` | `convert`, `batch` | fNIRS conversion |
| `eeg` | `convert`, `batch` | EEG conversion |
| `ecg` | `convert`, `batch` | ECG conversion |
| `marker` | `extract`, `batch`, `clean`, `info`, `match`, `crop`, `matchcrop`, `matchcrop-aligned` | Marker processing |
| `quality` | `assess`, `batch`, `assess-with-metadata`, `batch-with-metadata`, `resting-metrics` | Quality assessment |

### CLI Examples

```bash
# See CLI help
multichsync --help
multichsync fnirs --help
multichsync marker match --help

# Full pipeline example
multichsync fnirs batch --input-dir raw/fnirs --output-dir convert/fnirs
multichsync marker batch --input-dir convert/fnirs --device-type fnirs
multichsync marker match --input-files marker/*.csv --output-dir matching
multichsync quality batch --input-dir convert/fnirs --output-dir quality
```

## Error Handling

Most functions raise exceptions for invalid inputs or processing errors:

### Common Exceptions

| Exception | Raised When |
|-----------|-------------|
| `FileNotFoundError` | Input file doesn't exist |
| `ValueError` | Invalid parameter values |
| `ImportError` | Required dependency missing |
| `RuntimeError` | Processing failure |

### Error Recovery

```python
from multichsync.fnirs import convert_fnirs_to_snirf

try:
    result = convert_fnirs_to_snirf("data.TXT", "sources.csv", "detectors.csv", "out.snirf")
except FileNotFoundError as e:
    print(f"File not found: {e}")
except ValueError as e:
    print(f"Invalid parameter: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Type Hints

The codebase uses Python type hints for better IDE support and documentation:

```python
from typing import Union, List, Dict, Tuple, Optional
from pathlib import Path

def convert_fnirs_to_snirf(
    txt_path: Union[str, Path],
    src_coords_csv: Union[str, Path],
    det_coords_csv: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    ...
```

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test module
pytest tests/unit/test_marker_matcher.py

# Run with coverage
pytest --cov=multichsync tests/
```

### Test Structure

- `tests/unit/`: Unit tests for individual functions
- `tests/integration/`: Integration tests for workflows
- `tests/data/`: Test data files

## Versioning

The API follows semantic versioning. Breaking changes will increment the major version.

**Current**: v1.x

**Backward Compatibility**:
- v1.x: Stable API, new features may be added
- Future v2.x: May include breaking changes

## Support

For API questions and issues:
1. Check the relevant [guide](../guides/)
2. Examine function docstrings: `help(multichsync.fnirs.convert_fnirs_to_snirf)`
3. Review source code
4. Submit an issue on GitHub

## Related Documentation

- [Installation Guide](../guides/installation.md) - Setup and dependencies
- [Quickstart Guide](../guides/quickstart.md) - End-to-end examples
- [Architecture Overview](../architecture/overview.md) - System design
- [Signal-Level Quality Metrics](../fnirs_signal_level_qc_metrics.md) - Detailed metric specifications
