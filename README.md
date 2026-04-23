# MultiChSync

A Python tool for converting and synchronizing multimodal neuroimaging data (fNIRS, EEG, ECG).

## Features

- **fNIRS**: Convert Shimadzu/NIRS-SPM TXT → SNIRF v1.1
- **EEG**: Convert Curry/EEGLAB → BrainVision/EEGLAB/EDF with fixed sampling rate support
- **ECG**: Convert Biopac ACQ → CSV with fixed sampling rate support
- **Marker Processing**: Extract, clean, and match event markers across modalities with comprehensive reporting
- **Quality Assessment**: Automated fNIRS signal quality evaluation
- **BIDS-Compatible**: Output follows BIDS naming conventions

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd multichsync

# Install in development mode
pip install -e .
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
# Extract markers from all modalities
multichsync marker batch --types fnirs,ecg,eeg

# Clean markers (remove duplicates, filter quality, remove start marker at t=0)
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start

# Generate subject-level reports (scans Data/convert/ and Data/raw/ for data files)
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# Match markers across devices
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching

# Crop matched data using aligned timelines
multichsync marker matchcrop-aligned \
  --json-path Data/matching/matched_metadata.json \
  --taskname newtask

# Adjust device offsets and regenerate matched timeline
multichsync marker adjust-offsets \
  --json-path Data/matching/matched_metadata.json \
  --offsets "device1:1.5,device2:-0.3" \
  --output-dir Data/matching/adjusted \
  --prefix adjusted
```

### Quality Assessment (fNIRS)

```bash
# Batch quality assessment with metadata writing
multichsync quality batch --input-dir Data/convert/fnirs \
  --output-dir Data/quality --l-freq 0.01 --h-freq 0.2
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
└── quality/          # fNIRS quality reports
```

## Requirements

- Python >= 3.8
- numpy, pandas, h5py, scipy
- mne (EEG/fNIRS processing)
- bioread (ACQ files)
- pybv (BrainVision format)
- mne-nirs (optional, for SNIRF metadata writing)

Install all dependencies:
```bash
pip install -r requirements.txt
```

## Python API

```python
from multichsync.fnirs import convert_fnirs_to_snirf
from multichsync.ecg import convert_acq_to_csv
from multichsync.eeg import convert_eeg_format
from multichsync.marker import extract_marker_info
from multichsync.quality import process_one_snirf

# fNIRS conversion
output_path = convert_fnirs_to_snirf(
    txt_path="data.TXT",
    src_coords_csv="source_coordinates.csv",
    det_coords_csv="detector_coordinates.csv",
    output_path="output.snirf"
)

# ECG conversion with fixed sampling rate
result = convert_acq_to_csv(
    acq_path="data.acq",
    output_path="./convert",
    sampling_rate=250
)

# EEG conversion with fixed sampling rate
raw, output_path = convert_eeg_format(
    file_path="data.set",
    export_format="BrainVision",
    output_path="./convert/data.vhdr",
    sampling_rate=250
)

# Marker information extraction (scans Data/convert/ and Data/raw/ for data files)
reports = extract_marker_info(
    input_dir="Data/marker",
    output_dir="Data/marker/info"
)

# Quality assessment
summary = process_one_snirf(
    snirf_path="data.snirf",
    out_dir="./quality",
    l_freq=0.01,
    h_freq=0.2
)
```

## Development

```bash
# Set up development environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

# Install in development mode
pip install -e .

# Run tests
pytest tests/
```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[English Documentation](docs/en/README.md)** - Complete English documentation
- **[中文文档](docs/zh/README.md)** - Chinese documentation (partial translation)

The documentation includes:
- Installation and quickstart guides
- Module-specific guides (fNIRS, EEG, ECG, marker, quality)
- API reference and architecture overview
- Technical specifications and development guidelines

## License

MIT License

## Contributing

Issues and pull requests are welcome. Please ensure tests pass before submitting changes.