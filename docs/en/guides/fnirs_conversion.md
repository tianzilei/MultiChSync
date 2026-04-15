# fNIRS Conversion Guide

This guide covers the conversion of Shimadzu/NIRS-SPM TXT files to SNIRF (Shared Near Infrared Spectroscopy Format) v1.1, the standard format for fNIRS data.

## Overview

MultiChSync converts Shimadzu TXT files (exported from NIRS-SPM or Shimadzu devices) to SNIRF v1.1 format with the following features:

- **Complete SNIRF v1.1 compliance** - All required fields properly populated
- **HDF5 compression** - Optional gzip compression to reduce file size
- **Automatic event extraction** - Stim events from Mark column, aux data from Count column
- **Coordinate mapping** - Maps source/detector labels (T1-T8, R1-R8) to 3D coordinates
- **MNE-Python compatibility** - Optional patches for seamless MNE integration
- **BIDS naming** - Output files follow BIDS naming conventions

## Input Format Requirements

### Shimadzu TXT File Structure
The converter expects TXT files with the following columns:

| Column | Description | Required |
|--------|-------------|----------|
| Time(min) | Time in minutes | Yes |
| OxyHb | Oxygenated hemoglobin concentration | Yes |
| DeoxyHb | Deoxygenated hemoglobin concentration | Yes |
| TotalHb | Total hemoglobin concentration | Yes |
| Mark | Event markers (0=no event, 1=event) | No |
| Count | Counter for auxiliary data | No |
| Protocol Type | Protocol information (for marker extraction) | No |

**Note**: The converter automatically detects column names and handles variations.

### Coordinate Files
Two CSV files define the 3D positions of sources and detectors:

**source_coordinates.csv**:
```csv
label,x,y,z
T1,0.0,0.0,0.0
T2,30.0,0.0,0.0
T3,60.0,0.0,0.0
T4,90.0,0.0,0.0
T5,0.0,30.0,0.0
T6,30.0,30.0,0.0
T7,60.0,30.0,0.0
T8,90.0,30.0,0.0
```

**detector_coordinates.csv**:
```csv
label,x,y,z
R1,15.0,20.0,0.0
R2,45.0,20.0,0.0
R3,75.0,20.0,0.0
R4,105.0,20.0,0.0
R5,15.0,50.0,0.0
R6,45.0,50.0,0.0
R7,75.0,50.0,0.0
R8,105.0,50.0,0.0
```

**Requirements**:
- Labels must match the pattern `T<number>` for sources, `R<number>` for detectors
- Coordinates should be in millimeters
- All sources/detectors used in the data must be defined

## Basic Conversion

### Command Line Interface

#### Single File Conversion
```bash
multichsync fnirs convert \
  --txt-path Data/raw/fnirs/sub-001_task-rest.TXT \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output Data/convert/fnirs/sub-001_task-rest.snirf
```

#### Batch Conversion
```bash
multichsync fnirs batch \
  --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs
```

### Python API
```python
from multichsync.fnirs import convert_fnirs_to_snirf

output_path = convert_fnirs_to_snirf(
    txt_path="Data/raw/fnirs/sub-001_task-rest.TXT",
    src_coords_csv="Data/source_coordinates.csv",
    det_coords_csv="Data/detector_coordinates.csv",
    output_path="Data/convert/fnirs/sub-001_task-rest.snirf"
)
```

## Advanced Options

### HDF5 Compression
Enable gzip compression to reduce file size (enabled by default):

```bash
# Disable compression
multichsync fnirs convert ... --no-compress

# Python API
convert_fnirs_to_snirf(..., compress=False)
```

### Stim Event Extraction
The converter automatically creates stim events from the Mark column:

```bash
# Disable stim event extraction
multichsync fnirs convert ... --no-stim

# Python API
convert_fnirs_to_snirf(..., include_stim_from_mark=False)
```

### Auxiliary Data
The Count column can be included as auxiliary data:

```bash
# Exclude Count column as aux data
multichsync fnirs convert ... --no-aux-count

# Python API
convert_fnirs_to_snirf(..., include_aux_count=False)
```

### Coordinate System Specification
Define the coordinate system used:

```bash
# Specify coordinate system (default: "Other")
multichsync fnirs convert ... --coordinate-system "Other"

# Python API
convert_fnirs_to_snirf(
    ...,
    coordinate_system="Other",
    coordinate_system_description="3D coordinates in millimeter units; exact standard template/system not declared in source export."
)
```

### MNE-Python Compatibility
By default, the converter applies patches to ensure SNIRF files can be read by MNE-Python:

```bash
# Disable MNE compatibility patches
multichsync fnirs convert ... --no-mne-patch

# Python API
convert_fnirs_to_snirf(..., patch_for_mne=False)
```

**What the MNE patch does**:
1. Ensures `/nirs/probe/wavelengths` contains at least two wavelength values
2. Moves processed HbT channels from main data block to aux channels (MNE doesn't accept HbT as a channel type)
3. Adds MNE-compatible metadata tags

## MNE Compatibility Patch

### Standalone Patching
If you have existing SNIRF files that need MNE compatibility:

```bash
# Create a patched copy
multichsync fnirs patch \
  --input existing.snirf \
  --output existing_mne_fixed.snirf \
  --dummy-wavelengths 760.0 850.0

# Patch in-place (overwrites original)
multichsync fnirs patch \
  --input existing.snirf \
  --inplace \
  --no-move-hbt  # Keep HbT in main data block
```

### Python API for Patching
```python
from multichsync.fnirs import patch_snirf_for_mne, patch_snirf_inplace

# Create patched copy
patched_path = patch_snirf_for_mne(
    input_snirf="existing.snirf",
    output_snirf="existing_mne_fixed.snirf",
    dummy_wavelengths=(760.0, 850.0),
    move_hbt_to_aux=True,
    aux_name="HbT"
)

# Patch in-place
patched_path = patch_snirf_inplace(
    snirf_path="existing.snirf",
    dummy_wavelengths=(760.0, 850.0),
    move_hbt_to_aux=True,
    aux_name="HbT"
)
```

## Batch Processing

### Recursive Directory Processing
```bash
# Process all TXT files in subdirectories
multichsync fnirs batch \
  --input-dir Data/raw \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert \
  --recursive
```

### File Filtering
```bash
# Convert only files matching pattern
multichsync fnirs batch \
  --input-dir Data/raw/fnirs \
  --src-coords Data/source_coordinates.csv \
  --det-coords Data/detector_coordinates.csv \
  --output-dir Data/convert/fnirs \
  --pattern "*.TXT"

# Exclude specific patterns
multichsync fnirs batch ... --exclude "*test*" "*backup*"
```

### Progress Tracking and Error Handling
```bash
# Show progress bar
multichsync fnirs batch ... --progress

# Continue on error (skip failed files)
multichsync fnirs batch ... --continue-on-error

# Limit number of files for testing
multichsync fnirs batch ... --max-files 10
```

## Output SNIRF Structure

The generated SNIRF files contain the following structure:

```
/nirs/
├── data1
│   ├── dataTimeSeries    # HbO, HbR, HbT time series
│   ├── measurementList1  # Channel metadata
│   └── time
├── metaDataTags
│   ├── SubjectID
│   ├── MeasurementDate
│   └── ...
├── probe
│   ├── sourcePos3D
│   ├── detectorPos3D
│   ├── wavelengths
│   └── ...
├── stim1                 # From Mark column
│   ├── data
│   └── ...
└── aux1                  # From Count column
    ├── data
    └── ...
```

### BIDS Naming Convention
Output files follow BIDS naming:
```
sub-<label>_ses-<label>_task-<label>_run-<index>_fnirs.snirf
```

Example: `sub-001_ses-01_task-rest_run-01_fnirs.snirf`

## Quality Control

### Validation Checks
The converter performs several validation checks:

1. **File format validation** - Ensures TXT file can be parsed
2. **Coordinate mapping** - Verifies all source/detector labels have coordinates
3. **Data consistency** - Checks for NaN values and time monotonicity
4. **SNIRF compliance** - Validates output against SNIRF schema

### Logging and Debugging
```bash
# Enable verbose logging
multichsync fnirs convert ... --verbose

# Save log to file
multichsync fnirs batch ... --log-file conversion.log

# Debug mode (very detailed output)
multichsync fnirs convert ... --debug
```

## Troubleshooting

### Common Issues

#### 1. "Missing coordinate for source TX"
**Error**: `ValueError: Missing coordinate for source T5`

**Solution**:
- Check that `source_coordinates.csv` contains all source labels (T1-T8)
- Verify label format matches exactly (e.g., "T5" not "t5" or "T05")

#### 2. "Invalid column names"
**Error**: `KeyError: 'Time(min)' not found in columns`

**Solution**:
- Check TXT file has required columns
- Use `--header-row` to specify custom header row (0-indexed)
- Inspect file with: `head -n 5 yourfile.TXT`

#### 3. "MNE cannot read SNIRF file"
**Error**: `ValueError: wavelengths must have at least 2 entries`

**Solution**:
- Ensure MNE patch is enabled (default)
- Apply patch manually: `multichsync fnirs patch --input file.snirf --inplace`
- Check MNE version: `pip install --upgrade mne`

#### 4. "File too large" or "Memory error"
**Solution**:
- Enable compression: `--compress` (default)
- Process files individually instead of batch
- Increase system memory or use swap space

### Performance Tips

1. **Use batch processing** for multiple files (more efficient)
2. **Enable compression** for large files (smaller disk usage)
3. **Disable stim/aux extraction** if not needed (faster conversion)
4. **Process on SSD** for faster I/O
5. **Use `--max-files`** for testing before full conversion

## Python API Reference

### Core Conversion Function
```python
convert_fnirs_to_snirf(
    txt_path: Union[str, Path],
    src_coords_csv: Union[str, Path],
    det_coords_csv: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    compress: bool = True,
    include_stim_from_mark: bool = True,
    include_aux_count: bool = True,
    coordinate_system: str = "Other",
    coordinate_system_description: str = "3D coordinates in millimeter units; exact standard template/system not declared in source export.",
    patch_for_mne: bool = True,
    **kwargs
) -> Path
```

### Batch Conversion Function
```python
batch_convert_fnirs_to_snirf(
    input_dir: Union[str, Path],
    src_coords_csv: Union[str, Path],
    det_coords_csv: Union[str, Path],
    output_dir: Union[str, Path],
    pattern: str = "*.TXT",
    recursive: bool = False,
    continue_on_error: bool = False,
    max_files: Optional[int] = None,
    compress: bool = True,
    include_stim_from_mark: bool = True,
    include_aux_count: bool = True,
    patch_for_mne: bool = True,
    progress: bool = True
) -> List[Path]
```

### Patching Functions
```python
patch_snirf_for_mne(
    input_snirf: Union[str, Path],
    output_snirf: Union[str, Path],
    dummy_wavelengths: Tuple[float, float] = (760.0, 850.0),
    move_hbt_to_aux: bool = True,
    aux_name: str = "HbT"
) -> Path

patch_snirf_inplace(
    snirf_path: Union[str, Path],
    dummy_wavelengths: Tuple[float, float] = (760.0, 850.0),
    move_hbt_to_aux: bool = True,
    aux_name: str = "HbT"
) -> Path
```

## Examples

### Complete Workflow Example
```python
from pathlib import Path
from multichsync.fnirs import batch_convert_fnirs_to_snirf

# Convert all fNIRS files
converted_files = batch_convert_fnirs_to_snirf(
    input_dir=Path("Data/raw/fnirs"),
    src_coords_csv=Path("Data/source_coordinates.csv"),
    det_coords_csv=Path("Data/detector_coordinates.csv"),
    output_dir=Path("Data/convert/fnirs"),
    recursive=True,
    compress=True,
    patch_for_mne=True,
    progress=True
)

print(f"Converted {len(converted_files)} files")
```

### Custom Processing Pipeline
```python
from multichsync.fnirs import parse_shimadzu_txt, write_snirf
import pandas as pd

# Custom parsing and processing
parsed = parse_shimadzu_txt("data.TXT")

# Apply custom filters
df = parsed['data']
df['OxyHb_filtered'] = df['OxyHb'].rolling(window=10).mean()

# Write with custom metadata
write_snirf(
    output_path="custom.snirf",
    parsed=parsed,
    source_pos_3d=source_pos,
    detector_pos_3d=detector_pos,
    additional_metadata={
        'ProcessingSoftware': 'Custom Pipeline',
        'FilterType': 'MovingAverage'
    }
)
```

## Next Steps

After conversion, you can:

1. **Extract markers** for synchronization: See [Marker Processing Guide](marker_processing.md)
2. **Assess data quality**: See [Quality Assessment Guide](quality_assessment.md)
3. **Analyze with MNE-Python**: Load SNIRF files directly into MNE
4. **Share data**: SNIRF is the standard format for fNIRS data sharing

---

*Related Guides*: [EEG Conversion](eeg_conversion.md) | [ECG Conversion](ecg_conversion.md) | [Marker Processing](marker_processing.md)