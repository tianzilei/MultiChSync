# Quick Start Guide

This guide will help you get started with MultiChSync in minutes. We'll walk through a complete workflow from data conversion to marker synchronization.

## Overview

MultiChSync processes multimodal neuroimaging data in three main stages:

1. **Data Conversion**: Convert raw data to standard formats
2. **Marker Processing**: Extract, clean, and synchronize event markers
3. **Quality Assessment**: Evaluate fNIRS signal quality

## Step 1: Prepare Your Data

### Recommended Directory Structure
```
Data/
├── raw/
│   ├── fnirs/          # Shimadzu .TXT or .csv files
│   ├── EEG/           # Curry .set or EEGLAB .set files
│   └── ECG/           # Biopac .acq files
├── convert/           # Converted data (auto-created)
├── marker/           # Extracted markers (auto-created)
└── quality/          # Quality reports (auto-created)
```

### Required Coordinate Files (for fNIRS)
Place these in the `Data/` directory:
- `source_coordinates.csv` - 3D positions of fNIRS sources (T1-T8 labels)
- `detector_coordinates.csv` - 3D positions of fNIRS detectors (R1-R8 labels)

Example coordinate file format:
```csv
label,x,y,z
T1,0.0,0.0,0.0
T2,30.0,0.0,0.0
...
R1,15.0,20.0,0.0
R2,45.0,20.0,0.0
...
```

## Step 2: Convert Your Data

### Convert fNIRS Data
```bash
# Single file conversion
multichsync fnirs convert \
  --txt-path Data/raw/fnirs/sample.TXT \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output Data/convert/fnirs/sample.snirf

# Batch conversion (recommended)
multichsync fnirs batch \
  --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs
```

### Convert EEG Data
```bash
# Batch convert EEG files to BrainVision format
multichsync eeg batch \
  --input-dir Data/raw/EEG \
  --format BrainVision \
  --output-dir Data/convert/EEG \
  --recursive
```

### Convert ECG Data
```bash
# Batch convert ECG files
multichsync ecg batch \
  --input-dir Data/raw/ECG \
  --output-dir Data/convert/ECG
```

## Step 3: Extract Event Markers

### Extract Markers from All Modalities
```bash
# Extract all marker types
multichsync marker batch --types fnirs,ecg,eeg

# Or use the Python script for more control
python extract_all_markers.py --max-files 5  # Test with first 5 files
```

**What this does:**
- **fNIRS markers**: Extracts from `Data/raw/fnirs/*.csv` → `Data/marker/fnirs/`
- **ECG markers**: Extracts from `Data/convert/ecg/*input.csv` → `Data/marker/ecg/`
- **EEG markers**: Extracts from `Data/convert/eeg/**/*.vmrk` → `Data/marker/eeg/`

### Clean Extracted Markers
```bash
# Clean all marker files
multichsync marker clean \
  --input Data/marker \
  --inplace \
  --min-rows 2 \
  --min-interval 1.0
```

## Step 4: Generate Marker Reports

### Create Subject-Level Reports
```bash
multichsync marker info \
  --input-dir Data/marker \
  --output-dir Data/marker/info
```

This creates:
- `subject_XXX_marker_report.csv` - One per subject with marker statistics
- `report_errors.csv` - Files that failed processing

## Step 5: Synchronize Markers Across Devices

### Match Markers from Multiple Devices
```bash
# Match specific files
multichsync marker match \
  --input-files \
    Data/marker/fnirs/20251101060_1_marker.csv \
    Data/marker/ecg/20251101060part1_marker.csv \
    Data/marker/eeg/WJTB_060_SEG_01_marker.csv \
  --device-names fnirs ecg eeg \
  --output-dir Data/matching \
  --max-time-diff 2.0
```

### Alternative: Match All Files in Directory
```bash
# Match all BIDS-formatted marker files
multichsync marker match \
  --input-dir Data/marker \
  --output-dir Data/matching \
  --max-time-diff 5.0
```

**Output Files:**
- `matched_timeline.csv` - Consensus timeline with device times
- `matched_metadata.json` - Matching parameters and statistics
- `matched_timeline_alignment.png` - Visualization of aligned timelines
- `matched_confidence_distribution.png` - Confidence scores distribution

## Step 6: Crop Data Using Aligned Timelines

### Crop to Aligned Time Window
```bash
multichsync marker matchcrop-aligned \
  --json-path Data/matching/matched_metadata.json \
  --taskname synchronized_task
```

**What this does:**
1. Reads the matched timeline from `matched_metadata.json`
2. Applies drift correction to each device
3. Crops all data files to the aligned time window
4. Renames files with the new task name `synchronized_task`

### Custom Time Range
```bash
# Crop specific time range (0 to 300 seconds)
multichsync marker matchcrop-aligned \
  --json-path Data/matching/matched_metadata.json \
  --start-time 0 \
  --end-time 300 \
  --taskname task_first5min
```

## Step 7: Assess fNIRS Data Quality

### Single File Quality Assessment
```bash
multichsync quality assess \
  --input Data/convert/fnirs/sub-001_task-rest.snirf \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2
```

### Batch Quality Assessment
```bash
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2
```

**Output Includes:**
- Quality scores and bad channel lists
- Comprehensive signal metrics
- Visualizations of signal quality
- Metadata embedded in SNIRF files

## Complete Workflow Example

Here's a complete script that runs the entire pipeline:

```bash
#!/bin/bash

# 1. Convert all data
echo "Step 1: Converting data..."
multichsync fnirs batch --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs

multichsync eeg batch --input-dir Data/raw/EEG \
  --format BrainVision --output-dir Data/convert/EEG --recursive

multichsync ecg batch --input-dir Data/raw/ECG \
  --output-dir Data/convert/ECG

# 2. Extract markers
echo "Step 2: Extracting markers..."
python extract_all_markers.py --clean --clean-min-rows 3

# 3. Generate reports
echo "Step 3: Generating marker reports..."
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# 4. Match markers (example for subject 060)
echo "Step 4: Matching markers..."
multichsync marker match \
  --input-files \
    Data/marker/fnirs/20251101060_1_marker.csv \
    Data/marker/ecg/20251101060part1_marker.csv \
    Data/marker/eeg/WJTB_060_SEG_01_marker.csv \
  --device-names fnirs ecg eeg \
  --output-dir Data/matching \
  --max-time-diff 2.0

# 5. Crop aligned data
echo "Step 5: Cropping aligned data..."
multichsync marker matchcrop-aligned \
  --json-path Data/matching/matched_metadata.json \
  --taskname synchronized

# 6. Quality assessment
echo "Step 6: Assessing quality..."
multichsync quality batch \
  --input-dir Data/convert/fnirs \
  --output-dir Data/quality \
  --l-freq 0.01 \
  --h-freq 0.2

echo "Pipeline complete!"
```

## Python API Quick Start

Prefer programming to command line? Use the Python API:

```python
from multichsync.fnirs import convert_fnirs_to_snirf
from multichsync.ecg import batch_convert_acq_to_csv
from multichsync.eeg import batch_convert_eeg_format
from multichsync.marker import extract_marker_info, match_multiple_files_enhanced
from multichsync.quality import batch_process_snirf_folder

# Convert fNIRS data
output_path = convert_fnirs_to_snirf(
    txt_path="Data/raw/fnirs/sample.TXT",
    src_coords_csv="Data/source_coordinates.csv",
    det_coords_csv="Data/detector_coordinates.csv",
    output_path="Data/convert/fnirs/sample.snirf"
)

# Convert ECG data in batch
ecg_results = batch_convert_acq_to_csv(
    input_dir="Data/raw/ECG",
    output_dir="Data/convert/ECG"
)

# Extract marker information
reports = extract_marker_info(
    input_dir="Data/marker",
    output_dir="Data/marker/info",
    recursive=True
)

# Match markers across devices
match_results = match_multiple_files_enhanced(
    file_paths=[
        "Data/marker/fnirs/sub-060_marker.csv",
        "Data/marker/ecg/sub-060_marker.csv",
        "Data/marker/eeg/sub-060_marker.csv"
    ],
    device_names=["fnirs", "ecg", "eeg"],
    output_dir="Data/matching",
    output_prefix="matched"
)

# Assess fNIRS quality in batch
quality_summary, failed = batch_process_snirf_folder(
    in_dir="Data/convert/fnirs",
    out_dir="Data/quality",
    l_freq=0.01,
    h_freq=0.2
)
```

## Next Steps

### Explore Advanced Features
- **Custom cleaning parameters**: Adjust `--min-interval` and `--min-rows` for marker cleaning
- **Different matching algorithms**: Try `--method mincostflow` or `--method sinkhorn`
- **Quality assessment paradigms**: Use `--paradigm task` for task-based data
- **Metadata embedding**: Use `assess-with-metadata` to embed results in SNIRF files

### Learn More
- [fNIRS Conversion Guide](fnirs_conversion.md) - Detailed fNIRS processing
- [EEG Conversion Guide](eeg_conversion.md) - EEG format details
- [ECG Conversion Guide](ecg_conversion.md) - ECG processing specifics
- [Marker Processing Guide](marker_processing.md) - Advanced marker techniques
- [Quality Assessment Guide](quality_assessment.md) - Comprehensive quality metrics

### Get Help
- Use `multichsync <command> --help` for command-specific help
- Check the [API Reference](../api/index.md) for Python usage
- Review example scripts in the `scripts/` directory

---

**Congratulations!** You've successfully run the MultiChSync pipeline. The system is now ready for your research data processing needs.