# MultiChSync

A Python tool for converting and synchronizing multimodal neuroimaging data (fNIRS, EEG, ECG).

## Features

- **fNIRS**: Convert Shimadzu/NIRS-SPM TXT → SNIRF v1.1 with MNE compatibility
- **EEG**: Convert Curry/EEGLAB → BrainVision/EEGLAB/EDF
- **ECG**: Convert Biopac ACQ → CSV
- **Marker Processing**: Extract, clean, match, and crop event markers across modalities
- **Quality Assessment**: Automated fNIRS signal quality evaluation with metadata embedding
- **BIDS-Compatible**: Output follows BIDS naming conventions

## Installation

```bash
git clone <repository-url>
cd multichsync
pip install -e .          # Install from source
pip install -e ".[quality]"  # Install with quality features (requires mne-nirs)
multichsync --help         # Verify installation
```

## Usage

### Quick Start

#### 1. Prepare Your Data

```
Data/
├── raw/
│   ├── fnirs/          # Shimadzu .TXT or .csv files
│   ├── EEG/           # Curry .set or EEGLAB .set files
│   └── ECG/           # Biopac .acq files
├── source_coordinates.csv   # fNIRS source 3D positions
└── detector_coordinates.csv # fNIRS detector 3D positions
```

#### 2. Convert Data

```bash
# fNIRS: TXT to SNIRF
multichsync fnirs batch --input-dir Data/raw/fnirs --src-coords Data/source_coordinates.csv --det-coords Data/detector_coordinates.csv --output-dir Data/convert/fnirs
# EEG: to BrainVision (250Hz)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --output-dir Data/convert/EEG --recursive --sampling-rate 250
# ECG: ACQ to CSV
multichsync ecg batch --input-dir Data/raw/ECG --output-dir Data/convert/ECG --sampling-rate 250
```

#### 3. Process Markers

```bash
# Extract markers from all modalities
multichsync marker batch --types fnirs,ecg,eeg
# Clean markers (deduplicate, filter)
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start
# Generate marker reports and alignment JSONs
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info
```

#### 4. Synchronize Markers

```bash
# Base match (from alignment JSONs)
multichsync marker basematch --timeline-dir Data/marker/info
# Crop aligned data by sessions (auto-detects everything)
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop
# Device output mode: Data/matchcrop/{device}/subject-{id}/ses-{N}/
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop --output-mode device
```

#### 5. Assess fNIRS Quality

```bash
# Batch quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality --l-freq 0.01 --h-freq 0.2
# With metadata written to SNIRF (requires mne-nirs)
multichsync quality batch-with-metadata --input-dir Data/convert/fnirs --output-dir Data/quality
```

### Complete Workflow

```bash
# 1. Convert all data
multichsync fnirs batch --input-dir Data/raw/fnirs --src-coords Data/source_coordinates.csv --det-coords Data/detector_coordinates.csv --output-dir Data/convert/fnirs
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --output-dir Data/convert/EEG --recursive --sampling-rate 250
multichsync ecg batch --input-dir Data/raw/ECG --output-dir Data/convert/ECG --sampling-rate 250
# 2. Extract and clean markers
multichsync marker batch --types fnirs,ecg,eeg
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start
# 3. Generate marker reports and alignment JSONs
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info
# 4. Match and crop markers
multichsync marker basematch --timeline-dir Data/marker/info
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop
# 5. Quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality
```

### Common Commands

#### fNIRS Patch (MNE Compatibility)

```bash
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --inplace  # Patch in-place
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --output Data/convert/fnirs/sub-001_fixed.snirf  # Patch to new file
```

#### Manual Offset Adjustment

```bash
multichsync marker manual-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --offsets "[1.5, -0.3, 0]" --output-dir Data/matching --prefix manual
```

#### Quality Visualization

```bash
multichsync quality visualize --input Data/convert/fnirs/sub-001.snirf  # Single file
multichsync quality visualize-batch --input-dir Data/convert/fnirs --output-dir Data/quality  # Batch
```

### Python API

```python
from multichsync.fnirs import convert_fnirs_to_snirf, batch_convert_fnirs_to_snirf  # fNIRS
from multichsync.eeg import convert_eeg_to_brainvision, batch_convert_eeg_to_brainvision  # EEG
from multichsync.ecg import convert_acq_to_csv, batch_convert_acq_to_csv  # ECG
from multichsync.marker import extract_marker_time_only, clean_marker_csv, extract_marker_info  # Marker
from multichsync.quality import assess_hb_quality, process_one_snirf  # Quality
# Example: Convert fNIRS
result = convert_fnirs_to_snirf(txt_path="Data/raw/fnirs/sub-001.txt", src_coords="Data/source_coordinates.csv", det_coords="Data/detector_coordinates.csv", output_path="Data/convert/fnirs/sub-001.snirf")
```

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
│   └── info/         # Reports + alignment JSONs
├── matching/         # Cross-device matching results
├── matchcrop/        # Per-session cropped data
│   ├── subject-{id}/
│   │   ├── ses-01/
│   │   │   ├── sub-{id}_ses-01_task-{task}_fnirs.snirf
│   │   │   ├── sub-{id}_ses-01_task-{task}_ecg.csv
│   │   │   └── sub-{id}_ses-01_task-{task}_eeg.vhdr
│   │   └── ses-02/ ...
│   └── crop_report.json
└── quality/          # fNIRS quality reports
```

## Requirements

- Python >= 3.8
- Core: numpy, pandas, h5py, scipy, networkx
- fNIRS: snirf
- EEG: mne, pybv
- ECG: bioread, neurokit2
- Quality (optional): mne-nirs

## Development

```bash
pip install -e ".[dev]"  # Install dev dependencies
pytest --cov=multichsync --cov-report=term-missing -n auto  # Run tests
black multichsync tests  # Format code
ruff check multichsync tests  # Lint
mypy multichsync  # Type check
```

## Quality Metrics

- Signal-to-noise ratio (SNR)
- Coefficient of variation
- Near-flatline detection
- Baseline drift index
- Physiological band power ratios
- HbO-HbR correlation
- Task-based: CNR, GoodEventFraction
- Resting-state: Split-half reliability

## License

MIT License

## Contributing

Issues and pull requests are welcome. Before submitting:

1. Install dev dependencies: `pip install -e ".[dev]"`
2. Format code: `black multichsync tests`
3. Check lint: `ruff check multichsync tests`
4. Run tests: `pytest --cov=multichsync -n auto`
