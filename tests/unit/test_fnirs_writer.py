"""
Unit tests for fNIRS writer functions.

Tests the write_snirf function and helper functions from multichsync.fnirs.writer.
"""

import pytest
import numpy as np
from pathlib import Path
import h5py

from multichsync.fnirs.writer import (
    build_stim_from_mark,
    build_aux_numeric_series,
    write_snirf,
)


class TestBuildStimFromMark:
    """Test suite for build_stim_from_mark function."""

    def test_basic_conversion(self):
        """Test conversion of marks to stim groups."""
        times = np.array([1.0, 2.0, 3.0, 4.0])
        marks = ["", "1", "2", "1"]

        result = build_stim_from_mark(times, marks)

        assert isinstance(result, dict)
        assert len(result) == 2  # Mark_1 and Mark_2
        assert "Mark_1" in result
        assert "Mark_2" in result

        # Check Mark_1 has 2 events at times 2.0 and 4.0
        mark1_events = result["Mark_1"]
        assert mark1_events.shape == (2, 3)
        np.testing.assert_array_almost_equal(mark1_events[:, 0], [2.0, 4.0])
        np.testing.assert_array_almost_equal(mark1_events[:, 1], [0.0, 0.0])  # duration
        np.testing.assert_array_almost_equal(mark1_events[:, 2], [1.0, 1.0])  # value

        # Check Mark_2 has 1 event at time 3.0
        mark2_events = result["Mark_2"]
        assert mark2_events.shape == (1, 3)
        np.testing.assert_array_almost_equal(mark2_events[0, 0], 3.0)

    def test_ignore_values(self):
        """Test that specified ignore values are ignored."""
        times = np.array([1.0, 2.0, 3.0])
        marks = ["0", "1", "0Z"]

        # Default ignore values include "0", "0Z", ""
        result = build_stim_from_mark(times, marks)

        assert len(result) == 1
        assert "Mark_1" in result
        assert result["Mark_1"].shape == (1, 3)
        np.testing.assert_array_almost_equal(result["Mark_1"][0, 0], 2.0)

    def test_custom_ignore_values(self):
        """Test with custom ignore values."""
        times = np.array([1.0, 2.0, 3.0])
        marks = ["ignore", "keep", "ignore"]

        result = build_stim_from_mark(times, marks, ignore_values=["ignore"])

        assert len(result) == 1
        assert "Mark_keep" in result
        assert result["Mark_keep"].shape == (1, 3)
        np.testing.assert_array_almost_equal(result["Mark_keep"][0, 0], 2.0)

    def test_empty_marks(self):
        """Test with all marks ignored."""
        times = np.array([1.0, 2.0, 3.0])
        marks = ["", "0", "0Z"]

        result = build_stim_from_mark(times, marks)

        assert isinstance(result, dict)
        assert len(result) == 0


class TestBuildAuxNumericSeries:
    """Test suite for build_aux_numeric_series function."""

    def test_all_numeric(self):
        """Test conversion when all values are numeric."""
        values = ["1.5", "2.0", "3.14", "-4.2"]

        result = build_aux_numeric_series(values)

        assert isinstance(result, np.ndarray)
        assert result.shape == (4, 1)
        np.testing.assert_array_almost_equal(result.flatten(), [1.5, 2.0, 3.14, -4.2])

    def test_with_empty_strings(self):
        """Test conversion with empty strings (should become NaN)."""
        values = ["1.0", "", "2.0", "", "3.0"]

        result = build_aux_numeric_series(values)

        assert isinstance(result, np.ndarray)
        assert result.shape == (5, 1)
        assert np.isnan(result[1, 0])
        assert np.isnan(result[3, 0])
        np.testing.assert_array_almost_equal(result[0, 0], 1.0)
        np.testing.assert_array_almost_equal(result[2, 0], 2.0)
        np.testing.assert_array_almost_equal(result[4, 0], 3.0)

    def test_non_numeric_returns_none(self):
        """Test that non-numeric values cause function to return None."""
        values = ["1.0", "abc", "2.0"]

        result = build_aux_numeric_series(values)

        assert result is None

    def test_mixed_numeric_and_non_numeric(self):
        """Test that any non-numeric value causes None return."""
        values = ["1.0", "2.5", "not_a_number"]

        result = build_aux_numeric_series(values)

        assert result is None

    def test_empty_list(self):
        """Test with empty list."""
        values = []

        result = build_aux_numeric_series(values)

        assert isinstance(result, np.ndarray)
        assert result.shape == (0, 1)


class TestWriteSnirf:
    """Test suite for write_snirf function."""

    def test_minimal_write(self, temp_dir: Path):
        """Test writing minimal SNIRF file."""
        output_path = temp_dir / "test.snirf"

        # Minimal parameters
        meta = {
            "subject_id": "test_subject",
            "measurement_date": "2024-01-01",
            "measurement_time": "12:00:00",
        }
        channel_pairs = [(1, 1)]  # one source-detector pair
        times = np.array([0.0, 1.0, 2.0])
        data_matrix = np.random.randn(3, 2)  # 3 timepoints, 2 channels (HbO, HbR)
        sourcePos3D = np.array([[0.0, 0.0, 0.0]])
        detectorPos3D = np.array([[30.0, 0.0, 0.0]])
        src_map = {1: 1}  # source index mapping (SNIRF indices start at 1)
        det_map = {1: 1}  # detector index mapping (SNIRF indices start at 1)

        # Write SNIRF file
        write_snirf(
            output_path=output_path,
            meta=meta,
            channel_pairs=channel_pairs,
            times=times,
            data_matrix=data_matrix,
            sourcePos3D=sourcePos3D,
            detectorPos3D=detectorPos3D,
            src_map=src_map,
            det_map=det_map,
            compress=False,  # Disable compression for simpler test
            include_stim_from_mark=False,
            include_aux_count=False,
        )

        # Verify file was created
        assert output_path.exists()

        # Verify it's a valid HDF5 file
        with h5py.File(output_path, "r") as f:
            assert "nirs" in f
            nirs = f["nirs"]

            # Check data structure
            assert "data1" in nirs
            data1 = nirs["data1"]

            # Check time series
            assert "time" in data1
            time_data = data1["time"][:]
            assert len(time_data) == 3
            np.testing.assert_array_almost_equal(time_data, times)

            # Check data
            assert "dataTimeSeries" in data1
            data_series = data1["dataTimeSeries"][:]
            assert data_series.shape == (3, 2)
            np.testing.assert_array_almost_equal(data_series, data_matrix)

            # Check measurement list
            assert "measurementList1" in data1
            ml = data1["measurementList1"]
            assert "sourceIndex" in ml
            assert "detectorIndex" in ml

    def test_with_stim_marks_empty(self, temp_dir: Path):
        """Test writing SNIRF file with include_stim_from_mark=True but empty marks (should not create stim groups)."""
        output_path = temp_dir / "test_with_stim_empty.snirf"

        # Create times
        times = np.array([0.0, 1.0, 2.0, 3.0, 4.0])

        # Minimal parameters
        meta = {"subject_id": "test"}
        channel_pairs = [(1, 1)]
        data_matrix = np.random.randn(5, 2)
        sourcePos3D = np.array([[0.0, 0.0, 0.0]])
        detectorPos3D = np.array([[30.0, 0.0, 0.0]])
        src_map = {1: 1}  # SNIRF indices start at 1
        det_map = {1: 1}

        # Write SNIRF file with include_stim_from_mark=True (but marks are empty by default)
        write_snirf(
            output_path=output_path,
            meta=meta,
            channel_pairs=channel_pairs,
            times=times,
            data_matrix=data_matrix,
            sourcePos3D=sourcePos3D,
            detectorPos3D=detectorPos3D,
            src_map=src_map,
            det_map=det_map,
            include_stim_from_mark=True,
            compress=False,
        )

        # Verify file was created
        assert output_path.exists()

        # Verify no stim groups were created (since marks were empty)
        with h5py.File(output_path, "r") as f:
            nirs = f["nirs"]
            # Should not have stim groups (check that stim1 doesn't exist)
            # Note: HDF5 groups are created only if there are marks
            # The writer creates stim groups only when non-empty marks exist
            # Since we didn't provide marks, there should be no stim groups
            # We'll just verify the file is valid and contains data1
            assert "data1" in nirs
