"""
Pytest configuration and shared fixtures for MultiChSync tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create a temporary directory that is cleaned up after test."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_eeg_files(temp_dir):
    """Create minimal mock BrainVision EEG files."""
    vhdr_content = """Brain Vision Data Exchange Header File Version 1.0

[Common Infos]
Codepage=UTF-8
DataFile=test_device.eeg
MarkerFile=test_device.vmrk

[Binary Infos]
BinaryFormat=INT_16

[Channel Infos]
Ch1=Fp1,,0.1

[Coordinates]

[Sampling Interval]
5000
"""
    vmrk_content = """Brain Vision Data Exchange Marker File Version 1.0

[Common Infos]
DataFile=test_device.eeg

[Marker Infos]
Mk1=New Segment,,0,1,0,0
Mk2=Stimulus,S  1,1000,1,0
"""

    vhdr_path = temp_dir / "test_device.vhdr"
    vmrk_path = temp_dir / "test_device.vmrk"
    eeg_path = temp_dir / "test_device.eeg"

    vhdr_path.write_text(vhdr_content)
    vmrk_path.write_text(vmrk_content)
    eeg_path.write_bytes(b"\x00" * 100)

    return {
        "vhdr": vhdr_path,
        "vmrk": vmrk_path,
        "eeg": eeg_path,
        "base": "test_device",
    }


@pytest.fixture
def mock_snirf_file(temp_dir):
    """Create minimal mock SNIRF file."""
    import h5py
    import numpy as np

    snirf_path = temp_dir / "test.snirf"

    with h5py.File(snirf_path, "w") as f:
        nirs = f.create_group("nirs")
        data = nirs.create_group("data1")

        # Time array: 0 to 100 seconds at 10Hz
        time_data = np.arange(0, 100.1, 0.1)
        data.create_dataset("time", data=time_data)

        # Create measurement data (2 channels, 1001 timepoints)
        measuredata = data.create_group("measurementData1")
        measuredata.create_dataset("dataType", data="NIRS")

        # Create 2 channels with HbO and HbR
        probe = nirs.create_group("probe")
        probe.create_dataset("wavelengths", data=[760, 850])
        probe.create_dataset("sourceLabels", data=["S1", "S2"])
        probe.create_dataset("detectorLabels", data=["D1", "D2"])

    return snirf_path


@pytest.fixture
def mock_ecg_csv(temp_dir):
    """Create minimal mock ECG CSV file."""
    import pandas as pd
    import numpy as np

    # CSV with time column
    csv_path = temp_dir / "test_ecg.csv"
    df = pd.DataFrame(
        {
            "Time(sec)": np.arange(0, 10, 0.01),  # 1000 rows at 100Hz = 10 sec
            "CH1": np.random.randn(1000),
            "CH2": np.random.randn(1000),
        }
    )
    df.to_csv(csv_path, index=False)

    return csv_path


@pytest.fixture
def mock_ecg_csv_no_time(temp_dir):
    """Create minimal mock ECG CSV file without time column."""
    import pandas as pd
    import numpy as np

    csv_path = temp_dir / "test_ecg_no_time.csv"
    df = pd.DataFrame(
        {
            "CH1": np.random.randn(600),  # 600 rows
            "CH2": np.random.randn(600),
        }
    )
    df.to_csv(csv_path, index=False)

    return csv_path


# Pytest markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "slow: slow tests that take >10 seconds")
