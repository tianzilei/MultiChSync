# MultiChSync

A Python tool for converting and synchronizing multimodal neuroimaging data (fNIRS, EEG, ECG).

## Features

- **fNIRS**: Convert Shimadzu/NIRS-SPM TXT → SNIRF v1.1 with MNE compatibility patching
- **EEG**: Convert Curry/EEGLAB → BrainVision/EEGLAB/EDF with fixed sampling rate support
- **ECG**: Convert Biopac ACQ → CSV with fixed sampling rate support
- **Marker Processing**: Extract, clean, match, and crop event markers across modalities with comprehensive reporting and drift correction
- **Quality Assessment**: Automated fNIRS signal quality evaluation with metadata embedding
- **BIDS-Compatible**: Output follows BIDS naming conventions

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd multichsync

# Install with core dependencies
pip install -e .

# Install with all dev tools (pytest, black, ruff, mypy)
pip install -e ".[dev]"

# Install optional quality-assessment extras
pip install -e ".[quality]"
```

### Data Conversion

```bash
# fNIRS: Convert TXT to SNIRF
multichsync fnirs batch --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs

# EEG: Convert to BrainVision format with fixed sampling rate (250Hz default)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision \
  --output-dir Data/convert/EEG --recursive --sampling-rate 250

# ECG: Convert ACQ to CSV with fixed sampling rate
multichsync ecg batch --input-dir Data/raw/ECG \
  --output-dir Data/convert/ECG --sampling-rate 250
```

### Fixed Sampling Rate

EEG and ECG conversion support fixed sampling rate output for consistent downstream processing:

```bash
# EEG: Convert with 250Hz sampling rate (default when --sampling-rate flag is used)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --sampling-rate 250

# EEG: Convert with custom sampling rate (500Hz)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision --sampling-rate 500

# EEG: Convert without resampling (preserve original sampling rate)
multichsync eeg batch --input-dir Data/raw/EEG --format BrainVision

# ECG: Convert with 250Hz sampling rate (default)
multichsync ecg batch --input-dir Data/raw/ECG --sampling-rate 250
```

**Note:** EEG resampling uses a 0.1Hz tolerance threshold to avoid unnecessary processing when the original sampling rate is already close to the target rate.

### Marker Pipeline

```bash
# Extract markers from a single file (auto-detect type)
multichsync marker extract --input Data/raw/fnirs/sub-001_task-rest_fnirs.csv --type fnirs

# Extract markers from all modalities (batch mode)
multichsync marker batch --types fnirs,ecg,eeg

# Clean markers (remove duplicates, filter quality, remove start marker at t=0)
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start

# Generate subject-level reports (scans Data/convert/ and Data/raw/ for data files)
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# Match markers across devices (multiple algorithms available)
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg \
  --output-dir Data/matching --method hungarian

# Match by filename (auto-loads from Data/convert)
multichsync marker match --filename sub-060_ses-01_task-rest \
  --output-dir Data/matching

# Crop matched timeline to shortest sequence
multichsync marker crop --timeline-csv Data/matching/matched_timeline.csv \
  --metadata-json Data/matching/matched_metadata.json --output-prefix cropped

# Manually adjust device offsets and regenerate matched timeline
multichsync marker manual-match \
  --json-path Data/matching/matched_metadata.json \
  --offsets "[1.5, -0.3]" \
  --prefix manual

# Crop matched data using aligned timelines
multichsync marker matchcrop --timeline-csv Data/matching/matched_timeline.csv \
  --metadata-json Data/matching/matched_metadata.json \
  --reference sub-060_ses-01_task-rest_fnirs --output-dir Data/matchcrop

# Crop all device data using consensus time range
multichsync marker matchcrop-aligned \
  --json-path Data/matching/matched_metadata.json \
  --start-time 0.0 --end-time 300.0 --taskname newtask

# Supported matching methods (use with --method):
#   hungarian    - Hungarian algorithm (default)
#   mincostflow  - Min-cost flow network
#   sinkhorn     - Sinkhorn optimal transport
```

### Quality Assessment (fNIRS)

```bash
# Basic batch quality assessment
multichsync quality batch --input-dir Data/convert/fnirs \
  --output-dir Data/quality --l-freq 0.01 --h-freq 0.2

# Quality assessment with metadata written to SNIRF output
multichsync quality batch-with-metadata --input-dir Data/convert/fnirs \
  --output-dir Data/quality

# Compute resting-state metrics
multichsync quality resting-metrics --input-dir Data/convert/fnirs

# Generate visualization plots
multichsync quality visualize --input Data/convert/fnirs/sub-001.snirf
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

### Agent Guidelines

If using AI coding agents, see [AGENTS.md](docs/en/contributing/agents.md) for repo-specific guidance on toolchain, architecture, testing, and common gotchas.

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[English Documentation](docs/en/README.md)** - Complete English documentation
- **[中文文档](docs/zh/README.md)** - Chinese documentation

The documentation includes:
- Installation and quickstart guides
- Module-specific guides (fNIRS, EEG, ECG, marker, quality)
- API reference and architecture overview
- Technical specifications and development guidelines
- AI agent development guidelines

## License

MIT License

## Contributing

Issues and pull requests are welcome. Before submitting changes:

1. Install dev dependencies: `pip install -e ".[dev]"`
2. Format code: `black multichsync tests`
3. Check lint: `ruff check multichsync tests`
4. Run type check: `mypy multichsync`
5. Ensure tests pass: `pytest --cov=multichsync -n auto`
