# MultiChSync

A Python tool for converting and synchronizing multimodal neuroimaging data (fNIRS, EEG, ECG).

## Architecture Overview

MultiChSync is a multimodal neuroimaging data processing pipeline designed to handle the conversion, synchronization, and quality assessment of fNIRS, EEG, and ECG data. The system addresses three core challenges:

1. **Format conversion** — Transforming proprietary formats (Shimadzu TXT, Curry/EEGLAB, Biopac ACQ) into standard open formats (SNIRF, BrainVision, CSV)
2. **Temporal synchronization** — Aligning event markers across multiple recording devices with different clock drifts
3. **Quality assessment** — Automated signal quality evaluation for fNIRS data with comprehensive metrics

### High-Level Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                         User Interface Layer                          │
├───────────────────────────────────────────────────────────────────────┤
│  Command Line Interface (CLI)            Python API                   │
│  • multichsync fnirs convert            • from multichsync.fnirs import│
│  • multichsync eeg batch                  convert_fnirs_to_snirf     │
│  • multichsync marker match             • from multichsync.quality    │
│                                            import process_one_snirf   │
└───────────────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│                        Core Processing Modules                        │
├───────────────────────────────────────────────────────────────────────┤
│  fNIRS Module     EEG Module      ECG Module      Marker Module      │
│  • Parser         • Parser        • Parser        • Extractor        │
│  • Writer         • Writer        • Writer        • Cleaner          │
│  • Converter      • Converter     • Converter     • Matcher          │
│  • Batch          • Batch         • Batch         • Info Extractor   │
│  • MNE Patch      └───────────────┴───────────────┘                  │
│  • Quality Assessor                   │                              │
│                      Quality Module   │                              │
│                      • Signal Metrics │                              │
│                      • Metadata Writer│                              │
└───────────────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          Data Format Layer                            │
├───────────────────────────────────────────────────────────────────────┤
│  Input Formats                     Output Formats                     │
│  • Shimadzu TXT/CSV               • SNIRF v1.1 (HDF5)                │
│  • Curry .set/.fdt                • BrainVision (.vhdr/.vmrk/.eeg)   │
│  • EEGLAB .set                    • EEGLAB .set                      │
│  • Biopac .acq                    • EDF                              │
│  • BrainVision .vmrk              • CSV (ECG/markers)                │
└───────────────────────────────────────────────────────────────────────┘
```

### Module Structure

Each major module follows a consistent pattern:
```
__init__.py     # Public API exports
parser.py       # Input file parsing
writer.py       # Output file writing
converter.py    # Core conversion logic
batch.py        # Batch processing utilities
```

## Features

- **fNIRS**: Convert Shimadzu/NIRS-SPM TXT → SNIRF v1.1 with MNE compatibility patching
- **EEG**: Convert Curry/EEGLAB → BrainVision/EEGLAB/EDF with fixed sampling rate support
- **ECG**: Convert Biopac ACQ → CSV with fixed sampling rate support
- **Marker Processing**: Extract, clean, match, and crop event markers across modalities with comprehensive reporting and drift correction
- **Quality Assessment**: Automated fNIRS signal quality evaluation with metadata embedding
- **BIDS-Compatible**: Output follows BIDS naming conventions

## Installation

### Prerequisites

- **Python**: Version 3.8 or higher
- **Operating System**: Linux, macOS, or Windows
- **Memory**: 4GB RAM minimum, 8GB+ recommended for large datasets

### Install from Source (Recommended for Development)

```bash
git clone <repository-url>
cd multichsync
pip install -e .
```

### Verify Installation

```bash
multichsync --version
multichsync --help
python -c "from multichsync.fnirs import convert_fnirs_to_snirf; print('OK')"
```

### Troubleshooting

**h5py installation failures**: Install system HDF5 libraries (Linux: `libhdf5-dev`, macOS: `brew install hdf5`, Windows: use precompiled wheels).
**MNE import errors**: `pip install --upgrade mne`
**Permission errors**: Use a virtual environment or `pip install --user multichsync`

## Quick Start

### Prepare Your Data

Place raw data in the following structure:

```
Data/
├── raw/
│   ├── fnirs/          # Shimadzu .TXT or .csv files
│   ├── EEG/           # Curry .set or EEGLAB .set files
│   └── ECG/           # Biopac .acq files
├── source_coordinates.csv   # fNIRS source 3D positions (T1-T8)
└── detector_coordinates.csv # fNIRS detector 3D positions (R1-R8)
```

### Step 1: Convert Data

```bash
# fNIRS: TXT to SNIRF
multichsync fnirs batch --input-dir Data/raw/fnirs --src-coords Data/source_coordinates.csv --det-coords Data/detector_coordinates.csv --output-dir Data/convert/fnirs

# EEG: to BrainVision format (250Hz default)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --output-dir Data/convert/EEG --recursive --sampling-rate 250

# ECG: ACQ to CSV
multichsync ecg batch --input-dir Data/raw/ECG --output-dir Data/convert/ECG --sampling-rate 250
```

### Step 2: Extract & Clean Markers

```bash
# Extract markers from all modalities
multichsync marker batch --types fnirs,ecg,eeg

# Clean markers (deduplicate, filter quality, remove start marker at t=0)
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start

# Generate subject-level marker reports
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info
```

### Step 3: Synchronize Markers Across Devices

```bash
# Match markers using Hungarian algorithm (default) with BIDS wildcard files
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching --method hungarian

# Manually apply offset adjustments to matched markers
multichsync marker manual-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --offsets "[1.5, -0.3, 0]" --output-dir Data/matching --prefix manual

# Brute-force shift traversal matching (minimises mean per-marker distance)
multichsync marker traversal-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching

# Supported methods (marker match): hungarian (default), mincostflow, sinkhorn
# Supported methods (marker traversal-match): shift traversal with gap handling
```

### Step 4: Crop Aligned Data

```bash
# Crop all device data using consensus time range
multichsync marker matchcrop-aligned --json-path Data/matching/matched_metadata.json --start-time 0.0 --end-time 300.0 --taskname synchronized_task
```

### Step 5: Assess fNIRS Quality

```bash
# Batch quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality --l-freq 0.01 --h-freq 0.2

# Quality assessment with metadata written to SNIRF
multichsync quality batch-with-metadata --input-dir Data/convert/fnirs --output-dir Data/quality

# Generate visualization plots
multichsync quality visualize --input Data/convert/fnirs/sub-001.snirf
```

## Complete Workflow Script

```bash
#!/bin/bash
# 1. Convert all data
multichsync fnirs batch --input-dir Data/raw/fnirs --src-coords Data/source_coordinates.csv --det-coords Data/detector_coordinates.csv --output-dir Data/convert/fnirs
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --output-dir Data/convert/EEG --recursive
multichsync ecg batch --input-dir Data/raw/ECG --output-dir Data/convert/ECG

# 2. Extract and clean markers
multichsync marker batch --types fnirs,ecg,eeg
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0

# 3. Generate marker reports
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# 4. Match markers
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching --method hungarian

# 5. Crop aligned data
multichsync marker matchcrop-aligned --json-path Data/matching/matched_metadata.json --start-time 0.0 --end-time 300.0 --taskname synchronized

# 6. Quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality
```

## Fixed Sampling Rate

EEG and ECG conversion support fixed sampling rate output for consistent downstream processing:

```bash
# EEG: Convert with 250Hz sampling rate (default when --sampling-rate is used)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --sampling-rate 250

# EEG: Custom sampling rate (500Hz)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --sampling-rate 500

# EEG: Preserve original sampling rate (omit --sampling-rate)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision

# ECG: Convert with 250Hz sampling rate (default)
multichsync ecg batch --input-dir Data/raw/ECG --sampling-rate 250
```

**Note:** EEG resampling uses a 0.1Hz tolerance threshold to avoid unnecessary processing when the original sampling rate is already close to the target rate.

## Marker Pipeline Details

```bash
# Extract markers from a single file (auto-detect type)
multichsync marker extract --input Data/raw/fnirs/sub-001_task-rest_fnirs.csv --type fnirs

# Clean markers (deduplicate, filter quality, remove start marker at t=0)
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start

# Match markers across devices using BIDS wildcard files (multiple algorithms available)
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching --method hungarian

# Crop matched timeline to shortest sequence
multichsync marker crop --timeline-csv Data/matching/matched_timeline.csv --metadata-json Data/matching/matched_metadata.json --output-prefix cropped

# Crop matched data using aligned timelines
multichsync marker matchcrop --timeline-csv Data/matching/matched_timeline.csv --metadata-json Data/matching/matched_metadata.json --reference sub-060_ses-01_task-rest_fnirs --output-dir Data/matchcrop

# Crop all device data using consensus time range
multichsync marker matchcrop-aligned --json-path Data/matching/matched_metadata.json --start-time 0.0 --end-time 300.0 --taskname newtask

# Supported matching methods (use with --method):
#   hungarian    - Hungarian algorithm (default)
#   mincostflow  - Min-cost flow network
#   sinkhorn     - Sinkhorn optimal transport
```

### Traversal Match (Brute-Force Shift Search)

A brute-force matching strategy that **traverses every possible alignment
offset** (shift) between devices instead of using global optimisation. It
finds the alignment that minimises the **mean per-marker pairwise distance**
across devices, and explicitly handles gaps where a device has no
corresponding marker.

```bash
# Traversal match from BIDS wildcard files
multichsync marker traversal-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --max-time-diff 2.0

# Traversal match from specific marker CSV files
multichsync marker traversal-match --input-files Data/marker/fnirs/*_marker.csv Data/marker/ecg/*_marker.csv --device-names fnirs ecg --max-time-diff 2.0

# Traversal match from a directory of marker CSVs
multichsync marker traversal-match --input-dir Data/marker --max-time-diff 3.0 --gap-penalty 1000000 --random-restarts 10
```

**How it works:**
1. **Anchor** — the device with the most markers is used as the reference
2. **Shift traversal** — every possible alignment offset between the anchor and each other device is evaluated
3. **Distance scoring** — each offset is scored by the mean absolute time difference across all matched pairs; gaps (unmatched markers) add a configurable penalty
4. **Random restarts** — additional random offset candidates are tested for robustness
5. **Output** — timeline CSV with per-group distances, plus a metadata JSON with gap info and shift history

**Key parameters:**
- `--max-time-diff` — maximum time difference (s) for a valid match (default: 3.0)
- `--gap-penalty` — cost applied to each unmatched marker (default: 1e6)
- `--random-restarts` — random offset candidates for robustness (default: 5)

**Python API:**
```python
from multichsync.marker import match_traversal, match_traversal_from_files
import numpy as np

# From in-memory arrays
result = match_traversal({
    "fnirs": np.array([0.1, 10.2, 20.1, 30.0, 40.3]),
    "ecg":   np.array([0.0, 10.0, 20.0, 30.1, 40.0, 50.2]),
    "eeg":   np.array([0.2, 10.1, 19.9, 30.2, 40.1]),
}, max_time_diff=3.0)

print(f"Mean distance: {result.mean_distance:.3f}s")
print(f"Total distance: {result.total_distance:.3f}s")
print(f"Gaps: {result.gaps}")

# From CSV files
result = match_traversal_from_files(
    ["fnirs_marker.csv", "ecg_marker.csv", "eeg_marker.csv"],
    device_names=["fnirs", "ecg", "eeg"],
    output_dir="Data/matching",
    output_prefix="traversal_matched",
)
```

## Quality Assessment (fNIRS)

```bash
# Basic batch quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality --l-freq 0.01 --h-freq 0.2

# Quality assessment with metadata written to SNIRF output
multichsync quality batch-with-metadata --input-dir Data/convert/fnirs --output-dir Data/quality

# Compute resting-state metrics
multichsync quality resting-metrics --input-dir Data/convert/fnirs

# Generate visualization plots
multichsync quality visualize --input Data/convert/fnirs/sub-001.snirf
```

### Quality Metrics

- Signal-to-noise ratio (SNR)
- Coefficient of variation
- Near-flatline detection
- Baseline drift index
- Physiological band power ratios
- HbO-HbR correlation analysis
- Task-based: CNR (contrast-to-noise ratio), GoodEventFraction
- Resting-state: Split-half reliability

## Data Structure

```
Data/
├── raw/               # Original data
│   ├── fnirs/        # .txt, .csv files
│   ├── EEG/          # .set, .fdt files
│   └── ECG/          # .acq files
├── convert/          # Converted data
│   ├── fnirs/        # .snirf files
│   ├── EEG/          # .vhdr, .vmrk, .eeg
│   └── ECG/          # .csv files
├── marker/           # Extracted markers
│   ├── fnirs/
│   ├── ecg/
│   ├── eeg/
│   └── info/         # Subject reports
├── matching/         # Cross-device matching results
└── quality/          # fNIRS quality reports
```

## Requirements

- Python >= 3.8
- numpy, pandas, h5py, scipy, networkx
- mne (EEG/fNIRS processing)
- bioread (ACQ files)
- pybv (BrainVision format)
- neurokit2 (ECG processing)
- snirf (SNIRF format validation)
- mne-nirs (optional, for SNIRF metadata writing)

Install all dependencies:
```bash
pip install -r requirements.txt
```

## Development

### Setup

```bash
pip install -e ".[dev]"
```

### Commands

| Tool | Command | Description |
|------|---------|-------------|
| Test | `pytest --cov=multichsync --cov-report=term-missing -n auto` | Run all tests with coverage |
| Single test | `pytest tests/unit/test_fnirs_converter.py -v` | Run a specific test file |
| Format | `black multichsync tests` | Auto-format code |
| Lint | `ruff check multichsync tests` | Static analysis |
| Typecheck | `mypy multichsync` | Type checking |

### CI

GitHub Actions runs on push/PR to `main`/`develop` with a matrix of 3 OS × Python 3.8–3.12 (excludes macos-3.12, windows-3.12). Pipeline includes test, lint, and coverage check (threshold: 35%).

## License

MIT License

## Contributing

Issues and pull requests are welcome. Before submitting changes:

1. Install dev dependencies: `pip install -e ".[dev]"`
2. Format code: `black multichsync tests`
3. Check lint: `ruff check multichsync tests`
4. Run type check: `mypy multichsync`
5. Ensure tests pass: `pytest --cov=multichsync -n auto`
