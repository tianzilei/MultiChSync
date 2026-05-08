"""
Iterative marker matching with per-marker distance optimization.

This module provides an alternative to the Hungarian / min-cost-flow / Sinkhorn
approaches.  It uses a simple iterative shift-search strategy:

1. Pick the device with the most markers as the **anchor**.
2. For each other device, search over all possible alignment offsets (shifts)
   to find the one that minimises the **mean pairwise distance** between
   matched markers.
3. Refine the alignment locally by trying ±1 shifts on individual clusters.
4. For gaps (a device has no marker in a segment), the corresponding markers
   from the other devices are left *unmatched* in the output.
5. Return the assignment with the best (lowest) mean / total distance.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────


@dataclass
class IterativeMatchResult:
    """Holds the result of one iterative matching run."""

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
# Core algorithm
# ══════════════════════════════════════════════════════════════════════


def match_iterative(
    marker_dict: Dict[str, np.ndarray],
    *,
    anchor: Optional[str] = None,
    max_time_diff: float = 3.0,
    gap_penalty: float = 1e6,
    refine_iterations: int = 3,
    random_restarts: int = 5,
    rng_seed: int = 42,
) -> IterativeMatchResult:
    """
    Iteratively match markers across devices by searching over alignment
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
    refine_iterations : int
        After the global shift is found, perform this many local refinement
        passes (trying ±1 shifts on individual groups).
    random_restarts : int
        Number of random subsamples used to build initial alignment candidates.
        Only relevant when two devices have very different marker counts.
    rng_seed : int
        Seed for reproducible random restarts.

    Returns
    -------
    IterativeMatchResult
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
            refine_iterations=refine_iterations,
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

    return IterativeMatchResult(
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
    refine_iterations: int,
) -> _ShiftEval:
    """
    Search over all possible alignment shifts between *t_a* (anchor) and
    *t_b* (other device), returning the shift with the lowest **mean**
    pairwise distance.

    A "shift" means: marker *i* in the anchor is paired with marker
    *i + shift* in device B.  Negative shifts mean B's marker sequence
    starts earlier.
    """
    n_a, n_b = len(t_a), len(t_b)
    shift_min = -n_b + 1  # last B marker paired with first A marker
    shift_max = n_a - 1   # first B marker paired with last A marker

    best: Optional[_ShiftEval] = None

    # ── 1. Exhaustive search over all shifts ──────────────────────────
    for shift in range(shift_min, shift_max + 1):
        ev = _evaluate_shift(
            t_a, t_b, shift, max_time_diff, gap_penalty
        )
        if best is None or ev.mean_dist < best.mean_dist:
            best = ev

    # ── 2. Random restarts (for tricky cases with big count diff) ─────
    rng = np.random.default_rng(rng_seed)
    for _ in range(n_random_restarts):
        # Pick a random offset in time space rather than index space
        t_range = max(float(t_a[-1] - t_a[0]), 1.0)
        random_offset = rng.uniform(-t_range * 0.3, t_range * 0.3)
        # Convert the time offset to a rough index shift
        median_step_b = float(np.median(np.diff(t_b))) if n_b > 1 else 1.0
        approx_shift = int(round(random_offset / max(median_step_b, 1e-6)))
        approx_shift = int(np.clip(approx_shift, shift_min, shift_max))

        ev = _evaluate_shift(
            t_a, t_b, approx_shift, max_time_diff, gap_penalty
        )
        if best is None or ev.mean_dist < best.mean_dist:
            best = ev

    # ── 3. Local refinement ──────────────────────────────────────────
    if best is not None and refine_iterations > 0 and n_a > 0 and n_b > 0:
        best = _refine_locally(
            best, t_a, t_b, max_time_diff, gap_penalty, refine_iterations
        )

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


def _refine_locally(
    current: _ShiftEval,
    t_a: np.ndarray,
    t_b: np.ndarray,
    max_time_diff: float,
    gap_penalty: float,
    n_iterations: int,
) -> _ShiftEval:
    """
    Try perturbing matched pairs by ±1 index to reduce mean distance.
    """
    best = current
    for _ in range(n_iterations):
        improved = False
        base_shift = best.shift

        # Try shifting the whole alignment by ±1
        for delta in (-1, 1):
            candidate = _evaluate_shift(
                t_a, t_b, base_shift + delta, max_time_diff, gap_penalty
            )
            if candidate.mean_dist < best.mean_dist:
                best = candidate
                improved = True

        # Try flipping individual matches in the last few / first few
        for idx in range(min(3, len(best.a_idxs))):
            # Try shifting this specific match
            old_a = best.a_idxs[idx]
            old_b = best.b_idxs[idx]
            for db in (-1, 1):
                new_j = old_b + db
                if 0 <= new_j < len(t_b):
                    dt = abs(t_a[old_a] - t_b[new_j])
                    if dt <= max_time_diff:
                        # Build a new ShiftEval with this tweak
                        ev = _build_perturbed(
                            t_a, t_b, best, idx, old_a, new_j,
                            max_time_diff, gap_penalty,
                        )
                        if ev is not None and ev.mean_dist < best.mean_dist:
                            best = ev
                            improved = True

        if not improved:
            break

    return best


def _build_perturbed(
    t_a: np.ndarray,
    t_b: np.ndarray,
    original: _ShiftEval,
    perturb_idx: int,
    a_idx: int,
    new_b_idx: int,
    max_time_diff: float,
    gap_penalty: float,
) -> Optional[_ShiftEval]:
    """Rebuild a ShiftEval with one matched pair reassigned."""
    distances: List[float] = []
    a_idxs: List[int] = []
    b_idxs: List[int] = []

    for i in range(len(original.a_idxs)):
        if i == perturb_idx:
            # Use perturbed index
            dt = abs(t_a[a_idx] - t_b[new_b_idx])
            if dt <= max_time_diff:
                distances.append(dt)
                a_idxs.append(a_idx)
                b_idxs.append(new_b_idx)
            else:
                distances.append(gap_penalty)
        else:
            distances.append(original.distances[i])
            a_idxs.append(original.a_idxs[i])
            b_idxs.append(original.b_idxs[i])

    if not distances:
        return None

    total = sum(distances)
    mean = total / len(distances)

    return _ShiftEval(
        shift=original.shift,
        distances=distances,
        mean_dist=mean,
        total_dist=total,
        n_matched=len(distances),
        a_idxs=a_idxs,
        b_idxs=b_idxs,
    )


# ══════════════════════════════════════════════════════════════════════
# Convenience: load from CSV files
# ══════════════════════════════════════════════════════════════════════


def match_iterative_from_files(
    file_paths: List[str],
    device_names: Optional[List[str]] = None,
    *,
    max_time_diff: float = 3.0,
    gap_penalty: float = 1e6,
    refine_iterations: int = 3,
    random_restarts: int = 5,
    rng_seed: int = 42,
    output_dir: str = "data/matching",
    output_prefix: str = "iterative_matched",
    save_json: bool = True,
    save_csv: bool = True,
) -> IterativeMatchResult:
    """
    Load marker CSV files and run iterative matching.

    Parameters
    ----------
    file_paths : list of str
        Paths to marker CSV files (must contain a timestamp column).
    device_names : list of str, optional
        Names for each device.  If *None*, derived from the filenames.

    For other parameters see :func:`match_iterative`.

    Returns
    -------
    IterativeMatchResult
    """
    from .matcher import load_marker_csv_enhanced

    devices = []
    names: List[str] = []

    for i, path in enumerate(file_paths):
        name = device_names[i] if (device_names and i < len(device_names)) else None
        dev = load_marker_csv_enhanced(path, name)
        devices.append(dev)
        names.append(dev.name)

    marker_dict = {d.name: d.timestamps_raw for d in devices}

    result = match_iterative(
        marker_dict,
        max_time_diff=max_time_diff,
        gap_penalty=gap_penalty,
        refine_iterations=refine_iterations,
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


def match_iterative_by_filename(
    filename: str,
    *,
    convert_dir: str = "Data/convert",
    marker_dir: str = "Data/marker",
    max_time_diff: float = 3.0,
    gap_penalty: float = 1e6,
    refine_iterations: int = 3,
    random_restarts: int = 5,
    rng_seed: int = 42,
    output_dir: str = "data/matching",
    output_prefix: Optional[str] = None,
    save_json: bool = True,
    save_csv: bool = True,
) -> IterativeMatchResult:
    """
    Convenience wrapper that auto-loads markers for a given filename
    (see :func:`~multichsync.marker.matcher.load_markers_from_filename`)
    and runs iterative matching.

    Parameters
    ----------
    filename : str
        Base filename to match (e.g. ``"20251101060"``).
    convert_dir, marker_dir : str
        Directories to search for data / markers.

    For other parameters see :func:`match_iterative`.

    Returns
    -------
    IterativeMatchResult
    """
    from .matcher import load_markers_from_filename

    marker_data = load_markers_from_filename(
        filename, convert_dir=convert_dir, marker_dir=marker_dir
    )

    if len(marker_data) < 2:
        raise ValueError(
            f"Need at least 2 devices, found {len(marker_data)} "
            f"for '{filename}'"
        )

    marker_dict: Dict[str, np.ndarray] = {}
    file_paths: List[str] = []
    device_names: List[str] = []
    for dev_type, (timestamps, fpath) in marker_data.items():
        marker_dict[dev_type] = timestamps
        file_paths.append(fpath)
        device_names.append(dev_type)

    result = match_iterative(
        marker_dict,
        max_time_diff=max_time_diff,
        gap_penalty=gap_penalty,
        refine_iterations=refine_iterations,
        random_restarts=random_restarts,
        rng_seed=rng_seed,
    )

    # ── Save outputs ──────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    prefix = output_prefix or filename

    if save_csv:
        _save_timeline_csv(result, output_dir, prefix)
    if save_json:
        _save_metadata_json(result, output_dir, prefix)

    return result


# ══════════════════════════════════════════════════════════════════════
# Output helpers
# ══════════════════════════════════════════════════════════════════════


def _save_timeline_csv(
    result: IterativeMatchResult,
    output_dir: str,
    prefix: str,
) -> str:
    """Build a timeline CSV with one row per consensus group."""
    data: Dict[str, Any] = {
        "group": np.arange(result.n_groups, dtype=int),
        "mean_distance": result.per_marker_distances,
    }
    for d in result.device_names:
        data[f"{d}_time"] = result.assignments[d]
        data[f"{d}_index"] = result.group_indices[d]

    df = pd.DataFrame(data)
    path = os.path.join(output_dir, f"{prefix}_timeline.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved iterative-match timeline → {path}")
    return path


def _save_metadata_json(
    result: IterativeMatchResult,
    output_dir: str,
    prefix: str,
) -> str:
    """Save matching metadata as JSON."""
    meta = {
        "algorithm": "iterative_shift",
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
    print(f"Saved iterative-match metadata → {path}")
    return path


# ══════════════════════════════════════════════════════════════════════
# Simple CLI helper
# ══════════════════════════════════════════════════════════════════════


def match_iterative_cli(args: Any) -> None:
    """Entry point called from ``multichsync marker iterative-match``."""
    if args.filename:
        result = match_iterative_by_filename(
            args.filename,
            convert_dir=args.convert_dir or "Data/convert",
            marker_dir=args.marker_dir or "Data/marker",
            max_time_diff=args.max_time_diff,
            gap_penalty=args.gap_penalty,
            refine_iterations=args.refine_iterations,
            random_restarts=args.random_restarts,
            rng_seed=args.rng_seed,
            output_dir=args.output_dir or "data/matching",
            output_prefix=args.output_prefix,
            save_json=not args.no_json,
            save_csv=not args.no_csv,
        )
    else:
        from .matcher import load_marker_csv_enhanced

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
            raise ValueError("Provide --filename, --input-dir, or --input-files")

        if args.device_names:
            device_names = args.device_names

        result = match_iterative_from_files(
            file_paths,
            device_names=device_names,
            max_time_diff=args.max_time_diff,
            gap_penalty=args.gap_penalty,
            refine_iterations=args.refine_iterations,
            random_restarts=args.random_restarts,
            rng_seed=args.rng_seed,
            output_dir=args.output_dir or "data/matching",
            output_prefix=args.output_prefix or "iterative_matched",
            save_json=not args.no_json,
            save_csv=not args.no_csv,
        )

    # ── Print summary ─────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"Iterative matching complete")
    print(f"{'='*50}")
    print(f"  Anchor device:     {result.anchor_name}")
    print(f"  Devices:           {', '.join(result.device_names)}")
    print(f"  Consensus groups:  {result.n_groups}")
    print(f"  Matched groups:    {result.n_matched_groups}")
    print(f"  Total distance:    {result.total_distance:.4f} s")
    print(f"  Mean distance:     {result.mean_distance:.4f} s")
    if result.gaps:
        for dev, grps in result.gaps.items():
            print(f"  Gaps in {dev}:      {len(grps)}")
    print(f"{'='*50}\n")
