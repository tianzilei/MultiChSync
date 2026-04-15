# Quality Assessment Guide

## Overview

The MultiChSync quality assessment module provides automated evaluation of fNIRS data quality for SNIRF files. It implements a comprehensive signal-level quality assessment framework based on established metrics for hemoglobin signals (HbO and HbR).

**Core Purpose**: Automatically detect bad channels, compute signal quality metrics, and embed quality metadata in SNIRF files for reproducible quality control.

**Key Features**:
- **Comprehensive metrics**: 14+ signal-level quality indicators per channel
- **Dual assessment**: Pre-filter and post-filter quality evaluation
- **Paradigm-specific metrics**: Task-based CNR and resting-state reliability
- **Metadata embedding**: Write quality scores and bad channel lists directly to SNIRF files
- **Batch processing**: Process entire folders with automatic error handling
- **Flexible filtering**: Bandpass filtering with optional TDDR motion artifact correction

## Quality Assessment Framework

### Signal-Level Metrics

Based on the comprehensive specification in [`fnirs_signal_level_qc_metrics.md`](../fnirs_signal_level_qc_metrics.md), the quality module computes the following metrics for each HbO and HbR channel:

#### 1. Basic Signal Metrics

| Metric | Formula | Description |
|--------|---------|-------------|
| **Near-Flatline** | `1 if max(abs(diff(x))) < τ_flat` | Detects flat or dead channels |
| **Range** | `max(x) - min(x)` | Signal amplitude range |
| **Coefficient of Variation** | `σ(x) / (|μ(x)| + ε_μ)` | Normalized variability |
| **tSNR** | `|μ(x)| / (σ(x) + ε_σ)` | Temporal signal-to-noise ratio |
| **Robust Derivative Index** | `median(|dx|) / (MAD(x) + ε_MAD)` | Signal change relative to baseline variability |
| **Baseline Drift** | `|slope| / (σ(x) + ε_σ)` | Linear drift relative to signal variability |
| **Spectral Entropy** | `-Σ(P(f) log P(f)) / log(N)` | Frequency distribution uniformity |

#### 2. Physiological Band Power Ratios

| Band | Frequency Range | Purpose |
|------|----------------|---------|
| **Low Frequency** | 0.01-0.08 Hz | Mayer wave and vasomotion |
| **Mayer Band** | 0.08-0.15 Hz | Mayer waves (∼0.1 Hz) |
| **Respiration Band** | 0.15-0.40 Hz | Respiration-related oscillations |

Metrics:
- **Mayer Ratio**: `P_mayer / (P_low + ε)`
- **Respiration Ratio**: `P_resp / (P_low + ε)`

#### 3. HbO-HbR Pair Metrics

| Metric | Description | Expected Range |
|--------|-------------|----------------|
| **Correlation** | Pearson correlation between HbO and HbR | Negative (typical: -0.3 to -0.8) |
| **Variance Ratio** | `σ(HbO) / (σ(HbR) + ε)` | ~2-4 (HbO typically more variable) |
| **Derivative Correlation** | Correlation of first differences | Negative |

#### 4. Paradigm-Specific Metrics

**Task Paradigm**:
- **CNR (Contrast-to-Noise Ratio)**: `|μ_baseline - μ_response| / √(σ²_baseline + σ²_response)`
- **Good Event Fraction**: Percentage of events passing quality checks

**Resting-State Paradigm**:
- **Split-Half Reliability**: Correlation of functional connectivity matrices between temporal halves
- **Retained Duration Fraction**: Usable data after bad segment removal

### Quality Scoring System

Each metric is mapped to a **quality score (0-1)** using anchor-point based scoring:

| Quality Tier | Score Range | Description |
|--------------|-------------|-------------|
| **Excellent** | 0.8-1.0 | High-quality signal, minimal artifacts |
| **Good** | 0.6-0.8 | Acceptable quality for analysis |
| **Fair** | 0.4-0.6 | Moderate artifacts, use with caution |
| **Poor** | 0.0-0.4 | Severe artifacts, consider exclusion |

**Hard Gating Rules**: Channels failing minimum thresholds are automatically marked as bad:
- Near-flatline detection
- Extremely low tSNR (< 1.0)
- Excessive baseline drift
- Abnormal HbO-HbR correlation (> 0 or < -0.95)

## Command Line Usage

### 1. Single File Quality Assessment

Basic quality assessment with metadata writing:

```bash
multichsync quality assess \
  --input sub-001_task-rest.snirf \
  --output-dir ./quality \
  --l-freq 0.01 \
  --h-freq 0.2 \
  --resample-sfreq 4.0 \
  --paradigm resting
```

**Output Files**:
- `sub-001_task-rest_prefilter_detail.csv` - Pre-filter channel metrics
- `sub-001_task-rest_postfilter_detail.csv` - Post-filter channel metrics  
- `sub-001_task-rest_summary.json` - Summary statistics
- `sub-001_task-rest_comprehensive_detail.csv` - Comprehensive metrics (if enabled)
- `sub-001_task-rest_comprehensive_summary.json` - Comprehensive summary
- `sub-001_task-rest_processed.snirf` - SNIRF with embedded metadata
- `sub-001_task-rest_metadata_report.csv` - Single-line CSV report

### 2. Batch Processing

Process all SNIRF files in a directory:

```bash
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2 \
  --resample-sfreq 4.0 \
  --comprehensive \
  --paradigm resting \
  --write-metadata
```

**Batch Output Files**:
- `snirf_batch_summary.csv` - Aggregated results for all files
- `snirf_batch_failed.csv` - List of files that failed processing
- Per-file outputs in subdirectories

### 3. Assessment with Metadata Writing

Write quality metadata directly to SNIRF files:

```bash
multichsync quality assess-with-metadata \
  --input sub-001_task-rest.snirf \
  --output-dir ./quality \
  --no-tddr \
  --paradigm task
```

**Embedded SNIRF Metadata** (`/nirs/metaDataTags`):
- `bad_chs`: Semicolon-separated list of bad channels (e.g., "S1_D1 hbo; S2_D3 hbr")
- `overall_score`: Overall quality score (0-1)
- `channel_scores_json`: JSON string with per-channel scores
- `processing_date`: ISO format timestamp
- `processing_tool`: "MultiChSync Quality Module"

### 4. Resting-State Metrics Computation

Compute resting-state specific metrics:

```bash
multichsync quality resting-metrics \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality/resting_metrics \
  --l-freq 0.01 \
  --h-freq 0.2
```

**Resting Metrics Output**:
- Per-file JSON with split-half reliability and retained duration
- Aggregated CSV summary across files

### 5. Advanced Options

```bash
multichsync quality assess \
  --input data.snirf \
  --output-dir ./quality \
  --l-freq 0.01 \           # Low cutoff frequency (Hz)
  --h-freq 0.2 \            # High cutoff frequency (Hz)
  --resample-sfreq 4.0 \    # Resample to 4 Hz (0 = disable)
  --no-tddr \               # Disable TDDR motion correction
  --no-comprehensive \      # Disable comprehensive metrics
  --no-metadata \           # Disable metadata writing
  --paradigm task \         # "task" or "resting"
  --overwrite \             # Overwrite existing outputs
  --verbose                 # Detailed progress output
```

## Python API Usage

### Import Structure

```python
from multichsync.quality import (
    # High-level processing
    process_one_snirf,
    batch_process_snirf_folder,
    process_one_snirf_with_metadata,
    batch_process_snirf_folder_with_metadata,
    batch_compute_resting_metrics,
    
    # Core assessment functions
    assess_hb_quality,
    assess_hb_quality_comprehensive,
    compute_hb_snr,
    compute_signal_metrics,
    compute_hbo_hbr_pair_metrics,
    compute_task_metrics,
    compute_resting_metrics,
    
    # Utility functions
    smart_filter_raw,
    pair_hbo_hbr_channels,
    expand_fnirs_bads_to_pairs,
)
```

### Example Workflows

#### Complete Quality Assessment Pipeline

```python
from multichsync.quality import process_one_snirf_with_metadata

# Process single file with full metrics and metadata
summary = process_one_snirf_with_metadata(
    snirf_path="Data/convert/fnirs/sub-001_task-rest.snirf",
    out_dir="Data/quality/sub-001",
    l_freq=0.01,           # High-pass cutoff
    h_freq=0.2,            # Low-pass cutoff
    resample_sfreq=4.0,    # Resample to 4 Hz
    apply_tddr=True,       # Apply TDDR motion correction
    comprehensive=True,    # Enable comprehensive metrics
    paradigm="resting",    # Paradigm type
)

print(f"Overall quality score: {summary['overall_score']:.3f}")
print(f"Bad channels: {summary.get('bad_channels', [])}")
print(f"Retained duration: {summary.get('retained_duration_fraction', 1.0):.1%}")
```

#### Custom Signal Metrics Computation

```python
import numpy as np
from multichsync.quality import compute_signal_metrics, compute_hbo_hbr_pair_metrics

# Simulated HbO and HbR data
fs = 10.0  # 10 Hz sampling rate
n_samples = 1000
hbo = np.random.randn(n_samples) * 0.5 + 10.0  # HbO with mean ~10 μM
hbr = -0.3 * hbo + np.random.randn(n_samples) * 0.2 - 2.0  # HbR anti-correlated

# Compute per-channel metrics
hbo_metrics = compute_signal_metrics(hbo, fs)
hbr_metrics = compute_signal_metrics(hbr, fs)

print(f"HbO tSNR: {hbo_metrics['tsnr']:.2f}")
print(f"HbR tSNR: {hbr_metrics['tsnr']:.2f}")
print(f"HbO RDI: {hbo_metrics['rdi']:.3f}")
print(f"HbO spectral entropy: {hbo_metrics['spectral_entropy']:.3f}")

# Compute pair metrics
pair_metrics = compute_hbo_hbr_pair_metrics(hbo, hbr, fs)
print(f"HbO-HbR correlation: {pair_metrics['hbo_hbr_corr']:.3f}")
print(f"Variance ratio: {pair_metrics['var_ratio']:.3f}")
```

#### Task-Based Quality Assessment

```python
from multichsync.quality import compute_task_metrics

# Task event structure
events = {
    'onsets': [30.0, 90.0, 150.0, 210.0],  # Event onset times (seconds)
    'durations': [10.0, 10.0, 10.0, 10.0],  # Event durations
    'conditions': ['task', 'task', 'task', 'task'],
    'artifacts': [(25.0, 28.0)],  # Artifact intervals to exclude
}

# Compute task metrics
task_results = compute_task_metrics(
    hbo_data=hbo_data,      # Shape: (n_channels, n_times) or (n_times,)
    hbr_data=hbr_data,
    fs=fs,
    events=events,
    baseline_duration=5.0,   # Baseline period before each event
    response_duration=10.0,  # Response period after onset
)

print(f"Median CNR (HbO): {task_results['median_cnr_hbo']:.2f}")
print(f"Median CNR (HbR): {task_results['median_cnr_hbr']:.2f}")
print(f"Good event fraction: {task_results['good_event_fraction']:.1%}")
```

#### Batch Processing with Error Handling

```python
from pathlib import Path
from multichsync.quality import batch_process_snirf_folder_with_metadata

input_dir = Path("Data/convert/fnirs")
output_dir = Path("Data/quality")

# Process all SNIRF files in directory
summary_df, failed_files = batch_process_snirf_folder_with_metadata(
    in_dir=input_dir,
    out_dir=output_dir,
    l_freq=0.01,
    h_freq=0.2,
    resample_sfreq=4.0,
    apply_tddr=True,
    comprehensive=True,
    paradigm="resting",
    continue_on_error=True,  # Continue if some files fail
)

print(f"Successfully processed: {len(summary_df)} files")
print(f"Failed: {len(failed_files)} files")

if failed_files:
    print("Failed files:")
    for fail in failed_files:
        print(f"  {fail['file']}: {fail['error']}")
```

## Examples

### Example 1: Standard Resting-State Assessment

**Scenario**: Assess resting-state fNIRS data quality with comprehensive metrics.

```bash
# Single file assessment
multichsync quality assess \
  --input Data/convert/fnirs/sub-001_ses-01_task-rest_run-01.snirf \
  --output-dir Data/quality/sub-001 \
  --l-freq 0.01 \
  --h-freq 0.2 \
  --resample-sfreq 4.0 \
  --paradigm resting \
  --write-metadata

# Batch processing for multiple subjects
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2 \
  --paradigm resting \
  --overwrite
```

**Expected Outputs**:
- Per-subject quality reports in `Data/quality/sub-*/`
- Batch summary: `Data/quality/snirf_batch_summary.csv`
- Processed SNIRF files with embedded quality metadata

### Example 2: Task-Based Assessment with Event Information

**Scenario**: Assess task-based fNIRS data with event timing for CNR computation.

```python
from multichsync.quality import process_one_snirf
import json

# Define task events
events = {
    "onsets": [30.0, 90.0, 150.0, 210.0, 270.0],
    "durations": [10.0] * 5,
    "conditions": ["nback"] * 5,
    "artifacts": []  # No known artifacts
}

# Save events to JSON file
with open("events.json", "w") as f:
    json.dump(events, f)

# Run quality assessment with event information
summary = process_one_snirf(
    snirf_path="sub-001_task-nback.snirf",
    out_dir="./quality",
    l_freq=0.01,
    h_freq=0.2,
    paradigm="task",
    events=events,  # Pass events directly
    write_metadata=True,
)

print(f"Task CNR (HbO): {summary.get('median_cnr_hbo', 'N/A')}")
print(f"Good events: {summary.get('good_event_fraction', 'N/A'):.1%}")
```

### Example 3: Integration with Conversion Pipeline

**Scenario**: Complete pipeline from raw data to quality-assessed output.

```bash
# 1. Convert fNIRS data
multichsync fnirs batch \
  --input-dir Data/raw/fnirs \
  --output-dir Data/convert/fnirs \
  --src-coords coords/sources.csv \
  --det-coords coords/detectors.csv

# 2. Quality assessment
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2 \
  --paradigm resting \
  --write-metadata

# 3. Generate summary report
python -c "
import pandas as pd
df = pd.read_csv('Data/quality/snirf_batch_summary.csv')
print(f'Total files: {len(df)}')
print(f'Mean overall score: {df[\"overall_score\"].mean():.3f}')
print(f'Files with score < 0.6: {(df[\"overall_score\"] < 0.6).sum()}')
"
```

## Troubleshooting

### Common Issues

#### 1. "No MNE module found" or import errors

**Cause**: MNE-Python or mne-nirs not installed.

**Solution**:
```bash
# Install required packages
pip install mne mne-nirs

# Or install all dependencies
pip install -r requirements.txt

# Verify installation
python -c "import mne; import mne_nirs; print('MNE version:', mne.__version__)"
```

#### 2. "Cannot write metadata to SNIRF file"

**Cause**: File permissions or corrupted SNIRF file.

**Solutions**:
```bash
# Check file permissions
ls -la data.snirf

# Try without metadata writing first
multichsync quality assess --input data.snirf --no-metadata

# Check if file is valid SNIRF
python -c "
import h5py
try:
    with h5py.File('data.snirf', 'r') as f:
        print('Valid SNIRF file')
        print('Format version:', f.attrs.get('format_version', 'unknown'))
except Exception as e:
    print(f'Error: {e}')
"
```

#### 3. Unrealistically high or low quality scores

**Cause**: Incorrect paradigm specification or filtering parameters.

**Solutions**:
```bash
# Check paradigm matches data type
multichsync quality assess --paradigm resting  # for resting-state
multichsync quality assess --paradigm task     # for task data

# Adjust filter ranges
multichsync quality assess --l-freq 0.01 --h-freq 0.2  # standard fNIRS band

# Disable TDDR for very clean data
multichsync quality assess --no-tddr

# Examine intermediate files
cat sub-001_prefilter_detail.csv | head -5
cat sub-001_postfilter_detail.csv | head -5
```

#### 4. Memory errors with large files

**Cause**: High sampling rates or long recordings.

**Solutions**:
```bash
# Resample to lower frequency
multichsync quality assess --resample-sfreq 2.0

# Disable comprehensive metrics
multichsync quality assess --no-comprehensive

# Process in smaller chunks (Python API only)
from multichsync.quality import process_one_snirf
summary = process_one_snirf(..., chunk_size=1000)
```

#### 5. "No HbO/HbR channels found"

**Cause**: Channel naming doesn't match expected patterns.

**Solutions**:
```bash
# Check channel names in SNIRF file
python -c "
import mne
raw = mne.io.read_raw_snirf('data.snirf')
print('Channels:', raw.ch_names[:10])
print('Channel types:', raw.get_channel_types()[:10])
"

# Rename channels if needed (Python API)
import mne
raw = mne.io.read_raw_snirf('data.snirf')
raw.rename_channels({old: new for old, new in channel_mapping.items()})
raw.save('data_renamed.snirf', overwrite=True)
```

### Error Messages and Solutions

| Error Message | Likely Cause | Solution |
|---------------|--------------|----------|
| `"SNIRF file not found"` | Incorrect file path | Check path with `ls -la` |
| `"No 'nirs' group in SNIRF file"` | Invalid or corrupted SNIRF | Reconvert from raw data |
| `"Cannot read channel types"` | Channel naming mismatch | Check `raw.ch_names` and `raw.get_channel_types()` |
| `"Events required for task paradigm"` | Missing event information | Provide `--events-json` or use `--paradigm resting` |
| `"Failed to write metadata"` | File permissions or h5py version | Check permissions, update h5py: `pip install h5py --upgrade` |
| `"MemoryError"` | File too large | Use `--resample-sfreq`, process in chunks |

## Best Practices

### 1. Quality Control Workflow

**Recommended workflow for fNIRS data**:
1. **Pre-processing**: Convert to SNIRF, apply basic filtering
2. **Initial assessment**: Run `quality assess` with `--no-metadata`
3. **Review results**: Check `*_summary.json` and `*_detail.csv`
4. **Adjust parameters**: Modify filter ranges based on data
5. **Final assessment**: Run with `--write-metadata` to embed results
6. **Batch processing**: Apply consistent parameters to all files

### 2. Parameter Selection

| Parameter | Typical Value | Notes |
|-----------|---------------|-------|
| `--l-freq` | 0.01 Hz | Removes slow drift, keep Mayer waves |
| `--h-freq` | 0.2 Hz | Removes cardiac/respiration artifacts |
| `--resample-sfreq` | 4.0 Hz | Adequate for fNIRS, reduces file size |
| `--paradigm` | `resting` or `task` | Must match experimental design |
| `--apply-tddr` | Enabled (default) | Helps with motion artifacts |

### 3. Interpretation Guidelines

**Quality Score Interpretation**:
- **> 0.8**: Excellent - Suitable for all analyses
- **0.6-0.8**: Good - Standard analysis, consider minor preprocessing
- **0.4-0.6**: Fair - Requires careful preprocessing, may need channel exclusion
- **< 0.4**: Poor - Consider excluding from group analysis

**Bad Channel Criteria**:
- Automatic: Failed hard gating rules
- Manual: Review `*_detail.csv` for specific metric failures
- Pair-based: When one of HbO/HbR pair is bad, consider excluding both

### 4. Integration with Analysis Pipelines

**BIDS Integration**:
```bash
# Quality assessment for BIDS-organized data
multichsync quality batch \
  --input-dir derivatives/fnirs \
  --output-dir derivatives/quality \
  --paradigm resting \
  --write-metadata

# Results will be compatible with BIDS derivatives specification
```

**Downstream Analysis**:
```python
# Read quality metadata from SNIRF file
import h5py
import json

with h5py.File('data_processed.snirf', 'r') as f:
    bad_chs = f['/nirs/metaDataTags/bad_chs'][()].decode().split('; ')
    overall_score = f['/nirs/metaDataTags/overall_score'][()]
    channel_scores = json.loads(f['/nirs/metaDataTags/channel_scores_json'][()])
    
print(f"Quality score: {overall_score:.3f}")
print(f"Bad channels: {bad_chs}")
```

## API Reference

### Core Functions

#### `process_one_snirf(snirf_path, out_dir, **kwargs)`
Process a single SNIRF file for quality assessment.

**Parameters**:
- `snirf_path`: Path to SNIRF file
- `out_dir`: Output directory for results
- `l_freq`: Low cutoff frequency (Hz, default: 0.01)
- `h_freq`: High cutoff frequency (Hz, default: 0.2)
- `resample_sfreq`: Resampling frequency (Hz, default: 4.0, 0=disabled)
- `apply_tddr`: Apply TDDR motion correction (default: True)
- `comprehensive`: Compute comprehensive metrics (default: True)
- `paradigm`: "resting" or "task" (default: "resting")
- `events`: Event dictionary for task paradigm (optional)
- `write_metadata`: Write metadata to SNIRF file (default: True)

**Returns**: Dictionary with summary results

#### `assess_hb_quality_comprehensive(raw, fs, paradigm="resting", **kwargs)`
Comprehensive HbO/HbR quality assessment.

**Parameters**:
- `raw`: MNE Raw object or data array
- `fs`: Sampling frequency (Hz)
- `paradigm`: "resting" or "task"
- `events`: Event information for task paradigm
- `apply_hard_gating`: Apply automatic bad channel detection

**Returns**: Tuple of `(quality_df, bad_channels, summary_dict)`

#### `compute_signal_metrics(x, fs, **kwargs)`
Compute signal-level quality metrics for a time series.

**Parameters**:
- `x`: 1D array of signal values
- `fs`: Sampling frequency (Hz)
- `epsilon_mu`, `epsilon_sigma`, `epsilon_MAD`: Numerical stability constants

**Returns**: Dictionary with 11 signal metrics

### Data Structures

#### Event Dictionary (for task paradigm)
```python
events = {
    'onsets': [30.0, 90.0, 150.0],      # Event onset times (seconds)
    'durations': [10.0, 10.0, 10.0],     # Event durations
    'conditions': ['task', 'task', 'task'],  # Condition labels
    'artifacts': [(25.0, 28.0)],         # Artifact intervals to exclude
}
```

#### Quality DataFrame Columns
- `channel`: Channel name
- `type`: "hbo" or "hbr"
- `flatness`, `cv`, `tsnr`, `rdi`, `bdrift`: Basic metrics
- `spectral_entropy`, `mayer_ratio`, `resp_ratio`: Spectral metrics
- `hbo_hbr_corr`, `var_ratio`, `deriv_corr`: Pair metrics
- `score`: Composite quality score (0-1)
- `is_bad`: Boolean flag for bad channels

## Related Documentation

- **[Signal-Level Quality Metrics](../fnirs_signal_level_qc_metrics.md)** - Detailed metric specifications
- **[Installation Guide](installation.md)** - System requirements and installation
- **[Quickstart Guide](quickstart.md)** - End-to-end workflow example
- **[fNIRS Conversion Guide](fnirs_conversion.md)** - Creating SNIRF files for quality assessment
- **[Marker Processing Guide](marker_processing.md)** - Event timing for task-based assessment

## Support

For issues and questions:
1. Check the [troubleshooting](#troubleshooting) section
2. Review the [signal-level metrics specification](../fnirs_signal_level_qc_metrics.md)
3. Examine intermediate output files (`*_detail.csv`, `*_summary.json`)
4. Submit an issue on GitHub with:
   - Full error message and traceback
   - Command used and parameters
   - Sample data (if possible) or `*_summary.json` output
