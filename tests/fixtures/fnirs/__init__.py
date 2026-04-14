"""
fNIRS test fixtures - minimal mock SNIRF files for testing.
"""

import pytest
import h5py
import numpy as np
from pathlib import Path


def create_minimal_snirf(
    path: Path,
    n_sources: int = 1,
    n_detectors: int = 1,
    duration_s: float = 10.0,
    sfreq: float = 10.0,
):
    """Create minimal SNIRF file for testing."""
    n_timepoints = int(duration_s * sfreq)

    with h5py.File(path, "w") as f:
        nirs = f.create_group("nirs")

        # Data group
        data = nirs.create_group("data1")

        # Time data
        time_data = np.linspace(0, duration_s, n_timepoints)
        data.create_dataset("time", data=time_data)

        # Create channel list (all HbO-HbR pairs)
        n_channels = n_sources * n_detectors
        if n_channels == 0:
            n_channels = 1

        # Measurement data
        measuredata = data.create_group("measurementData1")
        measuredata.create_dataset("dataType", data="NIRS")

        # Probe - wavelengths and source/detector labels
        probe = nirs.create_group("probe")
        wavelengths = np.array([760.0, 850.0] * n_channels)
        probe.create_dataset("wavelengths", data=wavelengths)

        source_labels = [f"S{i + 1}" for i in range(n_sources)]
        detector_labels = [f"D{i + 1}" for i in range(n_detectors)]

        if n_sources == 1 and n_detectors == 1:
            source_labels = ["S1"]
            detector_labels = ["D1"]

        probe.create_dataset(
            "sourceLabels", data=np.array(source_labels, dtype=h5py.string_dtype())
        )
        probe.create_dataset(
            "detectorLabels", data=np.array(detector_labels, dtype=h5py.string_dtype())
        )

        # Create minimal data matrix (n_channels * 2 for HbO/HbR * n_timepoints)
        nirs_data = np.random.randn(n_channels * 2, n_timepoints) * 100 + 1000
        data.create_dataset("dataBlock1", data=nirs_data)

    return path


@pytest.fixture
def fnirs_minimal(temp_dir):
    """Create minimal 1-source, 1-detector SNIRF file (10 seconds)."""
    snirf_path = temp_dir / "minimal.snirf"
    create_minimal_snirf(snirf_path, n_sources=1, n_detectors=1, duration_s=10.0)
    return snirf_path


@pytest.fixture
def fnirs_2ch_30s(temp_dir):
    """Create 2-channel (1 SD pair) SNIRF file (30 seconds)."""
    snirf_path = temp_dir / "2ch_30s.snirf"
    create_minimal_snirf(snirf_path, n_sources=2, n_detectors=2, duration_s=30.0)
    return snirf_path
