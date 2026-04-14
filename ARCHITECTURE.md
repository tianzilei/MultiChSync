# MultiChSync Architecture

## Overview

MultiChSync is a comprehensive Python tool for converting, processing, and quality-assessing multimodal neuroimaging data (fNIRS, ECG, EEG). It supports multiple data formats with robust batch processing capabilities, automatic marker extraction, and comprehensive quality assessment with metadata integration.

**Primary Purpose**: Convert neuroimaging data between proprietary formats and standardized formats (SNIRF, BrainVision, CSV) while preserving metadata and enabling quality assessment.

## Tech Stack

### Languages
- **Python 3.8+** - Primary language

### Core Dependencies
- `numpy>=1.21.0`, `pandas>=1.3.0` - Numerical computing and data handling
- `h5py>=3.0.0` - HDF5/SNIRF file I/O
- `scipy>=1.7.0` - Scientific computing
- `snirf>=0.5.0` - SNIRF format validation

### Module-Specific Dependencies
- **fNIRS Conversion**: `snirf` (SNIRF validation)
- **ECG Conversion**: `bioread>=2.0.0` (ACQ file reading), `neurokit2>=0.2.0` (ECG processing)
- **EEG Conversion**: `mne>=1.0.0` (EEG processing), `pybv>=0.5.0` (BrainVision export)
- **Quality Assessment**: `mne>=1.0.0` (fNIRS processing), `mne-nirs` (optional, for metadata writing)

## Directory Structure

```
MultiChSync/
├── multichsync/                  # Main package
│   ├── __init__.py              # Root exports
│   ├── cli.py                   # Command-line interface
│   ├── fnirs/                   # fNIRS conversion module
│   │   ├── __init__.py          # fNIRS API exports
│   │   ├── parser.py            # Shimadzu TXT parsing
│   │   ├── writer.py            # SNIRF v1.1 writing
│   │   ├── converter.py         # Main conversion logic
│   │   ├── batch.py             # Batch conversion
│   │   └── mne_patch.py         # MNE compatibility fixes
│   ├── ecg/                     # ECG conversion module
│   │   ├── __init__.py
│   │   ├── parser.py            # ACQ file parsing
│   │   ├── writer.py            # CSV writing
│   │   ├── converter.py         # Conversion logic
│   │   └── batch.py             # Batch conversion
│   ├── eeg/                     # EEG conversion module
│   │   ├── __init__.py
│   │   ├── parser.py            # Curry/EEGLAB parsing
│   │   ├── writer.py            # BrainVision/EEGLAB/EDF writing
│   │   ├── converter.py         # Conversion logic
│   │   └── batch.py             # Batch conversion
│   ├── marker/                  # Marker extraction module
│   │   ├── __init__.py
│   │   ├── extractor.py         # Multi-format marker extraction
│   │   └── info_extractor.py    # Metadata extraction and reporting
│   ├── quality/                 # Quality assessment module
│   │   ├── __init__.py
│   │   └── assessor.py          # Comprehensive quality assessment
│   └── utils/                   # Shared utilities
├── Data/                        # Example data (not tracked in git)
├── examples/                    # Example scripts
├── tests/                       # Test files
├── README.md                    # Project documentation
├── setup.py                     # Package configuration
├── requirements.txt             # Dependencies
└── run_example.py              # Example runner
```

## Core Components

### 1. fNIRS Module (`multichsync/fnirs/`)
**Purpose**: Convert Shimadzu/NIRS-SPM TXT format to SNIRF v1.1

**Key Files**:
- `parser.py` - Parse Shimadzu TXT files, extract metadata, infer channel pairs
- `writer.py` - Write SNIRF v1.1 HDF5 files with compression and standard compliance
- `converter.py` - Coordinate parsing and writing, apply MNE compatibility patches
- `mne_patch.py` - Fix SNIRF files for MNE-Python compatibility (wavelength validation, HbT handling)

**Key Features**:
- Automatic stim event extraction from "Mark" column
- Auxiliary time series from "Count" column
- Strict source/detector coordinate validation (T1-T8, R1-R8 labels)
- Support for oxyHb/deoxyHb/totalHb triplets
- HDF5 compression and SNIRF v1.1 compliance

### 2. ECG Module (`multichsync/ecg/`)
**Purpose**: Convert Biopac ACQ files to CSV format

**Key Files**:
- `parser.py` - Parse ACQ files using bioread library
- `writer.py` - Write CSV files with channel grouping
- `converter.py` - Convert ACQ to CSV with sampling rate configuration

**Key Features**:
- Automatic channel grouping by type
- Configurable sampling rates
- Batch processing support

### 3. EEG Module (`multichsync/eeg/`)
**Purpose**: Convert EEG files between formats (Curry, EEGLAB → BrainVision, EEGLAB, EDF)

**Key Files**:
- `parser.py` - Read Curry/EEGLAB formats using MNE
- `writer.py` - Export to BrainVision/EEGLAB/EDF formats
- `converter.py` - Format conversion logic

**Key Features**:
- Support for multiple input formats (`.set`, `.cdt`, `.cdt.dpa`)
- Multiple export formats (BrainVision, EEGLAB, EDF)
- Batch processing with recursive directory search

### 4. Marker Module (`multichsync/marker/`)
**Purpose**: Extract, clean, and analyze timing markers from various formats

**Key Files**:
- `extractor.py` - Extract markers from fNIRS CSV, BrainVision .vmrk, Biopac CSV
- `info_extractor.py` - Generate per-subject reports with metadata and sequence durations

**Key Features**:
- Automatic type detection (fNIRS, EEG, ECG)
- Robust encoding handling (utf-8-sig, gbk, latin1 fallbacks)
- Data cleaning (deduplication, interval filtering)
- Subject-level reporting with device type inference
- Sequence duration extraction from raw data files

### 5. Quality Assessment Module (`multichsync/quality/`)
**Purpose**: Comprehensive fNIRS data quality evaluation with metadata integration

**Key File**:
- `assessor.py` - 90K+ lines of comprehensive quality assessment logic

**Key Features**:
- **Signal-level metrics** (based on `fnirs_signal_level_qc_metrics.md`):
  - Near-flatline detection, coefficient of variation, temporal SNR
  - Robust derivative index, baseline drift, spectral entropy
  - Physiological band power ratios, HbO-HbR correlation metrics
- **Paradigm-specific metrics**:
  - Task: CNR (contrast-to-noise ratio), GoodEventFraction
  - Resting-state: Split-half reliability
- **Metadata integration**:
  - Write bad channel lists, quality scores to SNIRF `/nirs/metaDataTags`
  - Generate processed SNIRF files with embedded quality metadata
- **Smart filtering**: IIR for short recordings (<10 min), FIR for longer
- **Batch processing**: Error isolation, summary reporting

## Data Flow

### 1. Conversion Pipeline
```
Raw Data → Format Detection → Parser → Converter → Writer → Standardized Output
    ↓
Metadata Extraction → Quality Assessment → Metadata Embedding
```

### 2. Marker Processing Pipeline
```
Raw/Marker Files → Type Detection → Extractor → Cleaner → Info Extractor → Subject Reports
                              ↓
                      Sequence Duration Extraction
```

### 3. Quality Assessment Pipeline
```
SNIRF File → Load with MNE → Pre-filter Assessment → Smart Filtering → Post-filter Assessment
      ↓                                                                      ↓
Signal-level Metrics ←──────────────┤               Metadata Writing → Processed SNIRF + Reports
      ↓
Paradigm-specific Metrics (Task/Resting)
```

## External Integrations

### File Formats
- **Input**: Shimadzu TXT, Biopac ACQ, Curry (.cdt), EEGLAB (.set), BrainVision (.vhdr/.vmrk)
- **Output**: SNIRF v1.1 (.snirf), CSV, BrainVision (.vhdr/.vmrk/.eeg), EEGLAB (.set), EDF

### Libraries
- **MNE-Python**: EEG/fNIRS data loading and processing
- **bioread**: ACQ file reading
- **neurokit2**: ECG processing
- **pybv**: BrainVision format export
- **h5py**: SNIRF/HDF5 file manipulation
- **snirf**: SNIRF format validation

## Configuration

### Package Configuration (`setup.py`)
- Entry point: `multichsync=multichsync.cli:main`
- Python 3.8+ requirement
- MIT license

### Dependencies (`requirements.txt`)
- Core dependencies listed with version constraints
- Optional dependencies for specific modules

### No Other Config Files
- No linter/formatter configs (flake8, black, ruff, etc.)
- No CI/CD configs (.github/workflows, .gitlab-ci.yml, etc.)
- No test runner configs (pytest.ini, tox.ini)

## Build & Deploy

### Installation
```bash
# From source
git clone <repository-url>
cd multichsync
pip install -e .

# Via pip
pip install multichsync
```

### Command-Line Interface
```bash
# Module structure
multichsync <module> <subcommand> [options]

# Examples
multichsync fnirs convert --txt-path data.TXT --src-coords source.csv --det-coords detector.csv
multichsync quality assess --input data.snirf --output-dir ./quality
multichsync marker info --input-dir Data/marker --output-dir ./reports
```

### Testing
```bash
# Run test files directly
python test_event_matching.py
python test_metadata_functionality.py
```

## Key Architectural Decisions

### 1. Modular Design
Each modality (fNIRS, ECG, EEG) has its own module with consistent structure:
- `parser.py` for input parsing
- `writer.py` for output writing  
- `converter.py` for coordination
- `batch.py` for batch processing

### 2. Dual Interfaces
- **Python API**: Functional interfaces for programmatic use
- **CLI**: Hierarchical commands for interactive use

### 3. Error Handling Strategy
- Graceful degradation when optional dependencies missing
- Comprehensive validation before processing
- Batch processing with per-file error isolation

### 4. Metadata Preservation
- Quality assessment results embedded in SNIRF files
- Automatic bad channel propagation (pair-based for fNIRS)
- Processing metadata recorded in output files

### 5. Smart Defaults
- Automatic filter selection based on recording length
- Comprehensive quality assessment enabled by default
- macOS hidden file filtering in batch operations

## Extension Points

### Adding New Formats
1. Add parser in appropriate module directory
2. Implement `parse_*` function following existing patterns
3. Add to module's `__init__.py` exports
4. Optionally add CLI command in `cli.py`

### Adding New Quality Metrics
1. Add metric calculation in `quality/assessor.py`
2. Integrate into `compute_signal_metrics()` or create new function
3. Update `assess_hb_quality_comprehensive()` to include new metric

### Adding New Marker Formats
1. Add extractor function in `marker/extractor.py`
2. Implement automatic type detection logic
3. Update CLI's type inference in `marker_extract()` function