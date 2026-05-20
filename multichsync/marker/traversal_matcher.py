"""
Traversal-based marker matching with per-marker distance optimization.

This module provides an alternative to the Hungarian / min-cost-flow / Sinkhorn
approaches.  It uses a brute-force shift traversal strategy:

1. Pick the device with the most markers as the **anchor**.
2. For each other device, traverse every possible alignment offset (shift)
   to find the one that minimises the **mean pairwise distance** between
   matched markers.
3. For gaps (a device has no marker in a segment), the corresponding markers
   from the other devices are left *unmatched* in the output.
4. Return the assignment with the best (lowest) mean / total distance.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────


@dataclass
class TraversalMatchResult:
    """Holds the result of one traversal matching run."""

    anchor_name: str
    """Name of the anchor (reference) device."""

    device_names: List[str]
    """All device names in the order they were processed."""

    assignments: Dict[str, np.ndarray]
    """For each device, an array of shape (n_groups,) giving the marker
    timestamp assigned to each consensus group, or NaN for gaps."""

    group_indices: Dict[str, np.ndarray]
    """For each device, the index into the original marker array for each
    group, or -1 for gaps."""

    per_marker_distances: np.ndarray
    """Array of shape (n_groups,) giving the mean pairwise distance across
    devices for each consensus group (NaN for groups with < 2 devices)."""

    total_distance: float
    """Sum of ``per_marker_distances`` over all groups with ≥2 devices."""

    mean_distance: float
    """Mean of ``per_marker_distances`` over all groups with ≥2 devices."""

    n_groups: int
    """Total number of consensus groups (including single-device gaps)."""

    n_matched_groups: int
    """Number of groups that have ≥2 devices contributing."""

    gaps: Dict[str, List[int]]
    """For each device, list of group indices where that device has a gap."""

    shift_history: Dict[str, List[Tuple[int, float]]]
    """For each (anchor, other) pair, the shifts tried and their costs."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor": self.anchor_name,
            "devices": self.device_names,
            "total_distance": float(self.total_distance),
            "mean_distance": float(self.mean_distance),
            "n_groups": self.n_groups,
            "n_matched_groups": self.n_matched_groups,
            "gaps": {k: v for k, v in self.gaps.items()},
        }


@dataclass
class _ShiftEval:
    """Internal helper: result of evaluating one shift."""

    shift: int
    distances: List[float]
    mean_dist: float
    total_dist: float
    n_matched: int
    a_idxs: List[int]
    b_idxs: List[int]


# ══════════════════════════════════════════════════════════════════════
# Session merging helpers
# ══════════════════════════════════════════════════════════════════════


def _infer_device_type(filename: str) -> str:
    """
    Infer device type from a CSV filename using BIDS naming conventions.

    Heuristics (in order):
    1. Strip trailing ``_marker`` suffix.
    2. Check for known BIDS suffixes (``_fnirs``, ``_eeg``, ``ecg``).
    3. Look for a known device-type token in the underscore-separated parts.
    4. Fall back to the last token.
    """
    stem = Path(filename).stem
    stem = re.sub(r"_marker$", "", stem)  # remove trailing _marker

    # Known BIDS modality suffixes
    for suffix in ["_fnirs", "_eeg", "_ecg"]:
        if stem.endswith(suffix):
            return suffix.lstrip("_")

    # Fallback: look for known device-type tokens
    parts = stem.split("_")
    for part in reversed(parts):
        if part.lower() in ("fnirs", "eeg", "ecg"):
            return part.lower()
    return parts[-1] if parts else "unknown"


def _load_and_merge_sessions(
    file_paths: List[str],
    device_names: Optional[List[str]] = None,
) -> Dict[str, np.ndarray]:
    """
    Load marker CSV files, group by device type/name, merge sessions
    within each device group, and cap the merged length.

    **Merge logic**
    1. Each file is tagged with a device key (from *device_names* or
       inferred via :func:`_infer_device_type`).
    2. The maximum marker count across *all individual files* is recorded
       (``max_n``).
    3. Files sharing the same key are concatenated in file order, then
       globally sorted.
    4. If the concatenated length exceeds ``max_n``, it is **capped**
       (trimmed from the end) so that no device timeline exceeds the
       longest single-file timeline.

    Parameters
    ----------
    file_paths : list of str
        Paths to marker CSV files.
    device_names : list of str, optional
        Device names, one per file.  If *None*, names are inferred from
        the filenames via :func:`_infer_device_type`.  Files that end up
        with the same name are merged.

    Returns
    -------
    dict of str → np.ndarray
        Device name → sorted, possibly merged, possibly capped 1-D array
        of marker timestamps.
    """
    from .matcher import load_marker_csv_enhanced, DeviceInfo

    # 1. Load all files, tagging each with a group key
    loaded: List[Tuple[str, DeviceInfo]] = []
    for i, path in enumerate(file_paths):
        key = (
            device_names[i]
            if (device_names and i < len(device_names))
            else _infer_device_type(path)
        )
        dev = load_marker_csv_enhanced(path)
        loaded.append((key, dev))

    # 2. Max marker count across ALL individual files (before merging)
    max_n = max(len(dev.timestamps_raw) for _, dev in loaded)

    # 3. Group by key
    groups: Dict[str, List[DeviceInfo]] = defaultdict(list)
    for key, dev in loaded:
        groups[key].append(dev)

    # 4. Merge & cap per group
    result: Dict[str, np.ndarray] = {}
    for key, devs in groups.items():
        if len(devs) == 1:
            merged = devs[0].timestamps_raw.copy()
        else:
            merged = np.concatenate([d.timestamps_raw for d in devs])
            merged.sort()
            if len(merged) > max_n:
                print(
                    f"  [{key}] {len(merged)} markers across "
                    f"{len(devs)} session(s), capped to {max_n} "
                    f"(max across individual sessions)"
                )
                merged = merged[:max_n]
            else:
                print(
                    f"  [{key}] {len(merged)} markers across "
                    f"{len(devs)} session(s)"
                )
        result[key] = merged

    return result


# ══════════════════════════════════════════════════════════════════════
# Core algorithm
# ══════════════════════════════════════════════════════════════════════


def match_traversal(
    marker_dict: Dict[str, np.ndarray],
    *,
    anchor: Optional[str] = None,
    max_time_diff: float = 3.0,
    gap_penalty: float = 1e6,
    random_restarts: int = 5,
    rng_seed: int = 42,
) -> TraversalMatchResult:
    """
    Traverse shift space to match markers across devices, searching over alignment
    shifts and choosing the assignment with the lowest mean distance.

    Parameters
    ----------
    marker_dict : dict of str → np.ndarray
        Device name → sorted 1-D array of marker timestamps (seconds).
    anchor : str, optional
        Name of the anchor (reference) device.  If *None*, the device with
        the most markers is used.
    max_time_diff : float
        Maximum absolute time difference (seconds) for two markers to be
        considered a valid match.
    gap_penalty : float
        Large cost used for gaps (markers left unmatched).  This prevents
        the optimiser from leaving everything unmatched.
    random_restarts : int
        Number of random subsamples used to build initial alignment candidates.
        Only relevant when two devices have very different marker counts.
    rng_seed : int
        Seed for reproducible random restarts.

    Returns
    -------
    TraversalMatchResult
    """
    # ── Validate ──────────────────────────────────────────────────────
    if len(marker_dict) < 2:
        raise ValueError(
            f"Need at least 2 devices, got {len(marker_dict)}"
        )

    # Sort each device's timestamps
    sorted_dict: Dict[str, np.ndarray] = {}
    for name, ts in marker_dict.items():
        t = np.asarray(ts, dtype=float).ravel()
        t.sort()
        if len(t) == 0:
            raise ValueError(f"Device '{name}' has 0 markers")
        sorted_dict[name] = t

    # ── Choose anchor ─────────────────────────────────────────────────
    if anchor is None:
        anchor = max(sorted_dict, key=lambda k: len(sorted_dict[k]))
    elif anchor not in sorted_dict:
        raise ValueError(
            f"Anchor '{anchor}' not found in marker_dict; "
            f"available: {list(sorted_dict)}"
        )

    device_names = [anchor] + [n for n in sorted_dict if n != anchor]
    t_anchor = sorted_dict[anchor]
    n_anchor = len(t_anchor)

    # ── Match each other device to the anchor ─────────────────────────
    assignments: Dict[str, np.ndarray] = {anchor: t_anchor.copy()}
    group_indices: Dict[str, np.ndarray] = {
        anchor: np.arange(n_anchor, dtype=int)
    }
    shift_history: Dict[str, List[Tuple[int, float]]] = {}

    for dev_name in device_names[1:]:
        t_dev = sorted_dict[dev_name]
        best = _find_best_shift(
            t_anchor,
            t_dev,
            max_time_diff=max_time_diff,
            gap_penalty=gap_penalty,
            n_random_restarts=random_restarts,
            rng_seed=rng_seed,
        )
        shift_history[dev_name] = [(best.shift, best.mean_dist)]

        # Build arrays aligned to anchor length
        dev_assign = np.full(n_anchor, np.nan)
        dev_indices = np.full(n_anchor, -1, dtype=int)
        for i, j in zip(best.a_idxs, best.b_idxs):
            dev_assign[i] = t_dev[j]
            dev_indices[i] = j

        assignments[dev_name] = dev_assign
        group_indices[dev_name] = dev_indices

    # ── Compute per-group distances ───────────────────────────────────
    n_groups = n_anchor
    per_marker_distances = np.full(n_groups, np.nan)

    for g in range(n_groups):
        times = []
        for d in device_names:
            t = assignments[d][g]
            if not np.isnan(t):
                times.append(t)
        if len(times) >= 2:
            # Mean pairwise absolute distance
            diffs = []
            for i in range(len(times)):
                for j in range(i + 1, len(times)):
                    diffs.append(abs(times[i] - times[j]))
            per_marker_distances[g] = float(np.mean(diffs))

    # ── Compute totals ────────────────────────────────────────────────
    valid_mask = ~np.isnan(per_marker_distances)
    total_distance = float(np.sum(per_marker_distances[valid_mask]))
    mean_distance = float(np.mean(per_marker_distances[valid_mask])) if valid_mask.any() else 0.0
    n_matched = int(valid_mask.sum())

    # ── Gap detection ─────────────────────────────────────────────────
    gaps: Dict[str, List[int]] = {}
    for d in device_names:
        gap_idxs = np.where(group_indices[d] == -1)[0].tolist()
        if gap_idxs:
            gaps[d] = gap_idxs

    return TraversalMatchResult(
        anchor_name=anchor,
        device_names=device_names,
        assignments=assignments,
        group_indices=group_indices,
        per_marker_distances=per_marker_distances,
        total_distance=total_distance,
        mean_distance=mean_distance,
        n_groups=n_groups,
        n_matched_groups=n_matched,
        gaps=gaps,
        shift_history=shift_history,
    )


# ══════════════════════════════════════════════════════════════════════
# Pairwise shift search
# ══════════════════════════════════════════════════════════════════════


def _find_best_shift(
    t_a: np.ndarray,
    t_b: np.ndarray,
    max_time_diff: float,
    gap_penalty: float,
    n_random_restarts: int,
    rng_seed: int,
) -> _ShiftEval:
    """
    Traverse every possible alignment shift between *t_a* (anchor) and
    *t_b* (other device), returning the shift with the lowest **mean**
    pairwise distance.

    A "shift" means: marker *i* in the anchor is paired with marker
    *i + shift* in device B.  Negative shifts mean B's marker sequence
    starts earlier.  This is a pure brute-force traversal — every valid
    shift is evaluated.
    """
    n_a, n_b = len(t_a), len(t_b)
    shift_min = -n_b + 1  # last B marker paired with first A marker
    shift_max = n_a - 1   # first B marker paired with last A marker

    best: Optional[_ShiftEval] = None

    # ── Exhaustive traversal over all shifts ─────────────────────────
    for shift in range(shift_min, shift_max + 1):
        ev = _evaluate_shift(
            t_a, t_b, shift, max_time_diff, gap_penalty
        )
        if best is None or ev.mean_dist < best.mean_dist:
            best = ev

    # ── Random restarts (cover time-domain offsets) ───────────────────
    rng = np.random.default_rng(rng_seed)
    t_range_val = float(t_a[-1] - t_a[0])
    if not np.isfinite(t_range_val):
        t_range_val = max(float(t_b[-1] - t_b[0]), 1.0) if len(t_b) > 1 else 1.0
    t_range_val = max(t_range_val, 1.0)
    for _ in range(n_random_restarts):
        random_offset = rng.uniform(-t_range_val * 0.3, t_range_val * 0.3)
        median_step_b = float(np.median(np.diff(t_b))) if n_b > 1 else 1.0
        approx_shift = int(round(random_offset / max(median_step_b, 1e-6)))
        approx_shift = int(np.clip(approx_shift, shift_min, shift_max))

        ev = _evaluate_shift(
            t_a, t_b, approx_shift, max_time_diff, gap_penalty
        )
        if best is None or ev.mean_dist < best.mean_dist:
            best = ev

    return best  # type: ignore[return-value]


def _evaluate_shift(
    t_a: np.ndarray,
    t_b: np.ndarray,
    shift: int,
    max_time_diff: float,
    gap_penalty: float,
) -> _ShiftEval:
    """
    Evaluate one shift alignment.

    Marker A[i] is paired with B[i + shift].  Every anchor marker
    contributes to the cost: valid matches add their time difference,
    gaps (out-of-range or too-large dt) add ``gap_penalty``.

    Returns
    -------
    _ShiftEval
        ``a_idxs`` / ``b_idxs`` only list *valid* matched pairs.
        ``distances`` includes one entry per anchor marker (penalty for gaps).
        ``mean_dist = total / len(t_a)`` so that shifts with many gaps
        are correctly penalised.
    """
    n_a = len(t_a)
    n_b = len(t_b)
    distances: List[float] = []
    a_idxs: List[int] = []
    b_idxs: List[int] = []

    for i in range(n_a):
        j = i + shift
        if 0 <= j < n_b:
            dt = abs(t_a[i] - t_b[j])
            if dt <= max_time_diff:
                # Valid match
                distances.append(float(dt))
                a_idxs.append(i)
                b_idxs.append(j)
            else:
                # Time diff too large — gap penalty
                distances.append(gap_penalty)
        else:
            # Index out of range for device B — gap penalty
            distances.append(gap_penalty)

    n_matched = len(a_idxs)
    total = sum(distances)
    # Mean over ALL anchor markers ensures shifts with few matches are
    # correctly penalised.
    mean = total / n_a if n_a > 0 else 0.0

    return _ShiftEval(
        shift=shift,
        distances=distances,
        mean_dist=mean,
        total_dist=total,
        n_matched=n_matched,
        a_idxs=a_idxs,
        b_idxs=b_idxs,
    )




# ══════════════════════════════════════════════════════════════════════
# Convenience: load from CSV files
# ══════════════════════════════════════════════════════════════════════


def match_traversal_from_files(
    file_paths: List[str],
    device_names: Optional[List[str]] = None,
    *,
    max_time_diff: float = 3.0,
    gap_penalty: float = 1e6,
    random_restarts: int = 5,
    rng_seed: int = 42,
    output_dir: str = "data/matching",
    output_prefix: str = "traversal_matched",
    save_json: bool = True,
    save_csv: bool = True,
    merge_sessions: bool = True,
) -> TraversalMatchResult:
    """
    Load marker CSV files and run traversal matching.

    Parameters
    ----------
    file_paths : list of str
        Paths to marker CSV files (must contain a timestamp column).
    device_names : list of str, optional
        Names for each device.  If *None*, derived from the filenames.
        When *merge_sessions* is True (default), files sharing the same
        name are merged into a single device timeline.

    merge_sessions : bool
        If True (default), files belonging to the same device (same name
        or inferred type) are concatenated into a single timeline.  The
        merged length is capped so it does not exceed the longest
        individual device file.

    For other parameters see :func:`match_traversal`.

    Returns
    -------
    TraversalMatchResult
    """
    if merge_sessions:
        marker_dict = _load_and_merge_sessions(file_paths, device_names)
    else:
        # Original 1:1 file → device behaviour
        from .matcher import load_marker_csv_enhanced

        devices = []
        for i, path in enumerate(file_paths):
            name = (
                device_names[i]
                if (device_names and i < len(device_names))
                else None
            )
            dev = load_marker_csv_enhanced(path, name)
            devices.append(dev)
        marker_dict = {d.name: d.timestamps_raw for d in devices}

    result = match_traversal(
        marker_dict,
        max_time_diff=max_time_diff,
        gap_penalty=gap_penalty,
        random_restarts=random_restarts,
        rng_seed=rng_seed,
    )

    # ── Save outputs ──────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)

    if save_csv:
        _save_timeline_csv(result, output_dir, output_prefix)
    if save_json:
        _save_metadata_json(result, output_dir, output_prefix)

    return result


# ══════════════════════════════════════════════════════════════════════
# Output helpers
# ══════════════════════════════════════════════════════════════════════


def _save_timeline_csv(
    result: TraversalMatchResult,
    output_dir: str,
    prefix: str,
) -> str:
    """Build a timeline CSV with one row per consensus group."""
    data: Dict[str, Any] = {
        "group": np.arange(result.n_groups, dtype=int),
        "mean_distance": result.per_marker_distances,
    }
    for d in result.device_names:
        if d not in result.assignments:
            continue
        data[f"{d}_time"] = result.assignments[d]
        data[f"{d}_index"] = result.group_indices[d]

    df = pd.DataFrame(data)
    path = os.path.join(output_dir, f"{prefix}_timeline.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved traversal-match timeline → {path}")
    return path


def _save_metadata_json(
    result: TraversalMatchResult,
    output_dir: str,
    prefix: str,
) -> str:
    """Save matching metadata as JSON."""
    meta = {
        "algorithm": "traversal_shift",
        "anchor": result.anchor_name,
        "devices": result.device_names,
        "n_groups": result.n_groups,
        "n_matched_groups": result.n_matched_groups,
        "total_distance": float(result.total_distance),
        "mean_distance": float(result.mean_distance),
        "gaps": {k: {"n_gaps": len(v), "groups": v} for k, v in result.gaps.items()},
        "shift_history": {
            k: [{"shift": s, "mean_distance": md} for s, md in v]
            for k, v in result.shift_history.items()
        },
        "files": {
            "timeline_csv": f"{prefix}_timeline.csv",
        },
    }
    path = os.path.join(output_dir, f"{prefix}_metadata.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, default=str)
    print(f"Saved traversal-match metadata → {path}")
    return path


# ══════════════════════════════════════════════════════════════════════
# Stacked-timeline matching from marker info reports
# ══════════════════════════════════════════════════════════════════════


def _find_converted_data_path(
    data_file_name: str,
    device: str,
    convert_base_dir: str = "Data/convert",
) -> Optional[str]:
    """
    Locate the converted data file corresponding to an info-report row.

    Constructs ``{convert_base_dir}/{device}/{data_file_name}`` if the file
    exists.  Falls back to case-insensitive glob in the same directory.

    Returns *None* if no file is found.
    """
    base = Path(convert_base_dir) / device
    if not base.exists():
        return None

    cand = base / data_file_name
    if cand.exists():
        return str(cand.resolve())

    # Case-insensitive fallback
    data_stem = Path(data_file_name).stem
    for ext in (".snirf", ".vhdr", ".vmrk", ".eeg", ".csv", ".set", ".edf", ".fdt"):
        for f in base.glob(f"{data_stem}{ext}"):
            return str(f.resolve())
        for f in base.glob(f"{data_stem.lower()}{ext}"):
            return str(f.resolve())

    return None


def _find_marker_csv(
    data_file_name: str,
    device: str,
    marker_base_dir: str = "Data/marker",
) -> Optional[str]:
    """
    Locate the marker CSV file that corresponds to a data file listed in an
    info report row.

    Search order in ``{marker_base_dir}/{device}/``:

    1. ``{stem}_marker.csv`` — standard MultiChSync naming
    2. ``{stem}.csv`` — marker file without ``_marker`` suffix
    3. ``{base_stem}_marker.csv`` — where *base_stem* removes the device
       suffix (e.g. ``sub-001_ses-01_task-rest_fnirs`` → base stem
       ``sub-001_ses-01_task-rest``)
    4. Glob ``{stem}*.csv`` — first match

    Returns *None* if no file is found.
    """
    marker_dir = Path(marker_base_dir) / device
    if not marker_dir.exists():
        return None

    stem = Path(data_file_name).stem  # e.g. sub-001_ses-01_task-rest_fnirs

    # 1. Direct: stem + _marker
    cand = marker_dir / f"{stem}_marker.csv"
    if cand.exists():
        return str(cand)

    # 2. Without _marker
    cand = marker_dir / f"{stem}.csv"
    if cand.exists():
        return str(cand)

    # 3. Remove device suffix from stem, try + _marker or + _input
    for dev_sfx in ("fnirs", "eeg", "ecg"):
        if stem.endswith(f"_{dev_sfx}"):
            base = stem[: -(len(dev_sfx) + 1)]
            for alt_sfx in ("_marker", "_input"):
                cand = marker_dir / f"{base}{alt_sfx}.csv"
                if cand.exists():
                    return str(cand)
                cand = marker_dir / f"{base}_{dev_sfx}{alt_sfx}.csv"
                if cand.exists():
                    return str(cand)

    # 4. Glob fallback
    for f in sorted(marker_dir.glob(f"{stem}*.csv")):
        return str(f)

    return None


def _build_stacked_timelines_from_info(
    info_rows: List[Dict[str, Any]],
    marker_base_dir: str = "Data/marker",
) -> Dict[str, Dict[str, Any]]:
    """
    Read info-report rows and build **stacked per-device timelines**.

    For each device:
    - Sessions are sorted by ``sequence_id`` (preserving original order).
    - Session markers are **time-offset** by the cumulative duration of all
      previous sessions, producing a continuous stacked timeline.
    - The total duration of a device is the **sum** of its session durations
      (from the data file's ``sequence_duration``).

    Parameters
    ----------
    info_rows : list of dict
        Rows from a ``subject_*_marker_report.csv``.  Each must have keys:
        ``file_name``, ``device``, ``sequence_id``, ``sequence_duration``.
    marker_base_dir : str
        Base directory under which ``{device}/`` subdirectories hold marker
        CSV files.

    Returns
    -------
    dict of str → dict
        ``{device_name: {"total_duration": float,
                         "n_markers_total": int,
                         "stacked_markers": np.ndarray,
                         "sessions": [{"sequence_id", "n_markers",
                                       "duration", "raw_markers",
                                       "offset_markers"}, ...]}}``

    Raises
    ------
    ValueError
        If no valid marker files can be found for any device.
    """
    from .matcher import load_marker_csv_enhanced

    # Group rows by device
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in info_rows:
        device = str(row.get("device", "unknown"))
        grouped[device].append(row)

    result: Dict[str, Dict[str, Any]] = {}

    # Sort helper: numeric sequence_id so "2" comes before "10"
    def _seq_sort_key(sid: str) -> int:
        try:
            return int(sid)
        except (ValueError, TypeError):
            return 9999

    # Helper: parse a session duration from the info row
    def _parse_session_duration(row: Dict[str, Any], marker_count: int, marker_span: float) -> float:
        raw_dur = row.get("sequence_duration")
        try:
            dur = float(raw_dur) if raw_dur not in (None, "", "nan", "NaN") else 0.0
        except (ValueError, TypeError):
            dur = 0.0
        if not np.isfinite(dur) or dur < 0:
            dur = 0.0
        if dur <= 0 and marker_count > 1:
            dur = marker_span
        if not np.isfinite(dur) or dur <= 0:
            dur = 1.0  # minimal fallback
        return dur

    for device, rows in grouped.items():
        # Sort sessions by sequence_id numerically ("2" before "10")
        rows.sort(key=lambda r: _seq_sort_key(str(r.get("sequence_id", "0"))))

        sessions: List[Dict[str, Any]] = []
        all_offsets: List[np.ndarray] = []
        cumulative_offset = 0.0

        for row in rows:
            marker_path = _find_marker_csv(
                str(row["file_name"]), device, marker_base_dir
            )

            if marker_path is None:
                # ── 0-marker session: preserve its duration as a gap ─────
                # The session exists (has recording duration) but no marker
                # CSV.  Keep the duration gap so subsequent sessions' markers
                # are offset correctly and the total device duration accounts
                # for this period.
                duration = _parse_session_duration(row, 0, 0.0)
                sessions.append({
                    "sequence_id": str(row.get("sequence_id", "?")),
                    "n_markers": 0,
                    "duration": duration,
                    "raw_markers": np.array([], dtype=float),
                    "offset_markers": np.array([], dtype=float),
                })
                cumulative_offset += duration
                continue

            dev = load_marker_csv_enhanced(marker_path)
            raw_markers = dev.timestamps_raw
            n_markers = len(raw_markers)

            # Duration from info report; fall back to marker span
            marker_span = float(raw_markers[-1] - raw_markers[0]) if n_markers > 1 else 0.0
            duration = _parse_session_duration(row, n_markers, marker_span)

            offset_markers = raw_markers + cumulative_offset

            sessions.append({
                "sequence_id": str(row.get("sequence_id", "?")),
                "n_markers": n_markers,
                "duration": duration,
                "raw_markers": raw_markers.copy(),
                "offset_markers": offset_markers.copy(),
            })
            all_offsets.append(offset_markers)
            cumulative_offset += duration

        if not sessions:
            # No sessions at all
            continue

        n_total = sum(s["n_markers"] for s in sessions)
        stacked = np.concatenate(all_offsets) if all_offsets else np.array([], dtype=float)

        result[device] = {
            "total_duration": cumulative_offset,
            "n_markers_total": n_total,
            "stacked_markers": stacked,
            "sessions": sessions,
        }

        if n_total == 0:
            print(f"  [{device}] 0 markers across {len(sessions)} session(s), "
                  f"total_duration={cumulative_offset:.1f}s (gap only)")

    if not result:
        raise ValueError(
            "Could not build any stacked timeline from the info report. "
            "Check that marker CSV files exist in the expected locations."
        )

    return result


def _calc_session_boundaries(
    sessions: List[Dict[str, Any]],
    stretch_factor: float = 1.0,
) -> np.ndarray:
    """Return cumulative session boundary times, stretched: [0, d1, d1+d2, ..., total]"""
    bounds = [0.0]
    cum = 0.0
    for s in sessions:
        dur = s.get("duration", 0) or 0
        cum += dur
        bounds.append(cum * stretch_factor)
    return np.array(bounds)


def _snap_boundaries(
    boundaries: np.ndarray,
    ref_boundaries: np.ndarray,
    aligned_markers: np.ndarray,
    snap_threshold: float = 5.0,
) -> np.ndarray:
    """
    Snap session boundaries to the nearest reference boundary within
    *snap_threshold* seconds.  Only interior boundaries (not 0 or last)
    are snapped.  Markers are adjusted accordingly.
    """
    result = aligned_markers.copy()
    for bi in range(1, len(boundaries) - 1):
        b = boundaries[bi]
        for rb in ref_boundaries:
            delta = rb - b
            if abs(delta) <= snap_threshold:
                mask = result >= b - 0.001
                result[mask] += delta
                boundaries[bi:] += delta
                break
    return result


def _align_stacked_timeline(
    t_ref: np.ndarray,
    t_other: np.ndarray,
    *,
    ref_duration: float,
    other_duration: float,
    ref_sessions: List[Dict[str, Any]],
    other_sessions: List[Dict[str, Any]],
    max_time_diff: float,
    gap_penalty: float,
    snap_threshold: float = 5.0,
) -> Tuple[float, float, int, List[int], List[int], np.ndarray]:
    """
    Align *t_other* to *t_ref* by **proportional stretching** with
    **session-boundary snapping** (±*snap_threshold* s).

    Workflow
    --------
    1. **Stretch** the other device's markers by factor
       ``ref_duration / other_duration`` so the stretched timeline exactly
       spans ``[0, ref_duration]`` (both start and end aligned).
    2. **Snap** interior session boundaries of the other device to the
       nearest reference session boundary if within *snap_threshold* s.
    3. **Match** greedily by nearest-neighbour on the snapped/stretched axis.

    Returns
    -------
    (stretch_factor, mean_dist, n_matched, a_idxs, b_idxs, aligned_t_other)
    """
    if len(t_other) == 0 or len(t_ref) == 0 or other_duration <= 0:
        return 1.0, float(gap_penalty), 0, [], [], t_other.copy()

    # 1. Proportional stretch — aligns start=0 and end=ref_duration
    stretch_factor = ref_duration / other_duration
    aligned = t_other * stretch_factor

    # 2. Session boundary snapping (±snap_threshold)
    if other_sessions and ref_sessions and snap_threshold > 0:
        other_bounds = _calc_session_boundaries(other_sessions, stretch_factor)
        ref_bounds = _calc_session_boundaries(ref_sessions, stretch_factor=1.0)
        aligned = _snap_boundaries(other_bounds, ref_bounds, aligned, snap_threshold)

    # 3. Greedy nearest-neighbour matching
    sort_idx = np.argsort(aligned)
    sorted_aligned = aligned[sort_idx]
    n_ref = len(t_ref)
    used = np.zeros(len(aligned), dtype=bool)

    a_idxs: List[int] = []
    b_idxs: List[int] = []
    total_dist = 0.0
    n_matched = 0

    for i in range(n_ref):
        ref_t = t_ref[i]
        pos = np.searchsorted(sorted_aligned, ref_t)

        candidates: List[Tuple[int, float]] = []
        for offset in (-1, 0, 1):
            p = pos + offset
            if 0 <= p < len(sorted_aligned) and not used[p]:
                candidates.append((p, abs(sorted_aligned[p] - ref_t)))

        if candidates:
            best_pos, best_dist = min(candidates, key=lambda x: x[1])
            if best_dist <= max_time_diff:
                total_dist += float(best_dist)
                a_idxs.append(i)
                b_idxs.append(int(sort_idx[best_pos]))
                used[best_pos] = True
                n_matched += 1
                continue

        total_dist += gap_penalty

    mean_dist = total_dist / n_ref if n_ref > 0 else 0.0
    return stretch_factor, mean_dist, n_matched, a_idxs, b_idxs, aligned


def _match_one_subject(
    subject_id: str,
    rows: List[Dict[str, Any]],
    *,
    marker_base_dir: str,
    convert_base_dir: str,
    max_time_diff: float,
    gap_penalty: float,
    random_restarts: int,
    n_refinement_rounds: int,
    rng_seed: int,
) -> Optional[TraversalMatchResult]:
    """
    Run stacked-timeline matching for a **single subject**.

    Returns *None* if fewer than 2 devices are available after stacking.
    """
    if len(rows) < 2:
        print(f"  [{subject_id}] Skipped: only {len(rows)} row(s), need ≥2 devices")
        return None

    try:
        stack = _build_stacked_timelines_from_info(rows, marker_base_dir)
    except ValueError as e:
        print(f"  [{subject_id}] Skipped: {e}")
        return None
    if len(stack) < 2:
        print(f"  [{subject_id}] Skipped: {len(stack)} device(s) after stacking, need ≥2")
        return None

    # Filter out devices with NaN/invalid durations
    valid_devices = []
    for dn, info in stack.items():
        dur = info["total_duration"]
        if not np.isfinite(dur) or dur <= 0:
            print(f"  [{subject_id}] Skipping device '{dn}': invalid total_duration={dur}")
            continue
        valid_devices.append((dn, dur, info["n_markers_total"]))

    if len(valid_devices) < 2:
        print(f"  [{subject_id}] Skipped: {len(valid_devices)} valid device(s), need ≥2")
        return None

    # Reference: device with markers AND longest duration.
    # 0-marker devices can be followers but not anchor.
    devices_with_markers = [(dn, dur, n) for dn, dur, n in valid_devices if n > 0]
    if not devices_with_markers:
        print(f"  [{subject_id}] Skipped: no device has markers to serve as reference")
        return None

    devices_with_markers.sort(key=lambda x: (x[1], x[2]), reverse=True)
    ref_name = devices_with_markers[0][0]
    ref_duration = devices_with_markers[0][1]
    actual_total_duration = ref_duration + max_time_diff

    log_durations = ", ".join(
        f"{dn}={info['total_duration']:.0f}s" for dn, info in stack.items()
    )
    print(f"\n  Subject {subject_id}: ref={ref_name} ({ref_duration:.1f}s, ±{max_time_diff:.0f}s)  [{log_durations}]")

    t_ref = stack[ref_name]["stacked_markers"]
    n_ref = len(t_ref)

    # All valid devices in output order (ref first, then others by duration)
    all_devices = sorted(valid_devices, key=lambda x: (x[1], x[2]), reverse=True)
    device_names_ordered = [ref_name] + [dn for dn, _, _ in all_devices if dn != ref_name]

    assignments: Dict[str, np.ndarray] = {ref_name: t_ref.copy()}
    group_indices: Dict[str, np.ndarray] = {ref_name: np.arange(n_ref, dtype=int)}
    shift_history: Dict[str, List[Tuple[int, float]]] = {}
    # drift_params: {device_name: {"offset": float, "scale": float}}
    drift_params: Dict[str, Dict[str, float]] = {ref_name: {"offset": 0.0, "scale": 1.0}}

    for other_name in device_names_ordered[1:]:
        other_info = stack[other_name]
        t_other = other_info["stacked_markers"]
        other_duration = other_info["total_duration"]
        other_n = other_info["n_markers_total"]

        if other_duration > actual_total_duration + 1e-9:
            print(
                f"    WARNING: [{other_name}] {other_duration:.1f}s exceeds "
                f"actual total duration {actual_total_duration:.1f}s"
            )

        if other_n == 0:
            # ── 0-marker device: all gaps, center-aligned drift ────
            ref_center = ref_duration / 2.0
            other_center = other_duration / 2.0
            center_offset = ref_center - other_center
            drift_params[other_name] = {"offset": center_offset, "scale": 1.0}
            shift_history[other_name] = [(0, 0.0)]

            dev_assign = np.full(n_ref, np.nan)
            dev_indices = np.full(n_ref, -1, dtype=int)

            print(
                f"    [{other_name}] 0 markers, "
                f"center-aligned (offset={center_offset:.1f}s)"
            )
        else:
            # ── Stretch-based matching (start+end magnetic snap) ───
            # Proportionally stretches the shorter device's markers to
            # span the ref duration, aligning both first-session start
            # and last-session end simultaneously.
            stretch_factor, mean_d, n_matched, a_idxs, b_idxs, aligned = (
                _align_stacked_timeline(
                    t_ref, t_other,
                    ref_duration=ref_duration,
                    other_duration=other_duration,
                    ref_sessions=stack[ref_name].get("sessions", []),
                    other_sessions=other_info.get("sessions", []),
                    max_time_diff=max_time_diff,
                    gap_penalty=gap_penalty,
                )
            )
            shift_history[other_name] = [(stretch_factor, mean_d)]

            expected_gap = abs(ref_duration - other_duration)
            print(
                f"    [{other_name}] stretch={stretch_factor:.4f}  "
                f"(matched {n_matched}/{n_ref})  "
                f"mean={mean_d:.3f}s  "
                f"gap≤{expected_gap:.0f}s"
            )

            # Drift: scale = other/ref (consensus_time→device_time)
            drift_scale = 1.0 / stretch_factor if stretch_factor > 0 else 1.0
            drift_params[other_name] = {"offset": 0.0, "scale": drift_scale}

            dev_assign = np.full(n_ref, np.nan)
            dev_indices = np.full(n_ref, -1, dtype=int)
            for i, j in zip(a_idxs, b_idxs):
                dev_assign[i] = aligned[j]  # stretched time
                dev_indices[i] = j

        assignments[other_name] = dev_assign
        group_indices[other_name] = dev_indices

    # ── Per-group distances ───────────────────────────────────────────
    per_marker_distances = np.full(n_ref, np.nan)
    for g in range(n_ref):
        times = [assignments[d][g] for d in device_names_ordered
                 if not np.isnan(assignments[d][g])]
        if len(times) >= 2:
            diffs = [abs(times[i] - times[j])
                     for i in range(len(times))
                     for j in range(i + 1, len(times))]
            per_marker_distances[g] = float(np.mean(diffs))

    valid_mask = ~np.isnan(per_marker_distances)
    total_distance = float(np.sum(per_marker_distances[valid_mask]))
    mean_distance = float(np.mean(per_marker_distances[valid_mask])) if valid_mask.any() else 0.0
    n_matched = int(valid_mask.sum())

    gaps: Dict[str, List[int]] = {}
    for d in device_names_ordered:
        gs = np.where(group_indices[d] == -1)[0].tolist()
        if gs:
            gaps[d] = gs

    result = TraversalMatchResult(
        anchor_name=ref_name,
        device_names=device_names_ordered,
        assignments=assignments,
        group_indices=group_indices,
        per_marker_distances=per_marker_distances,
        total_distance=total_distance,
        mean_distance=mean_distance,
        n_groups=n_ref,
        n_matched_groups=n_matched,
        gaps=gaps,
        shift_history=shift_history,
    )
    # Store drift params for downstream output
    result._drift_params = drift_params
    return result


def _save_subject_outputs(
    subject_id: str,
    result: TraversalMatchResult,
    rows: List[Dict[str, Any]],
    stack: Dict[str, Dict[str, Any]],
    *,
    marker_base_dir: str,
    convert_base_dir: str,
    max_time_diff: float,
    output_dir: str,
    output_prefix: str,
    save_csv: bool,
    save_json: bool,
    save_fig: bool = True,
    drift_params: Optional[Dict[str, Dict[str, float]]] = None,
) -> None:
    """Save per-subject output files (matchcrop-aligned compatible)."""
    prefix = f"{output_prefix}_subject-{subject_id}"
    os.makedirs(output_dir, exist_ok=True)

    ref_name = result.anchor_name
    ref_duration = stack[ref_name]["total_duration"]
    n_ref = result.n_groups
    device_names = [d for d in result.device_names if d in result.assignments]

    # Consensus time range
    valid_ref = ~np.isnan(result.assignments[ref_name])
    consensus_time_range = (
        [float(np.min(result.assignments[ref_name][valid_ref])),
         float(np.max(result.assignments[ref_name][valid_ref]))]
        if valid_ref.any()
        else [0.0, ref_duration]
    )

    # Drift parameters from matching (offset + scale for matchcrop-aligned)
    if drift_params is None:
        # Fallback: compute from shift_history (legacy)
        drift_params = {ref_name: {"offset": 0.0, "scale": 1.0}}
        for d in device_names:
            if d != ref_name:
                drift_params[d] = {"offset": result.shift_history.get(d, [(0, 0.0)])[0][0], "scale": 1.0}

    # Build device_info
    device_info_list: List[Dict[str, Any]] = []
    for dev_name in device_names:
        dev_stack = stack[dev_name]
        dev_rows = [r for r in rows
                    if str(r.get("device", "")).lower() == dev_name.lower()]
        data_file_name = str(dev_rows[0].get("file_name", "")) if dev_rows else ""
        converted_path = (
            _find_converted_data_path(data_file_name, dev_name, convert_base_dir)
            if data_file_name else None
        )
        marker_path = _find_marker_csv(data_file_name, dev_name, marker_base_dir)

        dp = drift_params.get(dev_name, {"offset": 0.0, "scale": 1.0})
        drift_correction = {
            "offset": dp.get("offset", 0.0),
            "scale": dp.get("scale", 1.0),
            "r_squared": 1.0,
            "n_matches": int(np.sum(~np.isnan(result.assignments[dev_name]))),
            "method": "traversal_shift_stacked",
        }

        device_info_list.append({
            "name": dev_name,
            "file_path": marker_path or "",
            "converted_data_file_path": converted_path or "",
            "n_events": dev_stack["n_markers_total"],
            "time_range": [0.0, dev_stack["total_duration"]],
            "raw_duration": dev_stack["total_duration"],
            "drift_correction": drift_correction,
            "session_files": [
                {"sequence_id": s["sequence_id"],
                 "n_markers": s["n_markers"],
                 "duration": s["duration"]}
                for s in dev_stack["sessions"]
            ],
        })

    timeline_metadata = {
        "algorithm": "traversal_shift_stack",
        "n_devices": len(device_names),
        "device_names": device_names,
        "n_consensus_events": n_ref,
        "n_matched_groups": result.n_matched_groups,
        "consensus_time_range": consensus_time_range,
        "total_distance": result.total_distance,
        "mean_distance": result.mean_distance,
        "subject_id": subject_id,
        "drift_corrections": {dn: dp.get("offset", 0.0) for dn, dp in drift_params.items()},
        "drift_scales": {dn: dp.get("scale", 1.0) for dn, dp in drift_params.items()},
        "session_info": {
            dn: [
                {"sequence_id": s["sequence_id"], "duration": s["duration"],
                 "n_markers": s["n_markers"]}
                for s in stack[dn]["sessions"]
            ]
            for dn in device_names
        },
    }

    # Save CSVs
    if save_csv:
        _save_timeline_csv(result, output_dir, prefix)
        _save_stacked_timeline_csv(result, stack, output_dir, prefix)

    # Save metadata JSON (matchcrop-aligned compatible)
    if save_json:
        meta = {
            "algorithm": "traversal_shift_stacked",
            "anchor": result.anchor_name,
            "subject_id": subject_id,
            "devices": device_names,
            "n_groups": result.n_groups,
            "n_matched_groups": result.n_matched_groups,
            "total_distance": float(result.total_distance),
            "mean_distance": float(result.mean_distance),
            "gaps": {k: {"n_gaps": len(v), "groups": v}
                     for k, v in result.gaps.items()},
            "shift_history": {
                k: [{"shift": s, "mean_distance": md} for s, md in v]
                for k, v in result.shift_history.items()
            },
            "device_info": device_info_list,
            "timeline_metadata": timeline_metadata,
            "output_files": {
                "timeline_csv": f"{prefix}_timeline.csv",
                "stacked_timeline_csv": f"{prefix}_stacked_timeline.csv",
            },
        }
        path = os.path.join(output_dir, f"{prefix}_metadata.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2, default=str)
        print(f"  Saved metadata → {os.path.basename(path)}")

    # Save matched timeline figure
    if save_fig:
        try:
            _save_matched_timeline_figure(
                result, stack, subject_id, output_dir, prefix,
            )
        except Exception as e:
            print(f"  Warning: failed to save figure ({e})")


def match_traversal_from_info(
    info_dir: str,
    *,
    marker_base_dir: str = "Data/marker",
    convert_base_dir: str = "Data/convert",
    max_time_diff: float = 10.0,
    gap_penalty: float = 1e6,
    random_restarts: int = 5,
    n_refinement_rounds: int = 3,
    rng_seed: int = 42,
    output_dir: str = "data/matching",
    output_prefix: str = "traversal_matched",
    save_json: bool = True,
    save_csv: bool = True,
    save_fig: bool = True,
) -> Dict[str, TraversalMatchResult]:
    """
    Read ``marker info`` reports and run **per-subject stacked-timeline
    traversal matching**.

    Workflow
    --------
    1. Load all ``subject_*_marker_report.csv`` files from *info_dir*.
    2. Group rows by ``subject_id`` — each subject is processed independently.
    3. For each subject:
       a. Build **stacked** (session-concatenated, time-offset) timelines
          per device via :func:`_build_stacked_timelines_from_info`.
       b. The device with the **longest total duration** is the reference.
          "Actual total duration" = reference duration + *max_time_diff*
          (±10 s tolerance).
       c. For each shorter device, run iterative shift refinement
          (:func:`_find_best_shift_iterative`) matching its stacked markers
          to the reference's stacked markers.
       d. Sessions within a device are **never reordered or deleted**.
    4. Save per-subject outputs (``{output_prefix}_subject-{id}_*.csv/json``)
       in *output_dir*.

    Parameters
    ----------
    info_dir : str
        Directory containing ``subject_*_marker_report.csv`` files (output of
        ``multichsync marker info``).
    marker_base_dir : str
        Base directory for marker CSV files (default ``Data/marker``).
    convert_base_dir : str
        Base directory for converted data files (default ``Data/convert``).
        Used to locate ``converted_data_file_path`` in the output metadata
        so that :func:`matchcrop_aligned` can find the raw data to crop.
    max_time_diff : float
        Maximum time difference (s) for a valid match; also defines the
        ± tolerance for the "actual total duration" window (default 10 s).
    gap_penalty : float
        Cost for each unmatched marker.
    random_restarts : int
        Random offset candidates for the initial traversal.
    n_refinement_rounds : int
        Iterative refinement rounds after the initial full traversal.
    rng_seed : int
        Random seed for reproducibility.

    For output parameters see :func:`match_traversal_from_files`.

    Returns
    -------
    dict of str → TraversalMatchResult
        Mapping ``subject_id`` → matching result for that subject.
    """
    info_dir_path = Path(info_dir)
    if not info_dir_path.exists():
        raise FileNotFoundError(f"Info directory not found: {info_dir}")

    # ── 1. Load all subject info reports ───────────────────────────────
    report_files = sorted(info_dir_path.glob("subject_*_marker_report.csv"))
    if not report_files:
        raise FileNotFoundError(
            f"No subject_*_marker_report.csv files found in {info_dir}"
        )

    all_rows: List[Dict[str, Any]] = []
    for rp in report_files:
        try:
            df = pd.read_csv(rp, encoding="utf-8-sig")
            all_rows.extend(df.to_dict(orient="records"))
            print(f"  Loaded {rp.name}: {len(df)} rows")
        except Exception as e:
            print(f"  Warning: skipping {rp.name} ({e})")

    if not all_rows:
        raise ValueError("No data rows loaded from info reports.")

    # ── 1b. Deduplicate rows ───────────────────────────────────────────
    # Info reports can have duplicate (file_name, device, sequence_id)
    # entries (e.g. ecg: one row with n_markers=0, another with actual
    # markers).  Keep the row with the highest n_markers.
    dedup_key = lambda r: (str(r.get("file_name", "")),
                           str(r.get("device", "")),
                           str(r.get("sequence_id", "")))
    deduped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in all_rows:
        k = dedup_key(row)
        existing = deduped.get(k)
        if existing is None or int(row.get("n_markers", 0)) > int(existing.get("n_markers", 0)):
            deduped[k] = row
    n_before = len(all_rows)
    all_rows = list(deduped.values())
    n_after = len(all_rows)
    if n_after < n_before:
        print(f"  Deduplicated {n_before - n_after} row(s) (kept highest n_markers per file)")

    # ── 1c. Remove secondary EEG/EEGLAB data files ─────────────────────
    # BrainVision: .eeg is binary data; a .vhdr with the same stem is the
    # canonical entry.  EEGLAB: .fdt is binary data; .set is canonical.
    # If both exist, keep only the header file.
    eeg_stems: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        fn = str(row.get("file_name", ""))
        if fn.lower().endswith((".eeg", ".fdt", ".vhdr", ".set")):
            stem = Path(fn).stem
            eeg_stems[stem].append(row)
    secondary_exts = (".eeg", ".fdt")
    filtered: List[Dict[str, Any]] = []
    for row in all_rows:
        fn = str(row.get("file_name", ""))
        ext = Path(fn).suffix.lower()
        if ext in secondary_exts:
            stem = Path(fn).stem
            has_header = any(
                str(r.get("file_name", "")).lower().endswith((".vhdr", ".set"))
                and Path(str(r.get("file_name", ""))).stem == stem
                for r in eeg_stems.get(stem, [])
            )
            if has_header:
                continue  # skip secondary binary file
        filtered.append(row)
    n_sec = len(all_rows) - len(filtered)
    if n_sec:
        print(f"  Removed {n_sec} secondary EEG binary file(s) (.eeg/.fdt with companion header)")
    all_rows = filtered

    # ── 1d. Dedup (device, sequence_id) with identical metrics — PER SUBJECT ──
    # Some sessions appear twice with different file_names but the same
    # device, sequence_id, n_markers, and duration (e.g. "task-pic" vs
    # "task-picture" — same recording).  Keep only the first occurrence.
    # NOTE: seen dict keyed by (subject_id, device, sequence_id) to avoid
    # cross-subject collisions.
    subject_groups_prelim: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        sid = str(row.get("subject_id", "unknown"))
        subject_groups_prelim[sid].append(row)

    sid_deduped: List[Dict[str, Any]] = []
    for sid, srows in subject_groups_prelim.items():
        seen_local: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for row in srows:
            key = (str(row.get("device", "")), str(row.get("sequence_id", "")))
            nm = int(row.get("n_markers", 0))
            dur_raw = row.get("sequence_duration", "")
            try:
                dur = float(dur_raw) if dur_raw not in (None, "", "nan", "NaN") else -1.0
            except (ValueError, TypeError):
                dur = -1.0
            existing = seen_local.get(key)
            if existing is not None:
                enm = int(existing.get("n_markers", 0))
                edur_raw = existing.get("sequence_duration", "")
                try:
                    edur = float(edur_raw) if edur_raw not in (None, "", "nan", "NaN") else -1.0
                except (ValueError, TypeError):
                    edur = -1.0
                if nm == enm and abs(dur - edur) < 1.0:
                    continue  # skip duplicate
            seen_local[key] = row
            sid_deduped.append(row)

    n_sid = len(all_rows) - len(sid_deduped)
    if n_sid:
        print(f"  Removed {n_sid} duplicate session(s) (same device+seq_id with identical metrics)")
    all_rows = sid_deduped

    # ── 2. Group by subject_id ─────────────────────────────────────────
    subject_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        sid = str(row.get("subject_id", "unknown"))
        subject_groups[sid].append(row)

    print(f"\nFound {len(subject_groups)} subject(s) to process:")
    for sid, srows in sorted(subject_groups.items()):
        devices_in = set(str(r.get("device", "")) for r in srows)
        # Warn about suspiciously many rows for a device (e.g. .eeg/.vhdr double-counting)
        dev_counts = defaultdict(int)
        for r in srows:
            dev_counts[str(r.get("device", ""))] += 1
        for dev, cnt in sorted(dev_counts.items()):
            if cnt > 25:
                print(f"  [WARN] Subject {sid}, device '{dev}': {cnt} rows — "
                      f"possible .eeg/.vhdr double-count.  "
                      f"Regenerate info reports after the fix.")
        print(f"  Subject {sid}: {len(srows)} rows, devices={sorted(devices_in)}")

    # ── 3. Process each subject independently ──────────────────────────
    results: Dict[str, TraversalMatchResult] = {}

    for subject_id in sorted(subject_groups):
        rows = subject_groups[subject_id]
        print(f"\n{'='*50}")
        print(f"Subject {subject_id}")
        print(f"{'='*50}")

        result = _match_one_subject(
            subject_id, rows,
            marker_base_dir=marker_base_dir,
            convert_base_dir=convert_base_dir,
            max_time_diff=max_time_diff,
            gap_penalty=gap_penalty,
            random_restarts=random_restarts,
            n_refinement_rounds=n_refinement_rounds,
            rng_seed=rng_seed,
        )
        if result is None:
            continue

        # Rebuild stack for saving (needed by _save_subject_outputs)
        stack = _build_stacked_timelines_from_info(rows, marker_base_dir)

        result_drift = getattr(result, "_drift_params", None)
        _save_subject_outputs(
            subject_id, result, rows, stack,
            marker_base_dir=marker_base_dir,
            convert_base_dir=convert_base_dir,
            max_time_diff=max_time_diff,
            output_dir=output_dir,
            output_prefix=output_prefix,
            save_csv=save_csv,
            save_json=save_json,
            save_fig=save_fig,
            drift_params=result_drift,
        )
        results[subject_id] = result

    # ── Summary ────────────────────────────────────────────────────────
    total = len(results)
    skipped = len(subject_groups) - total
    print(f"\n{'='*50}")
    print(f"Per-subject matching complete:")
    print(f"  Processed: {total} subject(s)")
    if skipped:
        print(f"  Skipped:   {skipped} subject(s) (< 2 devices)")
    print(f"  Output:    {output_dir}")
    for sid, res in sorted(results.items()):
        print(f"    {sid}: ref={res.anchor_name}, "
              f"devices={res.device_names}, "
              f"matched={res.n_matched_groups}/{res.n_groups}, "
              f"mean_dist={res.mean_distance:.3f}s")
    print(f"{'='*50}\n")

    return results


def _save_stacked_timeline_csv(
    result: TraversalMatchResult,
    stack: Dict[str, Dict[str, Any]],
    output_dir: str,
    prefix: str,
) -> str:
    """
    Save a stacked timeline CSV showing each device's (stacked) marker
    assignment per consensus group, annotated with session membership.
    """
    data: Dict[str, Any] = {
        "group": np.arange(result.n_groups, dtype=int),
        "mean_distance": result.per_marker_distances,
    }
    for d in result.device_names:
        if d not in result.assignments:
            continue
        data[f"{d}_stacked_time"] = result.assignments[d]
        data[f"{d}_index"] = result.group_indices[d]
    # Session annotation: for each group, indicate which session
    # the assigned marker belongs to (if matched).
    for d in result.device_names:
        if d not in result.assignments:
            continue
        col = np.full(result.n_groups, "", dtype=object)
        stack_d = stack.get(d)
        if stack_d:
            sessions = stack_d["sessions"]
            for g in range(result.n_groups):
                midx = result.group_indices[d][g]
                if midx >= 0:
                    # Find which session this marker index falls in
                    cum = 0
                    for sidx, sess in enumerate(sessions):
                        cum += sess["n_markers"]
                        if midx < cum:
                            col[g] = sess["sequence_id"]
                            break
        data[f"{d}_session"] = col

    df = pd.DataFrame(data)
    path = os.path.join(output_dir, f"{prefix}_stacked_timeline.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved stacked timeline → {path}")
    return path


def _save_matched_timeline_figure(
    result: TraversalMatchResult,
    stack: Dict[str, Dict[str, Any]],
    subject_id: str,
    output_dir: str,
    prefix: str,
    dpi: int = 150,
) -> str:
    """
    Save a PNG figure from the **matched timeline data** (result.assignments),
    ensuring the figure exactly corresponds to the matching output.

    Each device gets one horizontal track with markers plotted at the
    **consensus-group positions** stored in *result.assignments* (the same
    data that is written to ``{prefix}_timeline.csv``).
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    cmap_bar = plt.colormaps.get_cmap("tab10")

    device_names = [d for d in result.device_names if d in result.assignments]
    ref_name = result.anchor_name
    n_devices = len(device_names)

    palette = {"fnirs": "#4C72B0", "eeg": "#DD8452", "ecg": "#55A868"}
    colors = [palette.get(d, "#999999") for d in device_names]

    # ── X-axis range: markers + session durations ──────────────────────
    all_times = []
    for d in device_names:
        if d not in result.assignments:
            continue
        valid = result.assignments[d][~np.isnan(result.assignments[d])]
        if len(valid) > 0:
            all_times.extend(valid)
    # Also consider session total durations so session bars aren't clipped
    for d in device_names:
        s = stack.get(d)
        if s:
            dur = s.get("total_duration", 0) or 0
            if dur > 0:
                all_times.append(dur)
    if not all_times:
        all_times = [0.0, 100.0]
    t_max = max(all_times) if all_times else 100.0
    pad = max(t_max * 0.05, 10.0)
    x_lo = 0.0  # always start at 0
    x_hi = t_max + pad

    fig_h = max(2.5, 1.8 * n_devices + 1.0)
    fig_w = min(max(10, (x_hi - x_lo) / 30 + 6), 28)

    fig, axes = plt.subplots(n_devices, 1, figsize=(fig_w, fig_h),
                             sharex=True, squeeze=False)

    for idx, dev_name in enumerate(device_names):
        ax = axes[idx][0]
        color = colors[idx]
        is_ref = dev_name == ref_name

        assign = result.assignments[dev_name]
        gidx = result.group_indices[dev_name]
        matched = gidx >= 0
        gap_mask = ~matched
        _bar_h = 0.4

        # ── Background track (light line under everything) ─────────────
        ax.axhline(y=0, xmin=0, xmax=1, color="#dddddd",
                   linewidth=2, alpha=0.3, zorder=0)

        # ── Matched markers (filled circles) ───────────────────────────
        matched_t = assign[matched]
        if len(matched_t) > 0:
            ax.scatter(matched_t, np.zeros_like(matched_t),
                       marker="o", s=10, color=color, edgecolors="white",
                       linewidths=0.2, zorder=3)

        # ── Gap markers (hollow circles, at reference time positions) ──
        if np.any(gap_mask):
            ref_t = result.assignments[ref_name]
            gap_t = ref_t[gap_mask]
            if len(gap_t) > 0:
                ax.scatter(gap_t, np.zeros_like(gap_t),
                           marker="o", s=7, facecolors="none",
                           edgecolors=color, linewidths=0.5, alpha=0.5,
                           zorder=3)

        # ── Session bars from gap positions ──────────────────────────
        _bar_h = 0.35
        # Use _gap_info stored by match_baseline for correct session boundaries
        _gi = getattr(result, "_gap_info", {}).get(dev_name)
        _s0: Dict[int, float] = {}
        _s1: Dict[int, float] = {}
        _sessions_labels: List[Dict] = []

        if _gi is not None:
            # _gi is either (starts, gaps, durs, nm) [alignment-groups]
            # or (gaps, durs, nm) [basematch, no alignment groups]
            if len(_gi) == 4:
                _starts, _gap_positions, _durs, _nm_list = _gi
                for _si, (_start, _dur, _gap, _nm) in enumerate(zip(_starts, _durs, _gap_positions, _nm_list)):
                    if _dur > 0:
                        _s0[_si] = _start
                        _s1[_si] = _start + _dur
                    _sessions_labels.append({"nm": _nm})
            else:
                _gap_positions, _durs, _nm_list = _gi
                _cum = 0.0
                for _si, (_dur, _gap, _nm) in enumerate(zip(_durs, _gap_positions, _nm_list)):
                    if _dur > 0:
                        _s0[_si] = _cum
                        _s1[_si] = _cum + _dur
                    _cum += _dur + _gap
                    _sessions_labels.append({"nm": _nm})
        elif dev_name in stack:
            # Fallback: compute from stack positions
            _sessions = stack[dev_name].get("sessions", [])
            _cum = 0.0
            for _si, _s in enumerate(_sessions):
                _dur = _s.get("duration", 0) or 0
                if _dur > 0:
                    _s0[_si] = _cum
                    _s1[_si] = _cum + _dur
                _cum += _dur
                _sessions_labels.append({"nm": _s.get("n_markers", 0)})
            _bm_offset = _sessions[0].get("_basematch_offset", 0.0) if _sessions else 0.0
            if _bm_offset:
                for _si in _s0:
                    _s0[_si] += _bm_offset
                    _s1[_si] += _bm_offset

        # ── Draw session blocks (common code for both paths) ────────────
        if _s0:
            _all_si = sorted(_s0.keys())
            # 1. Color bars
            for _si in _all_si:
                _l = _s0[_si]
                _r = _s1.get(_si, _l)
                if _r - _l < 0.5:
                    _r = _l + 0.5
                _seg_c = cmap_bar(_si % 10)
                _nm_s = _sessions_labels[_si]["nm"] if _si < len(_sessions_labels) else 0
                ax.barh(0, _r - _l, height=0.6, left=_l,
                        color=_seg_c, alpha=0.85,
                        edgecolor="#222222", linewidth=0.6, zorder=0)

            # 2. Gap regions (only for _gi path where we have gap data)
            if _gi is not None:
                if len(_gi) == 4:
                    # Use actual start positions from device_starts
                    _starts_g, _gap_positions_g, _durs_g, _nm_list_g = _gi
                    for _si, (_start, _dur, _gap, _nm) in enumerate(zip(_starts_g, _durs_g, _gap_positions_g, _nm_list_g)):
                        _sess_end = _start + _dur
                        if _gap > 0.5:
                            _gl = _sess_end
                            _gr = _sess_end + _gap
                            ax.axvspan(_gl, _gr, ymin=0.15, ymax=0.85,
                                       color="#cccccc", alpha=0.4, zorder=0)
                            ax.text((_gl + _gr) / 2, 0,
                                    f"Δ{_gap:.0f}s", ha="center", va="center",
                                    fontsize=4.5, color="#666666", style="italic")
                else:
                    _gap_positions_g, _durs_g, _nm_list_g = _gi
                    _cum_g = 0.0
                    for _si, (_dur, _gap, _nm) in enumerate(zip(_durs_g, _gap_positions_g, _nm_list_g)):
                        _cum_g += _dur
                        if _gap > 0.5:
                            _gl = _cum_g
                            _gr = _cum_g + _gap
                            ax.axvspan(_gl, _gr, ymin=0.15, ymax=0.85,
                                       color="#cccccc", alpha=0.4, zorder=0)
                            ax.text((_gl + _gr) / 2, 0,
                                    f"Δ{_gap:.0f}s", ha="center", va="center",
                                    fontsize=4.5, color="#666666", style="italic")
                        _cum_g += _gap

            # 3. Session boundary lines BETWEEN bars
            for _i in range(len(_all_si) - 1):
                _sep = (_s1[_all_si[_i]] + _s0[_all_si[_i + 1]]) / 2.0
                ax.axvline(x=_sep, ymin=0.2, ymax=0.8,
                           color="#333333", linewidth=0.6,
                           linestyle="-", zorder=1)

            # 4. Session labels below the track
            for _si in _all_si:
                _cx = (_s0[_si] + _s1.get(_si, _s0[_si])) / 2.0
                _nm_s = _sessions_labels[_si]["nm"] if _si < len(_sessions_labels) else 0
                _label = f"S{_si+1}"
                if _nm_s == 0:
                    _label += "(g)"
                ax.text(_cx, -0.55, _label,
                        ha="center", fontsize=4.5, color="#444444",
                        fontweight="bold",
                        style="italic" if _nm_s == 0 else "normal")

        # ── Per-device match count ─────────────────────────────────────
        nm = int(matched.sum())
        nt = len(assign)
        ax.text(x_hi - pad * 0.1, 0,
                f"{nm}/{nt}",
                ha="right", va="center", fontsize=7, color=color,
                fontweight="bold")

        # ── Axis styling ──────────────────────────────────────────────
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(-0.6, 0.7)
        ax.set_yticks([0])
        label = dev_name.upper()
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

    # ── Match lines between adjacent devices ──────────────────────────
    for idx in range(n_devices - 1):
        ax_t = axes[idx][0]
        ax_b = axes[idx + 1][0]
        d_t = device_names[idx]
        d_b = device_names[idx + 1]
        a_t = result.assignments[d_t]
        a_b = result.assignments[d_b]
        g_t = result.group_indices[d_t]
        g_b = result.group_indices[d_b]

        both = (g_t >= 0) & (g_b >= 0)
        if not np.any(both):
            continue

        gi = np.where(both)[0]
        step = max(1, len(gi) // 40)
        for g in gi[::step]:
            tt = a_t[g]
            tb = a_b[g]
            if np.isnan(tt) or np.isnan(tb):
                continue
            fc_t = ax_t.transData.transform((tt, 0))
            fc_b = ax_b.transData.transform((tb, 0))
            inv = fig.transFigure.inverted()
            pt_t = inv.transform(fc_t)
            pt_b = inv.transform(fc_b)
            fig.lines.append(plt.Line2D(
                [pt_t[0], pt_b[0]],
                [pt_t[1], pt_b[1]],
                transform=fig.transFigure,
                color="#aaaaaa", linewidth=0.3, alpha=0.2, zorder=0,
            ))

    # ── Title & labels ────────────────────────────────────────────────
    axes[-1][0].set_xlabel("Time (seconds)", fontsize=9)
    fig.suptitle(
        f"Subject {subject_id} — Matched Timeline\n"
        f"ref: {ref_name}  |  "
        f"matched {result.n_matched_groups}/{result.n_groups} groups  |  "
        f"mean distance: {result.mean_distance:.3f}s",
        fontsize=11, fontweight="bold", y=0.97,
    )

    legend_elements = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#555555",
                   markersize=5, label="Matched marker"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="none",
                   markeredgecolor="#555555", markersize=4, label="Gap (unmatched)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=2, frameon=True, fontsize=7,
               bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.05, 1, 0.93])

    # Save next to the timeline CSV
    path = os.path.join(output_dir, f"{prefix}_matched_timeline.png")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved matched timeline figure → {os.path.basename(path)}")
    return path


def _save_stacked_metadata_json(
    result: TraversalMatchResult,
    stack: Dict[str, Dict[str, Any]],
    device_info_list: List[Dict[str, Any]],
    timeline_metadata: Dict[str, Any],
    device_names: List[str],
    drift_offsets: Dict[str, float],
    output_dir: str,
    prefix: str,
) -> str:
    """
    Save a metadata JSON in **matchcrop-aligned compatible format**,
    with full ``device_info`` and ``timeline_metadata`` sections so that
    :func:`~multichsync.marker.matchcrop_aligned.matchcrop_aligned` can
    consume this file directly.
    """
    meta = {
        "algorithm": "traversal_shift_stacked",
        "anchor": result.anchor_name,
        "devices": device_names,
        "n_groups": result.n_groups,
        "n_matched_groups": result.n_matched_groups,
        "total_distance": float(result.total_distance),
        "mean_distance": float(result.mean_distance),
        "gaps": {
            k: {"n_gaps": len(v), "groups": v}
            for k, v in result.gaps.items()
        },
        "shift_history": {
            k: [{"shift": s, "mean_distance": md} for s, md in v]
            for k, v in result.shift_history.items()
        },
        # ── matchcrop-aligned sections ────────────────────────────────
        "device_info": device_info_list,
        "timeline_metadata": timeline_metadata,
        "output_files": {
            "timeline_csv": f"{prefix}_timeline.csv",
            "stacked_timeline_csv": f"{prefix}_stacked_timeline.csv",
        },
    }
    path = os.path.join(output_dir, f"{prefix}_metadata.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, default=str)
    print(f"Saved stacked metadata (matchcrop-aligned compatible) → {path}")
    return path


# ══════════════════════════════════════════════════════════════════════
# Simple CLI helper
# ══════════════════════════════════════════════════════════════════════


def match_traversal_cli(args: Any) -> None:
    """Entry point called from ``multichsync marker traversal-match``."""
    from .matcher import load_marker_csv_enhanced

    # ── Detect input mode ──────────────────────────────────────────────
    info_dir = getattr(args, "info_dir", None)
    if info_dir:
        # === Mode A: per-subject stacked-timeline matching ===
        results = match_traversal_from_info(
            info_dir,
            marker_base_dir=getattr(args, "marker_base_dir", "Data/marker"),
            convert_base_dir=getattr(args, "convert_base_dir", "Data/convert"),
            max_time_diff=args.max_time_diff,
            gap_penalty=args.gap_penalty,
            random_restarts=args.random_restarts,
            rng_seed=args.rng_seed,
            output_dir=args.output_dir or "Data/matching",
            output_prefix=args.output_prefix or "traversal_matched",
            save_json=not args.no_json,
            save_csv=not args.no_csv,
            save_fig=not getattr(args, "no_fig", False),
        )
        # Summary is printed inside match_traversal_from_info
        return
    else:
        # === Mode B: direct file list (original behaviour) ===
        file_paths: List[str] = []
        device_names: Optional[List[str]] = None

        if args.input_dir:
            input_dir = Path(args.input_dir)
            if not input_dir.exists():
                raise FileNotFoundError(f"Input directory not found: {input_dir}")
            csv_files = sorted(input_dir.glob("*.csv"))
            if len(csv_files) < 2:
                raise ValueError(
                    f"Need ≥2 CSV files, found {len(csv_files)} in {input_dir}"
                )
            file_paths = [str(f) for f in csv_files]
            print(f"Loaded {len(file_paths)} files from {input_dir}")
        elif args.input_files:
            file_paths = list(args.input_files)
            print(f"Loaded {len(file_paths)} specified files")
        else:
            raise ValueError("Provide --input-dir or --input-files or --info-dir")

        if args.device_names:
            device_names = args.device_names

        # Session merging flag (default: merge)
        merge_sessions = not getattr(args, "no_merge_sessions", False)

        result = match_traversal_from_files(
            file_paths,
            device_names=device_names,
            max_time_diff=args.max_time_diff,
            gap_penalty=args.gap_penalty,
            random_restarts=args.random_restarts,
            rng_seed=args.rng_seed,
            output_dir=args.output_dir or "Data/matching",
            output_prefix=args.output_prefix or "traversal_matched",
            save_json=not args.no_json,
            save_csv=not args.no_csv,
            merge_sessions=merge_sessions,
        )

        # ── Print summary ─────────────────────────────────────────────────
        print(f"\n{'='*50}")
        print(f"Traversal matching complete")
        print(f"{'='*50}")
        print(f"  Reference device:  {result.anchor_name}")
        print(f"  Devices:           {', '.join(result.device_names)}")
        print(f"  Consensus groups:  {result.n_groups}")
        print(f"  Matched groups:    {result.n_matched_groups}")
        print(f"  Total distance:    {result.total_distance:.4f} s")
        print(f"  Mean distance:     {result.mean_distance:.4f} s")
        if result.gaps:
            for dev, grps in result.gaps.items():
                print(f"  Gaps in {dev}:      {len(grps)}")
        print(f"{'='*50}\n")


# ══════════════════════════════════════════════════════════════════════
# BaseMatch —  length-first, marker-second alignment
# ══════════════════════════════════════════════════════════════════════


def _group_sessions_by_length(
    ref_sessions: List[Dict[str, Any]],
    other_sessions: List[Dict[str, Any]],
    snap_threshold: float = 5.0,
) -> Tuple[List[List[int]], List[float]]:
    """
    Greedily group *other_sessions* so each group's total duration
    approximates a reference session (within ±*snap_threshold*).

    Returns
    -------
    (groups, group_target_durs)
        ``groups[g]`` = list of indices into *other_sessions*
        ``group_target_durs[g]`` = the reference duration this group maps to
    """
    ref_durs = [s["duration"] for s in ref_sessions]
    other_durs = [s["duration"] for s in other_sessions]

    groups: List[List[int]] = []
    targets: List[float] = []
    oi = 0  # index into other_sessions

    for rd in ref_durs:
        if oi >= len(other_durs):
            break
        group: List[int] = []
        group_sum = 0.0
        # Keep adding sessions while group_sum < target (or close)
        while oi < len(other_durs):
            next_sum = group_sum + other_durs[oi]
            if group_sum > 0 and abs(next_sum - rd) > abs(group_sum - rd):
                # Adding this session makes it worse — stop (unless group is empty)
                if abs(group_sum - rd) <= snap_threshold:
                    break
                # If current group is far from target, try including next session
                if abs(next_sum - rd) <= abs(group_sum - rd):
                    group.append(oi)
                    group_sum = next_sum
                    oi += 1
                break
            group.append(oi)
            group_sum = next_sum
            oi += 1
        if group:
            groups.append(group)
            targets.append(rd)

    # Any remaining other sessions form their own group
    while oi < len(other_durs):
        groups.append([oi])
        targets.append(other_durs[oi])
        oi += 1

    return groups, targets


def _reposition_by_groups(
    t_other: np.ndarray,
    other_sessions: List[Dict[str, Any]],
    groups: List[List[int]],
    targets: List[float],
    cumulative_offset: float,
) -> Tuple[np.ndarray, List[float]]:
    """
    Reposition *other* markers by grouping sessions to match *targets*.

    Algorithm
    ---------
    1. Within each group the **first** session start is snapped to the
       reference session start, the **last** session end is snapped to the
       reference session end.
    2. If the group's total duration differs from the target, the
       difference is distributed as **gaps** between consecutive sessions
       inside the group.
    3. Sessions keep their internal marker spacing unchanged — only the
       gap between sessions is adjusted.
    4. If a group has only 1 session, it is stretched/squeezed to match
       the target (same as proportional stretching at the session level).

    Returns
    -------
    (repositioned_markers, gap_positions)
        ``gap_positions[i]`` = duration of gap inserted after session *i*
        (0 for sessions within the same relative position).
    """
    if not groups:
        return t_other.copy(), []

    # Build original per-session marker arrays
    sess_markers: List[np.ndarray] = []
    idx = 0
    for s in other_sessions:
        n = s["n_markers"]
        if n > 0:
            sess_markers.append(t_other[idx: idx + n].copy())
        else:
            sess_markers.append(np.array([], dtype=float))
        idx += n

    gap_positions: List[float] = [0.0] * len(other_sessions)
    new_markers: List[np.ndarray] = []
    current_offset = 0.0

    for g_idx, group in enumerate(groups):
        target = targets[g_idx]
        group_dur = sum(other_sessions[si]["duration"] for si in group)
        gap_total = target - group_dur  # positive = extra gap, negative = squeeze
        n_gaps = len(group) - 1  # gaps BETWEEN sessions

        if len(group) == 1:
            # Single session: stretch/squeeze proportionally
            si = group[0]
            factor = target / group_dur if group_dur > 0 else 1.0
            markers = sess_markers[si] * factor + current_offset
            new_markers.append(markers)
            current_offset += target
        else:
            # Multiple sessions: distribute gap between them
            gap_each = gap_total / n_gaps if n_gaps > 0 else 0.0

            for pos_in_group, si in enumerate(group):
                markers = sess_markers[si] + current_offset
                new_markers.append(markers)
                dur = other_sessions[si]["duration"]
                current_offset += dur

                # Add gap after this session (except last)
                if pos_in_group < n_gaps:
                    gap_positions[si] = gap_each
                    current_offset += gap_each

    result = np.concatenate(new_markers) if new_markers else np.array([], dtype=float)
    return result, gap_positions


def _evaluate_middle_shift(
    t_ref: np.ndarray,
    repositioned: np.ndarray,
    sessions: List[Dict[str, Any]],
    gap_positions: List[float],
    group_spec: Tuple[int, int, int],  # (group_idx, start_session_idx, end_session_idx)
    mid_shift: float,
    max_time_diff: float,
    gap_penalty: float,
) -> Tuple[float, np.ndarray]:
    """
    Shift the middle sessions of a group by *mid_shift* seconds and
    re-evaluate match quality.  The first and last sessions in the group
    stay fixed.
    """
    # Build current marker array with shifted middle sessions
    # ... (simplified: just return mean distance)
    shifted = repositioned.copy()
    gs_idx, ss, es = group_spec
    # Find indices in repositioned that correspond to the group's sessions
    cum = 0
    for sidx in range(len(sessions)):
        n = sessions[sidx]["n_markers"]
        if n > 0:
            if ss < sidx < es:
                shifted[cum: cum + n] += mid_shift
            cum += n

    # Greedy matching
    sort_idx = np.argsort(shifted)
    sorted_s = shifted[sort_idx]
    n_ref = len(t_ref)
    used = np.zeros(len(shifted), dtype=bool)
    total_dist = 0.0
    n_matched = 0

    for i in range(n_ref):
        rt = t_ref[i]
        pos = np.searchsorted(sorted_s, rt)
        candidates = []
        for off in (-1, 0, 1):
            p = pos + off
            if 0 <= p < len(sorted_s) and not used[p]:
                candidates.append((p, abs(sorted_s[p] - rt)))
        if candidates:
            bp, bd = min(candidates, key=lambda x: x[1])
            if bd <= max_time_diff:
                total_dist += float(bd)
                used[bp] = True
                n_matched += 1
                continue
        total_dist += gap_penalty

    mean_d = total_dist / n_ref if n_ref > 0 else 0.0
    return mean_d, shifted


def _force_pivot_assignments(
    assignments: Dict[str, np.ndarray],
    group_indices: Dict[str, np.ndarray],
    t_anchor: np.ndarray,
    session_dict: Dict[str, List[Dict[str, Any]]],
    ref_sessions: List[Dict[str, Any]],
    anchor: str,
    device_names: List[str],
) -> None:
    """
    Post-processing force-alignment of pivot sessions at the assignment level.

    If ``fnirs`` has ``sequence_id=="ses02"`` AND ``ecg`` has
    ``sequence_id=="ses02"`` AND ``eeg`` has ``sequence_id=="ses03"``,
    the **first marker** of each of those pivot sessions is forced to the
    **same time position** in the final ``assignments``.

    **Anchor IS a pivot device** — all pivot devices' first pivot marker
    positions are snapped to the anchor's first pivot marker position.

    **Anchor is NOT a pivot device** — the three pivot devices' first
    pivot marker positions are set to their mean (so they all agree).

    The function works at the *output* level, so it is immune to any
    mis-grouping or re-adjustment by the baseline matching internals.
    Distances at the forced indices become 0, which is acceptable given
    the requirement for strict alignment.

    Parameters
    ----------
    assignments : dict
        Final matched marker-time arrays, ``{dev: (n_anchor,)}``.
        Modified in-place.
    group_indices : dict
        ``group_indices[dev][i]`` = index into dev's original marker
        array that matched anchor marker *i*.
    t_anchor : ndarray
        Anchor marker positions (the reference timeline).
    session_dict : dict
        Original session data ``{dev: [session-dict, ...]}``.
    ref_sessions : list
        Anchor's session list.
    anchor : str
        Anchor device name.
    device_names : list of str
        All device names in order.
    """
    pivot_condition: Dict[str, str] = {
        "fnirs": "ses02",
        "ecg": "ses02",
        "eeg": "ses03",
    }

    # ── Quick condition check ────────────────────────────────────────
    for dev_name, target_sid in pivot_condition.items():
        if dev_name not in session_dict:
            return
        sessions = session_dict[dev_name]
        if not any(str(s.get("sequence_id", "")) == target_sid for s in sessions):
            return

    n_anchor = len(t_anchor)

    # ── Helpers: find first marker index of a session, return None if missing ──
    def _first_marker_idx(sessions: List[Dict[str, Any]], sid: str) -> Optional[int]:
        cum = 0
        for s in sessions:
            n = max(s.get("n_markers", 0), 0)
            if str(s.get("sequence_id", "")) == sid:
                return cum if n > 0 else None
            cum += n
        return None

    # ── Find pivot first-marker local index for each device ──────
    # local_idx = position within the device's own marker array (sorted_dict)
    pivot_local: Dict[str, int] = {}
    for dev_name, target_sid in pivot_condition.items():
        if dev_name not in session_dict:
            return
        idx = _first_marker_idx(session_dict[dev_name], target_sid)
        if idx is None:
            return
        pivot_local[dev_name] = idx

    # ── Map local marker index → anchor marker index via group_indices ──
    # For each pivot device, find which anchor index its pivot first marker
    # was matched to.  group_indices[dev][i] = local marker index at anchor i.
    pivot_anchor_idx: Dict[str, int] = {}
    for dev_name in pivot_condition:
        if dev_name not in group_indices:
            return
        gidx_arr = group_indices[dev_name]
        local_target = pivot_local[dev_name]
        matches = np.where(gidx_arr == local_target)[0]
        if len(matches) == 0:
            # The pivot first marker was not matched to any anchor marker
            # (gap / beyond max_time_diff).  Try the closest anchor index.
            # We'll fall back to searching by time position.
            continue
        pivot_anchor_idx[dev_name] = int(matches[0])

    # For devices where we couldn't find the anchor index via group_indices,
    # try to find it via the ORIGINAL time position of the pivot first marker.
    # The original stacked position = sum of preceding sessions' durations.
    for dev_name in pivot_condition:
        if dev_name in pivot_anchor_idx:
            continue
        sessions = session_dict[dev_name]
        sid = pivot_condition[dev_name]
        # Compute the natural start time of the pivot session
        natural_start = 0.0
        for s in sessions:
            if str(s.get("sequence_id", "")) == sid:
                break
            natural_start += s.get("duration", 0.0) or 0.0
        # Find the anchor marker closest to this time
        aidx = int(np.argmin(np.abs(t_anchor - natural_start)))
        pivot_anchor_idx[dev_name] = aidx

    if not pivot_anchor_idx:
        return

    # ── Determine the target position ─────────────────────────────
    anchor_pivot_sid = pivot_condition.get(anchor)
    if anchor_pivot_sid is not None and anchor in pivot_anchor_idx:
        # Anchor IS a pivot device → use its position as the target
        aai = pivot_anchor_idx[anchor]
        if 0 <= aai < n_anchor:
            target_pos = float(t_anchor[aai])
        else:
            return
    else:
        # Anchor is NOT a pivot device → align to mean of all found
        positions = []
        for dev_name, aidx in pivot_anchor_idx.items():
            if 0 <= aidx < n_anchor and not np.isnan(assignments[dev_name][aidx]):
                positions.append(float(assignments[dev_name][aidx]))
        if not positions:
            return
        target_pos = sum(positions) / len(positions)

    print(
        f"    Force pivot alignment: fnirs(ses02)/ecg(ses02)/eeg(ses03) "
        f"→ t={target_pos:.2f}s"
    )

    # ── Snap every pivot device's assignment at the pivot anchor index ──
    any_snapped = False
    for dev_name in pivot_condition:
        aidx = pivot_anchor_idx.get(dev_name)
        if aidx is None or not (0 <= aidx < n_anchor):
            continue
        if dev_name not in assignments:
            continue
        if np.isnan(assignments[dev_name][aidx]):
            print(f"      [{dev_name}] first pivot marker unmatched, skipping")
            continue
        delta = target_pos - assignments[dev_name][aidx]
        if abs(delta) < 0.001:
            continue
        assignments[dev_name][aidx] = target_pos
        any_snapped = True
        print(f"      [{dev_name}] pivot first marker shifted by {delta:+.3f}s")

    if not any_snapped:
        print("      (no markers were moved)")


def match_baseline(
    marker_dict: Dict[str, np.ndarray],
    session_dict: Dict[str, List[Dict[str, Any]]],
    *,
    anchor: Optional[str] = None,
    max_time_diff: float = 10.0,
    gap_penalty: float = 1e6,
    snap_threshold: float = 5.0,
) -> TraversalMatchResult:
    """
    **Base-match**: align by session lengths first, then by markers.

    Workflow
    --------
    1. Pick the device with the **longest duration** as anchor.
    2. For each other device, group its sessions (via
       :func:`_group_sessions_by_length`) to match the anchor's session
       durations (±*snap_threshold*).
    3. Reposition markers by :func:`_reposition_by_groups` so start/end
       of each session group align with the corresponding anchor session.
       Duration mismatches become gaps **between** sessions.
    4. For groups with 3+ sessions, fine-tune middle session positions
       via a small traversal search.
    5. Single-session devices are centre-aligned.
    6. Finally greedily match markers by nearest neighbour.

    Returns
    -------
    TraversalMatchResult
    """
    if len(marker_dict) < 2:
        raise ValueError(f"Need at least 2 devices, got {len(marker_dict)}")

    sorted_dict: Dict[str, np.ndarray] = {}
    for name, ts in marker_dict.items():
        t = np.asarray(ts, dtype=float).ravel()
        # Do NOT globally sort — preserve per-session order so that
        # session annotation and boundary alignment work correctly.
        sorted_dict[name] = t

    # Anchor = device with markers AND longest total duration
    if anchor is None:
        candidates = [
            n for n in sorted_dict
            if n in session_dict and len(sorted_dict[n]) > 0
        ]
        if not candidates:
            raise ValueError("No device has markers — cannot determine anchor")
        anchor = max(
            candidates,
            key=lambda k: sum(s["duration"] for s in session_dict.get(k, [])),
        )
    elif anchor not in sorted_dict:
        raise ValueError(f"Anchor '{anchor}' not found")

    device_names = [anchor] + [n for n in sorted_dict if n != anchor]
    t_anchor_raw = sorted_dict[anchor]
    ref_sessions = session_dict.get(anchor, [])

    ref_dur = sum(s["duration"] for s in ref_sessions)

    # Compute max duration across ALL devices (for gap capping).
    # Also compute the max duration of 0‑marker devices (ecg continuous
    # recordings) — non‑anchor devices must not exceed this cap.
    _all_durs = [sum(s["duration"] for s in session_dict.get(n, [])) for n in device_names]
    max_dur = max(_all_durs)
    _markerless_durs = [
        d for d, n in zip(_all_durs, device_names)
        if len(sorted_dict.get(n, [])) == 0
    ]
    gap_cap = max(_markerless_durs) if _markerless_durs else max_dur

    # Reposition anchor markers — stretch to max_dur if needed
    _anchor_targets = [s["duration"] for s in ref_sessions]
    _anchor_sum = sum(_anchor_targets)
    if _anchor_sum < max_dur and _anchor_targets:
        _anchor_targets[-1] += max_dur - _anchor_sum
    _anchor_repos, _ = _reposition_by_groups(
        t_anchor_raw, ref_sessions,
        [[i] for i in range(len(ref_sessions))],
        _anchor_targets,
        0.0,
    )
    t_anchor = _anchor_repos
    n_anchor = len(t_anchor)

    # Store gap positions per device for session bar computation
    _all_gap_info: Dict[str, Tuple[List[float], List[float], List[int]]] = {}
    # Anchor gap info: no gaps, each session stands alone
    _all_gap_info[anchor] = (
        [0.0] * len(ref_sessions),
        [s["duration"] for s in ref_sessions],
        [s["n_markers"] for s in ref_sessions],
    )

    assignments: Dict[str, np.ndarray] = {anchor: t_anchor.copy()}
    group_indices: Dict[str, np.ndarray] = {anchor: np.arange(n_anchor, dtype=int)}
    shift_history: Dict[str, List[Tuple[int, float]]] = {}

    # Storage for multi-device boundary consensus
    _repos_store: Dict[str, Tuple[np.ndarray, List]] = {}
    _repos_order: List[str] = []

    for dev_name in device_names[1:]:
        t_dev = sorted_dict[dev_name]
        dev_sessions = session_dict.get(dev_name, [])
        dev_dur = sum(s["duration"] for s in dev_sessions)

        if not dev_sessions or len(dev_sessions) == 0:
            print(f"    [{dev_name}] no sessions, skipped")
            continue

        # ── Skip devices with total duration < 50% of max_dur ──────────
        if dev_dur < max_dur * 0.5:
            print(f"    [{dev_name}] duration {dev_dur:.1f}s < 50% "
                  f"of max_dur {max_dur:.1f}s — skipped")
            continue

        if all(s.get("n_markers", 0) == 0 for s in dev_sessions):
            # 0‑marker device – force start=0
            _offset = 0.0
            dev_sessions[0]["_basematch_offset"] = _offset
            shift_history[dev_name] = [(_offset, 0.0)]
            dev_assign = np.full(n_anchor, np.nan)
            dev_indices = np.full(n_anchor, -1, dtype=int)
            assignments[dev_name] = dev_assign
            group_indices[dev_name] = dev_indices
            _all_gap_info[dev_name] = (
                [0.0] * len(dev_sessions),
                [s["duration"] for s in dev_sessions],
                [s["n_markers"] for s in dev_sessions],
            )
            print(f"    [{dev_name}] 0 markers, force-aligned to start=0 "
                  f"({len(dev_sessions)} session(s))")
            continue

        # ── Phase 1 — Force start=0, end=max_dur, evenly distributed gaps ──
        n_sess = len(dev_sessions)
        if n_sess > 1:
            groups = [list(range(n_sess))]
            targets = [max_dur]
        else:
            groups = [[0]]
            targets = [max_dur]

        repositioned, gap_pos = _reposition_by_groups(
            t_dev, dev_sessions, groups, targets, 0.0
        )

        total_gap = sum(gap_pos)

        # ── Phase 2 — Session-by-session shift within gap bounds ─────
        # Each session may shift left (up to gap_before) or right
        # (up to gap_after) to improve marker alignment with anchor.
        final_aligned = repositioned.copy()
        if n_sess > 1 and total_gap > 0.01 and len(final_aligned) > 0:
            # Map each marker to its session index
            marker_sess_idx = np.concatenate([
                np.full(s["n_markers"], si, dtype=int)
                for si, s in enumerate(dev_sessions)
                if s["n_markers"] > 0
            ])

            # Cumulative session start positions in repositioned space
            _sess_starts = [0.0]
            for si in range(n_sess - 1):
                dur = dev_sessions[si]["duration"]
                g = gap_pos[si]
                _sess_starts.append(_sess_starts[-1] + dur + g)

            for si in range(n_sess):
                sess_mask = marker_sess_idx == si
                sess_inds = np.where(sess_mask)[0]
                if len(sess_inds) == 0:
                    continue

                # Gap available on each side of this session
                gap_before = gap_pos[si - 1] if si > 0 else 0.0
                gap_after  = gap_pos[si] if si < n_sess - 1 else 0.0

                if gap_before <= 0.01 and gap_after <= 0.01:
                    continue

                shift_min = -gap_before
                shift_max =  gap_after

                # Anchor markers roughly in this session's window
                sess_t_start = _sess_starts[si]
                sess_t_end   = _sess_starts[si] + dev_sessions[si]["duration"]
                anchor_mask  = (t_anchor >= sess_t_start - 1.0) & (t_anchor <= sess_t_end + 1.0)
                anchor_vals  = t_anchor[anchor_mask]
                if len(anchor_vals) == 0:
                    continue

                best_shift = 0.0
                best_mean  = float("inf")

                # Adaptive step size: finer for small gaps, coarser for large gaps
                gap_range = gap_before + gap_after
                step = 0.1 if gap_range <= 5.0 else (0.5 if gap_range <= 30.0 else 2.0)
                n_steps = int(np.floor(gap_range / step)) + 1

                for shift_step in range(n_steps + 1):
                    shift = round(shift_min + shift_step * step, 2)
                    if shift > shift_max + 0.01:
                        break
                    shifted_markers = final_aligned[sess_inds] + shift

                    # Greedy match within this session's markers
                    sort_idx = np.argsort(shifted_markers)
                    sorted_m = shifted_markers[sort_idx]
                    used = np.zeros(len(shifted_markers), dtype=bool)
                    total_d = 0.0
                    for av in anchor_vals:
                        pos = np.searchsorted(sorted_m, av)
                        best_d = float("inf")
                        best_p = -1
                        for off in (-1, 0, 1):
                            p = pos + off
                            if 0 <= p < len(sorted_m) and not used[p]:
                                d = abs(sorted_m[p] - av)
                                if d < best_d:
                                    best_d = d
                                    best_p = p
                        if best_d <= max_time_diff and best_p >= 0:
                            total_d += best_d
                            used[best_p] = True
                        else:
                            total_d += gap_penalty

                    mean_d = total_d / len(anchor_vals)
                    if mean_d < best_mean:
                        best_mean = mean_d
                        best_shift = shift

                if abs(best_shift) > 0.01:
                    final_aligned[sess_inds] += best_shift
                    # Shrink the gap that was consumed by the shift
                    if best_shift < 0 and si > 0:
                        gap_pos[si - 1] = max(0.0, gap_pos[si - 1] + best_shift)
                    elif best_shift > 0 and si < n_sess - 1:
                        gap_pos[si] = max(0.0, gap_pos[si] - best_shift)

        print(
            f"    [{dev_name}] {len(groups)} group(s), "
            f"{len(dev_sessions)} session(s), "
            f"gap={total_gap:.1f}s"
        )
        # Store gap positions for session bar computation
        _all_gap_info[dev_name] = (
            gap_pos,
            [s["duration"] for s in dev_sessions],
            [s["n_markers"] for s in dev_sessions],
        )
        # Store repositioned markers for multi-device boundary consensus
        _repos_store[dev_name] = (final_aligned.copy(), dev_sessions)
        _repos_order.append(dev_name)

        # Greedy matching on final_aligned
        sort_idx = np.argsort(final_aligned)
        sorted_final = final_aligned[sort_idx]
        used = np.zeros(len(final_aligned), dtype=bool)
        a_idxs: List[int] = []
        b_idxs: List[int] = []
        total_dist = 0.0
        n_matched = 0

        for i in range(n_anchor):
            rt = t_anchor[i]
            pos = np.searchsorted(sorted_final, rt)
            candidates = []
            for off in (-1, 0, 1):
                p = pos + off
                if 0 <= p < len(sorted_final) and not used[p]:
                    candidates.append((p, abs(sorted_final[p] - rt)))
            if candidates:
                bp, bd = min(candidates, key=lambda x: x[1])
                if bd <= max_time_diff:
                    total_dist += float(bd)
                    a_idxs.append(i)
                    b_idxs.append(int(sort_idx[bp]))
                    used[bp] = True
                    n_matched += 1
                    continue
            total_dist += gap_penalty

        mean_d = total_dist / n_anchor if n_anchor > 0 else 0.0
        shift_history[dev_name] = [(total_gap, mean_d)]

        dev_assign = np.full(n_anchor, np.nan)
        dev_indices = np.full(n_anchor, -1, dtype=int)
        for i, j in zip(a_idxs, b_idxs):
            dev_assign[i] = final_aligned[j]
            dev_indices[i] = j
        assignments[dev_name] = dev_assign
        group_indices[dev_name] = dev_indices

    # ── Multi-device session boundary consensus ──────────────────────
    # Collect session boundaries from ALL devices (anchor included).
    # Boundaries within snap_threshold are snapped to their mean.
    all_bounds: Dict[str, np.ndarray] = {}
    for dn in device_names:
        if dn == anchor:
            sessions = ref_sessions
            stretch = 1.0
        elif dn in _repos_store:
            sessions = _repos_store[dn][1]
            stretch = 1.0  # already in repositioned space
        else:
            continue
        cum = 0.0
        bounds = [0.0]
        for s in sessions:
            dur = s.get("duration", 0) or 0
            cum += dur
            bounds.append(cum)
        all_bounds[dn] = np.array(bounds)

    # Cluster boundaries across devices
    if len(all_bounds) >= 2:
        # Collect all interior boundaries (not 0, not total)
        all_pts: List[Tuple[float, str, int]] = []
        for dn, b_arr in all_bounds.items():
            for bi in range(1, len(b_arr) - 1):
                all_pts.append((b_arr[bi], dn, bi))
        all_pts.sort(key=lambda x: x[0])

        # Cluster: group consecutive boundaries within snap_threshold
        clusters: List[List[Tuple[float, str, int]]] = []
        current: List[Tuple[float, str, int]] = []
        for pt in all_pts:
            if not current or pt[0] - current[-1][0] <= snap_threshold:
                current.append(pt)
            else:
                if len(current) >= 2:  # only snap clusters with ≥2 devices
                    clusters.append(current)
                current = [pt]
        if len(current) >= 2:
            clusters.append(current)

        # Snap each cluster to the ANCHOR's boundary (anchor stays fixed).
        for cluster in clusters:
            # Find anchor boundary in cluster if present
            anchor_boundary = None
            for _, dn, bi in cluster:
                if dn == anchor:
                    anchor_boundary = all_bounds[anchor][bi]
                    break
            if anchor_boundary is None:
                continue  # no anchor boundary in this cluster, skip
            for _, dn, bi in cluster:
                if dn == anchor:
                    continue  # anchor stays fixed
                b_arr = all_bounds[dn]
                delta = anchor_boundary - b_arr[bi]
                if abs(delta) <= snap_threshold and dn in _repos_store:
                    markers = _repos_store[dn][0]
                    markers[b_arr[bi] <= markers + 1e-9] += delta
                    b_arr[bi:] += delta

    # ── Greedy matching on consensus-aligned markers ────────────────
    # (Re-run for stored devices with updated markers)
    for dev_name in _repos_order:
        final_aligned, dev_sessions = _repos_store[dev_name]
        t_other = sorted_dict[dev_name]

        sort_idx = np.argsort(final_aligned)
        sorted_final = final_aligned[sort_idx]
        used = np.zeros(len(final_aligned), dtype=bool)
        a_idxs: List[int] = []
        b_idxs: List[int] = []
        total_dist = 0.0
        n_matched = 0

        for i in range(n_anchor):
            rt = t_anchor[i]
            pos = np.searchsorted(sorted_final, rt)
            candidates = []
            for off in (-1, 0, 1):
                p = pos + off
                if 0 <= p < len(sorted_final) and not used[p]:
                    candidates.append((p, abs(sorted_final[p] - rt)))
            if candidates:
                bp, bd = min(candidates, key=lambda x: x[1])
                if bd <= max_time_diff:
                    total_dist += float(bd)
                    a_idxs.append(i)
                    b_idxs.append(int(sort_idx[bp]))
                    used[bp] = True
                    n_matched += 1
                    continue
            total_dist += gap_penalty

        mean_d = total_dist / n_anchor if n_anchor > 0 else 0.0

        dev_assign = np.full(n_anchor, np.nan)
        dev_indices = np.full(n_anchor, -1, dtype=int)
        for i, j in zip(a_idxs, b_idxs):
            dev_assign[i] = final_aligned[j]
            dev_indices[i] = j
        assignments[dev_name] = dev_assign
        group_indices[dev_name] = dev_indices
        total_gap = sum(
            g for g in (shift_history[dev_name][0] if dev_name in shift_history else [0])
        )
        shift_history[dev_name] = [(total_gap, mean_d)]

    # ── Force pivot session alignment at the output level ────────────
    # Overrides any mis-grouping caused by duration-based logic inside
    # the basematch.  Snaps the first marker of each pivot session to
    # a common time position in the final assignments array.
    _force_pivot_assignments(
        assignments, group_indices, t_anchor,
        session_dict, ref_sessions, anchor, device_names,
    )

    # Per-group distances
    per_marker_distances = np.full(n_anchor, np.nan)
    for g in range(n_anchor):
        times = [assignments[d][g] for d in device_names if d in assignments and not np.isnan(assignments[d][g])]
        if len(times) >= 2:
            diffs = [abs(times[i] - times[j]) for i in range(len(times)) for j in range(i + 1, len(times))]
            per_marker_distances[g] = float(np.mean(diffs))

    valid = ~np.isnan(per_marker_distances)
    total_distance = float(np.sum(per_marker_distances[valid]))
    mean_distance = float(np.mean(per_marker_distances[valid])) if valid.any() else 0.0
    n_matched_groups = int(valid.sum())

    gaps: Dict[str, List[int]] = {}
    for d in device_names:
        if d not in group_indices:
            continue
        gs = np.where(group_indices[d] == -1)[0].tolist()
        if gs:
            gaps[d] = gs

    result = TraversalMatchResult(
        anchor_name=anchor,
        device_names=device_names,
        assignments=assignments,
        group_indices=group_indices,
        per_marker_distances=per_marker_distances,
        total_distance=total_distance,
        mean_distance=mean_distance,
        n_groups=n_anchor,
        n_matched_groups=n_matched_groups,
        gaps=gaps,
        shift_history=shift_history,
    )
    result._gap_info = _all_gap_info
    # Build drift_params from shift_history
    _dp: Dict[str, Dict[str, float]] = {anchor: {"offset": 0.0, "scale": 1.0}}
    for _dn in device_names[1:]:
        _hist = shift_history.get(_dn, [(0.0, 0.0)])
        _dp[_dn] = {"offset": _hist[0][0] if isinstance(_hist[0][0], float) else 0.0, "scale": 1.0}
    result._drift_params = _dp
    return result

def match_baseline_cli(args: Any) -> None:
    """CLI entry point for ``multichsync marker basematch``."""
    import json as json_mod
    from .matcher import load_marker_csv_enhanced

    timeline_dir = args.timeline_dir
    timeline_dir_path = Path(timeline_dir)
    if not timeline_dir_path.exists():
        raise FileNotFoundError(f"Timeline directory not found: {timeline_dir}")

    json_files = sorted(timeline_dir_path.glob("subject_*_alignment.json"))
    if not json_files:
        raise FileNotFoundError(
            f"No subject_*_alignment.json files found in {timeline_dir}"
        )

    output_dir = args.output_dir or "Data/matching"
    output_prefix = args.output_prefix or "basematched"
    marker_base_dir = args.marker_base_dir or "Data/marker"
    max_time_diff = args.max_time_diff
    gap_penalty = args.gap_penalty
    save_csv = not args.no_csv
    save_json = not args.no_json
    save_fig = not args.no_fig

    results: Dict[str, TraversalMatchResult] = {}
    total_processed = 0

    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            alignment = json_mod.load(f)

        subject_id = alignment.get("subject_id", "unknown")
        devices_data = alignment.get("devices", [])
        if len(devices_data) < 2:
            print(f"\n  [{subject_id}] Skipped: {len(devices_data)} device(s), need >= 2")
            continue

        print(f"\n{'='*50}")
        print(f"Subject {subject_id} (from {jf.name})")

        # Read top-level start/end alignment groups (filename lists)
        start_groups: List[List[str]] = alignment.get("starttime_align", [])
        end_groups: List[List[str]] = alignment.get("endtime_align", [])
        needmatch_set: set = set(alignment.get("needmatch", []))

        # Build filename → start_time lookup from start_groups.
        # Group 0 starts at 0.0; each subsequent group starts at the
        # cumulative max session-duration of all previous groups.
        file_start_time: Dict[str, float] = {}
        group_start = 0.0
        for group in start_groups:
            max_dur = 0.0
            for fname in group:
                for dev_info in devices_data:
                    if fname in dev_info.get("filenames", []):
                        idx = dev_info["filenames"].index(fname)
                        dur = float(dev_info["durations"][idx]) if idx < len(dev_info["durations"]) else 0.0
                        max_dur = max(max_dur, dur)
                        break
            for fname in group:
                file_start_time[fname] = group_start
            group_start += max_dur

        # Build filename → target end time from end_groups.
        # Within each group, all files are stretched so they end at the
        # same time (the max natural end time of files in that group).
        file_target_end: Dict[str, float] = {}
        for group in end_groups:
            max_end = 0.0
            for fname in group:
                sa = file_start_time.get(fname, 0.0)
                for dev_info in devices_data:
                    if fname in dev_info.get("filenames", []):
                        idx = dev_info["filenames"].index(fname)
                        dur = float(dev_info["durations"][idx]) if idx < len(dev_info["durations"]) else 0.0
                        natural_end = sa + dur
                        max_end = max(max_end, natural_end)
                        break
            for fname in group:
                if fname not in file_target_end or max_end > file_target_end[fname]:
                    file_target_end[fname] = max_end

        # Build session_dict from alignment JSON
        session_dict: Dict[str, List[Dict[str, Any]]] = {}
        valid_devices = []

        for dev_info in devices_data:
            device = dev_info["device"]
            filenames = dev_info.get("filenames", [])
            durations = dev_info.get("durations", [])
            n_markers_list = dev_info.get("n_markers", [])
            seq_ids = dev_info.get("sequence_ids", [])

            if not filenames:
                continue

            # Find marker CSV files for each data filename
            sessions = []
            
            # Pre‑embedded raw markers (new JSON format)
            json_raw = dev_info.get("raw_markers", [])

            for fi, fname in enumerate(filenames):
                # Skip files not in needmatch (user may have trimmed the list)
                if needmatch_set and fname not in needmatch_set:
                    continue
                dur = float(durations[fi]) if fi < len(durations) else 0.0
                nm = int(n_markers_list[fi]) if fi < len(n_markers_list) else 0
                sid = str(seq_ids[fi]) if fi < len(seq_ids) else f"{fi+1:02d}"
                sa = file_start_time.get(fname, 0.0)

                # Try embedded raw_markers (from JSON) first
                if fi < len(json_raw) and len(json_raw[fi]) > 0:
                    raw_markers = np.array(json_raw[fi], dtype=float)
                else:
                    # Fallback: locate marker CSV on disk
                    marker_path = _find_marker_csv(fname, device, marker_base_dir)
                    if marker_path is not None:
                        dev = load_marker_csv_enhanced(marker_path)
                        raw_markers = dev.timestamps_raw
                    else:
                        raw_markers = np.array([], dtype=float)
                        if nm > 0:
                            print(f"    WARNING: [{device}] marker file for {fname} not found in {marker_base_dir}/{device}/")

                sessions.append({
                    "file_name": fname,
                    "sequence_id": sid,
                    "n_markers": nm,
                    "duration": dur,
                    "raw_markers": raw_markers.copy(),
                    "starttime_align": sa,
                })

            if not sessions:
                continue

            session_dict[device] = sessions
            valid_devices.append(device)

            dur_total = sum(s["duration"] for s in sessions)
            nm_total = sum(s["n_markers"] for s in sessions)
            align_str = ", ".join(
                f"{s['starttime_align']:.0f}s"
                for s in sessions
            )
            print(f"  [{device}] {nm_total} markers, {dur_total:.1f}s, "
                  f"{len(sessions)} session(s), "
                  f"start=[{align_str}]")

        if len(valid_devices) < 2:
            print(f"  Skipped: {len(valid_devices)} valid device(s), need >= 2")
            continue

        # ── Branch: basematch algorithm or alignment-group enforcement ──
        if not start_groups:
            # ── No alignment groups → run full basematch algorithm ──
            marker_dict: Dict[str, np.ndarray] = {}
            for dn in valid_devices:
                parts = [s["raw_markers"] for s in session_dict[dn] if len(s["raw_markers"]) > 0]
                marker_dict[dn] = np.concatenate(parts) if parts else np.array([], dtype=float)

            session_simple: Dict[str, List[Dict[str, Any]]] = {}
            for dn in valid_devices:
                session_simple[dn] = [{"duration": s["duration"], "n_markers": s["n_markers"]} for s in session_dict[dn]]

            print(f"  Running full basematch ({len(valid_devices)} devices, {len(needmatch_set)} files in needmatch)")
            try:
                result = match_baseline(
                    marker_dict, session_simple,
                    max_time_diff=max_time_diff,
                    gap_penalty=gap_penalty,
                )
            except ValueError as e:
                print(f"  Skipped: {e}")
                continue
            if result is None:
                continue

            # Build stack_out for saving
            stack_out: Dict[str, Dict[str, Any]] = {}
            for dn in result.device_names:
                s = session_dict.get(dn, [])
                total_dur = sum(ss["duration"] for ss in s)
                total_nm = sum(ss["n_markers"] for ss in s)
                stack_out[dn] = {
                    "total_duration": total_dur,
                    "n_markers_total": total_nm,
                    "stacked_markers": marker_dict.get(dn, np.array([], dtype=float)),
                    "sessions": s,
                }
        else:
            # ── Alignment groups provided → gap‑distribution + sequential session‑matching ──
            # Place starttime_align files at fixed positions, endtime_align files
            # at their target_end positions, and distribute all OTHER sessions
            # sequentially between the fixed boundaries.  Duration differences
            # become **gaps** BETWEEN sessions (never inside a session).
            #
            # Matching: start/end‑aligned sessions are FIXED and do NOT
            # participate in greedy matching.  Only **free** sessions (those
            # not in starttime_align or endtime_align) are matched against
            # each other, using the anchor device's free‑session markers as
            # the reference timeline.

            # Step 0 — classify sessions: which are aligned (fixed) vs free
            # Build a set of all filenames that appear in start or end groups.
            _aligned_fnames: set = set()
            for _g in start_groups:
                for _f in _g:
                    _aligned_fnames.add(_f)
            for _g in end_groups:
                for _f in _g:
                    _aligned_fnames.add(_f)

            # Step 1 — compute per-device session start positions and gaps
            # Sessions are processed in their ORIGINAL session order from the
            # alignment JSON.  Start-aligned sessions are snapped to their
            # file_start_time; end-aligned sessions get an extra gap after
            # the natural end if the target end is further out.
            #
            # For blocks of consecutive FREE sessions (not in start/end
            # groups), the remaining available time between fixed boundaries
            # is distributed EVENLY as gaps BETWEEN the free sessions.
            device_starts: Dict[str, List[float]] = {}
            device_gaps: Dict[str, List[float]] = {}

            for dn in valid_devices:
                sessions = session_dict[dn]
                n_sess = len(sessions)

                starts: List[float] = [0.0] * n_sess
                gaps: List[float] = [0.0] * n_sess

                # --- First pass: position aligned sessions at fixed times ---
                # Mark which sessions are in start/end alignment groups.
                _aligned_mask_inner: List[bool] = [
                    s.get("file_name", "") in _aligned_fnames
                    for s in sessions
                ]

                t = 0.0
                for i in range(n_sess):
                    s = sessions[i]
                    fname = s.get("file_name", "")
                    dur = s["duration"]

                    # Fixed-start constraint -> snap to file_start_time
                    fs = file_start_time.get(fname)
                    if fs is not None:
                        starts[i] = fs
                    else:
                        starts[i] = t

                    natural_end = starts[i] + dur

                    # Fixed-end constraint -> add extra gap after this session
                    fe = file_target_end.get(fname)
                    if fe is not None and fe > natural_end:
                        gap_after = fe - natural_end
                        gaps[i] = gap_after
                        t = max(t, fe)
                    else:
                        t = max(t, natural_end)

                # --- Second pass: distribute gaps evenly inside free blocks ---
                # A "free block" is a run of consecutive non-aligned sessions
                # bounded by aligned sessions (or start/end of device).
                # The available time between the two bounding aligned sessions
                # minus the sum of free-session durations gives the total gap,
                # which is split evenly into (n_free + 1) gaps so that EVERY
                # free session has gap space both BEFORE and AFTER it:
                #   prev_end  [g]  [s0]  [g]  [s1]  [g]  ...  [g]  [sn-1]  [g]  next_start
                _i = 0
                while _i < n_sess:
                    if _aligned_mask_inner[_i]:
                        _i += 1
                        continue

                    # Found start of a free block
                    _block_start = _i
                    while _i < n_sess and not _aligned_mask_inner[_i]:
                        _i += 1
                    _block_end = _i
                    _n_free = _block_end - _block_start

                    # Previous boundary: end of last aligned session (or 0)
                    if _block_start > 0 and _aligned_mask_inner[_block_start - 1]:
                        _prev_idx = _block_start - 1
                        _prev_end = (starts[_prev_idx]
                                     + sessions[_prev_idx]["duration"]
                                     + gaps[_prev_idx])
                    else:
                        _prev_end = 0.0

                    # Next boundary: start of next aligned session, if any.
                    # If no next aligned session, skip gap distribution.
                    if _block_end < n_sess and _aligned_mask_inner[_block_end]:
                        # For end-aligned-only sessions (fe set, no fs), the
                        # correct start position is target_end - duration, NOT
                        # the first-pass sequential position (which just stacks
                        # the gap AFTER the session, making it invisible to the
                        # free block's available-space calculation).
                        _next_fname = sessions[_block_end].get("file_name", "")
                        _next_fe = file_target_end.get(_next_fname)
                        _next_fs = file_start_time.get(_next_fname)
                        if _next_fe is not None and _next_fs is None:
                            _correct_start = _next_fe - sessions[_block_end]["duration"]
                            if _correct_start >= _prev_end:
                                # Reposition the end-aligned session so the
                                # gap is "pulled into" the free block.
                                _next_start = _correct_start
                                starts[_block_end] = _correct_start
                                gaps[_block_end] = 0.0  # natural end = fe
                            else:
                                _next_start = starts[_block_end]
                        else:
                            _next_start = starts[_block_end]
                    else:
                        # Reached end of device with no further aligned
                        # session — keep first-pass sequential positions.
                        continue

                    _available = _next_start - _prev_end
                    _free_sum = sum(sessions[_j]["duration"]
                                    for _j in range(_block_start, _block_end))
                    _total_gap = _available - _free_sum

                    # Distribute total_gap as (n_free + 1) equal gaps:
                    # one before the first free session, (n_free - 1) between
                    # consecutive sessions, and one after the last free session
                    # before the next aligned boundary.
                    if _n_free > 0 and _total_gap > 0:
                        _g_each = _total_gap / (_n_free + 1)
                        _pos = _prev_end + _g_each
                        for _j in range(_block_start, _block_end):
                            starts[_j] = _pos
                            gaps[_j] = _g_each
                            _pos += sessions[_j]["duration"] + _g_each

                device_starts[dn] = starts
                device_gaps[dn] = gaps

            # Step 2 — reposition markers with the computed session offsets
            aligned_marker_dict: Dict[str, np.ndarray] = {}
            for dn in valid_devices:
                sessions = session_dict[dn]
                ss = device_starts[dn]
                parts = []
                for i, s in enumerate(sessions):
                    m = s["raw_markers"]
                    if len(m) > 0:
                        parts.append(m + ss[i])
                    else:
                        parts.append(m)
                aligned_marker_dict[dn] = np.concatenate(parts) if parts else np.array([], dtype=float)

            # Reference = device with the most sessions, since it has the most
            # gaps and its internal gap structure should define the alignment
            # framework.  Other devices (fewer sessions) are refined in Phase 2
            # to match this reference.
            _ref_candidates = sorted(
                valid_devices,
                key=lambda dn: (
                    # session count (primary, descending) — most gaps
                    -len(session_dict[dn]),
                    # free-marker count (secondary, descending)
                    -sum(
                        s["n_markers"] for s in session_dict[dn]
                        if s.get("file_name", "") not in _aligned_fnames
                    ),
                    # total markers (tertiary, descending)
                    -len(aligned_marker_dict[dn]),
                ),
            )
            ref_name = _ref_candidates[0]
            device_names = [ref_name] + [dn for dn in valid_devices if dn != ref_name]
            t_ref_all = aligned_marker_dict[ref_name]
            n_ref = len(t_ref_all)
            print(f"  Ref device: {ref_name} ({n_ref} markers)")

            # Identify which anchor markers belong to free (non‑aligned) sessions.
            # Free markers form the matching reference axis; aligned markers are
            # copied verbatim into assignments without matching.
            _ref_sessions = session_dict[ref_name]
            _ref_free_mask = np.concatenate([
                np.full(max(int(s["n_markers"]), 0),
                        1 if s.get("file_name", "") not in _aligned_fnames else 0,
                        dtype=bool)
                for s in _ref_sessions
            ]) if n_ref > 0 else np.array([], dtype=bool)
            n_ref_free = int(_ref_free_mask.sum())
            t_ref_free = t_ref_all[_ref_free_mask]
            print(f"    free sessions: {n_ref_free} markers (aligned sessions excluded from matching)")

            # Step 3 — Phase 2: session‑by‑session shift within gap bounds.
            # Only non‑aligned (free) sessions are refined.
            final_marker_dict: Dict[str, np.ndarray] = {ref_name: t_ref_all.copy()}
            final_gap_info: Dict[str, Tuple[List[float], List[float], List[float], List[int]]] = {}
            shift_history: Dict[str, List[Tuple[float, float]]] = {}
            # Ref gap info
            _ref_starts = device_starts[ref_name]
            _ref_gaps = device_gaps[ref_name]
            _ref_durs = [s["duration"] for s in _ref_sessions]
            _ref_nm_l = [s["n_markers"] for s in _ref_sessions]
            final_gap_info[ref_name] = (_ref_starts, _ref_gaps, _ref_durs, _ref_nm_l)

            for dn in device_names[1:]:
                sessions = session_dict[dn]
                n_sess = len(sessions)
                t_dev = aligned_marker_dict[dn]
                n_dev = len(t_dev)

                if n_dev == 0 or all(s.get("n_markers", 0) == 0 for s in sessions):
                    final_marker_dict[dn] = t_dev
                    final_gap_info[dn] = (
                        device_starts[dn],
                        device_gaps[dn],
                        [s["duration"] for s in sessions],
                        [s["n_markers"] for s in sessions],
                    )
                    shift_history[dn] = [(0.0, float(gap_penalty))]
                    print(f"  [{dn}] 0 markers, all gaps")
                    continue

                gap_pos = list(device_gaps[dn])
                starts = device_starts[dn]
                repositioned = t_dev.copy()

                if n_sess > 1 and any(g > 0.01 for g in gap_pos):
                    # Map each marker to its session index
                    marker_sess_idx = np.concatenate([
                        np.full(int(s["n_markers"]), si, dtype=int)
                        for si, s in enumerate(sessions)
                        if s["n_markers"] > 0
                    ])
                    if len(marker_sess_idx) > 0:
                        for si in range(n_sess):
                            sess_mask = marker_sess_idx == si
                            sess_inds = np.where(sess_mask)[0]
                            if len(sess_inds) == 0:
                                continue

                            # Only refine free (non‑aligned) sessions
                            _fname = sessions[si].get("file_name", "")
                            if _fname in _aligned_fnames:
                                continue

                            # Gaps available on each side of this session
                            gap_before = gap_pos[si - 1] if si > 0 else 0.0
                            gap_after = gap_pos[si] if si < n_sess - 1 else 0.0

                            if gap_before <= 0.01 and gap_after <= 0.01:
                                continue

                            shift_min = -gap_before
                            shift_max = gap_after

                            # Anchor markers roughly in this session's window
                            sess_t_start = starts[si]
                            sess_t_end = starts[si] + sessions[si]["duration"]
                            anchor_mask = (t_ref_all >= sess_t_start - 1.0) & (t_ref_all <= sess_t_end + 1.0)
                            anchor_vals = t_ref_all[anchor_mask]
                            if len(anchor_vals) == 0:
                                continue

                            best_shift = 0.0
                            best_mean = float("inf")
                            gap_range = gap_before + gap_after

                            if gap_range > 0:
                                step = 0.1 if gap_range <= 5.0 else (0.5 if gap_range <= 30.0 else 2.0)
                                n_steps = int(np.floor(gap_range / step)) + 1

                                for shift_step in range(n_steps + 1):
                                    shift = round(shift_min + shift_step * step, 2)
                                    if shift > shift_max + 0.01:
                                        break
                                    shifted = repositioned[sess_inds] + shift

                                    # Greedy match within this session
                                    sort_idx = np.argsort(shifted)
                                    sorted_s = shifted[sort_idx]
                                    used_local = np.zeros(len(shifted), dtype=bool)
                                    total_d = 0.0
                                    for av in anchor_vals:
                                        pos = np.searchsorted(sorted_s, av)
                                        best_d = float("inf")
                                        best_p = -1
                                        for off in (-1, 0, 1):
                                            p = pos + off
                                            if 0 <= p < len(sorted_s) and not used_local[p]:
                                                d = abs(sorted_s[p] - av)
                                                if d < best_d:
                                                    best_d = d
                                                    best_p = p
                                        if best_d <= max_time_diff and best_p >= 0:
                                            total_d += best_d
                                            used_local[best_p] = True
                                        else:
                                            total_d += gap_penalty

                                    mean_d = total_d / len(anchor_vals)
                                    if mean_d < best_mean:
                                        best_mean = mean_d
                                        best_shift = shift

                                if abs(best_shift) > 0.01:
                                    repositioned[sess_inds] += best_shift
                                    # Consume shift from adjacent gaps
                                    if best_shift < 0 and si > 0:
                                        gap_pos[si - 1] = max(0.0, gap_pos[si - 1] + best_shift)
                                    elif best_shift > 0 and si < n_sess - 1:
                                        gap_pos[si] = max(0.0, gap_pos[si] - best_shift)

                final_marker_dict[dn] = repositioned
                final_gap_info[dn] = (
                    starts,
                    gap_pos,
                    [s["duration"] for s in sessions],
                    [s["n_markers"] for s in sessions],
                )
                shift_history[dn] = [(sum(gap_pos), 0.0)]
                _free_sessions = sum(1 for s in sessions if s.get("file_name", "") not in _aligned_fnames)
                print(f"    [{dn}] {n_sess} session(s) ({_free_sessions} free), gap={sum(gap_pos):.1f}s")

            # Step 4 — Greedy nearest‑neighbour matching.
            # **Only free sessions are matched**; aligned sessions are copied
            # verbatim into the output with their fixed positions.
            assignments: Dict[str, np.ndarray] = {ref_name: t_ref_all.copy()}
            group_indices: Dict[str, np.ndarray] = {ref_name: np.arange(n_ref, dtype=int)}

            for other_name in device_names[1:]:
                t_other = final_marker_dict[other_name]
                n_other = len(t_other)
                if n_other == 0:
                    assignments[other_name] = np.full(n_ref, np.nan)
                    group_indices[other_name] = np.full(n_ref, -1, dtype=int)
                    print(f"  [{other_name}] 0 markers, all gaps")
                    continue

                # Build a free‑only mask for the other device
                _oth_sessions = session_dict[other_name]
                _oth_free_mask = np.concatenate([
                    np.full(max(int(s["n_markers"]), 0),
                            1 if s.get("file_name", "") not in _aligned_fnames else 0,
                            dtype=bool)
                    for s in _oth_sessions
                ]) if n_other > 0 else np.array([], dtype=bool)

                # Only the free markers of the other device are matched to
                # the free markers of the anchor.  Aligned markers are placed
                # verbatim (they are already at their fixed position in t_other).
                t_other_free = t_other[_oth_free_mask]
                n_other_free = len(t_other_free)

                # Pre‑assign aligned markers: they come from t_other at their
                # original index positions.
                def _find_marker_positions(
                    _markers: np.ndarray, _query: np.ndarray
                ) -> Tuple[np.ndarray, np.ndarray]:
                    """For each query time, find closest marker position and index.
                    Returns (time_positions, indices) with NaN/-1 for gaps."""
                    _q_sorted = np.argsort(_markers)
                    _q_sorted_v = _markers[_q_sorted]
                    _out_t = np.full(len(_query), np.nan)
                    _out_i = np.full(len(_query), -1, dtype=int)
                    # For each anchor marker, find best match in query
                    _used_q = np.zeros(len(_markers), dtype=bool)
                    for _ai in np.argsort(_query):
                        _av = _query[_ai]
                        _p = np.searchsorted(_q_sorted_v, _av)
                        _cands = []
                        for _off in (-1, 0, 1):
                            _pp = _p + _off
                            if 0 <= _pp < len(_q_sorted_v) and not _used_q[_pp]:
                                _cands.append((_pp, abs(_q_sorted_v[_pp] - _av)))
                        if _cands:
                            _bp, _bd = min(_cands, key=lambda x: x[1])
                            if _bd <= max_time_diff:
                                _out_t[_ai] = _q_sorted_v[_bp]
                                _out_i[_ai] = int(_q_sorted[_bp])
                                _used_q[_bp] = True
                    return _out_t, _out_i

                dev_assign = np.full(n_ref, np.nan)
                dev_idx = np.full(n_ref, -1, dtype=int)

                # 1. Aligned anchor markers → copy from other device verbatim
                #    (anchor aligned markers keep their fixed positions)
                _aligned_ref_indices = np.where(~_ref_free_mask)[0]
                for _ai in _aligned_ref_indices:
                    dev_assign[_ai] = t_ref_all[_ai]
                    # Find matching index in other device's aligned markers
                    _aligned_other_idx = np.where(~_oth_free_mask)[0]
                    _best = min(
                        ((_oi, abs(t_other[_oi] - t_ref_all[_ai]))
                         for _oi in _aligned_other_idx
                         if not np.isnan(t_other[_oi])),
                        key=lambda x: x[1], default=(None, None)
                    )
                    if _best[0] is not None and _best[1] <= max_time_diff:
                        dev_idx[_ai] = int(_best[0])
                    # dev_assign stays as t_ref_all[_ai] (the anchor's time)

                # 2. Free anchor markers → greedy match against other's free markers
                _free_ref_indices = np.where(_ref_free_mask)[0]
                if n_other_free > 0 and len(_free_ref_indices) > 0:
                    _free_ref_vals = t_ref_all[_free_ref_indices]
                    _free_t, _free_i = _find_marker_positions(
                        t_other_free, _free_ref_vals
                    )
                    for _j, _ai in enumerate(_free_ref_indices):
                        if not np.isnan(_free_t[_j]):
                            dev_assign[_ai] = _free_t[_j]
                            dev_idx[_ai] = _free_i[_j]

                n_matched_total = int(np.sum(dev_idx >= 0))

                assignments[other_name] = dev_assign
                group_indices[other_name] = dev_idx
                print(f"  [{other_name}] matched {n_matched_total}/{n_ref} "
                      f"({n_other_free} free other markers vs {n_ref_free} free ref markers)")

            # Per-group distances
            per_marker_distances = np.full(n_ref, np.nan)
            for g in range(n_ref):
                times = [assignments[d][g] for d in device_names if d in assignments and not np.isnan(assignments[d][g])]
                if len(times) >= 2:
                    diffs = [abs(times[i] - times[j]) for i in range(len(times)) for j in range(i + 1, len(times))]
                    per_marker_distances[g] = float(np.mean(diffs))

            valid_dist_mask = ~np.isnan(per_marker_distances)
            total_distance = float(np.sum(per_marker_distances[valid_dist_mask]))
            mean_distance = float(np.mean(per_marker_distances[valid_dist_mask])) if valid_dist_mask.any() else 0.0
            n_matched_groups = int(valid_dist_mask.sum())

            gap_indices: Dict[str, List[int]] = {}
            for d in device_names:
                gs = np.where(group_indices[d] == -1)[0].tolist()
                if gs:
                    gap_indices[d] = gs

            result = TraversalMatchResult(
                anchor_name=ref_name,
                device_names=device_names,
                assignments=assignments,
                group_indices=group_indices,
                per_marker_distances=per_marker_distances,
                total_distance=total_distance,
                mean_distance=mean_distance,
                n_groups=n_ref,
                n_matched_groups=n_matched_groups,
                gaps=gap_indices,
                shift_history=shift_history,
            )
            result._gap_info = final_gap_info

            # Build stack_out for saving
            stack_out = {}
            for dn in device_names:
                s = session_dict.get(dn, [])
                total_dur = sum(ss["duration"] for ss in s)
                total_nm = sum(ss["n_markers"] for ss in s)
                stack_out[dn] = {
                    "total_duration": total_dur,
                    "n_markers_total": total_nm,
                    "stacked_markers": aligned_marker_dict.get(dn, np.array([], dtype=float)),
                    "sessions": s,
                }

        # ── Common save outputs ─────────────────────────────────────────
        prefix = f"{output_prefix}_subject-{subject_id}"
        os.makedirs(output_dir, exist_ok=True)
        if save_csv:
            _save_stacked_timeline_csv(result, stack_out, output_dir, prefix)
        if save_json:
            _save_metadata_json(result, output_dir, prefix)
        if save_fig:
            try:
                _save_matched_timeline_figure(result, stack_out, subject_id, output_dir, prefix)
            except Exception as e:
                print(f"  Warning: figure failed ({e})")

        results[subject_id] = result
        total_processed += 1

    mode_str = f"aligned via JSON" if start_groups else "basematch (no alignment groups)"
    print(f"\n{'='*50}")
    print(f"Base matching complete ({total_processed} subject(s), {mode_str})")
    print(f"{'='*50}")
    for sid, res in sorted(results.items()):
        print(f"  {sid}: ref={res.anchor_name}, devices={res.device_names}, "
              f"matched={res.n_matched_groups}/{res.n_groups}, mean={res.mean_distance:.3f}s")
    print(f"{'='*50}\n")
