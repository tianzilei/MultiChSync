"""
Unit tests for marker extraction functions.

Tests import from multichsync.marker.extractor:
- extract_biopac_marker
- extract_brainvision_marker
- extract_fnirs_marker
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path


class TestExtractBiopacMarker:
    """Tests for extract_biopac_marker function."""

    def test_basic_extraction(self, temp_dir):
        """Test basic marker extraction from ECG CSV (single column)."""
        from multichsync.marker.extractor import extract_biopac_marker

        # Create single-column CSV with marker signals (0V and 5V transitions)
        csv_path = temp_dir / "test_biopac.csv"
        signal = []
        for i in range(1000):
            if 100 <= i < 110:  # First marker at 5V
                signal.append(5.0)
            elif 500 <= i < 510:  # Second marker at 0V
                signal.append(0.0)
            else:
                signal.append(1.0)  # Background

        df = pd.DataFrame({"Voltage": signal})
        df.to_csv(csv_path, index=False, header=False)

        output_csv = temp_dir / "markers_output.csv"

        # Run extraction with correct sampling rate (1 Hz for this test)
        result = extract_biopac_marker(
            input_csv=csv_path,
            output_csv=output_csv,
            fs=1,  # 1 sample per second for easy calculation
            tolerance=0.2,
        )

        # Verify output
        assert isinstance(result, pd.DataFrame)
        assert "Time(sec)" in result.columns
        assert output_csv.exists()
        # Should detect at least the marker transitions
        assert len(result) >= 2

    def test_no_markers(self, temp_dir):
        """Test extraction when no markers present (no 0/5 volt transitions)."""
        from multichsync.marker.extractor import extract_biopac_marker

        # Create CSV with random voltage values (no 0/5 transitions)
        csv_path = temp_dir / "no_markers.csv"
        df = pd.DataFrame(
            {
                "Voltage": np.random.uniform(1, 2, 500),  # Random values, no markers
            }
        )
        df.to_csv(csv_path, index=False, header=False)

        output_csv = temp_dir / "markers_output.csv"

        # Run extraction - should handle gracefully
        result = extract_biopac_marker(
            input_csv=csv_path,
            output_csv=output_csv,
            fs=100,
            tolerance=0.2,
        )

        # Verify output exists but may be empty
        assert isinstance(result, pd.DataFrame)
        assert "Time(sec)" in result.columns
        assert output_csv.exists()

    def test_custom_tolerance(self, temp_dir):
        """Test marker extraction with custom tolerance."""
        from multichsync.marker.extractor import extract_biopac_marker

        # Create CSV with markers at 0V and 5V
        csv_path = temp_dir / "tolerance_test.csv"

        # Create signal with clear 0V and 5V markers, surrounded by distinct background
        signal = []
        for i in range(100):
            if 10 <= i < 15:  # First marker at 0V
                signal.append(0.0)
            elif 50 <= i < 55:  # Second marker at 5V
                signal.append(5.0)
            else:
                signal.append(1.0)  # Background

        df = pd.DataFrame({"Voltage": signal})
        df.to_csv(csv_path, index=False, header=False)

        # Test with tight tolerance (should only detect exact 0 and 5)
        output_csv_tight = temp_dir / "markers_tight.csv"
        result_tight = extract_biopac_marker(
            input_csv=csv_path,
            output_csv=output_csv_tight,
            fs=1,
            tolerance=0.05,  # Tight tolerance - only exact 0/5 values
        )

        # Test with loose tolerance (should also match background close to 0/5)
        output_csv_loose = temp_dir / "markers_loose.csv"
        result_loose = extract_biopac_marker(
            input_csv=csv_path,
            output_csv=output_csv_loose,
            fs=1,
            tolerance=1.0,  # Very loose tolerance
        )

        # With loose tolerance, more values are classified as 0 or 5,
        # resulting in fewer edges (markers detected)
        assert len(result_loose) <= len(result_tight)


class TestExtractBrainvisionMarker:
    """Tests for extract_brainvision_marker function."""

    def test_basic_extraction(self, temp_dir):
        """Test marker extraction from .vmrk file."""
        from multichsync.marker.extractor import extract_brainvision_marker

        # Create test BrainVision files with correct SamplingInterval= format
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

SamplingInterval=5000
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

        output_csv = temp_dir / "brainvision_markers.csv"

        # Run extraction
        result = extract_brainvision_marker(
            vmrk_path=vmrk_path,
            output_csv=output_csv,
        )

        # Verify output
        assert isinstance(result, pd.DataFrame)
        assert "reference_time" in result.columns
        assert "value" in result.columns
        assert output_csv.exists()

        # Should extract 1 marker (Mk2) - Mk1 is New Segment and is ignored
        assert len(result) == 1
        # The value extracted is the description field (e.g., "S  1" for stimulus markers)
        assert "S" in result.loc[0, "value"]

    def test_stimulus_markers(self, temp_dir):
        """Test extraction of stimulus markers."""
        from multichsync.marker.extractor import extract_brainvision_marker

        # Create test BrainVision files with stimulus markers
        vhdr_content = """Brain Vision Data Exchange Header File Version 1.0

[Common Infos]
Codepage=UTF-8
DataFile=stim_test.eeg
MarkerFile=stim_test.vmrk

[Binary Infos]
BinaryFormat=INT_16

[Channel Infos]
Ch1=Fp1,,0.1

[Coordinates]

SamplingInterval=1000
"""
        # Create markers with different stimulus types
        vmrk_content = """Brain Vision Data Exchange Marker File Version 1.0

[Common Infos]
DataFile=stim_test.eeg

[Marker Infos]
Mk1=New Segment,,0,1,0,0
Mk2=Stimulus,S  1,100,1,0
Mk3=Stimulus,S  2,200,1,0
Mk4=Stimulus,S  1,300,1,0
Mk5=Response,,500,1,0
"""

        vhdr_path = temp_dir / "stim_test.vhdr"
        vmrk_path = temp_dir / "stim_test.vmrk"
        eeg_path = temp_dir / "stim_test.eeg"

        vhdr_path.write_text(vhdr_content)
        vmrk_path.write_text(vmrk_content)
        eeg_path.write_bytes(b"\x00" * 100)

        output_csv = temp_dir / "stim_markers.csv"

        # Run extraction
        result = extract_brainvision_marker(
            vmrk_path=vmrk_path,
            output_csv=output_csv,
        )

        # Verify output structure
        assert isinstance(result, pd.DataFrame)
        assert "reference_time" in result.columns
        assert "value" in result.columns
        assert output_csv.exists()

        # Should extract 4 markers (Mk2, Mk3, Mk4, Mk5) - Mk1 is New Segment
        assert len(result) == 4

        # Verify stimulus markers contain "S" (the stimulus code) in their value
        # The value field contains the description like "S  1" or just the description
        stimulus_markers = result[result["value"].str.contains("S ", na=False)]
        assert len(stimulus_markers) == 3  # S  1, S  2, S  1


class TestExtractFnirsMarker:
    """Tests for extract_fnirs_marker function."""

    def test_basic_extraction(self, temp_dir):
        """Test marker extraction from fNIRS CSV (with Protocol Type column)."""
        from multichsync.marker.extractor import extract_fnirs_marker

        # Create mock fNIRS CSV with Protocol Type
        csv_path = temp_dir / "fnirs_test.csv"

        # fNIRS CSV format with Start Time and Protocol Type
        csv_content = """Start Time,Protocol Type,Other Data
00:00:00.00,Rest,100
00:00:05.00,TaskA,200
00:00:10.00,TaskB,300
00:00:15.00,Rest,150
00:00:20.00,TaskA,250
00:00:25.00,TaskB,350
"""

        csv_path.write_text(csv_content, encoding="utf-8-sig")

        output_csv = temp_dir / "fnirs_markers.csv"

        # Run extraction
        result = extract_fnirs_marker(
            input_csv=csv_path,
            output_csv=output_csv,
        )

        # Verify output
        assert isinstance(result, pd.DataFrame)
        assert "reference_time" in result.columns
        assert "value" in result.columns
        assert output_csv.exists()

        # Should extract all 6 markers
        assert len(result) == 6

        # Verify time conversion (00:00:05.00 -> 5.0 seconds)
        assert result.loc[1, "reference_time"] == 5.0

        # Verify Protocol Type values are extracted
        assert "Rest" in result["value"].values
        assert "TaskA" in result["value"].values
        assert "TaskB" in result["value"].values


class TestExtractMarkerIntegration:
    """Integration tests combining multiple marker extraction scenarios."""

    def test_all_marker_types(self, temp_dir):
        """Test that all three marker extraction functions work correctly."""
        from multichsync.marker.extractor import (
            extract_biopac_marker,
            extract_brainvision_marker,
            extract_fnirs_marker,
        )

        # 1. Create Biopac/ECG marker file (single column)
        ecg_path = temp_dir / "test_ecg.csv"
        signal = [0] * 50 + [5] * 10 + [0] * 50 + [5] * 10 + [0] * 50
        df = pd.DataFrame({"Voltage": signal})
        df.to_csv(ecg_path, index=False, header=False)

        biopac_output = temp_dir / "biopac_markers.csv"
        biopac_result = extract_biopac_marker(ecg_path, biopac_output, fs=1)
        assert biopac_output.exists()
        assert isinstance(biopac_result, pd.DataFrame)

        # 2. Create BrainVision marker file with correct SamplingInterval= format
        vhdr_path = temp_dir / "test.vhdr"
        vmrk_path = temp_dir / "test.vmrk"
        eeg_path = temp_dir / "test.eeg"

        vhdr_path.write_text("""Brain Vision Data Exchange Header File Version 1.0

[Common Infos]
Codepage=UTF-8
DataFile=test.eeg
MarkerFile=test.vmrk

[Binary Infos]
BinaryFormat=INT_16

[Channel Infos]
Ch1=Fp1,,0.1

[Coordinates]

SamplingInterval=1000
""")
        vmrk_path.write_text("""Brain Vision Data Exchange Marker File Version 1.0

[Common Infos]
DataFile=test.eeg

[Marker Infos]
Mk1=New Segment,,0,1,0,0
Mk2=Stimulus,S  1,100,1,0
""")
        eeg_path.write_bytes(b"\x00" * 100)

        brainvision_output = temp_dir / "brainvision_markers.csv"
        brainvision_result = extract_brainvision_marker(vmrk_path, brainvision_output)
        assert brainvision_output.exists()
        assert isinstance(brainvision_result, pd.DataFrame)

        # 3. Create fNIRS marker file
        fnirs_path = temp_dir / "fnirs.csv"
        fnirs_path.write_text(
            "Start Time,Protocol Type\n00:00:00.00,Rest\n00:00:01.00,Task\n",
            encoding="utf-8-sig",
        )

        fnirs_output = temp_dir / "fnirs_markers.csv"
        fnirs_result = extract_fnirs_marker(fnirs_path, fnirs_output)
        assert fnirs_output.exists()
        assert isinstance(fnirs_result, pd.DataFrame)

        # All outputs should be valid DataFrames with expected columns
        assert "Time(sec)" in biopac_result.columns
        assert "reference_time" in brainvision_result.columns
        assert "reference_time" in fnirs_result.columns
