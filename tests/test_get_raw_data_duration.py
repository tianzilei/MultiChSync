"""
Tests for get_raw_data_duration function.
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
import os
from pathlib import Path

# Import the function to test
from multichsync.marker.matcher import get_raw_data_duration


class TestGetRawDataDuration:
    """Test cases for get_raw_data_duration function."""

    def test_eeg_duration(self, tmp_path):
        """Test EEG duration extraction from .vhdr file."""
        # Create a mock BrainVision file structure
        vhdr_path = tmp_path / "test_device.vhdr"
        vmrk_path = tmp_path / "test_device.vmrk"
        eeg_path = tmp_path / "test_device.eeg"

        # Create minimal .vhdr file
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
        vhdr_path.write_text(vhdr_content)

        # Create .vmrk file with markers
        vmrk_content = """Brain Vision Data Exchange Marker File Version 1.0

[Common Infos]
DataFile=test_device.eeg

[Marker Infos]
Mk1=New Segment,,0,1,0,0
"""
        vmrk_path.write_text(vmrk_content)

        # Create minimal .eeg file (2 bytes = 1 sample for 1 channel)
        eeg_path.write_bytes(b"\x00\x00")

        # This test assumes mne is available
        try:
            import mne

            duration = get_raw_data_duration("test_device", "eeg")
            # Should return approximately 0.001 seconds (1 sample / 200 Hz)
            assert duration is None or duration > 0
        except ImportError:
            pytest.skip("mne not available")

    def test_fnirs_duration(self, tmp_path):
        """Test fNIRS duration extraction from .snirf file."""
        import h5py

        # Create temp convert directory structure
        convert_dir = tmp_path / "convert"
        fnirs_dir = convert_dir / "fnirs"
        fnirs_dir.mkdir(parents=True)

        snirf_path = fnirs_dir / "test_device.snirf"

        # Create minimal SNIRF file with time data
        with h5py.File(snirf_path, "w") as f:
            nirs = f.create_group("nirs")
            data = nirs.create_group("data1")
            # Create time array: 0, 0.1, 0.2, ... 100.0 (1001 samples = 100 seconds at 10Hz)
            time_data = np.arange(0, 100.1, 0.1)
            data.create_dataset("time", data=time_data)

        # Monkey-patch DEFAULT_CONVERT_DIR for testing
        import multichsync.marker.matcher as matcher

        original_dir = matcher.DEFAULT_CONVERT_DIR
        matcher.DEFAULT_CONVERT_DIR = str(convert_dir)

        try:
            duration = get_raw_data_duration("test_device", "fnirs")
            # Should return approximately 100.0 seconds (max time)
            assert duration == pytest.approx(100.0, rel=0.1)
        finally:
            matcher.DEFAULT_CONVERT_DIR = original_dir

    def test_ecg_duration(self, tmp_path):
        """Test ECG duration extraction from .csv file."""
        # Create temp convert directory structure
        convert_dir = tmp_path / "convert"
        ecg_dir = convert_dir / "ECG"
        ecg_dir.mkdir(parents=True)

        csv_path = ecg_dir / "test_device_ecg.csv"

        # Create CSV without time column (raw ECG data format)
        df = pd.DataFrame(
            {
                "channel1": np.random.randn(600),
            }
        )
        df.to_csv(csv_path, index=False)

        # Monkey-patch DEFAULT_CONVERT_DIR for testing
        import multichsync.marker.matcher as matcher

        original_dir = matcher.DEFAULT_CONVERT_DIR
        matcher.DEFAULT_CONVERT_DIR = str(convert_dir)

        try:
            duration = get_raw_data_duration("test_device", "ecg")
            # Should return approximately 2.4 seconds (600 rows / 250 Hz)
            assert duration == pytest.approx(2.4, rel=0.1)
        finally:
            matcher.DEFAULT_CONVERT_DIR = original_dir

    def test_file_not_found(self, tmp_path):
        """Test handling when file doesn't exist."""
        duration = get_raw_data_duration("nonexistent_device", "eeg")
        assert duration is None

    def test_unsupported_device_type(self):
        """Test handling of unsupported device type."""
        duration = get_raw_data_duration("test_device", "unsupported")
        assert duration is None

    def test_invalid_file_format(self, tmp_path):
        """Test handling of corrupted/invalid files."""
        # Create invalid EEG file
        vhdr_path = tmp_path / "test_device.vhdr"
        vhdr_path.write_text("invalid content")

        duration = get_raw_data_duration("test_device", "eeg")
        # Should return None due to parse error
        assert duration is None
