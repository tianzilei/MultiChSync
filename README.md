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
│  • multichsync marker basematch          • from multichsync.quality    │
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

- **fNIRS**: Convert Shimadzu/NIRS-SPM TXT → SNIRF v1.1 with MNE compatibility patching; patch existing SNIRF files (`fnirs patch`)
- **EEG**: Convert Curry/EEGLAB → BrainVision/EEGLAB/EDF with fixed sampling rate support
- **ECG**: Convert Biopac ACQ → CSV with fixed sampling rate support
- **Marker Processing**: Extract, clean, match (traversal + length‑first basematch + manual offset adjustment), and crop event markers across modalities with comprehensive reporting and drift correction
- **Quality Assessment**: Automated fNIRS signal quality evaluation with metadata embedding in SNIRF, resting‑state metrics computation, and multi‑format visualization
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

### Install with Quality Features

Quality assessment with metadata writing requires `mne-nirs`:

```bash
pip install -e ".[quality]"
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

# (Optional) Patch existing SNIRF files for MNE compatibility
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --inplace
```

### Step 2: Extract & Clean Markers

```bash
# Extract markers from all modalities
multichsync marker batch --types fnirs,ecg,eeg

# Clean markers (deduplicate, filter quality, remove start marker at t=0)
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0 --remove-start

# Generate subject-level marker reports, timeline figures, and alignment JSONs
# (alignment JSONs are consumed by `basematch --timeline-dir`)
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info
```

### Step 3: Synchronize Markers Across Devices

```bash
# --- Base match (from alignment JSONs generated by `marker info`) ---
multichsync marker basematch --timeline-dir Data/marker/info

# Manually apply offset adjustments to matched markers
multichsync marker manual-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --offsets "[1.5, -0.3, 0]" --output-dir Data/matching --prefix manual
```

### Step 4: Crop Aligned Data

```bash
# ── Mode A (recommended): Batch crop by sessions ─────────────────────
# Scans Data/matching/ for all basematched outputs,
# picks the device with the most sessions as reference per subject,
# auto-detects taskname from the original BIDS filenames, and saves
# per-session output.  Devices that can't be time-cropped (e.g. short
# eeg sessions) are copied as-is so every device has output.

# Subject mode (default): Data/matchcrop/subject-{id}/ses-{N}/...
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop

# Device mode:         Data/matchcrop/{device}/subject-{id}/ses-{N}/...
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop --output-mode device

# ── Mode B: Single subject, auto per-session split ──────────────────
# No --start-time / --end-time / --taskname needed — all auto-detected.
# Reference device = device with most sessions (falls back if shift >1000s).
multichsync marker matchcrop --json-path Data/matching/basematched_subject-001_metadata.json

# With device output mode:
multichsync marker matchcrop --json-path Data/matching/basematched_subject-001_metadata.json --output-mode device

# ── Mode C: Legacy continuous crop (requires start/end) ─────────────
multichsync marker matchcrop --json-path Data/matching/traversal_matched_subject-001_metadata.json --start-time 0.0 --end-time 300.0
```


### Step 5: Assess fNIRS Quality

```bash
# Batch quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality --l-freq 0.01 --h-freq 0.2

# Quality assessment with metadata written to SNIRF (requires mne-nirs)
multichsync quality batch-with-metadata --input-dir Data/convert/fnirs --output-dir Data/quality

# Compute resting-state metrics (split-half reliability)
multichsync quality resting-metrics --input-dir Data/convert/fnirs

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

# (Optional) Patch SNIRF files for MNE compatibility
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --inplace

# 2. Extract and clean markers
multichsync marker batch --types fnirs,ecg,eeg
multichsync marker clean --input Data/marker --inplace --min-rows 2 --min-interval 1.0

# 3. Generate marker reports, timeline figures, and alignment JSONs
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# 4. Match markers — reads alignment JSONs generated by `marker info`
multichsync marker basematch --timeline-dir Data/marker/info

# 5. Crop by session (auto‑detects ref device, taskname; copies short files as‑is)
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop
# Use --output-mode device to nest by device: {output_dir}/{device}/subject-{id}/ses-{N}/

# 6. Quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality
```

## fNIRS Patch

Existing SNIRF files can be patched for MNE compatibility (wavelength validation, HbT handling):

```bash
# Patch in-place (overwrites original)
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --inplace

# Patch to a new file
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --output Data/convert/fnirs/sub-001_fixed.snirf

# Custom dummy wavelengths
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --inplace --dummy-wavelengths 760.0 850.0

# Keep HbT in measurement list (default: move to aux)
multichsync fnirs patch --input Data/convert/fnirs/sub-001.snirf --output fixed.snirf --no-move-hbt
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

# Generate subject reports, timeline figures, and alignment JSONs
# (scans Data/convert/; alignment JSONs consumed by `basematch --timeline-dir`)
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# Crop matched timeline to shortest sequence
multichsync marker crop --timeline-csv Data/matching/matched_timeline.csv --metadata-json Data/matching/matched_metadata.json --output-prefix cropped

# Crop matched data using aligned timelines (legacy, requires --reference)
multichsync marker matchcrop --timeline-csv Data/matching/matched_timeline.csv --metadata-json Data/matching/matched_metadata.json --reference sub-060_ses-01_task-rest_fnirs --output-dir Data/matchcrop

# Auto session-split (recommended) — picks ref device, detects taskname from files
multichsync marker matchcrop --json-path Data/matching/basematched_subject-001_metadata.json

# Batch crop by sessions — scans matching dir, auto-detects everything
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop

# Batch crop, device output mode: Data/matchcrop/{device}/subject-{id}/ses-{N}/...
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop --output-mode device

# Legacy continuous crop (requires --start-time / --end-time)
multichsync marker matchcrop --json-path Data/matching/matched_metadata.json --start-time 0.0 --end-time 300.0

# Session‑based crop fallback: devices whose files are too short (e.g. eeg
# sessions < 60 s vs fnirs sessions > 300 s) are *copied as‑is* so every
# device always has output.  The reference device is automatically set to
# the device with the most sessions (down‑graded if its alignment shift
# exceeds 1000 s, i.e. a basematch artefact).

# Manually apply offset adjustments to matched markers
multichsync marker manual-match \
  --input-files sub-001_task-rest_fnirs.csv sub-001_task-rest_ecg.csv sub-001_task-rest_eeg.csv \
  --offsets "[1.5, -0.3, 0]" \
  --output-dir Data/matching --prefix manual

# Manual match with explicit device names (offset order follows device order)
multichsync marker manual-match \
  --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg \
  --device-names fnirs ecg eeg \
  --offsets "[0.5, 0.0, -0.2]" \
  --output-dir Data/matching --prefix adjusted
```

### Base Match (Length-First Alignment — ``multichsync marker basematch``)

A **session-length-first** matching strategy: instead of searching for marker-index
shifts, it groups sessions across devices to align their **start and end times**,
distributes duration differences as **gaps between sessions**, then fine-tunes
middle session positions with a light traversal.

#### Workflow:

```bash
# Step 1 — generate info reports, timeline figures, and alignment JSONs
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# Step 2 — read alignment JSONs and run basematch
multichsync marker basematch --timeline-dir Data/marker/info
```

The ``marker info`` command produces per-subject alignment JSONs
(``subject_<id>_alignment.json``) alongside the info reports and timeline
figures.  These JSONs encode the session structure and consensus start/end
alignment for all devices.

#### Alignment JSON structure

Each ``subject_<id>_alignment.json`` starts with empty alignment groups
and reference examples:

```json
{
  "subject_id": "060",
  "_example_starttime_align": [
    ["sub-060_ses-01_task-rest_fnirs.snirf",
     "sub-060_ses-01_task-rest_eeg.vhdr"]
  ],
  "_example_endtime_align": [
    ["sub-060_ses-01_task-rest_fnirs.snirf",
     "sub-060_ses-02_task-rest_fnirs.snirf",
     "sub-060_ses-01_task-rest_eeg.vhdr"]
  ],
  "starttime_align": [],
  "endtime_align": [],
  "needmatch": [
    "sub-060_ses-01_task-rest_fnirs.snirf",
    "sub-060_ses-02_task-rest_fnirs.snirf",
    "sub-060_ses-01_task-rest_eeg.vhdr"
  ],
  "devices": [
    {
      "device": "fnirs",
      "filenames": ["sub-060_ses-01_task-rest_fnirs.snirf",
                    "sub-060_ses-02_task-rest_fnirs.snirf"],
      "sequence_ids": ["01", "02"],
      "n_markers": [50, 45],
      "durations": [300.0, 300.0]
    },
    {
      "device": "eeg",
      "filenames": ["sub-060_ses-01_task-rest_eeg.vhdr"],
      "sequence_ids": ["01"],
      "n_markers": [48],
      "durations": [300.0]
    }
  ]
}
```

- ``_example_starttime_align`` / ``_example_endtime_align`` — reference
  examples showing the expected format (generated from actual filenames,
  1 cell each).  Ignored by basematch; for the user's reference only.
- ``starttime_align`` / ``endtime_align`` — start as **empty arrays**.
  The user **manually** edits these to define filename groups that should
  start (or end) at the same time, following the example format:

  ```json
  "starttime_align": [
    ["sub-060_ses-01_task-rest_fnirs.snirf",
     "sub-060_ses-01_task-rest_eeg.vhdr"]
  ],
  "endtime_align": [
    ["sub-060_ses-01_task-rest_fnirs.snirf",
     "sub-060_ses-02_task-rest_fnirs.snirf",
     "sub-060_ses-01_task-rest_eeg.vhdr"]
  ]
  ```

- ``needmatch`` — flat list of **all** filenames that participate in the
  matching.  You may **trim** this list to exclude specific files (e.g.
  corrupted recordings).  Basematch only processes files in this list.

**Basematch behaviour:**

- If ``starttime_align`` is empty → runs the full **basematch algorithm**
  (session grouping by length, gap distribution, traversal refinement)
  on the ``needmatch`` file set.
- If ``starttime_align`` has groups → **enforces both** alignment
  constraints: start groups fix session beginnings; end groups stretch/
  compress sessions so they finish at the same consensus end time.
  Files not in ``needmatch`` are skipped entirely.

**How it works:**

```
┌─ Step 1: Stack timelines ──────────────────────────────────┐
│  Sessions per device stacked end-to-end with time offsets.  │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─ Step 2: Align start / end ─────────────────────────────────┐
│  First session starts aligned at t=0 for all devices.       │
│  Last session ends aligned at t = max_total_duration.        │
│  (Proportional stretching if durations differ).             │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─ Step 3: Group sessions by length ──────────────────────────┐
│  For each reference session, greedily group consecutive     │
│  sessions from other devices whose total duration           │
│  approximates the reference session (±5 s).                 │
│                                                              │
│  Example — ref has [60s, 40s], other has [25, 30, 45]:      │
│    Group 1: session 0 + 1 (25+30=55 ≈ 60)                   │
│    Group 2: session 2 (45 ≈ 40)                             │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─ Step 4: Distribute gaps between sessions ──────────────────┐
│  Each group's total duration is adjusted to match the ref    │
│  session duration.  The difference becomes **gaps** placed   │
│  BETWEEN sessions (never inside a session).                 │
│                                                              │
│   ┌──────┐  ← gap →  ┌──────┐  ← gap →  ┌──────┐          │
│   │ Sess1 │           │ Sess2 │           │ Sess3 │          │
│   └──────┘           └──────┘           └──────┘          │
│   start fixed                                     end fixed │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─ Step 5: Traverse middle sessions ──────────────────────────┐
│  For groups with 3+ sessions, fine-tune the position of     │
│  middle sessions (±3 s in 0.2 s steps) to minimise marker   │
│  pairwise distance.  First and last sessions stay fixed.    │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─ Step 6: Match markers ─────────────────────────────────────┐
│  Greedy nearest-neighbour matching on the repositioned       │
│  timeline axis. Single-session devices use centre-alignment. │
└─────────────────────────────────────────────────────────────┘
```

**Output files** (same format as ``basematch``):

```
{prefix}_subject-{id}_timeline.csv
{prefix}_subject-{id}_stacked_timeline.csv
{prefix}_subject-{id}_metadata.json
{prefix}_subject-{id}_matched_timeline.png
```

**Key parameters:**
- ``--max-time-diff`` — maximum time difference (s) for a valid match (default: 10.0)
- ``--gap-penalty`` — cost applied to each unmatched marker (default: 1e6)
- ``--marker-base-dir`` — where marker CSV files live (default: ``Data/marker``)
- ``--no-fig`` — skip generating the matched timeline PNG (default: generate)

---

#### Python API

```python
from multichsync.marker import (
    match_traversal,
    match_traversal_from_files,
    match_traversal_from_info,
    match_baseline,
)
import numpy as np

# --- Low-level: in-memory arrays ---
result = match_traversal({
    "fnirs": np.array([0.1, 10.2, 20.1, 30.0, 40.3]),
    "ecg":   np.array([0.0, 10.0, 20.0, 30.1, 40.0, 50.2]),
    "eeg":   np.array([0.2, 10.1, 19.9, 30.2, 40.1]),
}, max_time_diff=3.0)

print(f"Mean distance: {result.mean_distance:.3f}s")
print(f"Total distance: {result.total_distance:.3f}s")
print(f"Gaps: {result.gaps}")

# --- From CSV files (legacy) ---
result = match_traversal_from_files(
    ["fnirs_marker.csv", "ecg_marker.csv", "eeg_marker.csv"],
    device_names=["fnirs", "ecg", "eeg"],
    output_dir="Data/matching",
    output_prefix="traversal_matched",
)

# --- Stacked-timeline from marker info (recommended) ---
# Returns a dict: {subject_id: TraversalMatchResult}
# Per-subject output files are saved automatically.
results = match_traversal_from_info(
    "Data/marker/info",
    marker_base_dir="Data/marker",
    convert_base_dir="Data/convert",
    max_time_diff=10.0,
    output_dir="Data/matching",
    output_prefix="traversal_matched",
)

# Iterate per-subject results
for subject_id, result in results.items():
    print(f"{subject_id}: ref={result.anchor_name}, "
          f"mean_dist={result.mean_distance:.3f}s")

# ── Per-session split (recommended) ──────────────────────────────────
from multichsync.marker.matchcrop_aligned import matchcrop_by_sessions

result = matchcrop_by_sessions(
    json_path="Data/matching/basematched_subject-001_metadata.json",
    output_dir="Data/matchcrop/subject-001",
)
# Taskname auto-detected (e.g. "rest" from _task-rest_).
# Devices too short for the session range are copied as-is.
for ses, sres in result["sessions"].items():
    for dev, dres in sres["devices"].items():
        status = dres["status"]  # "ok" | "copied_asis" | "skipped_*" | "error"
        print(f"  {ses}/{dev}: {status}")

# Device output mode nests files under device name:
#   Data/matchcrop/fnirs/subject-{id}/ses-{N}/...
result = matchcrop_by_sessions(
    json_path="Data/matching/basematched_subject-001_metadata.json",
    output_dir="Data/matchcrop",
    output_mode="device",
)

# ── Batch processing all subjects ────────────────────────────────────
from multichsync.marker.matchcrop_aligned import batch_matchcrop_from_matching_dir

results = batch_matchcrop_from_matching_dir(
    matching_dir="Data/matching",
    output_dir="Data/matchcrop",
)
# Batch report at Data/matchcrop/crop_report.json contains:
#   devices_ok, devices_copied, devices_skipped, devices_failed

# With device output mode:
results = batch_matchcrop_from_matching_dir(
    matching_dir="Data/matching",
    output_dir="Data/matchcrop",
    output_mode="device",
)

# ── Legacy continuous crop (requires start/end) ─────────────────────
from multichsync.marker.matchcrop_aligned import matchcrop_aligned
matchcrop_aligned(
    json_path="Data/matching/traversal_matched_subject-001_metadata.json",
    start_time=0.0,
    end_time=300.0,
    taskname=None,  # auto-detected
)
```

## Quality Assessment (fNIRS)

```bash
# Single-file quality assessment
multichsync quality assess --input Data/convert/fnirs/sub-001.snirf --output-dir Data/quality

# Basic batch quality assessment
multichsync quality batch --input-dir Data/convert/fnirs --output-dir Data/quality --l-freq 0.01 --h-freq 0.2

# Quality assessment with metadata written to SNIRF output (requires mne-nirs)
multichsync quality assess-with-metadata --input Data/convert/fnirs/sub-001.snirf --output-dir Data/quality

# Batch quality assessment with metadata written to SNIRF
multichsync quality batch-with-metadata --input-dir Data/convert/fnirs --output-dir Data/quality

# Compute resting-state metrics (split-half reliability)
multichsync quality resting-metrics --input-dir Data/convert/fnirs

# Generate visualization plots (single file)
multichsync quality visualize --input Data/convert/fnirs/sub-001.snirf

# Batch generate visualization plots
multichsync quality visualize-batch --input-dir Data/convert/fnirs --output-dir Data/quality
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
│   └── info/         # Subject reports + timeline figures + alignment JSONs
├── matching/         # Cross-device matching results
├── matchcrop/        # Per-session device data (cropped or copied as-is)
│   │                   # Subject mode (default):
│   ├── subject-{id}/
│   │   ├── ses-01/
│   │   │   ├── sub-{id}_ses-01_task-{task}_fnirs.snirf
│   │   │   ├── sub-{id}_ses-01_task-{task}_ecg.csv
│   │   │   ├── sub-{id}_ses-01_task-{task}_eeg.vhdr
│   │   │   ├── sub-{id}_ses-01_task-{task}_eeg.vmrk
│   │   │   ├── sub-{id}_ses-01_task-{task}_eeg.eeg
│   │   │   └── crop_metadata.json
│   │   └── ses-02/ ...
│   │                   # Device mode (--output-mode device):
│   ├── fnirs/
│   │   └── subject-{id}/
│   │       └── ses-01/
│   │           ├── sub-{id}_ses-01_task-{task}_fnirs.snirf
│   │           └── ...
│   ├── eeg/
│   │   └── subject-{id}/
│   │       └── ses-01/
│   │           └── ...
│   └── crop_report.json
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



## License

MIT License

## Contributing

Issues and pull requests are welcome. Before submitting changes:

1. Install dev dependencies: `pip install -e ".[dev]"`
2. Format code: `black multichsync tests`
3. Check lint: `ruff check multichsync tests`
4. Run type check: `mypy multichsync`
5. Ensure tests pass: `pytest --cov=multichsync -n auto`
