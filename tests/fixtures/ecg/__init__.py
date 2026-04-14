"""
ECG test fixtures - minimal mock CSV files for testing.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path


def create_ecg_csv(
    path: Path, n_samples: int = 1000, fs: float = 250.0, has_time_column: bool = True
):
    """Create minimal ECG CSV file for testing."""
    duration = n_samples / fs
    time = np.linspace(0, duration, n_samples) if has_time_column else None

    data = {}
    if has_time_column:
        data["Time(sec)"] = time

    # Add 2 channels
    data["CH1"] = np.sin(2 * np.pi * 1.2 * np.linspace(0, duration, n_samples)) * 100
    data["CH2"] = np.sin(2 * np.pi * 1.5 * np.linspace(0, duration, n_samples)) * 100

    df = pd.DataFrame(data)
    df.to_csv(path, index=False)

    return path


def create_ecg_with_markers(path: Path, n_samples: int = 1000, fs: float = 250.0):
    """Create ECG CSV file with marker events."""
    duration = n_samples / fs
    time = np.linspace(0, duration, n_samples)

    # Generate ECG-like signal with R-peaks
    t = np.linspace(0, duration, n_samples)
    ecg = np.zeros(n_samples)

    # Add simulated R-peaks at ~60 BPM (every 1 second)
    for i in range(60):
        peak_time = i * 1.0
        if peak_time < duration:
            idx = int(peak_time * fs)
            if idx < n_samples:
                ecg[idx] = 1000  # R-peak amplitude

    data = {
        "Time(sec)": time,
        "CH1": ecg + np.random.randn(n_samples) * 10,
        "CH2": ecg + np.random.randn(n_samples) * 10,
    }

    df = pd.DataFrame(data)
    df.to_csv(path, index=False)

    return path


@pytest.fixture
def ecg_basic(temp_dir):
    """Create basic ECG CSV with time column."""
    csv_path = temp_dir / "test_ecg.csv"
    create_ecg_csv(csv_path, n_samples=1000, fs=250.0, has_time_column=True)
    return csv_path


@pytest.fixture
def ecg_no_time(temp_dir):
    """Create ECG CSV without time column."""
    csv_path = temp_dir / "test_ecg_no_time.csv"
    create_ecg_csv(csv_path, n_samples=500, fs=250.0, has_time_column=False)
    return csv_path


@pytest.fixture
def ecg_with_markers(temp_dir):
    """Create ECG CSV with marker events."""
    csv_path = temp_dir / "test_ecg_markers.csv"
    create_ecg_with_markers(csv_path, n_samples=1500, fs=250.0)
    return csv_path
