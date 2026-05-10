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

# Generate per-subject multi-device timeline figures from info reports
# Stack mode: separate figure per device per subject, sorted by filename
multichsync marker timeline --input-dir Data/marker/info --output-dir Data/marker/timeline --stack
```

### Step 3: Synchronize Markers Across Devices

```bash
# Match markers using Hungarian algorithm (default) with BIDS wildcard files
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching --method hungarian

# Manually apply offset adjustments to matched markers
multichsync marker manual-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --offsets "[1.5, -0.3, 0]" --output-dir Data/matching --prefix manual

# --- Base match (recommended — session-length-first) ---
# Groups sessions across devices by duration, aligns start/end times,
# distributes gaps between sessions, then fine-tunes middle sessions.
multichsync marker basematch --info-dir Data/marker/info

# --- Traversal shift matching (alternative) ---

# Mode A (stacked-timeline): read from marker info reports
multichsync marker traversal-match --info-dir Data/marker/info

# Mode B (legacy): BIDS wildcard files (each file = one device)
multichsync marker traversal-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching

# Supported methods (marker match): hungarian (default), mincostflow, sinkhorn
# Supported methods (marker traversal-match): shift traversal with gap handling
```

### Step 4: Crop Aligned Data

```bash
# ── Mode A (recommended): Batch crop by sessions ─────────────────────
# Scans Data/matching/ for all basematched/traversal-match outputs,
# picks the device with the most sessions as reference per subject,
# auto-detects taskname from the original BIDS filenames, and saves
# per-session output.  Devices that can't be time-cropped (e.g. short
# eeg sessions) are copied as-is so every device has output.
#   Data/matchcrop/subject-{id}/ses-{N}/sub-{id}_ses-{N}_task-{auto}_{type}.ext
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop

# ── Mode B: Single subject, auto per-session split ──────────────────
# No --start-time / --end-time / --taskname needed — all auto-detected.
# Reference device = device with most sessions (falls back if shift >1000s).
multichsync marker matchcrop --json-path Data/matching/basematched_subject-001_metadata.json

# ── Mode C: Legacy continuous crop (requires start/end) ─────────────
multichsync marker matchcrop --json-path Data/matching/traversal_matched_subject-001_metadata.json --start-time 0.0 --end-time 300.0
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

# 3. Generate marker reports and timeline visualizations
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info
multichsync marker timeline --input-dir Data/marker/info --output-dir Data/marker/timeline

# 4. Match markers (stacked-timeline mode — recommended)
# Option A: length-first base matching (recommended)
multichsync marker basematch --info-dir Data/marker/info

# Option B: traversal shift matching (alternative)
multichsync marker traversal-match --info-dir Data/marker/info

# 5. Crop by session (auto‑detects ref device, taskname; copies short files as‑is)
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop

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

# Generate subject-level marker info reports (scans Data/convert/ only)
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# Generate combined timeline figure (all devices in subplot rows, sorted by sequence)
multichsync marker timeline --input-dir Data/marker/info --output-dir Data/marker/timeline

# Generate stacked timeline figures (one figure per device, sorted by filename)
multichsync marker timeline --input-dir Data/marker/info --output-dir Data/marker/timeline --stack

# Match markers across devices using BIDS wildcard files (multiple algorithms available)
multichsync marker match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --output-dir Data/matching --method hungarian

# Crop matched timeline to shortest sequence
multichsync marker crop --timeline-csv Data/matching/matched_timeline.csv --metadata-json Data/matching/matched_metadata.json --output-prefix cropped

# Crop matched data using aligned timelines (legacy, requires --reference)
multichsync marker matchcrop --timeline-csv Data/matching/matched_timeline.csv --metadata-json Data/matching/matched_metadata.json --reference sub-060_ses-01_task-rest_fnirs --output-dir Data/matchcrop

# Auto session-split (recommended) — picks ref device, detects taskname from files
multichsync marker matchcrop --json-path Data/matching/basematched_subject-001_metadata.json

# Batch crop by sessions — scans matching dir, auto-detects everything
multichsync marker matchcrop --input-dir Data/matching --output-dir Data/matchcrop

# Legacy continuous crop (requires --start-time / --end-time)
multichsync marker matchcrop --json-path Data/matching/matched_metadata.json --start-time 0.0 --end-time 300.0

# Session‑based crop fallback: devices whose files are too short (e.g. eeg
# sessions < 60 s vs fnirs sessions > 300 s) are *copied as‑is* so every
# device always has output.  The reference device is automatically set to
# the device with the most sessions (down‑graded if its alignment shift
# exceeds 1000 s, i.e. a basematch artefact).

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

The tool supports **two input modes**:

---

#### Mode A: Stacked-timeline matching (recommended — ``--info-dir``)

Reads the output of ``multichsync marker info`` and performs **session-aware
stacked-timeline matching**.  This mode handles multi-session devices
correctly by concatenating sessions end-to-end (like ``timeline --stack``).

```bash
# 1. Generate subject-level marker info reports
multichsync marker info --input-dir Data/marker --output-dir Data/marker/info

# 2. Stacked-timeline traversal match (default ±10 s tolerance)
multichsync marker traversal-match --info-dir Data/marker/info

# With explicit paths:
multichsync marker traversal-match --info-dir Data/marker/info --marker-base-dir Data/marker --convert-base-dir Data/convert --max-time-diff 10.0 --output-dir Data/matching --output-prefix my_subject
```

**How it works:**
1. **Stack sessions** — for each device, all sessions are sorted by
   ``sequence_id`` and their markers are time-offset by the cumulative sum
   of previous sessions' recording durations, forming a continuous
   **stacked timeline** (no reordering, no deletion).
2. **Reference selection** — the device with the **longest total duration**
   (sum of all its sessions) is selected as the reference.  The *actual
   total duration* is set to reference duration + *max_time_diff* (±10 s
   tolerance by default).
3. **Iterative shift refinement** — for each shorter device, a coarse-to-fine
   traversal searches all possible marker-index shifts.  The first round
   covers the full range; subsequent rounds progressively narrow the window
   around the best shift, stopping when no further improvement is found.
4. **Drift estimation** — after matching, a linear offset (median of
   matched-pair time differences) is stored per device so that downstream
   ``matchcrop-aligned`` can crop raw data correctly.

**Per-subject processing:** each ``subject_*_marker_report.csv`` is matched
independently.  Output files are named with the subject ID:

```
{prefix}_subject-{id}_timeline.csv
{prefix}_subject-{id}_stacked_timeline.csv
{prefix}_subject-{id}_metadata.json
{prefix}_subject-{id}_matched_timeline.png
```

| File | Description |
|------|-------------|
| ``{prefix}_subject-{id}_timeline.csv`` | Matched consensus groups (one row per reference marker) |
| ``{prefix}_subject-{id}_stacked_timeline.csv`` | Same groups annotated with ``_session`` columns showing which session each matched marker belongs to |
| ``{prefix}_subject-{id}_metadata.json`` | **matchcrop compatible** — consumed by ``multichsync marker matchcrop`` (contains ``device_info`` with ``converted_data_file_path`` & ``drift_correction``, and ``timeline_metadata`` with ``consensus_time_range``) |
| ``{prefix}_subject-{id}_matched_timeline.png`` | **Matched timeline figure** — each device shown as a horizontal track with session segments, marker dots (filled = matched, hollow = gap), thin match lines between adjacent devices, and match statistics in the title |

The matched timeline figure provides a quick visual overview of the
alignment quality:
- **Session segments** — coloured bars stacked end-to-end per device
  (gap sessions with 0 markers are shown with reduced opacity)
- **Marker dots** — filled circles for matched markers, hollow circles
  for gaps (unmatched reference markers)
- **Match lines** — thin gray lines connect matched markers between
  adjacent device rows (subsampled to at most 80 lines to avoid clutter)
- **Reference highlight** — the reference device track is marked with
  ``★REF`` and a coloured border
- **Statistics** — figure title shows ``matched / total`` groups and
  ``mean distance``; each device track shows its individual matched count

The per-subject metadata JSON can be consumed directly by
``multichsync marker matchcrop`` in either **session-split** or
**legacy continuous** mode:

```bash
# Session-split (recommended — auto time ranges & taskname from data)
multichsync marker matchcrop  --json-path Data/matching/traversal_matched_subject-001_metadata.json

# Legacy continuous crop (requires explicit start/end)
multichsync marker matchcrop  --json-path Data/matching/traversal_matched_subject-001_metadata.json \
  --start-time 0.0 --end-time 300.0
```

Both ``basematched`` and ``traversal_match`` metadata JSONs are supported.
The **taskname** is always auto-detected from the original BIDS filenames
(e.g. ``_task-rest_`` → ``"rest"``).

**Key parameters:**
- ``--max-time-diff`` — maximum time difference (s) for a valid match;
  also sets the ± tolerance for the reference duration window (default: 10.0)
- ``--gap-penalty`` — cost applied to each unmatched marker (default: 1e6)
- ``--random-restarts`` — random offset candidates for initial traversal (default: 5)
- ``--marker-base-dir`` — where marker CSV files live (default: ``Data/marker``)
- ``--convert-base-dir`` — where converted data files live (default: ``Data/convert``)
- ``--no-fig`` — skip generating the matched timeline PNG (default: generate)

---

#### Mode B: Legacy file-list mode (``--input-files`` / ``--input-dir``)

Each file is treated as a separate device (optionally merged by session).

```bash
# Traversal match from BIDS wildcard files
multichsync marker traversal-match --input-files *BIDS*_fnirs *BIDS*_ecg *BIDS*_eeg --max-time-diff 2.0

# Traversal match from specific marker CSV files
multichsync marker traversal-match --input-files Data/marker/fnirs/*_marker.csv Data/marker/ecg/*_marker.csv --device-names fnirs ecg --max-time-diff 2.0

# Traversal match from a directory of marker CSVs
multichsync marker traversal-match --input-dir Data/marker --max-time-diff 3.0 --gap-penalty 1000000 --random-restarts 10

# Disable session merging (each file = separate device)
multichsync marker traversal-match --input-dir Data/marker --no-merge-sessions
```

**How it works (legacy):**
1. **Anchor** — the device with the most markers is used as the reference
2. **Shift traversal** — every possible alignment offset between the anchor and each other device is evaluated
3. **Distance scoring** — each offset is scored by the mean absolute time difference across all matched pairs; gaps (unmatched markers) add a configurable penalty
4. **Random restarts** — additional random offset candidates are tested for robustness
5. **Output** — timeline CSV with per-group distances, plus a metadata JSON with gap info and shift history

**Key parameters:**
- ``--max-time-diff`` — maximum time difference (s) for a valid match (default: 3.0)
- ``--gap-penalty`` — cost applied to each unmatched marker (default: 1e6)
- ``--random-restarts`` — random offset candidates for robustness (default: 5)
- ``--no-merge-sessions`` — disable automatic session merging (default: merge)

---

### Base Match (Length-First Alignment — ``multichsync marker basematch``)

A **session-length-first** matching strategy: instead of searching for marker-index
shifts, it groups sessions across devices to align their **start and end times**,
distributes duration differences as **gaps between sessions**, then fine-tunes
middle session positions with a light traversal.

```bash
# From marker info reports (recommended)
multichsync marker basematch --info-dir Data/marker/info

# With explicit paths:
multichsync marker basematch --info-dir Data/marker/info  --marker-base-dir Data/marker \
    --convert-base-dir Data/convert  --max-time-diff 10.0 \
    --output-dir Data/matching  --output-prefix basematched
```

**How it works:**

```
┌─ Step 1: Stack timelines ──────────────────────────────────┐
│  Same as traversal-match — sessions per device stacked      │
│  end-to-end with time offsets.                              │
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

**Output files** (same format as ``traversal-match``):

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
- ``--convert-base-dir`` — where converted data files live (default: ``Data/convert``)
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

# ── Batch processing all subjects ────────────────────────────────────
from multichsync.marker.matchcrop_aligned import batch_matchcrop_from_matching_dir

results = batch_matchcrop_from_matching_dir(
    matching_dir="Data/matching",
    output_dir="Data/matchcrop",
)
# Batch report at Data/matchcrop/crop_report.json contains:
#   devices_ok, devices_copied, devices_skipped, devices_failed

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
├── matchcrop/        # Per-session device data (cropped or copied as-is)
│   ├── subject-{id}/
│   │   ├── ses-01/
│   │   │   ├── sub-{id}_ses-01_task-{task}_fnirs.snirf
│   │   │   ├── sub-{id}_ses-01_task-{task}_ecg.csv
│   │   │   ├── sub-{id}_ses-01_task-{task}_eeg.vhdr
│   │   │   ├── sub-{id}_ses-01_task-{task}_eeg.vmrk
│   │   │   ├── sub-{id}_ses-01_task-{task}_eeg.eeg
│   │   │   └── crop_metadata.json
│   │   └── ses-02/ ...
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
