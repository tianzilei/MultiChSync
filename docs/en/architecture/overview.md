# MultiChSync Architecture Overview

## System Purpose

MultiChSync is a multimodal neuroimaging data processing pipeline designed to handle the conversion, synchronization, and quality assessment of fNIRS, EEG, and ECG data. The system addresses three core challenges:

1. **Format conversion** - Transforming proprietary formats (Shimadzu TXT, Curry/EEGLAB, Biopac ACQ) into standard open formats (SNIRF, BrainVision, CSV)
2. **Temporal synchronization** - Aligning event markers across multiple recording devices with different clock drifts
3. **Quality assessment** - Automated signal quality evaluation for fNIRS data with comprehensive metrics

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Interface Layer                          │
├─────────────────────────────────────────────────────────────────────────┤
│  Command Line Interface (CLI)        Python API                         │
│  • multichsync fnirs convert         • from multichsync.fnirs import    │
│  • multichsync eeg batch               convert_fnirs_to_snirf           │
│  • multichsync marker match          • from multichsync.quality import  │
│                                      • process_one_snirf                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Core Processing Modules                          │
├─────────────────────────────────────────────────────────────────────────┤
│  fNIRS Module       EEG Module        ECG Module       Marker Module    │
│  • Parser           • Parser          • Parser         • Extractor      │
│  • Writer           • Writer          • Writer         • Cleaner        │
│  • Converter        • Converter       • Converter      • Matcher        │
│  • Batch Processor  • Batch Processor • Batch Processor• Info Extractor │
│  • MNE Patch        └─────────────────┴─────────────────┘               │
│  • Quality Assessor                    │                                │
│                                        ▼                                │
│                        Quality Module  │                                │
│                        • Signal Metrics│                                │
│                        • Metadata Writer                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Data Format Layer                               │
├─────────────────────────────────────────────────────────────────────────┤
│  Input Formats                      Output Formats                      │
│  • Shimadzu TXT/CSV                • SNIRF v1.1 (HDF5)                 │
│  • Curry .set/.fdt                 • BrainVision (.vhdr/.vmrk/.eeg)    │
│  • EEGLAB .set                     • EEGLAB .set                       │
│  • Biopac .acq                     • EDF                               │
│  • BrainVision .vmrk               • CSV (ECG/markers)                 │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### fNIRS Module (`multichsync/fnirs/`)
Converts Shimadzu/NIRS-SPM TXT files to SNIRF v1.1 format.

**Key Components:**
- **Parser**: Reads Shimadzu TXT files, extracts header metadata, hemoglobin data
- **Writer**: Creates SNIRF HDF5 files with proper structure and metadata
- **Converter**: Orchestrates parsing and writing, handles coordinate mapping
- **Batch Processor**: Processes multiple files with progress tracking
- **MNE Patch**: Fixes SNIRF files for MNE-Python compatibility
- **Quality Assessor**: Performs signal quality evaluation (separate module)

**Data Flow:**
```
Shimadzu TXT → Parser → DataFrame → Coordinate Mapping → Writer → SNIRF
```

### EEG Module (`multichsync/eeg/`)
Converts EEG data between various formats.

**Key Components:**
- **Parser**: Reads Curry and EEGLAB files using MNE-Python
- **Writer**: Exports to BrainVision, EEGLAB, or EDF formats
- **Converter**: Manages format conversion with proper channel info preservation
- **Batch Processor**: Recursive directory processing

**Supported Conversions:**
- Curry → BrainVision
- EEGLAB → BrainVision
- Curry → EEGLAB
- EEGLAB → EDF

### ECG Module (`multichsync/ecg/`)
Converts Biopac ACQ files to CSV format.

**Key Components:**
- **Parser**: Reads ACQ files using bioread library
- **Writer**: Exports to CSV with channel grouping
- **Converter**: Handles sampling rate conversion and channel organization
- **Batch Processor**: Processes multiple ACQ files

### Marker Module (`multichsync/marker/`)
Extracts, cleans, matches, and analyzes event markers across modalities.

**Key Components:**
- **Extractor**: Pulls marker timestamps from various formats (fNIRS CSV, BrainVision .vmrk, Biopac CSV)
- **Cleaner**: Removes duplicates, filters by quality, validates data
- **Matcher**: Aligns markers across devices using Hungarian algorithm with drift correction
- **Info Extractor**: Generates subject-level reports with metadata
- **Timeline Cropper**: Crops data based on aligned timelines

**Marker Processing Pipeline:**
```
Raw Data → Extract → Clean → Match → Generate Consensus Timeline → Crop
```

### Quality Module (`multichsync/quality/`)
Performs comprehensive signal quality assessment for fNIRS data.

**Key Components:**
- **Signal Metrics**: Computes 14+ signal-level quality indicators
- **Metadata Writer**: Embeds quality results in SNIRF files
- **Batch Processor**: Processes multiple SNIRF files with summary reports
- **Resting Metrics**: Specialized metrics for resting-state data

**Quality Assessment Features:**
- Signal-to-noise ratio (SNR)
- Coefficient of variation
- Near-flatline detection
- Baseline drift index
- Physiological band power ratios
- HbO-HbR correlation analysis
- Task-based metrics (CNR, GoodEventFraction)
- Resting-state reliability (split-half)

## Data Synchronization Architecture

### Multi-Device Timeline Matching

The system uses a sophisticated matching algorithm to align event markers across devices:

```
Device A Events → Hungarian Algorithm → Consensus Timeline
Device B Events → Drift Correction → Matched Events
Device C Events → Confidence Scoring → Quality Metrics
```

**Key Algorithms:**
- **Hungarian Algorithm**: Optimal assignment of events between devices
- **Drift Correction**: Linear/Theil-Sen regression to correct clock drift
- **Confidence Scoring**: Probabilistic matching with sigma-based confidence

### Timeline Cropping

Once events are matched, the system can crop data to aligned time windows:

```
Consensus Timeline → Device-Specific Time Mapping → Crop Functions → BIDS Renaming
```

## Configuration and Metadata

### Coordinate Files
- `source_coordinates.csv`: 3D positions of fNIRS sources (T1-T8 labels)
- `detector_coordinates.csv`: 3D positions of fNIRS detectors (R1-R8 labels)

### BIDS Compliance
Output files follow Brain Imaging Data Structure (BIDS) naming conventions:
```
sub-<label>_ses-<label>_task-<label>_run-<index>_<modality>.<ext>
```

## Error Handling and Validation

Each module includes comprehensive error handling:

1. **Input Validation**: File existence, format correctness, required columns
2. **Processing Validation**: Data integrity, coordinate mapping, SNIRF compliance
3. **Output Validation**: File creation, metadata completeness

## Performance Considerations

### Batch Processing
- Parallel file processing where possible
- Progress tracking and error continuation
- Memory-efficient streaming for large files

### Large File Support
- HDF5 compression for SNIRF files
- Streaming processing for long EEG/ECG recordings
- Incremental writing for memory-constrained environments

## Extension Points

The architecture supports several extension points:

1. **New Data Formats**: Implement new parser/writer pairs
2. **New Quality Metrics**: Add to the quality assessment framework
3. **New Matching Algorithms**: Plug into the matcher interface
4. **New Output Formats**: Extend writer modules

## Dependencies and Compatibility

### Core Dependencies
- **NumPy/Pandas**: Data manipulation
- **h5py**: SNIRF HDF5 file handling
- **MNE-Python**: EEG/fNIRS processing
- **bioread**: ACQ file reading
- **pybv**: BrainVision format export

### Optional Dependencies
- **mne-nirs**: Enhanced SNIRF metadata writing
- **networkx**: Alternative matching algorithms

## Development Patterns

### Module Structure
Each major module follows a consistent pattern:
```
__init__.py     # Public API exports
parser.py       # Input file parsing
writer.py       # Output file writing
converter.py    # Core conversion logic
batch.py        # Batch processing utilities
```

### API Design
- **Functional API**: Stateless functions with clear inputs/outputs
- **CLI Integration**: Consistent argument parsing across modules
- **Error Reporting**: Detailed error messages with recovery suggestions

## Testing Strategy

The system employs a multi-layered testing approach:

1. **Unit Tests**: Individual function testing
2. **Integration Tests**: End-to-end conversion pipelines
3. **Validation Tests**: Output format compliance
4. **Performance Tests**: Large file handling

## Deployment Considerations

### Installation
- **pip install**: Standard Python package installation
- **Development mode**: `pip install -e .` for active development
- **Dependency management**: `requirements.txt` with version pinning

### Configuration
- **Environment variables**: For path configurations
- **Command-line arguments**: Full control over processing parameters
- **Configuration files**: Future support for YAML/JSON configs

## Future Architecture Directions

### Planned Enhancements
1. **Web Interface**: GUI for non-technical users
2. **Database Integration**: Track processing history and results
3. **Cloud Processing**: Distributed processing for large datasets
4. **Real-time Processing**: Live data stream integration

### Scalability Improvements
1. **Dask Integration**: Parallel processing across cores/nodes
2. **Zarr Support**: Cloud-optimized storage formats
3. **API Server**: RESTful API for remote processing

---

*Last Updated: April 2025*  
*Architecture Version: 2.0*