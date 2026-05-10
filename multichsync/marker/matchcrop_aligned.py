"""
matchcrop_aligned: Crop multi-device data based on aligned device timelines
Uses consensus time range from marker matching and applies drift corrections.

Supports two metadata formats:
  - **Simple** (basematched): flat JSON with ``shift_history``, ``anchor``, ``devices``
  - **Rich** (traversal_match): includes ``device_info`` (with ``converted_data_file_path``,
    ``drift_correction``) and ``timeline_metadata`` (with ``consensus_time_range``)

Session-based cropping (``matchcrop_by_sessions`` / ``batch_matchcrop_from_matching_dir``):
  - Reads the stacked_timeline CSV to identify per-device session membership.
  - Picks the device with the **most sessions** as the reference.
  - For each reference session, crops ALL devices' raw data to the corresponding
    consensus time range, saving per-session output in separate sub-folders.
"""

import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .matchcrop import crop_ecg_data, crop_eeg_data, crop_fnirs_data, detect_device_type


def calculate_aligned_time_range(metadata) -> Tuple[float, float]:
    """
    Extract aligned time range from metadata.

    Prefers consensus_time_range from timeline_metadata.
    Falls back to calculating intersection of all device time_ranges.

    Parameters:
    -----------
    metadata : Dict or str
        The loaded matched_metadata.json (dict), or path to JSON file (str)

    Returns:
    --------
    Tuple[float, float]: (start_time, end_time) in consensus time
    """
    # Handle string input (file path)
    if isinstance(metadata, (str, Path)):
        json_path = Path(metadata) if isinstance(metadata, str) else metadata
        with open(json_path, "r") as f:
            metadata = json.load(f)

    timeline_meta = metadata.get("timeline_metadata", {})

    # Preferred: use consensus_time_range
    consensus_range = timeline_meta.get("consensus_time_range")
    if consensus_range and len(consensus_range) == 2:
        return (consensus_range[0], consensus_range[1])

    # Fallback: calculate intersection of device time ranges
    device_info = metadata.get("device_info", [])
    if not device_info:
        raise ValueError("No device_info found in metadata")

    # Find the overlapping range across all devices
    starts = []
    ends = []
    for dev in device_info:
        time_range = dev.get("time_range", [0, 0])
        if time_range and len(time_range) == 2:
            starts.append(time_range[0])
            ends.append(time_range[1])

    if not starts or not ends:
        raise ValueError("No valid time ranges found in device_info")

    # Return intersection (max of starts, min of ends)
    return (max(starts), min(ends))


def apply_drift_correction(consensus_time: float, drift_params: Dict) -> float:
    """
    Apply drift correction to convert consensus time to device time.

    Formula: device_time = consensus_time * scale + offset

    Parameters:
    -----------
    consensus_time : float
        Time in consensus timeline
    drift_params : Dict
        Dict with 'offset' and 'scale' keys

    Returns:
    --------
    float: Time in device's original timeline
    """
    if not drift_params:
        return consensus_time

    offset = drift_params.get("offset", 0.0)
    scale = drift_params.get("scale", 1.0)

    return consensus_time * scale + offset


def extract_taskname_from_filename(filename: str) -> Optional[str]:
    """
    Extract task name from BIDS format filename.

    Example: 'sub-068_ses-01_task-rest_fnirs' -> 'rest'
    """
    # Match pattern: _task-{taskname}_
    match = re.search(r"_task-([^_]+)_", filename)
    if match:
        return match.group(1)
    return None


def rename_bids_task(filename: str, old_taskname: str, new_taskname: str) -> str:
    """
    Rename BIDS task name in filename.

    Example: 'sub-068_ses-01_task-rest_fnirs.snirf'
             with new_taskname='mytask'
             -> 'sub-068_ses-01_task-mytask_fnirs.snirf'
    """
    # Replace the old task name with new task name
    pattern = f"_task-{old_taskname}_"
    replacement = f"_task-{new_taskname}_"

    # Handle case where task is at end before extension
    if pattern.rstrip("_") not in filename:
        pattern = f"_task-{old_taskname}(\\.|$)"
        replacement = f"_task-{new_taskname}\\1"

    return re.sub(pattern, replacement, filename)


# ──────────────────────────────────────────────────────────────────────
# New helpers: session-based batch cropping
# ──────────────────────────────────────────────────────────────────────


def _extract_subject_id(json_path: Path) -> str:
    """Extract numeric subject ID from a basematched/traversal metadata path.

    Examples::

        basematched_subject-101_metadata.json  → "101"
        traversal_matched_subject-17_metadata.json → "17"
    """
    m = re.search(r"subject[_-](\d+)", json_path.stem)
    if m:
        return m.group(1)
    # Fallback: try from the JSON's subject_id field or the containing folder
    stem = json_path.stem
    json_name = json_path.name
    json_name = json_name.replace("basematched_", "").replace("traversal_matched_", "")
    json_name = json_name.replace("_metadata.json", "").replace("_metadata", "")
    json_name = json_name.replace("subject-", "").replace("subject_", "")
    if json_name.isdigit():
        return json_name
    # Last resort: parent folder name
    return json_path.parent.stem


def _parse_stacked_csv(csv_path: Path) -> pd.DataFrame:
    """Read the stacked timeline CSV and normalise column names."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    # Strip BOM / whitespace from column names
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
    return df


def _discover_devices_from_csv(df: pd.DataFrame) -> List[str]:
    """Extract device names from stacked_timeline CSV columns.

    Device columns follow the pattern ``{device}_stacked_time``,
    ``{device}_index``, ``{device}_session``.
    """
    devices: List[str] = []
    for col in df.columns:
        # Match columns like "fnirs_stacked_time" or "fnirs_time"
        m = re.match(r"^(.+?)_(?:stacked_)?time$", col)
        if m:
            dev = m.group(1)
            if dev not in devices:
                devices.append(dev)
    return devices


def _get_reference_device(df: pd.DataFrame, devices: List[str],
                          metadata: Dict) -> str:
    """Pick the device with the **most sessions** (finest granularity).

    Falls back to ``metadata["anchor"]`` or first device on tie.
    """
    anchor = metadata.get("anchor", "")

    best_dev = None
    best_count = -1
    for dev in devices:
        ses_col = f"{dev}_session"
        if ses_col in df.columns:
            n_sessions = int(df[ses_col].dropna().nunique())
        else:
            n_sessions = 1
        if n_sessions > best_count or (n_sessions == best_count and best_dev is None):
            best_count = n_sessions
            best_dev = dev

    if best_dev is None:
        best_dev = metadata.get("anchor", devices[0] if devices else "")
    return best_dev


def _get_device_shift(metadata: Dict, device: str, anchor: str) -> float:
    """Extract the alignment shift (offset) for *device*.

    Supports both simple (basematched) and rich (traversal_match) formats.

    *Simple format:* ``metadata["shift_history"][device][-1].shift``
    *Rich format:*  ``metadata["device_info"][i].drift_correction.offset``
    """
    if device == anchor:
        return 0.0

    # Rich format: drift_correction in device_info
    device_info = metadata.get("device_info", [])
    for di in device_info:
        if di.get("name") == device:
            dc = di.get("drift_correction") or {}
            return float(dc.get("offset", 0.0))

    # Simple format: shift_history
    sh = metadata.get("shift_history", {})
    hist = sh.get(device)
    if hist and isinstance(hist, list) and len(hist) > 0:
        entry = hist[-1]
        if isinstance(entry, dict):
            return float(entry.get("shift", 0.0))
        elif isinstance(entry, (list, tuple)):
            return float(entry[0])

    return 0.0


def _find_converted_file(subject_id: str, device_type: str,
                         session_num: int,
                         convert_base_dir: str = "Data/convert",
                         metadata: Optional[Dict] = None,
                         device_name: str = "") -> Optional[Path]:
    """Locate the converted data file for a (subject, device, session).

    Five lookup strategies in order:

    1. If **rich metadata** with ``device_info`` is available, check if
       ``converted_data_file_path`` points to the right session.
    2. BIDS glob in the appropriate ``Data/convert/{type}/`` directory,
       using the subject_id as-is.
    3. Try zero-padded subject ID to 3 digits (e.g. ``"64"`` → ``"064"``).
    4. Try zero-padded to 2 digits.
    5. Broad glob for any file containing the subject_id.
    """
    base = Path(convert_base_dir)

    # Strategy 1: rich metadata → try device_info
    if metadata and device_name:
        for di in metadata.get("device_info", []):
            if di.get("name") == device_name:
                cpath = di.get("converted_data_file_path", "")
                if cpath:
                    cp = Path(cpath)
                    if cp.exists():
                        if f"ses-{session_num:02d}" in cp.stem:
                            return cp

    # Generate candidate subject IDs (padded variants)
    sid_candidates = [subject_id]
    try:
        n = int(subject_id)
        sid_candidates.append(f"{n:03d}")  # zero-padded to 3 digits
        sid_candidates.append(f"{n:02d}")  # zero-padded to 2 digits
        # Remove duplicates
        sid_candidates = list(dict.fromkeys(sid_candidates))
    except ValueError:
        pass

    # Determine search directory and extension
    if device_type == "fnirs":
        search_dir = base / "fnirs"
        ext = ".snirf"
    elif device_type == "ecg":
        search_dir = base / "ECG"
        ext = ".csv"
    elif device_type == "eeg":
        search_dir = base / "EEG"
        ext = ".vhdr"
    else:
        return None

    if not search_dir.exists():
        return None

    # Strategy 2-4: try each subject ID candidate.
    # Prefer files WITHOUT a ``_run-`` segment (canonical BIDS name).
    for sid in sid_candidates:
        pattern = f"sub-{sid}_*ses-{session_num:02d}*{device_type}*{ext}"
        matches = sorted(search_dir.glob(pattern))
        if matches:
            # Prefer file without _run-XX
            no_run = [m for m in matches if "_run-" not in m.stem.lower()]
            return (no_run[0] if no_run else matches[0])

    # Strategy 5: broad glob
    for sid in sid_candidates:
        pattern = f"*{sid}*ses-{session_num:02d}*{ext}"
        matches = sorted(search_dir.glob(pattern))
        if matches:
            no_run = [m for m in matches if "_run-" not in m.stem.lower()]
            return (no_run[0] if no_run else matches[0])

    return None


def _get_session_time_range(df: pd.DataFrame, ref_device: str,
                            session_num: int) -> Tuple[float, float]:
    """Get the consensus time range [t_start, t_end) for one reference session.

    Returns ``(NaN, NaN)`` if no markers are found for that session.
    """
    ses_col = f"{ref_device}_session"
    time_col = f"{ref_device}_stacked_time"

    # Also try without _stacked_ prefix
    if time_col not in df.columns:
        time_col = f"{ref_device}_time"

    if ses_col not in df.columns or time_col not in df.columns:
        return (float("nan"), float("nan"))

    mask = df[ses_col] == session_num
    times = df.loc[mask, time_col].dropna()

    if len(times) == 0:
        return (float("nan"), float("nan"))

    return (float(times.min()), float(times.max()))


def _find_device_session_for_ref(df: pd.DataFrame,
                                 device: str,
                                 ref_device: str,
                                 ref_session_num: int,
                                 t_start: float = 0.0,
                                 t_end: float = 0.0) -> Optional[int]:
    """Determine which session of *device* overlaps with the reference session.

    Three-pass strategy:

    1. **Marker-count pass** — count *matched* (non-gap) markers of *device*
       within the ref session's time range, grouped by device session → mode.
    2. **Time-overlap pass** — compute stacked-time boundaries for each device
       session from the CSV, pick the session with largest overlap.
    3. **Fallback** — if the device has *no* markers at all in the CSV (e.g.,
       continuous ecg recording with 0 events), assume the same session
       number as the reference.

    Returns ``None`` only when no overlap is found AND the fallback fails.
    """
    ref_ses_col = f"{ref_device}_session"
    dev_ses_col = f"{device}_session"
    dev_time_col = f"{device}_stacked_time"
    if dev_time_col not in df.columns:
        dev_time_col = f"{device}_time"
    dev_idx_col = f"{device}_index"

    # No session info at all → assume same session number
    if dev_ses_col not in df.columns:
        return ref_session_num

    # --- Pass 1: matched-marker count ────────────────────────────────
    mask = df[ref_ses_col] == ref_session_num
    if dev_idx_col in df.columns:
        mask = mask & (df[dev_idx_col].notna()) & (df[dev_idx_col] >= 0)
    if dev_time_col in df.columns and t_end > t_start:
        mask = mask & (df[dev_time_col] >= t_start - 5.0) & (df[dev_time_col] <= t_end + 5.0)

    sessions = df.loc[mask, dev_ses_col].dropna()
    if len(sessions) > 0:
        mode_val = sessions.mode()
        if len(mode_val) > 0:
            return int(mode_val.iloc[0])

    # --- Pass 2: time-overlap (even for gap rows) ───────────────────
    # Look at ALL rows where dev_ses_col is non-NaN, regardless of gap
    # status.  This handles devices that have session info but no matched
    # markers in the ref session.
    if dev_time_col in df.columns and t_end > t_start:
        ses_bounds: Dict[int, Tuple[float, float]] = {}
        for ses in sorted(df[dev_ses_col].dropna().unique()):
            ses = int(ses)
            # Use time column directly — include gaps (they have stacked_time=NaN)
            # Only use rows with valid timestamps and this session
            ses_mask = (df[dev_ses_col] == ses) & df[dev_time_col].notna()
            times = df.loc[ses_mask, dev_time_col]
            if len(times) > 0:
                ses_bounds[ses] = (float(times.min()), float(times.max()))

        if ses_bounds:
            best_ses: Optional[int] = None
            best_overlap = -1.0
            for ses, (s_start, s_end) in ses_bounds.items():
                overlap_start = max(t_start, s_start)
                overlap_end = min(t_end, s_end)
                overlap = max(0.0, overlap_end - overlap_start)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_ses = ses
            if best_ses is not None:
                return best_ses

    # --- Pass 3: fallback ────────────────────────────────────────────
    # The device may have zero markers in the CSV (all gaps, e.g.
    # continuous ecg).  Assume same session numbering as reference.
    return ref_session_num


def _old_taskname_from_metadata(metadata: Dict, devices: List[str],
                                subject_id: str = "",
                                convert_base_dir: str = "Data/convert") -> str:
    """Extract the original task name from metadata or files.

    Strategies in order:
    1. From device names that contain BIDS info (``_task-xxx_``).
    2. From ``device_info[].converted_data_file_path`` (rich metadata).
    3. From an actual converted file in ``Data/convert/{type}/``.
    4. Fall back to ``"rest"``.
    """
    # Strategy 1: BIDS pattern in device names
    for dev in devices:
        tn = extract_taskname_from_filename(dev)
        if tn:
            return tn

    # Strategy 2: from device_info converted_data_file_path
    for di in metadata.get("device_info", []):
        cpath = di.get("converted_data_file_path", "")
        tn = extract_taskname_from_filename(cpath)
        if tn:
            return tn

    # Strategy 3: scan actual files in convert directory
    if subject_id:
        base = Path(convert_base_dir)
        for sub_dir in ["fnirs", "ECG", "EEG"]:
            d = base / sub_dir
            if d.exists():
                for f in sorted(d.glob(f"sub-{subject_id}_*")):
                    tn = extract_taskname_from_filename(f.name)
                    if tn:
                        return tn

    return "rest"


def _find_stacked_csv_from_metadata(metadata: Dict,
                                    json_path: Path) -> Optional[Path]:
    """Derive the stacked timeline CSV path from metadata or JSON location."""
    # Check output_files section
    of = metadata.get("output_files", {})
    stacked_csv = of.get("stacked_timeline_csv")
    if stacked_csv:
        candidate = json_path.parent / stacked_csv
        if candidate.exists():
            return candidate

    # Check files section (simple format)
    files = metadata.get("files", {})
    basic_csv = files.get("timeline_csv")
    if basic_csv:
        # Try stacked variant
        stem = Path(basic_csv).stem.replace("_timeline", "_stacked_timeline")
        for ext in [".csv", ".CSV"]:
            candidate = json_path.parent / f"{stem}{ext}"
            if candidate.exists():
                return candidate

    # Fallback: glob from JSON's directory
    for pattern in ["*_stacked_timeline.csv", "*_stacked_timeline.CSV"]:
        matches = sorted(json_path.parent.glob(pattern))
        if matches:
            return matches[0]

    # Last resort: plain timeline CSV
    for pattern in ["*_timeline.csv", "*_timeline.CSV"]:
        matches = sorted(json_path.parent.glob(pattern))
        if matches:
            return matches[0]

    return None


def _save_crop_timeline_figure(
    df: pd.DataFrame,
    devices: List[str],
    ref_device: str,
    anchor: str,
    subject_id: str,
    session_num: int,
    t_start: float,
    t_end: float,
    shifts: Dict[str, float],
    output_path: Path,
    dpi: int = 150,
) -> None:
    """Save a timeline figure highlighting the crop window for one session.

    Each device gets a horizontal track with:
    - Coloured session bars (one colour per session).
    - Filled circles for matched markers, hollow for gaps.
    - A semi-transparent orange rectangle highlighting the crop range.
    - Session labels below the bars.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    cmap_bar = plt.colormaps.get_cmap("tab10")

    n_devices = len(devices)
    palette = {"fnirs": "#4C72B0", "eeg": "#DD8452", "ecg": "#55A868"}
    colors = [palette.get(d, "#999999") for d in devices]

    # ── X-axis range ──────────────────────────────────────────────────
    all_times = []
    for dev in devices:
        tc = f"{dev}_stacked_time"
        if tc in df.columns:
            all_times.extend(df[tc].dropna().tolist())
    if not all_times:
        all_times = [0.0, 100.0]
    t_max = max(all_times) if all_times else 100.0
    pad = max(t_max * 0.05, 10.0)
    x_lo = 0.0
    x_hi = t_max + pad

    fig_h = max(2.5, 1.6 * n_devices + 1.0)
    fig_w = min(max(10, (x_hi - x_lo) / 30 + 6), 28)
    fig, axes = plt.subplots(n_devices, 1, figsize=(fig_w, fig_h),
                             sharex=True, squeeze=False)

    for idx, dev in enumerate(devices):
        ax = axes[idx][0]
        color = colors[idx]
        is_ref = dev == ref_device
        stacked_col = f"{dev}_stacked_time"
        index_col = f"{dev}_index"
        session_col = f"{dev}_session"

        # ── Gather markers (keep NaN so shapes match df rows) ────────
        marker_times = df[stacked_col].values if stacked_col in df.columns else np.full(len(df), np.nan)
        marker_indices = df[index_col].values if index_col in df.columns else np.full(len(df), -1)
        session_vals = df[session_col].values if session_col in df.columns else np.full(len(df), np.nan)

        # ── Background track ──────────────────────────────────────────
        ax.axhline(y=0, xmin=0, xmax=1, color="#dddddd",
                   linewidth=2, alpha=0.3, zorder=0)

        # ── Session bars from stacked_time boundaries ─────────────────
        if session_col in df.columns and stacked_col in df.columns:
            ses_boundaries: Dict[int, Tuple[float, float]] = {}
            for ses in sorted(df[session_col].dropna().unique()):
                ses = int(ses)
                mask = df[session_col] == ses
                if index_col in df.columns:
                    mask = mask & (df[index_col].notna()) & (df[index_col] >= 0)
                ses_times = df.loc[mask, stacked_col].dropna()
                if len(ses_times) > 0:
                    ses_boundaries[ses] = (float(ses_times.min()), float(ses_times.max()))

            for ses_i, (s_start, s_end) in sorted(ses_boundaries.items()):
                dur = s_end - s_start
                if dur < 0.5:
                    dur = 0.5
                ax.barh(0, dur, height=0.55, left=s_start,
                        color=cmap_bar(ses_i % 10), alpha=0.85,
                        edgecolor="#222222", linewidth=0.5, zorder=0)

            # Session labels
            for ses_i, (s_start, s_end) in sorted(ses_boundaries.items()):
                cx = (s_start + s_end) / 2.0
                ax.text(cx, -0.45, f"S{ses_i}",
                        ha="center", fontsize=4.5, color="#444444",
                        fontweight="bold")

        # ── Matched markers (filled) ──────────────────────────────────
        valid_time = ~np.isnan(marker_times)
        if np.any(valid_time):
            matched_mask = valid_time & (marker_indices >= 0)
            if np.any(matched_mask):
                ax.scatter(marker_times[matched_mask], np.zeros_like(marker_times[matched_mask]),
                           marker="o", s=8, color=color, edgecolors="white",
                           linewidths=0.2, zorder=3, alpha=0.7)

            # ── Gap markers (hollow, at ref positions) ────────────────
            gap_mask = valid_time & (marker_indices == -1)
            if np.any(gap_mask):
                ax.scatter(marker_times[gap_mask], np.zeros_like(marker_times[gap_mask]),
                           marker="o", s=6, facecolors="none",
                           edgecolors=color, linewidths=0.5, alpha=0.4,
                           zorder=3)

        # ── Crop window highlight ─────────────────────────────────────
        crop_dur = t_end - t_start
        if crop_dur > 0:
            ax.axvspan(t_start, t_end, ymin=0.1, ymax=0.9,
                       color="orange", alpha=0.2, zorder=4)

        # ── Per-device match count ────────────────────────────────────
        n_matched = int(np.sum(marker_indices >= 0)) if len(marker_indices) == len(df) else 0
        n_total = len(df)
        ax.text(x_hi - pad * 0.1, 0,
                f"{n_matched}/{n_total}",
                ha="right", va="center", fontsize=7, color=color,
                fontweight="bold")

        # ── Axis styling ──────────────────────────────────────────────
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(-0.55, 0.65)
        ax.set_yticks([0])
        label = dev.upper()
        if is_ref:
            label += " ★REF"
        ax.set_yticklabels([label], fontsize=9,
                           fontweight="bold" if is_ref else "normal",
                           color=color)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", alpha=0.12, linestyle="--")
        if is_ref:
            for sp in ax.spines.values():
                sp.set_color(color)
                sp.set_linewidth(2.0)

    # ── Title ─────────────────────────────────────────────────────────
    ses_bids = f"ses-{session_num:02d}"
    axes[-1][0].set_xlabel("Time (seconds)", fontsize=9)
    fig.suptitle(
        f"Subject {subject_id} — {ses_bids}  |  crop: [{t_start:.1f}s, {t_end:.1f}s]\n"
        f"ref: {ref_device}  |  anchor: {anchor}",
        fontsize=11, fontweight="bold", y=0.97,
    )

    legend_elements = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#555555",
                   markersize=5, label="Matched marker"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="none",
                   markeredgecolor="#555555", markersize=4, label="Gap"),
        plt.Rectangle((0, 0), 1, 1, color="orange", alpha=0.3, label="Crop window"),
    ]
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=3, frameon=True, fontsize=7,
               bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.05, 1, 0.93])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"    Saved crop timeline → {output_path.name}")


def _copy_file_to_output(
    converted_file: Path, device_type: str,
    output_dir: Path, final_bids_stem: str,
) -> None:
    """Copy a device file to the output directory with the BIDS-renamed name.

    Used as fallback when cropping is not possible (file too short,
    shift mismatch, etc.).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if device_type == "fnirs":
        out = output_dir / f"{final_bids_stem}.snirf"
        shutil.copy2(converted_file, out)
    elif device_type == "ecg":
        out = output_dir / f"{final_bids_stem}.csv"
        shutil.copy2(converted_file, out)
    elif device_type == "eeg":
        for ext in [".vhdr", ".vmrk", ".eeg"]:
            src = converted_file.parent / f"{converted_file.stem}{ext}"
            if src.exists():
                new_name = f"{final_bids_stem}{ext}"
                dst = output_dir / new_name
                shutil.copy2(src, dst)


def _quick_file_duration(file_path: Path, device_type: str) -> Optional[float]:
    """Quickly estimate the duration of a data file without full load.

    Returns ``None`` if duration cannot be determined.
    """
    try:
        if device_type == "fnirs":
            import h5py
            with h5py.File(file_path, "r") as f:
                times = f["nirs/data1/time"][:]
                return float(times[-1] - times[0]) if len(times) > 1 else None
        elif device_type == "ecg":
            df = pd.read_csv(file_path, nrows=5)
            for col in ["Time(sec)", "time", "Time", "reference_time"]:
                if col in df.columns:
                    vals = pd.to_numeric(df[col], errors="coerce").dropna()
                    return float(vals.max() - vals.min()) if len(vals) > 1 else None
            return None
        elif device_type == "eeg":
            import mne
            raw = mne.io.read_raw_brainvision(file_path, preload=False, verbose=False)
            return raw.times[-1] - raw.times[0]
    except Exception:
        return None


def matchcrop_by_sessions(
    json_path: Path,
    output_dir: Optional[Path] = None,
    taskname: Optional[str] = None,
    stacked_csv_path: Optional[Path] = None,
    convert_base_dir: str = "Data/convert",
) -> Dict:
    """Crop multi-device data **per session**, one sub-directory per session.

    The **taskname** is auto-detected from the original BIDS filenames
    (e.g. ``_task-rest_`` → ``"rest"``).  Pass an explicit *taskname*
    to rename the task in output files.

    Workflow
    --------
    1. Read metadata JSON (simple or rich format).
    2. Read the stacked timeline CSV → discover devices & session counts.
    3. Pick the **device with the most sessions** as reference.
    4. For every reference session:
       a. Determine the consensus time range from the reference device's
          ``_stacked_time`` column.
       b. For each device, look up its alignment shift and find the
          appropriate converted data file.
       c. Crop the device's raw data to that session's consensus range.
       d. Save output to ``{output_dir}/ses-{N}/`` with the task name.

    Parameters
    ----------
    json_path : Path
        Path to ``basematched_subject-{id}_metadata.json`` (simple format) or
        the traversal-match equivalent (rich format with ``device_info``).
    output_dir : Path, optional
        Root output directory.  Defaults to ``{matching_dir}/../matchcrop/subject-{id}/``.
    taskname : str, optional
        New BIDS task name for output files.  If ``None`` (default),
        the original task name from the data files is kept unchanged.
    stacked_csv_path : Path, optional
        Path to the stacked timeline CSV.  Auto-detected from metadata if
        not provided.
    convert_base_dir : str
        Base directory for converted data (default: ``Data/convert``).

    Returns
    -------
    Dict
        Processing summary with per-session and per-device results.
    """
    if isinstance(json_path, str):
        json_path = Path(json_path)

    # ── 1. Load metadata ──────────────────────────────────────────────
    if not json_path.exists():
        raise FileNotFoundError(f"Metadata JSON not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    subject_id = _extract_subject_id(json_path)
    anchor = metadata.get("anchor", "")
    devices_meta = metadata.get("devices", [])

    # ── 2. Read stacked timeline CSV ──────────────────────────────────
    if stacked_csv_path is None:
        stacked_csv_path = _find_stacked_csv_from_metadata(metadata, json_path)
    if stacked_csv_path is None or not stacked_csv_path.exists():
        raise FileNotFoundError(
            f"Stacked timeline CSV not found for {json_path.name}. "
            "Please provide --stacked-csv."
        )

    df = _parse_stacked_csv(stacked_csv_path)
    devices_csv = _discover_devices_from_csv(df)
    all_devices = devices_csv or devices_meta

    if not all_devices:
        raise ValueError("No devices found in metadata or stacked CSV")

    # ── 3. Pick reference device (most sessions) ──────────────────────
    ref_device = _get_reference_device(df, all_devices, metadata)
    print(f"\nSubject {subject_id}:")
    print(f"  Reference device: {ref_device} (most sessions)")

    # ── 4. Collect shifts for all devices ─────────────────────────────
    shifts: Dict[str, float] = {}
    for dev in all_devices:
        shifts[dev] = _get_device_shift(metadata, dev, anchor)
    print(f"  Shifts: {shifts}")

    # ── 5. Determine output root ──────────────────────────────────────
    if output_dir is None:
        output_dir = json_path.parent.parent / "matchcrop" / f"subject-{subject_id}"
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    # ── 6. Extract old task name ──────────────────────────────────────
    old_taskname = _old_taskname_from_metadata(metadata, all_devices,
                                               subject_id=subject_id,
                                               convert_base_dir=convert_base_dir)

    # ── 7. Build reference session list ───────────────────────────────
    # Include both marker-bearing sessions from stacked_timeline AND
    # markerless sessions that exist in the convert directory (e.g. eeg
    # ses-02 with 0 markers).  For the latter we estimate the time range
    # from adjacent marker-bearing sessions.
    ses_col = f"{ref_device}_session"
    ref_session_nums = sorted(
        int(s) for s in df[ses_col].dropna().unique()
    ) if ses_col in df.columns else []

    # Discover additional sessions from convert directory (0-marker)
    ref_type = detect_device_type(ref_device)
    extra_sessions: List[int] = []
    for alt_ses in range(1, 50):
        if alt_ses in ref_session_nums:
            continue
        alt_file = _find_converted_file(
            subject_id, ref_type, alt_ses,
            convert_base_dir=convert_base_dir,
        )
        if alt_file is not None:
            extra_sessions.append(alt_ses)
    if extra_sessions:
        print(f"  Additional 0-marker sessions from convert: {extra_sessions}")
        ref_session_nums = sorted(set(ref_session_nums) | set(extra_sessions))

    if not ref_session_nums:
        ref_session_nums = [1]

    # Pre-compute existing session boundaries for NaN fallback
    _ses_boundary: Dict[int, Tuple[float, float]] = {}
    if ses_col in df.columns:
        for ses in sorted(df[ses_col].dropna().unique()):
            ses = int(ses)
            s_start, s_end = _get_session_time_range(df, ref_device, ses)
            if not np.isnan(s_start):
                _ses_boundary[ses] = (s_start, s_end)

    print(f"  Sessions: {ref_session_nums}")
    print(f"  Task: {old_taskname} -> {taskname or old_taskname}")
    print()

    results: Dict[str, Any] = {
        "subject_id": subject_id,
        "reference_device": ref_device,
        "anchor": anchor,
        "taskname": taskname or old_taskname,
        "output_root": str(output_root),
        "sessions": {},
        "errors": [],
    }

    for ses_num in ref_session_nums:
        ses_bids = f"ses-{ses_num:02d}"
        ses_dir = output_root / ses_bids
        ses_dir.mkdir(parents=True, exist_ok=True)

        # Get consensus time range for this session
        t_start, t_end = _get_session_time_range(df, ref_device, ses_num)

        # ── Fallback for 0‑marker sessions ────────────────────────────
        if np.isnan(t_start) or np.isnan(t_end):
            # Compute from adjacent marker-bearing sessions + file duration
            _sorted = sorted(_ses_boundary.keys())
            _prev = max((s for s in _sorted if s < ses_num), default=None)
            _next = min((s for s in _sorted if s > ses_num), default=None)
            _prev_end = _ses_boundary[_prev][1] if _prev is not None else 0.0
            _next_start = _ses_boundary[_next][0] if _next is not None else None

            # Get this session's file duration
            _ref_file = _find_converted_file(
                subject_id, ref_type, ses_num,
                convert_base_dir=convert_base_dir,
            )
            _file_dur = _quick_file_duration(_ref_file, ref_type) if _ref_file else None

            if _file_dur is not None and _file_dur > 0:
                t_est_start = _prev_end
                t_est_end = _prev_end + _file_dur
                if _next_start is not None and t_est_end > _next_start:
                    t_est_end = _next_start  # cap at next session start
                t_start, t_end = t_est_start, t_est_end
                print(f"  [{ses_bids}] Estimated range: {t_start:.3f}s - {t_end:.3f}s "
                      f"(file duration {_file_dur:.0f}s, no markers)")

        if np.isnan(t_start) or np.isnan(t_end):
            msg = f"  [{ses_bids}] Skipped (0 markers, cannot estimate range)"
            print(msg)
            results["errors"].append(msg)
            continue

        print(f"  [{ses_bids}] Time range: {t_start:.3f}s - {t_end:.3f}s")

        ses_result: Dict[str, Any] = {
            "time_range": [float(t_start), float(t_end)],
            "devices": {},
        }

        for device in all_devices:
            device_type = detect_device_type(device)
            shift = shifts.get(device, 0.0)

            # Determine which session file of THIS device to use.
            # For the reference device itself the session is always ses_num
            # (skip overlap-based lookup which fails for 0‑marker sessions).
            if device == ref_device:
                dev_ses = ses_num
            else:
                dev_ses = _find_device_session_for_ref(
                    df, device, ref_device, ses_num,
                    t_start=t_start, t_end=t_end,
                )
            if dev_ses is None:
                msg = f"    {device}: no data in this session range (gaps), skipped"
                print(msg)
                ses_result["devices"][device] = {"status": "skipped_gap", "reason": msg}
                continue

            # Find the converted data file (try exact session match first)
            converted_file = _find_converted_file(
                subject_id, device_type, dev_ses,
                convert_base_dir=convert_base_dir,
                metadata=metadata,
                device_name=device,
            )
            if converted_file is None:
                converted_file = _find_converted_file(
                    subject_id, device_type, dev_ses,
                    convert_base_dir=convert_base_dir,
                )

            # Fallback: try ALL available session files for this device.
            # This handles continuous recordings (ecg) that have only 1-2
            # session files while the reference device has many sessions.
            if converted_file is None:
                for alt_ses in range(1, 50):
                    if alt_ses == dev_ses:
                        continue
                    alt_file = _find_converted_file(
                        subject_id, device_type, alt_ses,
                        convert_base_dir=convert_base_dir,
                    )
                    if alt_file is not None:
                        converted_file = alt_file
                        print(f"    {device}: using ses-{alt_ses:02d} file "
                              f"(fallback for ses-{dev_ses:02d})")
                        break

            if converted_file is None:
                msg = f"    {device}: converted file not found for ses-{dev_ses:02d}, skipped"
                print(msg)
                ses_result["devices"][device] = {"status": "file_not_found", "reason": msg}
                results["errors"].append(msg)
                continue

            # Compute effective shift for this (device, session).
            #
            # The stacked_time for each device stores the ALIGNED time in
            # the consensus (anchor) timeline.  For the anchor device itself,
            # stacked_time = original_time (no shift).  For non‑anchor
            # devices, stacked_time = original_time + alignment_offset.
            #
            # To crop we must convert consensus_time → device_original_time:
            #   device_original = consensus_time - alignment_offset
            #
            # alignment_offset = dev_start_consensus (the first marker's
            # stacked_time), because the device's session file starts at
            # time 0 in its own coordinate system.
            effective_shift = 0.0  # default: no alignment offset
            dev_stacked = f"{device}_stacked_time"
            dev_idx_c = f"{device}_index"
            dev_ses_c = f"{device}_session"

            # Compute device session's actual start in consensus timeline
            session_start = 0.0  # fallback
            if dev_stacked in df.columns and dev_ses_c in df.columns:
                dev_mask = (df[dev_ses_c] == dev_ses)
                if dev_idx_c in df.columns:
                    dev_mask = dev_mask & (df[dev_idx_c].notna()) & (df[dev_idx_c] >= 0)
                dev_times = df.loc[dev_mask, dev_stacked].dropna()
                if len(dev_times) > 0:
                    session_start = float(dev_times.min())
                elif device == ref_device:
                    # 0‑marker reference session: estimated t_start IS the
                    # session's start in consensus (see NaN fallback above).
                    session_start = t_start
            # The offset from consensus to device's session start maps the
            # first marker (device original ≈ 0) to its consensus position.
            effective_shift = session_start

            device_start = t_start - effective_shift
            device_end = t_end - effective_shift
            shift_sane = True
            if device_start < -300.0 and device_end < -300.0:
                msg = (f"    {device}: device time range [{device_start:.1f}, "
                       f"{device_end:.1f}]s is far negative "
                       f"(effective_shift={effective_shift:.1f}s), skipped")
                print(msg)
                ses_result["devices"][device] = {"status": "skipped_shift_mismatch", "reason": msg}
                shift_sane = False
            if shift_sane and device_start > 1e8:
                msg = (f"    {device}: device time start {device_start:.0f}s is "
                       f"suspiciously large (effective_shift={effective_shift:.1f}s), "
                       f"skipped")
                print(msg)
                ses_result["devices"][device] = {"status": "skipped_shift_mismatch", "reason": msg}
                shift_sane = False
            # Build output BIDS filename from the actual data file.
            # e.g. "sub-100_ses-01_task-rest_fnirs.snirf"
            #   → "sub-100_ses-01_task-synchronized_fnirs.snirf"
            final_bids_stem = rename_bids_task(
                converted_file.stem, old_taskname, taskname or old_taskname
            )

            if not shift_sane:
                # Shift mismatch → copy file as-is instead of cropping
                _copy_file_to_output(converted_file, device_type, ses_dir, final_bids_stem)
                msg = (f"    {device}: shift mismatch, copied {converted_file.name} as-is "
                       f"→ {final_bids_stem}.*")
                print(msg)
                ses_result["devices"][device] = {"status": "copied_asis", "reason": msg}
                continue

            print(f"    {device}: cropping from {converted_file.name} "
                  f"(effective_shift={effective_shift:+.2f}s, "
                  f"device_range=[{device_start:.1f}, {device_end:.1f}])"
                  f" → {final_bids_stem}.*")

            try:
                # Call low-level crop functions directly for precise naming.
                # Use effective_shift (per-session offset from stacked_timeline)
                # instead of the raw metadata shift (total_gap).
                if device_type == "fnirs":
                    out_path = ses_dir / f"{final_bids_stem}.snirf"
                    crop_result = crop_fnirs_data(
                        input_file=converted_file,
                        output_file=out_path,
                        start_time=t_start,
                        end_time=t_end,
                        device_offset=effective_shift,
                    )
                elif device_type == "ecg":
                    out_path = ses_dir / f"{final_bids_stem}.csv"
                    crop_result = crop_ecg_data(
                        input_file=converted_file,
                        output_file=out_path,
                        start_time=t_start,
                        end_time=t_end,
                        device_offset=effective_shift,
                    )
                elif device_type == "eeg":
                    import tempfile

                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmp_out = Path(tmpdir) / "eeg_out"
                        crop_result = crop_eeg_data(
                            input_file=converted_file,
                            output_dir=tmp_out,
                            start_time=t_start,
                            end_time=t_end,
                            device_offset=effective_shift,
                        )
                        ses_dir.mkdir(parents=True, exist_ok=True)
                        for ext in [".vhdr", ".vmrk", ".eeg"]:
                            for src in tmp_out.glob(f"*{ext}"):
                                new_name = rename_bids_task(
                                    src.name, old_taskname, taskname or old_taskname
                                )
                                dst = ses_dir / new_name
                                shutil.copy2(src, dst)
                else:
                    raise ValueError(f"Unknown device type: {device_type}")

                ses_result["devices"][device] = {
                    "status": "ok",
                    "output": crop_result,
                }
            except ValueError as e:
                # Crop range outside file bounds → copy file as-is
                _copy_file_to_output(converted_file, device_type, ses_dir, final_bids_stem)
                msg = (f"    {device}: crop range outside data, copied "
                       f"{converted_file.name} as-is → {final_bids_stem}.*")
                print(msg)
                ses_result["devices"][device] = {"status": "copied_asis", "reason": msg}
            except Exception as e:
                msg = f"    {device}: crop failed: {e}"
                print(msg)
                import traceback
                traceback.print_exc()
                ses_result["devices"][device] = {"status": "error", "error": str(e), "reason": msg}
                results["errors"].append(msg)
        # Count per-session stats
        n_ok = sum(1 for d in ses_result["devices"].values() if d.get("status") == "ok")
        n_skip = sum(1 for d in ses_result["devices"].values()
                     if d.get("status") in ("skipped_gap", "skipped_shift_mismatch",
                                            "skipped_crop_range", "file_not_found"))
        n_copy = sum(1 for d in ses_result["devices"].values() if d.get("status") == "copied_asis")
        n_fail = sum(1 for d in ses_result["devices"].values() if d.get("status") == "error")
        ses_result["stats"] = {"ok": n_ok, "copied_asis": n_copy,
                               "skipped": n_skip, "failed": n_fail}

        # Save per-session metadata
        ses_meta = {
            "subject_id": subject_id,
            "session": ses_bids,
            "reference_device": ref_device,
            "time_range": [float(t_start), float(t_end)],
            "devices": {
                d: {"status": ses_result["devices"][d].get("status")}
                for d in ses_result["devices"]
            },
        }
        meta_path = ses_dir / "crop_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(ses_meta, f, indent=2)

        # Save crop timeline figure (shows the crop window overlaid)
        try:
            fig_path = ses_dir / f"crop_timeline_{ses_bids}.png"
            _save_crop_timeline_figure(
                df=df,
                devices=all_devices,
                ref_device=ref_device,
                anchor=anchor,
                subject_id=subject_id,
                session_num=ses_num,
                t_start=t_start,
                t_end=t_end,
                shifts=shifts,
                output_path=fig_path,
            )
        except Exception as e:
            print(f"    Warning: could not save crop timeline figure ({e})")

        results["sessions"][ses_bids] = ses_result

    # ── 9. Save no-crop report (devices not successfully cropped) ─────
    no_crop_entries: List[Dict] = []
    for ses_bids, ses_res in results.get("sessions", {}).items():
        for dev, dev_res in ses_res.get("devices", {}).items():
            status = dev_res.get("status")
            if status != "ok":
                no_crop_entries.append({
                    "session": ses_bids,
                    "device": dev,
                    "status": status,
                    "reason": dev_res.get("reason", dev_res.get("error", str(status))),
                })

    if no_crop_entries:
        no_crop_report = {
            "subject_id": subject_id,
            "taskname": taskname or old_taskname,
            "no_crop_devices": no_crop_entries,
        }
        no_crop_path = output_root / "no_crop_report.json"
        with open(no_crop_path, "w", encoding="utf-8") as f:
            json.dump(no_crop_report, f, indent=2)
        print(f"  No-crop report saved: {no_crop_path}")

    return results


def batch_matchcrop_from_matching_dir(
    matching_dir: str = "Data/matching",
    output_dir: str = "Data/matchcrop",
    taskname: Optional[str] = None,
    convert_base_dir: str = "Data/convert",
) -> Dict:
    """Scan a matching directory and crop by sessions for every subject.

    Looks for ``*_metadata.json`` files (both basematched and
    traversal_match prefixes), groups them by subject, and runs
    :func:`matchcrop_by_sessions` for each.

    The **taskname** is auto-detected from the original BIDS filenames
    in the convert directory (e.g. ``_task-rest_`` → task ``"rest"``).
    Pass an explicit value to override (renames the task in output files).

    Parameters
    ----------
    matching_dir : str
        Directory containing the matching outputs
        (e.g. ``basematched_subject-101_metadata.json``).
    output_dir : str
        Root output directory.  Per-subject results go into
        ``{output_dir}/subject-{id}/``.
    taskname : str, optional
        New BIDS task name for cropped files.  If ``None`` (default),
        the original task name from the data files is preserved.
    convert_base_dir : str
        Base directory for converted raw data.

    Returns
    -------
    Dict
        Summary keyed by subject ID.
    """
    match_path = Path(matching_dir)
    if not match_path.exists():
        raise FileNotFoundError(f"Matching directory not found: {match_path}")

    # Find all metadata JSONs (both basematched and traversal)
    json_files = sorted(match_path.glob("*_metadata.json"))
    if not json_files:
        raise FileNotFoundError(f"No *_metadata.json files found in {match_path}")

    # Group by subject ID
    subject_groups: Dict[str, List[Path]] = defaultdict(list)
    for jf in json_files:
        sid = _extract_subject_id(jf)
        subject_groups[sid].append(jf)

    overall_results: Dict[str, Any] = {}
    total_ok = 0
    total_err = 0

    print(f"\n{'='*60}")
    print(f"Batch matchcrop-by-sessions from: {matching_dir}")
    print(f"Output root: {output_dir}")
    print(f"Task name:   {taskname}")
    print(f"{'='*60}")

    for subject_id in sorted(subject_groups):
        jsons = subject_groups[subject_id]
        # Prefer the richer metadata (device_info present) if multiple JSOns
        chosen_json = jsons[0]
        for jf in jsons:
            with open(jf, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if "device_info" in meta and meta["device_info"]:
                chosen_json = jf
                break

        subj_output = Path(output_dir) / f"subject-{subject_id}"
        print(f"\n{'─'*50}")
        print(f"Subject {subject_id} → {subj_output}")

        try:
            result = matchcrop_by_sessions(
                json_path=chosen_json,
                output_dir=subj_output,
                taskname=taskname,
                convert_base_dir=convert_base_dir,
            )
            overall_results[subject_id] = result
            n_sessions = len(result.get("sessions", {}))
            n_errors = len(result.get("errors", []))
            total_ok += 1
            print(f"  Done: {n_sessions} session(s), {n_errors} error(s)")
        except Exception as e:
            total_err += 1
            err_msg = f"Subject {subject_id}: FAILED — {e}"
            print(f"  {err_msg}")
            overall_results[subject_id] = {"error": str(e)}

    # Save a batch report
    report_path = Path(output_dir) / "crop_report.json"
    total_ok_devices = 0
    total_copied = 0
    total_skipped = 0
    total_failed = 0
    subject_results = {}
    for sid, r in overall_results.items():
        if not isinstance(r, dict) or "sessions" not in r:
            subject_results[sid] = {"status": "error", "n_sessions": 0}
            continue
        n_ses = len(r["sessions"])
        n_ok = sum(s.get("stats", {}).get("ok", 0) for s in r["sessions"].values())
        n_copy = sum(s.get("stats", {}).get("copied_asis", 0) for s in r["sessions"].values())
        n_skip = sum(s.get("stats", {}).get("skipped", 0) for s in r["sessions"].values())
        n_fail = sum(s.get("stats", {}).get("failed", 0) for s in r["sessions"].values())
        total_ok_devices += n_ok
        total_copied += n_copy
        total_skipped += n_skip
        total_failed += n_fail
        subject_results[sid] = {
            "n_sessions": n_ses,
            "devices_ok": n_ok,
            "devices_copied": n_copy,
            "devices_skipped": n_skip,
            "devices_failed": n_fail,
        }
    # Determine effective taskname from first successful subject
    effective_taskname = taskname
    if effective_taskname is None:
        for sid, r in overall_results.items():
            tn = r.get("taskname") if isinstance(r, dict) else None
            if tn:
                effective_taskname = tn
                break
    report = {
        "taskname": effective_taskname,
        "convert_base_dir": convert_base_dir,
        "matching_dir": matching_dir,
        "subjects_total": len(overall_results),
        "devices_ok": total_ok_devices,
        "devices_copied": total_copied,
        "devices_skipped": total_skipped,
        "devices_failed": total_failed,
        "subject_results": subject_results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Save batch-level no-crop report
    all_no_crop_entries: List[Dict] = []
    for sid, r in overall_results.items():
        if not isinstance(r, dict) or "sessions" not in r:
            continue
        for ses_bids, ses_res in r.get("sessions", {}).items():
            for dev, dev_res in ses_res.get("devices", {}).items():
                status = dev_res.get("status")
                if status != "ok":
                    all_no_crop_entries.append({
                        "subject_id": sid,
                        "session": ses_bids,
                        "device": dev,
                        "status": status,
                        "reason": dev_res.get("reason", dev_res.get("error", str(status))),
                    })

    if all_no_crop_entries:
        no_crop_report = {
            "taskname": effective_taskname,
            "no_crop_devices": all_no_crop_entries,
        }
        no_crop_path = Path(output_dir) / "no_crop_report.json"
        with open(no_crop_path, "w", encoding="utf-8") as f:
            json.dump(no_crop_report, f, indent=2)
        print(f"No-crop report saved: {no_crop_path}")

    print(f"\n{'='*60}")
    print(f"Batch complete: {total_ok} OK, {total_err} failed")
    print(f"Report saved: {report_path}")
    print(f"{'='*60}")

    return overall_results


# ── Existing code below ──────────────────────────────────────────────


def crop_and_rename_device(
    device_info: Dict,
    crop_start_consensus: float,
    crop_end_consensus: float,
    output_dir: Path,
    old_taskname: str,
    new_taskname: str,
) -> Dict:
    """
    Crop one device's data and rename output files.

    Parameters:
    -----------
    device_info : Dict
        Device info from matched_metadata.json
    crop_start_consensus : float
        Start time in consensus timeline
    crop_end_consensus : float
        End time in consensus timeline
    output_dir : Path
        Output directory
    old_taskname : str
        Original task name (for renaming)
    new_taskname : str
        New task name (to rename to)

    Returns:
    --------
    Dict: Crop result with output files info
    """
    device_name = device_info["name"]
    device_type = detect_device_type(device_name)
    converted_file_path = device_info.get("converted_data_file_path")

    if not converted_file_path:
        raise ValueError(f"No converted_data_file_path for device: {device_name}")

    input_file = Path(converted_file_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Data file not found: {input_file}")

    # Get drift correction for this device
    drift_corrections = device_info.get("drift_correction") or {}
    offset = drift_corrections.get("offset", 0.0)
    scale = drift_corrections.get("scale", 1.0)

    # Crop the data using existing functions
    if device_type == "ecg":
        # ECG: output is CSV file
        output_filename = f"{device_name}_ecg.csv"
        output_filename = rename_bids_task(output_filename, old_taskname, new_taskname)
        output_file = output_dir / output_filename

        result = crop_ecg_data(
            input_file=input_file,
            output_file=output_file,
            start_time=crop_start_consensus,
            end_time=crop_end_consensus,
            device_offset=offset,
        )
        return result

    # Get this device's own task name for proper renaming
    device_name = device_info["name"]
    device_old_taskname = extract_taskname_from_filename(device_name)
    if not device_old_taskname:
        device_old_taskname = old_taskname  # Fallback to global old_taskname

    if device_type == "eeg":
        # EEG: output is directory with .vhdr, .vmrk, .eeg files
        # First crop with original name, then rename

        # Crop to temp location first
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_output_dir = Path(tmpdir) / "eeg_output"
            result = crop_eeg_data(
                input_file=input_file,
                output_dir=tmp_output_dir,
                start_time=crop_start_consensus,
                end_time=crop_end_consensus,
                device_offset=offset,
            )

            # Copy files to final location with renamed task
            output_dir.mkdir(parents=True, exist_ok=True)

            # FIX: Instead of assuming filename pattern, glob for actual output files
            # Then apply rename logic to each file found
            for ext in [".vhdr", ".vmrk", ".eeg"]:
                # Find files matching this extension in temp output dir
                # The cropped files use the input_file stem (original device name)
                cropped_files = list(tmp_output_dir.glob(f"*{ext}"))

                for src in cropped_files:
                    # Get the base name (stem + extension) from the actual cropped file
                    actual_filename = src.name

                    # Apply rename logic using THIS device's task name
                    new_name = rename_bids_task(
                        actual_filename, device_old_taskname, new_taskname
                    )

                    # Copy to final location with new name
                    dst = output_dir / new_name
                    shutil.copy2(src, dst)

        return result

    elif device_type == "fnirs":
        # fNIRS: output is SNIRF file
        output_filename = f"{device_name}.snirf"
        output_filename = rename_bids_task(
            output_filename, device_old_taskname, new_taskname
        )
        output_file = output_dir / output_filename

        result = crop_fnirs_data(
            input_file=input_file,
            output_file=output_file,
            start_time=crop_start_consensus,
            end_time=crop_end_consensus,
            device_offset=offset,
        )
        return result

    else:
        raise ValueError(f"Unknown device type: {device_type}")


def save_crop_metadata(
    output_dir: Path,
    crop_params: Dict,
    devices_cropped: List[str],
    original_metadata: Dict,
) -> Path:
    """
    Save metadata about the crop operation.
    """
    metadata = {
        "crop_parameters": crop_params,
        "devices_cropped": devices_cropped,
        "original_matched_metadata": original_metadata,
    }

    output_file = output_dir / "crop_metadata.json"
    with open(output_file, "w") as f:
        json.dump(metadata, f, indent=2)

    return output_file


def matchcrop_aligned(
    json_path,
    start_time: float,
    end_time: float,
    taskname: str = None,
) -> Dict:
    """
    Crop multi-device data based on aligned device timelines.

    This function:
    1. Reads matched_metadata.json to get device info and aligned timeline
    2. Calculates aligned time range using consensus_time_range for validation
    3. Uses user-provided start_time and end_time (required)
    4. Crops each device's raw data using drift-corrected time ranges
    5. Renames output files with new task name
    6. Saves to JSON's parent directory

    Parameters:
    -----------
    json_path : str or Path
        Path to matched_metadata.json
    start_time : float
        Start time in consensus timeline (required)
    end_time : float
        End time in consensus timeline (required)
    taskname : str
        New task name for output files (required)

    Returns:
    --------
    Dict: Processing results with cropped files info

    Raises:
    -------
    ValueError: If taskname is not provided or time range is invalid
    FileNotFoundError: If json_path doesn't exist
    """
    # Convert string to Path if needed
    if isinstance(json_path, str):
        json_path = Path(json_path)

    # Validate inputs
    if not json_path.exists():
        raise FileNotFoundError(f"Metadata JSON not found: {json_path}")

    if not taskname:
        raise ValueError("taskname is required (no default)")

    # Load metadata
    with open(json_path, "r") as f:
        metadata = json.load(f)

    # Calculate aligned time range for validation
    aligned_start, aligned_end = calculate_aligned_time_range(metadata)

    # Use user-provided times (required)
    crop_start = start_time
    crop_end = end_time

    # Validate time range
    if crop_start >= crop_end:
        raise ValueError(f"Invalid time range: start={crop_start} >= end={crop_end}")

    # Warn if user times are outside aligned range (but allow it)
    if crop_start < aligned_start or crop_end > aligned_end:
        print(f"  Warning: Crop range [{crop_start:.3f}s, {crop_end:.3f}s] extends beyond aligned range [{aligned_start:.3f}s, {aligned_end:.3f}s]")
        print(f"  This may result in missing data or errors if devices don't have data in the requested range.")

    # Get output directory (same as input JSON)
    output_dir = json_path.parent

    # Get device info
    device_info = metadata.get("device_info", [])
    if not device_info:
        raise ValueError("No device_info found in metadata")

    # Get old task name from first device
    first_device = device_info[0]
    old_taskname = extract_taskname_from_filename(first_device["name"])
    if not old_taskname:
        old_taskname = "unknown"
        print(f"  Warning: Could not extract task name, using '{old_taskname}'")

    # Process each device
    results = {
        "input_json": str(json_path),
        "output_dir": str(output_dir),
        "crop_time_range": [crop_start, crop_end],
        "old_taskname": old_taskname,
        "new_taskname": taskname,
        "cropped_devices": [],
        "output_files": {},
        "errors": [],
    }

    print(f"Cropping devices using aligned timeline:")
    print(f"  Time range: {crop_start:.3f}s - {crop_end:.3f}s")
    print(f"  Task name: {old_taskname} -> {taskname}")
    print(f"  Output directory: {output_dir}")

    for device in device_info:
        device_name = device["name"]
        device_type = detect_device_type(device_name)

        print(f"  Processing: {device_name} ({device_type})")

        try:
            crop_result = crop_and_rename_device(
                device_info=device,
                crop_start_consensus=crop_start,
                crop_end_consensus=crop_end,
                output_dir=output_dir,
                old_taskname=old_taskname,
                new_taskname=taskname,
            )

            results["cropped_devices"].append(device_name)
            results["output_files"][device_name] = crop_result
            print(f"    -> Cropped successfully")

        except Exception as e:
            error_msg = f"Failed to crop {device_name}: {str(e)}"
            print(f"    -> Error: {error_msg}")
            results["errors"].append(error_msg)

    # Save crop metadata
    crop_metadata_path = save_crop_metadata(
        output_dir=output_dir,
        crop_params={
            "crop_start": crop_start,
            "crop_end": crop_end,
            "taskname": taskname,
        },
        devices_cropped=results["cropped_devices"],
        original_metadata=metadata,
    )
    results["output_files"]["metadata"] = str(crop_metadata_path)

    # Print summary
    print(f"\nCrop complete:")
    print(f"  Devices processed: {len(results['cropped_devices'])}/{len(device_info)}")
    print(f"  Errors: {len(results['errors'])}")

    return results


def main():
    """Command-line entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Crop multi-device data based on aligned device timelines"
    )
    parser.add_argument(
        "--json-path", "-j", required=True, help="Path to matched_metadata.json"
    )
    parser.add_argument(
        "--start-time",
        "-s",
        type=float,
        required=True,
        help="Start time in consensus timeline (required)",
    )
    parser.add_argument(
        "--end-time",
        "-e",
        type=float,
        required=True,
        help="End time in consensus timeline (required)",
    )
    parser.add_argument(
        "--taskname",
        "-t",
        required=True,
        help="New task name for output files (required)",
    )

    args = parser.parse_args()

    result = matchcrop_aligned(
        json_path=Path(args.json_path),
        start_time=args.start_time,
        end_time=args.end_time,
        taskname=args.taskname,
    )

    print(f"\nProcessing complete!")
    print(f"  Output directory: {result['output_dir']}")


if __name__ == "__main__":
    main()
