"""
Enhanced multi-device event matching with drift correction and confidence scoring.

This module provides functionality to match marker events across multiple devices,
with support for linear drift estimation, confidence scoring, and weighted consensus
timeline generation.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

# Default data directory
DEFAULT_CONVERT_DIR = "Data/convert"


# =========================
# Data Classes
# =========================


@dataclass
class DriftResult:
    """Results of linear drift estimation between two time series"""

    offset: float  # time offset (seconds)
    scale: float  # drift rate (ideal = 1.0)
    r_squared: float  # goodness of fit
    n_matches: int  # number of matches used for estimation
    method: str  # estimation method used

    def __repr__(self):
        return (
            f"DriftResult(offset={self.offset:.3f}s, scale={self.scale:.4f}, "
            f"r²={self.r_squared:.3f}, n={self.n_matches})"
        )

    def to_dict(self):
        return {
            "offset": self.offset,
            "scale": self.scale,
            "r_squared": self.r_squared,
            "n_matches": self.n_matches,
            "method": self.method,
        }


@dataclass
class MatchConfidence:
    """Confidence scores for matches between two devices"""

    device_pair: Tuple[str, str]
    match_indices: List[Tuple[int, int]]  # [(idx_a, idx_b), ...]
    confidence_scores: np.ndarray  # confidence for each match (0-1)
    mean_confidence: float
    n_matches: int

    def to_dict(self):
        return {
            "device_pair": self.device_pair,
            "n_matches": self.n_matches,
            "mean_confidence": float(self.mean_confidence),
            "confidence_stats": {
                "min": float(np.min(self.confidence_scores)),
                "max": float(np.max(self.confidence_scores)),
                "mean": float(np.mean(self.confidence_scores)),
                "std": float(np.std(self.confidence_scores)),
            },
        }


@dataclass
class DeviceInfo:
    """Information about a single device's marker data"""

    name: str
    file_path: str
    timestamps_raw: np.ndarray
    timestamps_corrected: np.ndarray
    drift_result: Optional[DriftResult] = None
    n_events: int = 0
    time_range: Tuple[float, float] = (0.0, 0.0)

    def __post_init__(self):
        self.n_events = len(self.timestamps_raw)
        if self.n_events > 0:
            self.time_range = (
                float(self.timestamps_raw.min()),
                float(self.timestamps_raw.max()),
            )
        if self.timestamps_corrected is None:
            self.timestamps_corrected = self.timestamps_raw.copy()


# =========================
# Utility Functions
# =========================


def load_marker_csv_enhanced(path: str, name: Optional[str] = None) -> DeviceInfo:
    """
    Load marker CSV file with enhanced metadata extraction.

    Args:
        path: Path to CSV file
        name: Device name (if None, extracted from filename)

    Returns:
        DeviceInfo object with timestamps and metadata
    """
    # Extract device name from filename if not provided
    if name is None:
        filename = os.path.basename(path)
        # Remove _marker.csv suffix and extract meaningful part
        name = filename.replace("_marker.csv", "").replace(".csv", "")

    # Load CSV
    df = pd.read_csv(path)

    # Detect timestamp column
    timestamp_cols = ["reference_time", "Time(sec)", "time", "Time"]
    timestamp_col = None
    for col in timestamp_cols:
        if col in df.columns:
            timestamp_col = col
            break

    if timestamp_col is None:
        raise ValueError(
            f"No timestamp column found in {path}. Available columns: {df.columns.tolist()}"
        )

    # Extract timestamps
    timestamps = df[timestamp_col].values.astype(float)

    # Sort by time
    sort_idx = np.argsort(timestamps)
    timestamps = timestamps[sort_idx]

    return DeviceInfo(
        name=name,
        file_path=path,
        timestamps_raw=timestamps,
        timestamps_corrected=timestamps.copy(),
    )


def compute_cost_matrix(t1: np.ndarray, t2: np.ndarray, power: int = 1) -> np.ndarray:
    """
    Compute pairwise cost matrix based on time difference.

    Args:
        t1: First time array (n,)
        t2: Second time array (m,)
        power: Power of difference (1 for absolute, 2 for squared)

    Returns:
        Cost matrix C (n x m)
    """
    diff = np.abs(t1[:, None] - t2[None, :])
    return diff**power


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Numerically stable softmax"""
    x_max = np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x - x_max)
    return exp_x / np.sum(exp_x, axis=axis, keepdims=True)


# =========================
# Drift Estimation
# =========================


def estimate_linear_drift_endpoints(
    t_ref: np.ndarray, t_dev: np.ndarray
) -> DriftResult:
    """
    Estimate linear drift using endpoints alignment.

    Assumes: t_ref = scale * t_dev + offset

    Args:
        t_ref: Reference timestamps
        t_dev: Device timestamps to align

    Returns:
        DriftResult with estimated parameters
    """
    if len(t_ref) < 2 or len(t_dev) < 2:
        return DriftResult(
            offset=0.0, scale=1.0, r_squared=0.0, n_matches=0, method="endpoints"
        )

    # Find overlapping time range
    t_ref_min, t_ref_max = t_ref.min(), t_ref.max()
    t_dev_min, t_dev_max = t_dev.min(), t_dev.max()

    # Simple linear fit using min and max
    scale = (
        (t_ref_max - t_ref_min) / (t_dev_max - t_dev_min)
        if (t_dev_max - t_dev_min) > 0
        else 1.0
    )
    offset = t_ref_min - scale * t_dev_min

    # Calculate R² using all points
    t_dev_aligned = t_dev * scale + offset
    residuals = t_ref - t_dev_aligned
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((t_ref - np.mean(t_ref)) ** 2)
    r_squared = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    return DriftResult(
        offset=float(offset),
        scale=float(scale),
        r_squared=float(r_squared),
        n_matches=2,
        method="endpoints",
    )


def estimate_linear_drift_theil_sen(
    t_ref: np.ndarray, t_dev: np.ndarray, min_pairs: int = 5, n_iterations: int = 3
) -> DriftResult:
    """
    Estimate linear drift using Theil-Sen robust regression with iterative refinement.

    Args:
        t_ref: Reference timestamps
        t_dev: Device timestamps to align
        min_pairs: Minimum number of pairs for reliable estimation
        n_iterations: Number of iterative refinement passes (improves accuracy)

    Returns:
        DriftResult with estimated parameters
    """
    # First, get initial matches using Hungarian algorithm
    C = compute_cost_matrix(t_ref, t_dev, power=1)
    row_ind, col_ind = linear_sum_assignment(C)

    if len(row_ind) < min_pairs:
        return estimate_linear_drift_endpoints(t_ref, t_dev)

    # Use matched pairs for regression
    t_ref_matched = t_ref[row_ind]
    t_dev_matched = t_dev[col_ind]

    # Initial Theil-Sen estimation
    scale, offset = _theil_sen_single(t_ref_matched, t_dev_matched)

    # Iterative refinement: remove outliers and re-estimate
    for _ in range(n_iterations - 1):
        # Apply current estimate
        t_dev_aligned = t_dev_matched * scale + offset
        residuals = np.abs(t_ref_matched - t_dev_aligned)

        # Remove outliers (> 2 * median residual)
        median_residual = np.median(residuals)
        if median_residual > 0:
            mask = residuals <= 2 * median_residual
            if np.sum(mask) >= min_pairs:
                t_ref_filtered = t_ref_matched[mask]
                t_dev_filtered = t_dev_matched[mask]
                scale, offset = _theil_sen_single(t_ref_filtered, t_dev_filtered)

    # Calculate R²
    t_dev_aligned = t_dev_matched * scale + offset
    ss_res = np.sum((t_ref_matched - t_dev_aligned) ** 2)
    ss_tot = np.sum((t_ref_matched - np.mean(t_ref_matched)) ** 2)
    r_squared = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    return DriftResult(
        offset=offset,
        scale=scale,
        r_squared=r_squared,
        n_matches=len(row_ind),
        method="theil_sen",
    )


def _theil_sen_single(t_ref: np.ndarray, t_dev: np.ndarray) -> Tuple[float, float]:
    """
    Single-pass Theil-Sen estimator for linear drift.

    Args:
        t_ref: Reference timestamps
        t_dev: Device timestamps to align

    Returns:
        (scale, offset) tuple
    """
    n = len(t_ref)
    if n < 2:
        return 1.0, 0.0

    # Theil-Sen estimator: median of slopes
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            dt = t_dev[j] - t_dev[i]
            if abs(dt) > 1e-10:  # Avoid division by zero
                slope = (t_ref[j] - t_ref[i]) / dt
                slopes.append(slope)

    if not slopes:
        scale = 1.0
    else:
        scale = float(np.median(slopes))

    # Calculate offset as median of differences
    offsets = t_ref - scale * t_dev
    offset = float(np.median(offsets))

    return scale, offset


def estimate_linear_drift(
    t_ref: np.ndarray, t_dev: np.ndarray, method: str = "theil_sen", **kwargs
) -> DriftResult:
    """
    Unified interface for drift estimation.

    Args:
        t_ref: Reference timestamps
        t_dev: Device timestamps to align
        method: "endpoints", "linear" (alias for endpoints), or "theil_sen"/"theilsen"

    Returns:
        DriftResult with estimated parameters
    """
    # Normalize method names
    if method == "linear":
        method = "endpoints"
    elif method == "theilsen":
        method = "theil_sen"

    if method == "endpoints":
        return estimate_linear_drift_endpoints(t_ref, t_dev)
    elif method == "theil_sen":
        return estimate_linear_drift_theil_sen(t_ref, t_dev, **kwargs)
    else:
        raise ValueError(f"Unknown drift estimation method: {method}")


def apply_drift_correction(t: np.ndarray, drift: DriftResult) -> np.ndarray:
    """
    Apply linear drift correction to timestamps.

    Args:
        t: Original timestamps
        drift: DriftResult with correction parameters

    Returns:
        Corrected timestamps
    """
    return (t - drift.offset) / drift.scale


# =========================
# Matching Algorithms with Confidence
# =========================


def match_hungarian_with_confidence(
    t1: np.ndarray,
    t2: np.ndarray,
    sigma_time_s: float = 0.75,
    max_time_diff_s: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Hungarian algorithm with confidence scores based on time difference.

    Args:
        t1: First time array
        t2: Second time array
        sigma_time_s: Gaussian sigma for confidence calculation
        max_time_diff_s: Maximum allowed time difference for matching

    Returns:
        matches: Array of (idx1, idx2) pairs
        confidences: Confidence scores for each match (0-1)
    """
    C = compute_cost_matrix(t1, t2, power=1)
    row_ind, col_ind = linear_sum_assignment(C)

    matches = []
    confidences = []

    for i, j in zip(row_ind, col_ind):
        dt = abs(t1[i] - t2[j])
        if dt <= max_time_diff_s:
            # Gaussian confidence: exp(-dt²/(2σ²))
            confidence = np.exp(-(dt**2) / (2 * sigma_time_s**2))
            matches.append((i, j))
            confidences.append(confidence)

    return np.array(matches), np.array(confidences)


def match_min_cost_flow_with_confidence(
    t1: np.ndarray,
    t2: np.ndarray,
    sigma_time_s: float = 0.75,
    max_time_diff_s: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Min-cost flow algorithm with confidence based on flow value.

    Args:
        t1: First time array
        t2: Second time array
        sigma_time_s: Gaussian sigma for confidence calculation
        max_time_diff_s: Maximum allowed time difference for matching

    Returns:
        matches: Array of (idx1, idx2) pairs
        confidences: Confidence scores for each match (0-1)
    """
    compute_cost_matrix(t1, t2, power=1)

    # Create flow network
    G = nx.DiGraph()
    source = "s"
    sink = "t"

    # Add edges from source to t1 nodes
    for i in range(len(t1)):
        G.add_edge(source, f"a{i}", capacity=1, weight=0)

    # Add edges from t2 nodes to sink
    for j in range(len(t2)):
        G.add_edge(f"b{j}", sink, capacity=1, weight=0)

    # Add edges between t1 and t2 nodes
    for i in range(len(t1)):
        for j in range(len(t2)):
            dt = abs(t1[i] - t2[j])
            if dt <= max_time_diff_s:
                # Weight as integer cost (higher cost for larger dt)
                weight = int(dt * 1000)
                G.add_edge(f"a{i}", f"b{j}", capacity=1, weight=weight)

    # Solve min-cost flow
    flow = nx.max_flow_min_cost(G, source, sink)

    # Extract matches and calculate confidence
    matches = []
    confidences = []

    for i in range(len(t1)):
        for j in range(len(t2)):
            if flow.get(f"a{i}", {}).get(f"b{j}", 0) > 0:
                dt = abs(t1[i] - t2[j])
                confidence = np.exp(-(dt**2) / (2 * sigma_time_s**2))
                matches.append((i, j))
                confidences.append(confidence)

    return np.array(matches), np.array(confidences)


def match_sinkhorn_with_confidence(
    t1: np.ndarray,
    t2: np.ndarray,
    reg: float = 0.1,
    sigma_time_s: float = 0.75,
    max_time_diff_s: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Sinkhorn algorithm (optimal transport) with probability as confidence.

    Args:
        t1: First time array
        t2: Second time array
        reg: Regularization parameter for Sinkhorn
        sigma_time_s: Gaussian sigma for thresholding (currently unused; kept for API consistency)
        max_time_diff_s: Maximum allowed time difference for matching (seconds)

    Returns:
        matches: Array of (idx1, idx2) pairs
        confidences: Probability scores for each match
    """
    C = compute_cost_matrix(t1, t2, power=1)
    n, m = C.shape

    # Sinkhorn iterations
    K = np.exp(-C / reg)
    u = np.ones(n)
    v = np.ones(m)

    for _ in range(100):
        u = 1.0 / (K @ v + 1e-16)
        v = 1.0 / (K.T @ u + 1e-16)

    P = np.diag(u) @ K @ np.diag(v)

    # Threshold and extract matches
    matches = []
    confidences = []

    for i in range(n):
        for j in range(m):
            prob = P[i, j]
            # Filter by probability threshold AND time difference
            if prob > 0.1 and C[i, j] <= max_time_diff_s:
                matches.append((i, j))
                confidences.append(float(prob))

    return np.array(matches), np.array(confidences)


def match_events_with_confidence(
    t1: np.ndarray, t2: np.ndarray, method: str = "hungarian", **kwargs
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Unified interface for matching with confidence scores.

    Args:
        t1: First time array
        t2: Second time array
        method: "hungarian", "min_cost_flow", or "sinkhorn"

    Returns:
        matches: Array of (idx1, idx2) pairs
        confidences: Confidence scores for each match (0-1)
    """
    if method == "hungarian":
        return match_hungarian_with_confidence(t1, t2, **kwargs)
    elif method == "min_cost_flow":
        return match_min_cost_flow_with_confidence(t1, t2, **kwargs)
    elif method == "sinkhorn":
        return match_sinkhorn_with_confidence(t1, t2, **kwargs)
    else:
        raise ValueError(f"Unknown matching method: {method}")


# =========================
# Timeline Manager
# =========================


class EnhancedTimeline:
    """
    Manages consensus timeline with weighted averaging and drift correction.
    """

    def __init__(self, reference_device: DeviceInfo):
        """
        Initialize timeline with reference device.

        Args:
            reference_device: First device (becomes the reference)
        """
        self.devices = [reference_device]
        self.device_names = [reference_device.name]

        # Initialize timeline with reference device events
        self.consensus_times = reference_device.timestamps_corrected.copy()
        self.consensus_confidences = np.ones_like(self.consensus_times)

        # Store device contributions to each consensus event
        self.device_contributions = {
            reference_device.name: {
                "timestamps": reference_device.timestamps_corrected.copy(),
                "indices": np.arange(len(reference_device.timestamps_corrected)),
                "weights": np.ones_like(reference_device.timestamps_corrected),
            }
        }

        # Store all drift corrections
        self.drift_corrections = {}

    def add_device(
        self,
        device: DeviceInfo,
        method: str = "hungarian",
        estimate_drift: bool = True,
        drift_method: str = "theil_sen",
        sigma_time_s: float = 0.75,
        max_time_diff_s: float = 3.0,
    ) -> Dict[str, Any]:
        """
        Add a new device to the timeline with optional drift correction.

        Args:
            device: Device to add
            method: Matching method
            estimate_drift: Whether to estimate and correct drift
            drift_method: Drift estimation method
            sigma_time_s: Gaussian sigma for confidence
            max_time_diff_s: Maximum time difference for matching

        Returns:
            Dictionary with matching statistics
        """
        # Estimate drift if requested
        if estimate_drift and len(self.consensus_times) > 0:
            drift_result = estimate_linear_drift(
                self.consensus_times, device.timestamps_raw, method=drift_method
            )
            device.drift_result = drift_result
            device.timestamps_corrected = apply_drift_correction(
                device.timestamps_raw, drift_result
            )
            self.drift_corrections[device.name] = drift_result
        else:
            device.timestamps_corrected = device.timestamps_raw.copy()

        # Match with current consensus timeline
        matches, confidences = match_events_with_confidence(
            self.consensus_times,
            device.timestamps_corrected,
            method=method,
            sigma_time_s=sigma_time_s,
            max_time_diff_s=max_time_diff_s,
        )

        # Update device contributions for matched events
        for (consensus_idx, device_idx), confidence in zip(matches, confidences):
            dev_name = device.name
            if dev_name not in self.device_contributions:
                self.device_contributions[dev_name] = {
                    "timestamps": np.full_like(self.consensus_times, np.nan),
                    "indices": np.full_like(self.consensus_times, -1, dtype=int),
                    "weights": np.zeros_like(self.consensus_times),
                }

            self.device_contributions[dev_name]["timestamps"][consensus_idx] = (
                device.timestamps_corrected[device_idx]
            )
            self.device_contributions[dev_name]["indices"][consensus_idx] = device_idx
            self.device_contributions[dev_name]["weights"][consensus_idx] = confidence

            # Update consensus confidence (weighted sum)
            self.consensus_confidences[consensus_idx] += confidence

        # Handle unmatched device events
        device_matched_indices = set(matches[:, 1] if len(matches) > 0 else [])
        for i, t in enumerate(device.timestamps_corrected):
            if i not in device_matched_indices:
                # Add as new consensus event
                self._add_new_event(t, device.name, i, 1.0)

        # Recompute consensus times with weighted average
        self._recompute_consensus()

        # Add device to list
        self.devices.append(device)
        self.device_names.append(device.name)

        # Return statistics
        return {
            "device": device.name,
            "n_matches": len(matches),
            "mean_confidence": float(np.mean(confidences))
            if len(confidences) > 0
            else 0.0,
            "drift_correction": device.drift_result.to_dict()
            if device.drift_result
            else None,
        }

    def _add_new_event(
        self, timestamp: float, device_name: str, device_idx: int, weight: float
    ):
        """Add a new event to the consensus timeline."""
        # Add to consensus arrays
        self.consensus_times = np.append(self.consensus_times, timestamp)
        self.consensus_confidences = np.append(self.consensus_confidences, weight)

        # Update device contributions for all devices
        for dev in self.device_contributions:
            self.device_contributions[dev]["timestamps"] = np.append(
                self.device_contributions[dev]["timestamps"], np.nan
            )
            self.device_contributions[dev]["indices"] = np.append(
                self.device_contributions[dev]["indices"], -1
            )
            self.device_contributions[dev]["weights"] = np.append(
                self.device_contributions[dev]["weights"], 0.0
            )

        # Set contribution for this device
        if device_name not in self.device_contributions:
            self.device_contributions[device_name] = {
                "timestamps": np.full_like(self.consensus_times, np.nan),
                "indices": np.full_like(self.consensus_times, -1, dtype=int),
                "weights": np.zeros_like(self.consensus_times),
            }

        idx = len(self.consensus_times) - 1
        self.device_contributions[device_name]["timestamps"][idx] = timestamp
        self.device_contributions[device_name]["indices"][idx] = device_idx
        self.device_contributions[device_name]["weights"][idx] = weight

    def _recompute_consensus(self):
        """Recompute consensus times using weighted average."""
        for i in range(len(self.consensus_times)):
            timestamps = []
            weights = []

            for dev_name in self.device_contributions:
                t = self.device_contributions[dev_name]["timestamps"][i]
                w = self.device_contributions[dev_name]["weights"][i]

                if not np.isnan(t) and w > 0:
                    timestamps.append(t)
                    weights.append(w)

            if timestamps:
                # Weighted average
                weights = np.array(weights)
                weights = weights / weights.sum()  # Normalize
                self.consensus_times[i] = np.sum(np.array(timestamps) * weights)

    def get_merged_dataframe(self) -> pd.DataFrame:
        """Create merged DataFrame with all device timestamps and confidence."""
        data = {
            "consensus_time": self.consensus_times,
            "consensus_confidence": self.consensus_confidences,
        }

        # Add device columns
        for dev_name in self.device_names:
            if dev_name in self.device_contributions:
                data[f"{dev_name}_time"] = self.device_contributions[dev_name][
                    "timestamps"
                ]
                data[f"{dev_name}_weight"] = self.device_contributions[dev_name][
                    "weights"
                ]
            else:
                data[f"{dev_name}_time"] = np.full_like(self.consensus_times, np.nan)
                data[f"{dev_name}_weight"] = np.zeros_like(self.consensus_times)

        df = pd.DataFrame(data)

        # Sort by consensus time
        df = df.sort_values("consensus_time").reset_index(drop=True)

        return df

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the timeline and matching process."""
        return {
            "n_devices": len(self.devices),
            "device_names": self.device_names,
            "n_consensus_events": len(self.consensus_times),
            "consensus_time_range": (
                float(self.consensus_times.min()),
                float(self.consensus_times.max()),
            ),
            "drift_corrections": {
                name: drift.to_dict() for name, drift in self.drift_corrections.items()
            },
        }


# =========================
# Main Function
# =========================


def _get_device_raw_duration(device: DeviceInfo) -> Optional[float]:
    """
    Get raw data duration for a device based on its marker file path.

    Args:
        device: DeviceInfo object

    Returns:
        Raw data duration in seconds, or None if cannot determine
    """
    # Determine device type from file path
    file_path = device.file_path.lower()

    if "/eeg/" in file_path or "_eeg_marker" in file_path:
        device_type = "eeg"
    elif "/fnirs/" in file_path or "_fnirs_marker" in file_path:
        device_type = "fnirs"
    elif "/ecg/" in file_path or "_ecg_marker" in file_path:
        device_type = "ecg"
    else:
        # Try to infer from device name
        name_lower = device.name.lower()
        if "eeg" in name_lower:
            device_type = "eeg"
        elif "fnirs" in name_lower:
            device_type = "fnirs"
        elif "ecg" in name_lower:
            device_type = "ecg"
        else:
            print(f"Warning: Cannot determine device type for {device.name}")
            return None

    return get_raw_data_duration(device.name, device_type)


def match_multiple_files_enhanced(
    file_paths: List[str],
    device_names: Optional[List[str]] = None,
    method: str = "hungarian",
    # Matching parameters
    max_time_diff_s: float = 3.0,
    sigma_time_s: float = 0.75,
    # Drift correction parameters
    estimate_drift: bool = True,
    drift_method: str = "theil_sen",
    # Output parameters
    output_dir: str = "data/matching",
    output_prefix: str = "matched",
    save_json: bool = True,
    generate_plots: bool = True,
) -> Dict[str, Any]:
    """
    Enhanced multi-file event matching with drift correction and confidence scoring.

    Args:
        file_paths: List of paths to marker CSV files
        device_names: Optional list of device names (default: extracted from filenames)
        method: Matching method ("hungarian", "min_cost_flow", "sinkhorn")
        max_time_diff_s: Maximum time difference for matching (seconds)
        sigma_time_s: Gaussian sigma for confidence calculation
        estimate_drift: Whether to estimate and correct linear drift
        drift_method: Drift estimation method ("endpoints" or "theil_sen")
        output_dir: Directory to save outputs
        output_prefix: Prefix for output files
        save_json: Whether to save metadata as JSON
        generate_plots: Whether to generate visualization plots

    Returns:
        Dictionary with results and statistics
    """
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Load all devices
    devices = []
    for i, path in enumerate(file_paths):
        name = device_names[i] if device_names and i < len(device_names) else None
        try:
            device = load_marker_csv_enhanced(path, name)
            devices.append(device)
            print(f"Loaded device {device.name}: {device.n_events} events from {path}")
        except Exception as e:
            print(f"Error loading {path}: {e}")
            continue

    if len(devices) < 2:
        raise ValueError(
            f"Need at least 2 devices, but only {len(devices)} loaded successfully"
        )

    # Initialize timeline with first device
    timeline = EnhancedTimeline(devices[0])
    matching_stats = [
        {
            "device": devices[0].name,
            "n_matches": devices[0].n_events,
            "mean_confidence": 1.0,
        }
    ]

    # Add remaining devices
    for device in devices[1:]:
        print(f"Matching device {device.name}...")
        stats = timeline.add_device(
            device,
            method=method,
            estimate_drift=estimate_drift,
            drift_method=drift_method,
            sigma_time_s=sigma_time_s,
            max_time_diff_s=max_time_diff_s,
        )
        matching_stats.append(stats)
        print(
            f"  → {stats['n_matches']} matches, mean confidence: {stats['mean_confidence']:.3f}"
        )

    # Get merged DataFrame
    merged_df = timeline.get_merged_dataframe()

    # Save CSV
    csv_path = os.path.join(output_dir, f"{output_prefix}_timeline.csv")
    merged_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved timeline to {csv_path}")

    # Get raw duration for each device
    device_raw_durations = {}
    for dev in devices:
        device_raw_durations[dev.name] = _get_device_raw_duration(dev)

        # Prepare metadata
    metadata = {
        "processing_parameters": {
            "method": method,
            "max_time_diff_s": max_time_diff_s,
            "sigma_time_s": sigma_time_s,
            "estimate_drift": estimate_drift,
            "drift_method": drift_method,
        },
        "device_info": [
            {
                "name": dev.name,
                "file_path": dev.file_path,
                "converted_data_file_path": "",
                "n_events": dev.n_events,
                "time_range": [0.0, device_raw_durations[dev.name]]
                if device_raw_durations.get(dev.name)
                else dev.time_range,
                "raw_duration": device_raw_durations.get(dev.name),
                "drift_correction": dev.drift_result.to_dict()
                if dev.drift_result
                else None,
            }
            for dev in devices
        ],
        "matching_statistics": matching_stats,
        "timeline_metadata": timeline.get_metadata(),
        "output_files": {"timeline_csv": csv_path},
    }

    # Save JSON if requested
    if save_json:
        json_path = os.path.join(output_dir, f"{output_prefix}_metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)
        print(f"Saved metadata to {json_path}")
        metadata["output_files"]["metadata_json"] = json_path

    # Generate plots if requested
    if generate_plots:
        try:
            _generate_plots(
                merged_df,
                devices,
                device_raw_durations,
                timeline,
                output_dir,
                output_prefix,
            )
            print("Generated visualization plots")
        except Exception as e:
            print(f"Warning: Could not generate plots: {e}")

    return {"merged_dataframe": merged_df, "metadata": metadata, "timeline": timeline}


def _generate_plots(
    merged_df: pd.DataFrame,
    devices: List[DeviceInfo],
    device_raw_durations: Dict[str, float],
    timeline: EnhancedTimeline,
    output_dir: str,
    prefix: str,
):
    """Generate visualization plots."""
    import matplotlib.pyplot as plt

    # Plot 1: Timeline alignment
    fig, axes = plt.subplots(2, 1, figsize=(12, 10))

    # Define distinct colors for each device
    device_colors = [
        "#E63946",
        "#2A9D8F",
        "#457B9D",
        "#F4A261",
        "#9B59B6",
    ]  # Red, Teal, Blue, Orange, Purple

    # Subplot 1: Raw timeline
    ax1 = axes[0]
    for i, dev in enumerate(devices):
        y_pos = i * 0.1
        color = device_colors[i % len(device_colors)]
        ax1.scatter(
            dev.timestamps_raw,
            np.full_like(dev.timestamps_raw, y_pos),
            label=dev.name,
            c=color,
            alpha=0.7,
            s=30,
            edgecolors="white",
            linewidths=0.5,
        )
        # Add horizontal line showing raw_duration
        raw_duration = device_raw_durations.get(dev.name)
        if raw_duration is not None:
            ax1.hlines(
                y_pos,
                xmin=0,
                xmax=raw_duration,
                colors=color,
                linestyles="--",
                linewidths=1.5,
                alpha=0.8,
            )
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Device (raw)")
    ax1.set_title("Raw Device Timelines (dashed lines = raw_duration)")
    ax1.legend(loc="upper right", framealpha=0.9)
    ax1.grid(True, alpha=0.3)

    # Subplot 2: Aligned timeline
    ax2 = axes[1]
    consensus_times = merged_df["consensus_time"].values
    confidences = merged_df["consensus_confidence"].values

    for i, dev in enumerate(devices):
        dev_name = dev.name
        color = device_colors[i % len(device_colors)]
        if f"{dev_name}_time" in merged_df.columns:
            times = merged_df[f"{dev_name}_time"].values
            mask = ~np.isnan(times)
            if np.any(mask):
                y_pos = i * 0.1
                # Use device color, alpha by confidence
                alphas = 0.4 + 0.5 * (confidences[mask] / confidences.max())
                ax2.scatter(
                    consensus_times[mask],
                    np.full(np.sum(mask), y_pos),
                    c=color,
                    alpha=alphas,
                    label=dev_name,
                    s=30,
                    edgecolors="white",
                    linewidths=0.5,
                )
        # Add horizontal line showing raw_duration (in consensus time space)
        raw_duration = device_raw_durations.get(dev_name)
        if raw_duration is not None:
            ax2.hlines(
                y_pos,
                xmin=0,
                xmax=raw_duration,
                colors=color,
                linestyles="--",
                linewidths=1.5,
                alpha=0.8,
            )

    ax2.set_xlabel("Consensus Time (s)")
    ax2.set_ylabel("Device (aligned)")
    ax2.set_title(
        "Aligned Device Timelines (dashed lines = raw_duration, alpha = confidence)"
    )
    ax2.legend(loc="upper right", framealpha=0.9)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plot1_path = os.path.join(output_dir, f"{prefix}_timeline_alignment.png")
    plt.savefig(plot1_path, dpi=150, bbox_inches="tight")
    plt.close()

    # Plot 2: Confidence distribution
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Subplot 1: Confidence histogram
    ax1 = axes[0]
    valid_confidences = confidences[confidences > 0]
    if len(valid_confidences) > 0:
        ax1.hist(valid_confidences, bins=20, alpha=0.7, edgecolor="black")
        ax1.set_xlabel("Confidence")
        ax1.set_ylabel("Frequency")
        ax1.set_title("Distribution of Consensus Confidence")
        ax1.grid(True, alpha=0.3)

    # Subplot 2: Events per device
    ax2 = axes[1]
    device_counts = []
    device_names = []
    for dev in devices:
        dev_name = dev.name
        if f"{dev_name}_time" in merged_df.columns:
            times = merged_df[f"{dev_name}_time"].values
            count = np.sum(~np.isnan(times))
            device_counts.append(count)
            device_names.append(dev_name)

    if device_counts:
        bars = ax2.bar(range(len(device_counts)), device_counts)
        ax2.set_xlabel("Device")
        ax2.set_ylabel("Number of Matched Events")
        ax2.set_title("Events per Device in Consensus Timeline")
        ax2.set_xticks(range(len(device_counts)))
        ax2.set_xticklabels(device_names, rotation=45, ha="right")

        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{int(height)}",
                ha="center",
                va="bottom",
            )

    plt.tight_layout()
    plot2_path = os.path.join(output_dir, f"{prefix}_confidence_distribution.png")
    plt.savefig(plot2_path, dpi=150, bbox_inches="tight")
    plt.close()


# =========================
# Raw Data Duration Helper
# =========================


def get_raw_data_duration(device_name: str, device_type: str) -> Optional[float]:
    """
    Get the total duration (in seconds) of raw data file.

    Args:
        device_name: Device name (e.g., "sub-071_ses-01_task-rest_input")
        device_type: Device type ("eeg", "fnirs", "ecg")

    Returns:
        Total duration in seconds, or None if cannot be read
    """
    import h5py

    base_convert_dir = Path(DEFAULT_CONVERT_DIR)

    try:
        if device_type.lower() == "eeg":
            # EEG: Read from BrainVision .vhdr file
            # File path: Data/convert/EEG/{device_name}.vhdr
            eeg_dir = base_convert_dir / "EEG"
            vhdr_path = eeg_dir / f"{device_name}.vhdr"

            if not vhdr_path.exists():
                # Try with case-insensitive search
                for f in eeg_dir.glob("*.vhdr"):
                    if f.stem.lower() == device_name.lower():
                        vhdr_path = f
                        break
                else:
                    print(f"Warning: EEG file not found for {device_name}")
                    return None

            # Use mne to read BrainVision format
            try:
                import mne

                raw = mne.io.read_raw_brainvision(
                    str(vhdr_path), preload=False, verbose=False
                )
                n_times = raw.n_times
                sfreq = raw.info["sfreq"]
                return float(n_times / sfreq)
            except Exception as e:
                print(f"Warning: Failed to read EEG duration from {vhdr_path}: {e}")
                return None

        elif device_type.lower() == "fnirs":
            # fNIRS: Read from SNIRF file
            # File path: Data/convert/fnirs/{device_name}.snirf
            fnirs_dir = base_convert_dir / "fnirs"
            snirf_path = fnirs_dir / f"{device_name}.snirf"

            if not snirf_path.exists():
                # Try with case-insensitive search
                for f in fnirs_dir.glob("*.snirf"):
                    if f.stem.lower() == device_name.lower():
                        snirf_path = f
                        break
                else:
                    print(f"Warning: fNIRS file not found for {device_name}")
                    return None

            try:
                with h5py.File(snirf_path, "r") as f:
                    # Navigate to time data
                    # Typical path: nirs/data1/time
                    if "nirs/data1/time" in f:
                        time_data = f["nirs/data1/time"][:]
                        return float(np.max(time_data))
                    elif "nirs/data/time" in f:
                        time_data = f["nirs/data/time"][:]
                        return float(np.max(time_data))
                    else:
                        print(f"Warning: No time data found in {snirf_path}")
                        return None
            except Exception as e:
                print(f"Warning: Failed to read fNIRS duration from {snirf_path}: {e}")
                return None

        elif device_type.lower() == "ecg":
            # ECG: Get duration from original _ecg.csv file
            # Duration = timepoints / SR, where SR = 250 Hz (default for multichsync ecg)

            # Handle device_name mapping: _ecg -> _ecg file, _input -> _ecg file
            # e.g., sub-071_ses-01_task-rest_input -> sub-071_ses-01_task-rest_ecg.csv
            ecg_search_name = device_name
            if device_name.endswith("_input"):
                ecg_search_name = device_name[:-6] + "_ecg"
            elif not device_name.endswith("_ecg"):
                # Try adding _ecg suffix
                ecg_search_name = device_name + "_ecg"

            # First: Try _ecg file in convert/ECG (original data without time column)
            ecg_dir = base_convert_dir / "ECG"
            csv_path = ecg_dir / f"{ecg_search_name}.csv"

            if not csv_path.exists():
                # Try case-insensitive search
                for f in ecg_dir.glob("*_ecg.csv"):
                    if f.stem.lower() == ecg_search_name.lower():
                        csv_path = f
                        break
                else:
                    print(
                        f"Warning: ECG file not found for {device_name} (searched as {ecg_search_name})"
                    )
                    return None

            try:
                df = pd.read_csv(csv_path)
                # ECG _ecg.csv files don't have time column, calculate from row count
                # SR = 250 Hz (default for multichsync ecg batch)
                n_rows = len(df)
                sampling_rate = 250  # Default SR for ECG conversion
                duration = n_rows / sampling_rate
                return duration
            except Exception as e:
                print(f"Warning: Failed to read ECG duration from {csv_path}: {e}")
                return None
        else:
            print(f"Warning: Unsupported device type: {device_type}")
            return None

    except Exception as e:
        print(
            f"Warning: Error getting raw data duration for {device_name} ({device_type}): {e}"
        )
        return None
